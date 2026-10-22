"""Check that every spec quote in a builder brief appears verbatim in the spec text it is attributed to.

Finding brief-rule-from-memory: orchestrators wrote spec rules into briefs from memory and were wrong.
Usage: python scripts/orchestrator/check_brief.py <brief-file> [--strict] [--root <repo root>]
Exit 0: every cited quote is verbatim.  Exit 1: a quote is not in its cited spec text (FAIL), or with --strict
a quote has no citation (UNCITED).  Exit 2: bad usage.
Citation = the nearest REQ-### [AC-n] / ADR-### / Q### id in front of the quote, within the same paragraph;
when a REQ+AC cite and another id both precede the quote, the REQ+AC cite wins.
A Q### quote passes if the id's open-questions section or any spec/ file mentioning the id contains it.
Also (guard-set checks, exit 1): (a) some line must name all three literals `tests/test_*.py`,
`tests/errors/test_write_allowlist.py` and `tests/errors/test_producer_inventory.py` (the repo-wide guard tests);
(b) a Tier A brief whose first 10 lines mention a guard/door/gate/scan needs a `Findings checked:` line whose ids
each exist as knowledge/findings/<id>.json;
(c) any brief (any tier) whose first 10 lines mention a guard/door/gate/scan needs a line starting `Threat model:`
(outside a code fence) that contains both `in scope` and `out of scope`.
(d) a BUILDER brief (it has a `Standing items:` line; verifier and measure briefs do not) needs `Attack list:` followed
by a numbered item (`1.`), and a `Budget:` line whose minutes/calls are a size pair from docs/process/row-review.md R3
(30/40 S, 60/80 M or each part of an L, or a fix/re-check pair of at most half: 15/20, 20/30, 30/40).
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


GUARD_TESTS = ("tests/test_*.py", "tests/errors/test_write_allowlist.py",
               "tests/errors/test_producer_inventory.py", "-m repo_scan")
GUARD_WORD_RE = re.compile(r"\b(guards?|doors?|gates?|scans?)\b", re.I)
FINDINGS_RE = re.compile(r"^\W*Findings checked:(.*)$", re.I | re.M)
THREAT_RE = re.compile(r"^\W*Threat model:(.*)$", re.I)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
STANDING_RE = re.compile(r"^\W*Standing items:", re.I | re.M)
ATTACK_RE = re.compile(r"^\W*Attack list:(.*)$", re.I)
NUMBERED_RE = re.compile(r"^\W*\d+\.\s+\S")
BLOCK_END_RE = re.compile(r"^(#|[A-Z][\w /()-]*:(\s|$))")  # a heading or the next `Label:` line ends the attack list
BUDGET_RE = re.compile(r"^\W*Budget:\s*(\d+)\s*min\b[^,\n]*,\s*(\d+)\s*tool calls", re.I | re.M)
SIZE_PAIRS = {(30, 40), (60, 80), (15, 20), (20, 30)}  # row-review R3: S, M / each part of an L, fix and re-check


def _threat_model_lines(lines: list[str]) -> list[str]:
    """Lines starting `Threat model:` (case-insensitive, leading punctuation ok) outside a ``` or ~~~ fence."""
    out, fence = [], None
    for line in lines:
        m = FENCE_RE.match(line)
        if m and fence is None:
            fence = m.group(1)
        elif m and m.group(1) == fence:
            fence = None
        elif fence is None and THREAT_RE.match(line):
            out.append(line)
    return out


MIN_ATTACKS = 5  # row-review R1 (meta review after row 3): at least five numbered attacks


def _attack_count(lines: list[str]) -> int:
    """Numbered items in the `Attack list:` block (its own line remainder, then the following lines up to the next
    `Label:` line or heading); wrapped continuation lines of an item are not counted. 0 when there is no such line."""
    best = 0
    for i, line in enumerate(lines):
        m = ATTACK_RE.match(line)
        if not m:
            continue
        count = 1 if NUMBERED_RE.match(m.group(1)) else 0
        for nxt in lines[i + 1:]:
            if NUMBERED_RE.match(nxt):
                count += 1
            elif BLOCK_END_RE.match(nxt):
                break
        best = max(best, count)
    return best


def _has_attack_list(lines: list[str]) -> bool:
    """`Attack list:` followed by at least MIN_ATTACKS numbered items."""
    return _attack_count(lines) >= MIN_ATTACKS


def check_builder_brief(brief: str) -> list[str]:
    """Row-review R1 and R3 for a builder brief (one with a `Standing items:` line); other briefs are unaffected."""
    if not STANDING_RE.search(brief):
        return []
    misses: list[str] = []
    if not _has_attack_list(brief.splitlines()):
        misses.append(f"MISSING Attack list: `Attack list:` followed by at least {MIN_ATTACKS} numbered items "
                      "(`1.` ...) (row-review R1)")
    pairs = [(int(a), int(b)) for a, b in BUDGET_RE.findall(brief)]
    if not pairs or any(p not in SIZE_PAIRS for p in pairs):
        misses.append("MISSING size budget: `Budget: <N> min wall-clock, <M> tool calls` must be 30/40 (S), 60/80 "
                      "(M, or each part of an L) or a fix/re-check pair 15/20, 20/30, 30/40 (row-review R3)")
    misses.extend(_size_misses(brief, pairs))
    if not CI_LINE_RE.search(brief):
        misses.append("MISSING CI line: `CI: <job/step that runs the new tests>; vars: <the variables they need>` "
                      "(row-review R11: a test that passes only in the builder's shell, or never runs in CI)")
    build = _build_section(brief)
    if BUILD_GUARD_RE.search(build) and not ALLOW_LIST_RE.search(build):
        misses.append("MISSING allow-list: the build section describes a scan/guard/gate/detector but never says "
                      "`allow-list` (finding guard-as-forbidden-list, row-review R8)")
    return misses


SIZE_LINE_RE = re.compile(r"^\W*Size:\s*(S|M|L)\b[^\n]*?(\d+)\s*files?[^\n]*?(\d+)\s*items?([^\n]*)$", re.I | re.M)
CI_LINE_RE = re.compile(r"^\W*CI:\s*\S", re.M)
SMALL_PAIRS = {(30, 40), (15, 20), (20, 30)}  # S, and the fix / re-check pairs
MAX_S_FILES, MAX_S_ITEMS = 5, 4  # row-review R3; meta review after row 6: finish/fix briefs had 5 items on S budgets


def _size_misses(brief: str, pairs: list[tuple[int, int]]) -> list[str]:
    """R3 by machine (meta review after row 6): a `Size: S|M|L, <n> files, <k> items[, backend + frontend]` line, and a
    budget that matches it - more than 5 files, more than 4 items, or backend + frontend can never take an S budget."""
    m = SIZE_LINE_RE.search(brief)
    if not m:
        return ["MISSING size line: `Size: S|M|L, <n> files, <k> items` (add `backend + frontend` when both change) "
                "(row-review R3)"]
    size, files, items, rest = m.group(1).upper(), int(m.group(2)), int(m.group(3)), m.group(4).lower()
    spans_both = "backend" in rest and "frontend" in rest
    too_big = files > MAX_S_FILES or items > MAX_S_ITEMS or spans_both
    if too_big and size == "S":
        return [f"MISSING size: {files} files, {items} items{' across backend and frontend' if spans_both else ''} "
                "is not S - declare M (60/80) or split it (row-review R3)"]
    if size == "S" and any(p not in SMALL_PAIRS for p in pairs):
        return ["MISSING size budget: a Size S brief takes 30/40 (or a fix pair 15/20, 20/30) (row-review R3)"]
    if size in {"M", "L"} and any(p != (60, 80) for p in pairs):
        return [f"MISSING size budget: a Size {size} brief (or each part of an L) takes 60/80 (row-review R3)"]
    return []


BUILD_GUARD_RE = re.compile(r"\b(scan|guard|gate|detector)s?\b", re.I)
ALLOW_LIST_RE = re.compile(r"allow[- ]list", re.I)  # not `test_write_allowlist.py`, which every brief names


def _build_section(brief: str) -> str:
    """The text of the `## What to build` section (to the next `## ` heading); '' when the brief has none."""
    if "## What to build" not in brief:
        return ""
    section = brief.split("## What to build", 1)[1].split("\n## ", 1)[0]
    # The section ends at the next labelled block too (row 7: "no static detector" in Standing items tripped R8).
    return re.split(r"\n\W*(?:Attack list|Standing items|Threat model|Reviewer checklist):", section, maxsplit=1)[0]


