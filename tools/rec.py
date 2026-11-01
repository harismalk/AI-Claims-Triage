#!/usr/bin/env python3
"""rec.py: the machine interface to the project record.

Stdlib only. Agents and humans ask it what is true, what is ready, and what is
broken, and it is the only thing allowed to rewrite ticket fences.

Commands
  validate           Check the record; exit 1 on errors. Every error carries a fix.
  orient             Print the session-start packet (used by the SessionStart hook).
  status             Derived health per checkpoint. Nothing here is typed by hand.
  next               Tickets that are ready: todo, with every dependency done.
  ticket ID          Print one ticket's section and its dependency state.
  set ID KEY VALUE   Rewrite one field inside a ticket fence (the fence rule).
                     KEY: status | blocked_reason | evidence+ (append evidence)
  guard              PreToolUse hook: block edits that break record invariants.
  stop-check         Stop hook: run validate; exit 2 so the agent repairs errors.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent)
RECORD = ROOT / "record"

STATUSES = {"todo", "in_progress", "blocked", "done", "dropped"}
FENCE_KEYS = {"id", "status", "evidence", "exempt", "blocked_reason"}
EVIDENCE_KINDS = {"pr", "commit", "test", "file", "eval"}

NAME_RULES = {
    "1-truth": (r"^(ARCH|DOMAIN|DICT|GUIDE|RUNBOOK)-[a-z0-9]+(-[a-z0-9]+)*\.md$",
                "ARCH|DOMAIN|DICT|GUIDE|RUNBOOK"),
    "2-intent": (r"^(EP|PS)-[a-z0-9]+(-[a-z0-9]+)*\.md$", "EP|PS"),
    "3-history": (r"^DEC-\d{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$", "DEC-NNNN"),
}
UNGOVERNED_NAMES = {"README.md", "agent-journal.md"}

CP_RE = re.compile(r"^## (CP\d+) · (.+?)\s*$")
TICKET_RE = re.compile(r"^### (T\d+\.\d+) · (.+?)\s*$")
H2_RE = re.compile(r"^## ")
H3_RE = re.compile(r"^### ")
AC_RE = re.compile(r"^- \[( |x|X)\] (.+)$")
DEPENDS_RE = re.compile(r"^Depends:\s*(.+)$")
LINK_RE = re.compile(r"\[\[([A-Za-z0-9\-]+)\]\]")


# ---------------------------------------------------------------- parsing

def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    out = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = parse_value(v.strip())
    return out


def parse_value(v: str):
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
    return v.strip("'\"")


def render_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(v) + "]"
    return str(v)


@dataclass
class AC:
    checked: bool
    text: str
    line: int


@dataclass
class Ticket:
    id: str
    title: str
    file: Path
    line: int                     # 1-based heading line
    checkpoint: str | None
    acs: list = field(default_factory=list)
    depends: list = field(default_factory=list)
    fence: dict | None = None
    fence_span: tuple | None = None   # (open_idx, close_idx), 0-based line indexes
    section_end: int = 0              # 0-based exclusive

    @property
    def status(self) -> str:
        return (self.fence or {}).get("status", "?")

    @property
    def evidence(self) -> list:
        ev = (self.fence or {}).get("evidence", [])
        return ev if isinstance(ev, list) else [ev]


@dataclass
class Spec:
    file: Path
    meta: dict
    checkpoints: dict          # id -> title
    tickets: list


def parse_spec(path: Path) -> Spec:
    lines = path.read_text().splitlines()
    meta = parse_frontmatter(path.read_text())
    checkpoints: dict = {}
    tickets: list = []
    cur_cp = None
    cur: Ticket | None = None
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```ticket"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            if cur is not None:
                fence = {}
                for fl in lines[i + 1:j]:
                    if ":" in fl:
                        k, v = fl.split(":", 1)
                        fence[k.strip()] = parse_value(v.strip())
                cur.fence = fence
                cur.fence_span = (i, j)
            i = j + 1
            continue
        if line.startswith("```"):
            in_code = not in_code
            i += 1
            continue
        if in_code:
            i += 1
            continue
        if H2_RE.match(line):
            if cur:
                cur.section_end = i
                cur = None
            m = CP_RE.match(line)
            cur_cp = m.group(1) if m else None
            if m:
                checkpoints[m.group(1)] = m.group(2)
        elif H3_RE.match(line):
            if cur:
                cur.section_end = i
                cur = None
            m = TICKET_RE.match(line)
            if m:
                cur = Ticket(m.group(1), m.group(2), path, i + 1, cur_cp)
                tickets.append(cur)
        elif cur is not None:
            m = AC_RE.match(line)
            if m:
                cur.acs.append(AC(m.group(1).lower() == "x", m.group(2), i + 1))
            m = DEPENDS_RE.match(line)
            if m:
                cur.depends = [d.strip() for d in m.group(1).split(",") if d.strip()]
        i += 1
    if cur:
        cur.section_end = len(lines)
    return Spec(path, meta, checkpoints, tickets)


def load_specs() -> list:
    return [parse_spec(p) for p in sorted((RECORD / "2-intent").glob("PS-*.md"))]


def all_tickets(specs) -> dict:
    out = {}
    for s in specs:
        for t in s.tickets:
            out.setdefault(t.id, t)
    return out


def record_ids() -> dict:
    ids = {}
    for folder in ("1-truth", "2-intent", "3-history"):
        for p in (RECORD / folder).glob("*.md"):
            ids[p.stem] = p
    return ids


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- validation

@dataclass
class Finding:
    level: str      # error | warn
    where: str
    msg: str
    fix: str

    def __str__(self):
        return f"[{self.level.upper()}] {self.where}: {self.msg}\n        fix: {self.fix}"


def suggest_name(name: str, folder: str) -> str:
    stem = name[:-3] if name.endswith(".md") else name
    parts = re.split(r"[-_ ]+", stem, maxsplit=1)
    prefix = parts[0].upper()
    rest = re.sub(r"[^a-z0-9]+", "-", parts[1].lower()).strip("-") if len(parts) > 1 else "name"
    if folder == "3-history" and prefix == "DEC" and not re.match(r"^\d{4}-", rest):
        rest = "NNNN-" + rest
    return f"{prefix}-{rest}.md"


def git_time(path: Path) -> int | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except Exception:
        return None


def ticket_findings(t: Ticket, tickets: dict) -> list:
    F = []
    where = f"{rel(t.file)}:{t.line} {t.id}"
    if t.fence is None:
        return [Finding("error", where, "ticket has no ```ticket block",
                        f"add a fenced block under the ticket:\n          ```ticket\n          id: {t.id}\n          status: todo\n          evidence: []\n          ```")]
    for k in t.fence:
        if k not in FENCE_KEYS:
            F.append(Finding("error", where, f"unknown fence key '{k}'",
                             f"remove it; allowed keys: {', '.join(sorted(FENCE_KEYS))}"))
    if t.fence.get("id") != t.id:
        F.append(Finding("error", where, f"fence id '{t.fence.get('id')}' does not match heading '{t.id}'",
                         f"set the fence id to {t.id}"))
    exempt = str(t.fence.get("exempt", "")).lower() == "true"
    if t.checkpoint is None and not exempt:
        F.append(Finding("error", where, "ticket is not under a checkpoint",
                         "move it under a '## CPn · Title' heading, or add 'exempt: true' to its fence with a reason in the prose"))
    if not t.acs:
        F.append(Finding("error", where, "ticket has no acceptance criteria",
                         "add at least one '- [ ] observable, checkable criterion' line under the ticket"))
    st = t.status
    if st not in STATUSES:
        F.append(Finding("error", where, f"invalid status '{st}'",
                         f"use one of: {', '.join(sorted(STATUSES))} via `python3 tools/rec.py set {t.id} status <value>`"))
    for d in t.depends:
        if d not in tickets:
            F.append(Finding("error", where, f"depends on '{d}', which does not exist",
                             f"fix the Depends line or create ticket {d}"))
    if st == "blocked" and not t.fence.get("blocked_reason"):
        F.append(Finding("error", where, "blocked without a reason",
                         f'`python3 tools/rec.py set {t.id} blocked_reason "<why>"`'))
    for ev in t.evidence:
        kind, _, val = ev.partition(":")
        if kind not in EVIDENCE_KINDS or not val:
            F.append(Finding("error", where, f"bad evidence '{ev}'",
                             f"use kind:value with kind in {', '.join(sorted(EVIDENCE_KINDS))}, e.g. test:tests/test_x.py::test_y"))
        elif kind in ("test", "file"):
            path = val.split("::")[0]
            if not (ROOT / path).exists():
                F.append(Finding("error", where, f"evidence path '{path}' does not exist",
                                 "point evidence at a real file, or remove it"))
    if st == "done":
        unchecked = [a for a in t.acs if not a.checked]
        if unchecked:
            F.append(Finding("error", where, f"marked done with {len(unchecked)} unchecked criteria (first: line {unchecked[0].line})",
                             "verify and check each criterion, or set status back to in_progress"))
        if not t.evidence:
            F.append(Finding("error", where, "marked done with no evidence",
                             f"`python3 tools/rec.py set {t.id} evidence+ test:<path>::<test>` (or pr:, commit:, file:, eval:)"))
        for d in t.depends:
            if d in tickets and tickets[d].status not in ("done", "dropped"):
                F.append(Finding("error", where, f"done while dependency {d} is {tickets[d].status}",
                                 f"finish {d} first, or remove the dependency with a decision record explaining why"))
    if st == "in_progress":
        for d in t.depends:
            if d in tickets and tickets[d].status not in ("done", "dropped"):
                F.append(Finding("warn", where, f"in progress while dependency {d} is {tickets[d].status}",
                                 f"confirm this is intentional, or set {t.id} back to todo"))
    return F


def validate() -> list:
    F: list = []
    if not RECORD.exists():
        return [Finding("error", "record/", "record directory missing", "restore record/ from git")]

    # File naming
    for folder, (pattern, prefixes) in NAME_RULES.items():
        for p in sorted((RECORD / folder).glob("*")):
            if p.name in UNGOVERNED_NAMES or p.is_dir():
                continue
            if not re.match(pattern, p.name):
                F.append(Finding("error", rel(p), f"filename does not match {prefixes}-kebab-case.md",
                                 f"rename to {suggest_name(p.name, folder)}"))

    ids = record_ids()

    # Frontmatter and links
    for stem, p in ids.items():
        if p.name in UNGOVERNED_NAMES:
            continue
        text = p.read_text()
        meta = parse_frontmatter(text)
        if not meta:
            F.append(Finding("error", rel(p), "missing frontmatter",
                             f"start the file with:\n          ---\n          id: {stem}\n          status: <status>\n          ---"))
            continue
        if meta.get("id") != stem:
            F.append(Finding("error", rel(p), f"frontmatter id '{meta.get('id')}' does not match filename",
                             f"set id: {stem}"))
        if stem.startswith("DEC-") and not meta.get("date"):
            F.append(Finding("error", rel(p), "decision record has no date", "add date: YYYY-MM-DD"))
        if stem.startswith("PS-"):
            ep = meta.get("epic")
            if not ep or ep not in ids:
                F.append(Finding("error", rel(p), f"spec epic '{ep}' not found",
                                 "set epic: to an existing EP-* id"))
        for link in LINK_RE.findall(text):
            if link not in ids:
                F.append(Finding("error", rel(p), f"link [[{link}]] points at nothing",
                                 "fix the link, or create the record it names"))
        covers = meta.get("covers", [])
        if isinstance(covers, str):
            covers = [covers] if covers else []
        doc_t = git_time(p)
        for c in covers:
            target = ROOT / c
            if not target.exists():
                F.append(Finding("error", rel(p), f"covers '{c}', which does not exist",
                                 "update covers: to the current path, or archive the doc"))
            elif doc_t is not None:
                code_t = git_time(target)
                if code_t and code_t > doc_t:
                    F.append(Finding("warn", rel(p), f"'{c}' changed after this doc was last updated",
                                     "run the doc-gardener skill to check the doc still matches the code"))

    # Specs and tickets
    specs = load_specs()
    seen: dict = {}
    for s in specs:
        if s.tickets and not s.checkpoints:
            F.append(Finding("error", rel(s.file), "spec has tickets but no checkpoints",
                             "group tickets under '## CPn · Title' headings, each a demoable slice"))
        for t in s.tickets:
            if t.id in seen:
                F.append(Finding("error", f"{rel(t.file)}:{t.line}", f"duplicate ticket id {t.id}",
                                 f"also defined at {rel(seen[t.id].file)}:{seen[t.id].line}; renumber one"))
            seen.setdefault(t.id, t)
    tickets = all_tickets(specs)
    for t in tickets.values():
        F.extend(ticket_findings(t, tickets))
    return F


# ---------------------------------------------------------------- derived views

def ready(tickets: dict) -> list:
    return [t for t in tickets.values()
            if t.status == "todo" and all(tickets.get(d) and tickets[d].status in ("done", "dropped") for d in t.depends)]


def checkpoint_rows(specs, tickets, findings):
    bad_ids = {f.where.split()[-1] for f in findings if f.level == "error"}
    rows = []
    for s in specs:
        for cp, title in s.checkpoints.items():
            ts = [t for t in s.tickets if t.checkpoint == cp]
            done = sum(t.status in ("done", "dropped") for t in ts)
            prog = sum(t.status == "in_progress" for t in ts)
            blocked = sum(t.status == "blocked" for t in ts)
            rdy = sum(t in ready(tickets) for t in ts)
            if ts and done == len(ts):
                health = "DONE"
            elif any(t.id in bad_ids for t in ts) or blocked:
                health = "AT RISK"
            elif prog or rdy:
                health = "HEALTHY"
            else:
                health = "WAITING"
            rows.append((cp, title, done, len(ts), prog, blocked, rdy, health))
    return rows


def cmd_status():
    specs = load_specs()
    tickets = all_tickets(specs)
    F = validate()
    print(f"{'CP':<5}{'Checkpoint':<42}{'Done':>8}{'Active':>8}{'Blocked':>9}{'Ready':>7}  Health")
    for cp, title, done, total, prog, blocked, rdy, health in checkpoint_rows(specs, tickets, F):
        print(f"{cp:<5}{title[:40]:<42}{f'{done}/{total}':>8}{prog:>8}{blocked:>9}{rdy:>7}  {health}")
    errs = sum(f.level == "error" for f in F)
    print(f"\nRunway: {len(ready(tickets))} ready ticket(s). Validation: {errs} error(s), {len(F) - errs} warning(s).")
    print("Health is derived from the record. Missing data shows as WAITING, never guessed green.")


def cmd_next():
    tickets = all_tickets(load_specs())
    r = ready(tickets)
    if not r:
        print("No ready tickets. Check `python3 tools/rec.py status` for blocked or in-progress work.")
    for t in r:
        print(f"{t.id}  {t.title}  ({t.checkpoint}, {len(t.acs)} criteria)")


def cmd_ticket(tid: str):
    tickets = all_tickets(load_specs())
    t = tickets.get(tid)
    if not t:
        sys.exit(f"No ticket {tid}. Known: {', '.join(tickets)}")
    lines = t.file.read_text().splitlines()
    print(f"# {rel(t.file)}:{t.line}  checkpoint {t.checkpoint}\n")
    print("\n".join(lines[t.line - 1:t.section_end]).rstrip())
    if t.depends:
        print("\nDependency state:")
        for d in t.depends:
            print(f"  {d}: {tickets[d].status if d in tickets else 'MISSING'}")
    issues = ticket_findings(t, tickets)
    if issues:
        print("\nValidator says:")
        for f in issues:
            print("  " + str(f))


def cmd_orient():
    specs = load_specs()
    tickets = all_tickets(specs)
    F = validate()
    errs = [f for f in F if f.level == "error"]
    out = ["Project record orientation (generated by tools/rec.py orient from record/; this is the current state, not a summary from memory)."]
    eps = sorted((RECORD / "2-intent").glob("EP-*.md"))
    for ep in eps:
        first = next((l for l in ep.read_text().splitlines() if l.startswith("# ")), f"# {ep.stem}")
        out.append(f"Epic: {first[2:]}")
    rows = checkpoint_rows(specs, tickets, F)
    active = next((r for r in rows if r[7] != "DONE"), None)
    if active:
        cp, title, done, total, *_ , health = active
        out.append(f"Current checkpoint: {cp} · {title} ({done}/{total} done, {health}).")
    prog = [t for t in tickets.values() if t.status == "in_progress"]
    if prog:
        out.append("In progress: " + "; ".join(f"{t.id} {t.title}" for t in prog) + ".")
    blocked = [t for t in tickets.values() if t.status == "blocked"]
    if blocked:
        out.append("Blocked: " + "; ".join(f"{t.id} ({t.fence.get('blocked_reason', '?')})" for t in blocked) + ".")
    r = ready(tickets)[:5]
    out.append("Ready to start: " + ("; ".join(f"{t.id} {t.title}" for t in r) if r else "none") + ".")
    decs = sorted((RECORD / "3-history").glob("DEC-*.md"))[-5:]
    if decs:
        out.append("Recent decisions: " + "; ".join(
            next((l[2:] for l in d.read_text().splitlines() if l.startswith("# ")), d.stem) for d in decs) + ".")
    if errs:
        out.append(f"Validation: {len(errs)} error(s). First: {errs[0].where}: {errs[0].msg}. Fix: {errs[0].fix.splitlines()[0]}")
    else:
        out.append(f"Validation: clean ({len(F)} warning(s)).")
    out.append("Working rules for this repo are in CLAUDE.md. Ticket fences are changed only with `python3 tools/rec.py set`. "
               "Start ticket work with the execute-ticket skill.")
    print("\n".join(out))


# ---------------------------------------------------------------- the fence rule

def cmd_set(tid: str, key: str, value: str):
    specs = load_specs()
    tickets = all_tickets(specs)
    t = tickets.get(tid)
    if not t:
        sys.exit(f"No ticket {tid}.")
    if t.fence is None or t.fence_span is None:
        sys.exit(f"{tid} has no ticket fence. Add one by hand first (see `rec.py validate`).")
    fence = dict(t.fence)
    if key == "evidence+":
        ev = list(t.evidence)
        if value not in ev:
            ev.append(value)
        fence["evidence"] = ev
    elif key in ("status", "blocked_reason"):
        if key == "status" and value not in STATUSES:
            sys.exit(f"Invalid status '{value}'. Use one of: {', '.join(sorted(STATUSES))}")
        fence[key] = value
        if key == "status" and value != "blocked":
            fence.pop("blocked_reason", None)
    else:
        sys.exit("KEY must be status, blocked_reason, or evidence+ (ids and exemptions are edited deliberately by hand).")

    # Check the result before writing it: a claim that can't prove itself doesn't stick.
    probe = Ticket(t.id, t.title, t.file, t.line, t.checkpoint, t.acs, t.depends, fence, t.fence_span, t.section_end)
    errs = [f for f in ticket_findings(probe, tickets) if f.level == "error"]
    if errs:
        print(f"Refused: {tid} would be invalid after this change.", file=sys.stderr)
        for f in errs:
            print("  " + str(f), file=sys.stderr)
        sys.exit(1)

    lines = t.file.read_text().splitlines()
    open_i, close_i = t.fence_span
    order = ["id", "status", "blocked_reason", "exempt", "evidence"]
    body = [f"{k}: {render_value(fence[k])}" for k in order if k in fence]
    body += [f"{k}: {render_value(v)}" for k, v in fence.items() if k not in order]
    new = lines[:open_i + 1] + body + lines[close_i:]
    t.file.write_text("\n".join(new) + "\n")
    print(f"{tid}: {key} -> {value}")


# ---------------------------------------------------------------- hooks

def fences_of(text: str) -> list:
    return re.findall(r"```ticket\n(.*?)```", text, flags=re.S)


def apply_edit(text: str, old: str, new: str, replace_all: bool) -> str:
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def deny(reason: str):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def cmd_guard():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp:
        sys.exit(0)
    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ROOT) / path
    path = path.resolve()
    try:
        relp = path.relative_to(RECORD.resolve())
    except ValueError:
        sys.exit(0)
    parts = relp.parts
    if parts and parts[0] == ".archived":
        deny("record/.archived is read-only. Archived files are history; move files there with git mv yourself.")
    if len(parts) == 2 and parts[0] == "3-history" and parts[1].startswith("DEC-") and path.exists():
        deny(f"{parts[1]} is an accepted decision record and is immutable. Write a new DEC-NNNN that supersedes it and link back with [[{path.stem}]].")
    if len(parts) == 2 and parts[0] == "2-intent" and parts[1].startswith("PS-") and path.exists():
        before = path.read_text()
        if tool == "Write":
            after = ti.get("content", "")
        elif tool == "Edit":
            after = apply_edit(before, ti.get("old_string", ""), ti.get("new_string", ""), bool(ti.get("replace_all")))
        elif tool == "MultiEdit":
            after = before
            for e in ti.get("edits", []):
                after = apply_edit(after, e.get("old_string", ""), e.get("new_string", ""), bool(e.get("replace_all")))
        else:
            sys.exit(0)
        old_f, new_f = fences_of(before), fences_of(after)
        if old_f != new_f:
            # Allow pure additions of new tickets (new fences appended), never changes to existing ones.
            if not (len(new_f) > len(old_f) and all(f in new_f for f in old_f)):
                deny("Ticket fences are machine-owned. Edit prose and checkboxes freely, but change ticket state with "
                     "`python3 tools/rec.py set <ID> status|blocked_reason|evidence+ <value>`.")
    sys.exit(0)


def cmd_stop_check():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        sys.exit(0)   # already asked once this turn; don't loop
    errs = [f for f in validate() if f.level == "error"]
    if not errs:
        sys.exit(0)
    print(f"The project record has {len(errs)} validation error(s). Repair them before finishing:", file=sys.stderr)
    for f in errs[:10]:
        print(str(f), file=sys.stderr)
    if len(errs) > 10:
        print(f"...and {len(errs) - 10} more. Run `python3 tools/rec.py validate`.", file=sys.stderr)
    sys.exit(2)


def cmd_validate(quiet: bool):
    F = validate()
    errs = [f for f in F if f.level == "error"]
    for f in F:
        if not (quiet and f.level == "warn"):
            print(f)
    print(f"\n{len(errs)} error(s), {len(F) - len(errs)} warning(s).")
    sys.exit(1 if errs else 0)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "validate":
        cmd_validate("--quiet" in args)
    elif cmd == "orient":
        cmd_orient()
    elif cmd == "status":
        cmd_status()
    elif cmd == "next":
        cmd_next()
    elif cmd == "ticket" and len(args) == 1:
        cmd_ticket(args[0])
    elif cmd == "set" and len(args) == 3:
        cmd_set(*args)
    elif cmd == "guard":
        cmd_guard()
    elif cmd == "stop-check":
        cmd_stop_check()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
