"""Tests for tools/rec.py. Each test copies the whole repo into a temp project so
the real repo is never touched, then adds a synthetic spec (PS-test-fixtures.md,
tickets T99.1/T99.2) so these tests exercise generic rec.py behavior (set, guard,
validate, status transitions) without depending on the mutable state of any real
ticket in PS-mvp.md -- which changes as execute-ticket completes real work.
Run: python3 -m pytest tests/test_rec.py -q"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
REC = REPO / "tools" / "rec.py"

TEST_SPEC = """---
id: PS-test-fixtures
epic: EP-claims-dispute-agent
status: active
---
# PS-test-fixtures · Synthetic spec for testing rec.py

Exists only inside the temp copy made by tests/test_rec.py's `proj` fixture.
Gives the generic rec.py tests a ticket to exercise without depending on the
state of any real ticket in PS-mvp.md.

## CP99 · Test fixtures

### T99.1 · Synthetic ticket one

- [ ] Example criterion one
- [ ] Example criterion two

```ticket
id: T99.1
status: todo
evidence: []
```

### T99.2 · Synthetic ticket two, depends on T99.1

- [ ] Example criterion

Depends: T99.1

```ticket
id: T99.2
status: todo
evidence: []
```
"""


@pytest.fixture
def proj(tmp_path):
    shutil.copytree(REPO, tmp_path, dirs_exist_ok=True,
                     ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"))
    (tmp_path / "tests" / "test_dummy.py").write_text("def test_ok():\n    assert True\n")
    (tmp_path / "record" / "2-intent" / "PS-test-fixtures.md").write_text(TEST_SPEC)
    return tmp_path


def run(proj, *args, stdin=None):
    return subprocess.run([sys.executable, str(REC), *args], input=stdin, capture_output=True, text=True,
                          env={"CLAUDE_PROJECT_DIR": str(proj), "PATH": "/usr/bin:/bin"})


def spec_path(proj):
    return proj / "record" / "2-intent" / "PS-test-fixtures.md"


def test_clean_record_validates(proj):
    r = run(proj, "validate")
    assert r.returncode == 0, r.stdout


def test_done_without_evidence_is_refused(proj):
    r = run(proj, "set", "T99.1", "status", "done")
    assert r.returncode == 1
    assert "no evidence" in r.stderr
    assert "status: todo" in spec_path(proj).read_text()  # unchanged


def test_done_with_unchecked_criteria_is_refused(proj):
    assert run(proj, "set", "T99.1", "evidence+", "test:tests/test_dummy.py::test_ok").returncode == 0
    r = run(proj, "set", "T99.1", "status", "done")
    assert r.returncode == 1 and "unchecked" in r.stderr


def test_done_succeeds_with_evidence_and_checked_criteria(proj):
    text = spec_path(proj).read_text()
    section = text.split("### T99.1")[1].split("```ticket")[0]
    spec_path(proj).write_text(text.replace(section, section.replace("- [ ]", "- [x]")))
    run(proj, "set", "T99.1", "evidence+", "test:tests/test_dummy.py::test_ok")
    r = run(proj, "set", "T99.1", "status", "done")
    assert r.returncode == 0, r.stderr
    assert run(proj, "validate").returncode == 0


def test_set_only_rewrites_inside_the_fence(proj):
    before = spec_path(proj).read_text()
    run(proj, "set", "T99.1", "status", "in_progress")
    after = spec_path(proj).read_text()
    diff = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert diff == [("status: todo", "status: in_progress")]


def test_evidence_must_point_at_real_file(proj):
    r = run(proj, "set", "T99.1", "evidence+", "test:tests/nope.py::test_x")
    assert r.returncode == 1 and "does not exist" in r.stderr


def test_missing_acceptance_criteria_is_an_error(proj):
    text = spec_path(proj).read_text()
    spec_path(proj).write_text(text.replace("- [ ] Example criterion one\n", ""
                                            ).replace("- [ ] Example criterion two\n", ""))
    r = run(proj, "validate")
    assert r.returncode == 1 and "T99.1" in r.stdout and "no acceptance criteria" in r.stdout


def test_dangling_dependency_is_an_error(proj):
    spec_path(proj).write_text(spec_path(proj).read_text().replace("Depends: T99.1\n", "Depends: T999.9\n", 1))
    r = run(proj, "validate")
    assert r.returncode == 1 and "T999.9" in r.stdout


def test_bad_filename_suggests_fix(proj):
    (proj / "record" / "1-truth" / "arch_payments.md").write_text("---\nid: arch_payments\n---\n")
    r = run(proj, "validate")
    assert "rename to ARCH-payments.md" in r.stdout


def test_dangling_link_is_an_error(proj):
    p = proj / "record" / "1-truth" / "DOMAIN-claims-disputes.md"
    p.write_text(p.read_text() + "\nSee [[DEC-9999-nothing]].\n")
    assert "points at nothing" in run(proj, "validate").stdout


def guard(proj, tool, file_path, **tool_input):
    payload = {"tool_name": tool, "tool_input": {"file_path": str(file_path), **tool_input}, "cwd": str(proj)}
    r = run(proj, "guard", stdin=json.dumps(payload))
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "none"


def test_guard_blocks_editing_decisions(proj):
    dec = proj / "record" / "3-history" / "DEC-0001-propose-gate-execute.md"
    assert guard(proj, "Edit", dec, old_string="Context", new_string="Ctx") == "deny"


def test_guard_allows_new_decisions(proj):
    new = proj / "record" / "3-history" / "DEC-0004-something.md"
    assert guard(proj, "Write", new, content="x") == "none"


def test_guard_blocks_hand_edits_to_fences(proj):
    assert guard(proj, "Edit", spec_path(proj), old_string="id: T99.1\nstatus: todo",
                 new_string="id: T99.1\nstatus: done") == "deny"


def test_guard_allows_prose_and_checkbox_edits(proj):
    assert guard(proj, "Edit", spec_path(proj), old_string="- [ ] Example criterion one",
                 new_string="- [x] Example criterion one") == "none"


def test_guard_allows_adding_a_new_ticket(proj):
    text = spec_path(proj).read_text()
    added = text + "\n### T99.9 · Extra\n\n- [ ] something\n\n```ticket\nid: T99.9\nstatus: todo\nevidence: []\n```\n"
    assert guard(proj, "Write", spec_path(proj), content=added) == "none"


def test_guard_blocks_archive(proj):
    assert guard(proj, "Write", proj / "record" / ".archived" / "x.md", content="x") == "deny"


def test_stop_check_blocks_on_errors_once(proj):
    spec_path(proj).write_text(spec_path(proj).read_text().replace("Depends: T99.1\n", "Depends: T999.9\n", 1))
    r = run(proj, "stop-check", stdin=json.dumps({"stop_hook_active": False}))
    assert r.returncode == 2 and "T999.9" in r.stderr
    r = run(proj, "stop-check", stdin=json.dumps({"stop_hook_active": True}))
    assert r.returncode == 0  # no infinite loop


def test_stop_check_passes_clean(proj):
    assert run(proj, "stop-check", stdin="{}").returncode == 0