def check_guard_set(brief: str, root: Path) -> list[str]:
    """One-line reasons a brief misses the repo-wide guard tests or (Tier A guard work) the findings ids."""
    misses: list[str] = []
    if not any(all(g in line for g in GUARD_TESTS) for line in brief.splitlines()):
        misses.append("MISSING guard tests: no line names all of `tests/test_*.py`, "
                      "`tests/errors/test_write_allowlist.py` and "
                      "`tests/errors/test_producer_inventory.py` and `-m repo_scan` in its test commands")
    lines = brief.splitlines()
    if any("Tier A" in line for line in lines) and any(GUARD_WORD_RE.search(x) for x in lines[:10]):
        m = FINDINGS_RE.search(brief)
        ids = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", m.group(1)) if m else []
        if not ids:
            misses.append("MISSING `Findings checked:` line with finding ids (Tier A guard/door/gate/scan brief)")
        misses.extend(f"UNKNOWN finding id `{fid}`: no knowledge/findings/{fid}.json" for fid in ids
                      if not (root / "knowledge" / "findings" / f"{fid}.json").is_file())
    has_threat = any("in scope" in t.lower() and "out of scope" in t.lower() for t in _threat_model_lines(lines))
    if any(GUARD_WORD_RE.search(x) for x in lines[:10]) and not has_threat:
        misses.append("MISSING `Threat model:` line containing both `in scope` and `out of scope` "
                      "(guard/door/gate/scan brief)")
    return misses


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
    text = path.read_text(encoding="utf-8")
    results = check_text(text, Path(args.root))
    misses = check_guard_set(text, Path(args.root)) + check_builder_brief(text)
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
    out.extend(misses)
    sys.stdout.write("\n".join(out) + "\n")
    return 1 if fails or misses or (args.strict and (uncited or short)) else 0


if __name__ == "__main__":
    sys.exit(main())
