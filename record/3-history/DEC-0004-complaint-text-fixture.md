---
id: DEC-0004-complaint-text-fixture
date: 2026-11-01
status: accepted
---
# DEC-0004 · Complaint text lives in a committed fixture, not the legacy schema

## Context
T1.4 needed member complaint text per dispute. A real 2011-era claims backend
wouldn't store free-text member complaints on the claim/dispute record itself --
that's an intake-layer/portal concern sitting in front of the legacy system,
consistent with "nothing touches the legacy system except through the tool
runtime." Separately, `app.generate_data._build_scenarios` assigns dispute IDs
in a fixed order (same scenario-mix counts, same loop order) regardless of the
random seed, so the mapping from `disp_id` to scenario category/reason code
never changes across seeds.

## Decision
Complaint text is authored once -- by the LLM executing T1.4, as hand-written
template variants per `(category, reason_code)` pair, not a live API call per
dispute -- and committed to `fixtures/complaints/complaints.json`, keyed by
`disp_id` (1-200). `app.generate_data.generate_dataset()` attaches
`complaint_text` to each `Dispute` by reading this file through
`app.complaints.load_complaints()`. No DB column was added to `disp_hdr` for it.
Because one committed fixture covers every seed, dataset generation and tests
never call an LLM or network API. Future tools (T2.1's `get_dispute`, T3.x
specialists) should read complaint text via `app.complaints.load_complaints()`,
keyed by `disp_id` -- not expect it on any Postgres row.

## Consequences
- Dataset generation and the full test suite stay offline, free, and
  deterministic -- no API key dependency, no network flakiness in CI.
- Regenerating complaint text (e.g. after a scenario-mix change) requires
  rerunning `python -m app.complaints --write` by hand; it will not happen
  automatically if the mix changes without a matching fixture update.
- Any future tool that reads a dispute's complaint text must know to look in
  the fixture, not the legacy DB -- a boundary that isn't visible from the
  schema alone.
