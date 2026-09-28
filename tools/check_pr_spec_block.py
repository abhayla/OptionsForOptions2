#!/usr/bin/env python3
"""check_pr_spec_block.py — refuse a pull request whose body lacks a valid
Spec-deviation block (see templates/project-os/.claude/rules/kit/spec-adherence.md
for the rule this enforces).

Usage:
    python tools/check_pr_spec_block.py [--body-file FILE] [--spec-root DIR]

Without --body-file, the PR body is read from the JSON file at
$GITHUB_EVENT_PATH, key pull_request.body (the shape GitHub Actions gives a
pull_request-triggered job).

Rules checked, in order:
  1. A line "Spec deviation" must exist, optionally as a markdown heading
     ("Spec deviation", "## Spec deviation", "### Spec-deviation", ...).
     Missing entirely (or an empty/null body) -> fail.
  2. A "Class:" line after it, whose value is exactly one of: none, 1, 2, 3.
  3. For Class 1, 2 or 3: a "Spec section:" line whose path (before any "#")
     exists under --spec-root (default "."), and, if given, whose "#anchor"
     matches a GitHub-style slug of a markdown heading in that file.
  4. For Class 2 or 3: a non-empty "Detail:" line.
  "Class: none" is a valid, passing answer.

Exit codes:
  0  a valid Spec-deviation block was found
  1  the body was read, but the block is missing or invalid — one reason per
     line on stderr
  2  the body could not be obtained at all (bad input: no --body-file, no
     GITHUB_EVENT_PATH, unreadable/malformed event JSON, or no pull_request
     key in it)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

HEADING_LINE_RE = re.compile(r"^\s*#{0,6}\s*spec[\s-]+deviation\s*:?\s*$", re.IGNORECASE)
CLASS_LINE_RE = re.compile(r"^\s*class\s*:\s*(.*?)\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*spec section\s*:\s*(\S+)", re.IGNORECASE)
DETAIL_RE = re.compile(r"^\s*detail\s*:\s*(.*)$", re.IGNORECASE)
HEADING_LEVEL_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

VALID_CLASSES = {"none", "1", "2", "3"}


def strip_fenced_code_blocks(body: str) -> str:
    """Return body with the contents of any ``` or ~~~ fenced block removed (the
    fence lines themselves become blank so line-based scanning downstream is
    unaffected). A block only present inside a fence must not be found."""
    lines = body.splitlines()
    out: list[str] = []
    in_fence = False
    fence_char = ""
    for line in lines:
        m = FENCE_RE.match(line)
        if m:
            token = m.group(1)
            this_char = token[0]
            if not in_fence:
                in_fence = True
                fence_char = this_char
                out.append("")
                continue
            if this_char == fence_char:
                in_fence = False
                fence_char = ""
                out.append("")
                continue
        if in_fence:
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def slugify(text: str) -> str:
    """A GitHub-style heading slug: lowercase, drop punctuation, spaces -> hyphens."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text


def heading_slugs(markdown_text: str) -> set[str]:
    """GitHub-style heading slugs, including the -1, -2, ... suffix GitHub adds
    to each repeat of an identical slug."""
    slugs: set[str] = set()
    seen_counts: dict[str, int] = {}
    for line in markdown_text.splitlines():
        m = HEADING_LEVEL_RE.match(line)
        if m:
            base = slugify(m.group(2))
            count = seen_counts.get(base, 0)
            seen_counts[base] = count + 1
            slug = base if count == 0 else f"{base}-{count}"
            slugs.add(slug)
    return slugs


def find_block(body: str) -> list[str] | None:
    body = strip_fenced_code_blocks(body)
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if HEADING_LINE_RE.match(line):
            return lines[i + 1 :]
    return None


def check(body: str | None, spec_root: str) -> list[str]:
    """Return a list of failure reasons; empty list means the block is valid."""
    if not body or not body.strip():
        return ["no Spec-deviation block (empty body)"]

    block_lines = find_block(body)
    if block_lines is None:
        return ["no Spec-deviation block"]

    cls: str | None = None
    section: str | None = None
    detail: str | None = None
    class_raw: str | None = None
    for line in block_lines:
        if HEADING_LEVEL_RE.match(line):
            break  # next section of the PR body: stop scanning the block
        if cls is None:
            m = CLASS_LINE_RE.match(line)
            if m:
                class_raw = m.group(1)
                continue
        if section is None:
            m = SECTION_RE.match(line)
            if m:
                section = m.group(1).strip()
                continue
        if detail is None:
            m = DETAIL_RE.match(line)
            if m:
                detail = m.group(1).strip()
                continue

    if class_raw is None:
        return ["missing Class: line in Spec-deviation block"]

    cls = class_raw.strip().lower()
    if cls not in VALID_CLASSES:
        # Anything with more than one token, or extra characters, is treated as
        # a template placeholder left as-is (e.g. "none | 1 | 2 | 3", "1 extra
        # words") rather than a genuinely unknown value the author typed.
        if len(class_raw.split()) != 1:
            return ["Class not filled in (placeholder left as is)"]
        return [f"invalid Class value '{class_raw.strip()}' (must be one of: none, 1, 2, 3)"]
    if cls == "none":
        return []

    reasons: list[str] = []
    if not section:
        reasons.append(f"Class {cls} requires a Spec section: line")
    else:
        path_part, _, anchor = section.partition("#")
        resolved_root = Path(spec_root).resolve()
        if PurePosixPath(path_part).is_absolute() or PureWindowsPath(path_part).is_absolute():
            reasons.append(f"Spec section path is outside the repo: {path_part}")
            full_path = None
        else:
            candidate = (resolved_root / path_part).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                reasons.append(f"Spec section path is outside the repo: {path_part}")
                full_path = None
            else:
                full_path = candidate
        if full_path is not None and not full_path.exists():
            reasons.append(f"Spec section path not found: {path_part}")
        elif full_path is not None and anchor:
            try:
                text = full_path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"could not read Spec section file {path_part}: {exc}")
                text = None
            if text is not None and anchor not in heading_slugs(text):
                reasons.append(f"anchor not found: #{anchor} in {path_part}")

    if cls in ("2", "3") and not detail:
        reasons.append(f"Class {cls} requires a non-empty Detail: line")

    return reasons


def get_body(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return (body, error). error is None on success (body may still be empty)."""
    if args.body_file:
        try:
            return Path(args.body_file).read_text(encoding="utf-8"), None
        except Exception as exc:  # noqa: BLE001
            return None, f"could not read --body-file {args.body_file}: {exc}"

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None, "no --body-file given and GITHUB_EVENT_PATH is not set"
    try:
        with open(event_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read/parse GITHUB_EVENT_PATH ({event_path}): {exc}"
    if "pull_request" not in data:
        return None, "event payload at GITHUB_EVENT_PATH has no pull_request key"
    return (data["pull_request"].get("body") or ""), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file")
    parser.add_argument("--spec-root", default=".")
    args = parser.parse_args(argv)

    body, err = get_body(args)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    reasons = check(body, args.spec_root)
    if reasons:
        for reason in reasons:
            print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
