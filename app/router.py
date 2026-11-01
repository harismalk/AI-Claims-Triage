"""Deterministic router: picks a specialist from the dispute's reason code and
simple keyword rules. Per [[DEC-0002-deterministic-router]], an LLM classifier
runs only as a logged fallback when the reason code is missing or appears to
contradict the complaint text -- never on the normal path.

classify_fn is a pluggable fallback classifier, not wired to a real LLM yet
(the spec's "LLM provider sits behind one interface" is future work). Callers
in CP3+ can pass a real classifier; the default stub never resolves anything,
which is fine -- the fallback path is rare and always logged either way.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.specialists.billing_error.specialist import propose as propose_billing_error
from app.specialists.duplicate_denial.specialist import propose as propose_duplicate_denial

# record/1-truth/DOMAIN-claims-disputes.md dispute types. COV maps to no
# specialist: coverage disputes always escalate directly, per that doc.
REASON_TO_SPECIALIST: dict[str, str | None] = {
    "DUP": "duplicate_denial",
    "BIL": "billing_error",
    "DOC": "missing_documents",
    "COV": None,
}

# specialist name -> its propose() function. "missing_documents" has no entry
# yet -- no specialist is built for DOC (see T3.1's report); callers must
# handle a missing key the same way they handle no specialist at all.
SPECIALIST_PROPOSE_FNS: dict[str, Callable] = {
    "duplicate_denial": propose_duplicate_denial,
    "billing_error": propose_billing_error,
}

REASON_KEYWORDS: dict[str, tuple[str, ...]] = {
    "DUP": ("duplicate", "twice", "two entries", "two different", "same visit", "same claim"),
    "BIL": ("copay", "charged", "overcharged", "billing", "bill", "amount i was charged"),
    "DOC": ("document", "paperwork", "documentation"),
    "COV": ("covered", "coverage", "not covered", "exclude", "exclusion"),
}


def default_fallback_classifier(complaint_text: str | None) -> str | None:
    """Stub fallback classifier: never resolves. Replace with a real LLM-backed
    classifier once the project has one; the fallback path logs regardless."""
    return None


@dataclass
class RoutingDecision:
    dispute_id: int
    specialist: str | None   # None means "no specialist -- escalate directly" (COV)
    reason_code: str | None  # the reason code actually used to route (rule or fallback)
    used_fallback: bool
    fallback_reason: str | None = None


def _keywords_match(reason_code: str, complaint_text: str) -> bool:
    text = (complaint_text or "").lower()
    return any(k in text for k in REASON_KEYWORDS.get(reason_code, ()))


def _contradicts(reason_code: str, complaint_text: str) -> bool:
    """True if the complaint text strongly suggests a different reason code
    and shows no sign of the stated one."""
    if _keywords_match(reason_code, complaint_text):
        return False
    return any(
        other_code != reason_code and _keywords_match(other_code, complaint_text)
        for other_code in REASON_KEYWORDS
    )


def route_dispute(
    dispute_id: int,
    reason_code: str | None,
    complaint_text: str | None,
    classify_fn: Callable[[str | None], str | None] = default_fallback_classifier,
    fallback_log: list[dict] | None = None,
) -> RoutingDecision:
    """Route one dispute to a specialist.

    Args:
        dispute_id: the dispute's ID, for logging.
        reason_code: the dispute's DISP_TYP_CD (DUP/BIL/DOC/COV), or None/empty
            if missing.
        complaint_text: the member's complaint text.
        classify_fn: fallback LLM classifier, called ONLY when reason_code is
            missing or contradicts complaint_text. Must return one of
            REASON_TO_SPECIALIST's keys, or None.
        fallback_log: if given, a fallback use is appended to it as
            {"dispute_id", "reason", "classifier_result"}.

    Returns:
        A RoutingDecision. used_fallback is True only if classify_fn was called.
    """
    if reason_code and not _contradicts(reason_code, complaint_text):
        return RoutingDecision(dispute_id, REASON_TO_SPECIALIST.get(reason_code), reason_code, used_fallback=False)

    why = "missing reason code" if not reason_code else f"reason code {reason_code!r} contradicts the complaint text"
    resolved = classify_fn(complaint_text)
    if fallback_log is not None:
        fallback_log.append({"dispute_id": dispute_id, "reason": why, "classifier_result": resolved})
    return RoutingDecision(dispute_id, REASON_TO_SPECIALIST.get(resolved), resolved, used_fallback=True,
                            fallback_reason=why)
