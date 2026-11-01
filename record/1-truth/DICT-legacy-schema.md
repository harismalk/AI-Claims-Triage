---
id: DICT-legacy-schema
status: proposed
covers: [db/schema.sql]
---
# DICT-legacy-schema · Legacy database quirks

Status is `proposed` until T1.5 completes the full column-by-column mapping and
promotes this to `current`. This stub exists to satisfy T1.1's requirement that
deliberate legacy quirks be documented alongside the schema that has them.

## Tables (defined in `db/schema.sql`)

`MBR_MAST` (members), `PLAN_MAST` (plans), `PRV_MAST` (providers), `CLM_HDR`
(claims), `DISP_HDR` (disputes), `STS_CD_LKUP` (status/reason/type code lookup).

## Deliberate legacy quirks

| Quirk | Where | Why it's realistic |
|---|---|---|
| Cryptic abbreviated column names | All tables, e.g. `CLM_STS_CD`, `ADJ_RSN_2`, `MBR_ID_NBR` | 2000s-era mainframe-influenced naming conventions that outlived the people who chose them |
| Dates as `CHAR(8)` `YYYYMMDD` strings, not `DATE` | `MBR_DOB`, `MBR_EFF_DT`, `MBR_TERM_DT`, `DT_OF_SVC`, `CLM_SUBMIT_DT`, `DISP_FILED_DT`, `DISP_RESLN_DT` | Predates native date types being trusted; every date needs parsing in application code |
| Status/reason/type codes are bare strings, not enums | `CLM_STS_CD`, `MBR_STS_CD`, `ADJ_RSN_CD`, `ADJ_RSN_2`, `DISP_TYP_CD`, `DISP_STS_CD`, `PRV_NET_STS_CD` | Meaning only resolvable by joining `STS_CD_LKUP(CD_TYP, CD_VAL)` |
| Inconsistent money typing | `CLM_HDR.CLM_AMT` is `NUMERIC(10,2)`; `CLM_HDR.ADJ_AMT` is `VARCHAR(20)` holding strings like `'$123.45'` | A later feature (adjustment reporting) exported amounts as formatted strings and the column was never fixed |
| Sometimes-null fields | `ADJ_RSN_2` (secondary reason, only set when a second factor applies), `PRV_TIN` (null for providers onboarded before TIN capture began), `MBR_TERM_DT` (null while active) | Columns added mid-life of the system that don't apply to every row |

## Status code lookup values

Seeded in `db/schema.sql`. `CD_TYP` groups: `CLM_STS` (PD, DEN, PND), `MBR_STS`
(ACT, TRM), `NET_STS` (INN, OON), `ADJ_RSN` (DUP, BIL, DOC, COV), `DISP_TYP`
(DUP, BIL, DOC, COV), `DISP_STS` (OPN, RSLV, ESC).

## Decisions

- [[DEC-0003-project-record]]
