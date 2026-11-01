---
id: DICT-legacy-schema
status: current
covers: [db/schema.sql, app/generate_data.py]
---
# DICT-legacy-schema · Legacy database, reverse-engineered

Written as if inherited: every column mapped to its meaning, every code
resolved, every quirk named. Schema lives in `db/schema.sql`; the seeded data
and its NOTE_TXT/VISIT_ID conventions live in `app/generate_data.py`.

## STS_CD_LKUP · status/reason/type code lookup

Composite key `(CD_TYP, CD_VAL)`. Every bare code column elsewhere in the
schema is meaningless without a join through here.

| Column | Meaning |
|---|---|
| `CD_TYP` | Which code family this row belongs to: `CLM_STS`, `MBR_STS`, `NET_STS`, `ADJ_RSN`, `DISP_TYP`, `DISP_STS` |
| `CD_VAL` | The short code itself, e.g. `PD`, `ACT`, `DUP` |
| `CD_DESC` | Human-readable description |

### Seeded values, by `CD_TYP`

| CD_TYP | Values | Meaning |
|---|---|---|
| `CLM_STS` | `PD`, `DEN`, `PND` | Paid, Denied, Pending |
| `MBR_STS` | `ACT`, `TRM` | Active, Terminated |
| `NET_STS` | `INN`, `OON` | In network, Out of network |
| `ADJ_RSN` | `DUP`, `BIL`, `DOC`, `COV` | Duplicate claim, Billing error, Missing documents, Not covered |
| `DISP_TYP` | `DUP`, `BIL`, `DOC`, `COV` | Same four reasons, as a dispute's filed type (see `record/1-truth/DOMAIN-claims-disputes.md`) |
| `DISP_STS` | `OPN`, `RSLV`, `ESC` | Open, Resolved, Escalated to adjuster |

## PLAN_MAST · insurance plans

| Column | Meaning |
|---|---|
| `PLAN_CD` | Plan code, primary key. Matches `plan_code` in `fixtures/plans/plans.json` (the copay/deductible/coverage/network terms live there, not in this table -- see T1.2) |
| `PLAN_NM` | Plan display name |
| `PLAN_YR` | Plan year |

## MBR_MAST · members

| Column | Meaning |
|---|---|
| `MBR_ID_NBR` | Member ID, primary key |
| `MBR_LST_NM`, `MBR_FST_NM` | Last/first name (synthetic) |
| `MBR_DOB` | Date of birth, `CHAR(8)` `YYYYMMDD` -- not a native `DATE` |
| `PLAN_CD` | FK to `PLAN_MAST` |
| `MBR_STS_CD` | Resolve via `STS_CD_LKUP(CD_TYP='MBR_STS')`: `ACT` or `TRM` |
| `MBR_EFF_DT` | Plan effective date, `YYYYMMDD` |
| `MBR_TERM_DT` | Plan termination date, `YYYYMMDD`. **NULL while the member is still active** -- not "unknown," genuinely not-yet-terminated |

## PRV_MAST · providers

| Column | Meaning |
|---|---|
| `PRV_ID_NBR` | Provider ID, primary key |
| `PRV_NM` | Provider or group name (synthetic) |
| `PRV_TIN` | Tax ID. **NULL for providers onboarded before TIN capture began** -- a null here is not a data-quality bug, it's history |
| `PRV_NET_STS_CD` | Resolve via `STS_CD_LKUP(CD_TYP='NET_STS')`: `INN` or `OON` |
| `PRV_SPEC_CD` | Specialty code (free-standing short code, e.g. `PCP`, `CARD`; not in `STS_CD_LKUP`) |

## CLM_HDR · claims

| Column | Meaning |
|---|---|
| `CLM_ID_NBR` | Claim ID, primary key |
| `MBR_ID_NBR`, `PRV_ID_NBR` | FKs to member and provider |
| `DT_OF_SVC` | Date of service, `YYYYMMDD` |
| `CLM_SUBMIT_DT` | Date the claim was submitted, `YYYYMMDD` |
| `PROC_CD` | Procedure code. Maps to a service type (`primary_care_visit`, `specialist_visit`, `emergency_room`, `urgent_care`, `generic_drug`, `brand_drug`, `preventive_care`, `lab_test`, `imaging`, `hospital_stay`, `mental_health_visit`, `physical_therapy`) -- the catalog lives in `app.generate_data.PROC_CATALOG`, not in this table |
| `CLM_STS_CD` | Resolve via `STS_CD_LKUP(CD_TYP='CLM_STS')`: `PD`, `DEN`, or `PND` |
| `CLM_AMT` | Billed/charged amount. `NUMERIC(10,2)` -- a real number |
| `ADJ_AMT` | Amount actually adjudicated/paid. **`VARCHAR(20)` holding strings like `'$123.45'`**, not a number; NULL until the claim is paid |
| `ADJ_RSN_CD` | Primary denial reason, set only when `CLM_STS_CD='DEN'`. Resolve via `STS_CD_LKUP(CD_TYP='ADJ_RSN')` |
| `ADJ_RSN_2` | Secondary denial reason. Only populated when a second factor applies (~30% of denied claims in the generator); otherwise NULL |
| `VISIT_ID` | Free-text key grouping claims from the same visit (e.g. two procedures billed separately for one visit). Not always set |
| `NOTE_TXT` | Free text whose meaning depends on `CLM_STS_CD` and `ADJ_RSN_CD` -- the single ugliest column in the schema. Conventions used by the seeded data (`app.generate_data`): for `ADJ_RSN_CD='DOC'`, either `'DOCS_ON_FILE'` (docs were in fact received -- the denial was wrong) or `'DOCS_MISSING'` (denial was correct); for `ADJ_RSN_CD='COV'`, `'EXCLUDED:<service_type>'` naming which plan exclusion applied. Any other claim typically has `NOTE_TXT IS NULL` |

