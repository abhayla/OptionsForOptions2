#!/usr/bin/env python3
"""tools/ci_reds.py - read-only report of red GitHub Actions runs (REQ-062 AC-1).

For a repository, an optional workflow and a since-date it lists every failed run with its branch, head commit,
every failed job and step, and the subject of the first non-merge commit after the head on the same branch (the
fix), or "fix: none found". It ends with the count of red runs per job and step and the median minutes of failed
and of passed runs (updatedAt minus createdAt). It reads run metadata through the `gh` CLI only, never downloads
logs, and writes nothing. Exit 0 on success (even with reds); exit 2 with a one-line message when gh is missing,
a list/view call fails, or its output is not readable JSON. A failed or empty fix lookup is "none found".

Usage:
    python tools/ci_reds.py --repo OWNER/NAME [--workflow FILE] [--event NAME] [--since YYYY-MM-DD] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from statistics import median
from urllib.parse import quote

FIELDS = "databaseId,headSha,headBranch,createdAt,updatedAt,conclusion,displayTitle"


class ReportError(Exception):
    """A gh call that must succeed did not; the message is printed, exit 2."""


def gh_runner(argv: list[str]) -> tuple[int, str]:
    """Run `gh <argv>`; return (returncode, stdout). A missing gh raises ReportError."""
    try:
        done = subprocess.run(["gh", *argv], capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise ReportError("ci_reds: the gh command is not installed")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportError(f"ci_reds: gh could not be run ({type(exc).__name__})")
    return done.returncode, done.stdout


def _json(run, argv: list[str], what: str):
    rc, out = run(argv)
    if rc != 0:
        raise ReportError(f"ci_reds: gh {what} failed (exit {rc})")
    try:
        return json.loads(out)
    except ValueError:
        raise ReportError(f"ci_reds: gh {what} returned unreadable JSON")


def _list_runs(run, repo, workflow, event, since, limit, status):
    argv = ["run", "list", "-R", repo]
    if workflow:
        argv += ["--workflow", workflow]
    if event:
        argv += ["--event", event]
    argv += ["--status", status]
    if since:
        argv += ["--created", f">={since}"]
    argv += ["--limit", str(limit), "--json", FIELDS]
    data = _json(run, argv, f"run list ({status})")
    if not isinstance(data, list):
        raise ReportError(f"ci_reds: gh run list ({status}) returned unreadable JSON")
    return [r for r in data if isinstance(r, dict)]


def failed_steps(run, repo, run_id) -> list[str]:
    """'job / step' for every failed step of every failed job (a failed job with no failed step: '(no failed step)')."""
    data = _json(run, ["run", "view", str(run_id), "-R", repo, "--json", "jobs"], f"run view {run_id}")
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise ReportError(f"ci_reds: gh run view {run_id} returned unreadable JSON")
    found: list[str] = []
    for job in jobs:
        if not isinstance(job, dict) or job.get("conclusion") != "failure":
            continue
        name = str(job.get("name", "?"))
        steps = [s for s in job.get("steps") or [] if isinstance(s, dict) and s.get("conclusion") == "failure"]
        if not steps:
            found.append(f"{name} / (no failed step)")
        for s in steps:
            found.append(f"{name} / {s.get('name', '?')}")
    return found


def fix_subject(run, repo, head_sha, branch) -> str | None:
    """Subject of the first commit after head_sha on branch with exactly one parent, else None."""
    ref = f"{quote(head_sha, safe='')}...{quote(branch, safe='')}"
    try:
        rc, out = run(["api", f"repos/{repo}/compare/{ref}"])
    except ReportError:
        return None
    if rc != 0:
        return None
    try:
        commits = json.loads(out).get("commits")
    except (ValueError, AttributeError):
        return None
    for c in commits if isinstance(commits, list) else []:
        if isinstance(c, dict) and isinstance(c.get("parents"), list) and len(c["parents"]) == 1:
            message = (c.get("commit") or {}).get("message") or ""
            return (message.splitlines() or [""])[0]
    return None


def _minutes(run_rec) -> float | None:
    try:
        start = datetime.fromisoformat(run_rec["createdAt"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run_rec["updatedAt"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return None
    return (end - start).total_seconds() / 60


def _median_text(runs) -> str:
    values = [m for m in map(_minutes, runs) if m is not None]
    return f"{median(values):.1f} min (n={len(values)})" if values else "n/a (n=0)"


def _ascii(text) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def build_report(run, repo, workflow=None, event=None, since=None, limit=200) -> str:
    reds = _list_runs(run, repo, workflow, event, since, limit, "failure")
    greens = _list_runs(run, repo, workflow, event, since, limit, "success")
    lines: list[str] = []
    by_step: Counter = Counter()
    for r in reds:
        steps = failed_steps(run, repo, r.get("databaseId"))
        for key in set(steps):
            by_step[key] += 1
        sha = str(r.get("headSha", ""))
        branch = str(r.get("headBranch", ""))
        fix = fix_subject(run, repo, sha, branch) if sha and branch else None
        lines.append(f"RUN {r.get('databaseId')} {str(r.get('createdAt', ''))[:10]} {branch} {sha[:7]}")
        lines += [f"  failed: {s}" for s in steps] or ["  failed: (none listed)"]
        lines.append(f"  fix: {fix}" if fix is not None else "  fix: none found")
    lines.append(f"RED RUNS: {len(reds)}")
    for what, runs in (("red", reds), ("passed", greens)):
        if len(runs) >= limit:
            lines.append(f"WARN: {len(runs)} {what} runs = --limit {limit}; older runs in the window are not counted")
    for key, n in sorted(by_step.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"BY STEP: {n} {key}")
    lines.append(f"MEDIAN failed {_median_text(reds)}, passed {_median_text(greens)}")
    return _ascii("\n".join(lines))


def main(argv=None, run=gh_runner) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(description="Report red GitHub Actions runs by failing job and step.")
    ap.add_argument("--repo", required=True, help="OWNER/NAME")
    ap.add_argument("--workflow")
    ap.add_argument("--event")
    ap.add_argument("--since", help="YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args(argv)
    try:
        print(build_report(run, args.repo, args.workflow, args.event, args.since, args.limit))
    except ReportError as exc:
        print(_ascii(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
