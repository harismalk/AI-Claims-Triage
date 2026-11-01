"""Read tools over the legacy claims database.

Each function here is a clean, typed read over the ugly legacy schema
(db/schema.sql / record/1-truth/DICT-legacy-schema.md): legacy YYYYMMDD date
strings become `date`, the VARCHAR-money ADJ_AMT column becomes an int number
of cents, and every status/reason code is resolved through STS_CD_LKUP to a
human description. No tool here writes anything, and none returns a raw
legacy column name -- these are the shapes a specialist LLM should see.

Per record/1-truth/ARCH-system-overview.md, this module is the only thing
(besides app.generate_data's seeder) that is allowed to touch the legacy
Postgres database directly.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from app.complaints import load_complaints
from app.generate_data import default_dsn
from app.plans import Plan, load_plans
from app.tool_meta import tool


def _connect():
    return psycopg2.connect(default_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)


def _ymd_to_date(s: str | None) -> datetime.date | None:
    return datetime.datetime.strptime(s, "%Y%m%d").date() if s else None


def _dollars_str_to_cents(s: str | None) -> int | None:
    if s is None:
        return None
    return round(Decimal(s.replace("$", "")) * 100)


def _decimal_to_cents(d) -> int:
    return round(Decimal(d) * 100)


def _resolve_code(cur, cd_typ: str, cd_val: str | None) -> str | None:
    if cd_val is None:
        return None
    cur.execute("SELECT cd_desc FROM sts_cd_lkup WHERE cd_typ = %s AND cd_val = %s", (cd_typ, cd_val))
    row = cur.fetchone()
    return row["cd_desc"] if row else None


class ClaimView(BaseModel):
    """A single claim, with legacy codes resolved and legacy types cleaned up."""

    claim_id: int
    member_id: int
    provider_id: int
    date_of_service: datetime.date
    submit_date: datetime.date
    procedure_code: str
    status_code: str
    status_description: str | None
    billed_amount_cents: int
    paid_amount_cents: int | None
    denial_reason_code: str | None
    denial_reason_description: str | None
    secondary_denial_reason_code: str | None
    secondary_denial_reason_description: str | None
    visit_group_id: str | None
    note: str | None


class DisputeView(BaseModel):
    """A dispute, its disputed claim, and the member's complaint text."""

    dispute_id: int
    claim: ClaimView
    dispute_type_code: str
    dispute_type_description: str | None
    filed_date: datetime.date
    status_code: str
    status_description: str | None
    resolution_amount_cents: int | None
    resolution_date: datetime.date | None
    complaint_text: str | None


class MemberView(BaseModel):
    """A member, with legacy codes resolved and legacy types cleaned up."""

    member_id: int
    first_name: str
    last_name: str
    date_of_birth: datetime.date
    plan_code: str
    status_code: str
    status_description: str | None
    effective_date: datetime.date
    termination_date: datetime.date | None


def _row_to_claim_view(cur, row: dict) -> ClaimView:
    return ClaimView(
        claim_id=row["clm_id_nbr"],
        member_id=row["mbr_id_nbr"],
        provider_id=row["prv_id_nbr"],
        date_of_service=_ymd_to_date(row["dt_of_svc"]),
        submit_date=_ymd_to_date(row["clm_submit_dt"]),
        procedure_code=row["proc_cd"],
        status_code=row["clm_sts_cd"],
        status_description=_resolve_code(cur, "CLM_STS", row["clm_sts_cd"]),
        billed_amount_cents=_decimal_to_cents(row["clm_amt"]),
        paid_amount_cents=_dollars_str_to_cents(row["adj_amt"]),
        denial_reason_code=row["adj_rsn_cd"],
        denial_reason_description=_resolve_code(cur, "ADJ_RSN", row["adj_rsn_cd"]),
        secondary_denial_reason_code=row["adj_rsn_2"],
        secondary_denial_reason_description=_resolve_code(cur, "ADJ_RSN", row["adj_rsn_2"]),
        visit_group_id=row["visit_id"],
        note=row["note_txt"],
    )


