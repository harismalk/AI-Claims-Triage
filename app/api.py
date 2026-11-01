"""FastAPI endpoints for the adjuster queue: list open disputes with the
agent's recommendation, view one case in full, and accept or override it.

Per record/1-truth/ARCH-system-overview.md ("API + UI | Adjuster queue, case
view, accept/override | No" [LLM]), this layer is pure orchestration -- it
never decides anything itself, only calls the router/specialist/gate for a
recommendation and, on a decision, calls write tools through the tool runtime
([[DEC-0001-propose-gate-execute]]). This is the first real executor in the
project: every earlier ticket only tested write tools in isolation.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from app.gate import evaluate
from app.overrides import OverrideRecord, record_override
from app.router import SPECIALIST_PROPOSE_FNS, route_dispute
from app.tool_runtime import ToolRuntime
from app.tools import ClaimView

app = FastAPI(title="Claims Dispute Adjuster API")

# T5.2's React dev server runs on a different origin; this API has no
# authentication yet (MVP scope), so this is permissive by design, not an
# oversight -- tighten before this is ever exposed beyond local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DisputeSummary(BaseModel):
    dispute_id: int
    reason_code: str
    filed_date: date
    status_code: str
    recommended_decision: str | None  # the specialist's substantive proposal, if any exists
    recommended_amount_cents: int | None
    gate_action: Literal["auto_resolve", "escalate"] | None  # None if no specialist proposed anything


class CaseDetail(BaseModel):
    dispute_id: int
    reason_code: str
    reason_description: str | None
    filed_date: date
    status_code: str
    complaint_text: str | None
    claim: ClaimView
    recommended_decision: str | None
    recommended_amount_cents: int | None
    recommended_rationale: str | None
    recommended_evidence_claim_ids: list[int]
    gate_action: Literal["auto_resolve", "escalate"] | None
    gate_reasons: list[str]


class DecisionRequest(BaseModel):
    action: Literal["accept", "override"]
    decision: Literal["reverse", "deny"] | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    reason: str | None = None
    request_key: str | None = None

    @model_validator(mode="after")
    def _override_requires_decision_amount_and_reason(self):
        if self.action == "override":
            if self.decision is None or self.amount_cents is None or not self.reason:
                raise ValueError("override requires decision, amount_cents, and reason")
            if self.decision == "deny" and self.amount_cents != 0:
                raise ValueError("a 'deny' decision must have amount_cents=0")
        return self


class DecisionResponse(BaseModel):
    dispute_id: int
    action: Literal["accept", "override"]
    final_decision: Literal["reverse", "deny"]
    final_amount_cents: int
    claim_id: int


def _runtime() -> ToolRuntime:
    return ToolRuntime(mode="live")


def _recommendation(dispute_id: int, reason_code: str, complaint_text: str | None, runtime: ToolRuntime):
    """Returns (proposal, gate_decision), either of which may be None if no
    specialist exists for this reason code (DOC has none yet; COV never has one)."""
    routing = route_dispute(dispute_id, reason_code, complaint_text)
    propose_fn = SPECIALIST_PROPOSE_FNS.get(routing.specialist) if routing.specialist else None
    if propose_fn is None:
        return None, None
    proposal = propose_fn(dispute_id, runtime)
    gate_decision = evaluate(proposal, runtime)
    return proposal, gate_decision


@app.get("/disputes", response_model=list[DisputeSummary])
def list_disputes():
    """List open disputes with the agent's recommendation attached."""
    runtime = _runtime()
    # There's no "list open disputes" read tool; disp_hdr rows are listed by
    # walking dispute IDs via get_dispute, since that's the only sanctioned
    # path to the legacy database. For the seeded dataset (IDs 1-200) this is
    # cheap; a real system would add a list tool rather than scan a range.
    summaries = []
    for dispute_id in range(1, 201):
        dispute = runtime.call("get_dispute", dispute_id=dispute_id)
        if dispute is None or dispute.status_code != "OPN":
            continue
        proposal, gate_decision = _recommendation(dispute_id, dispute.dispute_type_code, dispute.complaint_text,
                                                    runtime)
        summaries.append(DisputeSummary(
            dispute_id=dispute.dispute_id,
            reason_code=dispute.dispute_type_code,
            filed_date=dispute.filed_date,
            status_code=dispute.status_code,
            recommended_decision=proposal.decision if proposal else None,
            recommended_amount_cents=proposal.amount_cents if proposal else None,
            gate_action=gate_decision.action if gate_decision else None,
        ))
    return summaries


