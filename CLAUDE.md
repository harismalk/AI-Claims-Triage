# CLAUDE.md

This file is a map, not a manual. Details live in `record/` and in skills.

## What this is

A tier-1 health-insurance claims-dispute agent built against a deliberately ugly
fictional legacy system. All data is synthetic. Plan: `record/2-intent/PS-mvp.md`.
Why: `record/2-intent/EP-claims-dispute-agent.md`.

## Where things live

| Path | Holds | Rules |
|---|---|---|
| `record/1-truth/` | What is true now (architecture, domain, data dictionary) | Update when code diverges. `covers:` lists the code a doc describes |
| `record/2-intent/` | Epics (product) and specs (engineering plan) | Checkpoints → tickets → acceptance criteria |
| `record/3-history/` | Decisions (`DEC-NNNN-*.md`) and the agent journal | DEC files are immutable; supersede with a new one |
| `record/scratchpad/` | Anything messy | Ungoverned, never treated as truth |
| `record/.archived/` | Superseded material | Read-only |
| `tools/rec.py` | The machine interface to the record | Run `python3 tools/rec.py --help` |

## Commands

| Need | Command |
|---|---|
| What's ready | `python3 tools/rec.py next` |
| Project health | `python3 tools/rec.py status` |
| One ticket with its criteria | `python3 tools/rec.py ticket T1.2` |
| Change ticket state | `python3 tools/rec.py set T1.2 status in_progress` |
| Attach evidence | `python3 tools/rec.py set T1.2 evidence+ test:tests/test_x.py::test_y` |
| Check the record | `python3 tools/rec.py validate` |
| Tests | `python3 -m pytest -q` |

## Rules

- **Ticket fences are machine-owned.** Edit prose and checkboxes freely; change status
  and evidence only through `rec.py set`. A hook blocks hand edits to fences.
- **Done means proven.** A ticket is done only when every acceptance criterion is
  checked and evidence is attached. `rec.py set` refuses anything less. Check a box
  only after you have run something that demonstrates it.
- **Decisions get written down.** Any choice a future session would otherwise
  re-litigate goes in a new DEC record (use the log-decision skill).
- **The LLM proposes, code verifies** ([[DEC-0001-propose-gate-execute]]). Never let a
  model call decide its own authority or call a write tool directly.
- **Nothing touches the legacy system except through the tool runtime.**
- **No real data.** Synthetic only. No real names, PHI, or credentials in the repo.
- If a check fails and you can't fix it, stop and say what is blocking, with the
  validator output. Do not weaken a check to make it pass.

## Skills

`execute-ticket` (start here for any ticket), `write-spec`, `log-decision`,
`verify` (runs before every commit), `doc-gardener`, `promote-failure`, `journal`.

## Stack

Python 3.12, FastAPI, Postgres 16 in Docker, React + TypeScript (Vite), pytest.
