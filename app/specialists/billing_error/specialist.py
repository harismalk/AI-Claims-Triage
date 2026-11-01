"""Billing-error specialist. Its prompt (prompt.md) and knowledge file
(knowledge.md) live alongside this module and belong to no other specialist.

Per [[DEC-0001-propose-gate-execute]] it only ever proposes; it never calls a
write tool. Per [[DEC-0005-specialist-reason-fn]] its LLM reasoning step is a
pluggable reason_fn, defaulting to a deterministic implementation of
knowledge.md's rule, so tests run offline and deterministically.

Note: this specialist proposes the substantive judgment only. If the overage
is above the $500 auto-resolve limit (record/1-truth/DOMAIN-claims-disputes.md),
it still proposes "reverse" with the full overage amount -- enforcing the
authority limit is the decision gate's job (T3.4), not the specialist's.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.generate_data import PROC_CATALOG
from app.plans import Plan
from app.specialists.base import Proposal
from app.tool_runtime import ToolRuntime
from app.tools import DisputeView, MemberView

HERE = Path(__file__).resolve().parent
PROMPT = (HERE / "prompt.md").read_text()
KNOWLEDGE = (HERE / "knowledge.md").read_text()

ALLOWED_TOOLS = frozenset({"get_dispute", "get_member", "get_plan_terms"})


class DisallowedToolError(Exception):
    """Raised if the specialist tries to call a tool outside its own allowed set."""


def _call(runtime: ToolRuntime, tool_name: str, **kwargs):
    if tool_name not in ALLOWED_TOOLS:
        raise DisallowedToolError(f"billing_error specialist may not call '{tool_name}'")
    return runtime.call(tool_name, **kwargs)


def default_reason_fn(dispute: DisputeView, member: MemberView, plan: Plan) -> Proposal:
    """The specialist's judgment, following knowledge.md: compare the claim's
    billed amount to the plan's copay for its service type."""
    disputed = dispute.claim
    service_type = PROC_CATALOG.get(disputed.procedure_code, (None,))[0]
    plan_copay_cents = plan.copays_cents.get(service_type) if service_type else None

    if plan_copay_cents is None:
        return Proposal(
            dispute_id=dispute.dispute_id,
            decision="escalate",
            amount_cents=0,
            evidence_claim_ids=[disputed.claim_id],
            rationale=(f"Plan {plan.plan_code} has no defined copay for service type "
                       f"{service_type!r} (claim {disputed.claim_id}, procedure "
                       f"{disputed.procedure_code}); needs human review."),
        )

    overage = disputed.billed_amount_cents - plan_copay_cents
    if overage > 0:
        return Proposal(
            dispute_id=dispute.dispute_id,
            decision="reverse",
            amount_cents=overage,
            evidence_claim_ids=[disputed.claim_id],
            rationale=(f"Plan {plan.plan_code}'s copay for {service_type} is "
                       f"${plan_copay_cents / 100:.2f}, but claim {disputed.claim_id} charged "
                       f"${disputed.billed_amount_cents / 100:.2f}: a ${overage / 100:.2f} overcharge."),
        )
    return Proposal(
        dispute_id=dispute.dispute_id,
        decision="deny",
        amount_cents=0,
        evidence_claim_ids=[disputed.claim_id],
        rationale=(f"Claim {disputed.claim_id} charged ${disputed.billed_amount_cents / 100:.2f}, "
                   f"matching plan {plan.plan_code}'s ${plan_copay_cents / 100:.2f} copay for "
                   f"{service_type}. No billing error."),
    )


def propose(
    dispute_id: int,
    runtime: ToolRuntime,
    reason_fn: Callable[[DisputeView, MemberView, Plan], Proposal] = default_reason_fn,
) -> Proposal:
    """Produce a structured proposal for a BIL dispute.

    Args:
        dispute_id: the dispute to review.
        runtime: a ToolRuntime (live or replay) -- the only way this
            specialist ever touches the legacy system.
        reason_fn: the specialist's reasoning step; swappable for a real LLM.

    Returns:
        A Proposal. Never calls a write tool.
    """
    dispute = _call(runtime, "get_dispute", dispute_id=dispute_id)
    member = _call(runtime, "get_member", member_id=dispute.claim.member_id)
    plan = _call(runtime, "get_plan_terms", plan_code=member.plan_code)
    return reason_fn(dispute, member, plan)
