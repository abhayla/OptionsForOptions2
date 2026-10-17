"""stage_scorecard.py [--since ISO] [--until ISO] [--repo-root DIR]

Delivery scorecard for a time window, derived from `gh pr list`, `gh run list` and `git log` output (process-cuts
PR 2b, owner-approved process plan 2026-10-17, decision 5: "scorecard per stage, generated"). Prints a Markdown table
and writes nothing. A source that fails or returns nothing prints `unmeasured: <reason>`, never zero (finding
check-validates-nothing-reports-pass).

Window rule: `since` is inclusive, `until` is exclusive (a run created exactly at `--until` is excluded). PRs and runs
are filtered here; the commit list uses git's own --since/--until.
Example: python scripts/orchestrator/stage_scorecard.py --since 2026-10-16T17:52:00Z --until 2026-10-17T12:00:00Z
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

LIMIT = 400
RUN_LIMIT = 1000  # runs are far more numerous than merged PRs; 400 did not reach back to 2026-10-16T17:52Z
AREA_ORDER = ("tests", "evidence", "spec/work/findings/views", "docs/process", "tooling", "product code", "other")
# First matching prefix wins, so test paths under frontend/ are matched before frontend/src.
_AREAS = (
    ("tests", ("tests/", "tests_app/", "frontend/tests/", "frontend/e2e/")),
    ("evidence", ("evidence/",)),
    ("spec/work/findings/views", ("spec/", "work/", "knowledge/", "views/", "releases/")),
    ("docs/process", ("docs/",)),
    ("tooling", ("scripts/", "tools/", ".claude/", ".github/")),
    ("product code", ("backend/", "frontend/src")),
)
_ROUND = re.compile(r"(\bround\s*\d+|\bfix round\b|^r\d+:)", re.IGNORECASE)
_MERGE_MAIN = re.compile(r"^Merge (remote-tracking )?branch '(origin/)?main'")


def parse_time(text: str) -> datetime:
    """Parse an ISO-8601 time; a value without a timezone is rejected (fail closed)."""
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(f"time without timezone: {text!r}")
    return value.astimezone(timezone.utc)


def in_window(stamp: str, since: datetime, until: datetime) -> bool:
    """since <= stamp < until."""
    return since <= parse_time(stamp) < until


def area_of(path: str) -> str:
    if path.endswith(".spec.ts"):
        return "tests"
    for name, prefixes in _AREAS:
        if path.startswith(prefixes):
            return name
    return "other"


def pr_kinds(prs: list[dict]) -> Counter:
    """Merged PRs by branch kind: the part of headRefName before the first '/', or 'other' with no slash."""
    return Counter(p["headRefName"].split("/", 1)[0] if "/" in p["headRefName"] else "other" for p in prs)


def lines_by_area(prs: list[dict]) -> Counter:
    """Lines added per area; each file of each PR is counted once, in the one area its path belongs to."""
    total: Counter = Counter()
    for pr in prs:
        for f in pr.get("files", []):
            total[area_of(f["path"])] += int(f["additions"])
    return total


def ci_summary(runs: list[dict]) -> dict[str, Counter]:
    """Per workflow: total, success, failure, cancelled, other (any other or empty conclusion)."""
    out: dict[str, Counter] = {}
    for run in runs:
        c = out.setdefault(run["workflowName"], Counter())
        c["total"] += 1
        conclusion = run.get("conclusion") or ""
        c[conclusion if conclusion in ("success", "failure", "cancelled") else "other"] += 1
    return out


def merge_only_commits(subjects: list[str]) -> list[str]:
    """Subjects that merge main / origin/main into a branch (pull-request merges are not included)."""
    return [s for s in subjects if _MERGE_MAIN.match(s)]


def round_commits(subjects: list[str]) -> list[str]:
    """Subjects naming a review round: `round N`, `fix round`, or a leading `rN:`."""
    return [s for s in subjects if _ROUND.search(s)]


def _run(cmd: list[str]) -> tuple[str | None, str]:
    """(stdout, reason). stdout is None when the command is missing, fails or prints nothing."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{cmd[0]} unavailable ({exc.__class__.__name__})"
    if done.returncode != 0:
        return None, f"{cmd[0]} failed: {done.stderr.strip()[:120]}"
    if not done.stdout.strip():
        return None, f"{cmd[0]} returned nothing"
    return done.stdout, ""


