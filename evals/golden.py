"""Golden dataset built from the T1.3 answer key.

Every dispute T1.3 planted becomes a GoldenCase: scenario-type metadata
(category, reason code), the input a specialist/router would see, the correct
answer, and -- critically -- a recorded trace of the real tool calls the
router -> specialist -> gate pipeline made the one time this was run live,
plus a DB snapshot reference (claim/dispute IDs) so app.tool_runtime can
rebuild a snapshot. Together these let T4.2's scorers replay every case
without touching the live legacy database (see T2.3).

Disputes whose reason code has no specialist yet (DOC, COV) still get a case
-- just with a minimal trace (the dispute lookup only) -- so the golden
dataset covers the full answer key, not only the reason codes with a built
specialist.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.gate import evaluate
from app.generate_data import generate_dataset
from app.router import REASON_TO_SPECIALIST
from app.specialists.base import Proposal
from app.specialists.billing_error.specialist import propose as propose_billing_error
from app.specialists.duplicate_denial.specialist import propose as propose_duplicate_denial
from app.tool_runtime import ToolCallRecord, ToolRuntime

SPECIALIST_PROPOSE_FNS = {
    "duplicate_denial": propose_duplicate_denial,
    "billing_error": propose_billing_error,
}


@dataclass
class GoldenCase:
    dispute_id: int
    category: str                 # scenario-type metadata: should_reverse | denial_correct | edge | over_limit | adversarial
    filed_reason_code: str        # scenario-type metadata: DUP | BIL | DOC | COV
    complaint_text: str | None    # the input a specialist/router would see
    expected_decision: str
    expected_amount_cents: int
    expected_evidence_claim_ids: list[int]
    recorded_trace: list[ToolCallRecord] = field(default_factory=list)
    snapshot_claim_ids: list[int] = field(default_factory=list)
    snapshot_dispute_ids: list[int] = field(default_factory=list)
    proposal: Proposal | None = None  # the specialist's proposal, if one exists for this reason code


def _build_case(disp, row) -> GoldenCase:
    runtime = ToolRuntime(mode="live")
    dispute = runtime.call("get_dispute", dispute_id=disp.disp_id)

    specialist_name = REASON_TO_SPECIALIST.get(row.reason_code)
    propose_fn = SPECIALIST_PROPOSE_FNS.get(specialist_name)
    proposal = None
    if propose_fn is not None:
        proposal = propose_fn(disp.disp_id, runtime)
        evaluate(proposal, runtime)

    claim_ids = sorted({dispute.claim.claim_id, *row.evidence_claim_ids})
    return GoldenCase(
        dispute_id=disp.disp_id,
        category=row.category,
        filed_reason_code=row.reason_code,
        complaint_text=disp.complaint_text,
        expected_decision=row.decision,
        expected_amount_cents=row.amount_cents,
        expected_evidence_claim_ids=row.evidence_claim_ids,
        recorded_trace=list(runtime.history),
        snapshot_claim_ids=claim_ids,
        snapshot_dispute_ids=[disp.disp_id],
        proposal=proposal,
    )


def build_golden_dataset(seed: int = 42) -> list[GoldenCase]:
    """Build the full golden dataset by running the real pipeline once, live,
    against the seeded database -- for every one of T1.3's 200 disputes."""
    dataset = generate_dataset(seed)
    answer_by_disp_id = {row.disp_id: row for row in dataset.answer_key}
    return [_build_case(disp, answer_by_disp_id[disp.disp_id]) for disp in dataset.disputes]
