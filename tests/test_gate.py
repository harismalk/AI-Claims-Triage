"""Tests for app/gate.py against the seeded (live) legacy database."""
import psycopg2
import pytest

from app.gate import AUTO_RESOLVE_LIMIT_CENTS, evaluate
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.specialists.base import Proposal
from app.specialists.billing_error.specialist import propose as propose_billing_error
from app.specialists.duplicate_denial.specialist import propose as propose_duplicate_denial
from app.tool_runtime import ToolRuntime


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


def test_valid_under_limit_proposal_auto_resolves(dataset):
    row = next(r for r in dataset.answer_key
               if r.reason_code == "DUP" and r.category == "should_reverse")
    runtime = ToolRuntime(mode="live")
    proposal = propose_duplicate_denial(row.disp_id, runtime)
    decision = evaluate(proposal, runtime)
    assert decision.action == "auto_resolve"
    assert decision.reasons


def test_coverage_disputes_always_escalate_even_with_a_clean_proposal(dataset):
    cov_row = next(r for r in dataset.answer_key if r.reason_code == "COV")
    runtime = ToolRuntime(mode="live")
    # Hand-built proposal: looks perfectly clean (low amount, cites the real
    # disputed claim) -- the gate must still escalate because of dispute type.
    proposal = Proposal(dispute_id=cov_row.disp_id, decision="reverse", amount_cents=100,
                         evidence_claim_ids=cov_row.evidence_claim_ids, rationale="looks fine")
    decision = evaluate(proposal, runtime)
    assert decision.action == "escalate"
    assert any("coverage_always_escalates" in r for r in decision.reasons)


def test_amount_over_the_limit_always_escalates(dataset):
    row = next(r for r in dataset.answer_key
               if r.reason_code == "BIL" and r.category == "over_limit")
    runtime = ToolRuntime(mode="live")
    proposal = propose_billing_error(row.disp_id, runtime)
    assert proposal.amount_cents > AUTO_RESOLVE_LIMIT_CENTS
    decision = evaluate(proposal, runtime)
    assert decision.action == "escalate"
    assert any("authority_limit" in r for r in decision.reasons)


def test_adversarial_complaints_escalate_as_a_risk_flag_even_under_the_limit(dataset):
    row = next(r for r in dataset.answer_key
               if r.reason_code == "BIL" and r.category == "adversarial")
    runtime = ToolRuntime(mode="live")
    proposal = propose_billing_error(row.disp_id, runtime)
    assert proposal.amount_cents <= AUTO_RESOLVE_LIMIT_CENTS  # otherwise this wouldn't isolate the risk-flag rule
    decision = evaluate(proposal, runtime)
    assert decision.action == "escalate"
    assert any("risk_flag" in r for r in decision.reasons)


def test_gate_rechecks_evidence_and_rejects_a_nonexistent_cited_claim(dataset):
    row = next(r for r in dataset.answer_key
               if r.reason_code == "DUP" and r.category == "should_reverse")
    runtime = ToolRuntime(mode="live")
    tampered = Proposal(dispute_id=row.disp_id, decision="reverse", amount_cents=100,
                         evidence_claim_ids=[999_999_999], rationale="tampered evidence")
    decision = evaluate(tampered, runtime)
    assert decision.action == "escalate"
    assert any("evidence_exists" in r for r in decision.reasons)


def test_gate_rejects_evidence_belonging_to_a_different_member(dataset):
    row = next(r for r in dataset.answer_key
               if r.reason_code == "DUP" and r.category == "should_reverse")
    runtime = ToolRuntime(mode="live")
    dispute = runtime.call("get_dispute", dispute_id=row.disp_id)
    wrong_member_claim_id = next(c.clm_id for c in dataset.claims if c.mbr_id != dispute.claim.member_id)

    tampered = Proposal(dispute_id=row.disp_id, decision="reverse", amount_cents=100,
                         evidence_claim_ids=[wrong_member_claim_id], rationale="wrong member's claim cited")
    decision = evaluate(tampered, runtime)
    assert decision.action == "escalate"
    assert any("evidence_supports_claim" in r for r in decision.reasons)


def test_specialist_proposed_escalation_is_honored(dataset):
    runtime = ToolRuntime(mode="live")
    proposal = Proposal(dispute_id=1, decision="escalate", amount_cents=0,
                         evidence_claim_ids=[], rationale="specialist couldn't resolve this")
    decision = evaluate(proposal, runtime)
    assert decision.action == "escalate"
    assert any("specialist_escalated" in r for r in decision.reasons)


def test_every_decision_records_reasons(dataset):
    runtime = ToolRuntime(mode="live")
    dup_row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    cov_row = next(r for r in dataset.answer_key if r.reason_code == "COV")

    allowed = evaluate(propose_duplicate_denial(dup_row.disp_id, runtime), runtime)
    blocked = evaluate(
        Proposal(dispute_id=cov_row.disp_id, decision="reverse", amount_cents=100,
                 evidence_claim_ids=cov_row.evidence_claim_ids, rationale="x"),
        runtime,
    )
    assert allowed.reasons and blocked.reasons
