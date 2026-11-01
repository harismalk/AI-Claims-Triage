---
id: PS-mvp
epic: EP-claims-dispute-agent
status: active
---
# PS-mvp · Claims-dispute agent MVP

Engineering plan for [[EP-claims-dispute-agent]]. Each `## CP` heading is a
**checkpoint**: a demoable slice. Each `### T` heading is a **ticket**: it belongs to
the checkpoint above it, its acceptance criteria are the checkboxes beneath it, and
its machine-owned state lives in the fenced `ticket` block.

Grammar rules (enforced by `python3 tools/rec.py validate`):

- People and agents edit the prose and checkboxes freely.
- Only `rec.py set` rewrites the inside of a `ticket` fence. Do not hand-edit fences.
- A ticket is `done` only when every checkbox is checked **and** it has evidence.
- `Depends:` lines reference other ticket IDs, which must exist.

Stack: Python 3.12, FastAPI, Postgres 16 (Docker), React + TypeScript (Vite), pytest.
The LLM provider sits behind one interface so models can be swapped.

---

## CP0 · Harness works

Demo: open a fresh Claude Code session; it starts oriented, and validation is clean.

### T0.1 · Verify the project harness end to end

Confirm the record, hooks, and skills behave as designed before building on them.

- [x] A fresh Claude Code session receives the orientation packet without prompting
- [x] `python3 tools/rec.py validate` passes
- [x] Editing a `DEC-*.md` file is blocked by the guard hook
- [x] The agent journal has a first entry describing the setup

```ticket
id: T0.1
status: done
evidence: [file:record/3-history/agent-journal.md, commit:guard-hook-block-observed-DEC-0001]
```

---

## CP1 · Legacy system and synthetic data

Demo: `make db && make seed` produces an ugly legacy claims database with planted
dispute scenarios and an answer key.

### T1.1 · Ugly legacy schema

Model a 15-year-old claims platform in Postgres on purpose: cryptic column names
(`CLM_STS_CD`, `ADJ_RSN_2`, `MBR_ID_NBR`), status codes that need a lookup table,
dates stored as `YYYYMMDD` strings, and a few sometimes-null fields.

- [x] `docker compose up -d` starts Postgres 16 with the schema applied
- [x] Tables cover members, plans, providers, claims, disputes, and a status-code lookup
- [x] At least three deliberate "legacy" quirks exist and are listed in the data dictionary

```ticket
id: T1.1
status: done
evidence: [file:docker-compose.yml, file:db/schema.sql, file:record/1-truth/DICT-legacy-schema.md]
```

### T1.2 · Plan definitions

Hand-write 3–4 insurance plans: copays by service type, deductibles, covered and
excluded services, network rules. Everything downstream depends on these.

- [x] Plans load from a versioned fixture file
- [x] Each plan defines copays, deductible, covered services, and network rules

Depends: T1.1

```ticket
id: T1.2
status: done
evidence: [test:tests/test_plans.py::test_loads_from_the_fixture_file, test:tests/test_plans.py::test_every_plan_defines_copays_deductible_coverage_and_network_rules, test:tests/test_plans.py::test_malformed_plan_missing_deductible_fails_validation]
```

### T1.3 · Scenario-first data generator with answer key

Generate ~200 members, ~50 providers, ~2,000 claims, ~200 disputes. Create each
dispute by *planting the situation first*, then recording the correct answer.
Fixed random seed so data is identical every run.

- [x] One command regenerates the full dataset deterministically from a seed
- [x] Scenario mix: ~35% should-reverse, ~25% denial-correct, ~20% edge, ~10% over-limit, ~10% adversarial
- [x] Every dispute has an answer-key row: decision, amount, evidence claim IDs
- [x] A test proves two runs with the same seed produce identical output

Depends: T1.2

```ticket
id: T1.3
status: done
evidence: [test:tests/test_generate_data.py::test_two_runs_same_seed_produce_identical_output, test:tests/test_generate_data.py::test_scenario_mix_matches_35_25_20_10_10_percent, test:tests/test_generate_data.py::test_every_dispute_has_an_answer_key_row, file:Makefile]
```

### T1.4 · Member complaint text, generated once and committed

An LLM writes each dispute's complaint text from the planted scenario. Run once,
cache to a committed file, never regenerate on test runs.

