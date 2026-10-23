"""Render a builder / fix / round-2 checker brief from the Measure agent's JSON (ADR-178: briefs are generated).

Usage: python scripts/orchestrator/make_brief.py <row> <measure.json> [--out <path>] [--kind build|fix|verify-r2]
                                                 [--root <repo root>]
Exit 0: the brief passes check_brief.py and copy_from_check.py (printed to stdout, or written to --out).
Exit 1: refused (an unknown or missing key, 16+ files, an unreadable register, a failing check) - the reason is printed
and an existing --out file is never touched. Exit 2: bad usage.

Input JSON keys. build / fix: row, w_id, req, title, tier, files (list), items (list of strings), core, proof,
spec_basis, copy_from, attack (list of {text, test_file}), standing ({a, b, c, d}), threat_model, findings_checked
(list), expected ({minutes, tokens}), ci. verify-r2: row, w_id, req, title, tier, spec_basis, attack, round1_findings
(list), changed_files (list). Optional in every kind: search_terms (list of words searched in the reference study;
REQUIRED when the register has no open record for `req`, because the line then reads `Reference: none - searched ...`).
Derived, never typed: Size and Budget (files: <= 5 S 30/40, 6-15 M 60/80, more refused as L - split), the round-2
budget (15 min / 20 calls), the `Reference:` line (reference_register.py open records plus their screens; SPEC CHANGE
records are marked as waiting for the owner), the `Why Opus:` line (only when a file is in `SAFETY_SET` of
measure_process.py, imported here, never copied) and the constant Common brief / Tests / Report / checklist lines.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_brief  # noqa: E402
import measure_process  # noqa: E402

KINDS = ("build", "fix", "verify-r2")
TIERS = ("A", "B", "C")
BUILD_KEYS = ("row", "w_id", "req", "title", "tier", "files", "items", "core", "proof", "spec_basis", "copy_from",
              "attack", "standing", "threat_model", "findings_checked", "expected", "ci")
VERIFY_KEYS = ("row", "w_id", "req", "title", "tier", "spec_basis", "attack", "round1_findings", "changed_files")
OPTIONAL_KEYS = ("search_terms",)
STANDING_KEYS = ("a", "b", "c", "d")
BANDS = ((check_brief.MAX_S_FILES, "S", 30, 40), (15, "M", 60, 80))  # (max files, size, minutes, calls); more = L
ROUND2_BUDGET = (15, 20)  # ADR-178 (1)
HARD_STOP = 0.8  # builder-brief.md: at 80% of the calls start nothing new
COMMON = "Common brief: docs/process/builder-brief.md"
TESTS_LINE = ("Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py "
              "tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests")
CHECKLIST_TAIL = ("no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted "
                  "tests only; no regenerated files in the PR.")
MUTATION = ("Run `python scripts/orchestrator/mutation_gate.py` on every guard you add or move before reporting; "
            "write the results to a file in your scratch folder and quote it.")
BARE_NA_RE = re.compile(r"^\s*n/?a\s*\.?\s*$", re.I)
SAFETY_SOURCE = "SAFETY_SET in scripts/orchestrator/measure_process.py"
TAIL_LINES = 6


class Refused(Exception):
    """The input cannot become a brief (fail closed: exit 1)."""


def _reg():
    path = HERE / "reference_register.py"
    spec = importlib.util.spec_from_file_location("reference_register", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _keys(kind: str) -> tuple[str, ...]:
    return VERIFY_KEYS if kind == "verify-r2" else BUILD_KEYS


def validate_input(data: object, kind: str) -> dict:
    """Refuse a non-object, an unknown key, or a missing/empty required key, naming the key."""
    if not isinstance(data, dict):
        raise Refused("the measure JSON must be an object")
    allowed = set(_keys(kind)) | set(OPTIONAL_KEYS)
    for key in data:
        if key not in allowed:
            raise Refused(f"unknown key `{key}` for kind {kind}")
    for key in _keys(kind):
        if key not in data:
            raise Refused(f"missing required key `{key}`")
        if data[key] in (None, "", [], {}):
            raise Refused(f"required key `{key}` is empty")
    if data["tier"] not in TIERS:
        raise Refused(f"`tier` must be one of {', '.join(TIERS)}, got {data['tier']!r}")
    return data


def _strings(data: dict, key: str) -> list[str]:
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise Refused(f"`{key}` must be a list of non-empty strings")
    return value


def size_and_budget(files: list[str]) -> tuple[str, int, int]:
    for limit, size, minutes, calls in BANDS:
        if len(files) <= limit:
            return size, minutes, calls
    raise Refused(f"{len(files)} files is size L (more than {BANDS[-1][0]}): split the item into briefs of "
                  f"at most {BANDS[-1][0]} files")


def _safety_file(files: list[str]) -> str | None:
    return next((f for f in files if measure_process.names_safety_file(f)), None)


def _why_opus(files: list[str]) -> list[str]:
    hit = _safety_file(files)
    return [f"Why Opus: `{hit}` is in the safety set ({SAFETY_SOURCE})"] if hit else []


def _record_text(rid: str, rec: dict) -> str:
    screens = ", ".join(rec.get("reference_screens") or []) or "no screen"
    waiting = "; SPEC CHANGE, waiting for the owner" if rec.get("spec_change") is True else ""
    return f"{rid} ({screens}{waiting})"


def reference_line(root: Path, req: str, terms: list[str]) -> str:
    """`Reference:` from the register's open records; fail closed on an unreadable or invalid register."""
    reg = _reg()
    try:
        errors = reg.validate(root)
        if errors:
            raise Refused("the reference register is invalid: " + "; ".join(errors[:3]))
        ids = reg.open_records(root, [req])
        recs = reg.load_records(root)
    except reg.RegisterError as exc:
        raise Refused(f"the reference register is unreadable ({exc})") from exc
    screens = sorted({s for i in ids for s in recs[i].get("reference_screens") or []})
    listed = ", ".join(_record_text(i, recs[i]) for i in ids)
    if screens:
        return (f"Reference: screens {', '.join(screens)} - copy only what each open record says; open {listed}")
    if len(terms) < check_brief.MIN_SEARCH_TERMS:
        raise Refused(f"no screen for {req}: `search_terms` needs at least {check_brief.MIN_SEARCH_TERMS} words "
                      "(`Reference: none - searched ...`)")
    return f"Reference: none - searched {', '.join(terms)}" + (f"; open {listed}" if ids else "")


