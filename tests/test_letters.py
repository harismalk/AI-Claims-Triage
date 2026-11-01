"""Tests for app/letters.py against the seeded (live) legacy database."""
import re

import psycopg2
import pytest

from app.gate import evaluate
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.letters import draft_letter
from app.specialists.billing_error.specialist import propose as propose_billing_error
from app.specialists.duplicate_denial.specialist import propose as propose_duplicate_denial
from app.tool_runtime import ToolRuntime

PROC_CODE_RE = re.compile(r"\b(?:\d{5}|J\d{4})\b")  # e.g. 99213, J1100
PLAN_CODES = ("BRONZE", "SILVER", "GOLD", "HDHP_2000")
REASON_CODES = ("DUP", "BIL", "DOC", "COV")


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


def _end_to_end(dataset, row, propose_fn):
    runtime = ToolRuntime(mode="live")
    proposal = propose_fn(row.disp_id, runtime)
    decision = evaluate(proposal, runtime)
    return decision, runtime


def test_letter_states_decision_amount_and_reason_in_plain_language(dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    decision, runtime = _end_to_end(dataset, row, propose_duplicate_denial)
    assert decision.action == "auto_resolve"

    letter = draft_letter(decision, runtime)
    assert f"${decision.proposal.amount_cents / 100:.2f}" in letter
    assert "payment" in letter.lower() or "refund" in letter.lower()
    assert "duplicate" in letter.lower()  # the plain-language DUP reason phrase


def test_deny_letter_states_plain_language_reason(dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct")
    decision, runtime = _end_to_end(dataset, row, propose_billing_error)
    assert decision.action == "auto_resolve"
    assert decision.proposal.decision == "deny"

    letter = draft_letter(decision, runtime)
    assert "no additional payment" in letter.lower() or "correct" in letter.lower()


def test_letters_never_contain_claim_ids_reason_codes_plan_codes_or_procedure_codes(dataset):
    cases = [
        (next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse"),
         propose_duplicate_denial),
        (next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "denial_correct"),
         propose_duplicate_denial),
        (next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "should_reverse"),
         propose_billing_error),
        (next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct"),
         propose_billing_error),
    ]
    for row, propose_fn in cases:
        decision, runtime = _end_to_end(dataset, row, propose_fn)
        assert decision.action == "auto_resolve", row.disp_id
        letter = draft_letter(decision, runtime)

        for claim_id in row.evidence_claim_ids:
            assert not re.search(rf"\b{claim_id}\b", letter), (row.disp_id, claim_id, letter)
        for code in REASON_CODES:
            assert code not in letter, (row.disp_id, code, letter)
        for code in PLAN_CODES:
            assert code not in letter, (row.disp_id, code, letter)
        assert not PROC_CODE_RE.search(letter), (row.disp_id, letter)
        assert "visit_id" not in letter.lower() and "clm_" not in letter.lower()


def test_draft_letter_raises_for_an_escalated_decision(dataset):
    row = next(r for r in dataset.answer_key if r.reason_code == "COV")
    runtime = ToolRuntime(mode="live")
    from app.specialists.base import Proposal
    proposal = Proposal(dispute_id=row.disp_id, decision="escalate", amount_cents=0,
                         evidence_claim_ids=[], rationale="coverage question")
    decision = evaluate(proposal, runtime)
    assert decision.action == "escalate"
    with pytest.raises(ValueError):
        draft_letter(decision, runtime)
