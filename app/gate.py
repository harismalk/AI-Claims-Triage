"""Decision gate: code, not LLM. Re-checks a specialist's proposal against the
live database before allowing auto-resolution. Per
[[DEC-0001-propose-gate-execute]], the LLM never decides its own authority --
this does. Only an executor behind this gate ever calls a write tool; this
module itself never does (see record/1-truth/ARCH-system-overview.md's flow:
gate decides, executor acts).

Every decision -- whether it auto-resolves or escalates -- records the named
rule(s) that allowed or blocked it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.specialists.base import Proposal
from app.tool_runtime import ToolRuntime

AUTO_RESOLVE_LIMIT_CENTS = 50_000  # $500, record/1-truth/DOMAIN-claims-disputes.md
NON_AUTO_RESOLVE_DISPUTE_TYPES = frozenset({"COV"})  # always escalate, per DOMAIN doc

# Prompt-injection markers planted in adversarial complaints (T1.4). A
# complaint showing these is a risk flag: never auto-resolve, regardless of
# how clean the rest of the proposal looks.
INJECTION_MARKERS = (
    "ignore your previous instructions", "system note", "admin mode", "disregard", "override",
)


@dataclass
class GateDecision:
    dispute_id: int
    action: str  # "auto_resolve" | "escalate"
    reasons: list[str] = field(default_factory=list)
    proposal: Proposal | None = None


def _escalate(dispute_id: int, reason: str, proposal: Proposal | None = None) -> GateDecision:
    return GateDecision(dispute_id=dispute_id, action="escalate", reasons=[reason], proposal=proposal)


def evaluate(proposal: Proposal, runtime: ToolRuntime) -> GateDecision:
    """Decide whether to auto-resolve a specialist's proposal, or escalate it.

    Args:
        proposal: the specialist's structured proposal.
        runtime: a ToolRuntime -- every check here is re-verified fresh
            against the database (or recorded trace/snapshot in replay),
            never trusted from the proposal alone.

    Returns:
        A GateDecision with the rule(s) that allowed or blocked it.
    """
    dispute_id = proposal.dispute_id
    dispute = runtime.call("get_dispute", dispute_id=dispute_id)
    if dispute is None:
        return _escalate(dispute_id, f"RULE dispute_exists: no dispute {dispute_id} found", proposal)

    if proposal.decision == "escalate":
        return _escalate(dispute_id, "RULE specialist_escalated: the specialist itself proposed escalation",
                          proposal)

    if dispute.dispute_type_code in NON_AUTO_RESOLVE_DISPUTE_TYPES:
        return _escalate(
            dispute_id,
            f"RULE coverage_always_escalates: dispute type {dispute.dispute_type_code!r} is never auto-resolved",
            proposal,
        )

    if proposal.amount_cents > AUTO_RESOLVE_LIMIT_CENTS:
        return _escalate(
            dispute_id,
            f"RULE authority_limit: amount_cents={proposal.amount_cents} exceeds the "
            f"${AUTO_RESOLVE_LIMIT_CENTS / 100:.0f} auto-resolve limit",
            proposal,
        )

    complaint_text = (dispute.complaint_text or "").lower()
    if any(marker in complaint_text for marker in INJECTION_MARKERS):
        return _escalate(
            dispute_id,
            "RULE risk_flag: complaint text shows signs of a prompt-injection attempt",
            proposal,
        )

    if not proposal.evidence_claim_ids:
        return _escalate(dispute_id, "RULE evidence_required: proposal cited no evidence", proposal)

    for claim_id in proposal.evidence_claim_ids:
        claim = runtime.call("lookup_claim", claim_id=claim_id)
        if claim is None:
            return _escalate(dispute_id, f"RULE evidence_exists: cited claim {claim_id} does not exist",
                              proposal)
        if claim.member_id != dispute.claim.member_id:
            return _escalate(
                dispute_id,
                f"RULE evidence_supports_claim: cited claim {claim_id} belongs to a different "
                "member than the disputed claim",
                proposal,
            )

    if dispute.claim.claim_id not in proposal.evidence_claim_ids:
        return _escalate(
            dispute_id,
            "RULE evidence_supports_claim: proposal does not cite the disputed claim itself",
            proposal,
        )

    return GateDecision(
        dispute_id=dispute_id,
        action="auto_resolve",
        reasons=[
            "RULE evidence_verified: every cited claim exists and belongs to the disputed member",
            f"RULE authority_limit: amount_cents={proposal.amount_cents} is within the "
            f"${AUTO_RESOLVE_LIMIT_CENTS / 100:.0f} limit",
            f"RULE dispute_type_eligible: {dispute.dispute_type_code!r} is auto-resolve eligible",
        ],
        proposal=proposal,
    )
