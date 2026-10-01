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
    owner-questions/OQ-###.md      -> owner-question.schema.json (YAML frontmatter)
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
OQ_ID_RE = re.compile(r"^OQ-\d{3,}$")
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
    "owner-question": load_schema("owner-question.schema.json"),
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


FINDING_SCOPES = ("generic", "project")


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

    errors = []
    for e in validate_data("finding", data, file_path):
        if e.field == "scope" or (e.field == "(root)" and "'scope' is a required property" in e.message):
            have = data.get("scope", "<missing>")
            e = LintError(e.path, "scope",
                          f"finding needs `scope` set to one of {list(FINDING_SCOPES)} (found {have!r}): "
                          f"generic = the class can happen in any project that uses the kit, "
                          f"project = it is about this repository only")
        errors.append(e)
    return errors


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


# --- Requirement prioritization checks (REQ-006; owner decisions OD-33, OD-34) -------------------
# Order comes from layer, depends_on, risk and skeleton — never from a score (spec-first.md,
# "Build order"). Every message names the field and the ids involved.

LAYERS = ("core", "foundation", "feature", "polish")
# Inner-to-outer rank for the depends_on direction check: core and foundation are one ring
# (core may depend on foundation and vice versa), feature is outside them, polish outermost.
_LAYER_RING = {"core": 0, "foundation": 0, "feature": 1, "polish": 2}
SKELETON_LAYERS = ("core", "foundation")
SCORE_FIELDS = ("score", "rice", "wsjf", "value_score", "effort_score")
BUILD_ORDER_RULE = ".claude/rules/kit/spec-first.md, section \"Build order\""
# A smoke line runs with no shell (tools/run_smoke.py), so a shell operator would silently become an
# argument: `a && b` runs `a` with extra arguments and never runs `b`. Checked per shlex word.
SHELL_OPERATORS = ("&&", "||", "|", ";", "<", ">", ">>", "2>", "2>>", "&", "&>", "<<")
MISSING_LAYER_MESSAGE = ("`layer` is required: one of core, foundation, feature, polish (how close the "
                         "requirement is to the core); existing projects: see the kit CHANGELOG 1.3.0 "
                         "migration (.claude/kit/CHANGELOG.md)")


MISSING_SECTION_MESSAGE = ("`section` is required: a non-empty name grouping this requirement with the ones on "
                           "the same subject (REQ-009, OD-30); spec/requirements/INDEX.md lists requirements by "
                           "section; existing projects: see the kit CHANGELOG 1.4.0 migration")


def smoke_line_problem(line: str) -> str | None:
    """Why a smoke line cannot run without a shell, or None when it can."""
    import shlex

    try:
        words = shlex.split(line)
    except ValueError as exc:
        return f"cannot be split into words ({exc})"
    ops = [w for w in words if w in SHELL_OPERATORS]
    if ops:
        return (f"contains shell operator {ops[0]!r}; no shell runs a smoke command, so split it into "
                f"separate smoke lines")
    return None


def _requirement_record_errors(p: Path, data: dict) -> list[LintError]:
    """Per-file checks the JSON Schema cannot phrase with a useful message."""
    fp = str(p)
    errors: list[LintError] = []
    if "priority" in data:
        errors.append(LintError(fp, "priority",
                                "`priority` is no longer a requirement field (OD-34): state how close it is to "
                                "the core with `layer` (core, foundation, feature, polish) and, if it names a "
                                "version or date, move that to `release`"))
    for field in SCORE_FIELDS:
        if field in data:
            errors.append(LintError(fp, field,
                                    f"scoring field `{field}` is not allowed: build order comes from layer, "
                                    f"depends_on, risk and skeleton, never from a score ({BUILD_ORDER_RULE})"))
    if data.get("risk") == "high":
        reason = data.get("risk_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(LintError(fp, "risk_reason",
                                    "risk: high needs a non-empty risk_reason saying what could fail"))
    if data.get("skeleton") is True:
        smoke = data.get("smoke")
        if (not isinstance(smoke, list) or not smoke
                or any(not isinstance(c, str) or not c.strip() for c in smoke)):
            errors.append(LintError(fp, "smoke",
                                    "skeleton: true needs a non-empty `smoke` list of non-empty commands"))
        layer = data.get("layer")
        if layer not in SKELETON_LAYERS:
            errors.append(LintError(fp, "layer",
                                    f"skeleton: true needs layer core or foundation, not '{layer}'"))
    smoke = data.get("smoke")
    if isinstance(smoke, list):
        for line in smoke:
            if isinstance(line, str) and line.strip():
                problem = smoke_line_problem(line)
                if problem:
                    errors.append(LintError(fp, "smoke", f"smoke line {line!r} {problem}"))
    errors.extend(_duplicate_ac_errors(p, data))
    return errors


