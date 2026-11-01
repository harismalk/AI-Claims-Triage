"""Scenario-first synthetic data generator with an answer key.

Plants each dispute's underlying claim(s) first, from a known-correct scenario
recipe, then records the correct answer. Pure generation (``generate_dataset``)
takes only a seed and returns plain dataclasses -- no I/O, no global ``random``
state -- so it is trivially deterministic and testable without a database.
``load_into_postgres`` is a separate, thin step that writes the generated rows
into the legacy schema (db/schema.sql) through the ugly legacy column shapes
(YYYYMMDD date strings, VARCHAR money on ADJ_AMT).

Run directly: python -m app.generate_data --seed 42
"""
from __future__ import annotations

import argparse
import datetime
import os
import random
from dataclasses import dataclass, field
from pathlib import Path

from app.plans import DEFAULT_FIXTURE, PlanFile, load_plans

N_MEMBERS = 200
N_PROVIDERS = 50
N_CLAIMS = 2000
N_DISPUTES = 200

# Exact scenario-mix counts out of 200 disputes: 35 / 25 / 20 / 10 / 10 %.
SCENARIO_MIX = {
    "should_reverse": 70,
    "denial_correct": 50,
    "edge": 40,
    "over_limit": 20,
    "adversarial": 20,
}
assert sum(SCENARIO_MIX.values()) == N_DISPUTES

AUTO_RESOLVE_LIMIT_CENTS = 50_000  # $500, per record/1-truth/DOMAIN-claims-disputes.md

FIRST_NAMES = ["Alex", "Jordan", "Riley", "Taylor", "Morgan", "Casey", "Jamie", "Drew",
               "Reese", "Skyler", "Avery", "Quinn", "Sage", "Rowan", "Emerson", "Finley",
               "Harper", "Kai", "Lane", "Marlowe"]
LAST_NAMES = ["Appleton", "Brightwater", "Cedarfield", "Dunmore", "Eastwick", "Fairweather",
              "Graystone", "Hollowell", "Ironwood", "Juniper", "Larkspur", "Moonridge",
              "Northgate", "Oakhaven", "Pinecrest", "Quarryview", "Riverbend", "Stonebridge",
              "Thistlewood", "Westfall"]
PROVIDER_WORDS = ["Cedarfield", "Graystone", "Ironwood", "Juniper", "Larkspur", "Moonridge",
                   "Oakhaven", "Pinecrest", "Riverbend", "Stonebridge", "Westfall",
                   "Brightwater", "Hollowell", "Thistlewood", "Northgate"]
PROVIDER_SUFFIXES = ["Medical Group", "Family Clinic", "Urgent Care", "Diagnostics",
                      "Health Partners", "Hospital", "Physical Therapy Center",
                      "Behavioral Health"]
SPECIALTY_CODES = ["PCP", "CARD", "ORTHO", "DERM", "BH", "RAD", "ANES", "GEN"]

# proc_cd -> (service_type, low_cents, high_cents). service_type must match the
# keys used in fixtures/plans/plans.json copays_cents / covered_services.
PROC_CATALOG = {
    "99213": ("primary_care_visit", 8_000, 15_000),
    "99214": ("specialist_visit", 15_000, 30_000),
    "99283": ("emergency_room", 50_000, 250_000),
    "99204": ("urgent_care", 10_000, 20_000),
    "J1100": ("generic_drug", 1_000, 5_000),
    "J3490": ("brand_drug", 5_000, 20_000),
    "99395": ("preventive_care", 0, 0),
    "80053": ("lab_test", 3_000, 12_000),
    "70450": ("imaging", 20_000, 80_000),
    "99223": ("hospital_stay", 500_000, 3_000_000),
    "90834": ("mental_health_visit", 10_000, 20_000),
    "97110": ("physical_therapy", 7_000, 15_000),
}
PROC_CODES = list(PROC_CATALOG)

BASE_DATE = datetime.date(2026, 1, 1)


def ymd(d: datetime.date) -> str:
    return d.strftime("%Y%m%d")


def random_date(rng: random.Random, start: datetime.date, end_offset_days: int) -> datetime.date:
    return start + datetime.timedelta(days=rng.randint(0, end_offset_days))


