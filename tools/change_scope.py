#!/usr/bin/env python3
"""Classify a pull request's changed paths as `docs-only` or `code` (REQ-057 AC-5).

Usage: python tools/change_scope.py --base <sha> [--head <sha>]

Prints exactly one word, `docs-only` or `code`, and exits 0 either way. It says `docs-only` only when
every changed path (both paths of a rename) sits under a listed docs folder, or is a markdown file at the
repo root, AND ends in a listed lower-case extension, AND is not named like a test file. Anything else, and
anything it cannot resolve (unreadable diff, unknown base, shallow clone, any exception), is `code`:
a wrong `code` costs one full test run, a wrong `docs-only` skips tests that could have caught a break.

Stdlib only. The rule tables are module-level data on purpose (the tests loosen each one in turn).
"""
from __future__ import annotations

import argparse
import subprocess
import sys

DOCS_FOLDERS = ("docs", "spec", "views", "knowledge", "evidence", "work", "releases", "plans", "owner-questions")
ALLOWED_EXTENSIONS = (".md", ".json", ".yaml", ".yml", ".csv", ".html", ".svg", ".png")
ROOT_FILE_EXTENSIONS = (".md",)
# A file with one of these names anywhere is code, whatever folder it sits in (pytest collects by name).
CODE_FILE_NAMES = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")
CODE_NAME_PREFIXES = ("test_",)
CODE_NAME_MARKERS = ("_test.",)
# A path whose old or new mode is anything else (symlink 120000, gitlink 160000, ...) is code; 000000 is the
# absent side of an add or a delete.
ALLOWED_MODES = ("100644", "100755", "000000")
# Only these git statuses are understood; any other (T type change, U unmerged, C copy, X, B) is code.
ALLOWED_STATUSES = ("A", "M", "D", "R")

DOCS_ONLY = "docs-only"
CODE = "code"
# The answer for every shape this tool cannot resolve. Data, so a mutation test can flip it.
ON_DOUBT = CODE
# Folder and extension comparison is exact. Data, so a mutation test can loosen it.
CASE_SENSITIVE = True


def path_is_docs(path: str) -> bool:
    """True only for a path that is provably a records file. Case-sensitive on purpose."""
    if not path or path != path.strip() or "\\" in path or "\x00" in path or path.startswith("/"):
        return False
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    name = parts[-1]
    lowered = name.lower()
    if name in CODE_FILE_NAMES or lowered in CODE_FILE_NAMES:
        return False
    if lowered.startswith(CODE_NAME_PREFIXES) or any(m in lowered for m in CODE_NAME_MARKERS):
        return False
    dot = name.rfind(".")
    ext = name[dot:] if dot > 0 else ""
    top = parts[0]
    if not CASE_SENSITIVE:
        ext, top = ext.lower(), top.lower()
    if len(parts) == 1:
        return ext in ROOT_FILE_EXTENSIONS
    return top in DOCS_FOLDERS and ext in ALLOWED_EXTENSIONS


def classify_entries(entries: list[tuple[str, list[str]]]) -> str:
    """entries: (git status letter, [paths], (old mode, new mode)) per changed file; a rename carries old
    and new path. The mode pair is always supplied by parse_raw_z; a bare 2-tuple (tests only) has none."""
    if not entries:
        return ON_DOUBT
    for entry in entries:
        status, paths = entry[0], entry[1]
        modes = entry[2] if len(entry) > 2 else ()
        if any(m not in ALLOWED_MODES for m in modes):
            return ON_DOUBT
        if status not in ALLOWED_STATUSES or not paths:
            return ON_DOUBT
        if len(paths) != (2 if status == "R" else 1):
            return ON_DOUBT
        if not all(path_is_docs(p) for p in paths):
            return ON_DOUBT
    return DOCS_ONLY


def parse_raw_z(raw: str) -> list[tuple[str, list[str], tuple[str, str]]] | None:
    """Parse `git diff --raw -z` output (`:oldmode newmode oldsha newsha STATUS` NUL path [NUL path]);
    None when it does not parse."""
    tokens = raw.split("\x00")
    if tokens and tokens[-1] == "":
        tokens.pop()
    entries: list[tuple[str, list[str], tuple[str, str]]] = []
    i = 0
    while i < len(tokens):
        meta = tokens[i].split(" ")
        if len(meta) != 5 or not meta[0].startswith(":"):
            return None
        letter = meta[4][:1]
        if not letter.isalpha() or not letter.isupper():
            return None
        count = 2 if letter in ("R", "C") else 1
        paths = tokens[i + 1:i + 1 + count]
        if len(paths) != count:
            return None
        entries.append((letter, paths, (meta[0][1:], meta[1])))
        i += 1 + count
    return entries


def changed_entries(base: str, head: str) -> list[tuple[str, list[str], tuple[str, str]]] | None:
    if not base or base.startswith("-") or not head or head.startswith("-"):
        return None
    proc = subprocess.run(
        ["git", "--no-pager", "-c", "core.quotepath=off", "diff", "--raw", "-M", "-z", "--no-abbrev",
         "--no-ext-diff", f"{base}...{head}", "--"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if proc.returncode != 0:
        return None
    return parse_raw_z(proc.stdout)


def classify_range(base: str, head: str = "HEAD") -> str:
    """Never raises: any failure is `code`."""
    try:
        entries = changed_entries(base, head)
        if entries is None:
            return ON_DOUBT
        return classify_entries(entries)
    except Exception:
        return ON_DOUBT


def main(argv: list[str] | None = None) -> int:
    try:
        ap = argparse.ArgumentParser(description=__doc__)
        ap.add_argument("--base", default="")
        ap.add_argument("--head", default="HEAD")
        args = ap.parse_args(argv)
        result = classify_range(args.base, args.head)
    except BaseException:  # argparse exits via SystemExit; still answer `code`
        result = ON_DOUBT
    print(result)
    return 0


def _stdio_replace() -> None:
    """Keep the stream's encoding but replace what it cannot hold, so a cp1252 console (Windows) never
    raises UnicodeEncodeError on text from a child process, GitHub or a spec file (issue 159)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    _stdio_replace()
    sys.exit(main())