def _ac_ids(data: dict) -> list[str]:
    acs = data.get("acceptance_criteria")
    if not isinstance(acs, list):
        return []
    return [a["id"] for a in acs if isinstance(a, dict) and isinstance(a.get("id"), str)]


def _duplicate_ac_errors(p: Path, data: dict) -> list[LintError]:
    """A requirement may not repeat an acceptance-criterion id: one evidence file would stand for two
    criteria (kit defect #39)."""
    seen: set[str] = set()
    dups: list[str] = []
    for ac in _ac_ids(data):
        if ac in seen and ac not in dups:
            dups.append(ac)
        seen.add(ac)
    return [LintError(str(p), "acceptance_criteria",
                      f"duplicate acceptance criterion id '{ac}' in {p.name}: every id must be unique "
                      f"(renumber one of them)") for ac in dups]


_TESTS_REQUIRED_RE = re.compile(r"^\s*(AC-\d+)\s*:")


def _tests_required_ac(entry: object) -> str | None:
    """'AC-1: tests/x.py::name' -> 'AC-1'; None when the entry does not start with 'AC-<n>:'."""
    if not isinstance(entry, str):
        return None
    m = _TESTS_REQUIRED_RE.match(entry)
    return m.group(1) if m else None


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Strongly connected components with more than one member (Tarjan, iterative).
    Self-loops are reported separately as self-dependencies."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for start in sorted(graph):
        if start in index:
            continue
        work = [(start, iter(sorted(graph[start])))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in graph:
                    continue
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(sorted(graph[nxt]))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))
    return sorted(out)


def check_requirement_set(records: list[tuple[Path, dict]]) -> list[LintError]:
    """Repo-level checks across all requirements: depends_on targets, self-dependency, cycles,
    inner-depends-on-outer, and at least one walking-skeleton requirement."""
    errors: list[LintError] = []
    by_id: dict[str, tuple[Path, dict]] = {}
    for p, data in records:
        rid = data.get("id")
        if isinstance(rid, str):
            by_id[rid] = (p, data)

    graph: dict[str, list[str]] = {}
    for rid, (p, data) in sorted(by_id.items()):
        deps = data.get("depends_on") or []
        if not isinstance(deps, list):
            continue  # schema reports the type
        graph[rid] = []
        layer = data.get("layer")
        seen_deps: set[str] = set()
        for dep in deps:
            if not isinstance(dep, str):
                continue
            if dep in seen_deps:
                errors.append(LintError(str(p), "depends_on", f"'{dep}' is listed more than once"))
                continue
            seen_deps.add(dep)
            if dep == rid:
                errors.append(LintError(str(p), "depends_on", f"{rid} depends on itself"))
                continue
            if dep not in by_id:
                errors.append(LintError(str(p), "depends_on",
                                        f"'{dep}' is not an existing requirement id (no spec/requirements/{dep}.md)"))
                continue
            graph[rid].append(dep)
            dep_layer = by_id[dep][1].get("layer")
            if (layer in _LAYER_RING and dep_layer in _LAYER_RING
                    and _LAYER_RING[dep_layer] > _LAYER_RING[layer]):
                errors.append(LintError(str(p), "depends_on",
                                        f"{rid} (layer {layer}) depends on {dep} (layer {dep_layer}): an inner "
                                        f"item may not depend on an outer one; move {dep} inward or drop the "
                                        f"dependency"))

    for comp in _cycles(graph):
        first = by_id[comp[0]][0]
        errors.append(LintError(str(first.parent), "depends_on",
                                f"dependency cycle among {', '.join(comp)}"))

    if by_id and not any(d.get("skeleton") is True for _p, d in by_id.values()):
        req_dir = next(iter(by_id.values()))[0].parent
        errors.append(LintError(str(req_dir), "skeleton",
                                "no requirement has skeleton: true; mark the walking-skeleton requirement "
                                "(layer core or foundation) with skeleton: true and its smoke commands"))
    return errors