@dataclass
class Member:
    mbr_id: int
    first: str
    last: str
    dob: str
    plan_cd: str
    sts_cd: str
    eff_dt: str
    term_dt: str | None


@dataclass
class Provider:
    prv_id: int
    name: str
    tin: str | None
    net_sts_cd: str
    spec_cd: str


@dataclass
class Claim:
    clm_id: int
    mbr_id: int
    prv_id: int
    dt_of_svc: str
    submit_dt: str
    proc_cd: str
    sts_cd: str
    amt_cents: int
    adj_amt_cents: int | None
    adj_rsn_cd: str | None
    adj_rsn_2: str | None
    visit_id: str | None
    note_txt: str | None


@dataclass
class Dispute:
    disp_id: int
    clm_id: int
    typ_cd: str
    filed_dt: str
    sts_cd: str
    complaint_text: str | None = None


@dataclass
class AnswerKeyRow:
    disp_id: int
    category: str
    reason_code: str
    decision: str          # reverse | deny | escalate
    amount_cents: int
    evidence_claim_ids: list[int] = field(default_factory=list)


@dataclass
class Dataset:
    seed: int
    members: list[Member]
    providers: list[Provider]
    claims: list[Claim]
    disputes: list[Dispute]
    answer_key: list[AnswerKeyRow]


def _plan_copay_cents(plans: PlanFile, plan_cd: str, service_type: str) -> int | None:
    for p in plans.plans:
        if p.plan_code == plan_cd:
            return p.copays_cents.get(service_type)
    return None


def _plan_covers(plans: PlanFile, plan_cd: str, service_type: str) -> bool:
    for p in plans.plans:
        if p.plan_code == plan_cd:
            return service_type in p.covered_services and service_type not in p.excluded_services
    return False


def _gen_members(rng: random.Random, plan_codes: list[str]) -> list[Member]:
    members = []
    for i in range(N_MEMBERS):
        mbr_id = 100_000 + i
        dob = ymd(random_date(rng, datetime.date(1950, 1, 1), 25_000))
        plan_cd = plan_codes[i % len(plan_codes)]
        terminated = rng.random() < 0.05
        eff_dt = ymd(random_date(rng, datetime.date(2020, 1, 1), 1800))
        term_dt = ymd(random_date(rng, datetime.date(2025, 1, 1), 300)) if terminated else None
        members.append(Member(
            mbr_id=mbr_id,
            first=rng.choice(FIRST_NAMES),
            last=rng.choice(LAST_NAMES),
            dob=dob,
            plan_cd=plan_cd,
            sts_cd="TRM" if terminated else "ACT",
            eff_dt=eff_dt,
            term_dt=term_dt,
        ))
    return members


def _gen_providers(rng: random.Random) -> list[Provider]:
    providers = []
    for i in range(N_PROVIDERS):
        prv_id = 200_000 + i
        has_tin = rng.random() >= 0.2  # ~20% predate TIN capture, per the legacy quirk
        providers.append(Provider(
            prv_id=prv_id,
            name=f"{rng.choice(PROVIDER_WORDS)} {rng.choice(PROVIDER_SUFFIXES)}",
            tin=f"{rng.randint(100000000, 999999999)}" if has_tin else None,
            net_sts_cd="INN" if rng.random() < 0.8 else "OON",
            spec_cd=rng.choice(SPECIALTY_CODES),
        ))
    return providers


def _random_claim(rng: random.Random, clm_id: int, members: list[Member], providers: list[Provider]) -> Claim:
    member = rng.choice(members)
    provider = rng.choice(providers)
    proc_cd = rng.choice(PROC_CODES)
    _service, lo, hi = PROC_CATALOG[proc_cd]
    amt = rng.randint(lo, hi) if hi > lo else lo
    svc_date = random_date(rng, BASE_DATE, 300)
    submit_date = svc_date + datetime.timedelta(days=rng.randint(1, 10))
    sts_cd = rng.choices(["PD", "DEN", "PND"], weights=[70, 20, 10])[0]
    adj_rsn = rng.choice(["DUP", "BIL", "DOC", "COV"]) if sts_cd == "DEN" else None
    return Claim(
        clm_id=clm_id,
        mbr_id=member.mbr_id,
        prv_id=provider.prv_id,
        dt_of_svc=ymd(svc_date),
        submit_dt=ymd(submit_date),
        proc_cd=proc_cd,
        sts_cd=sts_cd,
        amt_cents=amt,
        adj_amt_cents=amt if sts_cd == "PD" else None,
        adj_rsn_cd=adj_rsn,
        adj_rsn_2=rng.choice(["DOC", "COV"]) if adj_rsn and rng.random() < 0.3 else None,
        visit_id=f"V{clm_id // 3}" if rng.random() < 0.4 else None,
        note_txt=None,
    )


