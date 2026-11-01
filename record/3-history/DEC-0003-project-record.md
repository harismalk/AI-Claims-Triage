---
id: DEC-0003-project-record
date: 2026-11-01
status: accepted
---
# DEC-0003 · Project context lives in a validated record next to the code

## Context
Coding agents start every session with no memory. Plans and decisions that live
only in someone's head, or in chat, are invisible to them. Adapted from the
principles in Tenex's "Building an AI-Native SDLC" (MetaHarness), scaled down to
one engineer and one project.

## Decision
- `record/1-truth/` holds what is true now; `2-intent/` what we plan; `3-history/`
  what happened; `scratchpad/` is ungoverned; `.archived/` is read-only.
- Specs use a strict grammar: checkpoints → tickets → acceptance criteria, with
  machine state inside fenced `ticket` blocks that only `tools/rec.py set` rewrites.
- `tools/rec.py validate` enforces the grammar with fix suggestions; a Stop hook runs
  it so the agent repairs drift before ending a turn.
- A SessionStart hook injects an orientation packet so every session starts
  with the plan, ready tickets, recent decisions, and validation state.
- Decision records are immutable; a guard hook blocks edits. Supersede with a new DEC.

## Consequences
- Every session starts oriented; status is computed, not reported.
- Cost: discipline to write things down. Tenex notes this is overkill for tiny
  projects; here it is also the point of the exercise.
