"""Tests for app/write_tools.py and app/legacy_api.py against the seeded
(live) legacy database. Skips the module if Postgres isn't reachable."""
import inspect
import uuid

import psycopg2
import pytest

import app.legacy_api
import app.tools
import app.write_tools
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.tool_meta import is_side_effect
from app.tools import lookup_claim
from app.write_tools import WriteResult, issue_adjustment, update_claim_status


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


def test_update_claim_status_writes_through_the_legacy_api(dataset):
    claim_id = dataset.claims[0].clm_id
    result = update_claim_status(claim_id, "PD", request_key=str(uuid.uuid4()))
    assert isinstance(result, WriteResult)
    assert result.ok and not result.replayed
    assert lookup_claim(claim_id).status_code == "PD"


def test_issue_adjustment_writes_through_the_legacy_api(dataset):
    claim_id = dataset.claims[1].clm_id
    result = issue_adjustment(claim_id, amount_cents=4242, request_key=str(uuid.uuid4()))
    assert result.ok and not result.replayed
    assert lookup_claim(claim_id).paid_amount_cents == 4242


def test_update_claim_status_raises_for_missing_claim():
    with pytest.raises(app.legacy_api.LegacyApiFault):
        update_claim_status(999_999_999, "PD", request_key=str(uuid.uuid4()))


def test_retried_write_with_same_request_key_does_not_double_apply(dataset):
    claim_id = dataset.claims[2].clm_id
    key = str(uuid.uuid4())

    first = issue_adjustment(claim_id, amount_cents=1000, request_key=key)
    assert not first.replayed
    assert lookup_claim(claim_id).paid_amount_cents == 1000

    # Retried with a different amount under the SAME key: must not re-apply.
    second = issue_adjustment(claim_id, amount_cents=99_999, request_key=key)
    assert second.replayed
    assert lookup_claim(claim_id).paid_amount_cents == 1000  # unchanged


def test_both_write_tools_are_declared_side_effect():
    assert is_side_effect(update_claim_status)
    assert is_side_effect(issue_adjustment)


def test_read_tools_are_not_declared_side_effect():
    assert not is_side_effect(app.tools.lookup_claim)
    assert not is_side_effect(app.tools.get_dispute)


def test_no_write_outside_the_legacy_api_module():
    """app.write_tools must contain no SQL of its own -- every write goes
    through app.legacy_api.call_legacy_api, the single chokepoint."""
    write_tools_source = inspect.getsource(app.write_tools)
    assert "cur.execute" not in write_tools_source
    assert "import psycopg2" not in write_tools_source

    tools_source = inspect.getsource(app.tools)
    assert "UPDATE clm_hdr" not in tools_source and "UPDATE disp_hdr" not in tools_source

    legacy_api_source = inspect.getsource(app.legacy_api)
    assert "UPDATE clm_hdr" in legacy_api_source