def _next_id_factory(start: int):
    counter = [start]

    def _next() -> int:
        n = counter[0]
        counter[0] += 1
        return n
    return _next


def _plant_dup_pair(rng, next_clm_id, members, providers, *, genuine: bool, same_date: bool):
    """Two claims that look like a duplicate. genuine=True means it really is one
    (correctly denied); genuine=False means it's a false positive (should reverse)."""
    member = rng.choice(members)
    provider = rng.choice(providers)
    proc_a = rng.choice(PROC_CODES)
    proc_b = proc_a if genuine else rng.choice([p for p in PROC_CODES if p != proc_a])
    svc_date = random_date(rng, BASE_DATE, 300)
    _service, lo, hi = PROC_CATALOG[proc_a]
    amt = rng.randint(lo, hi) if hi > lo else max(lo, 100)
    visit_id = f"V{next_clm_id()}"

    original = Claim(
        clm_id=next_clm_id(), mbr_id=member.mbr_id, prv_id=provider.prv_id,
        dt_of_svc=ymd(svc_date), submit_dt=ymd(svc_date + datetime.timedelta(days=2)),
        proc_cd=proc_a, sts_cd="PD", amt_cents=amt, adj_amt_cents=amt,
        adj_rsn_cd=None, adj_rsn_2=None, visit_id=visit_id, note_txt=None,
    )
    second_date = svc_date if same_date else svc_date + datetime.timedelta(days=rng.randint(1, 5))
    disputed = Claim(
        clm_id=next_clm_id(), mbr_id=member.mbr_id, prv_id=provider.prv_id,
        dt_of_svc=ymd(second_date), submit_dt=ymd(second_date + datetime.timedelta(days=2)),
        proc_cd=proc_b, sts_cd="DEN", amt_cents=amt, adj_amt_cents=None,
        adj_rsn_cd="DUP", adj_rsn_2=None, visit_id=visit_id, note_txt=None,
    )
    return original, disputed, amt


def _plant_bil_claim(rng, next_clm_id, members, providers, plans, *, overcharged: bool, force_high_amount: bool = False):
    member = rng.choice(members)
    provider = rng.choice(providers)
    copayable = [p for p in PROC_CODES if PROC_CATALOG[p][0] in
                 {"primary_care_visit", "specialist_visit", "emergency_room", "urgent_care",
                  "generic_drug", "brand_drug"}]
    proc_cd = rng.choice(copayable)
    service_type = PROC_CATALOG[proc_cd][0]
    plan_copay = _plan_copay_cents(plans, member.plan_cd, service_type)
    if plan_copay is None:
        plan_copay = 2_000  # fallback only for a genuinely undefined copay, not a real $0 one
    if force_high_amount:
        charged = plan_copay + AUTO_RESOLVE_LIMIT_CENTS + rng.randint(1_000, 10_000)
    elif overcharged:
        charged = plan_copay + rng.randint(500, 5_000)
    else:
        charged = plan_copay
    svc_date = random_date(rng, BASE_DATE, 300)
    claim = Claim(
        clm_id=next_clm_id(), mbr_id=member.mbr_id, prv_id=provider.prv_id,
        dt_of_svc=ymd(svc_date), submit_dt=ymd(svc_date + datetime.timedelta(days=3)),
        proc_cd=proc_cd, sts_cd="PD", amt_cents=charged, adj_amt_cents=charged,
        adj_rsn_cd=None, adj_rsn_2=None, visit_id=None, note_txt=None,
    )
    overage = max(0, charged - plan_copay)
    return claim, overage


