"""Measures the T3.1 deterministic router's accuracy against the T1.3 answer
key: for all 200 real planted disputes, does the router pick the specialist
implied by the dispute's true reason code, without ever needing the LLM
fallback? Run: python3 scripts/measure_routing_accuracy.py
"""
from __future__ import annotations

from collections import Counter

from app.generate_data import generate_dataset
from app.router import REASON_TO_SPECIALIST, route_dispute


def poison_pill_classifier(_complaint_text):
    raise AssertionError("fallback classifier was called on a case with a present, consistent reason code")


def measure(seed: int = 42) -> dict:
    dataset = generate_dataset(seed)
    answer_by_disp_id = {row.disp_id: row for row in dataset.answer_key}

    total = 0
    correct = 0
    fallbacks_used = 0
    by_reason_code: Counter = Counter()
    by_reason_code_correct: Counter = Counter()

    for disp in dataset.disputes:
        row = answer_by_disp_id[disp.disp_id]
        expected_specialist = REASON_TO_SPECIALIST.get(row.reason_code)
        decision = route_dispute(disp.disp_id, disp.typ_cd, disp.complaint_text,
                                  classify_fn=poison_pill_classifier)
        total += 1
        by_reason_code[row.reason_code] += 1
        if decision.used_fallback:
            fallbacks_used += 1
        if decision.specialist == expected_specialist:
            correct += 1
            by_reason_code_correct[row.reason_code] += 1

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total,
        "fallbacks_used": fallbacks_used,
        "by_reason_code": {
            code: by_reason_code_correct[code] / count for code, count in by_reason_code.items()
        },
    }


def main() -> None:
    result = measure()
    print(f"routing accuracy: {result['correct']}/{result['total']} ({result['accuracy']:.1%})")
    print(f"LLM fallbacks used: {result['fallbacks_used']}")
    for code, acc in sorted(result["by_reason_code"].items()):
        print(f"  {code}: {acc:.1%}")


if __name__ == "__main__":
    main()
