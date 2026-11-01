"""Tests for evals/scorers.py against the seeded (live) legacy database.

golden_cases is a session-scoped fixture shared with test_golden.py and
test_invariants.py -- see tests/conftest.py."""
import pytest

from evals.scorers import CaseScore, report, score_all, score_case

REASON_CODES = {"DUP", "BIL", "DOC", "COV"}
SCENARIO_CATEGORIES = {"should_reverse", "denial_correct", "edge", "over_limit", "adversarial"}


@pytest.fixture(scope="module")
def scores(golden_cases):
    return score_all(golden_cases)


def test_score_case_structure_for_dup_and_bil(golden_cases):
    scorable = [c for c in golden_cases if c.filed_reason_code in ("DUP", "BIL")]
    assert scorable
    for case in scorable:
        s = score_case(case)
        assert isinstance(s, CaseScore)
        assert s.has_specialist
        assert isinstance(s.routing_correct, bool)
        assert isinstance(s.decision_correct, bool)
        assert isinstance(s.amount_correct, bool)
        assert isinstance(s.evidence_valid, bool)


def test_score_case_structure_for_doc_has_no_specialist_scores(golden_cases):
    doc_cases = [c for c in golden_cases if c.filed_reason_code == "DOC"]
    assert doc_cases
    for case in doc_cases:
        s = score_case(case)
        assert not s.has_specialist
        assert isinstance(s.routing_correct, bool)
        assert s.decision_correct is None
        assert s.amount_correct is None
        assert s.evidence_valid is None


def test_score_case_structure_for_cov_scores_decision_only(golden_cases):
    cov_cases = [c for c in golden_cases if c.filed_reason_code == "COV"]
    assert cov_cases
    for case in cov_cases:
        s = score_case(case)
        assert s.has_specialist  # trivially "has" correctness in the sense of always escalating
        assert s.decision_correct is True
        assert s.amount_correct is None
        assert s.evidence_valid is None


def test_report_groups_by_reason_code_and_category(scores, golden_cases):
    result = report(scores)
    assert set(result["by_reason_code"]) == REASON_CODES
    assert set(result["by_category"]) == SCENARIO_CATEGORIES

    for code, group in result["by_reason_code"].items():
        expected_n = sum(1 for c in golden_cases if c.filed_reason_code == code)
        assert group["n"] == expected_n
    for cat, group in result["by_category"].items():
        expected_n = sum(1 for c in golden_cases if c.category == cat)
        assert group["n"] == expected_n


def test_routing_accuracy_is_100_percent_everywhere(scores):
    result = report(scores)
    for group in {**result["by_reason_code"], **result["by_category"]}.values():
        assert group["routing_accuracy"] == 1.0


def test_decision_amount_evidence_accuracy_is_100_percent_where_scorable(scores):
    result = report(scores)
    for code in ("DUP", "BIL"):
        group = result["by_reason_code"][code]
        assert group["decision_accuracy"] == 1.0
        assert group["amount_accuracy"] == 1.0
        assert group["evidence_validity"] == 1.0

    cov = result["by_reason_code"]["COV"]
    assert cov["decision_accuracy"] == 1.0
    assert cov["amount_accuracy"] is None  # not scorable, no specialist

    doc = result["by_reason_code"]["DOC"]
    assert doc["decision_accuracy"] is None  # not scorable, no specialist yet

    for category in SCENARIO_CATEGORIES:
        group = result["by_category"][category]
        assert group["decision_accuracy"] == 1.0
