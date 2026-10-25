#!/usr/bin/env python3
"""delivery_metrics.py - how much was delivered, from git and GitHub only (REQ-055 AC-4).

Usage:
    python tools/delivery_metrics.py <repo-dir> [--since YYYY-MM-DD] [--json] [--doc-dirs a,b]

Works for any project: nothing here depends on a branch-naming convention or a project's folder names beyond the
generic path classes below. Every number is either derived from a command's output or printed as
`unmeasured: <reason>`; a listing that hit its limit prints `capped`, never a number that might be short.

- Merged pull requests in the window are classified by the FILES each one changed, never by branch name:
  product code / tests / docs+spec+process / generated. A pull request whose files span kinds is counted under
  its largest kind by changed lines (ties: product, tests, docs, generated).
- Lines added are summed by area (the same four kinds).
- CI runs and their conclusions are listed in date windows (`--created A..B`), so one capped listing (gh stops
  at 1000) never undercounts silently; a window that still fills the limit prints `capped`.
- Merge-main-into-branch commits are counted from the history of origin/main.
- Review rounds per work item are counted only when the project keeps review records (`reviews/*.md` whose
  frontmatter has `work_item` and `round`); otherwise `unmeasured`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

KINDS = ("product", "tests", "docs", "generated")  # tie order
PR_LIMIT = 200      # per date window; gh pr list with files is heavy, so windows stay small
RUN_LIMIT = 1000    # gh run list stops here
WINDOW_DAYS = 7
GH_TIMEOUT = 120

# generic path classes; a project changes them here, nowhere else
GENERATED_DIRS = {"views", "dist", "build", "generated", "node_modules", "vendor"}
GENERATED_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "PROVENANCE.md", "INDEX.md"}
GENERATED_MARKERS = (".min.", ".snap", ".lock", "-lock.")
TEST_DIRS = {"test", "tests", "__tests__", "e2e", "spec_tests"}
TEST_MARKERS = (".test.", ".spec.", "_test.", "-test.", "_spec.")
# matched at the FIRST path segment only; a project adds its own with --doc-dirs (e.g. spec, knowledge)
DOC_DIRS = {"docs", "doc", "work", "plans", "evidence", "releases", "owner-questions", "reviews", ".github", ".claude"}
DOC_EXTS = {".md", ".rst", ".txt", ".adoc"}


def classify_path(path: str, extra_doc_dirs=()) -> str:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    dirs = {p.lower() for p in parts[:-1]}
    if dirs & GENERATED_DIRS or name in GENERATED_NAMES or any(m in name for m in GENERATED_MARKERS):
        return "generated"
    if dirs & TEST_DIRS or name.startswith("test_") or any(m in name for m in TEST_MARKERS):
        return "tests"
    if (len(parts) > 1 and parts[0].lower() in DOC_DIRS | set(extra_doc_dirs)) or Path(name).suffix.lower() in DOC_EXTS or name.upper().startswith(("LICENSE", "README")):
        return "docs"
    return "product"


def classify_pr(files: list[dict], extra_doc_dirs=()) -> str | None:
    """The kind holding the most changed lines; None when the pull request lists no files."""
    lines = dict.fromkeys(KINDS, 0)
    for f in files:
        lines[classify_path(str(f.get("path", "")), extra_doc_dirs)] += int(f.get("additions") or 0) + int(f.get("deletions") or 0)
    if not files:
        return None
    return max(KINDS, key=lambda k: (lines[k], -KINDS.index(k)))


def _run(args: list[str], cwd: str) -> tuple[int, str]:
    """The one subprocess seam (tests replace it). Returns (exit code, stdout); never raises."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return 127, f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout


def _today() -> datetime.date:
    return datetime.date.today()


def windows(since: datetime.date, until: datetime.date) -> list[tuple[str, str]]:
    out, a = [], since
    while a <= until:
        b = min(a + datetime.timedelta(days=WINDOW_DAYS - 1), until)
        out.append((a.isoformat(), b.isoformat()))
        a = b + datetime.timedelta(days=1)
    return out


def _gh_list(repo: str, args: list[str], what: str):
    rc, out = _run(["gh", *args], repo)
    if rc != 0:
        return f"unmeasured: {what} failed (exit {rc}); command: gh {' '.join(args[:4])}"
    try:
        data = json.loads(out)
    except ValueError:
        return f"unmeasured: {what} printed something that is not JSON"
    return data if isinstance(data, list) else f"unmeasured: {what} printed no list"


def merged_prs(repo: str, since: datetime.date, until: datetime.date, extra_doc_dirs=()) -> dict | str:
    seen: dict[int, dict] = {}
    for a, b in windows(since, until):
        data = _gh_list(repo, ["pr", "list", "--state", "merged", "--search", f"merged:{a}..{b}", "--limit", str(PR_LIMIT),
                               "--json", "number,additions,deletions,files"], "merged pull request listing")
        if isinstance(data, str):
            return data
        if len(data) >= PR_LIMIT:
            return "capped"
        for p in data:
            seen[p["number"]] = p
    by_kind = dict.fromkeys(KINDS, 0)
    by_kind["unclassified"] = 0
    added = dict.fromkeys(KINDS, 0)
    partial = 0
    for p in seen.values():
        files = p.get("files") or []
        k = classify_pr(files, extra_doc_dirs)
        by_kind[k or "unclassified"] += 1
        for f in files:
            added[classify_path(str(f.get("path", "")), extra_doc_dirs)] += int(f.get("additions") or 0)
        shown = sum(int(f.get("additions") or 0) + int(f.get("deletions") or 0) for f in files)
        if shown < int(p.get("additions") or 0) + int(p.get("deletions") or 0):
            partial += 1   # gh lists a bounded number of files per pull request
    return {"count": len(seen), "by_kind": by_kind, "lines_added": added, "files_partial": partial}


