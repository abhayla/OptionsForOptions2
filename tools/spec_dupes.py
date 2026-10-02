#!/usr/bin/env python3
"""spec_dupes.py — block a spec item that restates an existing item of the same kind, and a requirement whose pin
of a decision it cites is missing or stale (REQ-009 AC-3, AC-5; OD-30, OD-32, OD-38, OD-39).

Usage:
    python tools/spec_dupes.py [ROOT] [--suggest]

Every run is a FULL scan (every PR and push); there is no base ref.

Duplicates. Items of the SAME kind only (OD-32): requirement items (each statement and criterion) of different
requirements; decision items (sentences of spec/decisions/*.md bodies with heading LINES removed, and for the Factory
the sentences of each docs/spec/decisions.md OD row with its notes removed) of different decisions. Items under 4
content words are skipped. A pair at >= 0.40 word overlap (OD-38) blocks unless an EXEMPTION on the NEWER record (the
higher id number) names the other record, carries the pair's CURRENT fingerprint and states a difference of at least
3 content words:
    distinct_from: ["REQ-001 AC-1 #<fp> — <the actual difference>"]      (requirements; ADR frontmatter the same)
    (distinct from OD-12 #<fp>: <the actual difference>)                 (inside a Factory OD row)
The fingerprint (spec_text.fingerprint) is sha256 over the two items' canonical texts, so an exemption is bound to
the exact pair of texts it was granted for: an edit to either text, or an extra copied item, is a different pair
and blocks again. It is bound to content, not position: renumbering criteria with their texts unchanged keeps it
valid, but its item label must still name the older item (a label naming another item is rejected). Two items whose canonical texts are identical can never be exempted. An
exemption whose fingerprint no longer matches, that settles no currently flagged pair, that names an unknown record,
or that lacks a fingerprint blocks as stale/unused.

Pins (OD-39). A requirement whose source, spec_refs, statement or criteria cite a decision (its id, any case, or the
decision file path) must carry confirmed_against: ["<decision id> #<fp>"], fp = fingerprint of that decision's
current text with its exemption notes removed. A missing or stale pin, or a pin naming a decision that does not
exist (removed), blocks. Editing the requirement never replaces re-pinning; a note-only change to a decision leaves
pins valid; a reverted decision matches its old pin.

--suggest: also print paste-ready exemption entries (with a placeholder difference that fails the 3-word rule, so it
cannot be pasted unchanged) and pins. Never writes a file.

Records. Every id is unique per kind: two OD rows, requirement files or decision files declaring one id block
(DUPLICATE-ID, naming every file/row), and a requirement or decision file that cannot be parsed blocks (UNREADABLE,
naming the file and the error); nothing is skipped silently.

Exit codes: 0 clean; 1 any blocking record, pair, exemption or pin (each line names the ids); 2 usage error.
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_text as st  # noqa: E402  (the one shared tokenizer, REQ-009 AC-2)

# "<record id>[ <item label>] #<fp> — <difference>" (separator: em/en dash, "--" or ":"); the fp is optional here
# so that an entry without one can be reported as lacking it
ENTRY_RE = re.compile(r"^\s*([A-Za-z]+-\d+)(?:\s+(?!#)(\S+))?(?:\s+#([0-9a-f]{12}))?\s*(?:—|–|--|:)\s*(.*)$", re.S)
PIN_RE = re.compile(r"^\s*([A-Za-z]+-\d+)\s+#([0-9a-f]{12})\s*$")
MIN_DIFF_WORDS = 3
PLACEHOLDER = "<difference>"


@dataclass(frozen=True)
class Exemption:
    record: str        # the record carrying it
    target: str        # the record id it names
    fp: str            # "" when missing
    difference: str
    raw: str
    label: str = ""    # optional item label after the record id ("AC-1", "statement", "s4")


def id_number(rid: str) -> int:
    m = re.search(r"(\d+)$", rid)
    return int(m.group(1)) if m else -1


def has_difference(text: str) -> bool:
    """A difference is real text: at least MIN_DIFF_WORDS words the tokenizer keeps ("different" is not one)."""
    return len(st.words(text)) >= MIN_DIFF_WORDS


def _list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []


def exemptions(rec: st.Record) -> list[Exemption]:
    if rec.path == st.OD_LOG:
        return [Exemption(rec.id, m.group(1).upper(), m.group(2) or "", m.group(3).strip(), m.group(0))
                for m in st.OD_NOTE_RE.finditer(rec.data.get("decision", ""))]
    out = []
    for entry in _list(rec.data.get("distinct_from")):
        m = ENTRY_RE.match(entry)
        if m:
            out.append(Exemption(rec.id, m.group(1).upper(), m.group(3) or "", m.group(4).strip(), entry,
                                 m.group(2) or ""))
        else:
            out.append(Exemption(rec.id, "", "", "", entry))
    return out


def find_pairs(records: list[st.Record]) -> list[tuple[float, st.Item, st.Item]]:
    """Same-kind pairs across different records at >= THRESHOLD (a full scan)."""
    pairs = []
    items = [i for r in records for i in r.items if st.comparable(i)]
    for a, b in itertools.combinations(items, 2):
        if a.kind != b.kind:
            continue  # same kind only (OD-32): requirement-to-decision links are the pins' job
        if a.owner == b.owner:
            continue  # items of one record never block each other
        s = st.score(a.words, b.words)
        if s >= st.THRESHOLD:
            pairs.append((s, a, b))
    pairs.sort(key=lambda p: (-p[0], p[1].label, p[2].label))
    return pairs


def newer_of(a: st.Item, b: st.Item) -> tuple[st.Item, st.Item]:
    return (a, b) if id_number(a.owner) > id_number(b.owner) else (b, a)


def entry_for(newer: st.Record, older: st.Item, fp: str, difference: str = PLACEHOLDER) -> str:
    if newer.path == st.OD_LOG:
        return f"({newer.id} decision text) (distinct from {older.owner} #{fp}: {difference})"
    return f'{newer.id}: distinct_from: ["{older.label} #{fp} — {difference}"]'


def check_pairs(records: list[st.Record]) -> tuple[list[str], list[str], list[str]]:
    by_id = {(r.kind, r.id): r for r in records}
    ids = {r.id.upper() for r in records}
    used: set = set()
    failures, accepted, suggestions = [], [], []
    for s, a, b in find_pairs(records):
        new, old = newer_of(a, b)
        rec = by_id[(new.kind, new.owner)]
        fp = st.fingerprint(old.text, new.text)
        line = f'{s:.2f} {a.kind}: {old.label} "{old.text}" <-> {new.label} "{new.text}"'
        match = [e for e in exemptions(rec) if e.target == old.owner.upper() and e.fp == fp]
        older_item = old.label.split(" ", 1)[1] if " " in old.label else ""
        mislabeled = [e for e in match if e.label and e.label.casefold() != older_item.casefold()]
        if mislabeled:
            used.update(match)
            failures.append(f"DUPLICATE {line} — exemption label {mislabeled[0].label} does not match the pair's older "
                            f"item {old.label}: {mislabeled[0].raw}")
            continue
        if st.canon(old.text) == st.canon(new.text):
            used.update(match)  # reported here, not again as unused
            failures.append(f"DUPLICATE {line} — identical text can never be exempted: merge into one item")
            continue
        good = [e for e in match if has_difference(e.difference)]
        if good:
            used.update(good)
            accepted.append(f"ACCEPTED {line} ({new.owner} #{fp})")
            continue
        used.update(match)
        why = ("the exemption's difference has fewer than 3 content words" if match
               else f"merge into one item, or add {entry_for(rec, old, fp)}")
        failures.append(f"DUPLICATE {line} — {why}")
        suggestions.append(f"SUGGEST {entry_for(rec, old, fp)}")
    for rec in records:
        for e in exemptions(rec):
            if e in used:
                continue
            if not e.target:
                why = "not of the form '<id> [item] #<fp> — <difference>'"
            elif e.target not in ids:
                why = f"names unknown record {e.target}"
            elif not e.fp:
                why = "lacks a fingerprint (#<fp>)"
            else:
                why = "stale or unused: its fingerprint settles no currently flagged pair"
            failures.append(f"EXEMPTION {rec.id}: {why}: {e.raw}")
    return failures, accepted, suggestions


def check_records(records: list[st.Record], problems: list[tuple[str, str]]) -> list[str]:
    """Ids unique per kind; every record readable."""
    out = [f"UNREADABLE {path}: {why}" for path, why in problems]
    seen: dict[tuple[str, str], list[str]] = {}
    for r in records:
        if r.path == st.OD_LOG and r.data.get("cells") != st.OD_CELLS:
            out.append(f"RECORD malformed decision row {r.id}: {r.data.get('cells')} cells, expected {st.OD_CELLS} "
                       f"(a literal pipe inside a cell is written \\|) — {r.path} line {r.data['line']}")
        where = f"{r.path} line {r.data['line']}" if r.path == st.OD_LOG else r.path
        seen.setdefault((r.kind, r.id.upper()), []).append(where)
    for (kind, rid), places in sorted(seen.items()):
        if len(places) > 1:
            out.append(f"DUPLICATE-ID {kind} {rid} is declared {len(places)} times: {'; '.join(places)} — "
                       f"give each record its own id")
    return out


def _citing_text(req: st.Record) -> str:
    refs = req.data.get("spec_refs") or []
    parts = [str(req.data.get("source") or "")] + _list(refs) + [i.text for i in req.items]
    return "\n".join(parts)


def _names(text: str, decision: st.Record) -> bool:
    if re.search(r"(?<![A-Za-z0-9])" + re.escape(decision.id) + r"(?![0-9])", text, re.I):
        return True
    return decision.path != st.OD_LOG and decision.path.lower() in text.lower()


def cites(req: st.Record, decision: st.Record) -> bool:
    """Any MENTION (source, spec_refs, statement, criteria): what pins and the amends rule track."""
    return _names(_citing_text(req), decision)


def covers(req: st.Record, decision: st.Record) -> bool:
    """A DELIBERATE citation, in `source` or `spec_refs` only: what coverage counts (REQ-013 AC-3). A decision named
    as an example inside a criterion is pinned (cites) but not covered."""
    return _names("\n".join([str(req.data.get("source") or "")] + _list(req.data.get("spec_refs"))), decision)


def check_pins(records: list[st.Record]) -> tuple[list[str], list[str]]:
    decisions = {r.id.upper(): r for r in records if r.kind == "decision"}
    failures, suggestions = [], []
    for req in (r for r in records if r.kind == "requirement"):
        have: dict[str, str] = {}
        for v in _list(req.data.get("confirmed_against")):
            m = PIN_RE.match(v)
            if not m:
                failures.append(f'PIN {req.id}: confirmed_against entry "{v}" is not "<decision id> #<fp>"')
                continue
            did = m.group(1).upper()
            if did in have:
                failures.append(f"PIN {req.id}: duplicate pins for {m.group(1)} — keep exactly one, the current one")
            have[did] = m.group(2)
            if did not in decisions:
                failures.append(f"PIN {req.id}: pins {m.group(1)}, which does not exist (removed?) — "
                                f"re-read the requirement and drop or replace the pin")
            elif not cites(req, decisions[did]):
                failures.append(f"PIN {req.id}: orphan pin {m.group(1)} — {req.id} does not cite it; cite it or drop "
                                f"the pin")
        for did, d in sorted(decisions.items()):
            if not cites(req, d):
                continue
            want = st.fingerprint(d.pin_text)
            if have.get(did) == want:
                continue
            state = "stale (the decision changed since it was pinned)" if did in have else "missing"
            pin = f'"{d.id} #{want}"'
            failures.append(f"PIN {req.id} cites {d.id}: pin {state} — re-read {d.id}, then set "
                            f"confirmed_against: [{pin}]")
            suggestions.append(f"SUGGEST {req.id}: confirmed_against: [{pin}]")
    return failures, suggestions


# --- Relations, the amends rule, sources and coverage (REQ-013; OD-43, OD-44, OD-45) ----------------------------

VERBS = ("amends", "supersedes", "refines", "extends", "narrows", "approves", "starts", "closes", "applies", "none",
         "no-requirement")
AMENDING = frozenset({"amends", "supersedes", "refines", "narrows"})   # the amends rule (AC-2); not extends/applies
# AC-3: a verb never exempts by itself; only a pure approval or an explicit `no-requirement — <reason>` entry
NO_REQUIREMENT = "no-requirement"
TARGET_RE = re.compile(r"^(?:handoff §(?P<sec>\d+)|(?P<ms>M\d+(?:\.\d+)?)|(?P<id>[A-Z][A-Za-z]*-\d+))$")
REASON_RE = re.compile(r"^(?:none|no-requirement)\s*(?:—|–|--)\s*(?P<why>.*)$", re.S)
HANDOFF_REF_RE = re.compile(r"handoff\s*§\s*(\d+)(?!\d)", re.I)
PLAN_REF_RE = re.compile(r"docs/milestones/M\d+(?:\.\d+)?-plan\.md")
COVERAGE_MODE_FILE = "docs/spec/coverage-mode.txt"
HANDOFF_SORT = "docs/spec/handoff-sort.md"
QUESTION_ID_RE = re.compile(r"\bQ\d+\b")          # an owner-question id, as a whole token
QUESTION_REGISTER = "spec/traceability/question-register.md"   # a project's register of the owner's questions
MILESTONE_DIR = "docs/milestones"
LIVE_STATUSES = frozenset(s.casefold() for s in (             # statuses that cover (REQ-013 AC-3/AC-4, REQ-014)
    "Specified", "Approved", "Planned", "Implementing", "Implemented", "Testing", "Verified", "Reviewed",
    "Released", "Delivered-before-trace"))  # an ALLOW-list: Draft, Superseded or an unknown status never covers
SORT_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*([A-Za-z0-9-]+)\s*\|")


@dataclass(frozen=True)
class Relation:
    verb: str
    targets: tuple[str, ...]
    reason: str = ""   # `none — <reason>` only


def relations_text(rec: st.Record) -> str | None:
    """The record's relations: the OD row's last cell, or a decision file's `changes` field (a string, or a list
    of entries joined with ';'). None = the file has no `changes` field."""
    if rec.path == st.OD_LOG:
        return str(rec.data.get("changes") or "")
    value = rec.data.get("changes")
    if value is None:
        return None
    return "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)


def parse_relations(text: str, known: set[str], self_id: str = "", *, milestones: set[str] | None = None,
                    sections: set[int] | None = None, decision_text: str = "") -> tuple[list[Relation], list[str]]:
    """(relations, problems). Grammar (AC-1): `;`-separated entries `<verb> <target>[, <target>...]`, verb in
    VERBS, target = a known decision or requirement id, a milestone `M4` / `M4.1` (with a plan file when
    `milestones` is given, or named in the decision's own text: a planned milestone), or `handoff §N` (a row of the sort, when `sections` is given); `none — <reason>` alone;
    `no-requirement — <reason>` never with an amending verb. Every problem is a sentence naming what is wrong."""
    rels, problems = [], []
    entries = [e.strip() for e in text.split(";")]
    if not any(entries):
        return [], ["relations are empty (write `none — <reason>` when nothing is related)"]
    for entry in entries:
        if not entry:
            problems.append("an empty entry between ';' separators")
            continue
        head, _, rest = entry.partition(" ")
        verb = head.lower()
        if verb not in VERBS:
            problems.append(f'unknown verb "{head}" in "{entry}" (verbs: {", ".join(VERBS)})')
            continue
        if verb in ("none", NO_REQUIREMENT):
            m = REASON_RE.match(entry)
            if not m or not has_difference(m.group("why")):
                problems.append(f'"{entry}": `{verb}` must say why in the same cell: `{verb} — <reason of 3+ words>`')
            elif verb == "none" and len(entries) > 1:
                problems.append(f'"{entry}": `none` cannot be combined with other relations')
            else:
                rels.append(Relation(verb, (), m.group("why").strip()))
            continue
        if not rest.strip():
            problems.append(f'"{entry}": `{verb}` names no target')
            continue
        targets, ok = [], True
        for t in (x.strip() for x in rest.split(",")):
            m = TARGET_RE.match(t)
            if not m:
                problems.append(f'unparseable target "{t}" in "{entry}" (targets are decision or requirement ids, '
                                f'milestones like M4 or M4.1, or `handoff §N`)')
                ok = False
            elif m.group("id") and t.upper() not in known:
                problems.append(f'target "{t}" in "{entry}" is not a known decision or requirement id')
                ok = False
            elif m.group("id") and t.upper() == self_id.upper():
                problems.append(f'"{entry}" names the decision itself')
                ok = False
            elif m.group("ms") and milestones is not None and t not in milestones and (
                    verb == "approves" or not re.search(
                        r"(?<![A-Za-z0-9.])" + re.escape(t) + r"(?![A-Za-z0-9]|\.[0-9])", decision_text)):
                why = ("an approval needs the plan file" if verb == "approves"
                       else "and is not named in the decision")
                problems.append(f'milestone "{t}" has no {MILESTONE_DIR}/{t}-plan.md ({why})')
                ok = False
            elif m.group("sec") and sections is not None and int(m.group("sec")) not in sections:
                problems.append(f'"{t}" is not a section of {HANDOFF_SORT}')
                ok = False
            else:
                targets.append(t.upper() if m.group("id") else t)
        if ok:
            rels.append(Relation(verb, tuple(targets)))
    amending = sorted({r.verb for r in rels if r.verb in AMENDING})
    if amending and any(r.verb == NO_REQUIREMENT for r in rels):
        problems.append(f"`no-requirement` cannot be combined with {', '.join(amending)}: a decision that changes "
                        f"another states a requirement")
    return rels, problems


def milestone_names(src: st.Source) -> set[str]:
    """Milestones that have a plan file (docs/milestones/<name>-plan.md)."""
    return {Path(p).name[: -len("-plan.md")] for p in src.list(MILESTONE_DIR, "M*-plan.md")}


def sort_sections(src: st.Source) -> set[int] | None:
    """Every section number of the master-spec sort; None when the repo has no sort (a project)."""
    text = src.read(HANDOFF_SORT)
    if text is None:
        return None
    return {int(m.group(1)) for m in map(SORT_ROW_RE.match, text.splitlines()) if m}


def read_mode(src: st.Source) -> tuple[str, list[str], list[str]]:
    """(mode, warnings, failures) from docs/spec/coverage-mode.txt. Missing file = `report` with a warning
    (fail-safe for adoption: a project upgrading the kit is not blocked by a file it has not written yet); a value
    other than report / block is a RECORD failure (a typo must not silently switch blocking off)."""
    raw = src.read(COVERAGE_MODE_FILE)
    if raw is None:
        return "report", [f"WARNING {COVERAGE_MODE_FILE} is missing: coverage runs in report mode "
                          f"(create it reading `report` or `block`)"], []
    value = raw.strip().lower()
    if value in ("report", "block"):
        return value, [], []
    return "report", [], [f'RECORD {COVERAGE_MODE_FILE} reads "{raw.strip()}": expected `report` or `block`']


def check_relations(records: list[st.Record], mode: str,
                    src: st.Source | None = None) -> tuple[list[str], list[str], dict[str, list[Relation]]]:
    """(record failures, report lines, relations by decision id). AC-1: every OD row's relations cell, and every
    decision file's `changes` field, parses in the vocabulary. A decision FILE without `changes` (records written
    before kit 1.4.0) is a RECORD failure in block mode and a REPORT line in report mode."""
    known = {r.id.upper() for r in records}
    ms = milestone_names(src) if src is not None else None
    secs = sort_sections(src) if src is not None else None
    failures, reports, by_id = [], [], {}
    for rec in (r for r in records if r.kind == "decision"):
        where = f"{rec.path} line {rec.data['line']}" if rec.path == st.OD_LOG else rec.path
        if rec.path == st.OD_LOG and rec.data.get("cells") != st.OD_CELLS:
            continue  # a malformed row is already a RECORD failure (check_records); its last cell is shifted
        text = relations_text(rec)
        if text is None:
            what = (f"{rec.id}: decision record has no `changes` field (its relations, e.g. `amends ADR-003` or "
                    f"`none — <reason>`) — {where}")
            if mode == "block":
                failures.append("RECORD " + what)
            else:
                reports.append("REPORT " + what)
            continue
        dec_text = rec.data.get("decision", "") if rec.path == st.OD_LOG else rec.pin_text
        rels, problems = parse_relations(text, known, rec.id, milestones=ms, sections=secs, decision_text=dec_text)
        for why in problems:
            failures.append(f"RECORD {rec.id} relations: {why} — {where}")
        by_id[rec.id.upper()] = rels
    return failures, reports, by_id


def _superseded(req: st.Record) -> bool:
    return str(req.data.get("status") or "").strip().casefold() == "superseded"


def live(req: st.Record) -> bool:
    """A requirement that can cover a decision or a section: its status is on the LIVE_STATUSES allow-list (never
    Draft, Superseded, a misspelt or an unknown status)."""
    return str(req.data.get("status") or "").strip().casefold() in LIVE_STATUSES


def check_amends(records: list[st.Record], rels: dict[str, list[Relation]]) -> list[str]:
    """AC-2: a decision whose relations amend / supersede / refine / narrow decision X makes every requirement that
    cites X cite (and therefore pin, via check_pins) the amending decision too, unless the requirement is
    Superseded. extends / applies never trigger it."""
    decisions = {r.id.upper(): r for r in records if r.kind == "decision"}
    amended_by: dict[str, list[tuple[str, str]]] = {}
    for did, rs in rels.items():
        for rel in rs:
            if rel.verb in AMENDING:
                for t in rel.targets:
                    if t in decisions:
                        amended_by.setdefault(t, []).append((did, rel.verb))
    reqs = {r.id.upper(): r for r in records if r.kind == "requirement"}
    failures = []
    # a decision that amends / supersedes / refines / narrows REQ-n changes that requirement: REQ-n must cite and pin it
    for did, rs in sorted(rels.items(), key=lambda kv: id_number(kv[0])):
        for rel in rs:
            if rel.verb not in AMENDING:
                continue
            for t in rel.targets:
                q = reqs.get(t)
                if q is not None and not _superseded(q) and not cites(q, decisions[did]):
                    d = decisions[did]
                    failures.append(f"PIN {q.id}: {d.id} {rel.verb} {q.id} (amends rule): re-read {d.id}, then cite "
                                    f'it in {q.id} and pin it (confirmed_against: "{d.id} #{st.fingerprint(d.pin_text)}"'
                                    f"), or set {q.id} status: Superseded")
    for req in (r for r in records if r.kind == "requirement"):
        if _superseded(req):
            continue
        for x in sorted(amended_by, key=id_number):
            if not cites(req, decisions[x]):
                continue
            for did, verb in amended_by[x]:
                d = decisions[did]
                if not cites(req, d):
                    failures.append(f"PIN {req.id} cites {decisions[x].id}, which {d.id} {verb} (amends rule): "
                                    f"re-read {d.id}, then cite it and pin it "
                                    f'(confirmed_against: "{d.id} #{st.fingerprint(d.pin_text)}"), '
                                    f"or set {req.id} status: Superseded")
    return failures


def _plan_approved(src: st.Source, rel: str) -> bool:
    text = src.read(rel)
    if text is None:
        return False
    status = next((ln for ln in text.splitlines() if ln.startswith("Status:")), "")
    return bool(re.search(r"(?i)\b(approved|done)\b", status))


def registered_questions(register: str | None) -> set[str]:
    """Owner-question ids that a register ROW declares (`| Q88 | ...`, the first cell), excluding rows whose `status`
    column (when the table has one) starts with superseded or withdrawn. An id mentioned in prose never counts."""
    out: set[str] = set()
    status_col = None
    for line in (register or "").splitlines():
        if not line.lstrip().startswith("|"):
            status_col = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        heads = [c.casefold() for c in cells]
        if "status" in heads and not QUESTION_ID_RE.fullmatch(cells[0]):
            status_col = heads.index("status")
            continue
        if not QUESTION_ID_RE.fullmatch(cells[0]):
            continue
        if status_col is not None and status_col < len(cells) and \
                cells[status_col].casefold().startswith(("superseded", "withdrawn")):
            continue
        out.add(cells[0])
    return out


def check_sources(records: list[st.Record], src: st.Source) -> list[str]:
    """AC-5: every requirement's `source` or `spec_refs` names an EXISTING target: a loaded decision's id (OD-n,
    ADR-n) or file path, an owner-question id found in the project's question register (none -> Q-ids never count),
    a `handoff §N` that is a row of the sort (any N when the repo has no sort), or an approved milestone plan
    (docs/milestones/M*-plan.md whose Status line says APPROVED or DONE)."""
    decisions = [r for r in records if r.kind == "decision"]
    secs = sort_sections(src)
    register = src.read(QUESTION_REGISTER)
    asked = registered_questions(register)
    failures = []
    for req in (r for r in records if r.kind == "requirement"):
        source = " | ".join([str(req.data.get("source") or "")] + _list(req.data.get("spec_refs")))
        if any(q in asked for q in QUESTION_ID_RE.findall(source)):
            continue
        if any(re.search(r"(?<![A-Za-z0-9])" + re.escape(d.id) + r"(?![0-9])", source, re.I)
               or (d.path != st.OD_LOG and d.path.lower() in source.lower()) for d in decisions):
            continue
        if any(secs is None or int(n) in secs for n in HANDOFF_REF_RE.findall(source)):
            continue
        if any(_plan_approved(src, m.group(0)) for m in PLAN_REF_RE.finditer(source)):
            continue
        failures.append(f'SOURCE {req.id}: source and spec_refs "{source}" name no decision id, '
                        f"no `handoff §N`, no owner-question id (Q88) and no approved milestone plan "
                        f"(docs/milestones/M*-plan.md) — name where the requirement came from")
    return failures


def requirement_sections(src: st.Source) -> list[int] | None:
    """Section numbers the approved master-spec sort files as `requirement`; None when the repo has no sort."""
    text = src.read(HANDOFF_SORT)
    if text is None:
        return None
    return [int(m.group(1)) for m in map(SORT_ROW_RE.match, text.splitlines())
            if m and m.group(2).strip().lower() == "requirement"]


def exemption(rs: list[Relation] | None) -> str | None:
    """Why a decision needs no requirement (AC-3), or None when it needs one: its relations are only `approves`
    (a pure approval, every target a milestone), or it carries `no-requirement — <reason>`. No other verb exempts;
    unparsed relations never do. Whether an exemption is TRUE (the decision really states no requirement) is a
    reading the verifier makes on every PR that adds one; no code check can."""
    if not rs:
        return None
    reason = next((r.reason for r in rs if r.verb == NO_REQUIREMENT), None)
    if reason is not None:
        return reason
    pure = all(r.verb == "approves" and all(TARGET_RE.match(t).group("ms") for t in r.targets) for r in rs)
    return "a pure approval" if pure else None


def coverage(records: list[st.Record], rels: dict[str, list[Relation]],
             src: st.Source) -> tuple[list[str], list[int] | None]:
    """(decision ids cited by no requirement although they need one, requirement sections cited by none, or None
    without a sort file). AC-3: a decision needs a requirement unless `exemption` gives a reason (only `approves`
    entries, or a `no-requirement — <reason>` entry); no other verb exempts, and unparsed relations never do.
    AC-4: `handoff §N` in a requirement's source or spec_refs covers section N."""
    reqs = [r for r in records if r.kind == "requirement" and live(r)]
    dec_gaps = []
    for d in (r for r in records if r.kind == "decision"):
        if exemption(rels.get(d.id.upper())) is not None:
            continue
        if not any(covers(q, d) for q in reqs):
            dec_gaps.append(d.id)
    dec_gaps.sort(key=lambda i: (i.rsplit("-", 1)[0], id_number(i)))
    sections = requirement_sections(src)
    if sections is None:
        return dec_gaps, None
    cited = set()
    for q in reqs:
        for part in [str(q.data.get("source") or "")] + _list(q.data.get("spec_refs")):
            cited.update(int(n) for n in HANDOFF_REF_RE.findall(part))
    return dec_gaps, [n for n in sections if n not in cited]