def lint_requirements(req_dir: Path) -> list[LintError]:
    """Lint every spec/requirements/REQ-*.md: schema, id, per-file and repo-level checks."""
    errors: list[LintError] = []
    records: list[tuple[Path, dict]] = []
    for p in sorted(req_dir.glob("REQ-*.md")):
        for e in lint_markdown_file(p, "requirement", REQ_ID_RE):
            if e.field == "(root)" and e.message == "'layer' is a required property":
                e = LintError(e.path, "layer", MISSING_LAYER_MESSAGE)
            elif (e.field == "(root)" and e.message == "'section' is a required property") or e.field == "section":
                e = LintError(e.path, "section", MISSING_SECTION_MESSAGE)
            errors.append(e)
        data, err = parse_frontmatter(p)
        if err is not None:
            continue
        if isinstance(data.get("id"), str) and not REQ_ID_RE.match(data["id"]):
            errors.append(LintError(str(p), "id", f"id '{data['id']}' does not match pattern REQ-###"))
        errors.extend(_requirement_record_errors(p, data))
        records.append((p, data))
    errors.extend(check_requirement_set(records))
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


def _unknown_ac_errors(p: Path, data: dict, root: Path) -> list[LintError]:
    """A work item's tests_required may only name AC ids that one of its requirement_ids has."""
    req_dir = root / "spec" / "requirements"
    known: set[str] = set()
    resolved = 0
    for rid in data.get("requirement_ids", []) or []:
        rp = req_dir / f"{rid}.md" if isinstance(rid, str) else None
        if rp is None or not rp.is_file():
            continue
        rdata, err = parse_frontmatter(rp)
        if err is None and isinstance(rdata, dict):
            resolved += 1
            known.update(_ac_ids(rdata))
    errors = []
    for entry in data.get("tests_required", []) or []:
        ac = _tests_required_ac(entry)
        if ac is None:
            errors.append(LintError(str(p), "tests_required",
                                    f"tests_required entry must start with 'AC-<n>:' in {p.name} "
                                    f"(entry: {entry!r})"))
        elif resolved and ac not in known:
            errors.append(LintError(str(p), "tests_required",
                                    f"tests_required names {ac} but none of {p.name}'s requirement_ids "
                                    f"{data.get('requirement_ids')} has that acceptance criterion "
                                    f"(entry: {entry!r})"))
    return errors


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
        counts["requirement"] = counts.get("requirement", 0) + len(list(req_dir.glob("REQ-*.md")))
        errors.extend(lint_requirements(req_dir))

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
                errors.extend(_unknown_ac_errors(p, data, root))

    oq_dir = root / "owner-questions"
    if oq_dir.is_dir():
        recognized = True
        files = sorted(oq_dir.glob("OQ-*.md"))
        counts["owner-question"] = counts.get("owner-question", 0) + len(files)
        for p in files:
            errors.extend(lint_markdown_file(p, "owner-question", OQ_ID_RE))

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
