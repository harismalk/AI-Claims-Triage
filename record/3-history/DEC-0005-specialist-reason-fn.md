---
id: DEC-0005-specialist-reason-fn
date: 2026-11-01
status: accepted
---
# DEC-0005 · A specialist's LLM step is a pluggable reason_fn, not a live call

## Context
No LLM provider interface is wired into the codebase yet -- the spec header's
"LLM provider sits behind one interface so models can be swapped" is still
future work. Tests and CI need to run offline and deterministically, with no
API cost or network flakiness, consistent with how T1.4 avoided live LLM calls
for complaint-text generation and T3.1's router used a pluggable `classify_fn`
for its fallback path.

## Decision
Each specialist's `propose(dispute_id, runtime, reason_fn=default_reason_fn)`
takes its LLM-reasoning step as a pluggable `reason_fn` parameter, defaulting
to a deterministic implementation of that specialist's `knowledge.md` rule.
`app/specialists/duplicate_denial/specialist.py`'s default `reason_fn` encodes:
match on procedure code, not date, to correctly handle the same-date-
different-procedure edge case. Every specialist follows the same shape: its
own `prompt.md`, `knowledge.md`, and `specialist.py` in
`app/specialists/<name>/`, an `ALLOWED_TOOLS` set restricting it to only the
tools it needs, and `propose(dispute_id, runtime, reason_fn=default_reason_fn)`.
When a real LLM provider interface exists, `reason_fn` can be swapped to a
live call without changing any caller.

## Consequences
- Tests and evals (CP4) run deterministically and offline against the T1.3/
  T1.4 golden data, with no API key dependency.
- The deterministic default is itself the thing standing in for "the LLM
  followed the knowledge file correctly" -- it does not exercise an actual
  model's judgment, only the rule a human/model should land on. A regression
  in real LLM judgment, as opposed to a regression in this default, would not
  be caught until a real `reason_fn` is wired in and evaluated.
- Adding a specialist means adding a `prompt.md`/`knowledge.md`/`specialist.py`
  triad following this shape, not inventing a new calling convention.
