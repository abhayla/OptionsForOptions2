"""Expected-vs-actual table per builder row, computed from the briefs, git and agent transcripts (ADR-178: never typed).

Usage: python scripts/orchestrator/row_actuals.py [--rows 11-16] [--repo .] [--tasks-dir <dir>]
Columns: row | expected minutes | expected tokens | actual wall-clock minutes | actual agent tokens.
- Expected: each row brief's `Expected (...): <N> min / ~<M>k` line in docs/process/builder-sequence-briefs/ (a brief
  file named `row-<n>...`); values of several briefs of one row are added. A missing value prints `unmeasured`.
- Actual wall-clock: first to last commit whose subject starts `Row <n>`, over all branches (git log --all); fewer than
  two such commits prints `unmeasured (<count> commits)`.
- Actual agent tokens: every agent transcript (`<tasks dir>/*/tasks/*.output`) whose first user text names the row
  (`row 11`, `row-11`) - input + output + cache-creation tokens of its assistant turns, cache reads excluded. The
  transcript reader is measure_process.py's (imported). No transcript prints `unmeasured (no transcript)`.
A number that cannot be derived is never replaced by a guess.
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measure_process as mp  # noqa: E402

BRIEFS = Path("docs") / "process" / "builder-sequence-briefs"
EXPECTED_ANY_RE = re.compile(r"^\W*Expected[^:\n]*:(.*)$", re.I | re.M)
MIN_RE = re.compile(r"(\d+)\s*min\b", re.I)
TOK_RE = re.compile(r"~\s*(\d+)\s*k\b", re.I)
RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
EPOCH = "1970-01-01"
UNMEASURED = "unmeasured"
HEADERS = ("row", "expected minutes", "expected tokens", "actual wall-clock minutes", "actual agent tokens")
MIN_COMMITS = 2


def parse_rows(text: str) -> list[int]:
    m = RANGE_RE.match(text.strip())
    if not m:
        raise ValueError(f"--rows must be N or N-M, got `{text}`")
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    if last < first:
        raise ValueError(f"--rows {text}: the end is before the start")
    return list(range(first, last + 1))


def expected_for(repo: Path, row: int) -> tuple[int | None, int | None]:
    """(minutes, thousand tokens) summed over the row's briefs; None when no brief states that value."""
    minutes: list[int] = []
    tokens: list[int] = []
    pat = re.compile(rf"^row-0*{row}(?!\d)", re.I)
    for path in sorted((repo / BRIEFS).glob("row-*.md")):
        if not pat.match(path.name):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in EXPECTED_ANY_RE.findall(text):
            minutes += [int(x) for x in MIN_RE.findall(line)]
            tokens += [int(x) for x in TOK_RE.findall(line)]
    return (sum(minutes) if minutes else None, sum(tokens) if tokens else None)


def wall_clock(repo: Path, row: int) -> str:
    pat = re.compile(rf"^Row\s+0*{row}(?!\d)")
    times = []
    for c in mp.git_commits(repo, EPOCH):
        t = mp._iso(c["time"])
        if t and pat.match(c["subject"]):
            times.append(t)
    if len(times) < MIN_COMMITS:
        return f"{UNMEASURED} ({len(times)} commits)"
    return f"{(max(times) - min(times)).total_seconds() / 60:.0f}"


def transcript_tokens(path: Path) -> int:
    total = 0
    for obj in mp._jsonl(path):
        usage = mp._usage(obj)
        if usage and obj.get("type") == "assistant":
            total += sum(int(usage.get(k, 0) or 0) for k in TOKEN_KEYS)
    return total


def agent_tokens(tasks_dir: Path | None, row: int) -> str:
    pat = re.compile(rf"\brow[ -]0*{row}(?!\d)", re.I)
    found = []
    if tasks_dir and tasks_dir.is_dir():
        for raw in sorted(glob.glob(str(tasks_dir / "*" / "tasks" / "*.output"))):
            task = mp.read_task(Path(raw))
            if task and pat.search(task["head"]):
                found.append(Path(raw))
    if not found:
        return f"{UNMEASURED} (no transcript)"
    return f"{sum(transcript_tokens(p) for p in found) // 1000}k ({len(found)} transcripts)"


def table(repo: Path, rows: list[int], tasks_dir: Path | None) -> str:
    out = ["| " + " | ".join(HEADERS) + " |", "|" + "---|" * len(HEADERS)]
    for row in rows:
        minutes, tokens = expected_for(repo, row)
        cells = [str(row), str(minutes) if minutes is not None else UNMEASURED,
                 f"{tokens}k" if tokens is not None else UNMEASURED, wall_clock(repo, row),
                 agent_tokens(tasks_dir, row)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rows", default="1-16")
    ap.add_argument("--repo", default=str(HERE.parents[1]))
    ap.add_argument("--tasks-dir", default=None)
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    try:
        rows = parse_rows(args.rows)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    tasks_dir = Path(args.tasks_dir) if args.tasks_dir else mp._default_dirs(repo)[1]
    sys.stdout.write(table(repo, rows, tasks_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
