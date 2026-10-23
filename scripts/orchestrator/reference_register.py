"""The reference-product difference register (ADR-176): one JSON record per difference, checked, gated and rendered.

Records live in `spec/reference-diffs/RD-NNN.json` (one file each). Every check is an allow-list: an unknown field,
kind, status or field shape, or an unreadable file, fails closed.

Usage: python scripts/orchestrator/reference_register.py [--root <repo>] (--check | --render | --open REQ-### ... |
       --close-check REQ-### ...)
  --check        validate every record and that docs/process/reference-differences.md is current. Exit 0 / 1.
  --render       write docs/process/reference-differences.md (deterministic: sorted, no clock). Exit 0 / 1.
  --open         print the ids of every blocking record of the named requirements, one per line. Exit 0.
  --close-check  exit 1 naming each blocking record of the named requirements, else exit 0.
Blocking = kind COPY or `spec_change` true, and status not verified / decided / deferred-with-an-issue.
Exit 2: bad usage, or the register cannot be read (a gate never passes on an unreadable register).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

REGISTER_DIR = Path("spec") / "reference-diffs"
PAGE = Path("docs") / "process" / "reference-differences.md"
SEQUENCE = Path("docs") / "process" / "builder-sequence-2026-10-22.md"

KINDS = ("COPY", "DIFFERENT-BY-DECISION", "NO-SCREEN", "MATCH")
STATUSES = ("open", "built", "verified", "deferred", "decided")
CLEARED = ("verified", "deferred", "decided")  # deferred clears only with an issue (see is_blocking)
REQUIRED = ("id", "kind", "title", "reference_behaviour", "reference_screens", "ours", "req", "row", "status",
            "spec_change", "bug", "recorded")
OPTIONAL = ("reference_label", "ac", "adr", "issue")
MAX_LEN = {"title": 120, "reference_behaviour": 400, "reference_label": 40, "ours": 400}
MAX_SCREENS = 20
EXIT_UNREADABLE = 2  # bad usage, or a register the gates cannot trust
INT_FIELDS = (("row", "a builder row number"), ("issue", "an issue number"))
# ADR-176 (4): the reference product's name never enters public text. Compared as a hash of whole lower-cased words.
BANNED_WORD_SHA256 = "51eb0a649e8ea998a8e8527a47858a91d20b263772281af86fffa67f898ca33a"

ID_RE = re.compile(r"^RD-\d{3}$")
FILE_RE = re.compile(r"^RD-\d{3}\.json$")
REQ_RE = re.compile(r"^REQ-\d{3}$")
ADR_RE = re.compile(r"^ADR-\d{3}$")
AC_RE = re.compile(r"^AC-\d+$")
SCREEN_RE = re.compile(r"^(screen|catalogue) \d{3}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WORD_RE = re.compile(r"[a-z0-9]+")
REQ_IN_CELL_RE = re.compile(r"\bREQ-\d{3}\b")
ROW_LINE_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|([^|]*)\|")


class RegisterError(Exception):
    """The register cannot be read (fail closed: exit 2)."""


def has_banned_word(text: str) -> bool:
    """True when any whole lower-cased word of `text` hashes to the banned name."""
    return any(hashlib.sha256(w.encode("utf-8")).hexdigest() == BANNED_WORD_SHA256
               for w in WORD_RE.findall(text.lower()))


def load_records(root: Path) -> dict[str, dict]:
    """Every record file, by file stem. A file that is not `RD-NNN.json`, not UTF-8 JSON or not an object raises."""
    folder = root / REGISTER_DIR
    if not folder.exists():
        return {}
    if not folder.is_dir():
        raise RegisterError(f"{REGISTER_DIR.as_posix()} is not a folder")
    records: dict[str, dict] = {}
    for path in sorted(folder.iterdir()):
        rel = (REGISTER_DIR / path.name).as_posix()
        if not FILE_RE.match(path.name) or not path.is_file():
            raise RegisterError(f"{rel}: only RD-NNN.json record files belong in the register")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise RegisterError(f"{rel}: unreadable ({exc.__class__.__name__})") from exc
        if not isinstance(data, dict):
            raise RegisterError(f"{rel}: a record is a JSON object")
        records[path.stem] = data
    return records


def sequence_rows(root: Path) -> dict[int, set[str]]:
    """Builder row number -> the REQ ids its REQ cell names (`REQ-006 + REQ-007` gives both)."""
    path = root / SEQUENCE
    if not path.is_file():
        raise RegisterError(f"{SEQUENCE.as_posix()} not found: rows cannot be checked")
    rows: dict[int, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW_LINE_RE.match(line)
        if m:
            rows[int(m.group(1))] = set(REQ_IN_CELL_RE.findall(m.group(2)))
    return rows


def _is_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _field_errors(rec: dict) -> list[str]:
    """Shape of every field (allow-list): unknown keys, missing keys, types, enums, lengths."""
    errs = [f"unknown field `{k}`" for k in sorted(set(rec) - set(REQUIRED) - set(OPTIONAL))]
    errs += [f"missing field `{k}`" for k in REQUIRED if k not in rec]
    return errs + _text_errors(rec) + _value_errors(rec) + _screen_errors(rec)


def _text_errors(rec: dict) -> list[str]:
    errs: list[str] = []
    for key in ("title", "reference_behaviour", "ours", "reference_label"):
        if key in rec and not _is_str(rec[key]):
            errs.append(f"`{key}` must be non-empty text")
        elif key in rec and len(rec[key]) > MAX_LEN[key]:
            errs.append(f"`{key}` is {len(rec[key])} characters, at most {MAX_LEN[key]}")
    return errs


def _value_errors(rec: dict) -> list[str]:
    checks = (("id", ID_RE), ("req", REQ_RE), ("ac", AC_RE), ("adr", ADR_RE), ("recorded", DATE_RE))
    errs = [f"`{key}` has the wrong shape" for key, pattern in checks
            if key in rec and not (isinstance(rec[key], str) and pattern.match(rec[key]))]
    if "kind" in rec and rec["kind"] not in KINDS:
        errs.append(f"`kind` must be one of {', '.join(KINDS)}")
    if "status" in rec and rec["status"] not in STATUSES:
        errs.append(f"`status` must be one of {', '.join(STATUSES)}")
    errs += [f"`{key}` must be true or false" for key in ("spec_change", "bug")
             if key in rec and not isinstance(rec[key], bool)]
    errs += [f"`{key}` must be a positive whole number ({what})" for key, what in INT_FIELDS
             if key in rec and not (_is_int(rec[key]) and rec[key] >= 1)]
    if "recorded" in rec and isinstance(rec["recorded"], str) and DATE_RE.match(rec["recorded"]):
        try:
            dt.date.fromisoformat(rec["recorded"])
        except ValueError:
            errs.append("`recorded` is not a real date")
    return errs


def _screen_errors(rec: dict) -> list[str]:
    if "reference_screens" not in rec:
        return []
    screens = rec["reference_screens"]
    if not isinstance(screens, list) or len(screens) > MAX_SCREENS or \
            not all(isinstance(s, str) and SCREEN_RE.match(s) for s in screens):
        return [f"`reference_screens` must be a list of at most {MAX_SCREENS} `screen NNN` / `catalogue NNN`"]
    if len(set(screens)) != len(screens):
        return ["`reference_screens` lists a screen twice"]
    if not screens and rec.get("kind") != "NO-SCREEN":
        return ["`reference_screens` is empty: only a NO-SCREEN record has no screen"]
    return []


def _link_errors(rec: dict, root: Path, rows: dict[int, set[str]]) -> list[str]:
    """Cross-references: REQ, AC, ADR and builder row exist; the rule fields each kind/status needs are present."""
    errs: list[str] = []
    req = rec.get("req")
    req_path = root / "spec" / "requirements" / f"{req}.md"
    if isinstance(req, str) and REQ_RE.match(req):
        if not req_path.is_file():
            errs.append(f"`req` {req} is not in spec/requirements")
        elif isinstance(rec.get("ac"), str) and AC_RE.match(rec["ac"]) and not re.search(
                rf"^- id: {re.escape(rec['ac'])}\s*$", req_path.read_text(encoding="utf-8"), re.M):
            errs.append(f"`ac` {rec['ac']} is not an acceptance criterion of {req}")
    adr = rec.get("adr")
    if rec.get("kind") == "DIFFERENT-BY-DECISION" and "adr" not in rec:
        errs.append("a DIFFERENT-BY-DECISION record names its `adr` (ADR-176 (2))")
    if isinstance(adr, str) and ADR_RE.match(adr) and not (root / "spec" / "decisions" / f"{adr}.md").is_file():
        errs.append(f"`adr` {adr} is not in spec/decisions")
    if rec.get("status") == "deferred" and "issue" not in rec:
        errs.append("a deferred record names its `issue` (ADR-176 (1))")
    row = rec.get("row")
    if _is_int(row) and row >= 1:
        if row not in rows:
            errs.append(f"`row` {row} is not in {SEQUENCE.as_posix()}")
        elif isinstance(req, str) and req not in rows[row]:
            names = ", ".join(sorted(rows[row])) or "no requirement"
            errs.append(f"`row` {row} belongs to {names}, not {req}")
    return errs


def validate(root: Path) -> list[str]:
    """Every error of every record (file-prefixed); raises RegisterError when the register cannot be read."""
    records = load_records(root)
    rows = sequence_rows(root) if records else {}
    errors: list[str] = []
    for stem, rec in records.items():
        rel = (REGISTER_DIR / f"{stem}.json").as_posix()
        errs = _field_errors(rec) + _link_errors(rec, root, rows)
        if rec.get("id") != stem:
            errs.append(f"`id` must equal the file name ({stem})")
        raw = (root / REGISTER_DIR / f"{stem}.json").read_text(encoding="utf-8")
        if has_banned_word(raw):
            errs.append("names the reference product: records say \"reference product\" (ADR-176 (4))")
        errors.extend(f"{rel}: {e}" for e in errs)
    return errors


def is_blocking(rec: dict) -> bool:
    """ADR-176 (2): COPY or spec_change records block a close until verified, decided, or deferred with an issue."""
    if not (rec.get("kind") == "COPY" or rec.get("spec_change") is True):
        return False
    status = rec.get("status")
    if status == "deferred":
        return not (_is_int(rec.get("issue")) and rec["issue"] >= 1)
    return status not in CLEARED


def open_records(root: Path, reqs: list[str]) -> list[str]:
    """Sorted ids of the blocking records whose `req` is one of `reqs`."""
    wanted = set(reqs)
    return sorted(stem for stem, rec in load_records(root).items() if rec.get("req") in wanted and is_blocking(rec))


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(root: Path) -> str:
    """The owner's page: SPEC CHANGE batch, NO-SCREEN capture list, COPY by row, DIFFERENT-BY-DECISION, MATCH count."""
    recs = [rec for _, rec in sorted(load_records(root).items())]
    by_kind = {k: [r for r in recs if r.get("kind") == k] for k in KINDS}
    counts = ", ".join(f"{k} {len(by_kind[k])}" for k in KINDS)
    out = ["# Reference-product differences (ADR-176)", "",
           "Generated by `python scripts/orchestrator/reference_register.py --render` from the records in "
           f"`{REGISTER_DIR.as_posix()}/`. Do not edit by hand; CI fails a stale page.", "",
           f"Records: {len(recs)} ({counts})", "",
           "## SPEC CHANGE batch for the owner", ""]
    batch = [r for r in recs if r.get("spec_change") is True and is_blocking(r)]
    out += ["| Id | Requirement | Difference | Ours | Reference product |", "|---|---|---|---|---|"] + [
        f"| {r['id']} | {r['req']} {r.get('ac', '')} | {_cell(r['title'])} | {_cell(r['ours'])} | "
        f"{_cell(r['reference_behaviour'])} |" for r in batch] if batch else ["None open."]
    out += ["", "## NO-SCREEN capture list", ""]
    ns = by_kind["NO-SCREEN"]
    out += ["| Id | Requirement | Row | What to capture | Status |", "|---|---|---|---|---|"] + [
        f"| {r['id']} | {r['req']} | {r['row']} | {_cell(r['title'])} | {r['status']} |" for r in ns] if ns else \
        ["None."]
    out += ["", "## COPY by builder row", ""]
    copies = sorted(by_kind["COPY"], key=lambda r: (r["row"], r["id"]))
    out += ["| Row | Id | Requirement | Difference | Screens | Status |", "|---|---|---|---|---|---|"] + [
        f"| {r['row']} | {r['id']} | {r['req']} {r.get('ac', '')} | {_cell(r['title'])} | "
        f"{', '.join(r['reference_screens'])} | {r['status']}{' (#' + str(r['issue']) + ')' if 'issue' in r else ''} |"
        for r in copies] if copies else ["None."]
    out += ["", "## DIFFERENT-BY-DECISION", ""]
    dbd = by_kind["DIFFERENT-BY-DECISION"]
    out += ["| Id | Requirement | Decision | Difference | Status |", "|---|---|---|---|---|"] + [
        f"| {r['id']} | {r['req']} | {r['adr']} | {_cell(r['title'])} | {r['status']} |" for r in dbd] if dbd else \
        ["None."]
    out += ["", "## MATCH", "", f"{len(by_kind['MATCH'])} record(s) match the reference product.", ""]
    return "\n".join(out)


