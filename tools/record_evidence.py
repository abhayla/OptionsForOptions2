#!/usr/bin/env python3
"""record_evidence.py - turn a checker agent's JSON reply into evidence files (OD-117: briefs, evidence and
handovers are produced by scripts from the agents' JSON, never hand-written).

Usage:
    python tools/record_evidence.py <reply.json | -> [--root ROOT] [--replace] [--dry-run]

The reply is a JSON list of blocks. Each block has `work_item` (W-###), `requirement` (REQ-###), `ac` (AC-#),
`verdict` (PASS or FAIL), `verified_by`, `commands` (list of the commands the checker ran) and `result` (the result
lines, a string or a list of strings); `notes` is optional (so is `builder`, which must then differ from
`verified_by`). One file per block is written to evidence/<W>/<AC>.md with the fields evidence.schema.json
names; `ac_fp` is computed by tools/ac_fp.py (written quoted) from the criterion's current text.

Fail closed: if anything about any block is wrong, nothing at all is written and the exit code is 1. Wrong means:
unreadable JSON or not a list, a block that is not an object, a missing or empty field, an unknown requirement or
criterion, a work item or AC id that is not well formed, `verified_by` equal to `builder` (trace_check refuses it),
a verdict other than PASS/FAIL, two blocks for one file, or an existing evidence file (unless --replace). A FAIL
verdict is written as `result: fail`. An empty list prints "nothing to record" and exits 0. Writes only under evidence/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ac_fp  # noqa: E402  (the one fingerprint lookup)

REQUIRED = ("work_item", "requirement", "ac", "verdict", "verified_by", "commands", "result")
WORK_ITEM_RE = re.compile(r"^W-\d{3,}$")
AC_RE = re.compile(r"^AC-\d+$")
YAML_WORDS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n"}  # plain scalars YAML would not read as text
VERDICTS = {"PASS": "pass", "FAIL": "fail"}


def _text(value: object) -> str | None:
    """A non-empty string, or a list of non-empty strings joined by newlines; otherwise None."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list) and value and all(isinstance(x, str) and x.strip() for x in value):
        return "\n".join(x.strip() for x in value)
    return None


def _commands(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list) and value and all(isinstance(x, str) and x.strip() for x in value):
        return "; ".join(x.strip() for x in value)
    return None


def render(block: dict, fp: str, today: str) -> str:
    """The evidence file text for one validated block (frontmatter in the order of the existing evidence files)."""
    def q(value: str, ensure_ascii: bool = False) -> str:
        """Plain when a YAML parser reads it back as the same string, else a JSON (= YAML) quoted string."""
        plain = re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value) and value.lower() not in YAML_WORDS
        return value if plain else json.dumps(value, ensure_ascii=ensure_ascii)

    lines = ["---", f"work_item: {block['work_item']}", f"requirement: {block['requirement']}", f"ac: {block['ac']}",
             f"result: {VERDICTS[block['verdict']]}", f"verified_by: {q(block['verified_by'], ensure_ascii=False)}"]
    if block.get("builder"):
        lines.append(f"builder: {q(block['builder'], ensure_ascii=False)}")
    lines += [f"date: {today}", f'ac_fp: "{fp}"',
              f"commands: {q(_commands(block['commands']), ensure_ascii=False)}", "---"]
    body = _text(block["result"]) or ""
    if block.get("notes"):
        body += "\n\n" + (_text(block["notes"]) or "")
    return "\n".join(lines) + "\n" + body + "\n"


def plan(blocks: object, root: Path, replace: bool, today: str) -> tuple[list[tuple[Path, str]], list[str]]:
    """(files to write, problems). Any problem means the whole batch is refused."""
    problems: list[str] = []
    out: list[tuple[Path, str]] = []
    if not isinstance(blocks, list):
        return [], ["the reply must be a JSON list of blocks"]
    seen: set[Path] = set()
    for i, b in enumerate(blocks, 1):
        tag = f"block {i}"
        if not isinstance(b, dict):
            problems.append(f"{tag}: not an object")
            continue
        bad = [k for k in REQUIRED if b.get(k) in (None, "", [])]
        if bad:
            problems.append(f"{tag}: missing or empty field(s): {', '.join(bad)}")
            continue
        if (not isinstance(b["work_item"], str) or not WORK_ITEM_RE.match(b["work_item"])
                or not isinstance(b["ac"], str) or not AC_RE.match(b["ac"])):
            problems.append(f"{tag}: work_item must look like W-### and ac like AC-#")
            continue
        tag = f"{b['work_item']} {b['ac']}"
        if not isinstance(b["requirement"], str) or not isinstance(b["verified_by"], str):
            problems.append(f"{tag}: requirement and verified_by must be strings")
            continue
        if b["verdict"] not in VERDICTS:
            problems.append(f"{tag}: verdict must be PASS or FAIL, got {b['verdict']!r}")
            continue
        if _text(b["result"]) is None or _commands(b["commands"]) is None:
            problems.append(f"{tag}: result and commands must be non-empty text or lists of text")
            continue
        if b.get("notes") is not None and _text(b["notes"]) is None:
            problems.append(f"{tag}: notes, when present, must be non-empty text")
            continue
        who = b["verified_by"].strip()
        if who.lower() == "builder" or (b.get("builder") and who == str(b["builder"]).strip()):
            problems.append(f"{tag}: verified_by {who!r} is the builder - not independent")
            continue
        fp, err = ac_fp.lookup(root, b["requirement"], b["ac"])
        if err or fp is None:
            problems.append(f"{tag}: {err}")
            continue
        path = root / "evidence" / b["work_item"] / f"{b['ac']}.md"
        if path in seen:
            problems.append(f"{tag}: two blocks for {path.relative_to(root).as_posix()}")
            continue
        seen.add(path)
        if path.exists() and not replace:
            problems.append(f"{tag}: {path.relative_to(root).as_posix()} already exists (use --replace)")
            continue
        out.append((path, render({**b, "verified_by": who}, fp, today)))
    return out, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write evidence files from a checker's JSON reply.")
    ap.add_argument("reply", help="JSON file holding a list of blocks, or - for stdin")
    ap.add_argument("--root", default=".", help="project root (default: the current directory)")
    ap.add_argument("--replace", action="store_true", help="rewrite an existing evidence file")
    ap.add_argument("--dry-run", action="store_true", help="print the paths that would be written; write nothing")
    a = ap.parse_args(argv)
    try:
        raw = sys.stdin.read() if a.reply == "-" else Path(a.reply).read_text(encoding="utf-8")
        blocks = json.loads(raw)
    except (OSError, ValueError) as e:
        print(f"record_evidence: cannot read the reply: {e}", file=sys.stderr)
        return 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    files, problems = plan(blocks, Path(a.root), a.replace, today)
    if problems:
        for p in problems:
            print(f"record_evidence: {p}", file=sys.stderr)
        print("record_evidence: nothing written", file=sys.stderr)
        return 1
    if not files:
        print("record_evidence: nothing to record")
        return 0
    for path, text in files:
        rel = path.relative_to(Path(a.root)).as_posix()
        if a.dry_run:
            print(f"would write {rel}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {rel}")
    return 0


def _stdio_replace() -> None:
    """Keep the stream's encoding but replace what it cannot hold, so a cp1252 console (Windows) never
    raises UnicodeEncodeError (issue 159)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    _stdio_replace()
    sys.exit(main())
