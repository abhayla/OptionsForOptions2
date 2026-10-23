"""SessionStart hook: print the ADR-178 tracker rows whose status is `open` or `missed`, so no session starts without
seeing what is not yet followed. Always exits 0; a missing or unreadable tracker prints nothing (fail open).
`open_rows(text)` returns the row lines to print."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TRACKER = Path(__file__).resolve().parents[2] / "docs" / "process" / "adr-178-tracker.md"
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*(open|missed)\b[^|]*\|\s*$", re.I)


def open_rows(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = ROW.match(line.strip())
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            out.append(f"  row {m.group(1)} [{m.group(3).lower()}] {cells[0]} -- limit {cells[-1]}")
    return out


def main() -> int:
    try:
        rows = open_rows(TRACKER.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return 0
    if rows:
        sys.stdout.write("ADR-178 tracker (docs/process/adr-178-tracker.md): rows not yet followed - run "
                         "`python scripts/orchestrator/measure_process.py` at session end and update the Status column "
                         "from its output only:\n" + "\n".join(rows) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - a hook never blocks a session start
        sys.exit(0)