## DISP_HDR · disputes

| Column | Meaning |
|---|---|
| `DISP_ID_NBR` | Dispute ID, primary key |
| `CLM_ID_NBR` | FK to the disputed claim |
| `DISP_TYP_CD` | Resolve via `STS_CD_LKUP(CD_TYP='DISP_TYP')`: `DUP`, `BIL`, `DOC`, or `COV` |
| `DISP_FILED_DT` | Date the dispute was filed, `YYYYMMDD` |
| `DISP_STS_CD` | Resolve via `STS_CD_LKUP(CD_TYP='DISP_STS')`: `OPN`, `RSLV`, or `ESC` |
| `DISP_RESLN_AMT` | Amount paid/refunded on resolution. NULL until resolved |
| `DISP_RESLN_DT` | Resolution date, `YYYYMMDD`. NULL until resolved |

**Not in this table:** the member's complaint text. A real intake system
sitting in front of this legacy platform would capture that, not the claims
backend itself. It's generated and committed separately
(`fixtures/complaints/complaints.json`, keyed by `DISP_ID_NBR`) and loaded by
`app.complaints.load_complaints()` -- see [[DEC-0004-complaint-text-fixture]].

## LGCY_REQ_LOG · legacy write-API idempotency log

Added in T2.2. Not part of the original 2011 schema design; the single table
every write tool's request key is checked against before any write is applied.

| Column | Meaning |
|---|---|
| `REQ_KEY` | Caller-chosen idempotency key, primary key. A repeated key returns the cached `RESPONSE_XML` instead of re-applying the write |
| `RESPONSE_XML` | The exact XML response returned the first time this key was seen |
| `CREATED_AT` | When the request was first processed |

## Deliberate legacy quirks

| Quirk | Where | Why it's realistic |
|---|---|---|
| Cryptic abbreviated column names | All tables, e.g. `CLM_STS_CD`, `ADJ_RSN_2`, `MBR_ID_NBR` | 2000s-era mainframe-influenced naming conventions that outlived the people who chose them |
| Dates as `CHAR(8)` `YYYYMMDD` strings, not `DATE` | `MBR_DOB`, `MBR_EFF_DT`, `MBR_TERM_DT`, `DT_OF_SVC`, `CLM_SUBMIT_DT`, `DISP_FILED_DT`, `DISP_RESLN_DT` | Predates native date types being trusted; every date needs parsing in application code |
| Status/reason/type codes are bare strings, not enums | `CLM_STS_CD`, `MBR_STS_CD`, `ADJ_RSN_CD`, `ADJ_RSN_2`, `DISP_TYP_CD`, `DISP_STS_CD`, `PRV_NET_STS_CD` | Meaning only resolvable by joining `STS_CD_LKUP(CD_TYP, CD_VAL)` |
| Inconsistent money typing | `CLM_HDR.CLM_AMT` is `NUMERIC(10,2)`; `CLM_HDR.ADJ_AMT` is `VARCHAR(20)` holding strings like `'$123.45'` | A later feature (adjustment reporting) exported amounts as formatted strings and the column was never fixed |
| Sometimes-null fields | `ADJ_RSN_2` (secondary reason, only set when a second factor applies), `PRV_TIN` (null for providers onboarded before TIN capture began), `MBR_TERM_DT` (null while active) | Columns added mid-life of the system that don't apply to every row |
| One free-text column, two unrelated meanings | `NOTE_TXT`: `DOCS_ON_FILE`/`DOCS_MISSING` for `DOC` denials, `EXCLUDED:<type>` for `COV` denials | No one ever added a proper column when a new case came up; they just overloaded the existing notes field |

## Decisions

- [[DEC-0003-project-record]]
- [[DEC-0004-complaint-text-fixture]]
