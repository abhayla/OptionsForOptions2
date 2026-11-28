#!/usr/bin/env python3
"""lane_watch: the coordinator's read-only watch over the lanes and the build.

Usage: python .claude/skills/lanes/lane_watch.py --repo PATH --state FILE [--now ISO] [--json]
       [--no-fetch] [--silent-minutes 90] [--instruction-minutes 30]
Exit 1 if a hold is violated, a migration collides or a commitment is past due; else 0.
Standard library and git only. It never pushes, never sends a message, never edits the repository. It runs only
read commands of git (an allow-list below, logged in GIT_LOG) and, unless --no-fetch, one `git fetch`.
Every time comes from COMMIT times and this script's own clock in IST. A lane's STATUS text is shown, never trusted
(lesson 19: lane clocks drift; F3's STATUS said 23:20 at 22:40).

The state file (one file the coordinator must keep; the real one is outside git at
docs/process/.run/coordinator-state.json; `state.example.json` next to this file is the tracked example):
  lanes: [{name, session_id, branch, results_file, owns: [path globs], base (optional branch it started from),
           state: working|closing|closed, started_at, first_push_due, next_push_due, context_note}]
         first_push_due: the first push is met by any commit newer than started_at.
         next_push_due: met by a commit newer than that time; the coordinator moves it forward after each push.
  holds: [{branch, commit | not_newer_than, reason, until}]
         commit: the build must not contain this commit. not_newer_than: the build may contain the branch only up
         to this commit (case: RA2 held at F3's as-of). until: the hold ends at this time.
  conditions: [{what, by, met}]      met false after `by` is an action.
  waves: [{name, due, commit, ci}]   past due with ci not green is an action.
  build: {branch, pull_request}      the branch every wave merges into.
  commitments: [{what, by, done (optional)}]   past `by` and not done: exit 1.
  items: path of the board's plan-items.json (optional; counted if it is a list of {status|state}).
  instructions: [{to_lane, sent_at, text_short, acknowledged_at or null}]
  migrations_path (optional): directory of the alembic version files; base_branch (optional): default lane base.
All times are ISO with the +05:30 offset (a time with no offset is read as IST).
"""
# ruff: noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917, PLR2004, S603, S607, PLW1510
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_MIGRATIONS = "backend/ofo_app/alembic/versions"
READ_ONLY = {"rev-parse", "rev-list", "log", "show", "diff", "merge-base", "cat-file", "ls-tree", "for-each-ref"}
GIT_LOG: list[list[str]] = []  # every git command run, for the tests
GREEN = {"green", "pass", "passed", "success"}
DONE = {"done", "closed", "proven", "merged", "passed", "complete", "completed"}


class Finding(Exception):
    pass


def git(repo: str, *args: str) -> tuple[int, str]:
    """Run one allow-listed git command; return (exit code, stdout)."""
    if args[0] not in READ_ONLY and args[0] != "fetch":
        raise RuntimeError(f"git {args[0]} is not allowed in lane_watch")
    GIT_LOG.append(list(args))
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)


def hhmm(t: datetime) -> str:
    return t.astimezone(IST).strftime("%H:%M")


def ref_of(branch: str) -> str:
    return f"origin/{branch}"


def commit_of(repo: str, ref: str) -> tuple[str, datetime] | None:
    rc, out = git(repo, "log", "-1", "--format=%H %ct", ref, "--")
    if rc != 0 or not out.strip():
        return None
    sha, ct = out.split()
    return sha, datetime.fromtimestamp(int(ct), IST)


def is_ancestor(repo: str, a: str, b: str) -> bool | None:
    rc, _ = git(repo, "merge-base", "--is-ancestor", a, b)
    return True if rc == 0 else False if rc == 1 else None


def merge_base(repo: str, a: str, b: str) -> str | None:
    rc, out = git(repo, "merge-base", a, b)
    return out.strip() if rc == 0 and out.strip() else None


def show(repo: str, ref: str, path: str) -> str | None:
    rc, out = git(repo, "show", f"{ref}:{path}")
    return out if rc == 0 else None


