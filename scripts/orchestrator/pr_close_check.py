"""Fail a PR whose body or commit messages hold a GitHub closing reference that is not a whole line.

GitHub closes an issue on: keyword + optional colon + whitespace + `#N` or `owner/repo#N`, in a PR body or in a commit
message reaching the default branch (also inside backticks, so those are flagged too). Only a whole line
`Fixes #N` / `Closes #N` / `Resolves #N` (optional trailing period) is allowed.

Usage:
  python scripts/orchestrator/pr_close_check.py --pr N
  python scripts/orchestrator/pr_close_check.py --body-file F [--commits-file G]
--commits-file holds commit messages separated by a line of exactly `---COMMIT---` (or one message).
Exit 0 pass, 1 offending reference, 2 input could not be read (fail closed).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

KEYWORD = r"(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)"
URL = r"https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+"
REF = rf"(?:{URL}|(?:[\w.-]+/[\w.-]+)?#\d+)"
WRAP = r"[*_`]*"
CLOSING = re.compile(rf"(?<![\w-]){WRAP}{KEYWORD}{WRAP}\s*:?{WRAP}\s+{REF}", re.IGNORECASE)
WHOLE_LINE = re.compile(rf"^(?:fixes|closes|resolves) (?:#\d+|{URL})\.?$", re.IGNORECASE)
SEPARATOR = "---COMMIT---"
HINT = ('qualified or prose closing reference; write "addresses items 1-3 of #N", '
        'or a whole line "Fixes #N" if all of it is done')


def check_text(label: str, text: str) -> list[str]:
    problems = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if not CLOSING.search(line):
            continue
        if WHOLE_LINE.match(line.strip()):
            continue
        problems.append(f'{label} line {number}: "{line.strip()}" - {HINT}')
    return problems


def check(body: str, commits: list[str]) -> list[str]:
    problems = check_text("body", body)
    for index, message in enumerate(commits, start=1):
        problems += check_text(f"commit {index}", message)
    return problems


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr")
    parser.add_argument("--body-file")
    parser.add_argument("--commits-file")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.pr:
            raw = subprocess.run(["gh", "pr", "view", str(args.pr), "--json", "body,commits"],
                                 capture_output=True, text=True, check=True, encoding="utf-8").stdout
            data = json.loads(raw)
            body = data["body"] or ""
            commits = [(c.get("messageHeadline") or "") + "\n" + (c.get("messageBody") or "")
                       for c in data["commits"]]
        elif args.body_file:
            body = _read(args.body_file)
            commits = []
            if args.commits_file:
                commits = [m for m in _read(args.commits_file).split(SEPARATOR) if m.strip()]
        else:
            print("pr_close_check: need --pr or --body-file", file=sys.stderr)
            return 2
    except Exception as error:  # fail closed
        print(f"pr_close_check: cannot read PR input: {error}", file=sys.stderr)
        return 2
    problems = check(body, commits)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("pr_close_check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
