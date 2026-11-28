#!/usr/bin/env python3
"""Before asking the owner: find where the spec and the decisions index already say something on the subject.

Usage: python .claude/skills/owner-decision/spec_search.py "<the subject's own words>" [--top 12] [--root .]

Prints the best-matching lines across spec/ (all .md) and docs/process/owner-decisions-by-subject-*.md as
`score  file:line  text`, plus the ADR point or heading each line sits under. A line scores by how many different
query words (matched by their first 5 letters, so "stops" finds "stop") it holds; a full-phrase hit adds a bonus.
It reads lines, not records: tools/spec_similar.py ranks whole requirement and decision sentences and is the tool for
"is my NEW spec line a restatement" (R1); this one answers "was this subject already decided, and where".
Zero hits proves only that these words failed: try the subject's other words before you ask (rule D1). Exit 0 always.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

STOP = set("the and for are but not you all can had her was one our out has have this that with from they will what "
           "when who how why does into than then them his she its been were would could should about which there "
           "their after before over under shown show shows page screen".split())
POINT = re.compile(r"^ {2}\((\d+)\) ")


def stems(text: str) -> list[str]:
    ws = [w for w in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower()) if w not in STOP]
    return sorted({w[:5] for w in ws})


def files(root: Path) -> list[Path]:
    out = sorted((root / "spec").rglob("*.md"))
    out += sorted((root / "docs" / "process").glob("owner-decisions-by-subject-*.md"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("subject")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--root", default=".")
    ns = ap.parse_args(argv)
    root = Path(ns.root)
    q = stems(ns.subject)
    phrase = " ".join(re.findall(r"[a-z0-9]+", ns.subject.lower()))
    if not q:
        print("no searchable words in the subject")
        return 0
    hits: list[tuple[float, str, int, str, str]] = []
    for f in files(root):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        where = ""
        rel = f.relative_to(root).as_posix()
        for n, ln in enumerate(lines, 1):
            m = POINT.match(ln)
            if m:
                where = f"point ({m.group(1)})"
            elif ln.startswith("#"):
                where = ln.strip("# ").strip()[:60]
            low = ln.lower()
            got = sum(1 for s in q if s in low)
            if got < min(2, len(q)):
                continue
            score = got / len(q) + (0.5 if phrase and phrase in " ".join(re.findall(r"[a-z0-9]+", low)) else 0)
            hits.append((score, rel, n, where, ln.strip()))
    hits.sort(key=lambda h: (-h[0], h[1], h[2]))
    print(f"query words (first 5 letters): {' '.join(q)}")
    for score, rel, n, where, text in hits[: ns.top]:
        print(f"{score:4.2f}  {rel}:{n}  [{where}]  {text[:150]}")
    print(f"{len(hits)} matching lines; showing {min(len(hits), ns.top)}. "
          "If one of these answers the question, cite it and do not ask.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