def owns_match(path: str, owns: list[str]) -> bool:
    for pat in owns:
        if fnmatch.fnmatchcase(path, pat) or fnmatch.fnmatchcase(path, pat.replace("/**/", "/")):
            return True
        if pat.endswith("/") and path.startswith(pat):
            return True
    return False


def migration_info(repo: str, ref: str, path: str) -> dict:
    text = show(repo, ref, path) or ""
    rev = re.search(r"(?m)^revision\s*(?::[^=]+)?=\s*[\"']([^\"']+)[\"']", text)
    down = re.search(r"(?m)^down_revision\s*(?::[^=]+)?=\s*(.+)$", text)
    name = path.rsplit("/", 1)[-1]
    revision = rev.group(1) if rev else name.rsplit(".", 1)[0]
    num = re.match(r"\d+", revision) or re.match(r"\d+", name)
    rc, blob = git(repo, "rev-parse", f"{ref}:{path}")
    return {"path": path, "revision": revision, "number": num.group(0) if num else revision,
            "down": down.group(1).strip().strip("\"'") if down else "", "blob": blob.strip() if rc == 0 else ""}


def added_files(repo: str, base: str, ref: str, subdir: str | None = None) -> list[str]:
    args = ["diff", "--name-only", "--diff-filter=A", base, ref]
    if subdir:
        args += ["--", subdir]
    rc, out = git(repo, *args)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def changed_files(repo: str, base: str, ref: str) -> list[str]:
    rc, out = git(repo, "diff", "--name-only", base, ref)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


class Report:
    def __init__(self) -> None:
        self.actions: list[dict] = []
        self.lines: list[str] = []  # the per-lane and info lines
        self.lanes: list[dict] = []
        self.holds: list[dict] = []
        self.fatal = False

    def act(self, flag: str, subject: str, text: str, fatal: bool = False) -> None:
        self.actions.append({"flag": flag, "subject": subject, "text": text, "fatal": fatal})
        self.fatal = self.fatal or fatal


