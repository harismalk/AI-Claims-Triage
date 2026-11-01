"""Tests for evals/golden.py against the seeded (live) legacy database."""
import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.tool_runtime import ToolRuntime, build_snapshot
from evals.golden import build_golden_dataset

SCENARIO_CATEGORIES = {"should_reverse", "denial_correct", "edge", "over_limit", "adversarial"}
REASON_CODES = {"DUP", "BIL", "DOC", "COV"}


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    try:
        conn = psycopg2.connect(default_dsn())
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip("Postgres is not reachable; start it with `docker compose up -d`", allow_module_level=True)
    load_into_postgres(generate_dataset(42), default_dsn())


@pytest.fixture(scope="module")
def golden_cases():
    return build_golden_dataset(seed=42)


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(42)


def test_golden_cases_load_from_the_answer_key_with_scenario_metadata(golden_cases, dataset):
    assert len(golden_cases) == 200
    answer_by_disp_id = {row.disp_id: row for row in dataset.answer_key}

    for case in golden_cases:
        row = answer_by_disp_id[case.dispute_id]
        assert case.category == row.category
        assert case.filed_reason_code == row.reason_code
        assert case.expected_decision == row.decision
        assert case.expected_amount_cents == row.amount_cents
        assert case.expected_evidence_claim_ids == row.evidence_claim_ids
        assert case.category in SCENARIO_CATEGORIES
        assert case.filed_reason_code in REASON_CODES


def test_every_case_bundles_input_tool_outputs_and_snapshot_reference(golden_cases):
    for case in golden_cases:
        assert case.complaint_text  # the input
        assert case.recorded_trace  # recorded tool outputs
        assert case.snapshot_claim_ids and case.snapshot_dispute_ids  # DB snapshot reference
        assert case.dispute_id in case.snapshot_dispute_ids


def test_cases_with_a_built_specialist_have_a_full_trace_and_proposal(golden_cases):
    dup_or_bil = [c for c in golden_cases if c.filed_reason_code in ("DUP", "BIL")]
    assert dup_or_bil
    for case in dup_or_bil:
        assert case.proposal is not None
        assert len(case.recorded_trace) > 1  # more than just the bare dispute lookup
        assert set(case.expected_evidence_claim_ids) <= set(case.snapshot_claim_ids)


def test_cases_without_a_built_specialist_still_exist_with_minimal_trace(golden_cases, dataset):
    doc_or_cov = [c for c in golden_cases if c.filed_reason_code in ("DOC", "COV")]
    expected_count = sum(1 for row in dataset.answer_key if row.reason_code in ("DOC", "COV"))
    assert len(doc_or_cov) == expected_count > 0
    for case in doc_or_cov:
        assert case.proposal is None
        assert case.recorded_trace  # at least the dispute lookup


def test_recorded_case_is_replayable_without_touching_the_live_database(golden_cases):
    case = next(c for c in golden_cases if c.filed_reason_code == "DUP")
    snapshot = build_snapshot(claim_ids=case.snapshot_claim_ids, dispute_ids=case.snapshot_dispute_ids)
    replay_runtime = ToolRuntime(mode="replay", replay_source=case.recorded_trace, snapshot=snapshot)

    from app.gate import evaluate
    from app.specialists.duplicate_denial.specialist import propose

    replayed_proposal = propose(case.dispute_id, replay_runtime)
    replayed_decision = evaluate(replayed_proposal, replay_runtime)

    assert replayed_proposal == case.proposal
    assert replayed_decision.action in ("auto_resolve", "escalate")
