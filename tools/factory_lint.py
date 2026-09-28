#!/usr/bin/env python3
"""factory_lint.py — validate Factory / Project OS artifacts against their JSON Schemas.

Usage:
    python tools/factory_lint.py [ROOT ...] [--quiet]

For each ROOT given (default: current directory), walks the tree and validates every
artifact file it finds by path convention:

    spec/requirements/REQ-###.md   -> requirement.schema.json  (YAML frontmatter)
    spec/decisions/ADR-###.md      -> decision.schema.json     (YAML frontmatter)
    spec/decisions/OD-#.md         -> decision.schema.json     (YAML frontmatter)
    work/W-###.md                  -> work-item.schema.json    (YAML frontmatter)
    releases/R-###.md              -> release.schema.json      (YAML frontmatter)
    capabilities/**/capability.json -> capability.schema.json  (JSON)

Prints one line per error: "path: field: message"
Exits 1 if any error was found across any root, 0 otherwise.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft7Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "factory" / "schemas"

REQ_ID_RE = re.compile(r"^REQ-\d{3,}$")
ADR_ID_RE = re.compile(r"^(ADR-\d{3,}|OD-\d+)$")
WORK_ID_RE = re.compile(r"^W-\d{3,}$")
RELEASE_ID_RE = re.compile(r"^R-\d{3,}$")
AC_ID_RE = re.compile(r"^AC-\d+$")


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_SCHEMAS = {
    "requirement": load_schema("requirement.schema.json"),
    "work-item": load_schema("work-item.schema.json"),
    "release": load_schema("release.schema.json"),
    "capability": load_schema("capability.schema.json"),
    "decision": load_schema("decision.schema.json"),
    "evidence": load_schema("evidence.schema.json"),
    "finding": load_schema("finding.schema.json"),
}

_VALIDATORS = {k: Draft7Validator(v) for k, v in _SCHEMAS.items()}


class LintError:
    __slots__ = ("path", "field", "message")

    def __init__(self, path: str, field: str, message: str):
        self.path = path
        self.field = field
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.field}: {self.message}"


# frontmatter-parser-splits-on-any-triple-dash: a delimiter line is '---' alone on its
# line (trailing whitespace allowed), never a '---' substring inside a value.
_FRONTMATTER_DELIM_RE = re.compile(r"(?m)^---[ \t]*\r?$")


def parse_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """Parse YAML frontmatter delimited by --- lines. Returns (data, error)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem errors
        return None, f"could not read file: {exc}"

    if not text.startswith("---"):
        return None, "missing YAML frontmatter (file must start with '---')"

    # frontmatter-parser-splits-on-any-triple-dash: split only on a line that is
    # EXACTLY '---' (after stripping trailing whitespace), never on a '---' that
    # merely appears inside a quoted frontmatter value.
    delims = list(_FRONTMATTER_DELIM_RE.finditer(text))
    if len(delims) < 2:
        return None, "malformed YAML frontmatter (need opening and closing '---')"

    fm_text = text[delims[0].end():delims[1].start()]
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        return None, f"invalid YAML: {exc}"

    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, "frontmatter must be a YAML mapping"

    data = _stringify_dates(data)
    return data, None


