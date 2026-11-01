"""Write tools over the legacy claims database.

Every tool here only ever builds an XML request and hands it to
app.legacy_api.call_legacy_api -- none issues SQL itself. That module is the
single chokepoint allowed to write to CLM_HDR or DISP_HDR (see its docstring).

Per record/1-truth/ARCH-system-overview.md, specialists propose and never call
these directly; only an executor behind the decision gate does
([[DEC-0001-propose-gate-execute]]) -- T5.1's API is the first such executor.
All are declared side_effect=True so T2.3's tool runtime can fail closed on
them outside live mode.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.legacy_api import call_legacy_api
from app.tool_meta import tool


class WriteResult(BaseModel):
    """Result of a claim-level write tool call."""

    claim_id: int
    request_key: str
    ok: bool
    replayed: bool  # True if this request_key was already processed; the write was NOT re-applied


class DisputeWriteResult(BaseModel):
    """Result of a dispute-level write tool call."""

    dispute_id: int
    request_key: str
    ok: bool
    replayed: bool  # True if this request_key was already processed; the write was NOT re-applied


@tool(side_effect=True)
def update_claim_status(claim_id: int, new_status_code: str, request_key: str) -> WriteResult:
    """Change a claim's status code (e.g. reversing a denial to paid).

    Args:
        claim_id: the claim to update.
        new_status_code: the new CLM_STS_CD value, e.g. "PD", "DEN", "PND".
        request_key: a caller-chosen idempotency key. Retrying this exact call
            with the same request_key will not re-apply the write; it returns
            the original result with replayed=True.

    Returns:
        A WriteResult.

    Raises:
        app.legacy_api.LegacyApiFault: if claim_id does not exist.
    """
    xml_request = (
        f"<UpdateClaimStatusRequest><ClaimId>{claim_id}</ClaimId>"
        f"<NewStatusCd>{new_status_code}</NewStatusCd>"
        f"<RequestKey>{request_key}</RequestKey></UpdateClaimStatusRequest>"
    )
    _response, replayed = call_legacy_api(xml_request)
    return WriteResult(claim_id=claim_id, request_key=request_key, ok=True, replayed=replayed)


@tool(side_effect=True)
def issue_adjustment(claim_id: int, amount_cents: int, request_key: str) -> WriteResult:
    """Issue a payment adjustment on a claim (e.g. a refund of an overcharge,
    or the amount paid on reversal).

    Args:
        claim_id: the claim to adjust.
        amount_cents: the adjusted/paid amount, in cents.
        request_key: a caller-chosen idempotency key. Retrying this exact call
            (even with different amount_cents, e.g. a buggy retry) will not
            re-apply a second write; it returns the original result with
            replayed=True.

    Returns:
        A WriteResult.

    Raises:
        app.legacy_api.LegacyApiFault: if claim_id does not exist.
    """
    xml_request = (
        f"<IssueAdjustmentRequest><ClaimId>{claim_id}</ClaimId>"
        f"<AmountCents>{amount_cents}</AmountCents>"
        f"<RequestKey>{request_key}</RequestKey></IssueAdjustmentRequest>"
    )
    _response, replayed = call_legacy_api(xml_request)
    return WriteResult(claim_id=claim_id, request_key=request_key, ok=True, replayed=replayed)


@tool(side_effect=True)
def resolve_dispute(dispute_id: int, resolution_amount_cents: int, request_key: str) -> DisputeWriteResult:
    """Close out a dispute as resolved (e.g. once an adjuster accepts or
    overrides a recommendation and the corresponding claim writes are done).

    Args:
        dispute_id: the dispute to resolve.
        resolution_amount_cents: the amount paid/refunded on resolution, in
            cents; 0 if the dispute was denied.
        request_key: a caller-chosen idempotency key. Retrying this exact call
            will not re-apply the write; it returns the original result with
            replayed=True.

    Returns:
        A DisputeWriteResult.

    Raises:
        app.legacy_api.LegacyApiFault: if dispute_id does not exist.
    """
    xml_request = (
        f"<ResolveDisputeRequest><DisputeId>{dispute_id}</DisputeId>"
        f"<ResolutionAmountCents>{resolution_amount_cents}</ResolutionAmountCents>"
        f"<RequestKey>{request_key}</RequestKey></ResolveDisputeRequest>"
    )
    _response, replayed = call_legacy_api(xml_request)
    return DisputeWriteResult(dispute_id=dispute_id, request_key=request_key, ok=True, replayed=replayed)