@tool(side_effect=False)
def lookup_claim(claim_id: int) -> ClaimView | None:
    """Fetch a single claim by ID.

    Args:
        claim_id: the claim's ID.

    Returns:
        A ClaimView with legacy codes resolved to descriptions and money in
        cents, or None if no claim with that ID exists.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM clm_hdr WHERE clm_id_nbr = %s", (claim_id,))
        row = cur.fetchone()
        return _row_to_claim_view(cur, row) if row else None


@tool(side_effect=False)
def find_similar_claims(claim_id: int) -> list[ClaimView]:
    """Find claims that could be confused with the given claim: same member and
    provider, and either the same procedure code or the same visit (grouped by
    VISIT_ID). Excludes the claim itself. Useful for checking whether a
    denied-as-duplicate claim is really a duplicate, or a distinct service from
    the same visit (the same-date-different-procedure edge case).

    Args:
        claim_id: the claim to find similar claims for.

    Returns:
        Matching claims as ClaimViews, ordered by date of service. Empty list
        if the claim does not exist or nothing else matches.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM clm_hdr WHERE clm_id_nbr = %s", (claim_id,))
        base = cur.fetchone()
        if not base:
            return []
        cur.execute(
            "SELECT * FROM clm_hdr WHERE clm_id_nbr != %s AND mbr_id_nbr = %s AND prv_id_nbr = %s "
            "AND (proc_cd = %s OR (visit_id IS NOT NULL AND visit_id = %s)) "
            "ORDER BY dt_of_svc",
            (claim_id, base["mbr_id_nbr"], base["prv_id_nbr"], base["proc_cd"], base["visit_id"]),
        )
        return [_row_to_claim_view(cur, row) for row in cur.fetchall()]


@tool(side_effect=False)
def get_plan_terms(plan_code: str) -> Plan | None:
    """Fetch a plan's terms: copays, deductible, covered/excluded services, and
    network rules (fixtures/plans/plans.json, not the legacy database).

    Args:
        plan_code: the plan's code, e.g. "GOLD".

    Returns:
        The Plan, or None if no plan with that code exists.
    """
    for plan in load_plans().plans:
        if plan.plan_code == plan_code:
            return plan
    return None


@tool(side_effect=False)
def get_payment_history(member_id: int) -> list[ClaimView]:
    """Fetch a member's paid claims, most recent first. Useful for checking
    whether a copay charged on a disputed claim matches what was actually
    paid for similar services in the past.

    Args:
        member_id: the member's ID.

    Returns:
        Paid claims (status PD) as ClaimViews, most recent date of service first.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM clm_hdr WHERE mbr_id_nbr = %s AND clm_sts_cd = 'PD' ORDER BY dt_of_svc DESC",
            (member_id,),
        )
        return [_row_to_claim_view(cur, row) for row in cur.fetchall()]


@tool(side_effect=False)
def get_dispute(dispute_id: int) -> DisputeView | None:
    """Fetch a dispute: its type/status resolved, its disputed claim attached,
    and the member's original complaint text (from the committed fixture, see
    [[DEC-0004-complaint-text-fixture]] -- complaint text is not stored in the
    legacy database).

    Args:
        dispute_id: the dispute's ID.

    Returns:
        A DisputeView, or None if no dispute with that ID exists.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM disp_hdr WHERE disp_id_nbr = %s", (dispute_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("SELECT * FROM clm_hdr WHERE clm_id_nbr = %s", (row["clm_id_nbr"],))
        claim_row = cur.fetchone()
        complaints = load_complaints()
        return DisputeView(
            dispute_id=row["disp_id_nbr"],
            claim=_row_to_claim_view(cur, claim_row),
            dispute_type_code=row["disp_typ_cd"],
            dispute_type_description=_resolve_code(cur, "DISP_TYP", row["disp_typ_cd"]),
            filed_date=_ymd_to_date(row["disp_filed_dt"]),
            status_code=row["disp_sts_cd"],
            status_description=_resolve_code(cur, "DISP_STS", row["disp_sts_cd"]),
            resolution_amount_cents=_decimal_to_cents(row["disp_resln_amt"]) if row["disp_resln_amt"] is not None else None,
            resolution_date=_ymd_to_date(row["disp_resln_dt"]),
            complaint_text=complaints.get(row["disp_id_nbr"]),
        )


@tool(side_effect=False)
def get_member(member_id: int) -> MemberView | None:
    """Fetch a member by ID: name, plan, and enrollment status. Needed to look
    up which plan's terms (get_plan_terms) apply to a claim.

    Args:
        member_id: the member's ID.

    Returns:
        A MemberView, or None if no member with that ID exists.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM mbr_mast WHERE mbr_id_nbr = %s", (member_id,))
        row = cur.fetchone()
        if not row:
            return None
        return MemberView(
            member_id=row["mbr_id_nbr"],
            first_name=row["mbr_fst_nm"],
            last_name=row["mbr_lst_nm"],
            date_of_birth=_ymd_to_date(row["mbr_dob"]),
            plan_code=row["plan_cd"],
            status_code=row["mbr_sts_cd"],
            status_description=_resolve_code(cur, "MBR_STS", row["mbr_sts_cd"]),
            effective_date=_ymd_to_date(row["mbr_eff_dt"]),
            termination_date=_ymd_to_date(row["mbr_term_dt"]),
        )
