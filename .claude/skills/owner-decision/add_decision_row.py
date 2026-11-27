#!/usr/bin/env python3
"""Add one numbered decision point to an ADR file, in the house style of ADR-330 points (59) to (63).

Usage:
  python add_decision_row.py ADR-FILE --number 64 --title "The Exit dialog when ..." \
      --asked "owner 27 Nov evening, question tool" --decision "..." --real-case "27 Nov 16:02: ..." \
      --reasons "he opens it after the close: to ... (served: ...) or ... (served: ...)" \
      --not-chosen "grey the button; leave it enabled" [--after N] [--width W] [--write]
  or the same fields as one JSON object: --json fields.json   (keys: number title asked decision real_case reasons
  not_chosen after)

The row reads:  (N) <title> (<asked>): <decision> Real case <real_case>. Reasons <reasons>. Not chosen: <not_chosen>.
Without --write it only prints the row (for review). With --write it inserts it after point --after (default: the last
numbered point, before any closing paragraph such as "Not in this record:"). It refuses a number that already exists,
and wraps at the width of the file's own numbered points (override with --width). Standard library only.
Exit 0 ok; 1 refused (number exists, no points found, missing field); 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

POINT = re.compile(r"^ {2}\((\d+)\) ")
CLOSERS = re.compile(r"^ {2}(Not in this record:|Owner's standing instruction|Also \d)")
FIELDS = ["title", "asked", "decision", "real_case", "reasons", "not_chosen"]


def point_blocks(lines: list[str]) -> list[tuple[int, int, int]]:
    """(number, first line index, end index exclusive) of each numbered point."""
    starts = [(int(m.group(1)), i) for i, ln in enumerate(lines) if (m := POINT.match(ln))]
    out = []
    for num, i in starts:
        j = i + 1
        while j < len(lines) and lines[j].startswith("  ") and not POINT.match(lines[j]) and not CLOSERS.match(lines[j]):
            j += 1
        out.append((num, i, j))
    return out


def file_width(lines: list[str], blocks: list[tuple[int, int, int]]) -> int:
    """The wrap width of the file's own points: the median of each recent point's longest line (one outlier line,
    such as a pasted sentence, must not widen every new row)."""
    maxima = sorted(max(len(lines[k]) for k in range(i, j)) for _, i, j in blocks[-5:])
    return maxima[len(maxima) // 2] if maxima else 118


def build_row(f: dict, width: int) -> list[str]:
    def end(s: str) -> str:
        s = s.strip()
        return s if s.endswith((".", "?", "!", '"')) else s + "."
    text = (f"({f['number']}) {f['title'].strip()} ({f['asked'].strip()}): {end(f['decision'])} "
            f"Real case {f['real_case'].strip().rstrip('.')}. Reasons {f['reasons'].strip().rstrip('.')}. "
            f"Not chosen: {f['not_chosen'].strip().rstrip('.')}.")
    return textwrap.wrap(text, width=width, initial_indent="  ", subsequent_indent="  ",
                         break_long_words=False, break_on_hyphens=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("adr")
    ap.add_argument("--json", dest="json_file")
    ap.add_argument("--number", type=int)
    for k in FIELDS:
        ap.add_argument("--" + k.replace("_", "-"), dest=k)
    ap.add_argument("--after", type=int, help="insert after this point (default: the last one)")
    ap.add_argument("--width", type=int)
    ap.add_argument("--write", action="store_true", help="insert the row into the file (default: print only)")
    ns = ap.parse_args(argv)

    f: dict = json.loads(Path(ns.json_file).read_text(encoding="utf-8")) if ns.json_file else {}
    for k in ["number", "after"] + FIELDS:
        v = getattr(ns, k, None)
        if v is not None:
            f[k] = v
    missing = [k for k in ["number"] + FIELDS if not f.get(k)]
    if missing:
        print("REFUSED: missing " + ", ".join(missing))
        return 1

    path = Path(ns.adr)
    lines = path.read_text(encoding="utf-8").split("\n")
    blocks = point_blocks(lines)
    if not blocks:
        print("REFUSED: no numbered points '  (N) ' found in " + str(path))
        return 1
    n = int(f["number"])
    if n in {b[0] for b in blocks}:
        print(f"REFUSED: point ({n}) already exists in {path} (last is ({blocks[-1][0]}))")
        return 1
    after = int(f.get("after") or blocks[-1][0])
    target = next((b for b in blocks if b[0] == after), None)
    if target is None:
        print(f"REFUSED: no point ({after}) to insert after")
        return 1
    f["number"] = n
    row = build_row(f, ns.width or file_width(lines, blocks))
    print("\n".join(row))
    if n != blocks[-1][0] + 1 and after == blocks[-1][0]:
        print(f"NOTE: the last point is ({blocks[-1][0]}); you asked for ({n}).", file=sys.stderr)
    if ns.write:
        lines[target[2]:target[2]] = row
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"WROTE point ({n}) after point ({after}) in {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
