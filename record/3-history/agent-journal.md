# Agent journal

Append-only notes on working with coding agents on this project: where they
helped, where they failed, and what check or skill was added in response.
Newest at the bottom. This feeds the T6.4 retrospective.

| Date | What happened | Helped / failed | What changed because of it |
|---|---|---|---|
| 2026-11-01 | T0.1: verified the harness end to end before any feature work. SessionStart hook delivered the orientation packet unprompted; `rec.py validate` returned 0 errors/warnings; attempted an `Edit` on `DEC-0001-propose-gate-execute.md` and the PreToolUse guard hook correctly refused it with a message pointing to writing a superseding DEC instead of hand-editing. | Helped | None yet — harness behaved exactly as designed, no gaps found. |
| 2026-11-01 | T1.2 side-fix: `tests/test_rec.py`'s `proj` fixture only copied `record/` into the temp project and hardcoded that T1.1 stays `status: todo` with empty evidence forever. Once T1.1 was legitimately completed (`file:` evidence pointing outside `record/`, e.g. `docker-compose.yml`, `db/schema.sql`), 7 of 16 tests broke — not because the record was wrong, but because the fixture didn't mirror real repo state and was coupled to a ticket id that was always going to change. This was invisible before because `pytest` wasn't installed in the dev environment at all (`ModuleNotFoundError`), so the breakage went unnoticed until `pytest` was set up for T1.2. | Failed (latent, until surfaced) | Set up `.venv` + `requirements.txt` (pytest, pydantic) so `python3 -m pytest -q` actually runs. Rewrote the `proj` fixture to copy the whole repo (minus `.git`/`.venv`/caches) and added a synthetic spec (`record/2-intent/PS-test-fixtures.md`, tickets `T99.1`/`T99.2`) inside that temp copy, so generic rec.py behavior tests never reference a real, evolving ticket id again. |