def _gh_json(args: list[str]) -> tuple[list[dict] | None, str]:
    out, reason = _run(["gh", *args])
    if out is None:
        return None, reason
    try:
        data = json.loads(out)
    except ValueError:
        return None, "gh output is not JSON"
    if not data:
        return None, "gh returned an empty list"
    return data, ""


def _truncated(rows: list[dict], key: str, since: datetime, limit: int = LIMIT) -> bool:
    """True when the fetch hit the limit and its oldest row is newer than the window start (rows may be missing)."""
    return len(rows) >= limit and min(parse_time(r[key]) for r in rows if r.get(key)) > since


def render(since: datetime, until: datetime, prs, prs_why, runs, runs_why, subjects, subj_why) -> str:
    rows = [f"Scorecard {since:%Y-%m-%dT%H:%MZ} .. {until:%Y-%m-%dT%H:%MZ} (since inclusive, until exclusive)", "",
            "| Measure | Value |", "|---|---|"]
    if prs is None:
        for label in ("Merged PRs by kind", "Lines added by area"):
            rows.append(f"| {label} | unmeasured: {prs_why} |")
    else:
        kinds = pr_kinds(prs)
        rows.append(f"| Merged PRs by kind | {len(prs)} total: " + (", ".join(
            f"{k} {n}" for k, n in sorted(kinds.items())) or "none") + " |")
        lines = lines_by_area(prs)
        rows.append("| Lines added by area | " + ", ".join(f"{a} {lines[a]}" for a in AREA_ORDER) + " |")
    if runs is None:
        rows.append(f"| CI | unmeasured: {runs_why} |")
    else:
        per = ci_summary(runs)
        total: Counter = Counter()
        for c in per.values():
            total.update(c)
        rows.append(f"| CI runs (all workflows) | {total['total']} runs: {total['success']} success, "
                    f"{total['failure']} failure, {total['cancelled']} cancelled, {total['other']} other |")
        for name, c in sorted(per.items()):
            rows.append(f"| CI {name} | {c['total']} runs, {c['failure']} failure, {c['success']} success, "
                        f"{c['cancelled']} cancelled |")
    if subjects is None:
        for label in ("Merge-only commits", "Round commits"):
            rows.append(f"| {label} | unmeasured: {subj_why} |")
    else:
        rows.append(f"| Merge-only commits | {len(merge_only_commits(subjects))} of {len(subjects)} |")
        rows.append(f"| Round commits | {len(round_commits(subjects))} of {len(subjects)} |")
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)
    since, until = parse_time(args.since), parse_time(args.until)
    if since >= until:
        ap.error("--since must be before --until")

    prs, prs_why = _gh_json(["pr", "list", "--state", "merged", "--limit", str(LIMIT), "--json",
                             "number,createdAt,mergedAt,headRefName,files"])
    runs, runs_why = _gh_json(["run", "list", "--limit", str(RUN_LIMIT), "--json",
                               "conclusion,createdAt,workflowName"])
    if prs is not None:
        if _truncated(prs, "mergedAt", since):
            prs, prs_why = None, f"gh pr list hit the {LIMIT} limit before the window start"
        else:
            prs = [p for p in prs if p.get("mergedAt") and in_window(p["mergedAt"], since, until)]
    if runs is not None:
        if _truncated(runs, "createdAt", since, RUN_LIMIT):
            runs, runs_why = None, f"gh run list hit the {RUN_LIMIT} limit before the window start"
        else:
            runs = [r for r in runs if in_window(r["createdAt"], since, until)]
    out, subj_why = _run(["git", "-C", args.repo_root, "log", "--all", f"--since={args.since}",
                          f"--until={args.until}", "--format=%s"])
    subjects = out.splitlines() if out is not None else None
    print(render(since, until, prs, prs_why, runs, runs_why, subjects, subj_why))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
