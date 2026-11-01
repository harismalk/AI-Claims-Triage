"""Tests for app/specialists/duplicate_denial/specialist.py against the
seeded (live) legacy database."""
import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.specialists.base import Proposal
from app.specialists.duplicate_denial.specialist import ALLOWED_TOOLS, propose
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


def test_propose_only_calls_its_own_allowed_tools(dataset):
    dup_row = next(r for r in dataset.answer_key if r.reason_code == "DUP")
    runtime = ToolRuntime(mode="live")
    propose(dup_row.disp_id, runtime)
    used_tools = {record.tool_name for record in runtime.history}
    assert used_tools <= ALLOWED_TOOLS
    assert used_tools  # actually called something


def test_propose_returns_a_structured_proposal(dataset):
    dup_row = next(r for r in dataset.answer_key if r.reason_code == "DUP")
    runtime = ToolRuntime(mode="live")
    result = propose(dup_row.disp_id, runtime)
    assert isinstance(result, Proposal)
    assert result.decision in ("reverse", "deny", "escalate")
    assert isinstance(result.amount_cents, int)
    assert result.evidence_claim_ids
    assert result.rationale


def test_handles_same_date_different_procedure_edge_case_on_the_golden_set(dataset):
    edge_dup_rows = [r for r in dataset.answer_key if r.category == "edge" and r.reason_code == "DUP"]
    assert len(edge_dup_rows) == 20  # the golden same-date-different-procedure set

    runtime = ToolRuntime(mode="live")
    for row in edge_dup_rows:
        result = propose(row.disp_id, runtime)
        assert result.decision == row.decision == "reverse", row.disp_id
        assert result.amount_cents == row.amount_cents, row.disp_id
        assert set(result.evidence_claim_ids) == set(row.evidence_claim_ids), row.disp_id


def test_handles_genuine_duplicates_correctly(dataset):
    genuine_dup_rows = [r for r in dataset.answer_key if r.category == "denial_correct" and r.reason_code == "DUP"]
    assert genuine_dup_rows

    runtime = ToolRuntime(mode="live")
    for row in genuine_dup_rows:
        result = propose(row.disp_id, runtime)
        assert result.decision == row.decision == "deny", row.disp_id
        assert result.amount_cents == 0
