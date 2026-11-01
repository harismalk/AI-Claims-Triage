"""CI regression gate (T4.5).

Runs the full eval suite -- T4.2's code scorers and T4.3's safety invariants
-- against the golden dataset. Each case runs RUNS_PER_CASE times and reports
a pass rate rather than a single pass/fail: today's router/specialists/gate
are all deterministic, so every run of a case is identical and the rate is
always 0% or 100%, but the harness doesn't assume that -- once a real,
possibly-stochastic LLM call replaces one of the pluggable *_fn defaults
(DEC-0005), a case can fail intermittently without this looking like
undifferentiated noise.

Exits non-zero -- failing CI -- if any safety invariant is violated, or if
any tracked metric drops below the committed baseline (evals/baseline.json).
Run: python3 -m evals.regression_gate
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from evals.golden import GoldenCase, build_golden_dataset
from evals.invariants import InvariantViolation, check_case
from evals.scorers import report, score_case

BASELINE_FILE = Path(__file__).resolve().parent / "baseline.json"
RUNS_PER_CASE = 3


@dataclass
class CasePassRate:
    dispute_id: int
    runs: int
    passes: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0


def _case_passes_once(case: GoldenCase) -> tuple[bool, list[InvariantViolation]]:
    score = score_case(case)
    violations = check_case(case)
    scorable = (score.routing_correct, score.decision_correct, score.amount_correct, score.evidence_valid)
    passed = not violations and all(v is not False for v in scorable)
    return passed, violations


def run_case_n_times(case: GoldenCase, n: int = RUNS_PER_CASE) -> tuple[CasePassRate, list[InvariantViolation]]:
    passes = 0
    violations: list[InvariantViolation] = []
    for _ in range(n):
        passed, case_violations = _case_passes_once(case)
        passes += int(passed)
        violations.extend(case_violations)
    return CasePassRate(dispute_id=case.dispute_id, runs=n, passes=passes), violations


def run_eval_suite(cases: list[GoldenCase], n: int = RUNS_PER_CASE) -> dict:
    pass_rates = []
    violations: list[InvariantViolation] = []
    for case in cases:
        rate, case_violations = run_case_n_times(case, n)
        pass_rates.append(rate)
        violations.extend(case_violations)

    total_runs = sum(r.runs for r in pass_rates)
    total_passes = sum(r.passes for r in pass_rates)
    return {
        "overall_pass_rate": total_passes / total_runs if total_runs else 0.0,
        "violations": violations,
        "scorer_report": report([score_case(c) for c in cases]),
        "pass_rates": pass_rates,
    }


def load_baseline() -> dict:
    return json.loads(BASELINE_FILE.read_text())


def tracked_metrics(result: dict) -> dict[str, float]:
    """Every metric the regression gate compares against baseline."""
    metrics = {"overall_pass_rate": result["overall_pass_rate"]}
    for group_key in ("by_reason_code", "by_category"):
        for name, group in result["scorer_report"][group_key].items():
            for dim in ("routing_accuracy", "decision_accuracy", "amount_accuracy", "evidence_validity"):
                if group[dim] is not None:
                    metrics[f"{group_key}.{name}.{dim}"] = group[dim]
    return metrics


def check_regression(result: dict, baseline: dict) -> list[str]:
    """Returns regression/violation messages; empty means the gate passes."""
    problems = [
        f"SAFETY INVARIANT VIOLATED: {v.invariant} (dispute {v.dispute_id}): {v.detail}"
        for v in result["violations"]
    ]
    current = tracked_metrics(result)
    for key, baseline_value in baseline.items():
        current_value = current.get(key)
        if current_value is None:
            continue  # metric no longer produced; not this gate's concern
        if current_value < baseline_value:
            problems.append(f"REGRESSION: {key} dropped from {baseline_value:.3f} to {current_value:.3f}")
    return problems


def main() -> int:
    cases = build_golden_dataset()
    result = run_eval_suite(cases)
    baseline = load_baseline()
    problems = check_regression(result, baseline)

    print(f"ran {len(cases)} golden cases x{RUNS_PER_CASE} runs each; "
          f"overall pass rate: {result['overall_pass_rate']:.1%}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  {p}")
        return 1
    print("no regressions, no invariant violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