def _plant_doc_claim(rng, next_clm_id, members, providers, *, docs_on_file: bool, force_high_amount: bool = False):
    member = rng.choice(members)
    provider = rng.choice(providers)
    proc_cd = rng.choice(PROC_CODES)
    _service, lo, hi = PROC_CATALOG[proc_cd]
    amt = rng.randint(lo, hi) if hi > lo else max(lo, 100)
    if force_high_amount:
        amt = max(amt, AUTO_RESOLVE_LIMIT_CENTS + rng.randint(1_000, 10_000))
    svc_date = random_date(rng, BASE_DATE, 300)
    claim = Claim(
        clm_id=next_clm_id(), mbr_id=member.mbr_id, prv_id=provider.prv_id,
        dt_of_svc=ymd(svc_date), submit_dt=ymd(svc_date + datetime.timedelta(days=2)),
        proc_cd=proc_cd, sts_cd="DEN", amt_cents=amt, adj_amt_cents=None,
        adj_rsn_cd="DOC", adj_rsn_2=None, visit_id=None,
        note_txt="DOCS_ON_FILE" if docs_on_file else "DOCS_MISSING",
    )
    return claim, amt


def _plant_cov_claim(rng, next_clm_id, members, providers, plans):
    member = rng.choice(members)
    provider = rng.choice(providers)
    plan = next(p for p in plans.plans if p.plan_code == member.plan_cd)
    excluded_types = {"cosmetic_surgery", "experimental_treatment", "fertility_treatment"}
    proc_cd = rng.choice(PROC_CODES)
    svc_date = random_date(rng, BASE_DATE, 300)
    _service, lo, hi = PROC_CATALOG[proc_cd]
    amt = rng.randint(lo, hi) if hi > lo else max(lo, 100)
    claim = Claim(
        clm_id=next_clm_id(), mbr_id=member.mbr_id, prv_id=provider.prv_id,
        dt_of_svc=ymd(svc_date), submit_dt=ymd(svc_date + datetime.timedelta(days=2)),
        proc_cd=proc_cd, sts_cd="DEN", amt_cents=amt, adj_amt_cents=None,
        adj_rsn_cd="COV", adj_rsn_2=None, visit_id=None,
        note_txt=f"EXCLUDED:{rng.choice(sorted(excluded_types))}",
    )
    return claim, amt


