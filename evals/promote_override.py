"""Promotes a reviewed adjuster override into a golden case (T4.1), closing
the correction loop: adjuster override -> effect diff -> grouped failure ->
new golden case (record/1-truth/ARCH-system-overview.md). The adjuster's
chosen decision becomes the new ground truth, overriding whatever the
specialist originally proposed.

No separate persistence for the derived case itself: like every other golden
case (T4.1), it's reconstructed fresh each time from a durable source -- there
the T1.3 answer key, here the override record (app.overrides) -- plus a live
run against the dispute, never stored directly.

Run as a single command: python -m evals.promote_override <dispute_id>
"""
from __future__ import annotations

import sys

from app.overrides import load_overrides
from app.router import REASON_TO_SPECIALIST, SPECIALIST_PROPOSE_FNS
from app.tool_runtime import ToolRuntime
from evals.golden import GoldenCase


def promote_override(dispute_id: int) -> GoldenCase:
    """Build a golden case from a reviewed override to dispute_id.

    Raises:
        ValueError: no recorded override, or no such dispute, for dispute_id.
    """
    override = next((o for o in load_overrides() if o.dispute_id == dispute_id), None)
    if override is None:
        raise ValueError(f"no recorded override for dispute {dispute_id}")

    runtime = ToolRuntime(mode="live")
    dispute = runtime.call("get_dispute", dispute_id=dispute_id)
    if dispute is None:
        raise ValueError(f"no dispute {dispute_id}")

    specialist_name = REASON_TO_SPECIALIST.get(dispute.dispute_type_code)
    propose_fn = SPECIALIST_PROPOSE_FNS.get(specialist_name) if specialist_name else None
    proposal = propose_fn(dispute_id, runtime) if propose_fn else None

    claim_ids = sorted({dispute.claim.claim_id, override.claim_id})
    return GoldenCase(
        dispute_id=dispute_id,
        category="adjuster_override",
        filed_reason_code=dispute.dispute_type_code,
        complaint_text=dispute.complaint_text,
        expected_decision=override.chosen_decision,
        expected_amount_cents=override.chosen_amount_cents,
        expected_evidence_claim_ids=[override.claim_id],
        recorded_trace=list(runtime.history),
        snapshot_claim_ids=claim_ids,
        snapshot_dispute_ids=[dispute_id],
        proposal=proposal,
    )


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m evals.promote_override <dispute_id>")
        sys.exit(2)
    dispute_id = int(sys.argv[1])
    case = promote_override(dispute_id)
    print(f"promoted dispute {dispute_id} into a golden case ({case.filed_reason_code}, "
          f"category={case.category}): expected decision={case.expected_decision} "
          f"amount_cents={case.expected_amount_cents}, snapshot claims={case.snapshot_claim_ids}")


if __name__ == "__main__":
    main()