def _stringify_dates(value):
    """YAML auto-parses unquoted ISO dates (2026-09-23) into date/datetime objects.
    Coerce them back to strings so schemas can declare plain string fields."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _stringify_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_dates(v) for v in value]
    return value


def field_path(err) -> str:
    if not err.path:
        return "(root)"
    return ".".join(str(p) for p in err.path)


def validate_data(kind: str, data: dict, file_path: str) -> list[LintError]:
    validator = _VALIDATORS[kind]
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        errors.append(LintError(file_path, field_path(err), err.message))
    return errors


def check_id_matches_filename(data: dict, filename: str, id_re: re.Pattern, file_path: str) -> list[LintError]:
    errors = []
    stem = Path(filename).stem
    declared_id = data.get("id")
    if declared_id is None:
        return errors  # already reported by schema (required field)
    if not isinstance(declared_id, str):
        return errors
    if declared_id != stem:
        errors.append(
            LintError(file_path, "id", f"id '{declared_id}' does not match filename '{stem}'")
        )
    return errors


def lint_markdown_file(path: Path, kind: str, id_re: re.Pattern) -> list[LintError]:
    file_path = str(path)
    data, err = parse_frontmatter(path)
    if err is not None:
        return [LintError(file_path, "frontmatter", err)]

    errors = validate_data(kind, data, file_path)
    errors.extend(check_id_matches_filename(data, path.name, id_re, file_path))
    return errors


def lint_capability_file(path: Path) -> list[LintError]:
    file_path = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        return [LintError(file_path, "file", f"could not read file: {exc}")]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [LintError(file_path, "json", f"invalid JSON: {exc}")]

    if not isinstance(data, dict):
        return [LintError(file_path, "(root)", "capability.json must contain a JSON object")]

    return validate_data("capability", data, file_path)


def lint_finding_file(path: Path) -> list[LintError]:
    """knowledge/findings/<slug>.json: validate against finding.schema.json."""
    file_path = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        return [LintError(file_path, "file", f"could not read file: {exc}")]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [LintError(file_path, "json", f"invalid JSON: {exc}")]

    if not isinstance(data, dict):
        return [LintError(file_path, "(root)", "finding file must contain a JSON object")]

    return validate_data("finding", data, file_path)


def lint_evidence_file(path: Path) -> list[LintError]:
    """evidence/<W-id>/<AC-id>.md: validate frontmatter, and cross-check that `ac`
    matches the filename and `work_item` matches the immediate parent directory
    name (the path convention that trace_check.py relies on)."""
    file_path = str(path)
    data, err = parse_frontmatter(path)
    if err is not None:
        return [LintError(file_path, "frontmatter", err)]

    errors = validate_data("evidence", data, file_path)

    ac = data.get("ac")
    stem = path.stem
    if isinstance(ac, str) and AC_ID_RE.match(stem) and ac != stem:
        errors.append(LintError(file_path, "ac", f"ac '{ac}' does not match filename '{stem}'"))

    work_item = data.get("work_item")
    parent = path.parent.name
    if isinstance(work_item, str) and WORK_ID_RE.match(parent) and work_item != parent:
        errors.append(
            LintError(file_path, "work_item", f"work_item '{work_item}' does not match parent directory '{parent}'")
        )

    return errors


def find_requirement_ids(root: Path) -> set[str] | None:
    """Return the set of REQ ids under root/spec/requirements, or None if that dir is absent."""
    req_dir = root / "spec" / "requirements"
    if not req_dir.is_dir():
        return None
    ids = set()
    for p in req_dir.glob("REQ-*.md"):
        data, err = parse_frontmatter(p)
        if err is None and isinstance(data, dict) and isinstance(data.get("id"), str):
            ids.add(data["id"])
    return ids


def lint_root(root: Path, quiet: bool) -> tuple[list[LintError], dict[str, int], bool]:
    """Lint one root. Returns (errors, counts, recognized) where counts maps artifact
    kind (as it appears by path convention under this root) to how many files of that
    kind were found and checked (used for the summary line), and `recognized` is True
    iff this root contains at least one directory matching a known Factory/Project-OS
    artifact convention (spec/requirements, spec/decisions, work, releases, capabilities,
    or is itself a capabilities dir) — regardless of whether any files were found inside
    it yet. A root with none of those directories at all (wrong folder, typo) is NOT
    recognized; a root with e.g. an empty spec/requirements/ (valid but not yet
    populated) IS recognized. See main() for how this distinguishes the two."""
    errors: list[LintError] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}
    recognized = False

    req_dir = root / "spec" / "requirements"
    if req_dir.is_dir():
        recognized = True
        files = sorted(req_dir.glob("REQ-*.md"))
        counts["requirement"] = counts.get("requirement", 0) + len(files)
        for p in files:
            errors.extend(lint_markdown_file(p, "requirement", REQ_ID_RE))
            data, err = parse_frontmatter(p)
            if err is None and isinstance(data.get("id"), str) and not REQ_ID_RE.match(data["id"]):
                errors.append(LintError(str(p), "id", f"id '{data['id']}' does not match pattern REQ-###"))

    dec_dir = root / "spec" / "decisions"
    if dec_dir.is_dir():
        recognized = True
        files = sorted(list(dec_dir.glob("ADR-*.md")) + list(dec_dir.glob("OD-*.md")))
        counts["decision"] = counts.get("decision", 0) + len(files)
        for p in files:
            errors.extend(lint_markdown_file(p, "decision", ADR_ID_RE))
            data, err = parse_frontmatter(p)
            if err is None and isinstance(data.get("id"), str) and not ADR_ID_RE.match(data["id"]):
                errors.append(LintError(str(p), "id", f"id '{data['id']}' does not match pattern ADR-### or OD-#"))

    work_dir = root / "work"
    req_ids = find_requirement_ids(root)
    if work_dir.is_dir():
        recognized = True
        files = sorted(work_dir.glob("W-*.md"))
        counts["work-item"] = counts.get("work-item", 0) + len(files)
        for p in files:
            errors.extend(lint_markdown_file(p, "work-item", WORK_ID_RE))
            data, err = parse_frontmatter(p)
            if err is None and isinstance(data.get("id"), str) and not WORK_ID_RE.match(data["id"]):
                errors.append(LintError(str(p), "id", f"id '{data['id']}' does not match pattern W-###"))
            if err is None and req_ids is not None:
                for rid in data.get("requirement_ids", []) or []:
                    if isinstance(rid, str) and rid not in req_ids:
                        warnings.append(
                            f"{p}: requirement_ids: '{rid}' not found under {req_dir}"
                        )

    rel_dir = root / "releases"
    if rel_dir.is_dir():
        recognized = True
        files = sorted(rel_dir.glob("R-*.md"))
        counts["release"] = counts.get("release", 0) + len(files)
        for p in files:
            errors.extend(lint_markdown_file(p, "release", RELEASE_ID_RE))
            data, err = parse_frontmatter(p)
            if err is None and isinstance(data.get("id"), str) and not RELEASE_ID_RE.match(data["id"]):
                errors.append(LintError(str(p), "id", f"id '{data['id']}' does not match pattern R-###"))

    # A root can itself BE a capabilities directory (root/**/capability.json found
    # directly under it), or CONTAIN one at root/capabilities/. Detect both
    # structurally (not by matching the literal name "capabilities") so
    # `factory_lint.py capabilities` (root IS the capabilities dir) is not a
    # silent no-op regardless of what the directory happens to be named — see RCA
    # in the commit/PR for why this matters.
    cap_candidates: set[Path] = set()
    cap_dir = root / "capabilities"
    if cap_dir.is_dir():
        recognized = True
        cap_candidates.update(cap_dir.rglob("capability.json"))
    # root itself is a capabilities-shaped dir: it contains at least one
    # capability.json anywhere under it (excluding the root/capabilities/ case
    # already handled above, which would double count nothing since paths differ).
    root_own_caps = list(root.rglob("capability.json"))
    if root_own_caps:
        recognized = True
        cap_candidates.update(root_own_caps)
    if cap_candidates:
        files = sorted(cap_candidates)
        counts["capability"] = counts.get("capability", 0) + len(files)
        for p in files:
            errors.extend(lint_capability_file(p))

    evidence_dir = root / "evidence"
    if evidence_dir.is_dir():
        recognized = True
        files = sorted(evidence_dir.glob("*/*.md"))
        counts["evidence"] = counts.get("evidence", 0) + len(files)
        for p in files:
            errors.extend(lint_evidence_file(p))

    findings_dir = root / "knowledge" / "findings"
    if findings_dir.is_dir():
        recognized = True
        files = sorted(findings_dir.glob("*.json"))
        counts["finding"] = counts.get("finding", 0) + len(files)
        for p in files:
            errors.extend(lint_finding_file(p))

    if not quiet:
        for w in warnings:
            print(f"WARNING: {w}")

    return errors, counts, recognized


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint Factory / Project OS artifacts against their schemas.")
    parser.add_argument("roots", nargs="*", default=["."], help="Root directories to lint (default: .)")
    parser.add_argument("--quiet", action="store_true", help="Suppress warnings, print only errors")
    args = parser.parse_args(list(argv) if argv is not None else None)

    all_errors: list[LintError] = []
    total_counts: dict[str, int] = {}
    any_root_bad = False

    for root_str in args.roots:
        root = Path(root_str)
        if not root.is_dir():
            print(f"{root_str}: (root): not a directory")
            all_errors.append(LintError(root_str, "(root)", "not a directory"))
            any_root_bad = True
            continue

        errors, counts, recognized = lint_root(root, args.quiet)
        all_errors.extend(errors)

        if not recognized:
            # Wrong folder, typo, or a dir with none of the known Factory/Project-OS
            # artifact conventions at all — distinct from a recognized-but-currently-
            # empty structure (e.g. a freshly scaffolded spec/requirements/ with no
            # REQ files yet), which is fine and counts as 0 checked, not an error.
            print(f"{root_str}: (root): no Factory artifacts found under {root_str}")
            all_errors.append(LintError(root_str, "(root)", f"no Factory artifacts found under {root_str}"))
            any_root_bad = True
            continue

        for kind, n in counts.items():
            total_counts[kind] = total_counts.get(kind, 0) + n

    for e in all_errors:
        print(str(e))

    if not args.quiet:
        summary = ", ".join(f"{n} {kind}" for kind, n in sorted(total_counts.items())) if total_counts else "0 artifacts"
        print(f"checked: {summary}")

    if all_errors or any_root_bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
