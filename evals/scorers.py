"""Code scorers for the T4.1 golden dataset. Each case's actual outcome is
re-derived by replaying its recorded trace through the router and gate --
never touching the live database (see T2.3) -- and compared against the
T1.3 answer key. Results are reported per dispute type (reason code) and per
scenario type (category), per [[DEC-0002-deterministic-router]] and
[[DEC-0001-propose-gate-execute]].
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.router import REASON_TO_SPECIALIST, route_dispute
from evals.golden import GoldenCase, build_golden_dataset

# The answer key's "decision" for over_limit is the GATE's authority-limit
# override ("escalate"), already tested in isolation by T3.4 -- not what the
# specialist itself should substantively propose (tested in isolation by
# T3.3, which expects "reverse"). Scoring specialist correctness here, not
# gate correctness, so compare against the specialist-level expectation.
EXPECTED_SPECIALIST_DECISION_OVERRIDES = {"over_limit": "reverse"}


@dataclass
class CaseScore:
    dispute_id: int
    category: str
    reason_code: str
    has_specialist: bool
    routing_correct: bool
    decision_correct: bool | None
    amount_correct: bool | None
    evidence_valid: bool | None


def _poison_pill_classifier(_complaint_text):
    raise AssertionError("fallback classifier was called on a case with a present, consistent reason code")


def score_case(case: GoldenCase) -> CaseScore:
    """Score one golden case's SPECIALIST correctness on all four dimensions
    where scorable. Gate-level correctness (authority limit, risk flag,
    coverage-always-escalates) is a separate concern, already tested in
    isolation by T3.4 -- scoring it again here would conflate two different
    questions ("did the specialist get the facts right?" vs. "did the gate
    correctly override it anyway?")."""
    routing = route_dispute(case.dispute_id, case.filed_reason_code, case.complaint_text,
                             classify_fn=_poison_pill_classifier)
    expected_specialist = REASON_TO_SPECIALIST.get(case.filed_reason_code)
    routing_correct = routing.specialist == expected_specialist and not routing.used_fallback

    decision_correct = amount_correct = evidence_valid = None
    has_specialist = case.proposal is not None

    if case.filed_reason_code == "COV":
        # No specialist exists for COV; the system is trivially correct here
        # as long as it never auto-resolves a coverage dispute -- which, with
        # no proposal generated at all, it structurally cannot.
        decision_correct = True
    elif has_specialist:
        expected_decision = EXPECTED_SPECIALIST_DECISION_OVERRIDES.get(case.category, case.expected_decision)
        decision_correct = case.proposal.decision == expected_decision
        amount_correct = case.proposal.amount_cents == case.expected_amount_cents
        evidence_valid = set(case.proposal.evidence_claim_ids) == set(case.expected_evidence_claim_ids)

    return CaseScore(
        dispute_id=case.dispute_id,
        category=case.category,
        reason_code=case.filed_reason_code,
        has_specialist=has_specialist or case.filed_reason_code == "COV",
        routing_correct=routing_correct,
        decision_correct=decision_correct,
        amount_correct=amount_correct,
        evidence_valid=evidence_valid,
    )


def score_all(cases: list[GoldenCase]) -> list[CaseScore]:
    return [score_case(c) for c in cases]


def _rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def _group_report(scores: list[CaseScore], key_fn) -> dict:
    groups: dict = defaultdict(list)
    for s in scores:
        groups[key_fn(s)].append(s)
    out = {}
    for key, group in groups.items():
        out[key] = {
            "n": len(group),
            "routing_accuracy": _rate([s.routing_correct for s in group]),
            "decision_accuracy": _rate([s.decision_correct for s in group if s.decision_correct is not None]),
            "amount_accuracy": _rate([s.amount_correct for s in group if s.amount_correct is not None]),
            "evidence_validity": _rate([s.evidence_valid for s in group if s.evidence_valid is not None]),
        }
    return out


def report(scores: list[CaseScore]) -> dict:
    """Results grouped per dispute type (reason code) and per scenario type (category)."""
    return {
        "by_reason_code": _group_report(scores, lambda s: s.reason_code),
        "by_category": _group_report(scores, lambda s: s.category),
    }


def _print_group(title: str, group_report: dict) -> None:
    print(f"\n{title}:")
    for key in sorted(group_report):
        r = group_report[key]

        def fmt(v):
            return "n/a" if v is None else f"{v:.0%}"

        print(f"  {key:<16} n={r['n']:<4} routing={fmt(r['routing_accuracy'])} "
              f"decision={fmt(r['decision_accuracy'])} amount={fmt(r['amount_accuracy'])} "
              f"evidence={fmt(r['evidence_validity'])}")


def main() -> None:
    cases = build_golden_dataset()
    scores = score_all(cases)
    result = report(scores)
    print(f"scored {len(scores)} golden cases")
    _print_group("By dispute type (reason code)", result["by_reason_code"])
    _print_group("By scenario type (category)", result["by_category"])


if __name__ == "__main__":
    main()