def ci_runs(repo: str, since: datetime.date, until: datetime.date) -> dict | str:
    total, conc = 0, {}
    for a, b in windows(since, until):
        data = _gh_list(repo, ["run", "list", "--created", f"{a}..{b}", "--limit", str(RUN_LIMIT), "--json", "conclusion,createdAt"],
                        "CI run listing")
        if isinstance(data, str):
            return data
        if len(data) >= RUN_LIMIT:
            return "capped"
        for r in data:
            total += 1
            key = r.get("conclusion") or "running"
            conc[key] = conc.get(key, 0) + 1
    return {"count": total, "conclusions": dict(sorted(conc.items()))}


MERGE_MAIN = re.compile(r"^Merge (remote-tracking )?branch '(origin/)?(main|master)'")


def merge_main_commits(repo: str, since: datetime.date) -> dict | str:
    rc, out = _run(["git", "log", "origin/main", f"--since={since.isoformat()}", "--format=%s"], repo)
    if rc != 0:
        return "unmeasured: git log origin/main failed (no origin/main in this checkout)"
    subjects = out.splitlines()
    return {"merge_main": sum(1 for s in subjects if MERGE_MAIN.match(s)), "commits": len(subjects)}


def review_rounds(repo: str) -> dict | str:
    d = Path(repo) / "reviews"
    if not d.is_dir():
        return "unmeasured: this project keeps no review records (no reviews/ folder)"
    rounds: dict[str, int] = {}
    for f in sorted(d.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"---\n(.*?)\n---", text, re.S)
        fm = m.group(1) if m else ""
        w = re.search(r"^work_item:\s*(\S+)", fm, re.M)
        r = re.search(r"^round:\s*(\d+)", fm, re.M)
        if not (w and r):
            return f"unmeasured: review record {f.name} lacks work_item or round"
        rounds[w.group(1)] = max(rounds.get(w.group(1), 0), int(r.group(1)))
    if not rounds:
        return "unmeasured: reviews/ holds no records"
    return {"items": len(rounds), "max_round": max(rounds.values()), "rounds": dict(sorted(rounds.items()))}


def collect(repo: str, since: datetime.date | None = None, today: datetime.date | None = None, extra_doc_dirs=()) -> dict:
    until = today or _today()
    since = since or until - datetime.timedelta(days=13)
    return {"since": since.isoformat(), "until": until.isoformat(),
            "prs": merged_prs(repo, since, until, extra_doc_dirs), "ci": ci_runs(repo, since, until),
            "merge_main": merge_main_commits(repo, since), "review_rounds": review_rounds(repo)}


def _fmt(v, fn) -> str:
    return v if isinstance(v, str) else fn(v)


def lines(m: dict) -> list[str]:
    out = [f"delivery {m['since']} .. {m['until']}"]
    out.append("merged PRs: " + _fmt(m["prs"], lambda p: f"{p['count']} (by files changed: " + ", ".join(
        f"{k} {n}" for k, n in p["by_kind"].items() if n or k in KINDS) + ")"
        + (f"; {p['files_partial']} with a file list cut short by gh" if p["files_partial"] else "")))
    out.append("lines added: " + _fmt(m["prs"], lambda p: ", ".join(f"{k} {n}" for k, n in p["lines_added"].items())))
    out.append("CI runs: " + _fmt(m["ci"], lambda c: f"{c['count']} (" + ", ".join(f"{k} {n}" for k, n in c["conclusions"].items()) + ")"))
    out.append("merge-main-into-branch commits: " + _fmt(m["merge_main"], lambda c: f"{c['merge_main']} of {c['commits']} commits on origin/main"))
    out.append("review rounds per item: " + _fmt(m["review_rounds"], lambda r: f"{r['items']} items, highest round {r['max_round']}"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Delivery numbers from git and GitHub for one repository.")
    ap.add_argument("repo_dir")
    ap.add_argument("--since", help="YYYY-MM-DD (default: 14 days ago)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--doc-dirs", default="", help="comma-separated extra top-level folders to count as docs (e.g. spec,knowledge)")
    a = ap.parse_args(argv)
    try:
        since = datetime.date.fromisoformat(a.since) if a.since else None
    except ValueError:
        print("--since must be YYYY-MM-DD", file=sys.stderr)
        return 2
    m = collect(a.repo_dir, since, extra_doc_dirs=tuple(d.strip().lower() for d in a.doc_dirs.split(",") if d.strip()))
    print(json.dumps(m, indent=2) if a.json else "\n".join(lines(m)))
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
