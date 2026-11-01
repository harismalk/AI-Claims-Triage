"""Duplicate-denial specialist. Its prompt (prompt.md) and knowledge file
(knowledge.md) live alongside this module and belong to no other specialist.

Per [[DEC-0001-propose-gate-execute]] it only ever proposes; it never calls a
write tool. Per [[DEC-0005-specialist-reason-fn]] its LLM reasoning step is a
pluggable reason_fn, defaulting to a deterministic implementation of
knowledge.md's rule, so tests run offline and deterministically; a real LLM
call can replace the default without touching callers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.specialists.base import Proposal
from app.tool_runtime import ToolRuntime
from app.tools import ClaimView, DisputeView

HERE = Path(__file__).resolve().parent
PROMPT = (HERE / "prompt.md").read_text()
KNOWLEDGE = (HERE / "knowledge.md").read_text()

ALLOWED_TOOLS = frozenset({"get_dispute", "lookup_claim", "find_similar_claims"})


class DisallowedToolError(Exception):
    """Raised if the specialist tries to call a tool outside its own allowed set."""


def _call(runtime: ToolRuntime, tool_name: str, **kwargs):
    if tool_name not in ALLOWED_TOOLS:
        raise DisallowedToolError(f"duplicate_denial specialist may not call '{tool_name}'")
    return runtime.call(tool_name, **kwargs)


def default_reason_fn(dispute: DisputeView, similar: list[ClaimView]) -> Proposal:
    """The specialist's judgment, following knowledge.md: a match on the same
    procedure code is a genuine duplicate (deny); a match on a different
    procedure code is a false positive even if the date matches (reverse) --
    that's the same-date-different-procedure trap this rule exists to avoid.

    find_similar_claims can also return a claim that merely happens to share
    the same procedure code elsewhere, unrelated to this denial. The claim the
    legacy system actually flagged this one against is the one from the same
    visit (shared VISIT_ID); prefer that pool before falling back to the full
    candidate list."""
    disputed = dispute.claim
    same_visit = [c for c in similar if disputed.visit_group_id and c.visit_group_id == disputed.visit_group_id]
    pool = same_visit or similar
    match = next((c for c in pool if c.procedure_code == disputed.procedure_code), None)
    evidence = sorted({disputed.claim_id, *(c.claim_id for c in pool)})

    if match is not None:
        return Proposal(
            dispute_id=dispute.dispute_id,
            decision="deny",
            amount_cents=0,
            evidence_claim_ids=evidence,
            rationale=(f"Claim {disputed.claim_id} and claim {match.claim_id} are the same "
                       f"procedure ({disputed.procedure_code}) for the same member and provider: "
                       "a genuine duplicate."),
        )
    return Proposal(
        dispute_id=dispute.dispute_id,
        decision="reverse",
        amount_cents=disputed.billed_amount_cents,
        evidence_claim_ids=evidence,
        rationale=(f"Claim {disputed.claim_id} was denied as a duplicate, but the claim(s) it was "
                   "matched against are for a different procedure code. Sharing a visit or date does "
                   "not make two different procedures a duplicate; the denial was incorrect."),
    )


def propose(
    dispute_id: int,
    runtime: ToolRuntime,
    reason_fn: Callable[[DisputeView, list[ClaimView]], Proposal] = default_reason_fn,
) -> Proposal:
    """Produce a structured proposal for a DUP dispute.

    Args:
        dispute_id: the dispute to review.
        runtime: a ToolRuntime (live or replay) -- the only way this
            specialist ever touches the legacy system.
        reason_fn: the specialist's reasoning step; swappable for a real LLM.

    Returns:
        A Proposal. Never calls a write tool.
    """
    dispute = _call(runtime, "get_dispute", dispute_id=dispute_id)
    similar = _call(runtime, "find_similar_claims", claim_id=dispute.claim.claim_id)
    return reason_fn(dispute, similar)