- [x] Complaint text is stored in a committed fixture and loaded by the seeder
- [x] Adversarial disputes include prompt-injection attempts in the complaint text
- [x] Test runs make no LLM calls to produce inputs

Depends: T1.3

```ticket
id: T1.4
status: done
evidence: [test:tests/test_complaints.py::test_complaints_load_from_the_committed_fixture, test:tests/test_complaints.py::test_adversarial_disputes_include_prompt_injection_attempts, test:tests/test_complaints.py::test_no_network_or_llm_api_calls_in_complaint_generation_code, file:fixtures/complaints/complaints.json]
```

### T1.5 · Legacy data dictionary

Reverse-engineer and document the legacy schema as if you had inherited it.

- [ ] `record/1-truth/DICT-legacy-schema.md` maps every cryptic column to its meaning
- [ ] Status-code lookup values are documented
- [ ] The doc's `covers:` frontmatter lists the schema files it describes

Depends: T1.1

```ticket
id: T1.5
status: todo
evidence: []
```

---

## CP2 · Tools and legacy adapter

Demo: call each tool from a REPL against the seeded database and get clean,
typed results; run the same call in replay mode and get the recorded result.

### T2.1 · Read tools

`lookup_claim`, `find_similar_claims`, `get_plan_terms`, `get_payment_history`,
`get_dispute`. Each wraps the ugly legacy data and returns clean typed objects.

- [ ] Each tool has a typed return model and a docstring written for an LLM reader
- [ ] Each tool has tests against the seeded database
- [ ] No tool returns a raw legacy column name

Depends: T1.3

```ticket
id: T2.1
status: todo
evidence: []
```

### T2.2 · Write path through a clunky legacy API

`update_claim_status` and `issue_adjustment` go through a deliberately awkward
legacy-style API (form-encoded or XML), not direct SQL.

- [ ] Writes are only possible through the legacy API wrapper
- [ ] Every write tool is declared `side_effect=True`
- [ ] Writes are idempotent on a request key (a retried write does not double-apply)

Depends: T2.1

```ticket
id: T2.2
status: todo
evidence: []
```

### T2.3 · Tool runtime: live, replay, and write interception

One runtime under every tool call. Modes: `live`, `replay`. Replay returns recorded
outputs, falls through to a snapshot DB, and raises on strict misses. Writes in
non-live modes go to an effect log plus a copy-on-write overlay so later reads stay
consistent. Undeclared tools are blocked outside live mode (fail closed).

- [ ] The agent code is identical in live and replay modes
- [ ] A replayed trace reproduces the original tool outputs exactly
- [ ] An intercepted write appears in the effect log and in subsequent reads
- [ ] A tool without a `side_effect` declaration is blocked in replay mode

Depends: T2.2

```ticket
id: T2.3
status: todo
evidence: []
```

---

## CP3 · Agent: router, specialists, gate

Demo: submit a duplicate-denial dispute and watch it auto-resolve with linked
evidence; submit a $2,000 one and watch it land in the adjuster queue.

### T3.1 · Deterministic router

Route by reason code and rules. An LLM classifier is a fallback only when the
reason code is missing or contradicts the complaint, and its use is logged.

- [ ] Routing uses no LLM call when the reason code is present and consistent
- [ ] Fallback classifications are logged with the reason the rules did not decide
- [ ] Routing accuracy is reported by the eval suite

Depends: T2.1

```ticket
id: T3.1
status: todo
evidence: []
```

### T3.2 · Duplicate-denial specialist

- [ ] Uses only its own prompt, tools, and knowledge file
- [ ] Produces a structured proposal: decision, amount, evidence claim IDs, rationale
- [ ] Handles the same-date-different-procedure edge case correctly on the golden set

Depends: T3.1, T2.3

```ticket
id: T3.2
status: todo
evidence: []
```

### T3.3 · Billing-error specialist

- [ ] Compares charged copay against plan terms and cites the plan rule used
- [ ] Produces the same structured proposal shape as T3.2

Depends: T3.1, T2.3

```ticket
id: T3.3
status: todo
evidence: []
```

### T3.4 · Decision gate (code, not LLM)

The LLM proposes; code verifies. Auto-resolve only when the amount is under the
limit, the dispute type is auto-eligible, every cited record exists and supports
the claim, and no risk flag is set. Everything else escalates with reasons.

