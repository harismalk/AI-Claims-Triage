---
name: journal
description: Append an entry to the agent journal about where a coding agent helped or failed on this project and what changed because of it. Use at the end of a ticket when something notable happened, or when asked to log a lesson.
---

Append one row to the table in `record/3-history/agent-journal.md`. Never edit or
delete earlier rows.

`| YYYY-MM-DD | What happened, specifically | Helped / Failed | Check, skill, rule, or doc added because of it (or "none yet") |`

Good entries are concrete: "Claimed T2.1 criteria passed without running the
tests against the seeded DB; added a step to execute-ticket requiring the command
output." Vague entries ("agent was helpful") are not worth writing.

If the lesson should change future behavior, make that change now (a validator
check, a skill step, a CLAUDE.md rule) and name it in the last column. A lesson
that only lives in the journal hasn't compounded yet.
