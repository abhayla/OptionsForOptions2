#!/usr/bin/env python3
"""Check a lane brief: every required part is there, and it does not repeat the standing rules.

Usage: python .claude/skills/lanes/check_brief.py <brief-file>   (or "-" for stdin)
Exit 0: the brief passes. Exit 1: it fails; each problem is printed on its own line.
Pure standard library. The standing rules live in SKILL.md ("Standing rules for every lane"); a brief names them once
on its first line and carries only what differs for this lane.
"""
import re
import sys

MAX_RULE_LINES = 15  # lines that restate a standing rule; more than this and the brief is no longer short

# (name, what to add, patterns; every pattern must match somewhere in the brief)
REQUIRED = [
    ("pointer to the standing rules", 'first line must say to read "Standing rules for every lane" in the lanes skill',
     None),
    ("Budget line", "add `Budget: <N> min wall-clock, <M> tool calls`",
     [r"(?im)^\W*Budget:\s*\d+\s*min\s+wall-clock,\s*\d+\s*tool calls"]),
    ("branch and base", "add `Branch from: <base>` and `Push to: <the lane's own branch>`",
     [r"(?im)^\W*Branch(?: from)?:\s*\S", r"(?im)^\W*Push to:\s*\S"]),
    ("file ownership", "add `May edit:` (this lane's files) and `Do not edit:` (other lanes' files, with lane names)",
     [r"(?im)^\W*May edit:\s*\S", r"(?im)^\W*Do not edit:\s*\S"]),
    ("queue", "add a `Queue` heading and numbered items (1., 2., ...) each with its real case",
     [r"(?im)^\W*(?:#+\s*)?Queue\b", r"(?m)^\s*1[.)]\s+\S"]),
    ("core and proof", "add `Core:` and `Proof:` (the smallest run on real input, and what to read back)",
     [r"(?im)^\W*Core:\s*\S", r"(?im)^\W*Proof:\s*\S"]),
]

# Key phrases of the standing rules. A brief line matching any of them counts as a repeated rule.
RULE_PHRASES = [
    r"times? (?:are|in) IST", r"work continuously", r"paper equals real", r"never call a broker order endpoint",
    r"exact decimal", r"one module per capability", r"decision-support wording", r"pending owner read",
    r"test first", r"every answer state", r"no migration", r"targeted tests", r"tail only", r"logs? to a file",
    r"sonnet builds", r"haiku (?:does|for) mechanical", r"opus only", r"ruff is at", r"git add, (?:git )?commit",
    r"separate calls", r"at most two rounds", r"no github issues", r"do not file github issues",
    r"fixed, not tested", r"market closed and (?:for )?live", r"status line at the (?:very )?top", r"@parent",
    r"safe to close", r"HTTPS_PROXY", r"PREPUSH_GATE_ALLOW", r"one file,? one lane", r"no waste",
    r"task / model / minutes", r"read[- ]first list",
]
RULE_RE = re.compile("|".join(RULE_PHRASES), re.I)


def check(text: str) -> list[str]:
    problems: list[str] = []
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    if not re.search(r"standing rules for every lane", first, re.I):
        problems.append(f"MISSING pointer to the standing rules: {REQUIRED[0][1]}")
    for name, advice, patterns in REQUIRED[1:]:
        missing = [p for p in patterns if not re.search(p, text)]
        if missing:
            problems.append(f"MISSING {name}: {advice}")
    rule_lines = [i + 1 for i, ln in enumerate(lines[1:], start=1) if RULE_RE.search(ln)]
    if len(rule_lines) > MAX_RULE_LINES:
        shown = ", ".join(map(str, rule_lines[:12]))
        problems.append(
            f"TOO LONG: {len(rule_lines)} lines repeat a standing rule (limit {MAX_RULE_LINES}; lines {shown}"
            f"{', ...' if len(rule_lines) > 12 else ''}). Delete them: the first line already points to the rules.")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    text = sys.stdin.read() if argv[1] == "-" else open(argv[1], encoding="utf-8").read()
    problems = check(text)
    if problems:
        print("\n".join(problems))
        print(f"BRIEF FAIL ({len(problems)} problem{'s' if len(problems) != 1 else ''})")
        return 1
    print(f"BRIEF PASS ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
