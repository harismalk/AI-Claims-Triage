"""Resolution letter drafting. Per record/1-truth/ARCH-system-overview.md,
writes the member letter from the gate's final auto-resolve decision.

Per [[DEC-0005-specialist-reason-fn]]'s pattern, the LLM step is a pluggable
letter_fn, defaulting to a deterministic template. Critically, the default
template never interpolates the specialist's internal `rationale` string --
that's full of claim IDs, plan codes, and procedure codes, meant for an
auditor, not a member. Instead it uses a short, hardcoded plain-language
phrase per reason code, so no internal code or claim-system jargon can leak
into a letter no matter what a specialist's rationale happens to say.
"""
from __future__ import annotations

from typing import Callable

from app.gate import GateDecision
from app.tool_runtime import ToolRuntime

# Plain-language reason, one per dispute type. Deliberately static strings --
# never built from a specialist's rationale -- so no internal code can leak.
REASON_PLAIN_LANGUAGE = {
    "DUP": "the charge was mistakenly treated as a duplicate when it was a separate service",
    "BIL": "the amount you were charged did not match your plan's terms for that service",
    "DOC": "the required documentation was on file but was not reflected in the original decision",
}


def default_letter_fn(decision: GateDecision, member_name: str, reason_code: str) -> str:
    proposal = decision.proposal
    reason_phrase = REASON_PLAIN_LANGUAGE.get(reason_code, "the circumstances of your claim")

    if proposal.decision == "reverse":
        body = (
            f"We have reviewed your dispute and found that {reason_phrase}. We are issuing a "
            f"payment of ${proposal.amount_cents / 100:.2f} to resolve this matter."
        )
    elif proposal.decision == "deny":
        body = (
            f"We have reviewed your dispute. After careful review, regarding {reason_phrase}, we "
            "have confirmed that the original decision was correct, and no additional payment is owed."
        )
    else:
        raise ValueError(f"cannot draft a resolution letter for decision {proposal.decision!r}")

    return (
        f"Dear {member_name},\n\n"
        f"{body}\n\n"
        "If you have any questions about this decision, please contact Member Services.\n\n"
        "Sincerely,\nMember Services"
    )


def draft_letter(
    decision: GateDecision,
    runtime: ToolRuntime,
    letter_fn: Callable[[GateDecision, str, str], str] = default_letter_fn,
) -> str:
    """Draft a resolution letter for an auto-resolved dispute.

    Args:
        decision: a GateDecision with action == "auto_resolve". Escalated
            decisions have no letter yet -- that happens once an adjuster
            resolves them.
        runtime: a ToolRuntime -- the only way this ever touches the legacy
            system, to look up the member's name and the dispute's type.
        letter_fn: the letter-writing step; swappable for a real LLM.

    Returns:
        The letter text.

    Raises:
        ValueError: if decision.action is not "auto_resolve".
    """
    if decision.action != "auto_resolve":
        raise ValueError(f"cannot draft a letter for a {decision.action!r} decision; it isn't resolved yet")

    dispute = runtime.call("get_dispute", dispute_id=decision.dispute_id)
    member = runtime.call("get_member", member_id=dispute.claim.member_id)
    member_name = f"{member.first_name} {member.last_name}"
    return letter_fn(decision, member_name, dispute.dispute_type_code)