def trace_report(root: Path) -> dict:
    """Everything the relations / amends / source / coverage checks found, for the status page (one definition)."""
    src = st.Source(root)
    records = st.load_records(src)
    mode, warnings, mode_failures = read_mode(src)
    rel_failures, rel_reports, rels = check_relations(records, mode, src)
    dec_gaps, sec_gaps = coverage(records, rels, src)
    return {"mode": mode, "warnings": warnings, "record_failures": mode_failures + rel_failures,
            "reports": rel_reports, "amends": check_amends(records, rels), "sources": check_sources(records, src),
            "decisions_uncovered": dec_gaps, "sections_uncovered": sec_gaps}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--suggest", action="store_true",
                    help="also print paste-ready exemption entries and pins (never writes a file)")
    args = ap.parse_args(argv)
    st.utf8_stdout()
    root = Path(args.root)
    if not root.is_dir():
        print(f"spec_dupes: ROOT not found: {root}", file=sys.stderr)
        return 2
    src = st.Source(root)
    records = st.load_records(src)
    record_failures = check_records(records, src.problems)
    failures, accepted, sugg = check_pairs(records)
    pin_failures, pin_sugg = check_pins(records)
    mode, warnings, mode_failures = read_mode(src)
    rel_failures, rel_reports, rels = check_relations(records, mode, src)
    record_failures += mode_failures + rel_failures
    pin_failures += check_amends(records, rels)
    source_failures = check_sources(records, src)
    dec_gaps, sec_gaps = coverage(records, rels, src)
    cov_lines = ([f"COVERAGE decision {d}: cited by no requirement (its relations need one)" for d in dec_gaps]
                 + [f"COVERAGE handoff §{n}: a `requirement` section of {HANDOFF_SORT} cited by no requirement "
                    f"(write `handoff §{n}` in a requirement's source or spec_refs)" for n in sec_gaps or []])
    for line in (warnings + record_failures + accepted + failures + pin_failures + source_failures + rel_reports
                 + cov_lines + ((sugg + pin_sugg) if args.suggest else [])):
        print(line)
    n_req = sum(len(r.items) for r in records if r.kind == "requirement")
    n_dec = sum(len(r.items) for r in records if r.kind == "decision")
    n_pairs = sum(1 for ln in failures if ln.startswith("DUPLICATE")) + len(accepted)
    print(f"spec_dupes: {n_req} requirement items, {n_dec} decision items (full scan); pairs >= {st.THRESHOLD:.2f}: "
          f"{n_pairs} ({n_pairs - len(accepted)} blocking, {len(accepted)} exempted); "
          f"exemption failures: {sum(1 for ln in failures if ln.startswith('EXEMPTION'))}; "
          f"pin failures: {len(pin_failures)}; record failures: {len(record_failures)}; "
          f"source failures: {len(source_failures)}")
    print(f"COVERAGE ({mode} mode, {'blocking' if mode == 'block' else 'not blocking'}): decisions not covered: "
          f"{len(dec_gaps)}; requirement sections not covered: {'n/a' if sec_gaps is None else len(sec_gaps)}; "
          f"decision records without relations: {len(rel_reports)}")
    coverage_blocks = mode == "block" and bool(dec_gaps or sec_gaps)
    return 1 if record_failures or failures or pin_failures or source_failures or coverage_blocks else 0

if __name__ == "__main__":
    sys.exit(main())
