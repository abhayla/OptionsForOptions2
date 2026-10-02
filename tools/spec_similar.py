#!/usr/bin/env python3
"""spec_similar.py — before writing a spec line, find what the spec already says like it (REQ-009 AC-2, OD-30).

Usage:
    python tools/spec_similar.py [ROOT] "<text>" [--top N]

Prints the N closest existing items (default 5), one per line: score, kind (requirement / decision), item id and
text. Items and scores come from tools/spec_text.py, the same tokenizer the blocking check tools/spec_dupes.py uses,
so a match here at >= 0.40 is exactly what CI would block as a same-kind restatement. Extend or cite a match; never
restate it.

Exit codes: 0 always when it ran (a lookup, not a gate); 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_text as st  # noqa: E402  (the one shared tokenizer, REQ-009 AC-2)


def similar(root: Path, text: str, top: int = 5) -> list[tuple[float, st.Item]]:
    query = st.words(text)
    scored = []
    for rec in st.load_records(st.Source(root)):
        for item in rec.items:
            s = st.score(query, item.words)
            if s > 0:
                scored.append((s, item))
    scored.sort(key=lambda p: (-p[0], p[1].label))
    return scored[:top]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("args", nargs="+", help='[ROOT] "<text>"')
    ap.add_argument("--top", type=int, default=5)
    ns = ap.parse_args(argv)
    st.utf8_stdout()
    if len(ns.args) > 2:
        ap.error('expected [ROOT] "<text>"')
    root, text = (Path(ns.args[0]), ns.args[1]) if len(ns.args) == 2 else (Path("."), ns.args[0])
    if not root.is_dir():
        print(f"spec_similar: ROOT not found: {root}", file=sys.stderr)
        return 2
    hits = similar(root, text, ns.top)
    if not hits:
        print("spec_similar: no existing item shares a content word with that text")
        return 0
    for s, item in hits:
        flag = "  <- CI would block a same-kind restatement" if s >= st.THRESHOLD else ""
        print(f"{s:.2f} {item.kind} {item.label}: {item.text}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