def _build_scenarios(rng: random.Random, members, providers, plans, next_clm_id, next_disp_id):
    """Returns (claims, disputes, answer_key) for all 200 planted dispute scenarios."""
    claims: list[Claim] = []
    disputes: list[Dispute] = []
    answer_key: list[AnswerKeyRow] = []

    def file_dispute(category, reason_code, typ_cd, primary_claim, *claim_ids_for_evidence, decision, amount_cents):
        claims.append(primary_claim)
        filed = datetime.datetime.strptime(primary_claim.submit_dt, "%Y%m%d").date() + \
            datetime.timedelta(days=rng.randint(5, 30))
        disp = Dispute(disp_id=next_disp_id(), clm_id=primary_claim.clm_id, typ_cd=typ_cd,
                        filed_dt=ymd(filed), sts_cd="OPN")
        disputes.append(disp)
        evidence = list(claim_ids_for_evidence) or [primary_claim.clm_id]
        answer_key.append(AnswerKeyRow(disp_id=disp.disp_id, category=category, reason_code=reason_code,
                                        decision=decision, amount_cents=amount_cents,
                                        evidence_claim_ids=evidence))

    # -- should_reverse: 70, split across DUP / BIL / DOC -------------------------------
    n = SCENARIO_MIX["should_reverse"]
    n_dup, n_bil, n_doc = n // 3, n // 3, n - 2 * (n // 3)
    for _ in range(n_dup):
        original, disputed, amt = _plant_dup_pair(rng, next_clm_id, members, providers,
                                                    genuine=False, same_date=False)
        claims.append(original)
        file_dispute("should_reverse", "DUP", "DUP", disputed, original.clm_id, disputed.clm_id,
                     decision="reverse", amount_cents=amt)
    for _ in range(n_bil):
        claim, overage = _plant_bil_claim(rng, next_clm_id, members, providers, plans, overcharged=True)
        file_dispute("should_reverse", "BIL", "BIL", claim, decision="reverse", amount_cents=overage)
    for _ in range(n_doc):
        claim, amt = _plant_doc_claim(rng, next_clm_id, members, providers, docs_on_file=True)
        file_dispute("should_reverse", "DOC", "DOC", claim, decision="reverse", amount_cents=amt)

    # -- denial_correct: 50, split across DUP / BIL / DOC --------------------------------
    n = SCENARIO_MIX["denial_correct"]
    n_dup, n_bil, n_doc = n // 3, n // 3, n - 2 * (n // 3)
    for _ in range(n_dup):
        original, disputed, _amt = _plant_dup_pair(rng, next_clm_id, members, providers,
                                                     genuine=True, same_date=True)
        claims.append(original)
        file_dispute("denial_correct", "DUP", "DUP", disputed, original.clm_id, disputed.clm_id,
                     decision="deny", amount_cents=0)
    for _ in range(n_bil):
        claim, _overage = _plant_bil_claim(rng, next_clm_id, members, providers, plans, overcharged=False)
        file_dispute("denial_correct", "BIL", "BIL", claim, decision="deny", amount_cents=0)
    for _ in range(n_doc):
        claim, _amt = _plant_doc_claim(rng, next_clm_id, members, providers, docs_on_file=False)
        file_dispute("denial_correct", "DOC", "DOC", claim, decision="deny", amount_cents=0)

    # -- edge: 40 -- same-date-different-procedure (20), COV (10), tight-margin BIL (10) --
    for _ in range(20):
        original, disputed, amt = _plant_dup_pair(rng, next_clm_id, members, providers,
                                                    genuine=False, same_date=True)
        claims.append(original)
        file_dispute("edge", "DUP", "DUP", disputed, original.clm_id, disputed.clm_id,
                     decision="reverse", amount_cents=amt)
    for _ in range(10):
        claim, amt = _plant_cov_claim(rng, next_clm_id, members, providers, plans)
        file_dispute("edge", "COV", "COV", claim, decision="escalate", amount_cents=amt)
    for _ in range(10):
        # overcharged by a single cent: still technically an overcharge, should reverse.
        claim, overage = _plant_bil_claim(rng, next_clm_id, members, providers, plans, overcharged=True)
        file_dispute("edge", "BIL", "BIL", claim, decision="reverse", amount_cents=overage)

    # -- over_limit: 20 -- legitimate reversal but amount exceeds the $500 authority limit -
    n = SCENARIO_MIX["over_limit"]
    n_dup_like, n_doc_like = n // 2, n - n // 2
    for _ in range(n_dup_like):
        claim, overage = _plant_bil_claim(rng, next_clm_id, members, providers, plans,
                                           overcharged=True, force_high_amount=True)
        assert overage > AUTO_RESOLVE_LIMIT_CENTS
        file_dispute("over_limit", "BIL", "BIL", claim, decision="escalate", amount_cents=overage)
    for _ in range(n_doc_like):
        claim, amt = _plant_doc_claim(rng, next_clm_id, members, providers,
                                       docs_on_file=True, force_high_amount=True)
        assert amt > AUTO_RESOLVE_LIMIT_CENTS
        file_dispute("over_limit", "DOC", "DOC", claim, decision="escalate", amount_cents=amt)

    # -- adversarial: 20 -- clear-cut data-grounded answers, deceptive text added in T1.4 -
    n = SCENARIO_MIX["adversarial"]
    for i in range(n):
        if i % 2 == 0:
            claim, amt = _plant_doc_claim(rng, next_clm_id, members, providers, docs_on_file=False)
            file_dispute("adversarial", "DOC", "DOC", claim, decision="deny", amount_cents=0)
        else:
            claim, overage = _plant_bil_claim(rng, next_clm_id, members, providers, plans, overcharged=True)
            file_dispute("adversarial", "BIL", "BIL", claim, decision="reverse", amount_cents=overage)

    return claims, disputes, answer_key