- [ ] The gate re-checks cited evidence against the database before acting
- [ ] Coverage disputes and amounts over the limit always escalate
- [ ] Every gate decision records which rule allowed or blocked it

Depends: T3.2

```ticket
id: T3.4
status: todo
evidence: []
```

### T3.5 · Resolution letter drafting

- [ ] Letters state the decision, amount, and reason in plain language
- [ ] Letters never contain internal codes or claim-system jargon

Depends: T3.4

```ticket
id: T3.5
status: todo
evidence: []
```

---

## CP4 · Evals and the CI gate

Demo: change a specialist prompt, open a PR, and watch CI block it for a regression.

### T4.1 · Golden dataset from the answer key

- [ ] Golden cases load from the T1.3 answer key with scenario-type metadata
- [ ] Each case bundles input, recorded tool outputs, and a DB snapshot reference

Depends: T1.4, T2.3

```ticket
id: T4.1
status: todo
evidence: []
```

### T4.2 · Code scorers

- [ ] Scorers for routing accuracy, decision correctness, amount correctness, and evidence validity
- [ ] Results reported per dispute type and per scenario type

Depends: T4.1

```ticket
id: T4.2
status: todo
evidence: []
```

### T4.3 · Safety invariants

- [ ] Never auto-resolve over the limit; never auto-resolve a coverage dispute
- [ ] Each write tool called at most once per dispute
- [ ] No tool outside the specialist's allowed set is ever called
- [ ] Any violation fails the suite regardless of other scores

Depends: T4.1, T3.4

```ticket
id: T4.3
status: todo
evidence: []
```

### T4.4 · Letter-quality judge, calibrated

- [ ] An LLM judge scores letters against a written rubric
- [ ] Judge agreement with ~30 hand-graded letters is measured and reported

Depends: T3.5

```ticket
id: T4.4
status: todo
evidence: []
```

### T4.5 · CI regression gate

- [ ] GitHub Actions runs validate, unit tests, and the eval suite on every PR
- [ ] A PR that lowers any tracked score below baseline, or breaks an invariant, fails
- [ ] Each case runs multiple times and reports a pass rate, not a single pass/fail

Depends: T4.2, T4.3

```ticket
id: T4.5
status: todo
evidence: []
```

---

## CP5 · Adjuster queue and the correction loop

Demo: override an agent recommendation in the UI and see a new eval case appear.

### T5.1 · API

- [ ] FastAPI endpoints for listing disputes, viewing a case, and accepting or overriding
- [ ] Request bodies validated; every endpoint has a test

Depends: T3.4

```ticket
id: T5.1
status: todo
evidence: []
```

### T5.2 · Adjuster queue screen

- [ ] One React screen: queue, case summary, recommendation, evidence links, accept/override
- [ ] Every evidence item opens the underlying record

Depends: T5.1

```ticket
id: T5.2
status: todo
evidence: []
```

### T5.3 · Overrides become eval cases

- [ ] An override stores what the agent proposed, what the adjuster chose, and why
- [ ] Overrides are grouped into failure patterns
- [ ] One command promotes a reviewed override into a golden case with its snapshot

Depends: T5.1, T4.1

```ticket
id: T5.3
status: todo
evidence: []
```

---

## CP6 · Ship and tell the story

Demo: a deployed URL, the CEO memo, and a five-minute walkthrough.

### T6.1 · Containerize and deploy

- [ ] Dockerfile and compose file run the full stack locally with one command
- [ ] Deployed to a public host with secrets in the host's environment, not the repo

Depends: T5.2

```ticket
id: T6.1
status: todo
evidence: []
```

### T6.2 · CEO memo

- [ ] One page: problem, cost per dispute, auto-resolve rate, risk controls, next step
- [ ] Every number in it comes from the eval report

Depends: T4.5

```ticket
id: T6.2
status: todo
evidence: []
```

### T6.3 · Engineer design doc

- [ ] Architecture, the three load-bearing decisions, tradeoffs, and what week 6 would add
- [ ] Links to the decision log entries it summarizes

Depends: T4.5

```ticket
id: T6.3
status: todo
evidence: []
```

### T6.4 · Demo script and agent-journal retrospective

- [ ] A five-minute demo script tested end to end on the deployed app
- [ ] A short retrospective from the agent journal: where coding agents helped and where they failed

Depends: T6.1, T6.2

```ticket
id: T6.4
status: todo
evidence: []
```
