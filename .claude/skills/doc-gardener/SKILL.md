---
name: doc-gardener
description: Check that truth docs in record/1-truth still match the code they describe, and fix drift. Use when the validator warns a covered path changed, after a checkpoint lands, or when asked whether docs are current.
---

## Validator warnings
!`python3 "${CLAUDE_PROJECT_DIR}/tools/rec.py" validate 2>&1 | grep -A1 WARN || echo "No staleness warnings."`

## Steps
For each doc in `record/1-truth/` (prioritize ones with warnings above):

1. Read the doc and every path in its `covers:` frontmatter.
2. List each claim in the doc that the code contradicts or no longer supports.
   Quote the doc line and cite the file and line in the code.
3. Fix the doc to match the code. If the *code* is what's wrong (it violates a
   documented decision), do not change the doc; report it as a bug instead.
4. Update `covers:` if paths moved. Set `status: current` once it matches.
5. Run `python3 tools/rec.py validate`.

Report a short table: doc, drift found, action taken.
