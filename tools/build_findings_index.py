#!/usr/bin/env python3
"""build_findings_index.py — generate knowledge/findings/INDEX.md from the JSON
finding files under knowledge/findings/.

Usage:
    python tools/build_findings_index.py [ROOT] [--check]

ROOT defaults to the current directory. The tool reads every
ROOT/knowledge/findings/*.json file, validates it against
factory/schemas/finding.schema.json (see knowledge/findings/README.md for the
finding shape), and writes ROOT/knowledge/findings/INDEX.md: a generated,
do-not-hand-edit table with one row per VALID finding (id, class, detection
status, other fields), sorted by id.

Round 4 (RCA): three rounds patched one malformed-input shape at a time
(wrong-shaped fields, malformed JSON, empty folder, then a list/dict id, deep
nesting, list-valued detection, raw Python values) and kept finding another.
The gap was that finding files had no defined format, so the tool kept
guessing. Now every file is validated whole against one schema: a file that
fails validation is never rendered from partially-trusted data. A file with
fields beyond id/class/detection/mechanism/fix/first_seen (unknown to this
generator, but schema `additionalProperties: true` at the top level) still
renders, with an "other fields" column listing the extra key names (REQ-001
AC-3).

--check: do not write. Exit 0 if INDEX.md exists and matches exactly what would
be generated AND no file failed to load/validate; exit 1 otherwise (missing,
stale, or any file errored).

Exit codes:
  0  index written/current and every file validated
  1  index missing/stale, OR at least one file failed to load or validate
     (reported as "ERROR <file>: <reason>" on stderr; the other valid files
     still render)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "factory" / "schemas" / "finding.schema.json"
)
KNOWN_FIELDS = {"id", "class", "mechanism", "first_seen", "fix", "detection"}

# Round 5 RCA: json.loads' own recursion behaviour on deep nesting depends on the
# OS / build (Windows hit Python's recursion limit and rejected a 3000-deep file;
# Linux's json C accelerator parsed the same file fine and accepted it) — a limit
# left to the runtime gives different results on different machines. MAX_DEPTH is
# an explicit, OS-independent ceiling, checked by a string-aware scan of the raw
# text BEFORE json.loads ever runs, so the result is identical on every OS.
MAX_DEPTH = 64


def _json_nesting_depth(text: str) -> int:
    """Return the maximum [/{ nesting depth in a raw JSON text, without parsing
    it (no recursion, one pass over the characters). String contents (and
    escaped characters within them) are skipped so brackets inside a string
    value are not counted."""
    depth = 0
    max_depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch in "}]":
            depth -= 1
    return max_depth

HEADER = (
    "<!-- generated — do not edit by hand; regenerate with "
    "python tools/build_findings_index.py -->\n"
)


def _load_validator() -> Draft7Validator:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    return Draft7Validator(schema)


def _escape_cell(text: object) -> str:
    """Make a value safe as a single Markdown table cell: escape pipes, collapse
    newlines/whitespace to single spaces."""
    if text is None:
        text = ""
    text = str(text)
    text = text.replace("|", "\\|")
    text = " ".join(text.split())
    return text


def load_findings(
    findings_dir: Path, validator: Draft7Validator
) -> tuple[list[dict], list[str]]:
    """Load and schema-validate every *.json finding file in findings_dir, sorted
    by id. Returns (findings, errors).

    Each file is wrapped in one try/except Exception around the whole load (open,
    decode, json.loads, schema validation), so bad bytes, bad JSON, wrong types,
    deep nesting (RecursionError) and any other malformed shape are all caught
    the same way and reported as "ERROR <file>: <reason>" without stopping the
    other files from rendering or crashing the run. A file whose top level is not
    a well-formed finding per the schema is skipped entirely — nothing partially
    trusted is rendered. A duplicate id is an ERROR naming both files; the second
    file is dropped.
    """
    findings = []
    errors = []
    seen_ids: dict[str, str] = {}
    for path in sorted(glob.glob(str(findings_dir / "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            depth = _json_nesting_depth(text)
            if depth > MAX_DEPTH:
                raise ValueError(f"nesting deeper than {MAX_DEPTH}")
            data = json.loads(text)
            schema_errors = sorted(
                validator.iter_errors(data), key=lambda e: list(e.path)
            )
            if schema_errors:
                first = schema_errors[0]
                field = ".".join(str(p) for p in first.path) or "(root)"
                raise ValueError(f"{field}: {first.message}")
        except Exception as exc:  # noqa: BLE001 - any failure here is an ERROR, never a crash
            errors.append(f"ERROR {path}: {exc}")
            continue

        source_file = os.path.basename(path)
        data["_source_file"] = source_file

        fid = data["id"]  # schema guarantees a string id is present
        if fid in seen_ids:
            errors.append(
                f"ERROR {path}: duplicate id '{fid}' also used by {seen_ids[fid]}"
            )
            continue
        seen_ids[fid] = source_file

        findings.append(data)
    findings.sort(key=lambda d: d["id"])
    return findings, errors


def render_index(findings: list[dict]) -> str:
    lines = [HEADER, "\n", "# Findings index\n", "\n"]
    lines.append(
        f"{len(findings)} finding(s), generated from `knowledge/findings/*.json`.\n"
    )
    lines.append("\n")
    lines.append("| id | class | detection status | other fields |\n")
    lines.append("|---|---|---|---|\n")
    for finding in findings:
        fid = _escape_cell(finding["id"])
        fclass = _escape_cell(finding["class"])
        status = _escape_cell(finding["detection"]["status"])
        extra_keys = sorted(
            k for k in finding.keys() if k not in KNOWN_FIELDS and k != "_source_file"
        )
        other = _escape_cell(", ".join(extra_keys)) if extra_keys else ""
        lines.append(f"| {fid} | {fclass} | {status} | {other} |\n")
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings_dir = root / "knowledge" / "findings"
    index_path = findings_dir / "INDEX.md"

    validator = _load_validator()
    findings, errors = load_findings(findings_dir, validator)
    for error in errors:
        print(error, file=sys.stderr)

    if not findings:
        print(f"no finding files found under {findings_dir}", file=sys.stderr)
        return 1

    generated = render_index(findings)

    if args.check:
        if errors:
            return 1
        if not index_path.exists():
            print(f"{index_path}: missing")
            return 1
        current = index_path.read_text(encoding="utf-8")
        if current != generated:
            print(f"{index_path}: stale (does not match generated output)")
            return 1
        return 0

    index_path.write_text(generated, encoding="utf-8")
    print(f"wrote {index_path} ({len(findings)} finding(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
