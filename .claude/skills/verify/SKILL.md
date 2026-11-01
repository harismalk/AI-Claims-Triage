---
name: verify
description: Verify the project before a commit - record validation, unit tests, and evals when they exist. Runs automatically before each commit; also use when asked to check that everything passes.
---

Run these in order and report each result. Stop at the first failure and fix it,
or report what is blocking.

1. `python3 tools/rec.py validate`
2. `python3 -m pytest -q`
3. If `evals/` exists: run the eval suite (see `record/1-truth/` for the current
   command once CP4 lands) and compare against the baseline. Any safety-invariant
   violation is a failure regardless of other scores.

Do not commit with a failing step. Do not skip, xfail, or loosen a check to make it
pass. If a check is genuinely wrong, say so and propose a decision record.
