"""Tests for app/api.py against the seeded (live) legacy database."""
import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.tools import get_dispute, lookup_claim


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


def test_list_disputes_returns_open_disputes_with_recommendations(client):
    response = client.get("/disputes")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 200  # all freshly seeded disputes are open
    dup_rows = [d for d in body if d["reason_code"] == "DUP"]
    assert dup_rows
    assert any(d["recommended_decision"] is not None for d in dup_rows)
    cov_rows = [d for d in body if d["reason_code"] == "COV"]
    assert all(d["recommended_decision"] is None for d in cov_rows)  # no specialist for COV


def test_get_case_returns_full_detail(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    response = client.get(f"/disputes/{row.disp_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["dispute_id"] == row.disp_id
    assert body["reason_code"] == "DUP"
    assert body["recommended_decision"] == "reverse"
    assert body["gate_action"] == "auto_resolve"
    assert body["claim"]["claim_id"]
    assert body["complaint_text"]


def test_get_case_404_for_missing_dispute(client):
    response = client.get("/disputes/999999")
    assert response.status_code == 404


def test_accept_recommendation_executes_the_write(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={"action": "accept"})
    assert response.status_code == 200
    body = response.json()
    assert body["final_decision"] == "reverse"
    assert body["final_amount_cents"] == row.amount_cents

    claim = lookup_claim(body["claim_id"])
    assert claim.status_code == "PD"
    assert claim.paid_amount_cents == row.amount_cents
    dispute = get_dispute(row.disp_id)
    assert dispute.status_code == "RSLV"
    assert dispute.resolution_amount_cents == row.amount_cents


def test_accept_with_no_recommendation_is_rejected(client, dataset):
    cov_row = next(r for r in dataset.answer_key if r.reason_code == "COV")
    response = client.post(f"/disputes/{cov_row.disp_id}/decisions", json={"action": "accept"})
    assert response.status_code == 400


def test_override_requires_decision_amount_and_reason(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={"action": "override"})
    assert response.status_code == 422  # pydantic validation failure, missing required override fields


def test_override_executes_a_different_decision_than_the_recommendation(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct")
    # the agent recommends "deny"; the adjuster overrides to pay a goodwill amount
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "reverse", "amount_cents": 500, "reason": "goodwill adjustment",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["final_decision"] == "reverse"
    assert body["final_amount_cents"] == 500

    claim = lookup_claim(body["claim_id"])
    assert claim.status_code == "PD"
    assert claim.paid_amount_cents == 500


def test_deny_override_must_have_zero_amount(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DOC")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "deny", "amount_cents": 100, "reason": "no evidence of overcharge",
    })
    assert response.status_code == 422


def test_decision_on_already_resolved_dispute_conflicts(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DOC" and r.category == "denial_correct")
    first = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "deny", "amount_cents": 0, "reason": "no documents on file",
    })
    assert first.status_code == 200

    second = client.post(f"/disputes/{row.disp_id}/decisions", json={
        "action": "override", "decision": "deny", "amount_cents": 0, "reason": "repeat attempt",
    })
    assert second.status_code == 409


def test_decision_on_missing_dispute_404s(client):
    response = client.post("/disputes/999999/decisions", json={"action": "accept"})
    assert response.status_code == 404


def test_invalid_action_value_is_rejected_by_request_validation(client, dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "over_limit")
    response = client.post(f"/disputes/{row.disp_id}/decisions", json={"action": "approve_please"})
    assert response.status_code == 422
