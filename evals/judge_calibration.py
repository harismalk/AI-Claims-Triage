"""Calibration: measures how well the deterministic judge (evals/judge.py)
agrees with 30 hand-graded example letters (fixtures/letters/hand_graded.json,
graded by reading each one against the rubric, not by running this checker).
Run: python -m evals.judge_calibration
"""
from __future__ import annotations

import json
from pathlib import Path

from evals.judge import judge_letter

HAND_GRADED_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "letters" / "hand_graded.json"


def load_hand_graded() -> list[dict]:
    return json.loads(HAND_GRADED_FIXTURE.read_text())


def calibrate() -> dict:
    examples = load_hand_graded()
    judged = [
        {"id": ex["id"], "hand_score": ex["hand_score"],
         "judge_score": judge_letter(ex["letter"], ex["member_name"], ex["issues_payment"]).score}
        for ex in examples
    ]
    n = len(judged)
    exact_matches = sum(1 for j in judged if j["judge_score"] == j["hand_score"])
    mae = sum(abs(j["judge_score"] - j["hand_score"]) for j in judged) / n
    within_one = sum(1 for j in judged if abs(j["judge_score"] - j["hand_score"]) <= 1) / n

    return {
        "n": n,
        "exact_match_rate": exact_matches / n,
        "within_one_point_rate": within_one,
        "mean_absolute_error": mae,
        "judged": judged,
    }


def main() -> None:
    result = calibrate()
    print(f"judge calibration against {result['n']} hand-graded letters:")
    print(f"  exact match rate:    {result['exact_match_rate']:.1%}")
    print(f"  within one point:    {result['within_one_point_rate']:.1%}")
    print(f"  mean absolute error: {result['mean_absolute_error']:.2f}")


if __name__ == "__main__":
    main()
