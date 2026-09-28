#!/usr/bin/env python3
"""check_spec_refs.py — every finding under knowledge/findings/*.json must carry a
resolvable spec_ref, per templates/project-os/.claude/rules/kit/spec-adherence.md
("every finding in knowledge/findings/ carries spec_ref").

Usage:
    python tools/check_spec_refs.py [ROOT]

ROOT defaults to the current directory. Reads every ROOT/knowledge/findings/*.json
file and checks its "spec_ref" field:

  - must be present, and a non-empty list of strings;
  - EITHER every entry is "spec/<file>" or "spec/<file>#<anchor>" (path relative to
    ROOT), and the path must exist and, if given, the "#anchor" must match a
    GitHub-style slug of a markdown heading in that file;
  - OR the list is exactly ["none: <reason>"] (a non-empty reason after "none:").

A findings folder with zero *.json files passes and prints "0 findings checked"
(never silently exits 0 with no output).

Exit codes:
  0  every finding's spec_ref resolves (or the folder has zero findings)
  1  at least one finding is missing spec_ref, malformed, or unresolvable —
     one "ERROR <file>: <reason>" line per problem on stderr
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pathsafe import contained  # noqa: E402

HEADING_LEVEL_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text


def heading_slugs(markdown_text: str) -> set[str]:
    slugs = set()
    for line in markdown_text.splitlines():
        m = HEADING_LEVEL_RE.match(line)
        if m:
            slugs.add(slugify(m.group(2)))
    return slugs


def check_entry(entry: object, root: Path) -> str | None:
    """Return an error string, or None if the entry resolves."""
    if not isinstance(entry, str) or not entry.strip():
        return f"spec_ref entry is not a non-empty string: {entry!r}"
    path_part, _, anchor = entry.partition("#")
    full_path = contained(root, path_part)
    if full_path is None:
        return f"spec_ref path is outside the project: {path_part}"
    if not full_path.exists():
        return f"spec_ref path not found: {path_part}"
    if anchor:
        try:
            text = full_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return f"could not read {path_part}: {exc}"
        if anchor not in heading_slugs(text):
            return f"anchor not found: #{anchor} in {path_part}"
    return None


def check_finding(data: dict, root: Path) -> list[str]:
    if "spec_ref" not in data:
        return ["missing spec_ref"]
    spec_ref = data["spec_ref"]
    if not isinstance(spec_ref, list) or not spec_ref:
        return ["spec_ref must be a non-empty list"]

    if len(spec_ref) == 1 and isinstance(spec_ref[0], str) and spec_ref[0].startswith("none:"):
        reason = spec_ref[0][len("none:") :].strip()
        if not reason:
            return ["spec_ref 'none:' entry has no reason"]
        return []

    if any(isinstance(e, str) and e.startswith("none:") for e in spec_ref):
        return ["spec_ref mixes a 'none:' entry with real references (must be exactly ['none: <reason>'])"]

    errors = []
    for entry in spec_ref:
        err = check_entry(entry, root)
        if err:
            errors.append(err)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings_dir = root / "knowledge" / "findings"

    paths = sorted(glob.glob(str(findings_dir / "*.json")))
    if not paths:
        print(f"0 findings checked ({findings_dir} has no *.json files)")
        return 0

    had_error = False
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {path}: could not read/parse: {exc}", file=sys.stderr)
            had_error = True
            continue
        if not isinstance(data, dict):
            print(f"ERROR {path}: top level is not a JSON object", file=sys.stderr)
            had_error = True
            continue
        errors = check_finding(data, root)
        for err in errors:
            print(f"ERROR {path}: {err}", file=sys.stderr)
            had_error = True

    if not had_error:
        print(f"{len(paths)} finding(s) checked, all spec_ref valid")
    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
