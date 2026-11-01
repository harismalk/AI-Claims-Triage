"""Tests for app/tools.py against the seeded (live) legacy database.

Seeds the database deterministically (seed=42) once per test session, so these
tests are self-contained regardless of whatever was last loaded by `make seed`.
Skips the whole module if Postgres isn't reachable, so `pytest -q` still works
on machines without Docker running.
"""
import datetime

import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.plans import Plan
from app.tools import (
    ClaimView,
    DisputeView,
    MemberView,
    find_similar_claims,
    get_dispute,
    get_member,
    get_payment_history,
    get_plan_terms,
    lookup_claim,
)

LEGACY_COLUMN_NAMES = {
    "clm_id_nbr", "mbr_id_nbr", "prv_id_nbr", "dt_of_svc", "clm_submit_dt", "proc_cd",
    "clm_sts_cd", "clm_amt", "adj_amt", "adj_rsn_cd", "adj_rsn_2", "visit_id", "note_txt",
    "disp_id_nbr", "disp_typ_cd", "disp_filed_dt", "disp_sts_cd", "disp_resln_amt", "disp_resln_dt",
}


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


def test_lookup_claim_returns_a_typed_claim_view(dataset):
    claim_id = dataset.claims[0].clm_id
    result = lookup_claim(claim_id)
    assert isinstance(result, ClaimView)
    assert result.claim_id == claim_id
    assert isinstance(result.date_of_service, datetime.date)
    assert isinstance(result.billed_amount_cents, int)


def test_lookup_claim_returns_none_for_missing_claim():
    assert lookup_claim(999_999_999) is None


def test_lookup_claim_resolves_status_and_denial_reason(dataset):
    denied = next(c for c in dataset.claims if c.sts_cd == "DEN" and c.adj_rsn_cd)
    result = lookup_claim(denied.clm_id)
    assert result.status_code == "DEN"
    assert result.status_description == "Denied"
    assert result.denial_reason_description  # e.g. "Duplicate claim"


def test_find_similar_claims_finds_the_dup_pair(dataset):
    should_reverse_dup = next(
        row for row in dataset.answer_key if row.category == "should_reverse" and row.reason_code == "DUP"
    )
    disputed_claim_id = max(should_reverse_dup.evidence_claim_ids)
    similar = find_similar_claims(disputed_claim_id)
    assert any(c.claim_id in should_reverse_dup.evidence_claim_ids for c in similar)


def test_find_similar_claims_empty_for_missing_claim():
    assert find_similar_claims(999_999_999) == []


def test_get_plan_terms_returns_the_plan_model():
    plan = get_plan_terms("GOLD")
    assert isinstance(plan, Plan)
    assert plan.plan_code == "GOLD"
    assert plan.copays_cents


def test_get_plan_terms_returns_none_for_unknown_plan():
    assert get_plan_terms("NOPE") is None


def test_get_payment_history_only_returns_paid_claims(dataset):
    member_id = dataset.members[0].mbr_id
    history = get_payment_history(member_id)
    assert all(c.status_code == "PD" for c in history)
    assert all(c.member_id == member_id for c in history)


def test_get_dispute_returns_claim_and_complaint_text(dataset):
    disp = dataset.disputes[0]
    result = get_dispute(disp.disp_id)
    assert isinstance(result, DisputeView)
    assert result.dispute_id == disp.disp_id
    assert isinstance(result.claim, ClaimView)
    assert result.claim.claim_id == disp.clm_id
    assert result.complaint_text == disp.complaint_text


def test_get_dispute_returns_none_for_missing_dispute():
    assert get_dispute(999_999_999) is None


def test_get_member_returns_a_typed_member_view(dataset):
    member_id = dataset.members[0].mbr_id
    result = get_member(member_id)
    assert isinstance(result, MemberView)
    assert result.member_id == member_id
    assert result.plan_code in ("BRONZE", "SILVER", "GOLD", "HDHP_2000")


def test_get_member_returns_none_for_missing_member():
    assert get_member(999_999_999) is None


def test_no_tool_return_model_uses_raw_legacy_column_names():
    for model in (ClaimView, DisputeView, MemberView):
        field_names = set(model.model_fields)
        assert not (field_names & LEGACY_COLUMN_NAMES), f"{model.__name__} leaks raw column names: {field_names & LEGACY_COLUMN_NAMES}"