def _standing(data: dict) -> str:
    std = data["standing"]
    if not isinstance(std, dict) or set(std) != set(STANDING_KEYS):
        raise Refused("`standing` must have exactly the keys a, b, c, d")
    for key in STANDING_KEYS:
        if not isinstance(std[key], str) or not std[key].strip() or BARE_NA_RE.match(std[key]):
            raise Refused(f"standing item ({key}) is empty or a bare n/a: apply it or say `n/a: <reason>`")
    return "Standing items: " + " ".join(f"({k}) {std[k].strip()}" for k in STANDING_KEYS)


def _attack(data: dict) -> list[str]:
    items = data["attack"]
    if not isinstance(items, list) or not all(isinstance(a, dict) and set(a) == {"text", "test_file"} for a in items):
        raise Refused("`attack` must be a list of {text, test_file}")
    return [f"{n}. {a['text']} (`{a['test_file']}`)" for n, a in enumerate(items, 1)]


def _expected(data: dict) -> str:
    exp = data["expected"]
    ok = isinstance(exp, dict) and set(exp) == {"minutes", "tokens"} and all(
        isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in exp.values())
    if not ok:
        raise Refused("`expected` must be {minutes: int, tokens: int}")
    return f"Expected (orchestrator, before dispatch): {exp['minutes']} min / ~{exp['tokens'] // 1000}k."


def _head(data: dict, kind: str) -> list[str]:
    label = {"build": "Builder brief", "fix": "Fix round", "verify-r2": "Verifier brief, round 2"}[kind]
    who = f"row {data['row']} ({data['req']} / {data['w_id']})"
    return [f"# {label}: {who} - {data['title']} (Tier {data['tier']})", ""]


def _reference_block(data: dict, root: Path, terms: list[str], files: list[str]) -> list[str]:
    return [reference_line(root, data["req"], terms), *_why_opus(files)]


