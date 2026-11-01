# claims-agent

A tier-1 health-insurance claims-dispute agent built against a deliberately ugly
fictional legacy system, developed with Claude Code using a small-scale version of
the AI-native SDLC principles Tenex describes in "Building an AI-Native SDLC."
All data is synthetic.

## How the repo is run

| Principle | How it's implemented here |
|---|---|
| Context is code | `record/` holds truth, intent, and history as validated markdown next to the code |
| Detailed plans that can change | `record/2-intent/PS-mvp.md`: checkpoints → tickets → checkable acceptance criteria |
| Every session starts senior | A SessionStart hook runs `rec.py orient` and injects plan state, ready work, decisions, and validation status |
| Skills ship like software | `.claude/skills/`: execute-ticket, write-spec, log-decision, verify, doc-gardener, promote-failure, journal |
| One record, a machine interface | `tools/rec.py`: validate, status, next, ticket, set |
| Agents check their own work | Validator errors carry fixes; a Stop hook makes the agent repair drift; `set ... done` is refused without evidence |
| Status is derived | `rec.py status` computes checkpoint health; nobody types it |
| Lessons compound | The agent journal, plus the rule that each lesson becomes a check, skill step, or rule |

Hard boundaries, enforced by a PreToolUse hook: ticket fences change only through
`rec.py set`, decision records are immutable, and `record/.archived/` is read-only.

## Quick start

```bash
python3 tools/rec.py status     # derived project health
python3 tools/rec.py next       # what's ready
python3 -m pytest -q            # includes tests for the record tooling
claude                          # Claude Code starts oriented via the hook
```

Then in Claude Code: `/execute-ticket T0.1`.

## Known limits

- This level of process is overkill for one person on one project. It's used here deliberately to practice it.
