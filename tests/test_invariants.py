"""Tests for evals/invariants.py and evals/suite.py.

The "real system" checks need the seeded live database (to build the golden
dataset -- golden_cases is a session-scoped fixture shared with
test_golden.py and test_scorers.py, see tests/conftest.py); the "synthetic
violation" checks construct GoldenCase/GateDecision objects by hand and need
no database at all -- they prove each checker actually detects what it
claims to, not just that today's system happens to be clean.
"""
from app.gate import AUTO_RESOLVE_LIMIT_CENTS, GateDecision
from app.specialists.base import Proposal
from app.tool_runtime import ToolCallRecord
from evals.golden import GoldenCase
from evals.invariants import (
    check_all,
    check_auto_resolve_authority,
    check_specialist_tool_allowlist,
    check_write_tools_called_at_most_once,
)
from evals.suite import run_suite


def _bare_case(dispute_id=1, category="should_reverse", reason_code="DUP", decision="reverse",
                amount_cents=100) -> GoldenCase:
    return GoldenCase(
        dispute_id=dispute_id, category=category, filed_reason_code=reason_code,
        complaint_text="x", expected_decision=decision, expected_amount_cents=amount_cents,
        expected_evidence_claim_ids=[1],
    )


# ---------------------------------------------------------------- real system

def test_real_system_has_zero_invariant_violations(golden_cases):
    assert check_all(golden_cases) == []


def test_real_suite_passes(golden_cases):
    result = run_suite(golden_cases)
    assert result.passed
    assert result.violations == []
    assert result.scores


# ------------------------------------------------------------- synthetic: 1

def test_auto_resolve_over_limit_is_detected():
    proposal = Proposal(dispute_id=1, decision="reverse", amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1,
                         evidence_claim_ids=[1], rationale="x")
    case = _bare_case(amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1)
    case.proposal = proposal
    case.gate_decision = GateDecision(dispute_id=1, action="auto_resolve", reasons=["bug"], proposal=proposal)

    violations = check_auto_resolve_authority(case)
    assert any(v.invariant == "never_auto_resolve_over_limit" for v in violations)


def test_auto_resolve_coverage_dispute_is_detected():
    proposal = Proposal(dispute_id=1, decision="reverse", amount_cents=100, evidence_claim_ids=[1], rationale="x")
    case = _bare_case(reason_code="COV")
    case.proposal = proposal
    case.gate_decision = GateDecision(dispute_id=1, action="auto_resolve", reasons=["bug"], proposal=proposal)

    violations = check_auto_resolve_authority(case)
    assert any(v.invariant == "never_auto_resolve_coverage" for v in violations)


def test_properly_escalated_decisions_raise_no_violation():
    proposal = Proposal(dispute_id=1, decision="reverse", amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1,
                         evidence_claim_ids=[1], rationale="x")
    case = _bare_case(amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1)
    case.proposal = proposal
    case.gate_decision = GateDecision(dispute_id=1, action="escalate", reasons=["authority_limit"],
                                       proposal=proposal)
    assert check_auto_resolve_authority(case) == []


# ------------------------------------------------------------- synthetic: 2

def test_write_tool_called_twice_is_detected():
    trace = [
        ToolCallRecord("issue_adjustment", {"claim_id": 1, "amount_cents": 100, "request_key": "a"}, None),
        ToolCallRecord("issue_adjustment", {"claim_id": 1, "amount_cents": 100, "request_key": "b"}, None),
    ]
    violations = check_write_tools_called_at_most_once(1, trace)
    assert len(violations) == 1
    assert violations[0].invariant == "write_tool_called_at_most_once"


def test_write_tool_called_once_raises_no_violation():
    trace = [ToolCallRecord("issue_adjustment", {"claim_id": 1}, None),
             ToolCallRecord("get_dispute", {"dispute_id": 1}, None)]
    assert check_write_tools_called_at_most_once(1, trace) == []


# ------------------------------------------------------------- synthetic: 3

def test_specialist_calling_a_disallowed_tool_is_detected():
    case = _bare_case(reason_code="BIL")
    case.specialist_trace = [
        ToolCallRecord("get_dispute", {"dispute_id": 1}, None),
        ToolCallRecord("find_similar_claims", {"claim_id": 1}, None),  # not in billing_error's allowlist
    ]
    violations = check_specialist_tool_allowlist(case)
    assert len(violations) == 1
    assert violations[0].invariant == "specialist_tool_allowlist"


def test_specialist_calling_only_allowed_tools_raises_no_violation():
    case = _bare_case(reason_code="BIL")
    case.specialist_trace = [
        ToolCallRecord("get_dispute", {"dispute_id": 1}, None),
        ToolCallRecord("get_member", {"member_id": 1}, None),
        ToolCallRecord("get_plan_terms", {"plan_code": "GOLD"}, None),
    ]
    assert check_specialist_tool_allowlist(case) == []


def test_reason_codes_with_no_specialist_are_not_checked():
    case = _bare_case(reason_code="DOC")
    case.specialist_trace = [ToolCallRecord("anything", {}, None)]
    assert check_specialist_tool_allowlist(case) == []


# ------------------------------------------------------------- criterion 4

def test_suite_fails_if_any_invariant_is_violated_even_with_perfect_scores(golden_cases):
    clean_result = run_suite(golden_cases)
    assert clean_result.passed  # the real system, with perfect T4.2 scores

    proposal = Proposal(dispute_id=1, decision="reverse", amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1,
                         evidence_claim_ids=[1], rationale="x")
    broken_case = _bare_case(dispute_id=999_999, amount_cents=AUTO_RESOLVE_LIMIT_CENTS + 1)
    broken_case.proposal = proposal
    broken_case.gate_decision = GateDecision(dispute_id=999_999, action="auto_resolve",
                                              reasons=["bug"], proposal=proposal)

    broken_result = run_suite(golden_cases + [broken_case])
    assert not broken_result.passed
    assert any(v.invariant == "never_auto_resolve_over_limit" for v in broken_result.violations)
