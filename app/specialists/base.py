"""Shared proposal shape every specialist returns. Per
[[DEC-0001-propose-gate-execute]], this is all a specialist ever produces --
it never calls a write tool. The decision gate (T3.4) re-checks it before
anything is acted on."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Proposal(BaseModel):
    """A specialist's structured proposal for one dispute."""

    dispute_id: int
    decision: Literal["reverse", "deny", "escalate"]
    amount_cents: int
    evidence_claim_ids: list[int]
    rationale: str
