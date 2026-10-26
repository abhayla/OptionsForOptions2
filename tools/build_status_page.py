#!/usr/bin/env python3
"""build_status_page.py — render one project status page (REQ-008, OD-35) from the project's own data.

Usage:
    python tools/build_status_page.py ROOT --issues ISSUES.json --runs RUNS.json --out FILE
                                      [--title TEXT] [--now TEXT] [--sha TEXT]
    python tools/build_status_page.py ROOT --fetch --out FILE      (runs the gh commands below first)

Inputs (all read-only; nothing is read from a previously published page — status-artifact R1):
    spec/requirements/REQ-*.md, work/W-*.md, evidence/, views/build-order.md,
    knowledge/findings/*.json, owner-questions/OQ-*.md, .github/workflows/*.yml, git log,
    ISSUES.json  = gh issue list --state all --json number,title,state,labels,body,createdAt,closedAt
    RUNS.json    = gh run list --json databaseId,name,conclusion,createdAt,workflowName, each run carrying
                   a "jobs" list (gh run view ID --json jobs; each job has "steps" with conclusions)

The page is a pure function of those inputs plus two stamps (git sha, generation time), both
overridable (--sha, --now) so tests compare exact output. Every number is computed from the inputs;
one that cannot be computed reads `unmeasured` and names the command that would measure it (R2).
An issue's relates-to comes only from a `Relates-to:` line of its body naming EITHER requirement ids
(`Relates-to: REQ-006` or `Relates-to: REQ-006, REQ-007`) OR a section (`Relates-to: section <name>`); an
issue without one (the untouched form placeholder included) is counted and shown as UNMAPPED. "Needs you" comes only from owner-questions/.
The generated HTML is never committed (it depends on live issue and CI state).
Each requirement shows a computed health beside its stored status (REQ-014 AC-5), first match wins:
Changed - needs re-check (stale or unusable evidence fingerprint per trace_check, or a failing confirmed_against pin
per spec_dupes), Blocked (a work item delivering it is blocked or lists blockers), Parked (a parked issue's
Relates-to names it; work items have no parked status), Unpinned evidence (evidence without ac_fp), else OK.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import math
import os
import re
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delivery_metrics  # noqa: E402  (delivery numbers from the repository host, computed only under --fetch)
import factory_lint  # noqa: E402  (frontmatter parser and the owner-question schema live there)
import spec_dupes  # noqa: E402  (`cites` is the one definition of "a requirement cites a decision")
import spec_text  # noqa: E402  (OD rows and decision records are read by the same parser the spec checks use)
import trace_check  # noqa: E402  (stale / unpinned evidence: the one definition, REQ-014)
import yaml  # noqa: E402


def _faster_yaml() -> None:
    """One render parses the same few hundred record files through several readers (this page, trace_check, spec_text):
    the same text is parsed once (libyaml when installed) and each caller gets its own copy. Same result, a third of the
    time; applied once per process."""
    if getattr(yaml.safe_load, "_cached", False):
        return
    import copy
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    memo: dict = {}

    def cached(stream):
        if not isinstance(stream, str):
            return yaml.load(stream, Loader=loader)
        if stream not in memo:
            try:
                memo[stream] = (True, yaml.load(stream, Loader=loader))
            except Exception as exc:                      # the same error again for the same text
                memo[stream] = (False, exc)
        ok, val = memo[stream]
        if not ok:
            raise val
        return copy.deepcopy(val)
    cached._cached = True
    yaml.safe_load = cached


_faster_yaml()

DONE = {"Verified", "Reviewed", "Released", "Delivered-before-trace"}   # REQ-014 AC-4
STATUS_ORDER = ["Draft", "Specified", "Approved", "Planned", "Implementing", "Implemented", "Testing", "Verified",
                "Reviewed", "Released", "Delivered-before-trace", "Superseded"]
# REQ-014 AC-5: one computed health per requirement, first match wins, in this order
H_CHANGED = "Changed - needs re-check"
H_BLOCKED = "Blocked"
H_PARKED = "Parked"
H_UNPINNED = "Unpinned evidence"
H_OK = "OK"
HEALTHS = [H_CHANGED, H_BLOCKED, H_PARKED, H_UNPINNED, H_OK]
PIN_LINE_RE = re.compile(r"^PIN (REQ-\d{3,})\b")
NO_REQUIREMENT = "no requirement"
UNMAPPED = "UNMAPPED"
ISSUE_LIMIT = 1000
GH_ISSUES_CMD = f"gh issue list --state all --limit {ISSUE_LIMIT} --json number,title,state,labels,body,createdAt,closedAt"
GH_RUNS_CMD = "gh run list --limit 10 --json databaseId,name,status,conclusion,createdAt,workflowName,headSha,url"
GH_JOBS_CMD = "gh run view <databaseId> --json jobs"
RELATES_LINE_RE = re.compile(r"^Relates-to:[ \t]*(.*?)[ \t]*$")
RELATES_REQS_RE = re.compile(r"^REQ-\d{3,}(?:[ \t]*,[ \t]*REQ-\d{3,})*$")
RELATES_SECTION_RE = re.compile(r"^section[ \t]+([^<\s].*)$")
STAGE_PATHS = ["spec/requirements", "work", "owner-questions", "evidence", "views/status-page.json"]
e = html.escape


def esc(v) -> str:
    return html.escape(str(v), quote=True)


# ---- reading the repo ------------------------------------------------------------------------------

def _fm(path: Path) -> dict | None:
    data, err = factory_lint.parse_frontmatter(path)
    return None if err else data


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def read_requirements(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "spec" / "requirements" / "REQ-*.md"))):
        d = _fm(Path(p))
        bad = d is None
        d = d or {}
        d.setdefault("id", Path(p).stem)
        if bad:
            d["_unreadable"] = True
        out.append(d)
    return out


def read_works(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "work" / "W-*.md"))):
        d = _fm(Path(p)) or {}
        d.setdefault("id", Path(p).stem)
        out.append(d)
    return out


def read_findings(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "knowledge" / "findings" / "*.json"))):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            d.setdefault("id", Path(p).stem)
            out.append(d)
    return out


def read_owner_questions(root: Path) -> tuple[list[dict], list[str]] | None:
    """(open questions, names of unreadable files); None when the project has no owner-questions/ folder at all
    (a missing source is not an empty one: knowledge/findings/absent-source-reads-as-empty.json). Answered ones are
    read and dropped."""
    if not (root / "owner-questions").is_dir():
        return None
    open_qs: list[dict] = []
    bad: list[str] = []
    for p in sorted(glob.glob(str(root / "owner-questions" / "OQ-*.md"))):
        path = Path(p)
        data = _fm(path)
        if data is None or factory_lint.validate_data("owner-question", data, str(path)):
            bad.append(path.name)
            continue
        if data.get("status") == "open":
            open_qs.append(data)
    return open_qs, bad


def read_build_order(root: Path) -> list[dict] | None:
    p = root / "views" / "build-order.md"
    if not p.is_file():
        return None
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| REQ-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({"id": cells[0], "title": cells[1], "layer": cells[2], "risk": cells[3], "state": cells[4]})
    return rows


def read_workflow_jobs(root: Path) -> list[tuple[str, str, set[str]]]:
    """(workflow name, job display name, names a run may report for it)."""
    out = []
    wf_dir = root / ".github" / "workflows"
    for p in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            continue
        wf = data.get("name") if isinstance(data.get("name"), str) else p.stem
        for key, job in data["jobs"].items():
            name = job.get("name") if isinstance(job, dict) and isinstance(job.get("name"), str) else None
            if name and "${{" in name:
                name = name.split("${{")[0].strip() or None
            display = name or str(key)
            out.append((wf, display, {str(key), display}))
    return out


def recent_stage_changes(root: Path) -> list[str] | None:
    out = _git(root, "log", "-20", "--format=%h|%cs|%s", "--", *STAGE_PATHS)
    return None if out is None else [ln for ln in out.splitlines() if ln]


# ---- code state, pull requests, now, plans, test results (REQ-052 AC-3, AC-4, AC-5) ---------------------
# Every function below fails soft: a git or gh call that does not work turns into the string
# `unmeasured: <command>` in that field, and nothing raises (status-artifact R2, REQ-052 AC-5).

SECRET_NAME_RE = re.compile(r"env|key|token|secret|pem|credential", re.I)
MAX_NAMES = 20
STALE_DAYS = 3
PAUSED_HOURS = 2
MERGED_DAYS = 14
PORCELAIN = ("status", "--porcelain", "-uall")   # the one set of flags used everywhere
MAIN_BRANCHES = {"main", "master"}


def _git_rc(root: Path, *args: str) -> int | None:
    """Exit code of `git -C root args`, or None when git could not be started."""
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").returncode
    except OSError:
        return None


def _unm(cmd: str) -> str:
    return f"unmeasured: {cmd}"


def _git_cmd(*args: str) -> str:
    return "git " + " ".join(args)


def _parse_iso(text) -> datetime.datetime | None:
    try:
        d = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()


def _porcelain_paths(out: str) -> list[str]:
    paths = []
    for ln in out.splitlines():
        if len(ln) < 4:
            continue
        p = ln[3:]
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        paths.append(p.strip().strip('"'))
    return paths


def summarize_unsaved(paths: list[str]) -> dict:
    """Counts per top folder, at most MAX_NAMES names; secret-looking names are counted as hidden, never listed."""
    shown = [p for p in paths if not SECRET_NAME_RE.search(p)]
    folders: dict[str, int] = {}
    for p in shown:
        top = p.split("/", 1)[0] if "/" in p else "(top level)"
        folders[top] = folders.get(top, 0) + 1
    return {"count": len(paths), "by_folder": dict(sorted(folders.items())), "names": shown[:MAX_NAMES],
            "more": max(0, len(shown) - MAX_NAMES), "hidden": len(paths) - len(shown)}


def read_code_state(root: Path) -> dict:
    """The main checkout and each of its worktrees: branch, last commit, unsaved files, commits not pushed."""
    root = Path(root)
    c = ("rev-parse", "--path-format=absolute", "--git-common-dir")
    common = _git(root, *c)
    main_co = Path(common.strip()).parent if common and common.strip() else None
    base = main_co or root
    state: dict = {"main_checkout": str(main_co) if main_co else _unm(_git_cmd(*c))}
    wl = ("worktree", "list", "--porcelain")
    listing = _git(base, *wl)
    if listing is None:
        state["worktrees"] = _unm(_git_cmd(*wl))
        return state
    entries: list[dict] = []
    for ln in listing.splitlines():
        if ln.startswith("worktree "):
            entries.append({"path": ln[9:].strip()})
        elif entries and ln.startswith("branch "):
            entries[-1]["branch"] = ln[7:].strip().removeprefix("refs/heads/")
        elif entries and ln.strip() == "detached":
            entries[-1]["branch"] = "(detached)"
    out = []
    for e_ in entries:
        p, b = Path(e_["path"]), e_.get("branch", "(detached)")
        w: dict = {"path": e_["path"], "branch": b}
        lc = ("log", "-1", "--format=%cI")
        t = _git(p, *lc)
        w["last_commit"] = t.strip() if t and t.strip() else _unm(_git_cmd(*lc))
        por = _git(p, *PORCELAIN)
        w["unsaved"] = summarize_unsaved(_porcelain_paths(por)) if por is not None else _unm(_git_cmd(*PORCELAIN))
        if b == "(detached)":
            w["not_pushed"] = "no branch (detached)"
        else:
            # origin/<branch> by name, never @{u}: a branch that tracks origin/main would be counted against main.
            sr = ("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{b}")
            rc = _git_rc(base, *sr)
            if rc == 1:                      # git ran and the ref is not there: the branch was never pushed
                w["not_pushed"] = "never pushed"
            elif rc != 0:                    # git itself failed: say so, never claim "never pushed"
                w["not_pushed"] = _unm(_git_cmd(*sr))
            else:
                rl = ("rev-list", "--count", f"origin/{b}..HEAD")
                n = _git(p, *rl)
                w["not_pushed"] = int(n) if n and n.strip().isdigit() else _unm(_git_cmd(*rl))
        out.append(w)
    state["worktrees"] = out
    lb = _git(base, "branch", "--format=%(refname:short)")
    state["local_branches"] = sorted({b for b in (lb or "").split() if b} - {w["branch"] for w in out})
    return state


def branch_upload_state(root: Path, b: str):
    """not_pushed for a local branch that no working copy has checked out: 'never pushed', a count, or unmeasured."""
    sr = ("show-ref", "--verify", "--quiet", f"refs/remotes/origin/{b}")
    rc = _git_rc(root, *sr)
    if rc == 1:
        return "never pushed"
    if rc != 0:
        return _unm(_git_cmd(*sr))
    rl = ("rev-list", "--count", f"origin/{b}..{b}")
    n = _git(root, *rl)
    return int(n) if n and n.strip().isdigit() else _unm(_git_cmd(*rl))


def _ci_state(rollup) -> str:
    if not isinstance(rollup, list) or not rollup:
        return "no checks"
    verdicts = set()
    for c in rollup:
        if not isinstance(c, dict):
            continue
        v = (c.get("conclusion") or c.get("state") or "").upper()
        if not v or str(c.get("status", "")).upper() in {"IN_PROGRESS", "QUEUED", "PENDING"} or v == "PENDING":
            verdicts.add("pending")
        elif v in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            verdicts.add("passing")
        else:
            verdicts.add("failing")
    return "failing" if "failing" in verdicts else "pending" if "pending" in verdicts else "passing" if verdicts else "no checks"


PR_LIMIT = 1000


def read_prs(root: Path, today: datetime.date | None = None) -> dict:
    """{'open': [...]|unmeasured, 'merged': [...]|unmeasured}; an empty list means none (rendered as 'none')."""
    root = Path(root)
    since = ((today or datetime.date.today()) - datetime.timedelta(days=MERGED_DAYS)).isoformat()
    open_args = ["pr", "list", "--state", "open", "--limit", str(PR_LIMIT), "--json",
                 "number,title,headRefName,url,isDraft,statusCheckRollup"]
    merged_args = ["pr", "list", "--state", "merged", "--limit", str(PR_LIMIT), "--search", f"merged:>={since}", "--json",
                   "number,title,headRefName,url,mergedAt"]
    out: dict = {}
    data = _gh_json(open_args, root)
    if isinstance(data, list):
        out["open"] = [{"number": d.get("number"), "title": d.get("title"), "branch": d.get("headRefName"),
                        "url": d.get("url"), "draft": bool(d.get("isDraft")), "ci": _ci_state(d.get("statusCheckRollup"))}
                       for d in data if isinstance(d, dict)]
        if len(data) >= PR_LIMIT:                      # gh stopped at the limit: the list may be longer
            out["open_capped"] = True
    else:
        out["open"] = _unm("gh " + " ".join(open_args))
    data = _gh_json(merged_args, root)
    if isinstance(data, list):
        out["merged"] = [{"number": d.get("number"), "title": d.get("title"), "branch": d.get("headRefName"),
                          "url": d.get("url"), "merged_at": d.get("mergedAt")} for d in data if isinstance(d, dict)]
        if len(data) >= PR_LIMIT:
            out["merged_capped"] = True
    else:
        out["merged"] = _unm("gh " + " ".join(merged_args))
    return out


def read_now(root: Path, works: list[dict], code_state: dict, now: datetime.datetime | None = None) -> dict:
    """What is being worked on: in-progress items with age, active worktree branches, and whether it is paused."""
    root = Path(root)
    now = now or datetime.datetime.now().astimezone()
    items, unknown_time = [], False
    for w in works:
        if w.get("status") != "in_progress":
            continue
        wid = str(w.get("id"))
        lc = ("log", "-1", "--format=%cI", "--", f"work/{wid}.md")
        out = _git(root, *lc)
        when = _parse_iso(out) if out and out.strip() else None
        item = {"id": wid, "title": w.get("title")}
        if when is None:
            item.update(last_change=_unm(_git_cmd(*lc)), age_days=None, stale=None)
        else:
            age = round((now - when).total_seconds() / 86400, 1)
            item.update(last_change=when.isoformat(), age_days=age, stale=age > STALE_DAYS)
        items.append(item)
    branches, recent = [], False
    wts = code_state.get("worktrees") if isinstance(code_state, dict) else None
    if not isinstance(wts, list):
        unknown_time = True
        wts = []
    for wt in wts:
        when = _parse_iso(wt.get("last_commit"))
        if when is None:
            unknown_time = True
        elif (now - when).total_seconds() < PAUSED_HOURS * 3600:
            recent = True
        if wt.get("branch") not in MAIN_BRANCHES and wt.get("branch") != "(detached)":
            branches.append({"branch": wt.get("branch"), "path": wt.get("path"), "last_commit": wt.get("last_commit")})
    if items or recent:
        paused = False
    else:
        paused = None if unknown_time else True   # cannot say "paused" when a commit time could not be read
    return {"in_progress": items, "branches": branches, "paused": paused}


def read_plans(root: Path) -> list[dict] | None:
    """Plan records; None when the project has no plans/ folder (missing), [] when the folder holds no plan."""
    root = Path(root)
    if not (root / "plans").is_dir():
        return None
    work_status = {str(w.get("id")): w.get("status") for w in read_works(root)}
    out = []
    for p in sorted(glob.glob(str(root / "plans" / "PL-*.md"))):
        path = Path(p)
        d = _fm(path)
        if not isinstance(d, dict):
            out.append({"id": path.stem, "unreadable": True})
            continue
        steps = [s for s in (d.get("steps") or []) if isinstance(s, dict)]
        live = [s for s in steps if s.get("status") != "dropped"]
        done = [s for s in live if s.get("status") == "done"]
        mismatch = []
        for s in done:
            for ref in s.get("refs") or []:
                if re.fullmatch(r"W-\d{3,}", str(ref)) and work_status.get(str(ref)) != "done":
                    mismatch.append({"step": s.get("id"), "work": str(ref), "work_status": work_status.get(str(ref), "missing")})
        dates = sorted(str(c.get("date")) for c in (d.get("changes") or []) if isinstance(c, dict) and c.get("date"))
        lc = ("log", "-1", "--format=%H|%cI", "--", f"plans/{path.name}")
        out_lc = _git(root, *lc)
        sha, _, cdate = out_lc.strip().partition("|") if out_lc and out_lc.strip() else ("", "", "")
        if sha:
            rl = ("rev-list", "--count", f"{sha}..HEAD")
            n = _git(root, *rl)
            since = int(n) if n and n.strip().isdigit() else _unm(_git_cmd(*rl))
        else:
            since = _unm(_git_cmd(*lc))
        out.append({"id": d.get("id", path.stem), "title": d.get("title"), "status": d.get("status"),
                    "steps": steps, "changes": [c for c in (d.get("changes") or []) if isinstance(c, dict)],
                    "done": len(done), "total": len(live),
                    "percent": round(100 * len(done) / len(live)) if live else None,
                    "mismatch": mismatch, "last_change": dates[-1] if dates else (cdate or _unm(_git_cmd(*lc))),
                    "commits_since_change": since})
    return out


def test_results_state(root: Path) -> str:
    """'missing' (no views/test-results.json), 'failed' (present but unreadable or not a suite list), 'empty'
    (readable, lists no suite) or 'data'."""
    p = Path(root) / "views" / "test-results.json"
    if not p.is_file():
        return "missing"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "failed"
    suites = data.get("suites") if isinstance(data, dict) else None
    if not isinstance(suites, list):
        return "failed"
    return "data" if suites else "empty"


def read_test_results(root: Path) -> list[dict] | None:
    """Suites from views/test-results.json (written by ci_local.py), each with stale = sha != HEAD or dirty.
    None when the file is absent or unreadable (test_results_state tells which)."""
    p = Path(root) / "views" / "test-results.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    suites = data.get("suites") if isinstance(data, dict) else None
    if not isinstance(suites, list):
        return None
    head = _git(Path(root), "rev-parse", "--short", "HEAD")
    head = head.strip() if head and head.strip() else None
    out = []
    for s in suites:
        if not isinstance(s, dict):
            continue
        sha, dirty = s.get("sha"), s.get("dirty")
        if head is None:
            stale, why = None, _unm("git rev-parse --short HEAD")
        elif not sha:
            stale, why = True, _unm("python tools/ci_local.py (the run did not record its git sha)")
        elif dirty is None:
            stale, why = True, _unm("python tools/ci_local.py (the run did not record whether files were unsaved)")
        elif sha != head:
            stale, why = True, f"ran at {sha}, HEAD is {head}"
        elif dirty:
            stale, why = True, "ran on uncommitted changes"
        else:
            stale, why = False, ""
        out.append({"suite": s.get("suite"), "sha": sha, "dirty": dirty if dirty is None else bool(dirty), "time": s.get("time"),
                    "passed": s.get("passed", 0), "failed": s.get("failed", 0), "skipped": s.get("skipped", 0),
                    "failures": [{"name": f.get("name"), "first_error_line": f.get("first_error_line")}
                                 for f in s.get("failures", []) if isinstance(f, dict)],
                    "stale": stale, "stale_reason": why})
    return out


TEST_RUN_RE = re.compile(r"\b(pytest|vitest|playwright)\b|\bnpm\s+(run\s+)?test\b|\bnpm\s+t\b")


INSTALL_RE = re.compile(r"\b(pip3?|npm|yarn|pnpm|apt(-get)?)\s+(-\S+\s+)*(install|ci|add)\b|-m\s+pip\b|\bplaywright\s+install\b")  # installing a runner is not running it


def read_unmeasured_suites(root: Path, results: list[dict] | None) -> list[dict]:
    """Workflow steps that run a test command and have no result in views/test-results.json:
    [{'suite', 'run', 'text': 'not measured: <run line>'}]. A step's suite name is `<job key>/<step name>`,
    the label ci_local.py gives it."""
    have = {s.get("suite") for s in results or []}
    out = []
    wf_dir = Path(root) / ".github" / "workflows"
    files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
    for f in files:
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, dict):
            continue
        for key, job in jobs.items():
            for st in (job.get("steps") or []) if isinstance(job, dict) else []:
                run = st.get("run") if isinstance(st, dict) else None
                if not isinstance(run, str):
                    continue
                lines = [ln.strip() for ln in run.splitlines() if TEST_RUN_RE.search(ln) and not INSTALL_RE.search(ln)]
                if not lines:
                    continue
                first = run.strip().splitlines()[0]
                label = f"{key}/{st.get('name') or first}"
                if label not in have:
                    out.append({"suite": label, "run": lines[0], "text": f"not measured: {lines[0]}"})
    return out


# ---- the first screen: this week, board ages, new requirements (REQ-052 AC-2) -------------------------

WEEK_DAYS = 7
FM_DELIM_RE = re.compile(r"^---[ \t]*$", re.M)
BOARD_COLUMNS = [("todo", "To do", ("todo",)), ("doing", "Doing", ("in_progress", "in_review")),
                 ("blocked", "Blocked", ("blocked",)), ("done", "Done", ("done",))]   # dropped is hidden
REQ_DONE = DONE   # ONE definition of done: the tile and the Requirements section both count this set
TITLE_IDS_RE = re.compile(r"\s*\((?:[^()]*\b(?:REQ|W|OD|PL)-\d+[^()]*)\)\s*$")


def plain_title(title) -> str:
    """The title without its trailing '(REQ-052 AC-2 ...)' id note: ids are small suffixes, never the headline."""
    t = str(title or "").strip()
    return TITLE_IDS_RE.sub("", t).strip() or t


def _fm_of_text(text) -> dict | None:
    if not isinstance(text, str):
        return None
    d = list(FM_DELIM_RE.finditer(text))
    if len(d) < 2 or d[0].start() != 0:
        return None
    try:
        data = yaml.safe_load(text[d[0].end():d[1].start()])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _since(now: datetime.datetime, days: int) -> str:
    return (now - datetime.timedelta(days=days)).isoformat(timespec="seconds")


def read_new_requirements(root: Path, now: datetime.datetime | None = None, days: int = WEEK_DAYS) -> int | str:
    """Requirement files first added to git in the last `days` days; 'unmeasured: <cmd>' when git cannot say."""
    now = now or datetime.datetime.now().astimezone()
    args = ("log", f"--since={_since(now, days)}", "--diff-filter=A", "--name-only", "--format=", "--",
            "spec/requirements")
    out = _git(Path(root), *args)
    if out is None:
        return _unm(_git_cmd(*args))
    return len({ln.strip() for ln in out.splitlines() if re.fullmatch(r"spec/requirements/REQ-\d+\.md", ln.strip())})


def read_work_ages(root: Path, now: datetime.datetime | None = None) -> dict[str, float | None]:
    """work id -> days since its record last changed (None when git cannot say)."""
    now = now or datetime.datetime.now().astimezone()
    out = _git(Path(root), "log", "--format=%x01%cI", "--name-only", "--", "work")
    ages: dict[str, float | None] = {}
    if out is None:
        return {str(w.get("id")): None for w in read_works(Path(root))}
    for block in out.split("\x01")[1:]:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        when = _parse_iso(lines[0]) if lines else None
        for f in lines[1:]:
            m = re.fullmatch(r"work/(W-\d+)\.md", f)
            if m and m.group(1) not in ages and when is not None:
                ages[m.group(1)] = round((now - when).total_seconds() / 86400, 1)
    for w in read_works(Path(root)):
        ages.setdefault(str(w.get("id")), None)
    return ages


def read_this_week(root: Path, prs: dict | None = None, now: datetime.datetime | None = None,
                   days: int = WEEK_DAYS) -> dict:
    """What happened in the last `days` days, from git history, grouped by day (newest day first):
    {'days': [{'date': 'YYYY-MM-DD', 'items': [plain sentence, ...]}], 'unmeasured': [text, ...]}.
    Items: a work item whose status became done; a requirement added or whose status changed; each plan `changes`
    entry whose own date is in the window ('was -> now, because why'; read from the plan file, never the commit
    history); a pull request merged (from `prs`, as read_prs returns it)."""
    root = Path(root)
    now = now or datetime.datetime.now().astimezone()
    by_day: dict[str, list[str]] = {}
    unm: list[str] = []
    args = ("log", f"--since={_since(now, days)}", "--format=%x01%H|%cI", "--name-only", "--", "work",
            "spec/requirements")
    out = _git(root, *args)
    if out is None:
        unm.append(_unm(_git_cmd(*args)))
        out = ""
    for block in out.split("\x01")[1:]:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        sha, _, when = lines[0].partition("|")
        day = when[:10]
        for f in lines[1:]:
            new = _fm_of_text(_git(root, "show", f"{sha}:{f}"))
            old = _fm_of_text(_git(root, "show", f"{sha}^:{f}"))
            if new is None:
                continue
            title = plain_title(new.get("title"))
            if f.startswith("work/") and new.get("status") == "done" and (old or {}).get("status") != "done":
                by_day.setdefault(day, []).append(f"Finished: {title} ({new.get('id', Path(f).stem)})")
            elif f.startswith("spec/requirements/"):
                rid = new.get("id", Path(f).stem)
                if old is None:
                    by_day.setdefault(day, []).append(f"Requirement added: {title} ({rid}), now {new.get('status')}")
                elif old.get("status") != new.get("status"):
                    by_day.setdefault(day, []).append(
                        f"Requirement moved from {old.get('status')} to {new.get('status')}: {title} ({rid})")
    cutoff = (now - datetime.timedelta(days=days)).date().isoformat()
    # plan changes come from each plan file's own `changes` entries (filtered by their `date`), never from the
    # commit history: a corrected entry must show its corrected words (W-039, REQ-053 AC-3)
    for pl in read_plans(root) or []:
        for c in [] if pl.get("unreadable") else pl["changes"]:
            d = str(c.get("date") or "")[:10]
            if d >= cutoff:
                by_day.setdefault(d, []).append(
                    f"Plan changed: {plain_title(pl.get('title'))} - was {c.get('was')} -> now {c.get('now')}, "
                    f"because {c.get('why')}")
    merged = (prs or {}).get("merged") if isinstance(prs, dict) else None
    if isinstance(merged, list):
        if (prs or {}).get("merged_capped"):
            unm.append(f"merged pull requests: at least {len(merged)} (list capped at {PR_LIMIT}); older ones may be missing")
        for pr in merged:
            when = str(pr.get("merged_at") or "")
            if when[:10] >= cutoff:
                by_day.setdefault(when[:10], []).append(f"Merged: {pr.get('title')} (#{pr.get('number')})")
    else:
        unm.append(merged if isinstance(merged, str) else _unm("gh pr list --state merged"))
    return {"days": [{"date": d, "items": by_day[d]} for d in sorted(by_day, reverse=True)], "unmeasured": unm}


# ---- owner decisions (REQ-012) ---------------------------------------------------------------------

def rollup_status(statuses: list[str]) -> str:
    """No citing requirement -> 'no requirement'; otherwise the least-advanced status (STATUS_ORDER). A status that
    is not in the order counts as the least advanced, and is shown as written."""
    if not statuses:
        return NO_REQUIREMENT
    statuses = [s or "unknown" for s in statuses]  # a requirement with no status is shown as unknown, never blank
    return min(statuses, key=lambda x: STATUS_ORDER.index(x) if x in STATUS_ORDER else -1)


def _cell(text: str) -> str:
    return text.replace("\\|", "|")


def _od_title(decision: str) -> str:
    m = re.match(r"\*\*(.+?)\*\*", decision)
    if m:
        return m.group(1).strip()
    first = re.split(r"(?<=[.;])\s+", decision, maxsplit=1)[0]
    return first if len(first) <= 120 else first[:117] + "..."


def read_decisions(root: Path) -> tuple[list[dict], list[str]]:
    """(decisions, problems). One dict per well-formed decision: Factory OD rows (docs/spec/decisions.md) and project
    records (spec/decisions/*.md), each with the ids of the requirements citing it (spec_dupes.cites) and the
    rolled-up status. An OD row that is not exactly 5 cells is never rendered (its cells would be shifted): it is
    returned as a problem line instead."""
    src = spec_text.Source(root)
    reqs = spec_text.requirement_records(src)
    recs = spec_text.od_records(src) + spec_text.adr_records(src)
    out, problems = [], []
    known = {r.id.upper() for r in reqs + recs}
    for rec in recs:
        if rec.path == spec_text.OD_LOG and rec.data.get("cells") != spec_text.OD_CELLS:
            problems.append(f"{rec.id}: {rec.data.get('cells')} cells, expected {spec_text.OD_CELLS} "
                            f"(line {rec.data.get('line')} of {spec_text.OD_LOG}; write a literal pipe as \\|)")
            continue
        if rec.path == spec_text.OD_LOG:
            cells = [_cell(c) for c in spec_text.od_cells(rec.raw)] + [""] * 5
            row = {"id": rec.id, "date": cells[1], "title": _od_title(cells[2]), "words": cells[3], "changes": cells[4]}
        else:
            d = rec.data
            row = {"id": rec.id, "date": str(d.get("date") or "—"), "title": str(d.get("title") or rec.id),
                   "words": str(d.get("owner_words") or "—"), "changes": str(d.get("changes") or "—")}
        citing = [r for r in reqs if spec_dupes.covers(r, rec)]  # deliberate only; mentions omitted
        citing.sort(key=lambda r: spec_dupes.id_number(r.id))
        row["cited"] = ", ".join(r.id for r in citing) or "—"
        row["status"] = rollup_status([str(r.data.get("status") or "unknown") for r in citing])
        text = spec_dupes.relations_text(rec)
        why = spec_dupes.exemption(spec_dupes.parse_relations(text, known, rec.id)[0]) if text else None
        if not citing and why is not None:  # REQ-013 AC-3: every exemption is shown with its reason
            row["status"] = f"{NO_REQUIREMENT} (exempt: {why})"
        out.append(row)
    out.sort(key=lambda r: (r["id"].rsplit("-", 1)[0], spec_dupes.id_number(r["id"])))
    return out, problems


# ---- computed health (REQ-014 AC-5) ----------------------------------------------------------------

def evidence_results(root: Path) -> dict[str, "trace_check.Result"]:
    """requirement id -> trace_check's result (stale / unpinned / hard failures). Requirements whose status demands
    no evidence (Delivered-before-trace, Superseded) are absent."""
    reqs, _ = trace_check.load_requirements(root)
    works, _ = trace_check.load_work_items(root)
    allowed = trace_check.load_unpinned_list(root)
    return {r.id: trace_check.check_requirement(root, r, works, allowed) for r in reqs
            if r.status not in trace_check.NO_EVIDENCE_STATUSES}


def pin_failing(root: Path, amends: list[str]) -> set[str]:
    """Requirement ids with a failing confirmed_against pin (spec_dupes: missing, stale, orphan or malformed pin, or
    the amends rule asking for a new one)."""
    src = spec_text.Source(root)
    failures, _ = spec_dupes.check_pins(spec_text.load_records(src))
    return {m.group(1) for m in map(PIN_LINE_RE.match, failures + list(amends)) if m}


def health(rid: str, results: dict, pins: set[str], works: list[dict], parked: set[str]) -> str:
    """First match wins: Changed - needs re-check (stale evidence, an unusable ac_fp, or a failing pin), Blocked (a
    work item delivering it is blocked or lists blockers), Parked (a parked issue's Relates-to names it), Unpinned
    evidence (any of its evidence lacks ac_fp), else OK."""
    res = results.get(rid)
    if (res is not None and (res.stale or res.failures)) or rid in pins:
        return H_CHANGED
    if any(w.get("status") == "blocked" or w.get("blockers") for w in works):
        return H_BLOCKED
    if rid in parked:
        return H_PARKED
    if res is not None and res.unpinned:
        return H_UNPINNED
    return H_OK


# ---- CI gates (AC-6) -------------------------------------------------------------------------------

def _step_executed(step: dict) -> bool:
    return (step.get("conclusion") or "") not in ("", "skipped")


def _job_matches(run_name: str, names: set[str]) -> bool:
    return any(run_name == n or run_name.startswith(n + " (") for n in names)


def _completed(run: dict) -> bool:
    """A run that has not finished says nothing about which steps ran."""
    if "status" in run and run.get("status") != "completed":
        return False
    return bool(run.get("conclusion"))


def classify_gates(root: Path, all_runs: list[dict] | None) -> dict:
    """Step-level gates. Each entry of 'gates' is (label, kind, workflow):
        (`<job> / <step>`, 'skipped-every-time')  a step skipped in every completed run where its job ran
        (`<job>`, 'skipped-every-time')           a job with no step detail that was skipped in every run
        (`<job>`, 'never-run')                    a workflow job with no runs
    A step that executed at least once is never listed. Steps are keyed by name plus occurrence within the
    job, so two steps with the same name are judged separately (the second is labelled `<name> (#2)`).
    Runs that have not completed are ignored."""
    if all_runs is None:
        return {"state": "unmeasured", "reason": "no runs file", "gates": []}
    runs = [r for r in all_runs if _completed(r)]
    not_completed = len(all_runs) - len(runs)
    if all_runs and not runs:
        return {"state": "unmeasured", "reason": "no completed runs in the window", "gates": []}
    wf_jobs = read_workflow_jobs(root)
    detailed = [r for r in runs if isinstance(r.get("jobs"), list)]
    if runs and not detailed:
        return {"state": "unmeasured", "reason": "runs carry no job detail", "gates": []}
    dates = sorted((r.get("createdAt") or "")[:10] for r in runs if r.get("createdAt"))
    window = (len(runs), dates[0] if dates else "", dates[-1] if dates else "")
    # (workflow, job) -> {"steps": {(step name, occurrence): [executed?]}, "jobs": [executed?] for jobs without steps}
    seen: dict[tuple[str, str], dict] = {(wf, disp): {"steps": {}, "jobs": []} for wf, disp, _n in wf_jobs}
    for r in detailed:
        wf = r.get("workflowName") or r.get("name") or ""
        for job in r["jobs"]:
            jname = job.get("name") or ""
            key = next(((w, d) for w, d, names in wf_jobs if w == wf and _job_matches(jname, names)), (wf, jname))
            rec = seen.setdefault(key, {"steps": {}, "jobs": []})
            steps = job.get("steps") or []
            if steps:
                occurrence: dict[str, int] = {}
                for s in steps:
                    nm = s.get("name") or ""
                    occurrence[nm] = occurrence.get(nm, 0) + 1
                    rec["steps"].setdefault((nm, occurrence[nm]), []).append(_step_executed(s))
            else:
                rec["jobs"].append((job.get("conclusion") or "") not in ("", "skipped"))
    wf_no_detail = {(r.get("workflowName") or r.get("name") or "") for r in runs if not isinstance(r.get("jobs"), list)}
    gates = []
    for (wf, name), rec in sorted(seen.items(), key=lambda kv: kv[0][1]):
        if not rec["steps"] and not rec["jobs"]:
            if wf not in wf_no_detail:
                gates.append((name, "never-run", wf))
            continue
        for (step, nth), ran in rec["steps"].items():
            if not any(ran):
                label = step if nth == 1 else f"{step} (#{nth})"
                gates.append((f"{name} / {label}", "skipped-every-time", wf))
        if rec["jobs"] and not any(rec["jobs"]):
            gates.append((name, "skipped-every-time", wf))
    gates.sort(key=lambda g: g[0])
    return {"state": "measured", "gates": gates, "window": window, "no_detail": len(runs) - len(detailed),
            "not_completed": not_completed}


# ---- issues and findings (AC-4) --------------------------------------------------------------------

def relates_to(body: str | None) -> str:
    for line in (body or "").splitlines():
        m = RELATES_LINE_RE.match(line.strip())
        if not m:
            continue
        value = m.group(1)
        if RELATES_REQS_RE.match(value):
            return ", ".join(x.strip() for x in value.split(","))
        s = RELATES_SECTION_RE.match(value)
        if s:
            return f"section {s.group(1).strip()}"
    return UNMAPPED


def issue_status(issue: dict) -> str:
    if str(issue.get("state", "")).upper() == "CLOSED":
        return "closed"
    names = {(lb.get("name") if isinstance(lb, dict) else str(lb)) for lb in issue.get("labels") or []}
    return "parked" if "parked" in names else "deferred" if "deferred" in names else "open"


# ---- kit adoption (REQ-017 AC-2; OD-76, OD-77: other projects are read, never written) ------------------

VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _ver(text) -> tuple[int, ...] | None:
    t = str(text or "").strip()
    return tuple(int(x) for x in t.split(".")) if VERSION_RE.match(t) else None


def _read_version(path: Path) -> tuple[str | None, str | None]:
    """(version text, None) or (None, why it is unmeasured). Read only."""
    try:
        text = path.read_text(encoding="utf-8").strip().splitlines()[0].strip() if path.is_file() else None
    except (OSError, IndexError, UnicodeDecodeError):
        text = None
    if text is None:
        return None, f"unmeasured: {path.as_posix()}"
    if _ver(text) is None:
        return None, f"unmeasured: {path.as_posix()} holds '{text}', which is not a version"
    return text, None


def read_kit_adoption(root: Path) -> dict:
    """Per kit project: its kit version and the released requirements it lacks.
    In the Factory (factory/kit-projects.json exists) every listed project's KIT_VERSION is read and compared with the
    template's; anywhere else only the project's own KIT_VERSION is shown."""
    root = Path(root)
    listing = root / "factory" / "kit-projects.json"
    rels = []
    for f_ in sorted(glob.glob(str(root / "releases" / "R-*.md"))):
        d_ = _fm(Path(f_)) or {}
        v_ = _ver(d_.get("version"))
        if v_ is not None:
            rels.append((v_, str(d_.get("id", Path(f_).stem)),
                         [str(x) for x in d_.get("items") or [] if str(x).startswith("REQ-")]))
    if not listing.is_file():
        for cand in (root / "KIT_VERSION", root / "kit" / "KIT_VERSION"):
            if cand.is_file():
                v, why = _read_version(cand)
                return {"mode": "project", "projects": [], "own": v, "own_why": why}
        return {"mode": "project", "projects": [], "own": None,
                "own_why": f"unmeasured: {(root / 'KIT_VERSION').as_posix()}"}
    tmpl, tmpl_why = _read_version(root / "templates" / "project-os" / "KIT_VERSION")
    try:
        listed = json.loads(listing.read_text(encoding="utf-8"))
        assert isinstance(listed, list)
    except (OSError, ValueError, AssertionError):
        return {"mode": "factory", "template": tmpl, "projects": [],
                "list_why": f"unmeasured: {listing.as_posix()} is not a list"}
    out = []
    for e in listed:
        if not isinstance(e, dict) or not e.get("name") or not e.get("path"):
            continue
        v, why = _read_version(Path(str(e["path"])) / "KIT_VERSION")
        rec = {"name": str(e["name"]), "path": str(e["path"]), "version": v, "why": why, "lacks": [], "behind": 0}
        if v is not None:
            pv = _ver(v)
            newer = [r for r in rels if r[0] > pv]
            rec["behind"] = len(newer)
            seen: list[str] = []
            for _, _, items in newer:
                for i in items:
                    if i not in seen:
                        seen.append(i)
            rec["lacks"] = seen
        out.append(rec)
    return {"mode": "factory", "template": tmpl, "template_why": tmpl_why, "projects": out}


def _kit_tech(why) -> str:
    """The path text of an unmeasured value: only inside a closed Technical detail (design spec section 9)."""
    return f'<details class="more"><summary>Technical detail</summary><p class="codebox">{esc(why)}</p></details>'


def kit_adoption_html(k: dict, titles: dict[str, str]) -> tuple[str, str]:
    """(card html, one-line count)."""
    def lacks_list(ids):
        return ('<details class="more"><summary>Show the requirements it lacks</summary><ul>'
                + "".join(f'<li>{esc(titles.get(i) or i)} <span class="id">{esc(i)}</span></li>' for i in ids)
                + "</ul></details>")
    if k["mode"] == "project":
        if k.get("own"):
            return (f'<p>This project is on kit {esc(k["own"])}.</p><p class="muted">The Factory holds the latest kit version; '
                    f'this project cannot see it, so it cannot say whether it is behind.</p>', f"kit {k['own']}")
        return (f'<p class="muted"><span class="chip idle">Not measured yet</span> The kit version of this project cannot be read, so it is not known whether it is behind. Add the kit version file and it appears here.</p>' + _kit_tech(k.get("own_why")), "unmeasured")
    parts = []
    if k.get("template"):
        parts.append(f'<p>The Factory template is on kit {esc(k["template"])}.</p>')
    else:
        parts.append('<p class="muted"><span class="chip idle">Not measured yet</span> the Factory template kit version cannot be read, so no project can be compared with it. Restore the template version file and it appears here.</p>' + _kit_tech(k.get("template_why")))
    if k.get("list_why"):
        parts.append('<p class="muted"><span class="chip idle">Not measured yet</span> the list of kit projects cannot be read, so no project is shown. Restore the list file and the projects appear here.</p>' + _kit_tech(k["list_why"]))
    items = []
    for p in k["projects"]:
        if p["version"] is None:
            items.append(f'<li><b>{esc(p["name"])}</b>: <span class="chip idle">Not measured yet</span> kit version not readable, so it is not known whether it is behind. Add its kit version file and it appears here.{_kit_tech(p["why"])}</li>')
        elif p["lacks"]:
            rel = f'{p["behind"]} release{"" if p["behind"] == 1 else "s"} behind'
            items.append(f'<li><b>{esc(p["name"])}</b>: kit {esc(p["version"])}, {rel} — lacks {len(p["lacks"])} '
                         f'requirement{"" if len(p["lacks"]) == 1 else "s"}{lacks_list(p["lacks"])}</li>')
        else:
            items.append(f'<li><b>{esc(p["name"])}</b>: kit {esc(p["version"])}, up to date</li>')
    parts.append(ul(items, "No kit projects are listed."))
    behind = sum(1 for p in k["projects"] if p["version"] is not None and p["lacks"])
    return "".join(parts), f'{len(k["projects"])} projects · {behind} behind'


# ---- html helpers ----------------------------------------------------------------------------------

def unmeasured(cmd: str, what: str = "") -> str:
    """A value that could not be measured: a plain sentence, and the command that measures it in a collapsed block."""
    return (f'<div class="unm"><p class="muted"><span class="chip idle">Not measured yet</span> {esc(what)}</p>'
            + technical(f'<p class="codebox">How to measure: unmeasured: <code>{esc(cmd)}</code></p>') + "</div>")


def ul(items: list[str], empty: str) -> str:
    return "<ul>" + "".join(items) + "</ul>" if items else f'<p class="muted">{esc(empty)}</p>'


NUM_KEYS = {"acs", "checks", "passed", "failed", "unsaved", "not_pushed", "count", "ver", "pf"}
ROW_CAP = 20


def table(cols: list[tuple[str, str]], data: list[dict], tid: str, prio: dict | None = None,
          cap: int | None = None, suffix: tuple[str, str] | None = ("title", "id"), phone_collapse: bool = False,
          raw: frozenset = frozenset(), phone_rows: int | None = None) -> str:
    """A sortable table. `prio` maps a column key to p1 (always) / p2 (from 768 px) / p3 (only after 'Show all
    columns'); a key not named is p1. `cap` shows that many rows, then a 'Show all N' button. Keys in `raw` hold
    HTML built here (already escaped); every other cell is escaped."""
    prio = {"id": "p3", **(prio or {})} if suffix else (prio or {})

    def cls(k: str) -> str:
        return " ".join(c for c in (prio.get(k, "p1"), "num" if k in NUM_KEYS else "", "idc" if k == "id" and not suffix else "") if c)
    def head(lbl: str) -> str:      # "Long label|Short": the short one replaces the long one on a phone
        long_, _, short_ = lbl.partition("|")
        return (f'<span class="hl">{esc(long_)}</span><span class="hs">{esc(short_)}</span>' if short_ else esc(long_))
    th = "".join(f'<th scope="col" class="{cls(k)} srt"><button type="button" data-k="{k}">{head(lbl)}</button></th>'
                 for k, lbl in cols)
    def trtag(i: int) -> str:
        return ('<tr class="extra">' if cap and i >= cap else "<tr>")
    tr = "".join(trtag(i)
                 + "".join(f'<td data-k="{k}" class="{cls(k)}">{d[k] if k in raw else esc(d[k])}'
                           + (f' <span class="id">{esc(d[suffix[1]])}</span>' if suffix and k == suffix[0] and suffix[1] in d else "")
                           + "</td>" for k, _ in cols) + "</tr>"
                 for i, d in enumerate(data))
    capped = bool(cap and len(data) > cap)
    pcap = bool(phone_rows and len(data) > phone_rows)
    more = ((f'<span class="pc-count">{len(data)} rows, collapsed on a phone.</span>' if phone_collapse else "")
            + f'<button type="button" class="tog{"" if capped else " phone-only"}" data-show-all="{tid}">Show all {len(data)}</button>'
            if capped or pcap else "")
    cols_btn = (f'<button type="button" class="tog" data-all-cols="{tid}">Show all columns</button>'
                if any(prio.get(k) == "p3" for k, _ in cols) else "")
    klass = (["capped"] if capped else []) + (["pc"] if capped and phone_collapse else []) + (["pcap"] if pcap else [])
    return (f'<div class="tw"><table id="{tid}"' + (f' class="{" ".join(klass)}"' if klass else "")
            + f'><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div><p class="tbtns">{more}{cols_btn}</p>')


def filters(qid: str, label: str, selects: list[tuple[str, str, list[str]]], primary: int | None = None) -> str:
    """Search box plus selects; with `primary` only the first N selects show, the rest sit in 'More filters'."""
    def one(sid, lbl, opts):
        return (f'<select id="{sid}" aria-label="{esc(lbl)}"><option value="">{esc(lbl)}</option>'
                + "".join(f"<option>{esc(o)}</option>" for o in opts) + "</select>")
    shown = selects if primary is None else selects[:primary]
    rest = [] if primary is None else selects[primary:]
    more = ('<details class="more"><summary>More filters</summary><div class="flt">'
            + "".join(one(*x) for x in rest) + "</div></details>") if rest else ""
    return (f'<div class="flt"><input id="{qid}" type="search" placeholder="{esc(label)}" '
            f'aria-label="{esc(label)}">{"".join(one(*x) for x in shown)}</div>{more}')


def sec_id(title: str) -> str:
    return re.sub(r"[^a-z]+", "-", title.lower()).strip("-")


def sec(title: str, body: str, count: str, open_: bool = False) -> str:
    """A collapsible block (a native <details>): Needs you, Engineering detail and its sub-blocks."""
    return (f'<details class="sec" id="sec-{sec_id(title)}"' + (" open" if open_ else "")
            + f'><summary><span>{esc(title)}</span><span class="ct">{esc(count)}</span></summary>'
            f'<div class="bd">{body}</div></details>')


def panel(title: str, body: str, count: str) -> str:
    """A flat card with a heading and a one-line summary at its right (design spec 3.2)."""
    return (f'<section class="panel sec" id="sec-{sec_id(title)}"><div class="sh"><h2>{esc(title)}</h2>'
            f'<span class="ct">{esc(count)}</span></div><div class="bd">{body}</div></section>')


def tile(key: str, value: str, label: str) -> str:
    return f'<div class="tile" data-tile="{key}"><b>{esc(value)}</b><span>{esc(label)}</span></div>'


# ---- first-screen blocks (REQ-052 AC-2..AC-5): pure functions of the readers' output ------------------

TIER_RE = re.compile(r"\s*\((?:[^()]*,\s*)?Tier [A-C]\)")
LEAD_IDS_RE = re.compile(r"^(?:[A-Z]{1,3}-\d+(?:\.\.(?:[A-Z]{1,3}-)?\d+)?[\s,:;]*)+")
ANY_ID_RE = re.compile(r"\b[A-Z]{1,3}-\d+(?:\.\.(?:[A-Z]{1,3}-)?\d+)?\b|#\d+")
CUT_RE = re.compile(r"\s+[—–-]\s+|:\s+|\s+×\s+|\s+\(")
TRAIL_NOTE_RE = re.compile(r"(?:\s*\([^()]*\))+\s*$")
# what a non-technical reader must not meet on the first screen: files, commands, versions, design-spec section 4 jargon
BAD_PLAIN_RE = re.compile(
    r"[\w.-]+\.(?:md|py|json|ya?ml|ps1|sh|js|html|txt)\b|\b[\w.-]+/[\w.-]+|\b(?:python|pytest|npm|gh|git)\b|"
    r"\b\d+\.\d+\.\d+\b|\b(?:sha|worktrees?|tiers?|layers?|unguarded|unmapped|superseded|gates?)\b|"
    r"acceptance[- ]criteri(?:a|on)|delivered-before-trace", re.I)
BAD_CASE_RE = re.compile(r"\b(?:CI|PRs?|ACs?)\b")
WORD_MAP = [(re.compile(r"\bCI\b"), "GitHub checks"), (re.compile(r"\bPRs\b"), "pull requests"),
            (re.compile(r"\bPR\b"), "pull request"), (re.compile(r"\bACs\b"), "acceptance checks"),
            (re.compile(r"\bsha\b", re.I), "version"), (re.compile(r"\bworktrees?\b", re.I), "working copy"),
            (re.compile(r"\bTier\b"), "Review level"), (re.compile(r"\bLayer\b"), "Kind"),
            (re.compile(r"\bunguarded\b", re.I), "has no automatic check yet"),
            (re.compile(r"\bunmapped\b", re.I), "not linked to a requirement"),
            (re.compile(r"\bsuperseded\b", re.I), "replaced"), (re.compile(r"acceptance[- ]criteri(?:a|on)", re.I), "acceptance checks")]
# id -> {"title", "display_title", "related": [ids]}; filled by render() from the repo's own records
TITLE_CTX: dict = {}


def map_words(t: str) -> str:
    for rx, word in WORD_MAP:
        t = rx.sub(word, t)
    return t


_PATH_RE = re.compile(r"(?<![\w/.-])[\w.-]+(?:/[\w.-]+)+")
_FILE_RE = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:md|py|json|ya?ml|ps1|sh|js|html|txt)\b")
_CMD_RE = re.compile(r"\b(?:python3?|pytest|npm|gh|git)\b(?:\s+-\S+)*(?:\s+[a-z][\w-]*)?", re.I)
_VERSION_RE = re.compile(r"\bv?\d+\.\d+\.\d+\b")
_LOWER_MAP = [(re.compile(r"\btiers?\b", re.I), "review level"), (re.compile(r"\blayers?\b", re.I), "kind"),
              (re.compile(r"\bgates?\b", re.I), "check")]


def plain_words(text) -> str:
    """THE plain-words function (OD-117: record wording never fails the build). Every record text that reaches the first
    screen ends here: ids dropped, any file name, path, command or version replaced by a plain word, section 4 words
    mapped, leftover jargon words reworded, so no wording in a record can put jargon on the page."""
    t = ANY_ID_RE.sub("", str(text or ""))
    t = _PATH_RE.sub(lambda m: "a file" if _FILE_RE.fullmatch(m.group(0).rsplit("/", 1)[-1]) else "a folder", t)
    t = _FILE_RE.sub("a file", t)
    t = _CMD_RE.sub("a command", t)
    t = _VERSION_RE.sub("a version", t)
    t = map_words(t)
    for rx, word in _LOWER_MAP:
        t = rx.sub(lambda m, w=word: w + ("s" if m.group(0).lower().endswith("s") else ""), t)
    t = re.sub(r"\(\s*\)", "", t)
    return re.sub(r"\s+", " ", re.sub(r"\s+([,;:.])", r"\1", t)).strip(" ,;:")


def has_jargon(t: str) -> bool:
    return bool(BAD_PLAIN_RE.search(t) or BAD_CASE_RE.search(t) or ANY_ID_RE.search(t))


def title_rule(title) -> str:
    """The headline of a record title: no Tier token, no trailing note, no leading id list, cut at the first
    ': ' / ' — ' / ' - ' / ' (' / ' × ', ids dropped, first letter capital."""
    t = TIER_RE.sub("", str(title or "")).strip()
    t = TRAIL_NOTE_RE.sub("", t)
    t = LEAD_IDS_RE.sub("", t)
    m = CUT_RE.search(t)
    if m:
        t = t[:m.start()]
    t = re.sub(r"\s+", " ", ANY_ID_RE.sub("", t)).strip(" ,;:-—–")
    return t[:1].upper() + t[1:]


def _title_ok(t: str) -> bool:
    return len(t.split()) >= 2 and not has_jargon(map_words(t))


def display_title(title, ids=()) -> tuple[str, str]:
    """(plain headline, id for the small grey suffix). THE choke point for every first-screen title.
    Chain: (a) a record's `display_title:` frontmatter; (b) title_rule; (c) when that still holds jargon or is under
    two words, the linked records' titles (the ids given, then the ids named in the title, then each one's requirements)
    through the same rule; (d) the design spec's section 4 word map."""
    ctx = TITLE_CTX
    ids = [i for i in ids if i]
    lead = LEAD_IDS_RE.match(str(title or ""))
    lead_id = re.match(r"[A-Z]{1,3}-\d+", lead.group(0)).group(0) if lead else ""
    suffix = ids[0] if ids else lead_id
    if ids and ctx.get(ids[0], {}).get("display_title"):
        return plain_words(ctx[ids[0]]["display_title"]), suffix
    t0 = title_rule(title)
    if _title_ok(t0):
        return plain_words(t0), suffix
    order: list[str] = []
    for i in ids + [x for x in re.findall(r"\b[A-Z]{1,3}-\d+\b", str(title or ""))]:
        for j in [i] + list((ctx.get(i) or {}).get("related") or []):
            if j in ctx and j not in order:
                order.append(j)
    first = ""
    for rid in order:
        rec = ctx[rid]
        cand = str(rec.get("display_title") or "") or title_rule(rec.get("title"))
        first = first or cand
        if _title_ok(cand):
            return plain_words(cand), suffix
    return plain_words(t0 or first or str(title or "")), suffix


def show_title(title, ids=()) -> tuple[str, str]:
    return display_title(title, ids)


def clean_prose(text) -> str:
    """Free prose (plan-change Was/Now/Because): through the one plain-words function."""
    return plain_words(text)


def checks_verified(res, n_acs: int) -> str:
    """'n of m' acceptance criteria whose evidence is independently verified (fresh, or unpinned-but-passing);
    stale evidence does not count. No criteria -> 'no criteria'; a status that needs no evidence -> said in words."""
    if not n_acs:
        return "no criteria"
    if res is None:
        return "evidence not required at this status"
    return f"{len(res.fresh) + len(res.unpinned)} of {n_acs}"


NOW_RE = re.compile(r"^Working on: (.*?)(?: \((W-\d+)\))? · (?:step (\S+): (.*?)|no plan step) · last activity (.*)$", re.S)
MOVING_RE = re.compile(r"^(.*?) \(([A-Z]+-\d+)\) — unchanged for (\d+) days$", re.S)


def short_title(t: str, n: int = 80) -> tuple[str, str]:
    """(shown text, title attribute): about 80 characters at a word end with an ellipsis; the full text in the attribute."""
    if len(t) <= n:
        return t, ""
    cut = t[:n].rsplit(" ", 1)[0].rstrip(" ,;:-—–") or t[:n]
    return cut + "…", t


def _ttl_span(t: str) -> str:
    shown, full = short_title(t)
    return f'<span class="ttl"' + (f' title="{esc(full)}"' if full else "") + f'>{esc(shown)}</span>'


def now_line_html(state: str, text: str) -> str:
    """'Working on' as a short title, a small grey id, and a grey detail line (plan step only when there is one)."""
    m = NOW_RE.match(text)
    if state != "working" or not m:
        return f'<p id="now" data-state="{state}"><span class="dot"></span><span>{esc(plain_words(text))}</span></p>'
    title, wid, sid, stext, ago = m.groups()
    if not wid:      # an unmapped branch name is a Development detail, never a first-screen title
        title = "Work in a working copy"
    ttl, pre = show_title(title, [wid])
    step_text = show_title(stext, TITLE_CTX.get("_steps", {}).get(sid, []))[0] if sid else ""
    detail = f"Last activity {ago}" + (f" · plan step {sid}: {step_text}" if sid else "")
    return (f'<p id="now" data-state="working"><span class="dot"></span><span>{_ttl_span(ttl)}'
            + (f' <span class="id">{esc(wid or pre)}</span>' if (wid or pre) else "")
            + f'<span class="sl">{esc(detail)}</span></span></p>')


def not_moving_html(text: str, cap: int = 3) -> str:
    items = [x for x in text.removeprefix("Not moving: ").split("; ") if x]
    out = []
    for it in items[:cap]:
        m = MOVING_RE.match(it)
        if m:
            ttl, ident, days = m.groups()
            out.append(f'{_ttl_span(show_title(ttl, [ident])[0])} <span class="id">{esc(ident)}</span>'
                       f'<span class="sl">Not moving · No change for {esc(days)} days</span>')
        else:
            out.append(f'<span class="ttl">{esc(plain_words(it))}</span><span class="sl">Not moving</span>')
    more = f'<span class="sl">+ {len(items) - cap} more</span>' if len(items) > cap else ""
    return ('<p id="not-moving"><span class="dot"></span><span>'
            + '<br>'.join(out) + more + "</span></p>")


def blk(title: str, body: str, cls: str = "") -> str:
    klass = f"blk panel {cls}".strip()
    return f'<section class="{klass}" id="blk-{sec_id(title)}"><h2>{esc(title)}</h2>{body}</section>'


def ago_words(days) -> str:
    if not isinstance(days, (int, float)):
        return "unknown"
    h = max(days, 0) * 24
    if h < 1:
        return "less than an hour ago"
    return f"{int(h)} h ago" if h < 48 else f"{int(days)} days ago"


def chip(text: str, kind: str = "idle") -> str:
    """A status chip: always words, colour is never the only signal (design spec 1)."""
    return f'<span class="chip {kind}">{esc(text)}</span>'


def sm_table(cols: list[tuple[str, str]], data: list[dict], prio: dict | None = None, raw: frozenset = frozenset()) -> str:
    """A small read-only table; p1/p2/p3 column priorities as in table(). Keys in `raw` hold HTML built here, already
    escaped; every other cell is escaped."""
    prio = prio or {}

    def cls(k: str) -> str:
        return " ".join(c for c in (prio.get(k, "p1"), "num" if k in NUM_KEYS else "") if c)
    th = "".join(f'<th scope="col" class="{cls(k)}">{esc(lbl)}</th>' for k, lbl in cols)
    tr = "".join("<tr>" + "".join(f'<td class="{cls(k)}">{d.get(k, "") if k in raw else esc(d.get(k, ""))}</td>'
                                  for k, _ in cols) + "</tr>" for d in data)
    cols_btn = ('<p class="tbtns"><button type="button" class="tog" data-all-cols="1">Show all columns</button></p>'
                if any(prio.get(k) == "p3" for k, _ in cols) else "")
    return f'<div class="tw sm"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>{cols_btn}'


def is_unm(v) -> bool:
    return isinstance(v, str) and v.startswith("unmeasured")


def unm_html(text: str, what: str = "") -> str:
    """A value that is 'unmeasured: <command>' as a visible chip plus the command."""
    return unmeasured(str(text).removeprefix("unmeasured: "), what)


def ring(pct: int, size: int = 56) -> str:
    """Progress ring (design spec 1): 6 px stroke, track accent-soft, arc accent, starts at 12 o'clock, percent inside."""
    r = (size - 6) / 2
    c = 2 * math.pi * r
    mid = size / 2
    pct = max(0, min(100, int(pct)))
    return (f'<svg class="ring" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" '
            f'aria-label="{pct} percent done"><circle class="trk" cx="{mid}" cy="{mid}" r="{r}" fill="none" stroke-width="6"/>'
            f'<circle class="arc" cx="{mid}" cy="{mid}" r="{r}" fill="none" stroke-width="6" stroke-linecap="round" '
            f'stroke-dasharray="{c * pct / 100:.1f} {c:.1f}" transform="rotate(-90 {mid} {mid})"/>'
            f'<text x="{mid}" y="{mid}" text-anchor="middle" dominant-baseline="central">{pct}%</text></svg>')


def big_tile(key: str, title: str, headline: str, details: list[str], pct: int | None = None, hcls: str = "",
             raw_sub: str = "") -> str:
    sub = raw_sub or "<br>".join(esc(d) for d in details)
    return (f'<div class="tile big" data-tile="{key}"><h3>{esc(title)}</h3><span class="tv">'
            f'{ring(pct) if pct is not None else ""}<b class="{hcls}">{esc(headline)}</b></span>'
            f'<span class="sub">{sub}</span></div>')


def requirements_tile(statuses: list[str], new_this_week) -> str:
    live = [s or "unknown" for s in statuses if s != "Superseded"]
    if not live:
        return big_tile("requirements", "Requirements", "None yet", ["No requirements recorded"])
    done = sum(1 for s in live if s in REQ_DONE)
    other = sorted({s for s in live if s not in STATUS_ORDER})
    n_other = sum(1 for s in live if s not in STATUS_ORDER)
    pending = len(live) - done - n_other
    plus = "new this week: Not measured yet" if is_unm(new_this_week) else f"{new_this_week} new this week"
    details = [f"{pending} pending · {plus}"]
    if other:
        details.append(f"other: {n_other} with an unknown status ({', '.join(other)})")
    return big_tile("requirements", "Requirements", f"{done} of {len(live)} done", details,
                    pct=round(100 * done / len(live)))


def plan_tile(plans: list[dict] | None) -> str:
    if not plans:
        return big_tile("plan", "Plan", "No plan records", ["This project has no plan records yet"])
    active = [p for p in plans if not p.get("unreadable") and p.get("status") == "active"]
    total = sum(p["total"] for p in active)
    if not active:
        return big_tile("plan", "Plan", "No active plan", ["No plan is marked active"])
    if not total:
        return big_tile("plan", "Plan", "No steps yet", [show_title(active[0]["title"], [active[0]["id"]])[0]])
    done = sum(p["done"] for p in active)
    details = [show_title(active[0]["title"], [active[0]["id"]])[0]]
    if len(active) > 1:
        details.append(f"+{len(active) - 1} more active plan{'s' if len(active) > 2 else ''}")
    return big_tile("plan", "Plan", f"{done} of {total} steps", details, pct=round(100 * done / total))


def suite_words(s: dict) -> str:
    txt = f"{s.get('suite')}: {s.get('passed', 0)} passed · {s.get('failed', 0)} failed"
    if s.get("stale") is True:
        txt += f" (out of date: {s.get('stale_reason')})"
    elif s.get("stale") is None:
        txt += f" (freshness {s.get('stale_reason')})"
    return txt


def stale_note(s: dict) -> tuple[str, str] | None:
    """(chip text, chip kind) for a suite whose result is not current, or None when it is current."""
    why = str(s.get("stale_reason") or "")
    if s.get("stale") is False:
        return None
    if s.get("stale") is True and why.startswith("ran at "):
        m = re.match(r"ran at (\S+), HEAD is", why)
        return (f"Ran on an older version ({m.group(1)})" if m else "Ran on an older version"), "warn"
    if s.get("stale") is True and why.startswith("ran on uncommitted"):
        return "Ran with unsaved changes", "warn"
    return "Freshness not measured yet", "idle"


def github_verdict(runs, head) -> dict | None:
    """What the latest run of each workflow says, or None when there is no usable GitHub result:
    {'state': passed|failed|running, 'n': jobs that passed, 'date': newest run date, 'older': True/False/None}."""
    if not isinstance(runs, list) or not runs:
        return None
    seen, jobs, picked = set(), [], []
    for r in runs:
        name = r.get("workflowName") or r.get("name")
        if name in seen:
            continue
        seen.add(name)
        picked.append(r)
        jobs += [str(j.get("conclusion") or j.get("status") or "") for j in r.get("jobs") or []]
    if not jobs:
        return None
    if "failure" in jobs:
        state = "failed"
    elif any(c in ("in_progress", "queued", "pending", "") for c in jobs):
        state = "running"
    elif "success" in jobs and all(c in ("success", "skipped") for c in jobs):
        state = "passed"
    else:
        return None
    latest = max(picked, key=lambda r: str(r.get("createdAt") or ""))
    sha = str(latest.get("headSha") or "")
    older = None if not (sha and head) else not str(head).startswith(sha[:7])
    d = _parse_iso(latest.get("createdAt"))
    return {"state": state, "n": jobs.count("success"), "date": f"{d.day} {d:%b}" if d else "", "older": older,
            "failed": jobs.count("failure"), "total": len(jobs),
            "running": sum(1 for c in jobs if c in ("in_progress", "queued", "pending", "")),
            "ran": jobs.count("success") + jobs.count("failure")}


def tests_tile(results: list[dict] | None, missing: list[dict], runs=None, head=None) -> str:
    """Neutral dark headline; the verdict is a small soft chip with a word in it (one strong colour only: the accent)."""
    gh = github_verdict(runs, head) if results is None else None
    if gh:
        tail = "not run on this computer"
        if gh["older"]:       # the verdict is for an older commit: say when it was last checked, in plain words
            tail = f"Last checked {gh['date']}, not on the latest code"
        if gh["state"] == "passed":
            return big_tile("tests", "Tests", "Passed on GitHub", [], raw_sub=chip("Passed", "ok") + "<br>"
                            + esc(f"{gh['n']} GitHub check{'' if gh['n'] == 1 else 's'}, {gh['date']} · {tail}"))
        if gh["state"] == "failed":
            return big_tile("tests", "Tests", "Failed on GitHub", [], raw_sub=chip("Failed", "bad") + "<br>"
                            + esc(f"{gh['failed']} of {gh['total']} GitHub checks failed, {gh['date']} · {tail}"))
        return big_tile("tests", "Tests", "Running on GitHub", [], raw_sub=chip("Running", "idle") + "<br>"
                        + esc(f"Not finished · {tail}"))
    if results is None:
        n = len(missing)
        return big_tile("tests", "Tests", "Not run yet",
                        [f"{n} test suite{'s' if n != 1 else ''} {'have' if n != 1 else 'has'} no result for this version"
                         if n else "No test results recorded for this version"])
    passed = sum(int(s.get("passed") or 0) for s in results)
    failed = sum(int(s.get("failed") or 0) for s in results)
    notes = []
    old = sum(1 for s in results if s.get("stale") is True and str(s.get("stale_reason")).startswith("ran at "))
    dirty = sum(1 for s in results if s.get("stale") is True and str(s.get("stale_reason")).startswith("ran on uncommitted"))
    unk = sum(1 for s in results if s.get("stale") is None)
    if old:
        notes.append("Ran on an older version" + (f" ({old} suites)" if old > 1 else ""))
    if dirty:
        notes.append("Ran with unsaved changes" + (f" ({dirty} suites)" if dirty > 1 else ""))
    if unk and unk == len(results):       # only when EVERY suite is unmeasured
        notes.append("Freshness not measured yet")
    if missing:
        notes.append(f"{len(missing)} suite{'s' if len(missing) != 1 else ''} not run yet")
    sub = "<br>".join(esc(n) for n in notes)
    if failed:
        sub = chip(f"{failed} failed", "bad") + ("<br>" + sub if sub else "")
    return big_tile("tests", "Tests", f"{passed} passed", [], raw_sub=sub)


def _line(text: str, nonzero: bool = False) -> str:
    """One short sentence of the Code tile; a small amber dot (never a big amber number) marks a non-zero count."""
    return f'<span class="ln">{"<i class=dotw></i>" if nonzero else ""}{esc(text)}</span>'


def code_tile(code_state: dict, prs: dict | None) -> str:
    wts = code_state.get("worktrees")
    open_prs = (prs or {}).get("open") if isinstance(prs, dict) else None
    if isinstance(open_prs, list):
        n = len(open_prs)
        wait = _line((f"At least {n} waiting to merge (list capped)" if prs.get("open_capped") else f"{n} waiting to merge"), n > 0)
    else:
        wait = _line("Waiting to merge: not measured yet")
    if not isinstance(wts, list):
        return big_tile("code", "Code", "", [], raw_sub=_line("Unsaved files: not measured yet")
                        + _line("Unuploaded commits: not measured yet") + wait)
    unsaved = [w["unsaved"]["count"] if isinstance(w.get("unsaved"), dict) else None for w in wts]
    pushed = [w.get("not_pushed") for w in wts]
    n_up = sum(p for p in pushed if isinstance(p, int))
    never = sum(1 for p in pushed if p == "never pushed")
    bad = sum(1 for p in pushed if is_unm(p))
    if any(u is None for u in unsaved):
        saved = _line("Unsaved files: not measured yet")
    else:
        k = sum(unsaved)
        saved = _line(f"{k} file{'' if k == 1 else 's'} not saved", k > 0)
    lines = [saved, _line(f"{n_up} commit{'' if n_up == 1 else 's'} not uploaded" + (" (some not measured)" if bad else ""), n_up > 0)]
    if never:
        lines.append(_line(f"{never} branch{'' if never == 1 else 'es'} never uploaded", True))
    return big_tile("code", "Code", "", [], raw_sub="".join(lines) + wait)


def age_words(age) -> str:
    if age is None:
        return "Not measured yet"
    return "today" if age < 1 else "1 day" if age < 2 else f"{int(age)} days"


BOARD_NARROW = ["doing", "blocked", "todo", "done"]       # the phone order: what is live first
BOARD_EMPTY = {"doing": "Nothing in progress", "blocked": "Nothing blocked", "todo": "Nothing waiting",
               "done": "Nothing finished yet"}


def board_html(works: list[dict], ages: dict, cap: int = 8) -> str:
    by_key = {key: (label, statuses) for key, label, statuses in BOARD_COLUMNS}
    if not any(w.get("status") in st for _k, _l, st in BOARD_COLUMNS for w in works):
        return '<p class="muted">No work items yet</p>'
    cols = []
    for key in BOARD_NARROW:
        label, statuses = by_key[key]
        cards = [w for w in works if w.get("status") in statuses]
        cards.sort(key=lambda w: (ages.get(str(w.get("id"))) is None, ages.get(str(w.get("id"))) or 0))
        shown = cards[:cap] if key in ("todo", "done") else cards      # Doing and Blocked are never capped
        items = []
        for w in shown:
            age = ages.get(str(w.get("id")))
            stuck = key in ("doing", "blocked") and age is not None and age > STALE_DAYS
            tail = (chip(f"No change for {int(age)} days", "warn flag") if stuck
                    else f'<span class="age">{esc(age_words(age))}</span>')
            items.append(f'<li class="card" data-id="{esc(w.get("id"))}"><span class="ttl">{esc(show_title(w.get("title"), [str(w.get("id"))])[0])}</span>'
                         f'<span class="foot"><span class="id">{esc(w.get("id"))}</span>{tail}</span></li>')
        more = f'<li class="muted more-n">+ {len(cards) - len(shown)} more</li>' if len(shown) < len(cards) else ""
        body = "".join(items) + more or f'<li class="muted">{esc(BOARD_EMPTY[key])}</li>'
        opened = " open" if key in ("doing", "blocked") else ""
        cols.append(f'<details class="col" data-col="{key}"{opened}><summary><h3>{esc(label)} '
                    f'<span class="ct">{len(cards)}</span></h3></summary><ul>{body}</ul></details>')
    return f'<div class="board">{"".join(cols)}</div>'


WEEK_LEADS = ("Finished", "Merged")
WEEK_ITEM_RE = re.compile(r"^(Finished|Merged): (.*) \(([^()]*)\)$", re.S)
WEEK_ADDED_RE = re.compile(r"^Requirement added: (.*) \(([^()]*)\), now (.*)$", re.S)
WEEK_MOVED_RE = re.compile(r"^Requirement moved from (.*?) to (.*?): (.*) \(([^()]*)\)$", re.S)
WEEK_PLAN_RE = re.compile(r"^Plan changed: (.*?) - was (.*?) -> now (.*?), because (.*)$", re.S)
ID_PREFIX_RE = re.compile(r"^((?:W|REQ|OD|PL)-\d+): (.+)$", re.S)


def _day_label(d: str) -> str:
    try:
        dt = datetime.date.fromisoformat(d)
    except ValueError:
        return d
    return f"{dt:%a} {dt.day} {dt:%b}"


def _week_li(text: str) -> str:
    """One 'What got done' line: a fixed lead word, the plain headline, then the id as a small suffix."""
    lead, title, suffix, extra = "", text, "", ""
    if m := WEEK_ITEM_RE.match(text):
        lead, title, suffix = m.group(1), m.group(2), m.group(3)
    elif m := WEEK_ADDED_RE.match(text):
        lead, title, suffix, extra = "Added", m.group(1), m.group(2), f", now {m.group(3)}"
    elif m := WEEK_MOVED_RE.match(text):
        lead, title, suffix, extra = "Moved", m.group(3), m.group(4), f", now {m.group(2)}"
    ttl, pre = show_title(title, re.findall(r"\b[A-Z]{1,3}-\d+\b", suffix))
    if pre and pre not in suffix:
        suffix = f"{suffix} {pre}".strip()
    lead_html = f'<span class="lead">{esc(lead)}</span> ' if lead else ""
    suffix_html = f' <span class="id">{esc(suffix)}</span>' if suffix else ""
    return f'<li>{lead_html}<span class="ttl">{esc(ttl + extra)}</span>{suffix_html}</li>'


def _plan_change_card(day: str, text: str) -> str:
    m = WEEK_PLAN_RE.match(text)
    if not m:
        return f'<div class="mini"><p>{esc(text)}</p></div>'
    rows = "".join(f'<p class="wnb"><span class="lbl">{lbl}</span><span>{esc(clean_prose(v))}</span></p>'
                   for lbl, v in (("Was", m.group(2)), ("Now", m.group(3)), ("Because", m.group(4))))
    return f'<div class="mini">{rows}<p class="id">{esc(_day_label(day))} · {esc(show_title(m.group(1))[0])}</p></div>'


def week_html(week: dict) -> str:
    shown, hidden, plans, n = [], [], [], 0
    for d in week["days"]:
        done = [i for i in d["items"] if not i.startswith("Plan changed:")]
        plans += [(d["date"], i) for i in d["items"] if i.startswith("Plan changed:")]
        if not done:
            continue
        head, take = f'<h3 class="day">{esc(_day_label(d["date"]))}</h3>', max(0, 8 - n)
        n += len(done)
        if take:
            shown.append(head + "<ul>" + "".join(_week_li(i) for i in done[:take]) + "</ul>")
        if len(done) > take:
            hidden.append(head + "<ul>" + "".join(_week_li(i) for i in done[take:]) + "</ul>")
    left = ["".join(shown)] if shown else []
    if hidden:
        left.append(f'<details class="more"><summary>Show {n - 8} more</summary>{"".join(hidden)}</details>')
    if not shown and not week["unmeasured"]:     # with a source missing, "nothing" would be a guess
        left.append('<p class="muted">Nothing finished this week.</p>')
    for u in week["unmeasured"]:
        left.append(unm_html(u, "Part of this week is missing: it could not be read from git. Run the page builder inside the repository to include it."))
    right = "".join(_plan_change_card(d, i) for d, i in plans[:3]) or '<p class="muted">No plan changes this week</p>'
    return (f'<div class="wk"><div class="wkl"><h3 class="grp">What got done</h3>{"".join(left)}</div>'
            f'<div class="wkr"><h3 class="grp">How plans changed</h3>{right}</div></div>')


def _step_icon(status) -> str:
    st = status if status in ("done", "doing", "dropped") else "todo"
    return f'<span class="ico {st}" role="img" aria-label="{st}"></span>'


def plans_html(plans: list[dict]) -> str:
    if not plans:
        return '<p class="muted">No plans recorded yet. Plans appear here when work is planned.</p>'
    live, rest = [], []
    for p in plans:
        if p.get("unreadable"):
            live.append(f'<p class="muted">{chip("unreadable", "bad")} {esc(p["id"])} - run '
                        f'<code>python tools/factory_lint.py .</code></p>')
            continue
        steps_done = {m["step"] for m in p["mismatch"]}
        head = (f'{ring(p["percent"], 40)}' if p["total"] else "")
        words = f"{p['done']} of {p['total']} steps" if p["total"] else "No steps yet"
        out = [f'<div class="plan" data-plan="{esc(p["id"])}"><div class="ph">{head}<div><h3>{esc(display_title(p["title"], [p["id"]])[0])} '
               f'<span class="id">{esc(p["id"])}</span></h3><p>{esc(words)} · {esc(str(p.get("status") or "").capitalize())}</p>'
               '</div></div>']
        if p["steps"]:
            lis = []
            for s_ in p["steps"]:
                refs = ", ".join(str(r) for r in s_.get("refs") or [])
                warn = (" " + chip("Marked done, work not finished", "warn")) if s_.get("id") in steps_done else ""
                lis.append(f'<li data-step="{esc(s_.get("id"))}" class="{"dropped" if s_.get("status") == "dropped" else ""}">'
                           f'{_step_icon(s_.get("status"))}<span class="ttl">{esc(display_title(s_.get("text"), [str(x) for x in s_.get("refs") or []])[0])}</span>'
                           + (f' <span class="id">{esc(refs)}</span>' if refs else "") + warn + "</li>")
            out.append('<ul class="steps">' + "".join(lis) + "</ul>")
        if p["changes"]:
            out.append("<h4>How this plan changed</h4>" + "".join(
                '<div class="mini">' + "".join(f'<p class="wnb"><span class="lbl">{lbl}</span><span>{esc(c.get(k))}</span></p>'
                                              for lbl, k in (("Was", "was"), ("Now", "now"), ("Because", "why")))
                + f'<p class="id">{esc(c.get("date"))}</p></div>' for c in p["changes"]))
        since = p["commits_since_change"]
        out.append(f'<p class="muted">Last changed {esc(p["last_change"])}; '
                   + (esc(since) if is_unm(since) else f"{esc(since)} commits since") + ".</p></div>")
        (live if p.get("status") == "active" else rest).append("".join(out))
    if rest:
        live.append(f'<details class="more"><summary>{len(rest)} finished or dropped plan{"s" if len(rest) != 1 else ""}'
                    f'</summary>{"".join(rest)}</details>')
    return "".join(live)


JOB_CHIPS = {"success": ("Passed", "ok"), "failure": ("Failed", "bad"), "in_progress": ("Running", "idle"),
             "skipped": ("Skipped", "idle"), "cancelled": ("Cancelled", "idle")}


def _job_chip(job: dict) -> str:
    v = str(job.get("conclusion") or job.get("status") or "")
    text, kind = JOB_CHIPS.get(v, (v.replace("_", " ").capitalize() or "Running", "idle"))
    return f'<span class="job">{esc(job.get("name"))} {chip(text, kind)}</span>'


def technical(body: str) -> str:
    """The closed 'Technical detail' card: check/job names, commands, file paths and per-folder lists live here."""
    return f'<details class="more tech"><summary>Technical detail</summary><div class="bd">{body}</div></details>' if body else ""


def tests_html(results: list[dict] | None, missing: list[dict], runs: list[dict] | None, head=None) -> str:
    out, tech = [], []
    gh = github_verdict(runs, head)
    if results is None:
        if gh is None:         # GitHub has no result either: the one honest sentence, with how to measure inside
            out.append(unm_html("unmeasured: python tools/ci_local.py", "No test results are recorded yet. Run the project's checks on this computer and the results appear here."))
    else:
        passed = sum(int(x.get("passed") or 0) for x in results)
        failed = sum(int(x.get("failed") or 0) for x in results)
        line = f"{passed} passed, {failed} failed on this computer."
        notes = {n for n in (stale_note(x) for x in results) if n}
        out.append(f'<p>{esc(line)} ' + (chip(f"{failed} failing", "bad") + " " if failed else "")
                   + " ".join(chip(*n) for n in sorted(notes)) + "</p>")
        rows = []
        for x in results:
            note = stale_note(x)
            rows.append({"suite": x.get("suite"), "passed": x.get("passed"), "failed": x.get("failed"),
                         "ran": str(x.get("time") or "")[:16].replace("T", " "),
                         "note": chip(*note) if note else ""})
        tech.append(sm_table([("suite", "Suite"), ("passed", "Passed"), ("failed", "Failed"), ("ran", "Ran on"),
                              ("note", "Result is")], rows, {"ran": "p2"}, raw=frozenset({"note"})))
        fails = [(x.get("suite"), f) for x in results for f in x.get("failures", [])]
        tech.append("<h3>Failures</h3>" + ul(
            [f'<li><b>{esc(f.get("name"))}</b> ({esc(suite)}) {chip("Failed", "bad")}<code class="err">{esc(f.get("first_error_line"))}</code></li>'
             for suite, f in fails], "No failing test in the last run."))
    if missing:
        out.append(f'<p>{len(missing)} test suite{"s" if len(missing) != 1 else ""} '
                   + ("not run on this computer yet." if gh else f'{"have" if len(missing) != 1 else "has"} no result for this version.') + "</p>")
    for m in missing:
        tech.append(f'<p class="muted">{chip("Not run yet")} {esc(m["suite"])}</p>'
                    f'<div class="codebox">How to measure: <code>{esc(m["run"])}</code></div>')
    if gh:
        kind = {"passed": "ok", "failed": "bad"}.get(gh["state"], "idle")
        word = {"passed": "Passed", "failed": "Failed"}.get(gh["state"], "Running")
        sent = (f"{gh['n']} of {gh['ran']} checks passed on GitHub, {gh['date']}" if gh["state"] != "running"
                else f"Checks are still running on GitHub ({gh['date']})")
        sent += ("; not run on this computer" if results is None else "") + ("; on an older version" if gh["older"] else "") + "."
        out.append(f"<p>{esc(sent)} {chip(word, kind)}</p>")
    tech.append("<h3>On GitHub</h3>")
    if runs is None:
        tech.append(unm_html(GH_RUNS_CMD, "GitHub check history was not fetched for this page. Build the page with the fetch option and it appears here."))
    else:
        seen, lines = set(), []
        for r in runs:
            name = r.get("workflowName") or r.get("name")
            if name in seen:
                continue
            seen.add(name)
            jobs = " ".join(_job_chip(j) for j in r.get("jobs") or [])
            lines.append(f"<li><b>{esc(name)}</b> ({esc(str(r.get('createdAt') or '')[:10])}): {jobs or 'no job detail'}</li>")
        tech.append(ul(lines, "No GitHub check run recorded."))
    return "".join(out) + technical("".join(tech))


def _when(iso) -> str:
    d = _parse_iso(iso)
    return f"{d.day} {d:%b %H:%M}" if d else str(iso)


def prs_list_html(prs: dict | None, key: str, label: str) -> str:
    """One pull-request list ('open' or 'merged') with its heading; unmeasured when gh was not run."""
    v = (prs or {}).get(key) if isinstance(prs, dict) else None
    out = [f"<h3>{esc(label)}</h3>"]
    if isinstance(v, list) and isinstance(prs, dict) and prs.get(key + "_capped"):
        out.append(f'<p class="flagline">At least {len(v)} (list capped at {PR_LIMIT}); more may exist.</p>')
    if isinstance(v, list):
        def li(p):
            tail = (chip({"passing": "Checks passing", "failing": "Checks failing"}.get(p.get("ci"), f"Checks {p.get('ci')}"),
                         {"passing": "ok", "failing": "bad"}.get(p.get("ci"), "idle")) if key == "open"
                    else f'<span class="age">{esc(str(p.get("merged_at") or "")[:10])}</span>')
            bm = BRANCH_WORK_RE.search(str(p.get("branch") or ""))
            ttl, pre = show_title(p.get("title"), [f"W-{bm.group(1)}"] if bm else [])
            return (f'<li><span class="ttl">{esc(ttl)}</span> <span class="id">#{esc(p.get("number"))}'
                    + (f" {esc(pre)}" if pre else "") + f'</span> {tail}</li>')
        items = [li(p) for p in v]
        if key == "merged" and len(items) > 8:
            out.append(ul(items[:8], "None.") + f'<details class="more"><summary>Show {len(items) - 8} more</summary>'
                       + ul(items[8:], "None.") + "</details>")
        else:
            out.append(ul(items, "None."))
    else:
        out.append(unm_html(v if isinstance(v, str) else "unmeasured: gh pr list", "Pull requests were not fetched from GitHub for this page. Build the page with the fetch option and they appear here."))
    return "".join(out)


def code_html(code_state: dict, prs: dict | None) -> str:
    wts = code_state.get("worktrees")
    if not isinstance(wts, list):
        return unm_html(str(wts), "Working copies could not be listed because git did not answer. Build the page inside the repository and they appear here.")
    rows, details, sentences = [], [], []
    k_files, folders, n_up, never, bad = 0, set(), 0, 0, False
    unknown_files = False
    for w in wts:
        u = w.get("unsaved")
        np_ = w.get("not_pushed")
        rows.append({"folder": Path(w["path"]).name, "branch": w.get("branch"), "last": _when(w.get("last_commit")),
                     "unsaved": u["count"] if isinstance(u, dict) else u,
                     "not_pushed": chip("Never uploaded", "warn") if np_ == "never pushed" else np_})
        if isinstance(u, dict):
            k_files += u["count"]
            folders |= set(u["by_folder"]) | ({"(hidden)"} if u["hidden"] and not u["by_folder"] else set())
        else:
            unknown_files = True
        n_up += np_ if isinstance(np_, int) else 0
        never += np_ == "never pushed"
        bad = bad or is_unm(np_)
        if isinstance(u, dict) and u["count"]:
            by = ", ".join(f"{k}: {v} files" for k, v in u["by_folder"].items())
            names = ", ".join(u["names"]) + (f" and {u['more']} more" if u["more"] else "")
            hid = f"{u['hidden']} file{'s' if u['hidden'] != 1 else ''} hidden (name looks like a secret)" if u["hidden"] else ""
            details.append(f'<li><b>{esc(Path(w["path"]).name)}</b>: {esc(by)}<br>'
                           f'<code class="err">{esc(names)}</code>' + (f'<br><span class="muted">{esc(hid)}</span>' if hid else "")
                           + "</li>")
    if unknown_files:
        sentences.append("<li>Unsaved files: " + chip("Not measured yet") + " git could not list them, so none are counted here. Build the page inside the repository.</li>")
    else:
        sentences.append(f"<li>{k_files} file{'' if k_files == 1 else 's'} not saved"
                         + (f" in {len(folders)} folder{'' if len(folders) == 1 else 's'}" if k_files else "") + "</li>")
    sentences.append(f"<li>{n_up} commit{'' if n_up == 1 else 's'} not uploaded"
                     + (" (some not measured)" if bad else "") + "</li>")
    if never:
        sentences.append(f"<li>{never} branch{'' if never == 1 else 'es'} never uploaded</li>")
    out = ["<ul>" + "".join(sentences) + "</ul>"]
    tech = [sm_table([("branch", "Branch"), ("unsaved", "Not saved"), ("not_pushed", "Not uploaded"), ("last", "Last change"),
                      ("folder", "Working copy")], rows, {"last": "p2", "folder": "p3"}, raw=frozenset({"not_pushed"})),
            "<h3>Not saved, by folder</h3>" + ul(details, "Nothing unsaved.")]
    out.append(prs_list_html(prs, "open", "Waiting to merge"))
    return "".join(out) + technical("".join(tech))


BRANCH_WORK_RE = re.compile(r"(?<![A-Za-z0-9])w-(\d{3,})", re.I)


def working_on(info: dict, plans: list[dict], code_state: dict, now_dt: datetime.datetime,
               works: list[dict] | None = None) -> tuple[str, str, str]:
    """(state, headline, not_moving) for the header; state is working | paused | unknown.
    The headline is the most recently active thing: a worktree branch with a commit inside PAUSED_HOURS (mapped to its
    work item when the branch name carries W-###) or an in_progress item changed within STALE_DAYS. Each 'last activity'
    is that thing's own time. In-progress items unchanged for over STALE_DAYS are only in `not_moving`."""
    works = works or []
    title_of = {str(w.get("id")): w.get("title") for w in works}
    cands = []                                   # (days since activity, kind, label, work id or None)
    wts = code_state.get("worktrees")
    unknown = not isinstance(wts, list)
    for w in (wts if isinstance(wts, list) else []):
        when = _parse_iso(w.get("last_commit"))
        if when is None:
            unknown = True
            continue
        br = str(w.get("branch"))
        if br in MAIN_BRANCHES or br == "(detached)":
            continue
        days = (now_dt - when).total_seconds() / 86400
        if days * 24 < PAUSED_HOURS:
            m = BRANCH_WORK_RE.search(br)
            wid = f"W-{m.group(1)}" if m else None
            label = plain_title(title_of[wid]) if wid in title_of else br
            cands.append((days, "branch", label, wid if wid in title_of else None))
    stale = []
    for i in info["in_progress"]:
        if i.get("age_days") is None:
            unknown = True
        elif i.get("stale"):
            stale.append(f"{plain_title(i['title'])} ({i['id']}) — unchanged for {int(i['age_days'])} days")
        else:
            cands.append((i["age_days"], "item", plain_title(i["title"]), i["id"]))
    not_moving = ("Not moving: " + "; ".join(stale)) if stale else ""
    if cands:
        days, kind, label, wid = min(cands, key=lambda c: c[0])
        step = next((f"step {s.get('id')}: {s.get('text')}" for p in plans if not p.get("unreadable")
                     for s in p.get("steps", []) if wid and s.get("status") == "doing" and wid in (s.get("refs") or [])),
                    "no plan step")
        ident = f" ({wid})" if wid else ""
        return "working", f"Working on: {label}{ident} · {step} · last activity {ago_words(days)}", not_moving
    if unknown:
        return "unknown", "Activity unknown", not_moving
    return "paused", "Paused, nothing running", not_moving


CSS = """
/* design spec docs/design/status-page-design.md: tokens on :root, one accent, flat cards, anchor nav, phone first */
:root{--bg:#F5F6F8;--surface:#FFFFFF;--surface-2:#F0F2F5;--line:#E3E6EB;--text:#16191F;--text-2:#4A5260;--text-3:#5F6877;--accent:#2F5BFF;--accent-text:#2449E0;--accent-soft:#EAF0FF;--ok:#1E7A46;--ok-bg:#E7F5EC;--warn:#8A5300;--warn-bg:#FFF4E0;--bad:#B42318;--bad-bg:#FDECEA;--idle:#4A5260;--idle-bg:#F0F2F5;--font:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,"SFMono-Regular",Consolas,monospace;--fs-xs:12px;--fs-sm:13px;--fs-base:15px;--fs-md:17px;--fs-lg:20px;--fs-xl:26px;--fw-regular:400;--fw-medium:500;--fw-semi:600;--fw-bold:700;--s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--s6:32px;--r-card:16px;--r-chip:8px;--r-pill:999px;--r-sm:6px;--shadow:0 1px 2px rgba(16,24,40,.06);--tap:44px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0F1115;--surface:#171A21;--surface-2:#1F232C;--line:#2A2F3A;--text:#E8EAEE;--text-2:#A9B0BC;--text-3:#8C94A1;--accent:#7C9BFF;--accent-text:#9DB4FF;--accent-soft:#1C2A55;--ok:#6FD49A;--ok-bg:#12291C;--warn:#F2B75B;--warn-bg:#2E2210;--bad:#FF8A80;--bad-bg:#341716;--idle:#A9B0BC;--idle-bg:#1F232C;--shadow:none;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0F1115;--surface:#171A21;--surface-2:#1F232C;--line:#2A2F3A;--text:#E8EAEE;--text-2:#A9B0BC;--text-3:#8C94A1;--accent:#7C9BFF;--accent-text:#9DB4FF;--accent-soft:#1C2A55;--ok:#6FD49A;--ok-bg:#12291C;--warn:#F2B75B;--warn-bg:#2E2210;--bad:#FF8A80;--bad-bg:#341716;--idle:#A9B0BC;--idle-bg:#1F232C;--shadow:none;color-scheme:dark}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{font:var(--fw-regular) var(--fs-base)/1.5 var(--font);background:var(--bg);color:var(--text);margin:0;font-variant-numeric:tabular-nums}
h1,h2,h3,h4{line-height:1.25}
.wrap{max-width:1200px;margin:0 auto;padding:0 16px 48px;display:grid;gap:var(--s4);min-width:0}
.wrap>*{min-width:0}
header{padding-top:24px}
.eyebrow{margin:0;font-size:var(--fs-sm);color:var(--text-2)}
.hrow{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:4px}
.hrow p{margin:0}
h1{font-size:22px;font-weight:var(--fw-bold);margin:0;overflow-wrap:anywhere}
.muted{color:var(--text-2)}
code,.mono{font-family:var(--mono);font-size:.9em;overflow-wrap:anywhere}
.panel,.wrap>details.sec,.tile.big{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);box-shadow:var(--shadow);padding:var(--s4);scroll-margin-top:56px}
.panel h2{font-size:var(--fs-lg);font-weight:var(--fw-semi);margin:0 0 12px}
.sh{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.sh h2{margin:0}
.ct{margin-left:auto;font-size:var(--fs-sm);font-weight:var(--fw-regular);color:var(--text-2);font-variant-numeric:tabular-nums;overflow-wrap:anywhere;text-align:right}
.sec>summary,.col>summary,details.more>summary{display:flex;align-items:center;gap:12px;min-height:var(--tap);cursor:pointer;list-style:none}
.sec>summary::-webkit-details-marker,.col>summary::-webkit-details-marker,details.more>summary::-webkit-details-marker{display:none}
.sec>summary>span:first-child{font-size:var(--fs-md);font-weight:var(--fw-semi)}
details>summary::after{content:"";flex:none;width:7px;height:7px;border:solid var(--text-2);border-width:0 2px 2px 0;transform:rotate(-45deg);margin:0 4px}
details[open]>summary::after{transform:rotate(45deg)}
details.more>summary{color:var(--accent-text);font-size:var(--fs-sm);font-weight:var(--fw-medium)}
.sec .bd{min-width:0;overflow-wrap:anywhere}
.wrap>details.sec>.bd{padding-top:4px}
.sec .sec{border-top:1px solid var(--line)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.id{font-size:var(--fs-xs);color:var(--text-3);font-weight:var(--fw-regular);margin-left:6px;white-space:nowrap}
.chip{display:inline-flex;align-items:center;height:22px;padding:0 8px;border-radius:var(--r-chip);font-size:var(--fs-xs);font-weight:var(--fw-semi);white-space:nowrap;vertical-align:middle}
.chip.ok{color:var(--ok);background:var(--ok-bg)}.chip.warn{color:var(--warn);background:var(--warn-bg)}.chip.bad{color:var(--bad);background:var(--bad-bg)}.chip.idle{color:var(--idle);background:var(--idle-bg)}.chip.accent{color:var(--accent-text);background:var(--accent-soft)}
.pill{display:inline-flex;align-items:center;gap:8px;height:28px;padding:0 12px;border-radius:var(--r-chip);font-size:var(--fs-sm);font-weight:var(--fw-semi);color:var(--idle);background:var(--idle-bg)}
.pill::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.fresh[data-level=ok]{color:var(--ok);background:var(--ok-bg)}.fresh[data-level=warn]{color:var(--warn);background:var(--warn-bg)}.fresh[data-level=bad]{color:var(--bad);background:var(--bad-bg)}
.banner{background:var(--bad-bg);color:var(--bad);border-radius:var(--r-card);padding:var(--s4);margin:0;font-weight:var(--fw-medium)}
.banner[hidden]{display:none}
.top{display:grid;gap:var(--s4);align-items:stretch}
#now,#not-moving{display:flex;gap:10px;align-items:flex-start;margin:0 0 8px}
.dot{flex:none;width:10px;height:10px;border-radius:50%;margin-top:7px;background:var(--accent)}
#now[data-state=paused] .dot,#now[data-state=unknown] .dot{background:var(--text-3)}
#not-moving .dot{background:var(--warn)}
.needs .sec>summary{padding:0}
.needs[data-has="1"] .ct{margin-left:auto;background:var(--accent);color:var(--surface);border-radius:var(--r-pill);min-width:24px;padding:0 8px;text-align:center;font-weight:var(--fw-semi)}
.needs[data-has="0"] .ct{margin-left:auto;background:var(--ok-bg);color:var(--ok);border-radius:var(--r-chip);padding:2px 8px;font-size:var(--fs-xs);font-weight:var(--fw-semi)}
.qs{list-style:none;margin:0;padding:0}
.qs li{padding:12px 0;border-top:1px solid var(--line);margin:0}
.qs .q{font-weight:var(--fw-medium)}
.qs .sl{display:block;font-size:var(--fs-sm);color:var(--text-2)}
#first-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.tile.big{min-height:132px;min-width:0;display:flex;flex-direction:column;gap:8px}
.tile.big h3{margin:0;font-size:var(--fs-sm);font-weight:var(--fw-semi);color:var(--text-2)}
.tv{display:flex;flex-direction:column;align-items:flex-start;gap:8px;min-width:0}
.tile .ring{width:44px;height:44px}
.tile.big b{font-size:var(--fs-lg);font-weight:var(--fw-bold);line-height:1.25;overflow-wrap:break-word;hyphens:auto;max-width:100%}
.tile.big b:empty{display:none}
.sub{display:block;font-size:var(--fs-sm);color:var(--text-2);overflow-wrap:break-word;hyphens:auto;max-width:100%}
.ln{display:block;font-size:var(--fs-sm);color:var(--text-2);margin:2px 0}
.dotw{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--warn);margin-right:8px}
.unm details{margin:0}
.ttl{overflow-wrap:anywhere}
#now .ttl,#not-moving .ttl{font-weight:var(--fw-medium);overflow-wrap:break-word}
#now .sl,#not-moving .sl{display:block;font-size:var(--fs-sm);color:var(--text-2)}
.ring{flex:none}.ring .trk{stroke:var(--accent-soft)}.ring .arc{stroke:var(--accent)}.ring text{font-size:13px;font-weight:var(--fw-semi);fill:var(--text)}
.plan .ring text{font-size:11px}
.strip{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.tile:not(.big){background:var(--surface-2);border-radius:var(--r-sm);padding:var(--s3);min-width:0}
.tile:not(.big) b{display:block;font-size:var(--fs-lg);font-weight:var(--fw-bold)}
.tile:not(.big)>span{display:block;font-size:var(--fs-sm);color:var(--text-2)}
.wk{display:grid;gap:var(--s4)}
.grp{font-size:var(--fs-md);font-weight:var(--fw-semi);margin:0 0 8px}
.day{font-size:var(--fs-sm);font-weight:var(--fw-semi);color:var(--text-2);margin:12px 0 4px}
.wk ul,.qs,.steps,.board ul{list-style:none;margin:0;padding:0}
.wk li{margin:6px 0}
.lead{color:var(--text-2);font-weight:var(--fw-medium)}
.mini{background:var(--surface-2);border-radius:var(--r-sm);padding:var(--s3);margin-bottom:8px}
.mini p{margin:0}
.wnb{font-size:var(--fs-sm);display:grid;grid-template-columns:64px 1fr;gap:8px}
.lbl{display:block;font-size:var(--fs-xs);font-weight:var(--fw-semi);color:var(--text-3)}
.board{display:grid;gap:12px}
.col{background:var(--surface-2);border-radius:var(--r-sm);padding:0 12px}
.col h3{margin:0;font-size:var(--fs-md);font-weight:var(--fw-semi)}
.col .ct{color:var(--text-3)}
.col>summary .ct{margin-left:6px}
.board ul{display:grid;gap:8px;padding-bottom:12px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0;min-width:0}
.card .ttl{display:block;font-size:var(--fs-sm);font-weight:var(--fw-medium);overflow-wrap:anywhere}
.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:6px}
.foot .id{margin-left:0}
.age{font-size:var(--fs-xs);color:var(--text-3)}
.col[data-col=blocked] .card{border-left:3px solid var(--bad)}
.more-n{color:var(--text-3);font-size:var(--fs-sm)}
.snav{position:sticky;top:0;z-index:10;background:var(--surface);border-bottom:1px solid var(--line);height:48px;display:flex;gap:4px;align-items:center;overflow-x:auto;scrollbar-width:none;margin-inline:-16px;padding-inline:16px}
.snav::-webkit-scrollbar{display:none}
.snav a{display:inline-flex;align-items:center;min-height:var(--tap);padding:0 8px;font-size:var(--fs-sm);font-weight:var(--fw-medium);color:var(--text-2);text-decoration:none;white-space:nowrap;border-bottom:2px solid transparent}
.snav a.active{color:var(--accent-text);border-bottom-color:var(--accent)}
.plan{background:var(--surface-2);border-radius:var(--r-sm);padding:var(--s4);margin-bottom:12px}
.ph{display:flex;gap:12px;align-items:center}
.ph h3{margin:0;font-size:var(--fs-md);font-weight:var(--fw-semi)}.ph p{margin:0;font-size:var(--fs-sm);color:var(--text-2)}
.plan h4{margin:12px 0 8px;font-size:var(--fs-sm);color:var(--text-2)}
.steps{margin:12px 0}
.steps li{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.steps .ttl{flex:1 1 140px;min-width:0;overflow-wrap:anywhere}
.ico{flex:none;width:20px;height:20px;border-radius:50%;display:inline-block;position:relative}
.ico.done{background:var(--accent)}
.ico.done::after{content:"";position:absolute;left:7px;top:3px;width:5px;height:10px;border:solid var(--surface);border-width:0 2px 2px 0;transform:rotate(45deg)}
.ico.doing{border:2px solid var(--accent)}
.ico.doing::after{content:"";position:absolute;inset:2px;border-radius:50%;background:var(--accent);clip-path:inset(0 50% 0 0)}
.ico.todo,.ico.dropped{border:2px solid var(--line)}
.steps li.dropped .ttl{text-decoration:line-through;color:var(--text-3)}
.tw{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;width:100%;font-size:var(--fs-sm)}
th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:break-word}
thead th{white-space:nowrap;overflow-wrap:normal;background:var(--surface-2);font-size:var(--fs-xs);font-weight:var(--fw-semi);color:var(--text-2)}
tbody tr:hover{background:var(--surface-2)}
.num{text-align:right}
.p3{display:none}
th.srt{padding:0}
th button{all:unset;box-sizing:border-box;display:flex;align-items:center;width:100%;min-height:var(--tap);padding:8px;cursor:pointer;font-weight:var(--fw-semi)}
.num button{justify-content:flex-end}
.top-empty{align-items:start}
.pc-count{display:none;align-self:center;font-size:var(--fs-sm);color:var(--text-2)}
.pc-count[hidden]{display:none!important}
@media (max-width:767px){.pc-count{display:block}table.pc:not(.filtering){display:none}}
td[data-k=status]{min-width:5.5em}
td[data-k=release]{white-space:nowrap}
th button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
th button[aria-sort=ascending]::after{content:" \\25B2";font-size:10px}th button[aria-sort=descending]::after{content:" \\25BC";font-size:10px}
table.capped:not(.filtering) tr.extra{display:none}
@media (max-width:767px){table.pcap:not(.filtering) tbody tr:nth-child(n+6){display:none}}
@media (min-width:768px){.phone-only{display:none}}
.tbtns{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0}.tbtns:empty{display:none}
.tog{min-height:var(--tap);padding:0 12px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface);color:var(--accent-text);font:inherit;font-size:var(--fs-sm);font-weight:var(--fw-medium);cursor:pointer}
.flt{display:flex;flex-wrap:wrap;gap:8px;margin-block:8px}
input,select{font:inherit;min-height:var(--tap);padding:0 12px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--surface);color:var(--text);max-width:100%}
.flt input[type=search]{flex:1 1 100%}
.codebox{background:var(--surface-2);border-radius:var(--r-sm);padding:8px 12px;max-width:100%;overflow-x:auto;font-size:var(--fs-sm)}
.err{display:block;font-family:var(--mono);font-size:var(--fs-xs);color:var(--text-2);overflow-wrap:anywhere}
.flagline{font-weight:var(--fw-semi)}
.job{display:inline-flex;gap:6px;align-items:center;margin-right:8px}
.nsy{padding:12px 0;border-top:1px solid var(--line)}.nsy h3{margin:0 0 4px;font-size:var(--fs-md);font-weight:var(--fw-semi)}.nsy p{margin:0;font-size:var(--fs-sm);color:var(--text-2)}
li{margin-block:4px}
h3{font-size:var(--fs-md);font-weight:var(--fw-semi);margin:12px 0 4px}
footer{font-size:var(--fs-xs);color:var(--text-3);text-align:center;padding:32px 0;margin:0}
footer p{margin:0}
@media (min-width:768px){
.tv{flex-direction:row;align-items:center;gap:12px}
.tile .ring{width:56px;height:56px}
.wrap{padding:0 24px 48px;gap:var(--s5)}
header{padding-top:32px}
.hrow{flex-direction:row;justify-content:space-between;align-items:center}
h1{font-size:var(--fs-xl)}
.panel,.wrap>details.sec,.tile.big{padding:var(--s5)}
#first-tiles{gap:16px}
.strip{grid-template-columns:repeat(4,1fr)}
.snav{margin-inline:-24px;padding-inline:24px}
.flt input[type=search]{flex:0 0 280px}
td{padding:8px 12px}
th button{padding:8px 12px}
}
@media (max-width:767px){.p2{display:none}}
.tw.allcols .p2,.tw.allcols .p3{display:table-cell}
@media (min-width:1024px){
.top{grid-template-columns:8fr 4fr}
#first-tiles{grid-template-columns:repeat(4,1fr)}
.wk{grid-template-columns:8fr 4fr}
.board{grid-template-columns:repeat(4,1fr);align-items:start}
.col[data-col=todo]{order:1}.col[data-col=doing]{order:2}.col[data-col=blocked]{order:3}.col[data-col=done]{order:4}
.snav{margin-inline:0;padding-inline:var(--s4);border:1px solid var(--line);border-radius:var(--r-card)}
.col>summary{pointer-events:none}.col>summary::after{display:none}
}
/* REQ-053 reader roles (docs/design/status-page-roles.md) */
.card.role{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);box-shadow:var(--shadow);padding:var(--s4);scroll-margin-top:56px;min-width:0}
.role h2{font-size:var(--fs-lg);font-weight:var(--fw-semi);margin:0 0 4px}
.asks{margin:0 0 8px;font-size:var(--fs-sm);color:var(--text-2)}
.answer{margin:0 0 16px;font-size:var(--fs-md);font-weight:var(--fw-semi);color:var(--text);overflow-wrap:anywhere}
.answer .chip{margin-left:4px}
.role>.top,.role>#first-tiles,.role>.blk{margin-top:16px}
.role>.blk{box-shadow:none}
.rb{border-top:1px solid var(--line);margin-top:16px;padding-top:4px;scroll-margin-top:56px;min-width:0;overflow-wrap:anywhere}
.rb>h3{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;font-size:var(--fs-md);font-weight:var(--fw-semi);margin:12px 0 8px}
.rb h4,.role h4{font-size:var(--fs-sm);font-weight:var(--fw-semi);color:var(--text-2);margin:12px 0 4px}
.role>details.sec{border-top:1px solid var(--line);margin-top:12px}
.role ul{list-style:none;margin:0;padding:0}
.role li{margin-block:6px}
.sl{display:block;font-size:var(--fs-sm);color:var(--text-2)}
.tlk{display:block;min-width:0;color:inherit;text-decoration:none;border-radius:var(--r-card)}
.tlk:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tlk .tile.big{height:100%}
.needs[data-has="none"] .ct{margin-left:auto;background:var(--idle-bg);color:var(--idle);border-radius:var(--r-chip);padding:2px 8px;font-size:var(--fs-xs);font-weight:var(--fw-semi)}
.chip.rec{border:1px dashed var(--line)}
.sbar{display:flex;height:12px;border-radius:var(--r-pill);overflow:hidden;background:var(--line);margin:12px 0 4px}
.sbar i{display:block;min-width:2px}
.s-done{background:var(--ok)}.s-check{background:var(--accent)}.s-approved{background:var(--idle);opacity:.4}.s-recorded{background:var(--line)}
.lane .sbar{height:6px;margin:8px 0}
.legend{margin:0 0 8px;font-size:var(--fs-sm);color:var(--text-2)}
.mb{display:inline-block;width:40px;height:6px;border-radius:var(--r-pill);background:var(--accent-soft);vertical-align:middle;margin-left:8px;overflow:hidden}
.mb i{display:block;height:100%;background:var(--accent)}
.areas li{display:grid;grid-template-columns:1fr auto;gap:4px 12px;padding:6px 0;margin:0}
.areas .an{font-size:var(--fs-sm);font-weight:var(--fw-medium);overflow-wrap:anywhere;min-width:0}
.areas .ad{font-size:var(--fs-sm);color:var(--text-2);text-align:right;white-space:nowrap}
.areas .mb{grid-column:1/-1;width:100%;margin:0}
.areas .ns{grid-column:1/-1;font-size:var(--fs-xs);color:var(--text-3)}
td[data-k=id],td.idc{white-space:nowrap;font-family:var(--mono);font-size:var(--fs-xs);color:var(--text-2)}
td[data-k=title],td[data-k=check]{overflow-wrap:anywhere;min-width:0}
td[data-k=checks]{white-space:nowrap}
.lanes{display:grid;gap:8px;align-items:stretch}
.lane{background:var(--surface-2);border-radius:var(--r-sm);padding:12px;min-width:0}
.lane h4{margin:0;font-size:var(--fs-md);font-weight:var(--fw-semi);color:var(--text)}
.lane .ld,.lane p{margin:4px 0;font-size:var(--fs-sm)}
.chev{display:block;text-align:center;color:var(--text-3);transform:rotate(90deg);line-height:1}
.bases li.base{padding:8px 0;border-top:1px solid var(--line);margin:0;min-width:0}
.bases li.open-base{border-left:3px solid var(--bad);padding-left:12px}
.nb{font-size:var(--fs-sm);color:var(--text-2);margin:2px 0 2px 16px}
.wcs{display:grid;gap:8px}
.wc{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0;min-width:0}
.wc p{margin:4px 0}
.wc.blocked{border-left:3px solid var(--bad)}
.blk-line{color:var(--bad);font-size:var(--fs-sm)}
.two{display:grid;gap:var(--s4);min-width:0}
.two>*{min-width:0}
.pcols{display:grid;gap:var(--s4);margin-top:12px}
.pcols>*{min-width:0}
.track{display:flex;gap:4px;margin:12px 0 4px}
.sg{flex:1;height:8px;border-radius:var(--r-pill);background:var(--line);box-sizing:border-box}
.sg.done{background:var(--accent)}.sg.doing{background:var(--accent-soft);border:2px solid var(--accent)}
.now-line{margin:4px 0;font-size:var(--fs-sm);font-weight:var(--fw-semi)}
.steps.tl{position:relative}
.steps.tl::before{content:"";position:absolute;left:9px;top:10px;bottom:10px;width:2px;background:var(--line)}
.steps.tl>li.st{position:relative;display:flex;gap:8px;align-items:flex-start;flex-wrap:nowrap;margin:0;padding:6px 4px}
.st .stt{flex:1;min-width:0;overflow-wrap:anywhere}
.st .stw{flex:none;font-size:var(--fs-sm);color:var(--text-2);white-space:nowrap}
.st.done .ttl{color:var(--text-2)}
.st.now{background:var(--accent-soft);border-radius:var(--r-sm)}
.st.collapsed{display:block}
.chg .wnb{margin:6px 0}
.chg .wnb.was{border-left:3px solid var(--line);padding-left:8px;color:var(--text-2)}
.chg .wnb.now{border-left:3px solid var(--accent);padding-left:8px}
details.rq>summary{display:flex;align-items:center;min-height:var(--tap);cursor:pointer;list-style:none}
details.rq ul{padding-left:8px}
.fl{color:var(--bad)}
details.grp{border-top:1px solid var(--line)}
details.grp>.bd{overflow-x:auto}
@media (min-width:768px){
.areas{columns:1}
.wcs{grid-template-columns:1fr 1fr}
.lanes{grid-template-columns:1fr 1fr}.lanes .chev{display:none}
.card.role{padding:var(--s5)}
}
@media (min-width:1024px){
.lanes{grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;align-items:stretch}
.lanes .chev{display:flex;align-items:center;transform:none}
.two{grid-template-columns:1fr 1fr}
.pcols{grid-template-columns:7fr 5fr}
.areas{columns:2;column-gap:24px}
.areas li{break-inside:avoid}
}
/* round 2 (ratings): the role bar is two rows of four on a phone; every anchor target clears the bar's height */
.wrap{--bar-h:89px}
.panel,.wrap>details.sec,.tile.big,.card.role,.rb{scroll-margin-top:calc(var(--bar-h) + 8px)}
@media (max-width:767px){
.snav{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));height:auto;overflow:visible;gap:0;padding-inline:0;align-items:stretch}
.snav a{justify-content:center;text-align:center;min-height:var(--tap);padding:0 2px;border-bottom:0;white-space:normal;min-width:0}
.snav a.active{box-shadow:inset 0 -2px 0 var(--accent)}
}
@media (min-width:768px){.wrap{--bar-h:48px}.sl.sm-only{display:none}}
th .hs{display:none}
@media (max-width:767px){th .hl{display:none}th .hs{display:inline}}
details.more>summary{width:max-content;max-width:100%;border:1px solid var(--line);border-radius:var(--r-sm);padding:0 12px;background:var(--surface)}
details.more>summary:hover{background:var(--surface-2)}
details.more.inl{display:inline}
details.rq>summary,details.grp>summary{border:1px solid var(--line);border-radius:var(--r-sm);padding:6px 12px;min-height:var(--tap);background:var(--surface);cursor:pointer}
details.rq>summary:hover,details.grp>summary:hover{background:var(--surface-2)}
details.rq>summary::after{content:"Show checks";margin-left:12px;color:var(--accent-text);font-size:var(--fs-sm);font-weight:var(--fw-medium)}
details.rq[open]>summary::after{content:"Hide checks"}
details.rq>summary{flex-wrap:wrap;gap:4px 12px;min-width:0}
details.rq>summary::after{flex:none;white-space:nowrap;margin-left:auto;position:static;transform:none;width:auto;height:auto;border:0}
@media (max-width:767px){#role-data .tw.sm th,#role-data .tw.sm td{padding-inline:4px}#role-data .tw.sm .chip{white-space:normal}}
details.more.inl>summary{display:inline-flex;vertical-align:middle;margin-left:4px}
.idkey{font-size:var(--fs-xs);margin:8px 0 0}
.wc.orphan p{margin:4px 0}
.bchip{vertical-align:middle}
.sl b{font-weight:var(--fw-semi)}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
""".strip()

JS = """
(function () {
  var p = document.getElementById("fresh");
  if (!p) { return; }
  var t = Date.parse(p.getAttribute("data-iso"));
  if (isNaN(t)) { return; }
  var h = (Date.now() - t) / 3600000;
  var txt = h * 60 < 1 ? "just now" : h < 1 ? Math.floor(h * 60) + " min ago" : h < 48 ? Math.floor(h) + " h ago" : Math.floor(h / 24) + " days ago";
  p.textContent = "Updated " + txt;
  p.title = p.getAttribute("data-iso");
  p.setAttribute("data-level", h < 24 ? "ok" : h <= 72 ? "warn" : "bad");
  var b = document.getElementById("stale");
  if (h > 72 && b) { b.textContent = "This page is " + Math.floor(h / 24) + " days old. What you see may have changed since."; b.hidden = false; }
})();
document.querySelectorAll("[data-all-cols]").forEach(function (b) {
  b.addEventListener("click", function () {
    var tw = b.parentNode.previousElementSibling;
    tw.classList.toggle("allcols");
    b.textContent = tw.classList.contains("allcols") ? "Show fewer columns" : "Show all columns";
  });
});
document.querySelectorAll("[data-show-all]").forEach(function (b) {
  b.addEventListener("click", function () {
    document.getElementById(b.getAttribute("data-show-all")).classList.remove("capped", "pc", "pcap");
    b.parentNode.querySelectorAll(".pc-count").forEach(function (x) { x.hidden = true; });
    b.hidden = true;
  });
});
(function () {
  var mq = window.matchMedia("(min-width:1024px)");
  function sync() { if (mq.matches) { document.querySelectorAll(".col").forEach(function (d) { d.open = true; }); } }
  sync();
  if (mq.addEventListener) { mq.addEventListener("change", sync); }
})();
(function () {
  var links = document.querySelectorAll(".snav a");
  if (!("IntersectionObserver" in window)) { return; }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (e.isIntersecting) {
        links.forEach(function (a) {
          var on = a.getAttribute("href") === "#" + e.target.id;
          a.classList.toggle("active", on);
          if (on && a.scrollIntoView) { a.scrollIntoView({ inline: "nearest", block: "nearest" }); }
        });
      }
    });
  }, { rootMargin: "-20% 0px -70% 0px" });
  links.forEach(function (a) { var el = document.getElementById(a.getAttribute("href").slice(1)); if (el) { io.observe(el); } });
})();
function cmpCells(x, y) {
  var num = /^-?\\d+(\\.\\d+)?$/;
  if (num.test(x) && num.test(y)) { return parseFloat(x) - parseFloat(y); }
  return x.localeCompare(y, undefined, { numeric: true });
}
function wireTable(tid, qid, selects) {
  var t = document.getElementById(tid);
  if (!t) { return; }
  var body = t.tBodies[0];
  t.querySelectorAll("th button").forEach(function (b, ix) {
    b.addEventListener("click", function () {
      var dir = b.getAttribute("aria-sort") === "ascending" ? -1 : 1;
      t.querySelectorAll("th button").forEach(function (x) { x.removeAttribute("aria-sort"); });
      b.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
      var rows = Array.from(body.rows);
      rows.sort(function (a, c) { return cmpCells(a.cells[ix].textContent, c.cells[ix].textContent) * dir; });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
  var q = document.getElementById(qid);
  function apply() {
    var s = q ? (q.value || "").toLowerCase() : "";
    var on = !!s || selects.some(function (pair) { return !!document.getElementById(pair[0]).value; });
    t.classList.toggle("filtering", on);
    Array.from(body.rows).forEach(function (r) {
      var ok = r.textContent.toLowerCase().indexOf(s) >= 0;
      selects.forEach(function (pair) {
        var v = document.getElementById(pair[0]).value;
        if (v && pair[1] === "cov") {
          var st = r.querySelector('td[data-k="status"]');
          var t = st ? st.textContent : "";
          var kind = t === "no requirement" ? "not covered" : t.indexOf("no requirement (exempt") === 0 ? "exempt" : "covered";
          ok = ok && kind === v;
        } else if (v) { var c = r.querySelector('td[data-k="' + pair[1] + '"]'); ok = ok && !!c && c.textContent === v; }
      });
      r.hidden = !ok;
    });
  }
  if (q) { q.addEventListener("input", apply); }
  selects.forEach(function (pair) { document.getElementById(pair[0]).addEventListener("change", apply); });
}
wireTable("t-req", "q-req", [["f-req-status", "status"], ["f-req-health", "health"], ["f-req-release", "release"]__SECTION__]);
wireTable("t-od", "q-od", [["f-od-cov", "cov"], ["f-od-status", "status"]]);
wireTable("t-next", null, []);
wireTable("t-iss", "q-iss", [["f-iss-status", "status"]]);
""".strip()


# ---- the reader-role page (REQ-053, W-039; docs/design/status-page-roles.md) ---------------------------------------
# One section per reader role, each with a one-line answer computed here from the readers' output. A source the
# project does not keep is reported as missing, never as empty (knowledge/findings/absent-source-reads-as-empty.json).

ROLE_BAR = [("summary", "Summary"), ("product", "Product"), ("architecture", "Architecture"),
            ("development", "Development"), ("testing", "Testing"), ("releases", "Releases"),
            ("operations", "Operations"), ("data", "Data checks")]
CHECKING = {"Implemented", "Testing", "Implementing"}      # being checked (Implementing: the build is not finished yet)
APPROVED_STATUSES = {"Approved", "Planned"}
GROUPS = [("done", "Done", "ok"), ("check", "Being checked", "accent"), ("approved", "Approved, not started", "idle"),
          ("recorded", "Recorded, not approved", "idle")]
GROUP_WORD = {k: w for k, w, _c in GROUPS}
GROUP_CHIP = {k: c for k, _w, c in GROUPS}
LAYER_ORDER = ["foundation", "core", "feature", "polish"]
OTHER_DESIGN_DIRS = [("data", "data"), ("technical-design", "technical design"), ("api", "API"),
                     ("security", "security"), ("ui", "UI"), ("testing", "testing")]
CHECK_COMMANDS = ["python tools/build_order.py . --check", "python tools/build_spec_index.py . --check",
                  "python tools/trace_check.py . --check-view"]


def req_group(status) -> str:
    """The four plain-word groups every count on the page uses; the groups add up to the live requirements."""
    s = status or "unknown"
    return "done" if s in DONE else "check" if s in CHECKING else "approved" if s in APPROVED_STATUSES else "recorded"


def group_chip(status) -> str:
    g = req_group(status)
    return (f'<span class="chip {GROUP_CHIP[g]}{" rec" if g == "recorded" else ""}" title="{esc(status or "unknown")}">'
            f'{esc(GROUP_WORD[g])}</span>')


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def short_date(v) -> str:
    d = _parse_iso(v)
    return f"{d.day} {d:%b}" if d else str(v or "")


def mini_bar(done: int, total: int) -> str:
    pct = round(100 * done / total) if total else 0
    return f'<span class="mb" aria-hidden="true"><i style="width:{pct}%"></i></span>'


def seg_bar(parts: list[tuple[str, int]], label: str = "") -> str:
    """A stacked bar, segments in the order given: [(css key, count)]."""
    return (f'<div class="sbar" role="img" aria-label="{esc(label)}">'
            + "".join(f'<i class="s-{k}" style="flex:{n}"></i>' for k, n in parts if n) + "</div>")


def nm_chip(text: str = "Not measured yet") -> str:
    return chip(text, "idle")


def nm_html(what: str, how: str = "") -> str:
    """A value the page cannot compute: the idle chip and a plain sentence; the way to measure it only inside a closed
    Technical detail card."""
    return (f'<p class="muted">{nm_chip()} {esc(what)}</p>'
            + (technical(f'<p class="codebox">How to measure: <code>{esc(how)}</code></p>') if how else ""))


def role_section(rid: str, name: str, asks: str, answer: str, chip_html: str, body: str) -> str:
    return (f'<section id="role-{rid}" class="card role" data-role="{rid}"><h2>{esc(name)}</h2>'
            f'<p class="asks">{esc(asks)}</p><p class="answer" data-answer>{esc(answer)} {chip_html}</p>{body}</section>')


def oblk(title: str, body: str, count: str = "", bid: str | None = None) -> str:
    """An open block inside a role section: h3 with its count at the right."""
    return (f'<div class="rb" id="{bid or "sec-" + sec_id(title)}"><h3>{esc(title)}'
            f'<span class="ct">{esc(count)}</span></h3>{body}</div>')


def cut(text, n: int) -> tuple[str, str]:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return (t, "") if len(t) <= n else (t[:n].rsplit(" ", 1)[0].rstrip(" ,;:-—–") + "…", t)


def ids_suffix(text: str) -> str:
    """Escaped text with every id in the small grey suffix style."""
    out, last = [], 0
    for m in ANY_ID_RE.finditer(text):
        out.append(esc(text[last:m.start()]))
        out.append(f'<span class="id">{esc(m.group(0))}</span>')
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


FILE_EXT = r"(?:md|py|json|ya?ml|ps1|sh|js|html|txt)"
SLASH_TOKEN_RE = re.compile(r"(?<![\w/.-])[\w.\-{}=]*(?:/[\w.\-{}=]+)+")
FILE_TOKEN_RE = re.compile(rf"(?<![\w/])[\w\-]+\.{FILE_EXT}\b")
IDENT_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b(?:=\w+)?")


def free_text(text) -> tuple[str, list[str]]:
    """Free prose from a record (next_action, blockers): path, route, branch, file and code-name tokens are replaced by a
    plain word ("a route", "a file") and returned for that card's closed Technical detail; ids become grey suffixes."""
    toks: list[str] = []

    def slash(m):
        tok = m.group(0)
        if tok.startswith("/"):
            kind = "a route"
        elif re.search(rf"\.{FILE_EXT}$", tok):
            kind = "a file"
        elif tok == tok.lower() and re.search(r"[\d_\-.]", tok):
            kind = "a branch or path"
        else:
            return tok            # "and/or", "Limited/Read-Only": ordinary words
        toks.append(tok)
        return kind

    def other(kind):
        def f(m):
            toks.append(m.group(0))
            return kind
        return f
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = SLASH_TOKEN_RE.sub(slash, t)
    t = FILE_TOKEN_RE.sub(other("a file"), t)
    t = IDENT_TOKEN_RE.sub(other("a code name"), t)
    t = re.sub(r"\bbranch (a (?:branch or path|route|file))", r"\1", t).replace("a branch or path", "a branch")
    return ids_suffix(t), toks


def which_cell(ids: list[str], n: int = 8) -> str:
    """The first n ids; the rest open in place (a native details), never a bare '+N'."""
    if len(ids) <= n:
        return esc(", ".join(ids))
    return (esc(", ".join(ids[:n])) + f' <details class="more inl"><summary>+{len(ids) - n} more</summary>'
            + esc(", ".join(ids[n:])) + "</details>")


# ---- readers for the role sections: each tells a missing source from an empty one ------------------------------

def read_releases(root: Path) -> list[dict] | None:
    """Release records; None when the project has no releases/ folder, [] when it holds none (README only)."""
    d = Path(root) / "releases"
    if not d.is_dir():
        return None
    out = []
    for p in sorted(glob.glob(str(d / "R-*.md"))):
        fm = _fm(Path(p))
        if fm is None:
            out.append({"id": Path(p).stem, "unreadable": True})
            continue
        out.append({"id": str(fm.get("id") or Path(p).stem), "kind": str(fm.get("kind") or "production"),
                    "version": str(fm.get("version") or ""), "date": str(fm.get("date") or ""),
                    "status": str(fm.get("status") or ""), "items": [str(x) for x in fm.get("items") or []],
                    "file": Path(p).name})
    return out


def read_architecture(root: Path) -> dict:
    """{'state': 'missing' | 'empty' | 'data', 'docs': [...], 'other': [...]}. 'empty' = the folder holds only its README."""
    root = Path(root)

    def doc(p: Path, folder: str) -> dict:
        try:
            first = next((ln[2:].strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("# ")), "")
        except (OSError, UnicodeDecodeError):
            first = ""
        out = _git(root, "log", "-1", "--format=%cs", "--", p.relative_to(root).as_posix())
        return {"title": first or p.stem, "file": p.name, "date": (out or "").strip(), "folder": folder}
    arch = root / "spec" / "architecture"
    docs = [doc(p, "architecture") for p in sorted(arch.glob("*.md")) if p.name.lower() != "readme.md"] if arch.is_dir() else []
    other = []
    for d, word in OTHER_DESIGN_DIRS:
        f = root / "spec" / d
        other += [doc(p, word) for p in sorted(f.glob("*.md")) if p.name.lower() != "readme.md"] if f.is_dir() else []
    for rel, word in (("docs/design", "design"), ("docs/spec", "spec")):       # the Factory keeps its design notes here
        f = root / rel
        other += [doc(p, word) for p in sorted(f.glob("*.md")) if p.name.lower() not in ("readme.md", "decisions.md")] if f.is_dir() else []
    return {"state": "missing" if not arch.is_dir() else "data" if docs else "empty", "docs": docs, "other": other}


def read_domain_rules(root: Path) -> int | None:
    """How many domain rules spec/testing/core-invariants.md names (numbered table rows and 'N —' notes of its first
    section); None when the file does not exist."""
    p = Path(root) / "spec" / "testing" / "core-invariants.md"
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    parts = re.split(r"(?m)^## ", text)
    first = parts[1] if len(parts) > 1 else ""
    nums = set(re.findall(r"(?m)^\|\s*(\d{1,3})\s*\|", first)) | set(re.findall(r"(?:^|[\s.,;(])(\d{1,3}) — ", first))
    return len(nums)


def _trigger_words(on) -> list[str]:
    names = [on] if isinstance(on, str) else list(on) if isinstance(on, (list, dict)) else []
    out = []
    for n in names:
        if n in ("pull_request", "pull_request_target"):
            out.append("every pull request")
        elif n == "push":
            br = on.get("push", {}).get("branches") if isinstance(on, dict) and isinstance(on.get("push"), dict) else None
            out.append(f"every push to {' and '.join(map(str, br))}" if br else "every push")
        elif n == "workflow_dispatch":
            out.append("when started by hand")
        elif n == "schedule":
            out.append("on a schedule")
        elif n == "workflow_call":
            out.append("when another workflow calls it")
        else:
            out.append(str(n).replace("_", " "))
    return out


def read_workflows(root: Path) -> list[dict]:
    """[{'name', 'triggers': [words], 'scheduled': bool, 'jobs': [display names]}] from .github/workflows."""
    out = []
    wf_dir = Path(root) / ".github" / "workflows"
    for p in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        on = data.get("on", data.get(True))
        jobs = data.get("jobs") if isinstance(data.get("jobs"), dict) else {}
        names = [str(j.get("name")) if isinstance(j, dict) and j.get("name") else str(k) for k, j in jobs.items()]
        out.append({"name": str(data.get("name") or p.stem), "triggers": _trigger_words(on),
                    "scheduled": "on a schedule" in _trigger_words(on), "jobs": names})
    return out


def commits_since_path(root: Path, rel: str) -> int | str:
    lc = ("log", "-1", "--format=%H", "--", rel)
    h = _git(root, *lc)
    if not h or not h.strip():
        return _unm(_git_cmd(*lc))
    rl = ("rev-list", "--count", f"{h.strip()}..HEAD")
    n = _git(root, *rl)
    return int(n) if n and n.strip().isdigit() else _unm(_git_cmd(*rl))


def commits_in_days(root: Path, now: datetime.datetime, days: int = 7) -> int | str:
    rl = ("rev-list", "--count", f"--since={_since(now, days)}", "HEAD")
    n = _git(root, *rl)
    return int(n) if n and n.strip().isdigit() else _unm(_git_cmd(*rl))


def work_state_words(w: dict, ages: dict) -> str:
    st = w.get("status")
    if st == "done":
        return "Done"
    if st in ("in_progress", "in_review"):
        a = ages.get(str(w.get("id")))
        return "Doing" + (f" · {age_words(a)}" if a is not None else "")
    return {"blocked": "Blocked", "dropped": "Dropped"}.get(st, "To do")


# ---- Summary (owner) -------------------------------------------------------------------------------------------

def summary_answer(c) -> tuple[str, str]:
    """'<needs-you text> · <track text>' and the chip: Needs attention / On track."""
    if c.oq is None:
        needs, need_attn = ("Needs you: not known, this project keeps no question records, so the page cannot tell whether "
                            "anything needs you"), False
    elif c.oq[0]:
        n = len(c.oq[0])
        needs, need_attn = f"{n} question{'s' if n != 1 else ''} need{'s' if n == 1 else ''} you", True
    else:
        needs, need_attn = "Nothing needs you", False
    gh = github_verdict(c.runs, c.head_full)
    stuck = [i for i in c.info["in_progress"] if i.get("stale")]
    n_changed = sum(1 for r in c.live if r["health"] == H_CHANGED)
    n_blocked = len(c.blocked_works)
    if gh and gh["state"] == "failed":
        track = f"Off track: {plural(gh['failed'], 'GitHub check')} failed"
    elif n_blocked:
        track = f"Off track: {plural(n_blocked, 'work item')} blocked"
    elif stuck:
        days = max(int(i["age_days"]) for i in stuck)
        first = display_title(stuck[0].get("title"), [str(stuck[0].get("id"))])[0]
        who = f"“{first}”" + (f" and {len(stuck) - 1} more" if len(stuck) > 1 else "")
        track = f"Off track: {who} {'has' if len(stuck) == 1 else 'have'} not moved for {days} days"
    elif n_changed:
        track = ("Needs a look: 1 requirement's proof needs re-checking" if n_changed == 1
                 else f"Needs a look: {n_changed} requirements' proof needs re-checking")
    else:
        track = "On track: nothing is blocked, failed or stuck"
    attn = need_attn or not track.startswith("On track")
    if not attn and c.oq is None:
        return f"{needs} · {track}", chip("Cannot tell if anything needs you", "idle")
    return f"{needs} · {track}", chip("Needs attention", "warn") if attn else chip("On track", "ok")


# ---- Product (product manager) ---------------------------------------------------------------------------------

def sec_product(c) -> tuple[str, str, str]:
    live = c.live
    total = len(live)
    cnt = {g: sum(1 for r in live if r["group"] == g) for g, _w, _k in GROUPS}
    blocked = sum(1 for r in live if r["health"] == H_BLOCKED)
    in_work = [r for r in live if r["group"] != "done" and r["open_work"]]
    no_work = [r for r in live if r["group"] == "approved" and not r["works_all"]]
    if not total:
        return "No requirements recorded yet", chip("Nothing yet", "idle"), '<p class="muted">No requirements recorded.</p>'
    # ONE partition everywhere: the answer line, the four tiles and the legend all print cnt[], and the four add up to total.
    # Blocked is a state inside the partition ("of which N blocked"), never a fifth group.
    answer = (f"{cnt['done']} of {total} requirements done · {cnt['check']} being checked · {cnt['approved']} approved, "
              f"not started · {cnt['recorded']} recorded, not approved" + (f" · of which {blocked} blocked" if blocked else ""))
    chip_html = (chip(f"{blocked} blocked", "warn") if blocked else chip(f"{len(in_work)} {'has' if len(in_work) == 1 else 'have'} open work", "idle") if in_work
                 else chip("On track", "ok"))
    # 3.1 coverage
    tiles_ = "".join(tile("cov-" + g, str(cnt[g]), GROUP_WORD[g]) for g, _w, _k in GROUPS)
    a = sum(1 for r in live if r["acs"] and r["verified"] is not None and r["verified"] == r["acs"])
    b = sum(1 for r in live if r["acs"] and r["verified"] == 0)
    legend = " · ".join(f"{GROUP_WORD[g]} {cnt[g]}" for g, _w, _k in GROUPS) + f" · {total} in all"
    extra = (f"Of the {total}, {blocked} {'is' if blocked == 1 else 'are'} blocked; {len(in_work)} "
             f"{'has' if len(in_work) == 1 else 'have'} a work item open; {len(no_work)} approved "
             f"{'has' if len(no_work) == 1 else 'have'} no work item yet.")
    n_unc = len(c.cov["decisions_uncovered"])
    see_data = '<a href="#role-data">See the data checks</a>' if n_unc else ""
    uncovered = f'<p>Decisions with no requirement: {chip(str(n_unc), "warn") if n_unc else n_unc} {see_data}</p>'
    cover = (f'<div class="strip cov">{tiles_}</div>'
             + seg_bar([(g, cnt[g]) for g, _w, _k in GROUPS], legend) + f'<p class="legend">{esc(legend)}</p>'
             + f'<p class="legend">{esc(extra)}</p>'
             + f"<p>All acceptance checks verified on {plural(a, 'requirement')}; none verified on {b}.</p>" + uncovered)
    # 3.2 by area
    areas: dict[str, list[dict]] = {}
    for r in live:
        areas.setdefault(r["section"] if r["section"] != "—" else "No area set", []).append(r)
    arows = sorted(areas.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    def arow(name, rs):
        d = sum(1 for r in rs if r["group"] == "done")
        bar = mini_bar(d, len(rs)) if d else '<span class="muted ns">Not started</span>'
        return (f'<li class="area"><span class="an">{esc(name)}</span><span class="ad">{d} of {len(rs)} done</span>{bar}</li>')
    shown = "".join(arow(n, rs) for n, rs in arows[:8])
    rest = "".join(arow(n, rs) for n, rs in arows[8:])
    area_body = (f'<ul class="areas">{shown}</ul>'
                 + (f'<details class="more"><summary>Show {len(arows) - 8} more</summary><ul class="areas">{rest}</ul></details>'
                    if rest else ""))
    # 3.3 requirements table
    return answer, chip_html, oblk("Coverage", cover) + oblk("By area", area_body, plural(len(arows), "area")) + c.req_table_blk + \
        sec("What a user gets", c.user_gets_body, str(c.n_user_gets), open_=True)


def requirements_table_block(c) -> tuple[str, str, int]:
    """(Requirements table block, 'What a user gets' body, n done for users)."""
    rows = c.rows
    cols = [("id", "Id"), ("title", "Requirement"), ("status", "Status"), ("checks", "Acceptance checks|Verified"),
            ("kind", "Kind / area"), ("section", "Area"), ("deps", "Depends on"), ("release", "Release"), ("health", "Health"),
            ("work", "Work item"), ("wstatus", "Work status"), ("tier", "Review level"), ("review", "Review PR")]
    prio = {"kind": "p2", "section": "p3", "deps": "p2", "release": "p2", "health": "p3", "work": "p3", "wstatus": "p3", "tier": "p3",
            "review": "p3"}
    data = [{**r, "status": group_chip(r["status"]), "checks": r["checks"],
             "kind": (str(r["layer"]).capitalize() + (f" · {r['section']}" if r["section"] != "—" else ""))} for r in rows]
    # the status filter compares the cell text, so its options are the four group words
    selects = [("f-req-status", "Any status", [w for _g, w, _k in GROUPS]),
               ("f-req-health", "Any health", HEALTHS),
               ("f-req-release", "Any release", sorted({r["release"] for r in rows}))]
    if any(r["section"] != "—" for r in rows):
        selects.append(("f-req-section", "Any section", sorted({r["section"] for r in rows if r["section"] != "—"})))
    body = (filters("q-req", "Filter requirements", selects, primary=1)
            + table(cols, data, "t-req", prio, cap=ROW_CAP, suffix=None, phone_rows=5, raw=frozenset({"status", "checks"})))
    done_users = [r for r in c.live if r["group"] == "done" and r["layer"] in ("feature", "polish")]
    n_base = sum(1 for r in c.live if r["group"] == "done") - len(done_users)
    users = ('<p class="muted">Every finished requirement a user can see or use (feature and polish), with the release that carries it.</p>'
             f'<p class="muted">Only Feature and Polish requirements count as something a user gets. The other {n_base} finished '
             f'{"requirement is" if n_base == 1 else "requirements are"} the base underneath (foundation and core) and '
             f'{"is" if n_base == 1 else "are"} not listed here.</p>') + ul([f'<li><span class="ttl">{esc(display_title(r["title"], [r["id"]])[0])}</span> <span class="id">{esc(r["id"])}</span> '
                f'<span class="muted">{esc(r["release"])}</span></li>' for r in done_users],
               "No user-facing requirement is done yet")
    return oblk("Requirements", body, f"{c.n_done} of {c.n_total} done"), users, len(done_users)


# ---- Architecture (architect) ----------------------------------------------------------------------------------

def sec_architecture(c) -> tuple[str, str, str]:
    live = c.live
    lanes = []
    for layer in LAYER_ORDER + (["other"] if any(r["layer"] not in LAYER_ORDER for r in live) else []):
        rs = [r for r in live if (r["layer"] if r["layer"] in LAYER_ORDER else "other") == layer]
        lanes.append((layer, rs, sum(1 for r in rs if r["group"] == "done")))
    by = {n: (rs, d) for n, rs, d in lanes}
    links = [(r, d) for r in live for d in r["dep_list"]]
    unfinished = {}
    for r, d in links:
        base = c.by_row.get(d)
        if base is not None and base["group"] != "done":
            unfinished[d] = unfinished.get(d, 0) + 1
    n_waiting = len({(r["id"], d) for r, d in links if d in unfinished})
    core_rs, core_d = by["core"]
    feat_done = by["feature"][1]
    early = feat_done if core_d < len(core_rs) else 0
    parts = [f"{n.capitalize()} {d}/{len(rs)}" for n, rs, d in lanes if n in LAYER_ORDER]
    if c.dep_state == "missing":
        deps_txt = "no dependencies recorded"
    else:
        deps_txt = f"{plural(len(links), 'dependency', 'dependencies')}, {n_waiting} waiting on an unfinished base"
    # layers that have finished work while the layer under them is not finished (any pair, not only core/feature)
    started_early = []
    for (pn, prs_, pd_), (cn, _crs, cd) in zip(lanes, lanes[1:]):
        if pn in LAYER_ORDER and cn in LAYER_ORDER and pd_ < len(prs_) and cd:
            started_early.append(f"{cn} started before {pn} was finished")
    answer = " · ".join(parts) + f" done · {deps_txt}" + "".join(f" · {x}" for x in started_early)
    if early:        # name the features themselves: with no dependencies recorded this is the only way to see the ordering
        names = [display_title(r["title"], [r["id"]])[0] for r in by["feature"][0] if r["group"] == "done"]
        shown = ", ".join(names[:2]) + (f" and {len(names) - 2} more" if len(names) > 2 else "")
        answer += f" · {plural(early, 'feature requirement')} done before core was finished ({shown})"
    core_unfinished = bool(core_rs) and core_d < len(core_rs) and (feat_done or by["polish"][1])
    chip_html = (chip("Layers out of order", "warn") if started_early or core_unfinished
                 else chip("Base not finished", "warn") if unfinished
                 else chip("No dependencies recorded", "idle") if c.dep_state == "missing" else chip("On track", "ok"))
    # 4.1 lanes
    cards, prev = [], None
    for n, rs, d in lanes:
        gc = {g: sum(1 for r in rs if r["group"] == g) for g, _w, _k in GROUPS}
        flag = (chip("Built before the layer under it was finished", "warn")
                if prev is not None and prev[2] < len(prev[1]) and d else "")
        counts = " · ".join(f"{GROUP_WORD[g]} {gc[g]}" for g, _w, _k in GROUPS)       # the four groups, adding up to the lane
        lis = "".join(f'<li><span class="ttl">{esc(display_title(r["title"], [r["id"]])[0])}</span> '
                      f'<span class="id">{esc(r["id"])}</span> {group_chip(r["status"])}</li>' for r in rs)
        cards.append(f'<div class="lane" data-lane="{n}"><h4>{esc(n.capitalize())}</h4><p class="ld">{d} of {len(rs)} done</p>'
                     + seg_bar([(g, gc[g]) for g, _w, _k in GROUPS], counts) + f'<p class="muted">{esc(counts)}</p>{flag}'
                     f'<details class="more"><summary>Show the {len(rs)} requirements</summary><ul>{lis}</ul></details></div>')
        prev = (n, rs, d)
    lanes_html = '<div class="lanes">' + '<span class="chev" aria-hidden="true">›</span>'.join(cards) + "</div>"
    # 4.2 what depends on what
    if c.dep_state == "missing":
        dep_body = (f'<p>{chip("Not recorded", "idle")} None of the {len(live)} requirements says which other requirement it '
                    f'depends on, so the page cannot show what depends on what and the build order cannot use dependencies. '
                    f'Record a dependency on a requirement and it appears here.</p>')
    elif not links:
        dep_body = '<p class="muted">No requirement depends on another.</p>'
    else:
        needed: dict[str, list[dict]] = {}
        for r, d in links:
            needed.setdefault(d, []).append(r)
        order = sorted(needed, key=lambda d: (d not in unfinished, -len(needed[d]), d))

        def base_row(d):
            br = c.by_row.get(d)
            head = (f'<span class="ttl">{esc(display_title(br["title"], [d])[0])}</span> <span class="id">{esc(d)}</span> '
                    f'{group_chip(br["status"])}' if br else f'<span class="ttl">An unknown requirement</span> <span class="id">{esc(d)}</span>')
            hold = f' <span class="chip bad">Not finished, holds up {len(needed[d])}</span>' if d in unfinished else ""
            by_ = "".join(f'<li class="nb">{esc(display_title(r["title"], [r["id"]])[0])} '
                          f'<span class="id">{esc(r["id"])}</span></li>' for r in needed[d])
            n_by = len(needed[d])
            return (f'<li class="base{" open-base" if d in unfinished else ""}">{head}{hold}'
                    f'<span class="sl">Needed by {plural(n_by, "requirement")}</span>'
                    f'<details class="more"><summary>Show the {plural(n_by, "requirement")}</summary><ul>{by_}</ul></details></li>')
        dep_body = (f'<ul class="bases">{"".join(base_row(d) for d in order[:6])}</ul>'
                    + (f'<details class="more"><summary>Show {len(order) - 6} more</summary><ul class="bases">'
                       f'{"".join(base_row(d) for d in order[6:])}</ul></details>' if len(order) > 6 else ""))
    if c.unreadable_reqs:
        dep_body += f'<p class="muted">{plural(c.unreadable_reqs, "requirement record")} could not be read.</p>'
    # 4.3 key decisions
    decs = c.decisions

    titles_by_id = {d["id"]: d["title"] for d in decs}
    titles_by_id.update({r["id"]: r["title"] for r in c.rows})

    def dec_title(did: str, title) -> str:
        """The row's bold lead sentence in full: "SPEC CHANGE to OD-22: <the change>" shows the change; ids are dropped
        (they follow as the grey suffix); words go through the page's word map. Never cut."""
        t = re.sub(r"\s+", " ", str(title or did)).strip()
        m = re.match(r"SPEC CHANGE to [^:]*:\s*(.+)$", t, re.I)
        t = (m.group(1) if m else t)
        t = ANY_ID_RE.sub("", map_words(t[:1].upper() + t[1:]))
        t = re.sub(r"\(\s*[,;]?\s*\)", "", t)
        t = re.sub(r",\s*\)", ")", re.sub(r"\s+([,;:.)])", r"\1", re.sub(r"\s+", " ", t)))
        return t.strip(" ,;:") or str(did)

    plain_dec = dec_title

    def changes_html(text: str) -> str:
        """'amends OD-31' with every known id shown as its plain title and the id as a grey suffix; an unknown id stays a
        grey suffix on its own."""
        out, last = [], 0
        for m in ANY_ID_RE.finditer(text):
            out.append(esc(text[last:m.start()]))
            i = m.group(0)
            out.append((f'{esc(plain_dec(i, titles_by_id[i]))} ' if i in titles_by_id else "") + f'<span class="id">{esc(i)}</span>')
            last = m.end()
        out.append(esc(text[last:]))
        return "".join(out)

    def relations(text: str) -> list[str]:
        """'amends A, B; extends C' -> ['amends A', 'amends B', 'extends C']: one relation per related record."""
        rels = []
        for part in re.split(r";\s*", text):
            part = part.strip()
            m = re.match(r"([a-z]+)\s+(.+)$", part)
            verb, rest = (m.group(1) + " ", m.group(2)) if m else ("", part)
            rels += [verb + x.strip() for x in re.split(r",\s*", rest) if x.strip()]
        return rels

    def dec_li(d):
        n = 0 if d["cited"] == "—" else len([x for x in d["cited"].split(",") if x.strip()])
        rels = [] if d["changes"] in ("", "—") else relations(d["changes"])
        ch = "".join(f'<span class="sl">{changes_html(x)}</span>' for x in rels[:2])
        if len(rels) > 2:         # at most two relations in words; the rest sit in a closed list
            ch += (f'<details class="more"><summary>Show {len(rels) - 2} more {"relation" if len(rels) == 3 else "relations"}</summary>'
                   + "".join(f'<span class="sl">{changes_html(x)}</span>' for x in rels[2:]) + "</details>")
        return (f'<li><span class="ttl">{esc(plain_dec(d["id"], d["title"]))}</span> <span class="id">{esc(d["id"])}</span>'
                f'<span class="sl">Cited by {plural(n, "requirement")}</span>{ch}</li>')
    top = sorted(decs, key=lambda d: (-(0 if d["cited"] == "—" else len(d["cited"].split(","))), d["id"]))[:5]
    top_ids = {d["id"] for d in top}
    latest = [d for d in sorted(decs, key=lambda d: (d["date"], d["id"]), reverse=True) if d["id"] not in top_ids][:3]
    key_body = (ul([dec_li(d) for d in top], "No decisions recorded.")
                + ('<h4>Latest (not already listed above)</h4>' + ul([dec_li(d) for d in latest], "") if latest else ""))
    # 4.4 system map
    a = c.arch
    if a["state"] == "data":
        map_body = ul([f'<li><span class="ttl">{esc(d["title"])}</span> <span class="muted">{esc(d["date"])}</span></li>' for d in a["docs"]], "")
    else:
        sub = ("This project has no architecture folder" if a["state"] == "missing"
               else "The architecture folder holds only its README")
        map_body = f'<p>No architecture written yet.</p><p class="muted">{esc(sub)}</p>'
    if a["other"]:
        oth = [f'<li><span class="ttl">{esc(display_title(d["title"])[0] or d["title"])}</span> <span class="muted">{esc(d["folder"])}</span></li>'
               for d in a["other"]]
        map_body += ("<h4>Other design documents</h4>" + ul(oth[:8], "")
                     + (f'<details class="more"><summary>Show {len(oth) - 8} more</summary>{ul(oth[8:], "")}</details>' if len(oth) > 8 else ""))
    map_body += technical('<p class="codebox">Folder: <code>spec/architecture</code></p>')
    id_key = ('<p class="muted idkey">What the small grey ids mean: REQ requirement · W work item · OD (or ADR) owner decision · '
              'PL plan · R release.</p>')
    body = (oblk("Layers", lanes_html + id_key)
            + '<div class="two">' + oblk("What depends on what", dep_body, plural(len(links), "link"))
            + oblk("Key decisions", key_body, f"{len(decs)} recorded") + "</div>" + oblk("System map", map_body)
            + sec("All owner decisions", c.dec_body, f"Show all {len(decs)}"))
    return answer, chip_html, body


# ---- Development (developer) -----------------------------------------------------------------------------------

def sec_development(c) -> tuple[str, str, str]:
    works = c.works
    doing = [w for w in works if w.get("status") in ("in_progress", "in_review")]
    blocked = [w for w in works if w.get("status") == "blocked"]
    wts = c.code_state.get("worktrees")
    if isinstance(wts, list):
        unsaved = [w["unsaved"]["count"] if isinstance(w.get("unsaved"), dict) else None for w in wts]
        never = sum(1 for w in wts if w.get("not_pushed") == "never pushed")
        saved_txt = ("unsaved files not known (git could not be read)" if any(u is None for u in unsaved)
                     else f"{plural(sum(unsaved), 'unsaved file')}")
        never_txt = plural(never, "branch never uploaded", "branches never uploaded")
    else:
        never, saved_txt, never_txt = 0, "unsaved files not known (git could not be read)", "branches never uploaded not known"
    open_prs = (c.prs or {}).get("open") if isinstance(c.prs, dict) else None
    wait_txt = f"{len(open_prs)} waiting to merge" if isinstance(open_prs, list) else "waiting to merge not known (GitHub was not asked)"
    # "Start here": the in-progress work item and its next action, else the first unblocked to-do work item, else the
    # first build-order requirement
    start = None
    unblocked_todo = next((w for w in works if w.get("status") not in ("done", "dropped", "blocked", "in_progress", "in_review")
                           and not w.get("blockers")), None)
    pick = (min(doing, key=lambda w: (c.ages.get(str(w.get("id"))) if c.ages.get(str(w.get("id"))) is not None else 10 ** 9, str(w.get("id"))))
            if doing else unblocked_todo)         # the in-progress item that moved most recently
    if pick is not None:
        start = {"kind": "work", "id": str(pick.get("id")), "title": display_title(pick.get("title"), [str(pick.get("id"))])[0],
                 "next": str(pick.get("next_action") or "")}
    elif c.build:
        open_w = {r["id"]: any(w.get("status") not in ("done", "dropped", "blocked") for w in r["works_all"]) for r in c.rows}
        sr = (next((b for b in c.build if b["state"] == "next" and open_w.get(b["id"])), None)
              or next((b for b in c.build if b["state"] == "next"), None) or c.build[0])
        start = {"kind": "req", "id": sr["id"], "title": display_title(sr["title"], [sr["id"]])[0], "next": ""}
    if start is not None:
        nxt = start["title"]
    elif c.build is None:
        nxt = "not known, the build order is not recorded"
    else:
        nxt = "nothing left to build"
    # 6.1 in progress: every card carries its branch chip; a branch goes to the first card that names its work item
    wt_branches = [x for x in (wts if isinstance(wts, list) else []) if x.get("branch") not in (None, "(detached)")]
    branches = wt_branches + [{"branch": b, "local_only": True} for b in c.code_state.get("local_branches") or []]
    used: set[int] = set()

    def take_branch(w: dict):
        """A local branch whose name contains the work item id, else a local branch named in the item's next_action text."""
        m = re.fullmatch(r"W-(\d+)", str(w.get("id")))
        if not m:
            return None
        rx = re.compile(rf"(?<![A-Za-z0-9])w-0*{int(m.group(1))}(?!\d)", re.I)
        for i, x in enumerate(branches):
            if i not in used and rx.search(str(x.get("branch"))):
                used.add(i)
                return with_state(x)
        text = str(w.get("next_action") or "")
        for i, x in enumerate(branches):
            name = str(x.get("branch"))
            if i not in used and name not in ("main", "master") and re.search(rf"(?<![\w/.-]){re.escape(name)}(?![\w/-])", text):
                used.add(i)
                return with_state(x)
        return None

    def with_state(x: dict) -> dict:
        if x.get("local_only") and "not_pushed" not in x:
            x["not_pushed"] = branch_upload_state(c.root, str(x.get("branch")))
        return x

    def branch_chip(branch) -> str:
        if branch is None:
            return chip("No branch yet", "idle bchip")
        up = branch.get("not_pushed")
        if up == "never pushed":
            return chip("Never uploaded", "warn bchip never")
        if is_unm(up):
            return chip("Upload state not known", "idle bchip")
        return chip("Uploaded", "ok bchip") + (f' <span class="sl">{plural(up, "commit")} not uploaded yet</span>' if isinstance(up, int) and up else "")

    def split_long(text, n: int = 300) -> tuple[str, str]:
        """(shown, rest): text up to 300 characters ends at a sentence end, never mid-sentence; a longer text shows its
        sentences up to the limit (or its first sentence) and the rest goes to the card's closed detail."""
        t = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(t) <= n:
            return t, ""
        ends = [m.end() for m in re.finditer(r"[.!?;](?=\s)", t)]
        k = max((e for e in ends if e <= n), default=None) or next((e for e in ends if e > n), None)
        return (t[:k].strip(), t[k:].strip()) if k else (t, "")

    def hide_branches(text: str) -> tuple[str, list[str]]:
        """A branch name written in free text becomes 'a branch' there; the name goes to the card's Technical detail."""
        found = []
        for x in branches:
            n = str(x.get("branch"))
            rx = rf"(?<![\w/.-]){re.escape(n)}(?![\w/-])"
            if n not in ("main", "master") and re.search(rx, text):
                text = re.sub(rx, "a branch", text)
                found.append(n)
        text = text.replace("branch a branch", "a branch")       # "built on branch X:" must not read "branch a branch:"
        return text, found

    cards = []
    for w in doing + blocked:
        wid = str(w.get("id"))
        age = c.ages.get(wid)
        reqs_ = [str(x) for x in w.get("requirement_ids") or []]
        rt = display_title(c.by_row[reqs_[0]]["title"], [reqs_[0]])[0] if reqs_ and reqs_[0] in c.by_row else ""
        step = next((f"{s.get('text')}" for p in c.plans or [] if not p.get("unreadable") for s in p["steps"]
                     if wid in [str(x) for x in s.get("refs") or []] and s.get("status") == "doing"), "")
        branch = take_branch(w)
        tech_bits: list[str] = []
        tech_rest: list[str] = []
        waiting = ""
        nxt_html = ""
        why = "; ".join(str(b) for b in w.get("blockers") or [])
        if w.get("status") == "blocked":
            shown_why, rest_why = split_long(why or str(w.get("next_action") or "Blocked"))
            shown_why, hb = hide_branches(shown_why)
            why_html, t1 = free_text(shown_why)
            tech_bits += hb + t1
            if rest_why:
                tech_rest.append(f"Rest of what it is waiting on: {rest_why}")
            waiting = f'<p class="blk-line">Waiting on: {why_html}</p>'
        if w.get("status") != "blocked" or w.get("blockers"):        # a blocked card without blockers already said its next_action
            nxt_t, nxt_rest = split_long(w.get("next_action"))
            if nxt_t and nxt_t != split_long(why)[0]:
                nxt_t, hb2 = hide_branches(nxt_t)
                nx_html, t2 = free_text(nxt_t)
                tech_bits += hb2 + t2
                if nxt_rest:
                    tech_rest.append(f"Rest of the next action: {nxt_rest}")
                nxt_html = f'<p class="sl">Next: {nx_html}</p>'
        if branch:
            tech_bits.insert(0, str(branch.get("branch")))
        tech = ""
        if tech_bits or tech_rest:
            tech = technical('<p class="codebox">' + "<br>".join(
                [f"<code>{esc(t)}</code>" for t in dict.fromkeys(tech_bits)] + [esc(t) for t in tech_rest]) + "</p>")
        cards.append(
            f'<li class="wc{" blocked" if w.get("status") == "blocked" else ""}" data-id="{esc(wid)}">'
            f'<p><span class="ttl">{esc(display_title(w.get("title"), [wid])[0])}</span> <span class="id">{esc(wid)}</span> '
            f'{chip("Blocked", "bad") if w.get("status") == "blocked" else chip("Doing", "accent")} '
            f'<span class="age">{esc(age_words(age))}</span></p>'
            + (f'<p class="sl">For: {esc(rt)}</p>' if rt else "")
            + (f'<p class="sl">Plan step: {esc(display_title(step)[0])}</p>' if step else "")
            + waiting + nxt_html + f'<p class="sl">Branch: {branch_chip(branch)}</p>' + tech + "</li>")
    # a branch nobody's card claimed is still counted: the "never uploaded" number in the answer equals the chips shown
    orphans = [x for i, x in enumerate(wt_branches) if i not in used and x.get("not_pushed") == "never pushed"]
    orphan_html = ""
    if orphans:
        orphan_html = ('<h4>Other branches never uploaded</h4><ul class="wcs">' + "".join(
            f'<li class="wc orphan"><p>A working copy not tied to any work item {chip("Never uploaded", "warn bchip never")}</p>'
            + technical(f'<p class="codebox"><code>{esc(x.get("branch"))}</code></p>') + "</li>" for x in orphans) + "</ul>")
    prog = ('<p class="muted"><a href="#role-summary">The full work board is in the summary</a></p>'
            + (f'<ul class="wcs">{"".join(cards)}</ul>' if cards else '<p class="muted">Nothing in progress</p>') + orphan_html)
    # unsaved files in working copies that no work item card is tied to
    tied = {id(branches[i]) for i in used}
    never_all = never + sum(1 for i in used if branches[i].get("local_only") and branches[i].get("not_pushed") == "never pushed")
    if isinstance(wts, list):
        never_txt = plural(never_all, "branch never uploaded", "branches never uploaded")
    answer = f"{len(doing)} in progress · {len(blocked)} blocked · start here: {nxt} · {saved_txt}, {never_txt}, {wait_txt}"
    chip_html = chip("Needs attention", "warn") if blocked or never_all else chip("On track", "ok")
    untied_files = sum(w_["unsaved"]["count"] for w_ in (wts if isinstance(wts, list) else [])
                       if isinstance(w_.get("unsaved"), dict) and id(w_) not in tied)
    code_note = (f'<p class="muted">{plural(untied_files, "unsaved file")} {"is" if untied_files == 1 else "are"} not tied to any work item.</p>'
                 if untied_files else "")
    # 6.3 pick up next
    if c.build is None:
        nxt_body = nm_html("The build order is not recorded, so the page cannot say what to build next. Generate the build order and it appears here.", "python tools/build_order.py .")
        nxt_ct = "Not measured yet"
    else:
        hasw = {r["id"]: r["works_all"] for r in c.rows}
        data = [{"id": b["id"], "title": display_title(b["title"], [b["id"]])[0], "state": b["state"], "layer": str(b["layer"]).capitalize(),
                 "risk": b["risk"], "work": ("Yes " + ", ".join(w["id"] for w in hasw[b["id"]])) if hasw.get(b["id"]) else "No"}
                for b in c.build]
        nxt_body = (table([("id", "Id"), ("title", "Requirement"), ("state", "State"), ("layer", "Kind"), ("risk", "Risk"),
                           ("work", "Has work item")], data, "t-next", {"layer": "p2", "risk": "p2", "work": "p2"}, cap=5, suffix=None)
                    if data else '<p class="muted">Nothing left to build.</p>')
        nxt_ct = f"{sum(1 for b in c.build if b['state'] == 'next')} next"
    if start:
        nx_s, nx_r = split_long(start["next"])
        nx_s, nx_b = hide_branches(nx_s)
        nx_h, nx_t = free_text(nx_s)
        nx_t = nx_b + nx_t
        start_html = (f'<p><b>Start here:</b> <span class="ttl">{esc(start["title"])}</span> <span class="id">{esc(start["id"])}</span></p>'
                      + (f'<p class="sl">Next: {nx_h}</p>' if nx_s else "")
                      + (technical('<p class="codebox">' + "<br>".join([f"<code>{esc(t)}</code>" for t in dict.fromkeys(nx_t)]
                                                                       + ([esc("Rest of the next action: " + nx_r)] if nx_r else [])) + "</p>")
                         if nx_t or nx_r else ""))
        nxt_body = start_html + nxt_body
    # 6.4 blocked and parked, 6.5 open issues; a work item already shown as a card above is not listed a second time
    card_ids = {str(w.get("id")) for w in doing + blocked}
    shown_bl = [h for wid, h in c.blockers if wid not in card_ids]
    n_bl = len(shown_bl)
    blk_body = ul(shown_bl, "Nothing else is blocked or parked." if card_ids else "No blocked work items or parked issues.") + (c.blockers_note or "")
    prog_ct = f"{len(doing)} in progress · {len(blocked)} blocked" if blocked else f"{len(doing)}"     # the block lists both kinds
    body = (oblk("In progress", prog, prog_ct)
            + '<div class="two">' + oblk("Code not finished", c.code_body + code_note, c.code_count)
            + oblk("Pick up next", nxt_body, nxt_ct) + "</div>"
            + (oblk("Blocked and parked", blk_body, str(n_bl)) if n_bl else sec("Blocked and parked", blk_body, "0"))
            + sec("Open issues", c.issues_body, c.issues_count))
    return answer, chip_html, body


# ---- Testing (QA lead) -----------------------------------------------------------------------------------------

def gh_run_rows(runs, head) -> list[dict]:
    """One row per job of the latest run of each workflow."""
    out, seen = [], set()
    for r in runs or []:
        name = r.get("workflowName") or r.get("name")
        if name in seen:
            continue
        seen.add(name)
        sha = str(r.get("headSha") or "")
        older = bool(sha and head and not str(head).startswith(sha[:7]))
        for j in r.get("jobs") or []:
            failed_step = next((str(s.get("name")) for s in j.get("steps") or [] if str(s.get("conclusion") or "") == "failure"), "")
            out.append({"job": j.get("name"), "conclusion": str(j.get("conclusion") or j.get("status") or ""),
                        "date": r.get("createdAt"), "older": older, "step": failed_step,
                        "url": str(r.get("url") or j.get("url") or "")})
    return out


def suite_plain(label: str) -> str:
    """The step name of a `<job key>/<step>` suite label; a label whose step is only a command keeps the job key."""
    job, _, step = str(label).partition("/")
    return job if not step or TEST_RUN_RE.search(step) else step


def sec_testing(c) -> tuple[str, str, str]:
    gh = github_verdict(c.runs, c.head_full)
    live = c.live
    v = sum(r["verified"] for r in live if r["verified"] is not None)
    m = sum(r["acs"] for r in live)
    z = sum(1 for r in live if r["acs"] and r["verified"] == 0)
    k_re = sum(r["recheck"] for r in live)
    s = len(c.missing)
    if gh is None:
        ghs = "GitHub: not run"
    elif gh["state"] == "failed":
        ghs = f"GitHub: {gh['failed']} failed"
    elif gh["state"] == "running":
        ghs = f"GitHub: {gh['n']} passed, {gh['running']} running ({gh['date']})"
    else:
        ghs = f"GitHub: all {gh['n']} passed ({gh['date']})"
    local_failed = sum(int(x.get("failed") or 0) for x in c.results or [])
    answer = (f"{ghs} · {v} of {m} acceptance checks verified" + (f" ({k_re} more need re-checking)" if k_re else "")
              + f" · {plural(z, 'requirement')} with none verified · "
              f"{plural(s, 'suite')} not run on this computer")
    if (gh and gh["state"] == "failed") or local_failed:
        chip_html = chip("Failed", "bad")
    elif k_re:
        chip_html = chip(f"{k_re} need re-check", "warn")
    elif s:
        chip_html = chip("Not run here", "idle")
    elif gh is None and not c.results:
        chip_html = chip("Nothing yet", "idle")
    else:
        chip_html = chip("All passed", "ok")
    # 7.1 failures
    fails = [(x.get("suite"), f) for x in c.results or [] for f in x.get("failures", [])]
    gh_fail = [j for j in gh_run_rows(c.runs, c.head_full) if j["conclusion"] == "failure"]
    fail_html = ""
    def gh_fail_li(j: dict) -> str:
        """The failed job, the failed step, the run date and a link to the run (GitHub carries no error text)."""
        url = j["url"] if j["url"].startswith("https://") else ""
        step = f' · step <b>{esc(j["step"])}</b>' if j["step"] else ""
        when = f" · run of {esc(short_date(j['date']))}" if j.get("date") else ""
        link = f' · <a href="{esc(url)}" target="_blank" rel="noopener">Open the run</a>' if url else ""
        return (f'<li class="fl"><b>{esc(j["job"])}</b> {chip("Failed", "bad")} <span class="muted">GitHub check{step}{when}{link}</span></li>')
    if not (fails or gh_fail) and gh is not None:
        fail_html = oblk("Failures", '<p class="muted">No failures in the latest GitHub run.</p>', "None")
    if fails or gh_fail:
        fail_html = oblk("Failures", ul(
            [f'<li class="fl"><b>{esc(f.get("name"))}</b> {chip("Failed", "bad")}<code class="err">{esc(f.get("first_error_line"))}</code></li>'
             for _suite, f in fails]
            + [gh_fail_li(j) for j in gh_fail], "")
            + ('<p class="muted">GitHub gives job results, not error text: open the run to read the error.</p>' if gh_fail else ""),
            str(len(fails) + len(gh_fail)))
    # 7.2 acceptance checks by requirement
    built = [r for r in live if r["group"] != "done" and r["open_work"]]
    done = [r for r in live if r["group"] == "done"]
    started = [r for r in live if r not in built and r not in done]

    def ac_state(res, ac):
        if res is not None and ac in res.fresh:
            return chip("Verified", "ok")
        if res is not None and ac in res.unpinned:
            return chip("Proof needs refreshing", "warn")
        if res is not None and ac in [x[0] for x in res.stale]:
            return chip("Changed, needs re-check", "warn")
        return chip("Not verified", "idle")

    def req_state(r):
        res = c.ev.get(r["id"])
        if not r["acs"]:
            return chip("None yet", "idle")
        if r["verified"] is None:
            return chip("Not required", "idle")
        if r["recheck"]:
            return chip(f"{r['verified']} verified, {r['recheck']} need re-check", "warn")
        return chip("All verified", "ok") if r["verified"] == r["acs"] else chip("Partly", "warn") if r["verified"] else chip("None yet", "idle")

    def req_row(r):
        res = c.ev.get(r["id"])
        crit = "".join(f'<li><span class="id">{esc(a["id"])}</span> {esc(cut(a["text"], 100)[0])} {ac_state(res, a["id"])}</li>'
                       for a in r["criteria"])
        cell = (f'<details class="rq"><summary>{esc(display_title(r["title"], [r["id"]])[0])}</summary><ul>{crit}</ul></details>'
                if crit else esc(display_title(r["title"], [r["id"]])[0]))
        n_re = r["recheck"]                                         # proof that does not count: stale or not pinned to the check text
        ver = ("—" if r["verified"] is None else f"{r['verified']} of {r['acs']}{mini_bar(r['verified'], r['acs'])}"
               + (f'<span class="sl">{n_re} need re-check</span>' if n_re else ""))
        return {"id": r["id"], "title": cell, "ver": ver, "state": req_state(r),
                "work": ", ".join(w["id"] for w in r["works_all"]) or "None"}

    def group(title, rs, open_):
        rs = sorted(rs, key=lambda r: (r["verified"] if r["verified"] is not None else 10 ** 6, r["id"]))
        t = sm_table([("id", "Id"), ("title", "Requirement"), ("ver", "Verified"), ("state", "State"), ("work", "Work item")],
                     [req_row(r) for r in rs], {"state": "p2", "work": "p2"}, raw=frozenset({"title", "ver", "state"}))
        inner = t if rs else '<p class="muted">None</p>'
        gv = sum(r["verified"] for r in rs if r["verified"] is not None)
        gm = sum(r["acs"] for r in rs)
        gs = sum(r["recheck"] for r in rs)
        tot = (f"{len(rs)}" + (" · all verified" if gm and gv == gm and not gs else f" · {gv} of {gm} checks verified" if gm else "")
               + (f" · {gs} need re-check" if gs else ""))
        return (f'<details class="sec grp"{" open" if open_ else ""}><summary><span>{esc(title)}</span>'
                f'<span class="ct">{esc(tot)}</span></summary><div class="bd">{inner}</div></details>')
    ac_body = group("Being built", built, True) + group("Done", done, False) + group("Not started", started, False)
    # 7.3 test suites
    rows, tech = [], []
    state = c.results_state
    for x in c.results or []:
        note = stale_note(x)
        res = chip("Failed", "bad") if int(x.get("failed") or 0) else chip("Passed", "ok")
        when = esc(short_date(x.get("time"))) + ((" " + chip("older version", "warn")) if note and note[1] == "warn" else "")
        rows.append({"suite": suite_plain(x.get("suite")), "where": "This computer", "result": res,
                     "pf": f"{x.get('passed', 0)} / {x.get('failed', 0)}", "when": when})
    for mi in c.missing:
        rows.append({"suite": suite_plain(mi["suite"]), "where": "This computer", "result": chip("Not run yet", "idle"),
                     "pf": "—", "when": "—"})
        tech.append(f'<p class="codebox">How to measure: <code>{esc(mi["run"])}</code></p>')
    for j in gh_run_rows(c.runs, c.head_full):
        txt, kind = JOB_CHIPS.get(j["conclusion"], (j["conclusion"].replace("_", " ").capitalize() or "Running", "idle"))
        rows.append({"suite": str(j["job"]), "where": "GitHub", "result": chip(txt, kind),
                     "pf": '<span title="GitHub gives job results, not test counts">—</span>',
                     "when": esc(short_date(j["date"])) + ((" " + chip("older version", "warn")) if j["older"] else "")})
    if c.runs is None:
        tech.append(f'<p class="codebox">How to measure: <code>{esc(GH_RUNS_CMD)}</code></p>')
    notes = {"missing": "", "failed": nm_html("The test results file could not be read, so no result is shown. Run the project's checks again to write a new one.", "python tools/ci_local.py"),
             "empty": '<p class="muted">The last run listed no suites.</p>', "data": ""}[state]
    if state == "missing":
        tech.append('<p class="codebox">How to measure: <code>python tools/ci_local.py</code></p>')
    suites_body = notes + (sm_table([("suite", "Suite"), ("where", "Where"), ("result", "Result"), ("pf", "Passed / Failed"),
                                     ("when", "When")], rows, {"pf": "p2", "when": "p2"}, raw=frozenset({"result", "pf", "when"}))
                           if rows else (nm_html("No test results are recorded yet. Run the project's checks on this computer and the results appear here.") if state == "missing" else ""))
    if state == "missing" and rows:
        suites_body = '<p class="muted">Not run yet on this computer.</p>' + suites_body
    suites_body += technical("".join(tech))
    # 7.4 steps that never ran
    g = c.gates
    if g["state"] == "unmeasured":
        never_body = nm_html("GitHub step history is not available: GitHub was not asked in this run. Fetch the recent runs and the steps that never ran appear here.",f"{GH_RUNS_CMD} and, for each run, {GH_JOBS_CMD}")
        never_ct = "Not measured yet"
    else:
        n_runs, _first, last = g["window"]
        items = []
        for gate, kind, wf in g["gates"]:
            words = (f"never ran in the {plural(n_runs, 'run')} checked (latest {short_date(last)})" if n_runs
                     else "never ran: no GitHub run was checked")                                          # one wording for both kinds
            note = ' <span class="muted">runs only when something fails</span>' if re.search(r"on failure", gate, re.I) else ""
            items.append(f'<li data-gate="{esc(gate)}" data-state="{kind}" data-workflow="{esc(wf)}"><b>{esc(gate.replace(" / ", ": "))}</b>: {words}{note}</li>')
        never_body = ul(items, "Every GitHub step ran at least once in the window.")
        if g.get("not_completed"):
            never_body += f'<p class="muted">{plural(g["not_completed"], "run")} had not finished and {"was" if g["not_completed"] == 1 else "were"} ignored.</p>'
        if g["no_detail"]:
            never_body += nm_html(f"{plural(g['no_detail'], 'run')} had no job detail.", GH_JOBS_CMD)
        never_ct = str(len(g["gates"]))
    # 7.5 known failure classes
    fnd = [r for r in c.iss_rows if r["type"] == "finding"]
    none_ = [r for r in fnd if r["status"] != "guarded"]
    cls_body = (f'<p class="muted">{len(fnd) - len(none_)} have an automatic check.</p><h4>No automatic check yet</h4>'
                + ul([f'<li>{esc(r["title"])} <span class="id">{esc(r["id"])}</span></li>' for r in none_], "None"))
    ac_note = ('<p class="muted">Only proof tied to the exact current wording of a check counts as verified. "Proof needs refreshing" '
               'means the check passed but its proof was written before proofs were tied to a check\'s wording, so nobody can tell '
               'whether the check was reworded since; "Changed, needs re-check" means the check was reworded after its proof was written. '
               'Neither is counted as verified.</p>')
    body = (fail_html + oblk("Acceptance checks by requirement", ac_note + ac_body, f"{v} of {m} verified")
            + oblk("Test suites", suites_body, plural(len(rows), "suite"))
            + (oblk("GitHub steps that never ran", never_body, never_ct) if g["state"] == "unmeasured" or g["gates"]
               else sec("GitHub steps that never ran", never_body, never_ct))
            + sec("Known failure classes", cls_body, f"{len(none_)} of {len(fnd)} have none"))
    return answer, chip_html, body


# ---- Releases (delivery / release manager) ---------------------------------------------------------------------

def plan_card(p: dict, c) -> str:
    if p.get("unreadable"):
        return f'<p class="muted">{chip("unreadable", "bad")} {esc(p["id"])}</p>'
    steps = [s for s in p["steps"] if s.get("status") != "dropped"]
    mism = {m["step"] for m in p["mismatch"]}
    now_step = next((s for s in steps if s.get("status") == "doing"), None)
    segs = "".join(f'<i class="sg {s.get("status") if s.get("status") in ("done", "doing") else "todo"}"></i>' for s in steps)
    head = (f'<div class="ph"><div><h3>{esc(display_title(p["title"], [p["id"]])[0])} <span class="id">{esc(p["id"])}</span></h3>'
            f'<p>{chip(str(p.get("status") or "").capitalize(), "accent" if p.get("status") == "active" else "idle")} '
            + (f"{p['done']} of {p['total']} steps done" if p["total"] else "No steps yet") + "</p></div></div>"
            + (f'<div class="track" role="img" aria-label="{p["done"]} of {p["total"]} steps done">{segs}</div>' if steps else "")
            + (f'<p class="now-line">Now: {esc(display_title(now_step.get("text"), [str(x) for x in now_step.get("refs") or []])[0])}</p>' if now_step else ""))

    def row(s):
        refs = [str(r) for r in s.get("refs") or []]
        ws = next((c.w_by_id[r] for r in refs if r in c.w_by_id), None)
        st = s.get("status") if s.get("status") in ("done", "doing") else "todo"
        warn = (" " + chip("Marked done, work not finished", "warn")) if s.get("id") in mism else ""
        txt = display_title(s.get("text"), refs)[0]
        nxt = ""
        if st == "doing" and ws and ws.get("next_action"):
            nxt = f'<span class="sl">{esc(cut(ws.get("next_action"), 120)[0])}</span>'
        return (f'<li data-step="{esc(s.get("id"))}" class="st {st}{" now" if st == "doing" else ""}">{_step_icon(s.get("status"))}'
                f'<span class="stt"><span class="ttl">{esc(txt)}</span>'
                + (f' <span class="id">{esc(", ".join(refs))}</span>' if refs else "") + (" " + chip("Now", "accent") if st == "doing" else "")
                + warn + nxt + "</span>"
                + (f'<span class="stw">{esc(work_state_words(ws, c.ages))}</span>' if ws else "") + "</li>")
    done_rows = [row(s) for s in steps if s.get("status") == "done"]
    other_rows = [row(s) for s in steps if s.get("status") != "done"]
    if len(done_rows) > 4:
        lis = f'<li class="st collapsed"><details class="more"><summary>{len(done_rows)} steps done</summary><ul class="steps">{"".join(done_rows)}</ul></details></li>' + "".join(other_rows)
    else:
        lis = "".join(done_rows + other_rows)
    track = f'<ul class="steps tl">{lis}</ul>' if steps else ""
    # change log: the plan file's own entries, newest first
    chg = sorted(p["changes"], key=lambda x: str(x.get("date") or ""), reverse=True)

    def chg_card(x):
        return (f'<div class="mini chg"><p><span class="chip idle">{esc(short_date(x.get("date")))}</span></p>'
                f'<p class="wnb was"><span class="lbl">Was</span><span>{esc(clean_prose(x.get("was")))}</span></p>'
                f'<p class="wnb now"><span class="lbl">Now</span><span>{esc(clean_prose(x.get("now")))}</span></p>'
                f'<p class="sl">Because {esc(clean_prose(x.get("why")))}</p></div>')
    since = p["commits_since_change"]
    foot = (f'Last changed {short_date(p["last_change"])} · ' + (since if is_unm(since) else f"{plural(since, 'commit')} since"))
    right = ("".join(chg_card(x) for x in chg[:3])
             + (f'<details class="more"><summary>Show {len(chg) - 3} more</summary>{"".join(chg_card(x) for x in chg[3:])}</details>' if len(chg) > 3 else "")
             if chg else '<p class="muted">No changes since the plan was made</p>')
    return (f'<div class="plan" data-plan="{esc(p["id"])}">{head}<div class="pcols"><div class="ptrack">{track}</div>'
            f'<div class="pchg"><h4>How this plan changed</h4>{right}<p class="muted">{esc(foot)}</p></div></div></div>')


def release_counts_words(named_by: list[str], listed: list[str]) -> str:
    """How many requirements name a release in their own `release` field against how many its record lists. Both counts
    are printed when they differ and "counts agree" when the two lists are the same, so a reader never has to wonder."""
    n = plural(len(named_by), "requirement")
    if set(named_by) == set(str(i) for i in listed) and len(named_by) == len(listed):
        return f"{n}, counts agree"
    if len(named_by) != len(listed):
        return f"{n} (record lists {len(listed)})"
    return f"{n} (record lists as many, but not the same ones)"


def delivery_html(m: dict | None) -> str:
    """The delivery block: every number derived, or `capped` / `unmeasured: <reason>`; no data is never zero."""
    if m is None:
        return ('<p class="muted">Delivery numbers: not fetched. Build the page with the fetch option and they appear here.</p>'
                + technical('<p class="codebox">How to measure: <code>python tools/delivery_metrics.py . --since YYYY-MM-DD</code></p>'))

    def val(v, fn):
        return f'<span class="muted">{esc(v)}</span>' if isinstance(v, str) else esc(fn(v))
    kinds = {"product": "product code", "tests": "tests", "docs": "docs, spec and process", "generated": "generated"}
    rows = [
        ("Merged pull requests", val(m["prs"], lambda p: f"{p['count']} (" + ", ".join(
            f"{kinds.get(k, k)} {n}" for k, n in p["by_kind"].items() if n) + ")")),
        ("Lines added", val(m["prs"], lambda p: ", ".join(f"{kinds[k]} {n}" for k, n in p["lines_added"].items()))),
        ("CI runs", val(m["ci"], lambda c_: f"{c_['count']} (" + ", ".join(f"{k} {n}" for k, n in c_["conclusions"].items()) + ")")),
        ("Merge-main commits", val(m["merge_main"], lambda x: f"{x['merge_main']} of {x['commits']} commits on main")),
        ("Review rounds per item", val(m["review_rounds"], lambda r: f"{r['items']} items, highest round {r['max_round']}")),
    ]
    return ("<ul>" + "".join(f'<li><span class="ttl">{esc(k)}</span> {v}</li>' for k, v in rows) + "</ul>"
            f'<p class="muted">{esc(m["since"])} to {esc(m["until"])}; pull requests are classified by the files they changed.</p>')


def sec_releases(c) -> tuple[str, str, str]:
    recs = [r for r in c.releases or [] if not r.get("unreadable")]
    live = c.live
    rel_ids = {r["id"] for r in recs}
    # delivered before tracking began never belonged to a release, so it is not "done, not released"
    # released = the requirement's own release field names a release record, OR a release record lists it; a release value that
    # names no record (a target such as V1) is not a release
    listed = {str(i) for r in recs for i in r["items"]}
    done_unreleased = [r for r in live if r["group"] == "done" and r["status"] != "Delivered-before-trace"
                       and r["rel_field"] not in rel_ids and r["id"] not in listed]
    # answer
    plan_next = ""
    for p in c.plans or []:
        if p.get("unreadable") or p.get("status") != "active":
            continue
        s = next((s for s in p["steps"] if s.get("status") == "doing"), None) or next((s for s in p["steps"] if s.get("status") == "todo"), None)
        if s:
            plan_next = display_title(s.get("text"), [str(x) for x in s.get("refs") or []])[0]
            break
    if recs:
        last = max(recs, key=lambda r: (r["date"], _ver(r["version"]) or ()))
        since = commits_since_path(c.root, f"releases/{last['file']}")
        answer = (f"Last release: {last['kind']} {last['version']}, {short_date(last['date'])} ({last['id']}) · "
                  + (f"{since} commits since" if isinstance(since, int) else "commits since: not measured yet")
                  + (f" · next plan step: {plan_next}" if plan_next else ""))
        chip_html = (chip(f"{len(done_unreleased)} done, not released", "warn") if done_unreleased
                     else chip(f"Released {short_date(last['date'])}", "ok"))
    else:
        tgt: dict[str, int] = {}
        for r in live:
            if r["rel_field"]:
                tgt[r["rel_field"]] = tgt.get(r["rel_field"], 0) + 1
        week_n = commits_in_days(c.root, c.now_dt, 7)
        part = ""
        if tgt:
            v, n = max(tgt.items(), key=lambda kv: (kv[1], kv[0]))
            done_v = sum(1 for r in live if r["rel_field"] == v and r["group"] == "done")
            part = (f" · ships next: release {v} ({plural(n, 'requirement')} target it, {done_v} done, {n - done_v} to go)")
        if not tgt and c.build:
            part = f" · next to build: {cut(display_title(c.build[0]['title'], [c.build[0]['id']])[0], 50)[0]}"
        answer = ("No release yet" if c.releases is not None else "This project keeps no release records") + part + \
            (f" · {week_n} commits in the last 7 days" if isinstance(week_n, int) else "")
        chip_html = chip("Nothing released", "idle")
    # 5.1 plans
    if c.plans is None:
        plans_body = '<p>No plan records yet.</p><p class="muted">Plans written only as documents are not shown here.</p>'
        plans_ct = "No plan records yet"
    elif not c.plans:
        plans_body = '<p>The plans folder holds no plan yet.</p>'
        plans_ct = "0 active"
    else:
        act = [p for p in c.plans if p.get("status") == "active"]
        rest = [p for p in c.plans if p.get("status") != "active"]
        plans_body = "".join(plan_card(p, c) for p in act) or '<p class="muted">No active plan.</p>'
        if rest:
            plans_body += f'<details class="more"><summary>Finished plans ({len(rest)})</summary>{"".join(plan_card(p, c) for p in rest)}</details>'
        plans_ct = f"{len(act)} active of {len(c.plans)}"
    # 5.2 ships next
    def capped_ul(items: list[str], n: int, empty: str) -> str:
        """The first n items; the rest open under 'and N more'."""
        if len(items) <= n:
            return ul(items, empty)
        return ul(items[:n], empty) + f'<details class="more"><summary>and {len(items) - n} more</summary>{ul(items[n:], "")}</details>'
    left = (capped_ul([f'<li><span class="ttl">{esc(display_title(r["title"], [r["id"]])[0])}</span> <span class="id">{esc(r["id"])}</span>'
                       + (f' <span class="muted">{esc(r["release"])}</span>' if r["rel_field"] else "") + "</li>"
                       for r in done_unreleased], 8, "None")
            + ('<p class="muted">No release record lists these.</p>' if done_unreleased else ""))
    nxt3 = capped_ul([f'<li><span class="ttl">{esc(display_title(b["title"], [b["id"]])[0])}</span> <span class="id">{esc(b["id"])}</span></li>'
                      for b in (c.build or [])], 3, "None")
    ships = f'<div class="two"><div><h4>Done, not in a release</h4>{left}</div><div><h4>Next to build</h4>{nxt3}</div></div>'
    # 5.3 releases
    if c.releases is None:
        rel_body = '<p>This project keeps no release records.</p>'
    elif not recs and not c.releases:
        tg = sorted({r["rel_field"] for r in live if r["rel_field"]})
        rel_body = "<p>No release records yet." + (f" {len(live)} requirements target {esc(', '.join(tg))}." if tg else "") + "</p>"
    else:
        lis = []
        for r in sorted(recs, key=lambda r: (r["date"], r["id"]), reverse=True):
            by_field = [x for x in live if x["rel_field"] == r["id"]]
            counts = release_counts_words([x["id"] for x in by_field], r["items"])
            titles = "; ".join(display_title(x["title"], [x["id"]])[0] for x in by_field[:6]) + (f" and {len(by_field) - 6} more" if len(by_field) > 6 else "")
            lis.append(f'<li><span class="ttl">{esc(r["kind"].capitalize())} {esc(r["version"])}</span> <span class="id">{esc(r["id"])}</span> '
                       f'<span class="muted">{esc(short_date(r["date"]))} · {esc(counts)}</span>'
                       + (f'<span class="sl">{esc(titles)}</span>' if titles else "") + "</li>")
        rel_body = ul(lis, "No release records yet.")
    # 5.4 what changed
    merged = (c.prs or {}).get("merged") if isinstance(c.prs, dict) else None
    mlines = c.merged_html
    commits = c.recent
    if commits is None:
        cm = nm_html("Recent commits could not be read from git, so none are listed. Run this page's builder inside the project's repository.", "git log -20")
    else:
        byday: dict[str, list[str]] = {}
        for ln in commits:
            _h, _, rest_ = ln.partition("|")
            d, _, subj = rest_.partition("|")
            byday.setdefault(d, []).append(subj)
        flat = [(d, s) for d in sorted(byday, reverse=True) for s in byday[d]]

        def cm_ul(items):
            out_, lastd = "", None
            for d, s in items:
                if d != lastd:
                    out_ += (f"</ul>" if lastd else "") + f'<h4 class="day">{esc(_day_label(d))}</h4><ul>'
                    lastd = d
                out_ += f"<li>{esc(s)}</li>"
            return out_ + "</ul>" if items else '<p class="muted">No stage change recorded yet.</p>'
        cm = cm_ul(flat[:8]) + (f'<details class="more"><summary>Show {len(flat) - 8} more</summary>{cm_ul(flat[8:])}</details>' if len(flat) > 8 else "")
    changed = f"<h4>Merged in the last {MERGED_DAYS} days</h4>{mlines}<h4>Recent commits</h4>{cm}"
    body = (oblk("Plans", plans_body, plans_ct, bid="plans") + f'<div class="two top">' + oblk("Ships next", ships) + oblk("Releases", rel_body, plural(len(recs), "release")) + "</div>"
            + oblk("Delivery (last 14 days)", delivery_html(c.delivery), "", bid="delivery")
            + sec("What changed", changed, "Merged pull requests and recent commits"))
    return answer, chip_html, body


# ---- Operations (operations / deployment) ----------------------------------------------------------------------

def sec_operations(c) -> tuple[str, str, str]:
    recs = [r for r in c.releases or [] if not r.get("unreadable")]
    prod = sorted([r for r in recs if r["kind"] == "production" and r["status"] == "deployed"], key=lambda r: (r["date"], r["id"]), reverse=True)
    kit_rel = sorted([r for r in recs if r["kind"] == "kit" and r["status"] == "released" and _ver(r["version"])],
                     key=lambda r: _ver(r["version"]), reverse=True)
    k = c.kit
    installed = k.get("own") if k["mode"] == "project" else k.get("template")
    latest = kit_rel[0] if kit_rel else None
    if k["mode"] == "factory":
        kit_line = f"the Factory runs no server; it ships kit releases" + (f" (latest {latest['version']}, {short_date(latest['date'])})" if latest else "")
    else:
        kit_line = (f"kit {installed} (the Factory holds the latest kit version; this project cannot see it)" if installed
                    else "kit version cannot be read from this project")
    behind = bool(installed and latest and k["mode"] == "project" and _ver(installed) and _ver(latest["version"]) and _ver(installed) < _ver(latest["version"]))
    if prod:
        prev = prod[1] if len(prod) > 1 else None
        answer = (f"Production runs {prod[0]['version']} since {short_date(prod[0]['date'])} · undo: "
                  + (f"back to {prev['version']}" if prev else "no earlier version recorded"))
        chip_html = chip("Deployed", "ok")
    else:
        answer = "Not deployed: " + (kit_line if k["mode"] == "factory" else "no production deploy recorded · " + kit_line)
        chip_html = chip("Not deployed", "idle")
    if behind:
        chip_html = chip("Kit behind", "warn")
    # 8.1 environments
    wfs = c.workflows
    stg = [w for w in wfs if "staging" in w["name"].lower() or any("staging" in j.lower() for j in w["jobs"])]
    gh_txt = "; ".join(f"{w['name']}: {' and '.join(w['triggers']) or 'no trigger'}" for w in wfs) or "No workflows"
    sched = [w for w in wfs if w["scheduled"]]
    env_rows = [
        # the last deploy is the Production row: version, and the date in Since
        {"env": "Production", "runs": (f"{prod[0]['kind'].capitalize()} {prod[0]['version']}, last deployed {short_date(prod[0]['date'])}" if prod
                                       else "Nothing deployed: no production deploy is recorded"),
         "since": short_date(prod[0]["date"]) if prod else "—", "source": "Release records (production, deployed)" if prod else "No production release record"},
        {"env": "Staging", "runs": ", ".join(w["name"] for w in stg) if stg
         else "No staging environment is recorded: no workflow or job name mentions staging.", "since": "—",
         "source": "Workflow and job names" if stg else "Workflow and job names, none mention staging"},
        {"env": "GitHub", "runs": gh_txt, "since": "—", "source": "Workflow files"},
        {"env": "Scheduled jobs", "runs": ", ".join(w["name"] for w in sched) if sched else "No scheduled jobs", "since": "—", "source": "Workflow files"}]
    for er in env_rows:      # the Source column is hidden on a phone, so the source also sits as a second line under the value
        er["runs"] = f'{esc(er["runs"])}<span class="sl sm-only">Source: {esc(er["source"])}</span>'
    env_cols = [("env", "Environment"), ("runs", "What runs"), ("since", "Since"), ("source", "Source")]
    if all(er["since"] == "—" for er in env_rows):      # an all-empty column is not shown
        env_cols = [x for x in env_cols if x[0] != "since"]
    env_body = sm_table(env_cols, env_rows, {"since": "p2", "source": "p2"}, raw=frozenset({"runs"}))
    # 8.2 undo
    if prod:
        undo = (f"<p>Back to {esc(prod[1]['version'])} ({esc(short_date(prod[1]['date']))}).</p>" if len(prod) > 1
                else "<p>No earlier version is recorded.</p>")
    else:
        undo = "<p>Nothing to undo: nothing is deployed.</p>"
    undo += ("<p>A production deploy needs the owner's typed authorization.</p>"
             + ('<p class="muted">No rollback plan is recorded. Write one before the next production deploy.</p>' if prod
                else '<p class="muted">No rollback plan is recorded. None is needed until the first production deploy; write one before it.</p>'))
    kit_html, kit_count = c.kit_html
    body = oblk("Environments", env_body) + oblk("How to undo", undo) + oblk("Kit in this project", kit_html, kit_count)
    return answer, chip_html, body


# ---- Data checks (domain owner) --------------------------------------------------------------------------------

def data_checks(c) -> list[dict]:
    """The nine cross-checks. state: agrees | differs | nm (not measured) | na (not applicable); ids that differ."""
    live = c.live
    out = []

    def add(text, ids=None, state=None, tech="", why="", na_why="", pop=0, noun="requirements", mass_all=""):
        st = state or ("differs" if ids else "agrees")
        mass = ""
        if ids and pop > 1 and len(ids) == pop:       # every record differs: one sentence, not a list of ids
            mass = mass_all or f"All {pop} {noun} differ."
        elif ids and len(ids) > 20:
            mass = f"{len(ids)} of {pop} {noun} differ." if pop >= len(ids) else f"{len(ids)} {noun} differ."
        out.append({"check": text, "state": st, "ids": ids or [], "tech": tech, "why": why, "na_why": na_why, "mass": mass})
    add("Every requirement marked done has all its acceptance checks verified",
        [r["id"] for r in live if r["status"] in DONE and r["acs"] and r["verified"] is not None and r["verified"] < r["acs"]],
        why="A requirement called done without all its checks verified is done on trust.", pop=len(live))
    add("No requirement has all its acceptance checks verified while its status says it is not done",
        [r["id"] for r in live if r["group"] != "done" and r["acs"] and r["verified"] is not None and r["verified"] == r["acs"]],
        why="Proof that is complete while the status is behind means finished work is not counted.")
    if c.plans:
        mm = [f"{p['id']} {m['step']}" for p in c.plans if not p.get("unreadable") for m in p["mismatch"]]
        add("Plan steps marked done have their work finished", mm,
            why="A step ticked done while its work is still open misleads whoever follows the plan.")
    else:
        add("Plan steps marked done have their work finished", state="na",
            why="A step ticked done while its work is still open misleads whoever follows the plan.",
            na_why="This project has no plan records, so there is no step to compare.")
    add("No proof is out of date with its acceptance check", [r["id"] for r in live if r["stale"]],
        why="Proof written for an older wording of a check does not prove the new wording.", pop=len(live))
    add("Every proof is pinned to its acceptance check text", [r["id"] for r in live if r["unpinned"]],
        why="Proof that is not pinned cannot notice when the check it proves is reworded.", pop=len(live))
    add("Every owner decision is covered by a requirement", list(c.cov["decisions_uncovered"]),
        why="A decision no requirement carries may never be built.", noun="decisions")
    rel_ids = {r["id"] for r in c.releases or [] if not r.get("unreadable")}
    named = [r for r in live if r["rel_field"]]
    no_rec = [r["id"] for r in named if r["rel_field"] not in rel_ids]
    names = sorted({r["rel_field"] for r in named if r["rel_field"] not in rel_ids})
    add("Every release named on a requirement has a release record", no_rec,
        why="A requirement that names a release with no record claims something nobody can check.", pop=len(named),
        mass_all=(f"All {len(named)} requirements that name a release name {', '.join(names)}, which has no release record."
                  if len(names) == 1 else f"All {len(named)} requirements that name a release name one with no release record "
                  f"({', '.join(names)})."))
    if c.issues is None:
        add("Every issue is linked to a requirement", state="nm", tech=GH_ISSUES_CMD,
            why="An issue tied to no requirement is work nobody can trace to a need.",
            na_why="Not measured here: the issues were not fetched from GitHub in this run.")
    else:
        add("Every issue is linked to a requirement", [r["id"] for r in c.iss_rows if r["type"] == "issue" and r["rel"] == UNMAPPED],
            why="An issue tied to no requirement is work nobody can trace to a need.", noun="issues",
            pop=sum(1 for r in c.iss_rows if r["type"] == "issue"))
    add("The page's generated views are current", state="nm", tech="; ".join(CHECK_COMMANDS),
        why="A generated view that is out of date shows numbers that were true once.",
        na_why="Not measured here: this page does not run the generator checks. Run them (see Technical detail) and compare.")
    return out


def sec_data(c) -> tuple[str, str, str]:
    checks = data_checks(c)
    counted = [x for x in checks if x["state"] != "na"]
    ag = sum(1 for x in counted if x["state"] == "agrees")
    df = sum(1 for x in counted if x["state"] == "differs")
    nm = sum(1 for x in counted if x["state"] == "nm")
    na = len(checks) - len(counted)
    age = _parse_iso((_git(c.root, "log", "-1", "--format=%cI") or "").strip())
    # the time is printed as text, so the page reads the same with scripts off (the header pill adds the relative age)
    off = age.utcoffset() if age else None
    mins = int(off.total_seconds() // 60) if off is not None else 0
    tz = "UTC" if not mins else f"UTC{'+' if mins > 0 else '-'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"
    asof = (f" · data as of {c.sha_short or 'an unknown version'}" + (f", committed {age.day} {age:%b %H:%M} {tz}" if age else ""))
    answer = (f"{ag} of {len(counted)} applicable checks agree · {df} need attention · {nm} not measured"
              + (f" · {na} not applicable" if na else "") + asof)
    chip_html = chip(f"{df} need attention", "warn") if df else chip("All agree", "ok")
    chips = {"agrees": chip("Agrees", "ok"), "differs": chip("Differs", "warn"), "nm": nm_chip(), "na": chip("Not applicable", "idle")}

    def which_or_sentence(x: dict) -> str:
        if not x["mass"]:
            return which_cell(x["ids"])
        return (esc(x["mass"]) + f' <details class="more inl"><summary>Show all {len(x["ids"])} ids</summary>'
                + esc(", ".join(x["ids"])) + "</details>")

    def check_cell(x: dict) -> str:
        out_ = esc(x["check"]) + (f'<span class="sl">{esc(x["why"])}</span>' if x["why"] else "")
        if x["state"] in ("nm", "na") and x["na_why"]:
            out_ += f'<span class="sl">{esc(x["na_why"])}</span>'
        if x["ids"]:        # the Which column is hidden on a phone: the ids also sit under the check
            out_ += f'<span class="sl sm-only">Differs: {which_or_sentence(x)}</span>'
        return out_
    rows = [{"check": check_cell(x), "result": chips[x["state"]], "count": "—" if x["state"] in ("nm", "na") else str(len(x["ids"])),
             "which": which_or_sentence(x) if x["ids"] else ""} for x in checks]
    tech = "".join(f'<p class="codebox">How to measure: <code>{esc(x["tech"])}</code></p>' for x in checks if x["tech"])
    table_html = sm_table([("check", "Check"), ("result", "Result"), ("count", "Count"), ("which", "Which")], rows,
                          {"which": "p2"}, raw=frozenset({"check", "result", "which"}))
    body = oblk("Cross-checks", table_html + technical(tech),
                f"{ag} agree · {df} differ · {nm} not measured" + (f" · {na} not applicable" if na else ""))
    body += sec("Overall numbers", c.overall_html, f"{c.n_done}/{c.n_total} {c.done_word}")
    if c.domain_rules is not None:
        body += oblk("Domain rules", f'<p>This project names {c.domain_rules} domain rules. The page cannot say which tests '
                                     f'prove them: that link is not recorded anywhere yet. {nm_chip()}</p>')
    else:
        body += oblk("Domain rules", '<p>This project has not written down any domain rules, so there is nothing to compare '
                                     'its tests against.</p>')
    return answer, chip_html, body


# ---- the page --------------------------------------------------------------------------------------

def _parse_stamp(text) -> datetime.datetime | None:
    """The --now text as a time: ISO 8601, or 'YYYY-MM-DD HH:MM TZ' (UTC read as UTC, other names as local)."""
    t = _parse_iso(text)
    if t:
        return t
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})(?: (\S+))?", str(text).strip())
    if not m:
        return None
    t = datetime.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    return t.replace(tzinfo=datetime.timezone.utc) if (m.group(3) or "").upper() in ("UTC", "Z", "GMT") else t.astimezone()


def render(root: Path, issues: list[dict] | None, runs: list[dict] | None, *, now: str | None = None,
           sha: str | None = None, title: str | None = None, prs: dict | None = None,
           code_state: dict | None = None, delivery: dict | None = None) -> tuple[str, dict]:
    """`prs` is read_prs()'s answer (gh); None means it was not fetched and the page says unmeasured.
    `delivery` is delivery_metrics.collect()'s answer; None means not fetched (the block says so, never zero)."""
    root = Path(root)
    code_state = code_state if code_state is not None else read_code_state(root)
    main_co = code_state.get("main_checkout")
    project = Path(main_co).name if isinstance(main_co, str) and not is_unm(main_co) else root.resolve().name
    title = title or f"{project} Status"
    if now is None:
        now_dt = datetime.datetime.now().astimezone().replace(microsecond=0)
        now = now_dt.isoformat()
    else:
        now_dt = _parse_stamp(now)
    now_iso = now_dt.isoformat(timespec="seconds") if now_dt else ""
    now_dt = now_dt or datetime.datetime.now().astimezone()
    if sha is None:
        out = _git(root, "rev-parse", "--short", "HEAD")
        sha = out.strip() if out and out.strip() else None
    sha_html = esc(sha) if sha else "unmeasured</span> <span class=\"muted\">(git rev-parse --short HEAD)"

    reqs, works, findings = read_requirements(root), read_works(root), read_findings(root)
    TITLE_CTX.clear()
    for r_ in reqs:
        TITLE_CTX[str(r_["id"])] = {"title": r_.get("title"), "display_title": r_.get("display_title"), "related": []}
    for w_ in works:
        TITLE_CTX[str(w_["id"])] = {"title": w_.get("title"), "display_title": w_.get("display_title"),
                                    "related": [str(x) for x in w_.get("requirement_ids") or []]}
    for f_ in sorted(glob.glob(str(root / "releases" / "R-*.md"))):
        d_ = _fm(Path(f_)) or {}
        TITLE_CTX[str(d_.get("id", Path(f_).stem))] = {
            "title": f"{str(d_.get('kind') or 'Project').capitalize()} release", "related": [str(x) for x in d_.get("items") or []]}
    steps_: dict = {}
    for pl_ in read_plans(root) or []:
        if pl_.get("unreadable"):
            continue
        TITLE_CTX[str(pl_["id"])] = {"title": pl_.get("title"), "related": []}
        for st_ in pl_.get("steps") or []:
            steps_.setdefault(str(st_.get("id")), [str(x) for x in st_.get("refs") or []])
    TITLE_CTX["_steps"] = steps_
    w_of: dict[str, list[dict]] = {}
    for w in works:
        for rid in w.get("requirement_ids") or []:
            w_of.setdefault(rid, []).append(w)
    by_req = {r["id"]: r for r in reqs}
    has_section = any(r.get("section") for r in reqs)

    releases = read_releases(root)
    release_ids = {r["id"] for r in releases or [] if not r.get("unreadable")}
    dep_state = ("missing" if not any("depends_on" in r for r in reqs)
                 else "data" if any(r.get("depends_on") for r in reqs) else "empty")

    def release_label(r: dict) -> str:
        f = str(r.get("release") or "").strip()
        return f if f in release_ids else f"Target {f}" if f else "Not released"
    rows = []
    for r in reqs:
        ws = w_of.get(r["id"], [])
        rows.append({
            "id": r["id"], "title": r.get("title", ""), "section": r.get("section") or "—",
            "layer": r.get("layer") or "unset", "status": r.get("status", ""),
            "work": ", ".join(w["id"] for w in ws) or "none",
            "wstatus": ", ".join(str(w.get("status")) for w in ws) or "—",
            "tier": ", ".join(str(w.get("tier")) for w in ws) or "—",
            "deps": ", ".join(r.get("depends_on") or []) or "—",
            "acs": len(r.get("acceptance_criteria") or []),
            # REQ-016 AC-4: the release that delivered it (or unreleased) and the pull request(s) that merged its
            # done work items; a done work item naming no `PR #n` says so, never a blank
            "release": release_label(r), "rel_field": str(r.get("release") or "").strip(),
            "group": req_group(r.get("status")), "dep_list": [str(d) for d in r.get("depends_on") or []],
            "works_all": ws, "open_work": any(w.get("status") not in ("done", "dropped") for w in ws),
            "criteria": [{"id": str(a.get("id")), "text": a.get("text")} for a in r.get("acceptance_criteria") or []
                         if isinstance(a, dict)],
            "review": ", ".join(dict.fromkeys(
                trace_check.review_cell(w) or f"{w.get('id')}: no PR named" for w in ws if w.get("status") == "done"))
            or "—",
        })
    # headline (REQ-014): "done" = verified + delivered-before-trace, shown split; Superseded is out of the total
    n_dbt = sum(1 for r in rows if r["status"] == "Delivered-before-trace")
    n_sup = sum(1 for r in rows if r["status"] == "Superseded")
    n_done = sum(1 for r in rows if r["status"] in DONE)
    n_total = len(rows) - n_sup
    done_word = "verified" if not n_dbt else f"done ({n_done - n_dbt} verified, {n_dbt} done before tracking began)"
    decisions, dec_problems = read_decisions(root)
    n_dec_exempt = sum(1 for d in decisions if d["status"].startswith(NO_REQUIREMENT + " (exempt"))
    n_dec_cov = sum(1 for d in decisions if not d["status"].startswith(NO_REQUIREMENT))
    dec_count = (f"{len(decisions)} decisions · {n_dec_cov} covered · "
                 f"{len(decisions) - n_dec_cov - n_dec_exempt} not covered"
                 + (f" · {n_dec_exempt} need no requirement" if n_dec_exempt else ""))
    if decisions:
        dec_body = (filters("q-od", "Filter decisions", [
            ("f-od-cov", "Covered or not", ["covered", "not covered"] + (["exempt"] if n_dec_exempt else [])),
            ("f-od-status", "Any status", sorted({d["status"] for d in decisions}))])
            + table([("id", "ID"), ("date", "Date"), ("title", "Decision"), ("words", "Owner's words"),
                     ("changes", "Changes"), ("cited", "Cited by"), ("status", "Status")], decisions, "t-od",
                     {"date": "p2", "cited": "p2", "words": "p3", "changes": "p3"}))
    else:
        dec_body = '<p class="muted">No decision records (docs/spec/decisions.md or spec/decisions/*.md).</p>'
    if dec_problems:
        dec_body = ('<p class="muted" data-problems="decisions"><span class="chip bad">Data problems</span> '
                    + esc("; ".join(dec_problems)) + " — not shown in the table; fix the row, "
                    "<code>python tools/spec_dupes.py .</code> reports it.</p>") + dec_body
        dec_count += f" · {len(dec_problems)} data problems"
    # coverage (REQ-013 AC-3/AC-4/AC-6): the same counts spec_dupes prints, from the one definition
    cov = spec_dupes.trace_report(root)
    n_cov_dec = len(cov["decisions_uncovered"])
    n_cov_sec = "n/a" if cov["sections_uncovered"] is None else len(cov["sections_uncovered"])
    cov_text = (f"COVERAGE ({cov['mode']} mode, {'blocking' if cov['mode'] == 'block' else 'not blocking'}): "
                f"{n_cov_dec} decisions need a requirement and have none"
                + (f" ({', '.join(cov['decisions_uncovered'])})" if n_cov_dec else "")
                + f"; {n_cov_sec} requirement sections of the master spec are cited by no requirement"
                + (f" ({', '.join('§' + str(n) for n in cov['sections_uncovered'])})"
                   if cov["sections_uncovered"] else "")
                + ". Measured by python tools/spec_dupes.py .")
    dec_body = (f'<p class="muted" data-coverage="{n_cov_dec}/{n_cov_sec}/{esc(cov["mode"])}">'
                f'<span class="chip idle">coverage</span> {esc(cov_text)}</p>') + dec_body
    dec_count += f" · decisions with no requirement: {n_cov_dec}, spec sections not cited: {n_cov_sec}"
    blocked_works = [w for w in works if w.get("status") == "blocked"]
    oq = read_owner_questions(root)
    open_qs, bad_qs = oq if oq is not None else ([], [])

    # issues + findings rows
    iss_rows: list[dict] = []
    n_unmapped_issues = n_open = n_parked = 0
    parked_issues: list[dict] = []
    if issues is not None:
        for i in sorted(issues, key=lambda x: x.get("number", 0)):
            rel = relates_to(i.get("body"))
            st = issue_status(i)
            n_unmapped_issues += rel == UNMAPPED
            n_open += str(i.get("state", "")).upper() != "CLOSED"
            row = {"id": f"#{i.get('number')}", "type": "issue", "title": i.get("title", ""), "rel": rel,
                   "status": st, "opened": (i.get("createdAt") or "")[:10]}
            iss_rows.append(row)
            if st == "parked":
                n_parked += 1
                parked_issues.append(row)
    n_unmapped_findings = 0
    for f in findings:
        wm = re.search(r"W-\d{3,}", (f.get("first_seen") or {}).get("where", "") or "")
        target = next((w for w in works if wm and w["id"] == wm.group(0)), None)
        rel = ", ".join(target.get("requirement_ids") or []) if target else ""
        rel = rel or UNMAPPED
        n_unmapped_findings += rel == UNMAPPED
        text = str(f.get("class", ""))
        iss_rows.append({"id": f["id"], "type": "finding", "title": text if len(text) <= 160 else text[:157] + "...",
                         "rel": rel, "status": (f.get("detection") or {}).get("status") or "unmeasured",
                         "opened": (f.get("first_seen") or {}).get("date", "")})
    n_unguarded = sum(1 for f in findings if (f.get("detection") or {}).get("status") == "unguarded")

    # computed health beside the stored status (REQ-014 AC-5)
    ev_results = evidence_results(root)
    pins = pin_failing(root, cov["amends"])
    parked_reqs = {rid for p in parked_issues for rid in re.findall(r"REQ-\d{3,}", p["rel"])}
    for row in rows:
        row["health"] = health(row["id"], ev_results, pins, w_of.get(row["id"], []), parked_reqs)
        res_ = ev_results.get(row["id"])
        # only proof pinned to the CURRENT text of a check counts as verified; proof without a pin ("Proof needs refreshing")
        # and proof written for an older wording ("Changed, needs re-check") are counted apart, as "need re-check"
        row["verified"] = None if res_ is None else len(res_.fresh)
        row["recheck"] = 0 if res_ is None else len((set(res_.unpinned) | {a for a, _p, _h in res_.stale}) - set(res_.fresh))
        row["stale"], row["unpinned"] = bool(res_ and res_.stale), bool(res_ and res_.unpinned)
        row["checks"] = ("None yet" if not row["acs"] else "Not required" if row["verified"] is None
                         else f"{row['verified']} of {row['acs']}" + mini_bar(row["verified"], row["acs"]))
    n_health = {h: sum(1 for r in rows if r["health"] == h) for h in HEALTHS}

    gates = classify_gates(root, runs)
    n_skipped = sum(1 for g in gates["gates"] if g[1] == "skipped-every-time")
    n_never = sum(1 for g in gates["gates"] if g[1] == "never-run")
    build = read_build_order(root)
    recent = recent_stage_changes(root)

    # -- blockers
    blockers = []
    for w in blocked_works:     # (work item id or None, html); Development drops the ones it already shows as cards
        blockers.append((str(w["id"]), f'<li>{esc(w["id"])}: {esc(w.get("title", ""))} — {esc(w.get("next_action", ""))}</li>'))
    for w in works:
        if w.get("status") != "blocked" and w.get("blockers"):
            blockers.append((str(w["id"]), f'<li>{esc(w["id"])}: {esc("; ".join(str(b) for b in w["blockers"]))}</li>'))
    for p in parked_issues:
        blockers.append((None, f'<li>{esc(p["id"])} (parked): {esc(p["title"])}</li>'))
    blockers_note = unmeasured(GH_ISSUES_CMD, "Parked issues are not counted because the issues were not fetched. Build the page with the fetch option to count them.") if issues is None else ""

    # -- needs you: a project with no owner-questions/ folder keeps no question records; that is not "nothing waiting"
    needs = [f'<li data-oq="{esc(q["id"])}"><span class="q">{esc(q["question"])}</span><span class="id">{esc(q["id"])}</span>'
             f'<span class="sl">Asked {esc(q.get("asked", ""))}</span>'
             f'<span class="sl">Recommendation: {esc(q["recommendation"])}</span>'
             f'<span class="sl">Spec basis: {esc(q["spec_basis"])}</span></li>'
             for q in open_qs]
    if oq is None:
        needs_body, needs_count, needs_has = "<p>This project keeps no question records.</p>", "No question records in this project", "none"
    else:
        needs_body = ('<ul class="qs">' + "".join(needs) + "</ul>") if needs else "<p>Nothing is waiting on you.</p>"
        needs_count, needs_has = (str(len(open_qs)) if open_qs else "Nothing is waiting on you"), (1 if open_qs else 0)
    if bad_qs:
        needs_body += (f'<p class="muted"><span class="chip bad">{len(bad_qs)} unreadable</span> '
                       f'{esc(", ".join(bad_qs))}</p>' + technical('<p class="codebox">Run <code>python tools/factory_lint.py .</code></p>'))

    # -- issues (issues only; findings are in Testing)
    at_limit = issues is not None and len(issues) >= ISSUE_LIMIT
    if issues is None:
        issues_body = unmeasured(GH_ISSUES_CMD, "The issues were not fetched from GitHub for this page. Build the page with the fetch option and they appear here.")
        issues_count = "Not measured yet"
    else:
        irows = sorted([r for r in iss_rows if r["type"] == "issue"],
                       key=lambda r: ({"parked": 0, "open": 1, "deferred": 1}.get(r["status"], 2), -int(r["id"][1:] or 0)))
        idata = [{**r, "rel": "Not linked to a requirement" if r["rel"] == UNMAPPED else r["rel"]} for r in irows]
        issues_body = (filters("q-iss", "Filter issues", [("f-iss-status", "Any status", sorted({r["status"] for r in irows}))])
                       + table([("id", "Id"), ("title", "Title"), ("rel", "Relates to"), ("status", "Status"), ("opened", "Opened")],
                               idata, "t-iss", {"rel": "p2", "opened": "p2"}, suffix=None))
        issues_count = (f"{n_open} open of at least {len(issues)} issues (fetch limit reached)" if at_limit
                        else f"{n_open} open of {len(issues)}")

    # -- overall numbers
    def n(v):
        return str(v) if issues is not None else "unmeasured"
    tiles = "".join([
        tile("verified", f"{n_done}/{n_total}", "requirements " + done_word),
        tile("delivered-before-trace", str(n_dbt), "done before tracking began (counted as done)"),
        tile("superseded", str(n_sup), "replaced (not in the total)"),
        tile("decisions", str(len(decisions)), "owner decisions"),
        tile("decisions-covered", str(n_dec_cov), "decisions covered by a requirement"),
        tile("decisions-uncovered", str(len(decisions) - n_dec_cov - n_dec_exempt), "decisions not covered"),
    ] + ([tile("decisions-exempt", str(n_dec_exempt), "decisions that need no requirement")] if n_dec_exempt else []) + [
        tile("needs-you", str(len(open_qs)), "need you"),
        tile("blocked", str(len(blocked_works)), "blocked work items"),
        tile("parked", n(n_parked), "parked issues"),
        tile("open-issues", n(n_open), "open issues"),
        tile("unmapped", n(n_unmapped_issues), "issues not linked to a requirement"),
        tile("unguarded", str(n_unguarded), "findings with no automatic check yet"),
    ] + [tile("health-" + re.sub(r"[^a-z]+", "-", h.lower()).strip("-"), str(n_health[h]), f"health: {h}")
         for h in HEALTHS])
    overall = f'<div class="strip">{tiles}</div>'
    if issues is None:
        overall += unmeasured(GH_ISSUES_CMD, "Health 'Parked' comes from parked issues; none were supplied, so no "
                                             "requirement can show Parked.")
    if at_limit:
        overall += (f'<p class="muted"><span class="chip idle">at least {len(issues)} issues (fetch limit reached)</span> '
                    f'counts of issues are lower bounds.</p>')

    js = JS.replace("__SECTION__", ', ["f-req-section", "section"]' if has_section else "")

    # -- first screen (REQ-052 AC-2)
    plans = read_plans(root)
    results = read_test_results(root)
    results_state = test_results_state(root)
    missing = read_unmeasured_suites(root, results)
    info = read_now(root, works, code_state, now_dt)
    state, now_text, not_moving = working_on(info, plans or [], code_state, now_dt, works)
    ages = read_work_ages(root, now_dt)
    week = read_this_week(root, prs, now_dt)
    new_reqs = read_new_requirements(root, now_dt)
    head_full = (_git(root, "rev-parse", "HEAD") or "").strip() or None
    h1 = re.sub(r"\s+Status$", "", title) or title
    header = (f'<header><p class="eyebrow">Project status</p><div class="hrow"><h1>{esc(h1)}</h1><p>'
              f'<span class="pill fresh" id="fresh" data-iso="{esc(now_iso)}">Updated {esc(now)}</span></p></div></header>')
    banner = '<p class="banner" id="stale" role="status" hidden></p>'
    now_card = (f'<section class="panel" id="right-now"><h2>Right now</h2>{now_line_html(state, now_text)}'
                + (not_moving_html(not_moving) if not_moving else "") + "</section>")
    needs_card = (f'<div class="panel needs" data-has="{needs_has}">'
                  + sec("Needs you", needs_body, needs_count, bool(open_qs)) + "</div>")

    def link_tile(href: str, html_: str) -> str:
        return f'<a class="tlk" href="{href}">{html_}</a>'
    tiles4 = ('<div id="first-tiles">' + link_tile("#role-product", requirements_tile([r["status"] for r in rows], new_reqs))
              + link_tile("#plans", plan_tile(plans)) + link_tile("#role-testing", tests_tile(results, missing, runs, head_full))
              + link_tile("#role-development", code_tile(code_state, prs)) + "</div>")
    sha_line = (f'<footer><p>Data as of <span class="mono" id="stamp-sha">{sha_html}</span>, '
                f'<span id="stamp-time">{esc(now)}</span>; changes made only on GitHub appear after the next pull.</p></footer>')
    not_shown = ('<div class="nsy" id="not-shown-yet"><h3>Not shown yet</h3><p>Not shown yet: incidents, architecture (beyond the '
                 'layers, dependencies and decisions above), learning, capability usage, efficiency and engineering health. '
                 'These views come in later milestones (M5, M6).</p></div>')
    kit_html = kit_adoption_html(
        read_kit_adoption(root), {str(r_["id"]): display_title(r_.get("title"), [str(r_["id"])])[0] for r_ in reqs})
    n_wc = len(code_state["worktrees"]) if isinstance(code_state.get("worktrees"), list) else None
    n_wait = len(prs["open"]) if isinstance(prs, dict) and isinstance(prs.get("open"), list) else None
    code_count = ("Not measured yet" if n_wc is None else f"{n_wc} working cop{'y' if n_wc == 1 else 'ies'}"
                  + (f" · {n_wait} waiting to merge" if n_wait is not None else ""))
    nav = ('<nav class="snav" aria-label="Sections">' + "".join(f'<a href="#role-{i}">{t}</a>' for i, t in ROLE_BAR) + "</nav>")

    c = types.SimpleNamespace(
        root=root, now_dt=now_dt, rows=rows, live=[r for r in rows if r["status"] != "Superseded"], by_row={r["id"]: r for r in rows},
        works=works, w_by_id={str(w.get("id")): w for w in works}, blocked_works=blocked_works, ev=ev_results, cov=cov,
        decisions=decisions, dec_body=dec_body, issues=issues, iss_rows=iss_rows, plans=plans, releases=releases,
        results=results, results_state=results_state, missing=missing, runs=runs, head_full=head_full,
        sha_short=sha, code_state=code_state, prs=prs, delivery=delivery, build=build, gates=gates, recent=recent, ages=ages, info=info,
        oq=oq, kit=read_kit_adoption(root), kit_html=kit_html, n_done=n_done, n_total=n_total, done_word=done_word,
        overall_html=overall, dep_state=dep_state, unreadable_reqs=sum(1 for r in reqs if r.get("_unreadable")),
        arch=read_architecture(root), blockers=blockers, blockers_note=blockers_note, issues_body=issues_body,
        issues_count=issues_count, code_body=code_html(code_state, prs), code_count=code_count,
        merged_html=prs_list_html(prs, "merged", f"Merged in the last {MERGED_DAYS} days").split("</h3>", 1)[1],
        workflows=read_workflows(root), domain_rules=read_domain_rules(root))
    c.req_table_blk, c.user_gets_body, c.n_user_gets = requirements_table_block(c)

    summary_ans, summary_chip = summary_answer(c)
    summary_body = (f'<div class="top{"" if open_qs else " top-empty"}">{now_card}{needs_card}</div>' + tiles4
                    + blk("This week", week_html(week), "week") + blk("Work board", board_html(works, ages), "board-blk"))
    built = [
        ("summary", "Does anything need me, and are we on track?", (summary_ans, summary_chip, summary_body)),
        ("product", "Which requirements are done, pending or blocked, and what does a user get?", sec_product(c)),
        ("architecture", "What is the structure, what depends on what, and which decisions shaped it?", sec_architecture(c)),
        ("development", "What do I pick up next, and what is half-done in code?", sec_development(c)),
        ("testing", "Which tests and acceptance checks pass, fail or never ran, per requirement?", sec_testing(c)),
        ("releases", "What changed, what is released, and what ships next?", sec_releases(c)),
        ("operations", "What runs where, and how do I undo it?", sec_operations(c)),
        ("data", "Are the numbers right?", sec_data(c))]
    names = dict(ROLE_BAR)
    role_html = [role_section(rid, names[rid], asks, ans, chip_html, body) for rid, asks, (ans, chip_html, body) in built]
    page = (
        f"<title>{esc(title)}</title>\n"
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<style>\n{CSS}\n</style>\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n'
        f'<main class="wrap">\n{header}\n{nav}\n{banner}\n'
        + "\n".join(role_html + [not_shown])
        + f"\n</main>\n{sha_line}\n<script>\n{js}\n</script>\n")
    summary = {"requirements": len(rows), "verified": n_done, "delivered_before_trace": n_dbt,
               "superseded": n_sup, "decisions": len(decisions),
               "decisions_covered": n_dec_cov, "issues": len(issues) if issues is not None else None,
               "findings": len(findings), "unmapped_issues": n_unmapped_issues, "unmapped_findings": n_unmapped_findings,
               "unguarded": n_unguarded, "needs_you": len(open_qs), "blocked": len(blocked_works),
               "never_run": n_never, "skipped_every_time": n_skipped, "health": n_health}
    return page, summary


# ---- fetching live inputs (the only impure part; render() never calls it) ---------------------------

GH_TIMEOUT = 60


def _gh_json(args: list[str], root: Path):
    """Parsed JSON from `gh <args>`, or None when gh is missing, not logged in, offline, slow, exits non-zero or
    prints something that is not JSON. Never raises: the caller shows `unmeasured: gh <args>` (REQ-052 AC-5)."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(root), timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def fetch_gh_inputs(root: Path, run_limit: int = 10) -> tuple[list[dict] | None, list[dict] | None]:
    """(issues, runs); either is None when its gh call failed, and render() then says unmeasured."""
    issues = _gh_json(["issue", "list", "--state", "all", "--limit", str(ISSUE_LIMIT), "--json",
                       "number,title,state,labels,body,createdAt,closedAt"], root)
    if not isinstance(issues, list):
        issues = None
    runs = _gh_json(["run", "list", "--limit", str(run_limit), "--json",
                     "databaseId,name,status,conclusion,createdAt,workflowName,headSha,url"], root)
    if not isinstance(runs, list):
        return issues, None
    for run in runs:
        jobs = _gh_json(["run", "view", str(run["databaseId"]), "--json", "jobs"], root)
        if not isinstance(jobs, dict):
            return issues, None   # a gate verdict built from half the runs would be a guess
        run["jobs"] = jobs.get("jobs", [])
    return issues, runs


def _load_json(path: str | None):
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the project status page from repo data, issues and CI runs.")
    ap.add_argument("root")
    ap.add_argument("--issues", help="gh issue list --state all --json ... output")
    ap.add_argument("--runs", help="gh run list output, each run carrying a jobs list")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--now", help="generation stamp text (default: the system clock)")
    ap.add_argument("--sha", help="git sha text (default: git rev-parse --short HEAD)")
    ap.add_argument("--fetch", action="store_true", help="run the gh commands for --issues and --runs first")
    a = ap.parse_args(argv)
    root = Path(a.root)
    prs = None
    delivery = None
    if a.fetch:
        issues, runs = fetch_gh_inputs(root)
        prs = read_prs(root)
        delivery = delivery_metrics.collect(str(root), today=datetime.date.today())
    else:
        issues, runs = _load_json(a.issues), _load_json(a.runs)
    page, s = render(root, issues, runs, now=a.now, sha=a.sha, title=a.title, prs=prs, delivery=delivery)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    issue_txt = "issues unmeasured" if s["issues"] is None else f"{s['issues']} issues ({s['unmapped_issues']} unmapped)"
    print(f"wrote {out}: {s['requirements']} requirements ({s['verified']} verified), {issue_txt}, "
          f"{s['findings']} findings ({s['unguarded']} unguarded), {s['needs_you']} need you, "
          f"{s['blocked']} blocked work items, {s['never_run'] + s['skipped_every_time']} never-run gates "
          f"({s['never_run']} never run, {s['skipped_every_time']} skipped every time)")
    return 0


def _stdio_replace() -> None:
    """Keep the stream's encoding but replace what it cannot hold, so a cp1252 console (Windows) never
    raises UnicodeEncodeError on text from a child process, GitHub or a spec file (issue 159)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    _stdio_replace()
    sys.exit(main())
