"""copy_from_check.py <repo-root> <brief.md> [<brief.md> ...] [--append]

Copy first (ADR-047): every row of spec/technical-design/legacy-reuse.md that names a requirement the brief covers must
be cited in the brief. Prints the missing rows per brief (exit 1 when any is missing). With --append, writes them into
the brief as a "Legacy map rows" section the builder must act on: COPY/ADAPT rows are used or the brief records why
not; REFERENCE rows are read before designing; SKIP rows are listed so nobody re-surveys them.
Why: on 2026-10-21 15 of 24 builder-scope lane briefs left out map rows for their own requirements (C2/C5 missed the
ADAPT rows for ticker/pool.py, ticker/router.py and rate_limiter.py), which would have rebuilt existing code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MAP = Path("spec") / "technical-design" / "legacy-reuse.md"
REQ = re.compile(r"REQ-\d{3}")
HEADING = "## Legacy map rows (copy_from_check.py)"
MIN_ARGS = 2  # the repo root and at least one brief


def map_rows(root: Path) -> list[str]:
    return [line for line in (root / MAP).read_text(encoding="utf-8").splitlines()
            if line.startswith("| ") and REQ.search(line)]


def brief_reqs(text: str) -> set[str]:
    head = text.split("## What to build", 1)[0] if "## What to build" in text else text[:3000]
    return set(REQ.findall(head))


def row_key(row: str) -> str:
    first = row.split("|")[1].strip()
    files = re.findall(r"`([^`]+)`", first)
    return files[0].rsplit("/", 1)[-1].split(".", 1)[0] if files else first[:30]


def missing(rows: list[str], text: str) -> list[str]:
    reqs = brief_reqs(text)
    return [r for r in rows if reqs & set(REQ.findall(r)) and row_key(r) not in text]


def main(argv: list[str]) -> int:
    append = "--append" in argv
    args = [a for a in argv if a != "--append"]
    if len(args) < MIN_ARGS:
        print(__doc__)
        return 2
    root, briefs = Path(args[0]), [Path(a) for a in args[1:]]
    rows, bad = map_rows(root), 0
    for brief in briefs:
        text = brief.read_text(encoding="utf-8")
        gaps = missing(rows, text)
        if not gaps:
            continue
        bad += 1
        print(f"## {brief.name}: {len(gaps)} map row(s) not cited")
        for g in gaps:
            print("  ", g[:160])
        if append and HEADING not in text:
            block = [HEADING,
                     "Rows of the legacy-reuse map that name this brief's requirements. Act on each:",
                     "COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read",
                     "before designing; SKIP -> do not re-survey.", "", *gaps, ""]
            brief.write_text(text.rstrip("\n") + "\n\n" + "\n".join(block), encoding="utf-8", newline="")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