@app.get("/disputes/{dispute_id}", response_model=CaseDetail)
def get_case(dispute_id: int):
    """View one case in full: the dispute, its claim, and the agent's recommendation."""
    runtime = _runtime()
    dispute = runtime.call("get_dispute", dispute_id=dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail=f"no dispute {dispute_id}")

    proposal, gate_decision = _recommendation(dispute_id, dispute.dispute_type_code, dispute.complaint_text, runtime)
    return CaseDetail(
        dispute_id=dispute.dispute_id,
        reason_code=dispute.dispute_type_code,
        reason_description=dispute.dispute_type_description,
        filed_date=dispute.filed_date,
        status_code=dispute.status_code,
        complaint_text=dispute.complaint_text,
        claim=dispute.claim,
        recommended_decision=proposal.decision if proposal else None,
        recommended_amount_cents=proposal.amount_cents if proposal else None,
        recommended_rationale=proposal.rationale if proposal else None,
        recommended_evidence_claim_ids=proposal.evidence_claim_ids if proposal else [],
        gate_action=gate_decision.action if gate_decision else None,
        gate_reasons=gate_decision.reasons if gate_decision else [],
    )


@app.get("/claims/{claim_id}", response_model=ClaimView)
def get_claim(claim_id: int):
    """Fetch one claim's full record. A case's evidence is cited by claim ID
    only; this is what an evidence link in the UI opens."""
    runtime = _runtime()
    claim = runtime.call("lookup_claim", claim_id=claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"no claim {claim_id}")
    return claim


@app.post("/disputes/{dispute_id}/decisions", response_model=DecisionResponse)
def decide_case(dispute_id: int, body: DecisionRequest):
    """Accept the agent's recommendation, or override it. Either way, this
    executes the resolution for real through the write tools."""
    runtime = _runtime()
    dispute = runtime.call("get_dispute", dispute_id=dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail=f"no dispute {dispute_id}")
    if dispute.status_code != "OPN":
        raise HTTPException(status_code=409, detail=f"dispute {dispute_id} is not open (status={dispute.status_code})")

    proposal, _gate_decision = _recommendation(dispute_id, dispute.dispute_type_code, dispute.complaint_text, runtime)

    if body.action == "accept":
        if proposal is None:
            raise HTTPException(status_code=400,
                                 detail="no recommendation exists for this dispute; use action=override")
        final_decision, final_amount_cents = proposal.decision, proposal.amount_cents
    else:
        final_decision, final_amount_cents = body.decision, body.amount_cents

    request_key = body.request_key or str(uuid.uuid4())
    claim_id = dispute.claim.claim_id
    if final_decision == "reverse":
        runtime.call("update_claim_status", claim_id=claim_id, new_status_code="PD", request_key=request_key)
        runtime.call("issue_adjustment", claim_id=claim_id, amount_cents=final_amount_cents,
                     request_key=request_key)
    runtime.call("resolve_dispute", dispute_id=dispute_id, resolution_amount_cents=final_amount_cents,
                 request_key=request_key)

    if body.action == "override":
        record_override(OverrideRecord(
            dispute_id=dispute_id,
            claim_id=claim_id,
            reason_code=dispute.dispute_type_code,
            proposed_decision=proposal.decision if proposal else None,
            proposed_amount_cents=proposal.amount_cents if proposal else None,
            chosen_decision=final_decision,
            chosen_amount_cents=final_amount_cents,
            reason=body.reason,
        ))

    return DecisionResponse(
        dispute_id=dispute_id,
        action=body.action,
        final_decision=final_decision,
        final_amount_cents=final_amount_cents,
        claim_id=claim_id,
    )
