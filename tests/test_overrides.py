"""Tests for app/overrides.py and evals/promote_override.py.

Redirects app.overrides.OVERRIDES_FILE to a temp path for every test, so
these never touch the real data/overrides.jsonl.
"""
import psycopg2
import pytest
from fastapi.testclient import TestClient

import app.overrides as overrides_module
from app.api import app
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.overrides import OverrideRecord, group_by_failure_pattern, load_overrides, record_override
from evals.promote_override import promote_override


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    try:
        conn = psycopg2.connect(default_dsn())
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip("Postgres is not reachable; start it with `docker compose up -d`", allow_module_level=True)
    load_into_postgres(generate_dataset(42), default_dsn())


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(42)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "OVERRIDES_FILE", tmp_path / "overrides.jsonl")
    # app.api imports record_override by reference, so patch it there too.
    import app.api as api_module
    monkeypatch.setattr(api_module, "record_override", overrides_module.record_override)


def test_override_records_what_was_proposed_chosen_and_why(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "reverse", "amount_cents": 500, "reason": "goodwill adjustment",
    })
    assert response.status_code == 200

    records = load_overrides()
    assert len(records) == 1
    record = records[0]
    assert record.dispute_id == row.disp_id
    assert record.proposed_decision == "deny"  # what the agent proposed
    assert record.proposed_amount_cents == 0
    assert record.chosen_decision == "reverse"  # what the adjuster chose
    assert record.chosen_amount_cents == 500
    assert record.reason == "goodwill adjustment"  # why


def test_override_with_no_recommendation_records_none_proposed(client, dataset):
    cov_row = next(r for r in dataset.answer_key if r.reason_code == "COV")
    response = client.post(f"/disputes/{cov_row.disp_id}/decisions", json={
        "action": "override", "decision": "deny", "amount_cents": 0, "reason": "coverage exclusion confirmed",
    })
    assert response.status_code == 200

    records = load_overrides()
    record = next(r for r in records if r.dispute_id == cov_row.disp_id)
    assert record.proposed_decision is None
    assert record.proposed_amount_cents is None


def test_accept_does_not_record_an_override(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={"action": "accept"})
    assert response.status_code == 200
    assert load_overrides() == []


def test_overrides_are_grouped_into_failure_patterns():
    records = [
        OverrideRecord(dispute_id=1, claim_id=10, reason_code="BIL", proposed_decision="deny",
                        proposed_amount_cents=0, chosen_decision="reverse", chosen_amount_cents=500,
                        reason="a"),
        OverrideRecord(dispute_id=2, claim_id=11, reason_code="DUP", proposed_decision="reverse",
                        proposed_amount_cents=100, chosen_decision="deny", chosen_amount_cents=0,
                        reason="b"),
        OverrideRecord(dispute_id=3, claim_id=12, reason_code="BIL", proposed_decision="reverse",
                        proposed_amount_cents=200, chosen_decision="reverse", chosen_amount_cents=300,
                        reason="c"),
        OverrideRecord(dispute_id=4, claim_id=13, reason_code="COV", proposed_decision=None,
                        proposed_amount_cents=None, chosen_decision="deny", chosen_amount_cents=0,
                        reason="d"),
        OverrideRecord(dispute_id=5, claim_id=14, reason_code="BIL", proposed_decision="deny",
                        proposed_amount_cents=0, chosen_decision="reverse", chosen_amount_cents=600,
                        reason="e"),
    ]
    groups = group_by_failure_pattern(records)

    assert records[0] in groups["decision_changed:deny->reverse"]
    assert records[4] in groups["decision_changed:deny->reverse"]
    assert groups["decision_changed:reverse->deny"] == [records[1]]
    assert groups["amount_changed"] == [records[2]]
    assert groups["no_recommendation"] == [records[3]]


def test_promote_override_builds_a_golden_case_with_snapshot(client, dataset):
    # A different dispute than test_override_records_what_was_proposed_chosen_and_why
    # used, so this doesn't collide with an already-resolved dispute.
    rows = [r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct"]
    row = rows[1]
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "reverse", "amount_cents": 777, "reason": "manual review found an overcharge",
    })
    assert response.status_code == 200

    case = promote_override(row.disp_id)
    assert case.dispute_id == row.disp_id
    assert case.category == "adjuster_override"
    assert case.expected_decision == "reverse"
    assert case.expected_amount_cents == 777
    assert case.recorded_trace  # a real trace, replayable without the live DB
    assert case.snapshot_claim_ids
    assert case.snapshot_dispute_ids == [row.disp_id]
    assert case.proposal is not None and case.proposal.decision == "deny"  # the original (overridden) recommendation


def test_promote_override_raises_for_a_dispute_with_no_recorded_override():
    with pytest.raises(ValueError):
        promote_override(999_999)
