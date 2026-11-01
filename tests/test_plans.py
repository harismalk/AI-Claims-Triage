"""Tests for app/plans.py and the hand-written fixtures/plans/plans.json."""
import json

import pytest
from pydantic import ValidationError

from app.plans import DEFAULT_FIXTURE, Plan, load_plans


def test_loads_from_the_fixture_file():
    plan_file = load_plans()
    assert plan_file.schema_version == 1
    assert 3 <= len(plan_file.plans) <= 4
    codes = {p.plan_code for p in plan_file.plans}
    assert len(codes) == len(plan_file.plans)


def test_every_plan_defines_copays_deductible_coverage_and_network_rules():
    plan_file = load_plans()
    for plan in plan_file.plans:
        assert plan.deductible_cents >= 0
        assert plan.copays_cents, f"{plan.plan_code} has no copays"
        assert plan.covered_services, f"{plan.plan_code} has no covered services"
        assert plan.excluded_services, f"{plan.plan_code} has no excluded services"
        assert plan.network_rules is not None


def test_malformed_plan_missing_deductible_fails_validation():
    base = json.loads(DEFAULT_FIXTURE.read_text())["plans"][0]
    del base["deductible_cents"]
    with pytest.raises(ValidationError):
        Plan.model_validate(base)


def test_malformed_plan_negative_copay_fails_validation():
    base = json.loads(DEFAULT_FIXTURE.read_text())["plans"][0]
    base["copays_cents"] = {**base["copays_cents"], "primary_care_visit": -100}
    with pytest.raises(ValidationError):
        Plan.model_validate(base)


def test_malformed_plan_empty_covered_services_fails_validation():
    base = json.loads(DEFAULT_FIXTURE.read_text())["plans"][0]
    base["covered_services"] = []
    with pytest.raises(ValidationError):
        Plan.model_validate(base)