def _bad_reqs(reqs: list[str]) -> list[str]:
    return [r for r in reqs if not REQ_RE.match(r)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--open", nargs="+", metavar="REQ")
    mode.add_argument("--close-check", nargs="+", metavar="REQ")
    args = ap.parse_args(argv)
    reqs = args.open or args.close_check or []
    if _bad_reqs(reqs):
        sys.stderr.write(f"not a requirement id: {', '.join(_bad_reqs(reqs))}\n")
        return EXIT_UNREADABLE
    try:
        return _run(args, Path(args.root), reqs)
    except RegisterError as exc:
        sys.stderr.write(f"register unreadable: {exc}\n")
        return EXIT_UNREADABLE


def _run(args: argparse.Namespace, root: Path, reqs: list[str]) -> int:
    errors = validate(root)
    if reqs and errors:  # a gate never reads an invalid register (fail closed)
        sys.stderr.write("register invalid:\n" + "".join(f"{e}\n" for e in errors))
        return EXIT_UNREADABLE
    if reqs:
        ids = open_records(root, reqs)
        if args.open:
            sys.stdout.write("".join(f"{i}\n" for i in ids))
            return 0
        for i in ids:
            sys.stdout.write(f"BLOCKED: {i} is open for {', '.join(reqs)} (ADR-176 (2)): verify, decide or "
                             "defer it with an issue before the row closes\n")
        return 1 if ids else 0
    page = root / PAGE
    if args.render and not errors:
        page.write_text(render(root), encoding="utf-8", newline="\n")
        sys.stdout.write(f"wrote {PAGE.as_posix()}\n")
        return 0
    if not errors and (not page.is_file() or page.read_text(encoding="utf-8") != render(root)):
        errors.append(f"{PAGE.as_posix()} is stale: run reference_register.py --render")
    sys.stdout.write("".join(f"{e}\n" for e in errors) or f"{len(load_records(root))} record(s) ok, page current\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
