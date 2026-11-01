"""The clunky legacy write API: an XML request/response interface, like
something from 2008, that is the ONLY code path allowed to write to CLM_HDR
or DISP_HDR.

Per record/1-truth/ARCH-system-overview.md ("nothing outside the tool runtime
touches the legacy system") and [[DEC-0001-propose-gate-execute]] (specialists
propose, executors write), app.write_tools builds an XML request and hands it
here -- it never issues SQL itself.

Idempotency: every request carries a RequestKey. The cache key actually stored
in LGCY_REQ_LOG is "<request-tag>:<RequestKey>", not the bare RequestKey --
a caller resolving one dispute legitimately issues several different request
types (e.g. UpdateClaimStatusRequest, IssueAdjustmentRequest,
ResolveDisputeRequest) that may reasonably share one RequestKey for the
overall action; scoping by request type too means those distinct operations
never collide with each other, while a true retry of the SAME request type
and key still returns the original cached response instead of re-applying.
"""
from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET

import psycopg2
import psycopg2.extras

from app.generate_data import default_dsn


class LegacyApiFault(Exception):
    """Raised for a malformed or unprocessable legacy API request."""


def _connect():
    return psycopg2.connect(default_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)


def _dollars_str(cents: int) -> str:
    return f"${cents / 100:.2f}"


def call_legacy_api(xml_request: str) -> tuple[str, bool]:
    """Send an XML request to the legacy claims API.

    Args:
        xml_request: the raw XML request body. Must have a <RequestKey> and be
            one of <UpdateClaimStatusRequest>, <IssueAdjustmentRequest>, or
            <ResolveDisputeRequest>.

    Returns:
        (xml_response, replayed) -- replayed is True if this RequestKey was
        already processed, in which case the write was NOT re-applied and the
        original cached response is returned verbatim.

    Raises:
        LegacyApiFault: missing RequestKey, unknown request type, or no
            matching claim.
    """
    try:
        root = ET.fromstring(xml_request)
    except ET.ParseError as e:
        raise LegacyApiFault(f"malformed XML request: {e}") from e

    req_key = root.findtext("RequestKey")
    if not req_key:
        raise LegacyApiFault("request is missing <RequestKey>")
    cache_key = f"{root.tag}:{req_key}"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT response_xml FROM lgcy_req_log WHERE req_key = %s", (cache_key,))
        cached = cur.fetchone()
        if cached:
            return cached["response_xml"], True

        if root.tag == "UpdateClaimStatusRequest":
            response = _handle_update_claim_status(cur, root)
        elif root.tag == "IssueAdjustmentRequest":
            response = _handle_issue_adjustment(cur, root)
        elif root.tag == "ResolveDisputeRequest":
            response = _handle_resolve_dispute(cur, root)
        else:
            raise LegacyApiFault(f"unknown request type <{root.tag}>")

        cur.execute(
            "INSERT INTO lgcy_req_log (req_key, response_xml) VALUES (%s, %s)",
            (cache_key, response),
        )
        conn.commit()
        return response, False


def _handle_update_claim_status(cur, root: ET.Element) -> str:
    claim_id = int(root.findtext("ClaimId", ""))
    new_status_cd = root.findtext("NewStatusCd", "")
    cur.execute("UPDATE clm_hdr SET clm_sts_cd = %s WHERE clm_id_nbr = %s", (new_status_cd, claim_id))
    if cur.rowcount == 0:
        raise LegacyApiFault(f"no such claim {claim_id}")
    return (f"<UpdateClaimStatusResponse><ClaimId>{claim_id}</ClaimId>"
            f"<Status>OK</Status></UpdateClaimStatusResponse>")


def _handle_issue_adjustment(cur, root: ET.Element) -> str:
    claim_id = int(root.findtext("ClaimId", ""))
    amount_cents = int(root.findtext("AmountCents", ""))
    cur.execute("UPDATE clm_hdr SET adj_amt = %s WHERE clm_id_nbr = %s",
                (_dollars_str(amount_cents), claim_id))
    if cur.rowcount == 0:
        raise LegacyApiFault(f"no such claim {claim_id}")
    return (f"<IssueAdjustmentResponse><ClaimId>{claim_id}</ClaimId>"
            f"<AmountCents>{amount_cents}</AmountCents><Status>OK</Status></IssueAdjustmentResponse>")


def _handle_resolve_dispute(cur, root: ET.Element) -> str:
    dispute_id = int(root.findtext("DisputeId", ""))
    resolution_amount_cents = int(root.findtext("ResolutionAmountCents", ""))
    today = datetime.date.today().strftime("%Y%m%d")
    cur.execute(
        "UPDATE disp_hdr SET disp_sts_cd = 'RSLV', disp_resln_amt = %s, disp_resln_dt = %s "
        "WHERE disp_id_nbr = %s",
        (resolution_amount_cents / 100, today, dispute_id),
    )
    if cur.rowcount == 0:
        raise LegacyApiFault(f"no such dispute {dispute_id}")
    return (f"<ResolveDisputeResponse><DisputeId>{dispute_id}</DisputeId>"
            f"<ResolutionAmountCents>{resolution_amount_cents}</ResolutionAmountCents>"
            f"<Status>OK</Status></ResolveDisputeResponse>")
