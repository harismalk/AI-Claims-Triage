"""Tests for evals/regression_gate.py.

golden_cases is the session-scoped fixture shared with test_golden.py,
test_scorers.py, and test_invariants.py -- see tests/conftest.py.
"""
from evals.regression_gate import (
    CasePassRate,
    check_regression,
    load_baseline,
    run_case_n_times,
    run_eval_suite,
    tracked_metrics,
)


def test_each_case_runs_multiple_times_and_reports_a_pass_rate(golden_cases):
    case = golden_cases[0]
    rate, violations = run_case_n_times(case, n=3)
    assert isinstance(rate, CasePassRate)
    assert rate.runs == 3
    assert 0 <= rate.passes <= 3
    assert rate.pass_rate == rate.passes / 3
    assert violations == []  # this is a clean case


def test_real_system_matches_the_committed_baseline_with_no_regressions(golden_cases):
    result = run_eval_suite(golden_cases, n=1)
    baseline = load_baseline()
    problems = check_regression(result, baseline)
    assert problems == []


def test_tracked_metrics_matches_the_baseline_key_set(golden_cases):
    result = run_eval_suite(golden_cases, n=1)
    assert set(tracked_metrics(result)) == set(load_baseline())


def test_check_regression_detects_a_score_drop(golden_cases):
    result = run_eval_suite(golden_cases, n=1)
    inflated_baseline = dict(load_baseline())
    inflated_baseline["overall_pass_rate"] = 1.1  # impossible to meet -- simulates a regression
    problems = check_regression(result, inflated_baseline)
    assert any("REGRESSION" in p and "overall_pass_rate" in p for p in problems)


def test_check_regression_detects_invariant_violations_even_with_perfect_scores(golden_cases):
    from evals.invariants import InvariantViolation

    result = run_eval_suite(golden_cases, n=1)
    result["violations"] = [InvariantViolation(999_999, "never_auto_resolve_over_limit", "synthetic test violation")]
    baseline = load_baseline()
    problems = check_regression(result, baseline)
    assert any("SAFETY INVARIANT VIOLATED" in p for p in problems)
