"""Tests for app/tool_runtime.py against the seeded (live) legacy database."""
import uuid

import psycopg2
import pytest

from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.tools import lookup_claim
from app.tool_runtime import StrictMissError, ToolRuntime, UndeclaredToolError, build_snapshot


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


def _sample_flow(runtime, claim_id, request_key):
    """The exact same code path, called once in live mode and once in replay
    mode in the tests below -- proving criterion 1."""
    before = runtime.call("lookup_claim", claim_id=claim_id)
    write = runtime.call("issue_adjustment", claim_id=claim_id, amount_cents=4242, request_key=request_key)
    after = runtime.call("lookup_claim", claim_id=claim_id)
    return before, write, after


def test_agent_code_is_identical_in_live_and_replay_modes(dataset):
    claim_id = dataset.claims[10].clm_id
    request_key = str(uuid.uuid4())

    live_runtime = ToolRuntime(mode="live")
    live_result = _sample_flow(live_runtime, claim_id, request_key)

    replay_runtime = ToolRuntime(mode="replay", replay_source=live_runtime.history)
    replay_result = _sample_flow(replay_runtime, claim_id, request_key)

    assert live_result == replay_result


def test_replayed_trace_reproduces_original_outputs_exactly(dataset):
    claim_id = dataset.claims[11].clm_id
    request_key = str(uuid.uuid4())

    live_runtime = ToolRuntime(mode="live")
    original = [
        live_runtime.call("lookup_claim", claim_id=claim_id),
        live_runtime.call("issue_adjustment", claim_id=claim_id, amount_cents=333, request_key=request_key),
        live_runtime.call("lookup_claim", claim_id=claim_id),
    ]

    replay_runtime = ToolRuntime(mode="replay", replay_source=live_runtime.history)
    replayed = [
        replay_runtime.call("lookup_claim", claim_id=claim_id),
        replay_runtime.call("issue_adjustment", claim_id=claim_id, amount_cents=333, request_key=request_key),
        replay_runtime.call("lookup_claim", claim_id=claim_id),
    ]

    assert original == replayed


def test_intercepted_write_appears_in_effect_log_and_subsequent_reads(dataset):
    claim_id = dataset.claims[12].clm_id
    snapshot = build_snapshot(claim_ids=[claim_id])
    runtime = ToolRuntime(mode="replay", snapshot=snapshot)

    before = runtime.call("lookup_claim", claim_id=claim_id)
    result = runtime.call("issue_adjustment", claim_id=claim_id, amount_cents=12345, request_key=str(uuid.uuid4()))
    assert result.ok and not result.replayed
    assert len(runtime.effect_log) == 1
    assert runtime.effect_log[0].tool_name == "issue_adjustment"

    after = runtime.call("lookup_claim", claim_id=claim_id)
    assert after.paid_amount_cents == 12345
    assert before.paid_amount_cents != 12345

    # The real database was never touched by the replay-mode write.
    real = lookup_claim(claim_id)
    assert real.paid_amount_cents != 12345


def test_replay_strict_miss_raises_without_trace_or_snapshot(dataset):
    claim_id = dataset.claims[13].clm_id
    runtime = ToolRuntime(mode="replay")
    with pytest.raises(StrictMissError):
        runtime.call("lookup_claim", claim_id=claim_id)


def test_replay_non_strict_miss_returns_none(dataset):
    claim_id = dataset.claims[14].clm_id
    runtime = ToolRuntime(mode="replay", strict=False)
    assert runtime.call("lookup_claim", claim_id=claim_id) is None


def test_undeclared_tool_is_blocked_outside_live_mode():
    def mystery():
        return "boo"

    registry = {"mystery": mystery}

    live_runtime = ToolRuntime(mode="live", registry=registry)
    assert live_runtime.call("mystery") == "boo"

    replay_runtime = ToolRuntime(mode="replay", registry=registry)
    with pytest.raises(UndeclaredToolError):
        replay_runtime.call("mystery")


def test_get_plan_terms_works_identically_in_both_modes():
    live_runtime = ToolRuntime(mode="live")
    replay_runtime = ToolRuntime(mode="replay")
    assert live_runtime.call("get_plan_terms", plan_code="GOLD") == replay_runtime.call(
        "get_plan_terms", plan_code="GOLD"
    )
