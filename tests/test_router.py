"""Tests for app/router.py. No database needed -- pure logic plus the
committed T1.3/T1.4 fixtures."""
import pytest

from app.generate_data import generate_dataset
from app.router import REASON_TO_SPECIALIST, route_dispute
from scripts.measure_routing_accuracy import measure, poison_pill_classifier


def test_present_consistent_reason_code_never_calls_the_classifier():
    decision = route_dispute(1, "DUP", "My claim was denied as a duplicate, but it wasn't.",
                              classify_fn=poison_pill_classifier)
    assert not decision.used_fallback
    assert decision.specialist == "duplicate_denial"


def test_missing_reason_code_falls_back_and_logs_why():
    log = []
    decision = route_dispute(2, None, "I was charged too much for my visit.",
                              classify_fn=lambda text: "BIL", fallback_log=log)
    assert decision.used_fallback
    assert decision.specialist == "billing_error"
    assert len(log) == 1
    assert log[0]["dispute_id"] == 2
    assert "missing" in log[0]["reason"]


def test_contradictory_reason_code_falls_back_and_logs_why():
    log = []
    # Reason code says DUP, but the complaint is clearly about a copay overcharge.
    decision = route_dispute(3, "DUP", "I was overcharged on my copay for this visit, please refund it.",
                              classify_fn=lambda text: "BIL", fallback_log=log)
    assert decision.used_fallback
    assert decision.specialist == "billing_error"
    assert len(log) == 1
    assert "contradicts" in log[0]["reason"]


def test_coverage_disputes_route_to_no_specialist():
    decision = route_dispute(4, "COV", "This isn't covered under my plan.",
                              classify_fn=poison_pill_classifier)
    assert not decision.used_fallback
    assert decision.specialist is None  # always escalate directly, no specialist


def test_routing_accuracy_against_the_t1_3_answer_key():
    result = measure()
    assert result["total"] == 200
    assert result["fallbacks_used"] == 0
    assert result["accuracy"] == 1.0
    for code in REASON_TO_SPECIALIST:
        assert result["by_reason_code"][code] == 1.0


def test_dataset_disputes_use_only_known_reason_codes():
    dataset = generate_dataset(42)
    for row in dataset.answer_key:
        assert row.reason_code in REASON_TO_SPECIALIST
