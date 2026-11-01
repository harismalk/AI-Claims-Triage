"""Stores adjuster overrides: what the agent proposed, what the adjuster
chose, and why. Powers the correction loop -- per
record/1-truth/ARCH-system-overview.md's flow, "adjuster override -> effect
diff -> grouped failure -> new golden case" -- and CP5's demo (override a
recommendation in the UI, see a new eval case appear via evals.promote_override).

Stored in a local JSON Lines file, not the legacy database: an override
record is OUR system's own data, not something the legacy claims platform
would ever have held -- the same reasoning DEC-0004 applied to complaint text.
Only true overrides are recorded here, not plain accepts: there's nothing to
learn from a case where the agent was already right.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

OVERRIDES_FILE = Path(__file__).resolve().parent.parent / "data" / "overrides.jsonl"


@dataclass
class OverrideRecord:
    dispute_id: int
    claim_id: int
    reason_code: str
    proposed_decision: str | None       # the specialist's proposal, or None if no specialist existed
    proposed_amount_cents: int | None
    chosen_decision: str                # the adjuster's decision
    chosen_amount_cents: int
    reason: str                         # why the adjuster chose differently
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def changed_decision(self) -> bool:
        return self.proposed_decision is not None and self.proposed_decision != self.chosen_decision

    @property
    def changed_amount(self) -> bool:
        return self.proposed_amount_cents is not None and self.proposed_amount_cents != self.chosen_amount_cents

    @property
    def failure_pattern(self) -> str:
        """A simple bucket describing what kind of disagreement this override represents."""
        if self.proposed_decision is None:
            return "no_recommendation"
        if self.changed_decision:
            return f"decision_changed:{self.proposed_decision}->{self.chosen_decision}"
        if self.changed_amount:
            return "amount_changed"
        return "accepted_as_proposed"


def record_override(record: OverrideRecord) -> None:
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OVERRIDES_FILE.open("a") as f:
        f.write(json.dumps(asdict(record)) + "\n")


def load_overrides() -> list[OverrideRecord]:
    if not OVERRIDES_FILE.exists():
        return []
    return [OverrideRecord(**json.loads(line)) for line in OVERRIDES_FILE.read_text().splitlines() if line.strip()]


def group_by_failure_pattern(records: list[OverrideRecord]) -> dict[str, list[OverrideRecord]]:
    groups: dict[str, list[OverrideRecord]] = {}
    for r in records:
        groups.setdefault(r.failure_pattern, []).append(r)
    return groups