def render_build(data: dict, kind: str, root: Path) -> str:
    files = _strings(data, "files")
    items = _strings(data, "items")
    size, minutes, calls = size_and_budget(files)
    terms = _strings(data, "search_terms") if "search_terms" in data else []
    findings = _strings(data, "findings_checked")
    out = _head(data, kind)
    out += [f"{COMMON} (Budget hard stop: at {int(calls * HARD_STOP)} calls start nothing new, commit, report). "
            f"{MUTATION}",
            f"Size: {size}, {len(files)} files, {len(items)} items", f"CI: {data['ci']}", _expected(data), "",
            f"Core: {data['core']}", f"Proof: {data['proof']}", "",
            f"Spec basis: {data['spec_basis']}", f"Copy from: {data['copy_from']}",
            *_reference_block(data, root, terms, files), "", "## What to do"]
    out += [f"{n}. {text}" for n, text in enumerate(items, 1)]
    out += ["", "Attack list: (each names its test file)", *_attack(data), "", _standing(data),
            f"Threat model: {data['threat_model']}", f"Findings checked: {', '.join(findings)}",
            f"Reviewer checklist: the Proof test first, every attack item tested, gate results quoted; "
            f"{CHECKLIST_TAIL}", "", TESTS_LINE,
            f"Budget: {minutes} min wall-clock, {calls} tool calls", "Report: evidence-table", ""]
    return "\n".join(out)


def render_verify_r2(data: dict, root: Path) -> str:
    changed = _strings(data, "changed_files")
    findings = _strings(data, "round1_findings")
    terms = _strings(data, "search_terms") if "search_terms" in data else []
    minutes, calls = ROUND2_BUDGET
    out = _head(data, "verify-r2")
    out += [f"{COMMON}; findings-only round 2 (ADR-178 (1)).", "",
            f"Spec basis: {data['spec_basis']}", *_reference_block(data, root, terms, changed), "",
            "Round 2 findings:", *[f"{n}. {f}" for n, f in enumerate(findings, 1)], "",
            "Changed files:", *[f"- {f}" for f in changed], "", "Attack list: (the items these findings touch)",
            *_attack(data), "", TESTS_LINE, f"Budget: {minutes} min wall-clock, {calls} tool calls",
            "Report: evidence-table", ""]
    return "\n".join(out)


def render(data: object, kind: str, root: Path) -> str:
    checked = validate_input(data, kind)
    return render_verify_r2(checked, root) if kind == "verify-r2" else render_build(checked, kind, root)


def _run(args: list[str]) -> tuple[int, list[str]]:
    proc = subprocess.run([sys.executable, *args], capture_output=True, text=True, check=False,  # noqa: S603
                          encoding="utf-8", errors="replace")
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    return proc.returncode, lines[-TAIL_LINES:]


def run_checks(text: str, root: Path) -> list[str]:
    """Write `text` to a scratch file, run check_brief and copy_from_check on it; return failure lines (empty = ok)."""
    fd, name = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        failures: list[str] = []
        for label, cmd in (("check_brief", [str(HERE / "check_brief.py"), name, "--root", str(root)]),
                           ("copy_from_check", [str(HERE / "copy_from_check.py"), str(root), name])):
            code, tail = _run(cmd)
            if code != 0:
                failures += [f"{label} exit {code}:", *tail]
        return failures
    finally:
        os.unlink(name)


def _write(text: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("row")
    ap.add_argument("measure")
    ap.add_argument("--out", default=None)
    ap.add_argument("--kind", choices=KINDS, default="build")
    ap.add_argument("--root", default=str(HERE.parents[1]))
    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        data = json.loads(Path(args.measure).read_text(encoding="utf-8"))
        if isinstance(data, dict) and str(data.get("row")) != args.row:
            raise Refused(f"row {args.row} on the command line, row {data.get('row')} in the JSON")
        text = render(data, args.kind, root)
    except (Refused, OSError, ValueError) as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        return 1
    failures = run_checks(text, root)
    if failures:
        sys.stderr.write("REFUSED: the rendered brief fails its checks (nothing written)\n")
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    if args.out:
        try:
            _write(text, Path(args.out))
        except OSError as exc:
            sys.stderr.write(f"REFUSED: cannot write --out {args.out}: {exc}\n")
            return 1
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
