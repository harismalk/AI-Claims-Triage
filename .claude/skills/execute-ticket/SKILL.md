---
name: execute-ticket
description: Execute one ticket from the project spec against its acceptance criteria, from start to proven done. Use whenever starting, continuing, or finishing work on a ticket ID like T1.3.
argument-hint: "[ticket-id]"
---

Execute ticket $ARGUMENTS.

## 1. Orient
- Run `python3 tools/rec.py ticket $ARGUMENTS`. Read the prose, acceptance criteria, and dependency state.
- If any dependency is not done, stop and report it. Do not start blocked work.
- Read the truth docs and decisions the ticket touches (follow `[[links]]`).
- Run `python3 tools/rec.py set $ARGUMENTS status in_progress`.

## 2. Plan briefly
State in 3–6 lines: what you will build, which files change, and **how each
acceptance criterion will be demonstrated** (which test or command proves it).
If a criterion can't be demonstrated as written, say so and propose a sharper
wording before writing code. Edit the criterion text in the spec only with the
user's agreement.

## 3. Build
- Write the test for a criterion before or alongside the code that satisfies it.
- Keep changes inside the ticket's scope. New work you discover goes into the spec
  as a new ticket (use `write-spec`), not into this one.
- If you make a choice a future session would re-litigate, use `log-decision`.

## 4. Prove each criterion
For each acceptance criterion, run the command that demonstrates it and read the
output. Check the box only after it passes. Attach evidence:

`python3 tools/rec.py set $ARGUMENTS evidence+ test:tests/<file>.py::<test>`

Evidence kinds: `test:`, `file:`, `commit:`, `pr:`, `eval:`.

## 5. Close
- Run `python3 tools/rec.py set $ARGUMENTS status done`. If it refuses, fix what it names. Never weaken a criterion to get past it.
- If a truth doc no longer matches the code, update it and its `covers:` list.
- Run `python3 tools/rec.py validate`.
- Use the `journal` skill if a coding agent notably helped or failed during the ticket.
- Report: what changed, the evidence for each criterion, and what `rec.py next` says is ready.