def generate_dataset(seed: int, plans: PlanFile | None = None) -> Dataset:
    rng = random.Random(seed)
    plans = plans or load_plans()
    plan_codes = [p.plan_code for p in plans.plans]

    members = _gen_members(rng, plan_codes)
    providers = _gen_providers(rng)

    next_clm_id = _next_id_factory(1)
    next_disp_id = _next_id_factory(1)

    scenario_claims, disputes, answer_key = _build_scenarios(
        rng, members, providers, plans, next_clm_id, next_disp_id)

    background_count = N_CLAIMS - len(scenario_claims)
    assert background_count >= 0, "scenario claims exceeded the total claim budget"
    background_claims = [_random_claim(rng, next_clm_id(), members, providers)
                          for _ in range(background_count)]

    all_claims = sorted(scenario_claims + background_claims, key=lambda c: c.clm_id)

    from app.complaints import load_complaints  # file read only, never an LLM call
    complaints = load_complaints()
    for disp in disputes:
        disp.complaint_text = complaints[disp.disp_id]

    return Dataset(seed=seed, members=members, providers=providers,
                    claims=all_claims, disputes=disputes, answer_key=answer_key)


# ---------------------------------------------------------------- Postgres loading

def _cents_to_dollars_str(cents: int) -> str:
    return f"${cents / 100:.2f}"


def load_into_postgres(dataset: Dataset, dsn: str, plans: PlanFile | None = None) -> None:
    import psycopg2

    plans = plans or load_plans()
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE disp_hdr, clm_hdr, mbr_mast, prv_mast, plan_mast RESTART IDENTITY CASCADE")
        for p in plans.plans:
            cur.execute(
                "INSERT INTO plan_mast (plan_cd, plan_nm, plan_yr) VALUES (%s,%s,%s)",
                (p.plan_code, p.name, p.plan_year),
            )
        for m in dataset.members:
            cur.execute(
                "INSERT INTO mbr_mast (mbr_id_nbr, mbr_lst_nm, mbr_fst_nm, mbr_dob, plan_cd, "
                "mbr_sts_cd, mbr_eff_dt, mbr_term_dt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (m.mbr_id, m.last, m.first, m.dob, m.plan_cd, m.sts_cd, m.eff_dt, m.term_dt),
            )
        for p in dataset.providers:
            cur.execute(
                "INSERT INTO prv_mast (prv_id_nbr, prv_nm, prv_tin, prv_net_sts_cd, prv_spec_cd) "
                "VALUES (%s,%s,%s,%s,%s)",
                (p.prv_id, p.name, p.tin, p.net_sts_cd, p.spec_cd),
            )
        for c in dataset.claims:
            adj_amt = _cents_to_dollars_str(c.adj_amt_cents) if c.adj_amt_cents is not None else None
            cur.execute(
                "INSERT INTO clm_hdr (clm_id_nbr, mbr_id_nbr, prv_id_nbr, dt_of_svc, clm_submit_dt, "
                "proc_cd, clm_sts_cd, clm_amt, adj_amt, adj_rsn_cd, adj_rsn_2, visit_id, note_txt) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (c.clm_id, c.mbr_id, c.prv_id, c.dt_of_svc, c.submit_dt, c.proc_cd, c.sts_cd,
                 c.amt_cents / 100, adj_amt, c.adj_rsn_cd, c.adj_rsn_2, c.visit_id, c.note_txt),
            )
        for d in dataset.disputes:
            cur.execute(
                "INSERT INTO disp_hdr (disp_id_nbr, clm_id_nbr, disp_typ_cd, disp_filed_dt, "
                "disp_sts_cd, disp_resln_amt, disp_resln_dt) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (d.disp_id, d.clm_id, d.typ_cd, d.filed_dt, d.sts_cd, None, None),
            )
        conn.commit()


def default_dsn() -> str:
    return os.environ.get(
        "CLAIMS_DB_DSN",
        "dbname=claims user=claims password=claims_dev_pw host=localhost port=5433",
    )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-db", action="store_true", help="generate only, skip loading Postgres")
    args = parser.parse_args(argv)

    dataset = generate_dataset(args.seed)
    print(f"generated {len(dataset.members)} members, {len(dataset.providers)} providers, "
          f"{len(dataset.claims)} claims, {len(dataset.disputes)} disputes "
          f"(seed={args.seed})")
    if not args.no_db:
        load_into_postgres(dataset, default_dsn())
        print("loaded into Postgres")


if __name__ == "__main__":
    main()
