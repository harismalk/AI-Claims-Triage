---
name: write-spec
description: Add or restructure checkpoints and tickets in a project spec using the record grammar. Use when planning new work, splitting a ticket, or capturing work discovered mid-ticket.
---

## Grammar (enforced by `python3 tools/rec.py validate`)

```markdown
## CPn · Checkpoint title

Demo: what someone can see working when every ticket here is done.

### Tn.m · Ticket title

Why this ticket exists and any constraints. Prose is free.

- [ ] Observable, checkable criterion
- [ ] Another one

Depends: Tn.k, Tp.q

` ` `ticket
id: Tn.m
status: todo
evidence: []
` ` `
```
(Remove the spaces in the fence markers.)

## Rules
- Every ticket sits under exactly one checkpoint. A checkpoint is a demoable slice,
  not a phase. If a ticket truly fits none, add `exempt: true` to its fence and say why in prose.
- Acceptance criteria must be **checkable by running something**. "Works well" is
  not a criterion; "routing uses no LLM call when the reason code is present" is.
- Prefer 2–4 criteria. More than 5 usually means the ticket should split.
- New tickets get the next free number in their checkpoint. Never reuse or renumber
  an ID that has evidence attached.
- Only add new fences by hand. Existing fences change only through `rec.py set`.
- After editing, run `python3 tools/rec.py validate` and `python3 tools/rec.py status`.
