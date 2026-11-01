"""Tests for app/specialists/billing_error/specialist.py against the seeded
(live) legacy database."""
import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.specialists.base import Proposal
from app.specialists.billing_error.specialist import ALLOWED_TOOLS, propose
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


def test_allowed_tools_exclude_every_write_tool():
    assert "update_claim_status" not in ALLOWED_TOOLS
    assert "issue_adjustment" not in ALLOWED_TOOLS


def test_allowed_tools_are_not_the_duplicate_denial_specialists():
    from app.specialists.duplicate_denial.specialist import ALLOWED_TOOLS as DUP_TOOLS
    assert ALLOWED_TOOLS != DUP_TOOLS
    assert "find_similar_claims" not in ALLOWED_TOOLS


def test_propose_only_calls_its_own_allowed_tools(dataset):
    bil_row = next(r for r in dataset.answer_key if r.reason_code == "BIL")
    runtime = ToolRuntime(mode="live")
    propose(bil_row.disp_id, runtime)
    used_tools = {record.tool_name for record in runtime.history}
    assert used_tools <= ALLOWED_TOOLS
    assert used_tools


def test_propose_returns_the_same_proposal_shape_as_duplicate_denial(dataset):
    bil_row = next(r for r in dataset.answer_key if r.reason_code == "BIL")
    runtime = ToolRuntime(mode="live")
    result = propose(bil_row.disp_id, runtime)
    assert isinstance(result, Proposal)
    assert result.decision in ("reverse", "deny", "escalate")
    assert isinstance(result.amount_cents, int)
    assert result.evidence_claim_ids
    assert result.rationale


def test_overcharged_claims_under_the_limit_are_reversed_for_the_overage(dataset):
    rows = [r for r in dataset.answer_key
            if r.reason_code == "BIL" and r.category in ("should_reverse", "edge", "adversarial")
            and r.decision == "reverse"]
    assert rows

    runtime = ToolRuntime(mode="live")
    for row in rows:
        result = propose(row.disp_id, runtime)
        assert result.decision == "reverse", row.disp_id
        assert result.amount_cents == row.amount_cents, row.disp_id


def test_correctly_charged_claims_are_denied(dataset):
    rows = [r for r in dataset.answer_key
            if r.reason_code == "BIL" and r.category == "denial_correct"]
    assert rows

    runtime = ToolRuntime(mode="live")
    for row in rows:
        result = propose(row.disp_id, runtime)
        assert result.decision == row.decision == "deny", row.disp_id
        assert result.amount_cents == 0


def test_over_limit_claims_propose_reverse_not_escalate(dataset):
    """The answer key's `decision` for over_limit is "escalate" -- but that's
    the GATE's downstream output after enforcing the $500 authority limit
    (T3.4), not this specialist's job. The specialist should honestly propose
    its substantive judgment ("reverse", with the full overage), and the gate
    is what will escalate it later."""
    rows = [r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "over_limit"]
    assert rows

    runtime = ToolRuntime(mode="live")
    for row in rows:
        result = propose(row.disp_id, runtime)
        assert result.decision == "reverse", row.disp_id
        assert result.amount_cents == row.amount_cents, row.disp_id


def test_rationale_cites_the_specific_plan_rule(dataset):
    bil_row = next(r for r in dataset.answer_key if r.reason_code == "BIL" and r.category == "denial_correct")
    runtime = ToolRuntime(mode="live")
    result = propose(bil_row.disp_id, runtime)
    assert "copay" in result.rationale.lower()
    assert any(code in result.rationale for code in ("BRONZE", "SILVER", "GOLD", "HDHP_2000"))
