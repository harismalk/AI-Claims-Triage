"""Loads and validates the hand-written plan fixture (fixtures/plans/plans.json)."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "plans" / "plans.json"


class NetworkRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    out_of_network_covered: bool
    out_of_network_coinsurance_pct: int | None = Field(default=None, ge=0, le=100)
    referral_required_for_specialist: bool


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str
    name: str
    plan_year: int
    deductible_cents: int = Field(ge=0)
    out_of_pocket_max_cents: int = Field(ge=0)
    copays_cents: dict[str, int]
    covered_services: list[str]
    excluded_services: list[str]
    network_rules: NetworkRules

    @field_validator("copays_cents")
    @classmethod
    def _copays_non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("copays_cents must define at least one service type")
        for service, cents in v.items():
            if cents < 0:
                raise ValueError(f"copay for {service!r} is negative: {cents}")
        return v

    @field_validator("covered_services")
    @classmethod
    def _covered_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("covered_services must not be empty")
        return v


class PlanFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    plans: list[Plan]


def load_plans(path: Path = DEFAULT_FIXTURE) -> PlanFile:
    data = json.loads(Path(path).read_text())
    return PlanFile.model_validate(data)
