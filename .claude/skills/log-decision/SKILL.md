---
name: log-decision
description: Record an architecture or process decision as a new immutable DEC record in record/3-history. Use when a choice is made that a future session might otherwise re-litigate, or to supersede an earlier decision.
---

## Existing decisions
!`ls "${CLAUDE_PROJECT_DIR}/record/3-history" | grep '^DEC-'`

## Steps
1. Take the next number after the highest DEC above. Name the file
   `record/3-history/DEC-NNNN-short-kebab-title.md`.
2. Use exactly this shape:

```markdown
---
id: DEC-NNNN-short-kebab-title
date: YYYY-MM-DD
status: accepted
---
# DEC-NNNN · One-line decision

## Context
What forced the choice. Two to four sentences.

## Decision
What we will do. Specific enough that a future session can check compliance.

## Consequences
What gets easier, what gets harder, what it costs.
```

3. If this supersedes an earlier decision, write `Supersedes [[DEC-XXXX-...]]` in
   Context. Do not edit the old file; decision records are immutable and a hook
   blocks edits.
4. If the decision changes the architecture, update `record/1-truth/ARCH-system-overview.md`
   and link the new DEC from it.
5. Run `python3 tools/rec.py validate`.