def watch(repo: str, state: dict, now: datetime, silent_min: int = 90, instr_min: int = 30,
          fetch: bool = True) -> Report:
    rep = Report()
    if fetch:
        rc, _ = git(repo, "fetch", "--quiet", "--prune", "origin")
        if rc != 0:
            rep.act("FETCH FAILED", "origin", "git fetch failed; refs below may be old")
    build = (state.get("build") or {}).get("branch", "")
    build_ref = ref_of(build) if build else ""
    build_ok = bool(build) and commit_of(repo, build_ref) is not None
    if build and not build_ok:
        rep.act("FINDING", build, f"build branch {build} not found on origin")
    lanes = state.get("lanes", [])
    mig_dir = state.get("migrations_path", DEFAULT_MIGRATIONS)

    # ---- lanes: head, age, STATUS, OVERDUE, SILENT, CLOSING WITHOUT SAFE TO CLOSE
    info: dict[str, dict] = {}
    for lane in lanes:
        name, br = lane["name"], lane.get("branch", "")
        st = lane.get("state", "working")
        started = parse_time(lane.get("started_at"))
        c = commit_of(repo, ref_of(br)) if br else None
        rec = {"name": name, "branch": br, "state": st, "head": None, "minutes_since_commit": None,
               "status": None, "flags": []}
        status_line = None
        if c:
            rec["head"], ct = c[0][:9], c[1]
            rec["minutes_since_commit"] = max(0, int((now - ct).total_seconds() // 60))
            text = show(repo, ref_of(br), lane["results_file"]) if lane.get("results_file") else None
            if text is not None:
                status_line = next((ln for ln in text.splitlines() if ln.lstrip().startswith("STATUS")), None)
                if status_line:
                    rec["status"] = status_line[:200]
                    m = re.match(r"\s*STATUS\s+(\d{1,2}):(\d{2})", status_line)
                    if m:
                        diff = (int(m.group(1)) * 60 + int(m.group(2))) - (now.hour * 60 + now.minute)
                        diff = (diff + 720) % 1440 - 720
                        ahead = (int(m.group(1)) * 60 + int(m.group(2))) - (ct.hour * 60 + ct.minute)
                        ahead = (ahead + 720) % 1440 - 720
                        if diff > 10 or ahead > 15:
                            rec["flags"].append(f"STATUS CLOCK AHEAD {max(diff, ahead)} min (ignored)")
        info[name] = {"commit": c, "text_ok": rec["status"] is not None}
        if st == "working":
            missing = [k for k in ("results_file", "owns") if not lane.get(k)]
            if not lane.get("first_push_due") and not lane.get("next_push_due"):
                missing.append("first_push_due or next_push_due")
            if missing:
                rep.act("STATE INCOMPLETE", name, f"{name}: state file lacks {', '.join(missing)}; "
                        "checks for this lane are off until it is filled")
                rec["flags"].append("STATE INCOMPLETE")
            due = parse_time(lane.get("next_push_due")) or parse_time(lane.get("first_push_due"))
            if parse_time(lane.get("next_push_due")):
                met = c is not None and c[1] >= due
            else:
                met = c is not None and (started is None or c[1] >= started)
            if due and now > due and not met:
                late = int((now - due).total_seconds() // 60)
                why = f"no branch {br} on origin" if c is None else f"last commit {hhmm(c[1])}"
                rep.act("OVERDUE", name, f"{name}: push due {hhmm(due)}, now {hhmm(now)} ({late} min late); {why}")
                rec["flags"].append("OVERDUE")
            elif c is None:
                rec["flags"].append("NO BRANCH YET")
            if c and rec["minutes_since_commit"] > silent_min:
                rep.act("SILENT", name, f"{name}: no commit for {rec['minutes_since_commit']} min "
                        f"(last {hhmm(c[1])}); STATUS text is not a heartbeat")
                rec["flags"].append("SILENT")
        if st in ("closing", "closed"):
            text = show(repo, ref_of(br), lane["results_file"]) if c and lane.get("results_file") else None
            if not text or "SAFE TO CLOSE" not in text:
                rep.act("CLOSING WITHOUT SAFE TO CLOSE", name,
                        f"{name} is {st} but its results file has no SAFE TO CLOSE line")
                rec["flags"].append("CLOSING WITHOUT SAFE TO CLOSE")
        rep.lanes.append(rec)

    # ---- holds
    for h in state.get("holds", []):
        br = h.get("branch", "?")
        until = parse_time(h.get("until"))
        rec = {"branch": br, "reason": h.get("reason", ""), "until": h.get("until"), "status": "HELD"}
        if until and now > until:
            rec["status"] = "EXPIRED"
            rep.holds.append(rec)
            continue
        if not build_ok:
            rec["status"] = "UNKNOWN"
            rep.act("FINDING", br, f"hold on {br} cannot be checked: build branch not reachable")
            rep.holds.append(rec)
            continue
        viol = None
        if h.get("commit"):
            viol = is_ancestor(repo, h["commit"], build_ref)
            if viol is None:
                rec["status"] = "UNKNOWN"
                rep.act("FINDING", br, f"hold commit {h['commit'][:9]} of {br} not found in the repository")
        elif h.get("not_newer_than"):
            hb = ref_of(br)
            rc, out = git(repo, "rev-list", "--first-parent", "--no-merges", "--max-count=500",
                          hb, f"^{h['not_newer_than']}")
            if rc != 0:
                rec["status"] = "UNKNOWN"
                rep.act("FINDING", br, f"hold on {br}: branch or limit {h['not_newer_than'][:9]} not found")
            else:
                # the branch's OWN commits newer than the limit (first-parent: what it merged from the build is not
                # its own work); held if the build contains any of them
                viol = any(is_ancestor(repo, c, build_ref) for c in out.split())
        if viol:
            rec["status"] = "VIOLATED"
            rep.act("HOLD VIOLATED", br, f"{br}: the build {build} contains held work ({h.get('reason', '')}); "
                    f"revert or stop the merge", fatal=True)
        rep.holds.append(rec)

    # ---- migrations (core)
    if build_ok:
        by_branch: dict[str, dict[str, dict]] = {}
        cands = [ln["branch"] for ln in lanes if ln.get("state") == "working" and ln.get("branch")]
        for br in cands:
            ref = ref_of(br)
            if br == build or commit_of(repo, ref) is None:
                continue
            mb = merge_base(repo, ref, build_ref)
            if mb is None:
                rep.act("FINDING", br, f"{br}: no merge base with the build {build}")
                continue
            files = {p: migration_info(repo, ref, p) for p in added_files(repo, mb, ref, mig_dir)
                     if p.endswith(".py")}
            bfiles = {p: migration_info(repo, build_ref, p) for p in added_files(repo, mb, build_ref, mig_dir)
                      if p.endswith(".py")}
            by_branch[br] = files
            by_branch.setdefault(f"{build} (since {br})", bfiles)
        seen: set[tuple] = set()
        names = list(by_branch)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if b.startswith(f"{build} (since ") and a.startswith(b.split(" (since ")[0]):
                    continue
                for pa, ia in by_branch[a].items():
                    for pb, ib in by_branch[b].items():
                        if ia["blob"] and ia["blob"] == ib["blob"] and pa == pb:
                            continue  # the same file reached both
                        kinds = []
                        if ia["number"] == ib["number"]:
                            kinds.append(f"same revision number {ia['number']}")
                        if ia["down"] and ia["down"] == ib["down"]:
                            kinds.append(f"same down_revision {ia['down']} (two heads)")
                        if kinds:
                            key = (frozenset([a.split(" (")[0], b.split(" (")[0]]), ia["revision"], ib["revision"])
                            if key in seen:
                                continue
                            seen.add(key)
                            rep.act("MIGRATION COLLISION", f"{a} / {b}",
                                    f"{a} adds {ia['revision']} and {b} adds {ib['revision']}: {', '.join(kinds)}; "
                                    f"`alembic upgrade head` fails after both merge; renumber the later one",
                                    fatal=True)

    # ---- file overlap and files outside owns
    changed: dict[str, list[str]] = {}
    for ln in lanes:
        if ln.get("state") != "working" or not ln.get("branch"):
            continue
        ref = ref_of(ln["branch"])
        if commit_of(repo, ref) is None:
            continue
        base_br = build if build_ok else (ln.get("base") or state.get("base_branch") or build)
        base_ref = ref_of(base_br) if base_br else ""
        mb = merge_base(repo, ref, base_ref) if base_ref else None
        if mb is None:
            rep.act("FINDING", ln["name"], f"{ln['name']}: no merge base with {base_br}; file checks skipped")
            continue
        changed[ln["name"]] = changed_files(repo, mb, ref)
    owns = {ln["name"]: ln.get("owns", []) for ln in lanes}
    names = list(changed)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            both = sorted(set(changed[a]) & set(changed[b]))
            bad = [f for f in both if not (owns_match(f, owns[a]) and owns_match(f, owns[b]))]
            if bad:
                rep.act("FILE OVERLAP", f"{a} / {b}", f"{a} and {b} both changed {len(bad)} file(s) not owned by "
                        f"both: {', '.join(bad[:5])}{' ...' if len(bad) > 5 else ''}")
    for n in names:
        if not owns[n]:
            continue
        out = [f for f in changed[n] if not owns_match(f, owns[n])]
        if out:
            rep.act("OUTSIDE OWNS", n, f"{n} changed {len(out)} file(s) outside its owns: "
                    f"{', '.join(out[:5])}{' ...' if len(out) > 5 else ''}")

    # ---- instructions, conditions, waves, commitments
    for ins in state.get("instructions", []):
        sent = parse_time(ins.get("sent_at"))
        if sent and not ins.get("acknowledged_at") and (now - sent) > timedelta(minutes=instr_min):
            mins = int((now - sent).total_seconds() // 60)
            rep.act("INSTRUCTION NOT ACKNOWLEDGED", ins.get("to_lane", "?"),
                    f"{ins.get('to_lane', '?')}: sent {hhmm(sent)}, no acknowledgement for {mins} min: "
                    f"{ins.get('text_short', '')} (a lane hears only at turn end; re-send or check its branch)")
    for c in state.get("conditions", []):
        by = parse_time(c.get("by"))
        if by and not c.get("met") and now > by:
            rep.act("CONDITION NOT MET", c.get("what", "?"), f"condition past {hhmm(by)} and not met: {c.get('what')}")
    for w in state.get("waves", []):
        due = parse_time(w.get("due"))
        if due and now > due and str(w.get("ci", "")).lower() not in GREEN:
            rep.act("WAVE PAST DUE", w.get("name", "?"), f"wave {w.get('name')} was due {hhmm(due)}; "
                    f"commit {str(w.get('commit') or 'none')[:9]}, ci {w.get('ci') or 'none'}")
    for c in state.get("commitments", []):
        by = parse_time(c.get("by"))
        if by and now > by and not c.get("done"):
            rep.act("COMMITMENT PAST DUE", c.get("what", "?"), f"promised by {hhmm(by)}, not done: {c.get('what')}",
                    fatal=True)

    # ---- items count (optional)
    src = state.get("items")
    if src:
        try:
            data = json.loads(Path(src if Path(src).is_absolute() else Path(repo) / src).read_text("utf-8"))
            if isinstance(data, dict):
                data = data.get("items", [])
            rows = [r for r in data if isinstance(r, dict)]
            open_n = sum(1 for r in rows if str(r.get("status", r.get("state", ""))).lower() not in DONE)
            rep.lines.append(f"ITEMS: {open_n} open of {len(rows)} ({src})")
        except (OSError, ValueError, TypeError):
            rep.lines.append(f"ITEMS: source {src} not readable")
    return rep


def render(rep: Report, now: datetime) -> str:
    out = [f"ACT NOW: {len(rep.actions)}   (watch time {now.strftime('%d %b %H:%M')} IST)"]
    for i, a in enumerate(rep.actions, 1):
        out.append(f" {i}. {a['flag']}: {a['text']}")
    out.append("LANES")
    for r in rep.lanes:
        age = "no commit" if r["minutes_since_commit"] is None else f"{r['minutes_since_commit']} min since last commit"
        flags = f" [{'; '.join(r['flags'])}]" if r["flags"] else ""
        out.append(f" {r['name']} ({r['state']}) head {r['head'] or '-'} | {age}{flags}")
        if r["status"]:
            out.append(f"   {r['status']}")
    out.append("HOLDS")
    holds = rep.holds or [{"branch": "-", "status": "none", "reason": "", "until": None}]
    out.extend(f" {h['status']} {h['branch']}: {h['reason']}" + (f" (until {h['until']})" if h.get("until") else "")
               for h in holds)
    out.extend(rep.lines)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only watch over the lanes and the build.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--now", help="ISO time with offset; default the system clock in IST")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fetch", action="store_true", help="do not run git fetch (read commands only)")
    ap.add_argument("--silent-minutes", type=int, default=90)
    ap.add_argument("--instruction-minutes", type=int, default=30)
    a = ap.parse_args(argv)
    try:
        state = json.loads(Path(a.state).read_text("utf-8"))
    except (OSError, ValueError) as e:
        print(f"ACT NOW: 1\n 1. FINDING: state file {a.state} not readable: {e}")
        return 1
    now = parse_time(a.now) if a.now else datetime.now(IST)
    if now is None:
        print(f"bad --now {a.now!r}")
        return 2
    rep = watch(a.repo, state, now, a.silent_minutes, a.instruction_minutes, fetch=not a.no_fetch)
    code = 1 if rep.fatal else 0
    if a.json:
        print(json.dumps({"now": now.isoformat(), "act_now": rep.actions, "lanes": rep.lanes, "holds": rep.holds,
                          "notes": rep.lines, "exit_code": code}, indent=2))
    else:
        print(render(rep, now))
    return code


if __name__ == "__main__":
    sys.exit(main())
