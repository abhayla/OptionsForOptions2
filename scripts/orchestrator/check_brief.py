"""Check that every spec quote in a builder brief appears verbatim in the spec text it is attributed to.

Finding brief-rule-from-memory: orchestrators wrote spec rules into briefs from memory and were wrong.
Usage: python scripts/orchestrator/check_brief.py <brief-file> [--strict] [--root <repo root>]
Exit 0: every cited quote is verbatim.  Exit 1: a quote is not in its cited spec text (FAIL), or with --strict
a quote has no citation (UNCITED).  Exit 2: bad usage.
Citation = the nearest REQ-### [AC-n] / ADR-### / Q### id in front of the quote, within the same paragraph;
when a REQ+AC cite and another id both precede the quote, the REQ+AC cite wins.
A Q### quote passes if the id's open-questions section or any spec/ file mentioning the id contains it.
A quote under 12 characters is TOO-SHORT (exit 1 only with --strict); "..." fragments must occur in order.
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

QUOTE_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
ID_RE = re.compile(r"(REQ-\d{3})(?:[\s,]*(AC-\d+))?|(ADR-\d{3})|\b(Q\d{2,3})\b")
ELLIPSIS_RE = re.compile(r"…|\.\.\.")
MAX_PREFIX = 200
MIN_QUOTE = 12
INHERIT_PREFIX = 20  # "and", ",", "or" between two quotes that share one citation


@dataclass
class Result:
    line: int
    quote: str
    cite: str | None
    status: str  # OK | FAIL | UNCITED | TOO-SHORT
    detail: str = ""


def norm(text: str) -> str:
    """Whitespace-normalise and unify straight/curly quotes and dashes."""
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("''", "'")
    return re.sub(r"\s+", " ", text).strip()


def _ac_text(raw: str, ac: str) -> str | None:
    m = re.search(rf"^- id: {re.escape(ac)}\s*$(.*?)(?=^- id: |^[A-Za-z_]+:|^---|\Z)", raw, re.S | re.M)
    return m.group(1) if m else None


def _q_text(raw: str, q: str) -> str:
    m = re.search(rf"^##+ {re.escape(q)}\b(.*?)(?=^## |\Z)", raw, re.S | re.M)
    return m.group(1) if m else raw


def _q_texts(root: Path, q: str) -> tuple[list[str] | None, str]:
    """A Q-id's text: its open-questions section, plus every other spec/ file that mentions the id."""
    oq = root / "spec" / "open-questions.md"
    texts: list[str] = []
    if oq.is_file():
        texts.append(_q_text(oq.read_text(encoding="utf-8"), q))
    pat = re.compile(r"(?<![0-9A-Za-z])" + re.escape(q) + r"(?![0-9A-Za-z])")
    for f in sorted((root / "spec").rglob("*.md")):
        if f == oq:
            continue
        raw = f.read_text(encoding="utf-8")
        if pat.search(raw):
            texts.append(raw)
    if not texts:
        return None, f"{q} not found in spec/"
    return texts, ""


def _in_order(text: str, fragments: list[str]) -> bool:
    hay, pos = norm(text), 0
    for f in fragments:
        i = hay.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def scope_text(root: Path, cite: str) -> tuple[list[str] | None, str]:
    """Return (candidate texts, any one of which may hold the quote; error) for 'REQ-060 AC-2', 'ADR-010', 'Q237'."""
    head = cite.split()[0]
    if head.startswith("Q"):
        return _q_texts(root, head)
    if head.startswith("REQ-"):
        path = root / "spec" / "requirements" / f"{head}.md"
    elif head.startswith("ADR-"):
        path = root / "spec" / "decisions" / f"{head}.md"
    else:
        path = root / "spec" / "open-questions.md"
    if not path.is_file():
        return None, f"{path.relative_to(root).as_posix()} not found"
    raw = path.read_text(encoding="utf-8")
    if head.startswith("REQ-") and " " in cite:
        ac = _ac_text(raw, cite.split()[1])
        if ac is None:
            return None, f"{cite.split()[1]} not found in {head}"
        return [ac], ""
    return [raw], ""


def nearest_line(text: str, quote: str) -> str:
    lines = [norm(x) for x in text.splitlines() if norm(x)]
    best = difflib.get_close_matches(norm(quote), lines, n=1, cutoff=0.0)
    return best[0] if best else ""


def _cite_from(match: re.Match[str]) -> str:
    if match.group(1):
        return " ".join(x for x in (match.group(1), match.group(2)) if x)
    return match.group(3) or match.group(4)


def check_text(brief: str, root: Path) -> list[Result]:
    results: list[Result] = []
    prev_end = 0
    prev_cite: str | None = None
    for m in QUOTE_RE.finditer(brief):
        quote = m.group(1) or m.group(2)
        start = max(prev_end, m.start() - MAX_PREFIX)
        prefix = re.split(r"\n\s*\n", brief[start:m.start()])[-1]
        ids = list(ID_RE.finditer(prefix))
        cite: str | None = None
        if ids:
            with_ac = [i for i in ids if i.group(1) and i.group(2)]
            cite = _cite_from((with_ac or ids)[-1])
        elif prev_cite and len(prefix.strip()) <= INHERIT_PREFIX and m.start() - prev_end <= INHERIT_PREFIX:
            cite = prev_cite
        prev_end, prev_cite = m.end(), cite
        line = brief.count("\n", 0, m.start()) + 1
        if cite is None:
            results.append(Result(line, quote, None, "UNCITED"))
            continue
        texts, err = scope_text(root, cite)
        if texts is None:
            results.append(Result(line, quote, cite, "FAIL", err))
            continue
        frags = [norm(f).strip(" .,;:") for f in ELLIPSIS_RE.split(quote) if norm(f).strip(" .,;:")]
        if not any(_in_order(t, frags) for t in texts):
            results.append(Result(line, quote, cite, "FAIL", "nearest spec line: "
                                  + nearest_line(texts[0], frags[0] if frags else quote)))
        elif len(norm(quote)) < MIN_QUOTE:
            results.append(Result(line, quote, cite, "TOO-SHORT", f"under {MIN_QUOTE} characters: proves little"))
        else:
            results.append(Result(line, quote, cite, "OK"))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("brief")
    ap.add_argument("--strict", action="store_true", help="an uncited quote also fails")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args(argv)
    path = Path(args.brief)
    if not path.is_file():
        sys.stderr.write(f"brief not found: {path}\n")
        return 2
    results = check_text(path.read_text(encoding="utf-8"), Path(args.root))
    out = []
    for r in results:
        short = r.quote if len(r.quote) <= 80 else r.quote[:77] + "..."
        out.append(f'{r.status:7} line {r.line}: {r.cite or "(no citation)"}: "{short}"')
        if r.detail:
            out.append(f"        {r.detail}")
    fails = sum(r.status == "FAIL" for r in results)
    uncited = sum(r.status == "UNCITED" for r in results)
    short = sum(r.status == "TOO-SHORT" for r in results)
    ok = len(results) - fails - uncited - short
    out.append(f"{len(results)} quotes: {ok} OK, {fails} FAIL, {uncited} UNCITED, {short} TOO-SHORT")
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if fails or (args.strict and (uncited or short)) else 0


if __name__ == "__main__":
    sys.exit(main())
