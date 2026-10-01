#!/usr/bin/env python3
"""trace_check.py — checks that the requirement -> AC -> work item -> test -> evidence
chain is complete for every requirement in a Project OS tree, and can generate a
human-readable trace view.

Usage:
    python tools/trace_check.py ROOT [--strict] [--write-view] [--check-view]

For each requirement under ROOT/spec/requirements/REQ-###.md, checks:

  - it has at least one acceptance criterion (the schema already requires this, but a
    hand-broken file can still lack one; this check does not depend on the schema);
  - each acceptance criterion is named in the `tests_required` of at least one work
    item that links this requirement (an entry counts as naming AC-<n> when it is
    exactly "AC-<n>" or starts with "AC-<n>:");
  - that acceptance criterion has an evidence file at
    ROOT/evidence/<W-id>/<AC-id>.md (the work item that named it), with
    `result: pass` and a `verified_by` that is present and differs from `builder`
    (independent verification — the same agent cannot be both);
  - REQ-014: the evidence's `ac_fp` (tools/ac_fp.py) equals the fingerprint of the criterion's
    CURRENT text. A differing ac_fp is STALE (an incompleteness reason, plus a FAIL line naming
    requirement, criterion and file when the requirement is Verified or later; a hint when it
    equals another criterion's fingerprint: renumbered?). Evidence without ac_fp is
    "unpinned: before tracing": it completes the chain, is shown as unpinned and never counted
    fresh; this tool never writes a fingerprint into it. A malformed ac_fp is a FAIL at any status.

Hard FAIL lines at any status (REQ-014 AC-3/AC-4): `split_from` naming no other existing
requirement; unpinned evidence on a split requirement; status Delivered-before-trace without a
`delivered_in` naming an existing docs/milestones/*-report.md that names it, or linked by any work item (OD-48); status Superseded without a
`superseded_by` naming an existing requirement or decision (OD row / spec/decisions record).
Those two statuses demand no evidence and print DELIVERED-BEFORE-TRACE / SUPERSEDED.

REQ-016 releases and reviews (hard FAIL lines at any status; each names the requirement or work item and the record):

  - Release records are ROOT/releases/R-###.md (release schema). No releases/ folder = no releases yet. Anything
    else in releases/ (a subfolder, another extension, a misnamed record) except README.md FAILS. A record whose
    frontmatter does not parse, whose `id` is not R-### or differs from its file name, whose `items` is not a list
    of strings, whose `kind` is not kit or production (absent = production), or whose items hold an id that is
    neither REQ-### nor W-### (or names no such record) FAILS: a shape this check cannot read is never "nothing to
    check".
  - Two-way link: a requirement at Released must name `release: R-###`; that record must exist, list it in
    `items`, and be at its kind's delivered status (kit: released; production: deployed; cancelled, preparing,
    rolled_back, missing ... FAIL). Any requirement naming `release: R-###` (at any status) is held to the same
    link. A record listing a requirement that does not name it back, or that is not at Released, FAILS. A
    non-Released requirement is shown as unreleased, never released (`release_label`); a `release` that is not R-###
    on a non-Released requirement is a target label, not checked.
  - Review link: a done work item's `review_status` must START with the pull request that merged it, `PR #<n>`
    (n >= 1, optional space after PR); later `PR #` mentions are follow-ups, a bare `#n` is an issue reference.
    Tier A and B continue with `; reviewed` (word) or the explicit legacy marker `; review not recorded`; anything
    else ("not reviewed", "review pending") FAILS. Tier C names the pull request only. A done work item whose tier
    is not A, B or C, or whose review_status is not a string, FAILS (fail closed).

Separately, every work item's `requirement_ids` must each name a requirement that
actually exists under ROOT/spec/requirements/; a work item naming an unknown
requirement is reported as an orphan link and always fails the run.

Output: one line per requirement, `REQ-###: VERIFIED` or
`REQ-###: INCOMPLETE — <reason>; <reason>...`, plus one line per orphan work item link.

Exit code:
  - 1 if any orphan work-item link exists (a broken chain, always a hard failure);
  - 1 if --strict and any requirement is INCOMPLETE;
  - 1 if (without --strict) any requirement whose `status` is Verified, Reviewed, or
    Released is INCOMPLETE (a requirement not yet claimed done may be incomplete —
    that is normal, in-progress work, not a defect);
  - 1 if --check-view is given and views/trace.md is missing or does not match what
    --write-view would produce right now;
  - 0 otherwise.

--write-view writes ROOT/views/trace.md (generated — never hand-edit it).
--check-view exits 1 if that file would differ from a fresh generation.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_text  # noqa: E402  (spec_text.fingerprint is the one fingerprint function; OD/ADR ids come from it too)

AC_ID_RE = re.compile(r"^AC-\d+$")
REQ_ID_RE = re.compile(r"^REQ-\d{3,}$")
WORK_ID_RE = re.compile(r"^W-\d{3,}$")

DONE_STATUSES = {"Verified", "Reviewed", "Released"}
# REQ-014 AC-4: statuses that demand no evidence; each names where the work went instead
DELIVERED_BEFORE_TRACE = "Delivered-before-trace"
SUPERSEDED = "Superseded"
NO_EVIDENCE_STATUSES = {DELIVERED_BEFORE_TRACE, SUPERSEDED}
AC_FP_RE = re.compile(r"^[0-9a-f]{12}$")
MILESTONE_DIR = ("docs", "milestones")
SUPERSEDED_BY_RE = re.compile(r"^(REQ-\d{3,}|OD-\d+|ADR-\d{3,})$")
UNPINNED = "unpinned: before tracing"
# REQ-014 AC-2 (round 2): only evidence that existed BEFORE fingerprints may lack ac_fp. The list of those files is
# written once (python tools/ac_fp.py --freeze-unpinned ROOT); a missing list means no evidence may be unpinned.
UNPINNED_LIST = ("spec", "traceability", "unpinned-before-tracing.txt")


def load_unpinned_list(root: Path) -> set[str]:
    """Evidence paths (posix, relative to ROOT) allowed to lack ac_fp. Blank lines and # comments are skipped."""
    p = root.joinpath(*UNPINNED_LIST)
    if not p.is_file():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line.replace("\\", "/"))
    return out


VIEW_HEADER = (
    "<!-- generated by tools/trace_check.py --write-view — do not edit by hand -->\n"
    "# Requirement trace view\n\n"
)


# frontmatter-parser-splits-on-any-triple-dash: a delimiter line is '---' alone on its
# line (trailing whitespace allowed), never a '---' substring inside a value.
_FRONTMATTER_DELIM_RE = re.compile(r"(?m)^---[ \t]*\r?$")


def parse_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Minimal YAML-frontmatter parser: (data, error). Never raises."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        return None, f"PyYAML not available: {exc}"

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        return None, f"could not read file: {exc}"

    if not text.startswith("---"):
        return None, "missing YAML frontmatter"

    delims = list(_FRONTMATTER_DELIM_RE.finditer(text))
    if len(delims) < 2:
        return None, "malformed YAML frontmatter"

    try:
        data = yaml.safe_load(text[delims[0].end():delims[1].start()])
    except Exception as exc:
        return None, f"invalid YAML: {exc}"

    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, "frontmatter must be a YAML mapping"

    return data, None


def _names_ac(entry: str, ac_id: str) -> bool:
    entry = entry.strip()
    return entry == ac_id or entry.startswith(ac_id + ":")


class Requirement:
    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data
        self.id: str = data.get("id", path.stem)
        self.status: str = data.get("status", "")
        acs = data.get("acceptance_criteria") or []
        self.ac_ids: list[str] = [
            ac["id"] for ac in acs if isinstance(ac, dict) and isinstance(ac.get("id"), str)
        ]
        # REQ-014: the fingerprint of each criterion's CURRENT text, which an evidence file's ac_fp must still match
        self.ac_fps: dict[str, str] = {
            ac["id"]: spec_text.fingerprint(str(ac.get("text") or ""))
            for ac in acs if isinstance(ac, dict) and isinstance(ac.get("id"), str)
        }


class WorkItem:
    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data
        self.id: str = data.get("id", path.stem)
        self.requirement_ids: list[str] = [
            r for r in (data.get("requirement_ids") or []) if isinstance(r, str)
        ]
        self.tests_required: list[str] = [
            t for t in (data.get("tests_required") or []) if isinstance(t, str)
        ]

    def names_ac(self, ac_id: str) -> bool:
        return any(_names_ac(t, ac_id) for t in self.tests_required)


def load_requirements(root: Path) -> tuple[list[Requirement], list[str]]:
    req_dir = root / "spec" / "requirements"
    reqs: list[Requirement] = []
    parse_errors: list[str] = []
    if not req_dir.is_dir():
        return reqs, parse_errors
    for p in sorted(req_dir.glob("REQ-*.md")):
        data, err = parse_frontmatter(p)
        if err is not None:
            parse_errors.append(f"{p}: {err}")
            continue
        reqs.append(Requirement(p, data))
    return reqs, parse_errors


def load_work_items(root: Path) -> tuple[list[WorkItem], list[str]]:
    work_dir = root / "work"
    items: list[WorkItem] = []
    parse_errors: list[str] = []
    if not work_dir.is_dir():
        return items, parse_errors
    for p in sorted(work_dir.glob("W-*.md")):
        data, err = parse_frontmatter(p)
        if err is not None:
            parse_errors.append(f"{p}: {err}")
            continue
        items.append(WorkItem(p, data))
    return items, parse_errors


def load_evidence(root: Path, work_id: str, ac_id: str) -> tuple[dict[str, Any] | None, str | None]:
    ev_path = root / "evidence" / work_id / f"{ac_id}.md"
    if not ev_path.is_file():
        return None, "no evidence file"
    data, err = parse_frontmatter(ev_path)
    if err is not None:
        return None, f"evidence file unreadable: {err}"
    return data, None


class Result:
    """What one requirement's check found (REQ-014).

    reasons   incompleteness reasons: fail the run only for a Verified/Reviewed/Released requirement (or --strict);
    failures  hard failures that fail the run at ANY status: a malformed ac_fp, unpinned evidence on a requirement
              that is split_from another;
    fresh / unpinned / stale  criterion ids by the state of the evidence that proves them.
    """

    def __init__(self) -> None:
        self.reasons: list[str] = []
        self.failures: list[str] = []
        self.fresh: list[str] = []
        self.unpinned: list[str] = []
        self.stale: list[tuple[str, str, str]] = []   # (AC id, evidence path, renumber hint)


def _ev_rel(work_id: str, ac_id: str) -> str:
    return f"evidence/{work_id}/{ac_id}.md"


def _renumber_hint(req: Requirement, ac_id: str, fp: str) -> str:
    """AC-3: a stale fingerprint that equals ANOTHER current criterion's is a hint, never a re-attachment."""
    others = [a for a, f in req.ac_fps.items() if f == fp and a != ac_id]
    return f"; matches {', '.join(others)}'s text: renumbered?" if others else ""


def check_requirement(root: Path, req: Requirement, work_items: list[WorkItem],
                      allowed_unpinned: set[str] | None = None) -> Result:
    """Check one requirement's chain. Evidence is keyed by criterion id; its `ac_fp` must equal the fingerprint of
    that criterion's CURRENT text, else it is stale. Evidence without `ac_fp` is 'unpinned: before tracing': it
    still completes the chain, it is never counted fresh, and nothing here ever writes a fingerprint into it."""
    res = Result()

    if not req.ac_ids:
        res.reasons.append("no acceptance criteria")
        return res

    split = req.data.get("split_from") is not None
    linked_items = [wi for wi in work_items if req.id in wi.requirement_ids]

    for ac_id in req.ac_ids:
        owning_items = [wi for wi in linked_items if wi.names_ac(ac_id)]
        if not owning_items:
            res.reasons.append(f"{ac_id} not named in any linked work item's tests_required")
            continue

        # An AC could in principle be named by more than one work item; it is complete if at least one of them has
        # valid, independently-verified, passing evidence. Fresh outranks unpinned; any stale file is reported.
        state = None          # None | "unpinned" | "fresh"
        ac_reason = None
        stale_lines: list[str] = []
        for wi in owning_items:
            rel = _ev_rel(wi.id, ac_id)
            data, err = load_evidence(root, wi.id, ac_id)
            if err is not None:
                ac_reason = f"{ac_id} {err} (work item {wi.id}, {rel})"
                continue
            if data.get("ac") != ac_id:
                ac_reason = f"{ac_id} evidence file's ac field does not match ({wi.id})"
                continue
            if data.get("work_item") != wi.id:
                ac_reason = f"{ac_id} evidence file's work_item field does not match ({wi.id})"
                continue
            if data.get("result") != "pass":
                ac_reason = f"{ac_id} evidence result is not pass ({wi.id})"
                continue
            verified_by = data.get("verified_by")
            builder = data.get("builder")
            if not verified_by:
                ac_reason = f"{ac_id} evidence has no verified_by ({wi.id})"
                continue
            if builder and verified_by == builder:
                ac_reason = f"{ac_id} evidence verified_by matches builder — not independent ({wi.id})"
                continue
            bound = data.get("requirement")
            if bound is not None and bound != req.id:
                res.failures.append(f"{req.id} {ac_id}: {rel} names requirement {bound!r}, not {req.id} — evidence "
                                    f"proves only the requirement it names")
                ac_reason = f"{ac_id} evidence names requirement {bound!r}, not {req.id} ({rel})"
                continue
            if "ac_fp" in data and bound is None:
                res.failures.append(f"{req.id} {ac_id}: {rel} carries ac_fp but no requirement: — pinned evidence "
                                    f"must name its requirement (python tools/ac_fp.py {req.id} {ac_id} --yaml)")
                ac_reason = f"{ac_id} pinned evidence names no requirement ({rel})"
                continue
            if "ac_fp" not in data:
                if split:
                    res.failures.append(
                        f"{req.id} {ac_id}: {rel} has no ac_fp, but {req.id} is split_from "
                        f"{req.data.get('split_from')} and was born after fingerprints existed; its evidence must "
                        f"carry ac_fp (python tools/ac_fp.py {req.id} {ac_id})")
                    ac_reason = f"{ac_id} evidence has no ac_fp on a split requirement ({rel})"
                    continue
                if rel not in (allowed_unpinned or set()):
                    res.failures.append(
                        f"{req.id} {ac_id}: {rel} has no ac_fp and is not listed in "
                        f"{'/'.join(UNPINNED_LIST)} — new evidence must carry ac_fp "
                        f"(python tools/ac_fp.py {req.id} {ac_id} --yaml)")
                    ac_reason = f"{ac_id} evidence has no ac_fp and was not written before tracing ({rel})"
                    continue
                state = state or "unpinned"
                continue
            fp = data.get("ac_fp")
            if not isinstance(fp, str) or not AC_FP_RE.match(fp):
                res.failures.append(f"{req.id} {ac_id}: {rel} has a malformed ac_fp {fp!r} "
                                    f"(want 12 lowercase hex: python tools/ac_fp.py {req.id} {ac_id})")
                ac_reason = f"{ac_id} evidence has a malformed ac_fp ({rel})"
                continue
            if fp != req.ac_fps[ac_id]:
                hint = _renumber_hint(req, ac_id, fp)
                stale_lines.append(
                    f"{ac_id} evidence STALE: {rel} proved text #{fp}, the criterion is now #{req.ac_fps[ac_id]} — "
                    f"re-verify {req.id} {ac_id}{hint}")
                res.stale.append((ac_id, rel, hint))
                continue
            state = "fresh"

        if stale_lines:
            res.reasons.extend(stale_lines)
        elif state == "fresh":
            res.fresh.append(ac_id)
        elif state == "unpinned":
            res.unpinned.append(ac_id)
        else:
            res.reasons.append(ac_reason or f"{ac_id} incomplete")

    return res


def decision_ids(root: Path) -> set[str]:
    """Ids of the decision records a `superseded_by` may name: OD rows of the decision log and spec/decisions/."""
    src = spec_text.Source(root)
    return {r.id.upper() for r in spec_text.od_records(src) + spec_text.adr_records(src)}


def _chain(req: Requirement, key: str, by_id: dict[str, Requirement]) -> list[str] | None:
    """Follow `key` (superseded_by / split_from) through requirements; the loop as a list of ids, or None."""
    seen = [req.id]
    cur = req
    while True:
        nxt = cur.data.get(key)
        if not isinstance(nxt, str) or nxt.strip() not in by_id:
            return None
        nxt = nxt.strip()
        if nxt in seen:
            return seen[seen.index(nxt):] + [nxt]
        seen.append(nxt)
        cur = by_id[nxt]
        if key == "superseded_by" and cur.status != SUPERSEDED:
            return None


def check_status_fields(root: Path, req: Requirement, req_ids: set[str], dec_ids: set[str],
                        by_id: dict[str, Requirement] | None = None,
                        linked_by: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(hard failures, warnings) of the REQ-014 fields, at any status: split_from, delivered_in, superseded_by."""
    by_id = by_id or {}
    out: list[str] = []
    warn: list[str] = []
    if "split_from" in req.data:
        split = req.data.get("split_from")
        if not isinstance(split, str) or split not in req_ids or split == req.id:
            out.append(f"{req.id}: split_from {split!r} does not name another existing requirement")
        else:
            loop = _chain(req, "split_from", by_id)
            if loop:
                out.append(f"{req.id}: split_from loop {' -> '.join(loop)}")
    if req.status == DELIVERED_BEFORE_TRACE:
        where = req.data.get("delivered_in")
        where = where.strip() if isinstance(where, str) else where
        if not isinstance(where, str) or not where:
            out.append(f"{req.id}: status {DELIVERED_BEFORE_TRACE} needs delivered_in: a docs/milestones/*-report.md "
                       f"that names {req.id} (OD-48)")
        elif re.match(r"(?i)^PR\b", where):
            out.append(f"{req.id}: delivered_in {where!r}: delivered_in must be a milestone report (OD-48); cite the PR "
                       f"inside the report")
        else:
            base = root.joinpath(*MILESTONE_DIR).resolve()
            target = (root / where).resolve()
            if base not in target.parents:
                out.append(f"{req.id}: delivered_in {where!r} is not inside docs/milestones/ (OD-48: a milestone report)")
            elif target.name.endswith("-plan.md"):
                out.append(f"{req.id}: delivered_in {where!r} is a plan, not a report of what was delivered")
            elif not target.name.endswith("-report.md"):
                out.append(f"{req.id}: delivered_in {where!r} is not a milestone report (*-report.md, OD-48)")
            elif not target.is_file():
                out.append(f"{req.id}: delivered_in {where!r} does not exist")
            elif not re.search(r"(?<![A-Za-z0-9])" + re.escape(req.id) + r"(?![0-9])",
                               target.read_text(encoding="utf-8", errors="replace")):
                out.append(f"{req.id}: delivered_in {where!r} never names {req.id}; the report must cite it")
        for wid in linked_by or []:
            out.append(f"{req.id}: status {DELIVERED_BEFORE_TRACE}, but work item {wid} links it — a requirement "
                       f"delivered through the records is not Delivered-before-trace (OD-48)")
    if req.status == SUPERSEDED:
        by = req.data.get("superseded_by")
        if not isinstance(by, str) or not SUPERSEDED_BY_RE.match(by.strip()):
            out.append(f"{req.id}: status {SUPERSEDED} needs superseded_by: an existing REQ-### or decision id")
        else:
            by = by.strip()
            if not ((by in req_ids and by != req.id) or by.upper() in dec_ids):
                out.append(f"{req.id}: superseded_by {by} names no existing requirement or decision")
            else:
                loop = _chain(req, "superseded_by", by_id)
                if loop:
                    out.append(f"{req.id}: superseded_by loop {' -> '.join(loop)}")
                elif by in by_id and by_id[by].status == "Draft":
                    warn.append(f"WARN {req.id}: superseded_by {by}, which is still a Draft")
    return out, warn


def orphan_evidence(root: Path, wi: WorkItem, by_id: dict[str, Requirement]) -> list[str]:
    """WARN lines for evidence files of a work item whose AC id none of its requirements has any more."""
    folder = root / "evidence" / wi.id
    reqs = [by_id[r] for r in wi.requirement_ids if r in by_id]
    if not folder.is_dir() or not reqs:
        return []
    known = {a for r in reqs for a in r.ac_ids}
    out = []
    for p in sorted(folder.glob("AC-*.md")):
        if p.stem in known:
            continue
        data, _err = parse_frontmatter(p)
        fp = (data or {}).get("ac_fp")
        hint = ""
        for r in reqs:
            same = [a for a, f in r.ac_fps.items() if f == fp]
            if same:
                hint = f"; matches {r.id} {', '.join(same)}'s text: renumbered?"
        out.append(f"WARN {wi.id}: evidence/{wi.id}/{p.name} proves {p.stem}, which "
                   f"{', '.join(r.id for r in reqs)} no longer has{hint}")
    return out


def shared_ac_ids(wi: WorkItem, by_id: dict[str, Requirement]) -> list[str]:
    """A work item delivering two requirements that share an AC id: one evidence file cannot prove both."""
    owners: dict[str, list[str]] = {}
    for rid in dict.fromkeys(wi.requirement_ids):
        if rid in by_id:
            for a in by_id[rid].ac_ids:
                owners.setdefault(a, []).append(rid)
    return [f"{wi.id} delivers {' and '.join(rs)}, which both have {a}; one evidence file cannot prove both — "
            f"split the work item" for a, rs in sorted(owners.items()) if len(rs) > 1]


def status_line(req: Requirement, res: Result | None) -> str:
    """The one line per requirement, printed and written into views/trace.md."""
    if req.status == DELIVERED_BEFORE_TRACE:
        where = req.data.get("delivered_in") or "<delivered_in missing>"
        return f"{req.id}: DELIVERED-BEFORE-TRACE (delivered in {where}; no evidence demanded)"
    if req.status == SUPERSEDED:
        by = req.data.get("superseded_by") or "<superseded_by missing>"
        return f"{req.id}: SUPERSEDED (by {by}; no evidence demanded)"
    if res is None:  # pragma: no cover - callers pass a result for every other status
        raise ValueError(f"{req.id}: no check result")
    if res.reasons:
        return f"{req.id}: INCOMPLETE — " + "; ".join(res.reasons)
    tail = f"{len(req.ac_ids)} criteria: {len(res.fresh)} fresh"
    if res.unpinned:
        tail += f", {len(res.unpinned)} {UNPINNED} ({', '.join(res.unpinned)})"
    return f"{req.id}: VERIFIED ({tail})"


# ---- REQ-016: release records and review links -------------------------------------------------------------------

RELEASE_ID_RE = re.compile(r"^R-\d{3,}$")
RELEASE_FILE_RE = re.compile(r"^R-\d{3,}\.md$")
RELEASES_README = "README.md"
RELEASED = "Released"
UNRELEASED = "unreleased"
# a release record's kind -> the one status at which it has delivered (absent kind = production)
DELIVERED_STATE = {"kit": "released", "production": "deployed"}
DEFAULT_KIND = "production"
# the merging pull request is the `PR #<n>` the value STARTS with (n >= 1, optional space after PR); later `PR #`
# mentions are follow-ups and a bare "#60" is an issue reference, never a pull request
MERGING_PR_RE = re.compile(r"^PR ?#([1-9]\d*)(?![0-9])")
# Tier A/B: `PR #<n>;` then the verdict `reviewed` or the explicit legacy marker `review not recorded`
REVIEWED_RE = re.compile(r"^PR ?#[1-9]\d*(?![0-9]);\s*(reviewed|review not recorded)\b")
LEGACY_REVIEW = "review not recorded"
REVIEWED_TIERS = {"A", "B"}
ALL_TIERS = {"A", "B", "C"}
YAML_HINT = "if the value contains ' #', quote it: YAML treats ' #' as a comment"


class Release:
    def __init__(self, path: Path, rid: str, items: list[str], kind: str, status: Any):
        self.path = path
        self.id = rid
        self.items = items
        self.kind = kind
        self.status = status

    @property
    def rel(self) -> str:
        return f"releases/{self.path.name}"


def load_releases(root: Path) -> tuple[dict[str, Release], list[str]]:
    """(records by id, hard failures). Fails closed on every shape it cannot read, and on any entry of releases/
    that is not R-###.md or README.md (a subfolder, another extension, a misnamed record)."""
    rel_dir = root / "releases"
    out: dict[str, Release] = {}
    fails: list[str] = []
    if not rel_dir.is_dir():
        return out, fails
    for p in sorted(rel_dir.iterdir(), key=lambda q: q.name):
        rel = f"releases/{p.name}"
        if p.is_dir():
            fails.append(f"{rel}: a folder inside releases/; only R-###.md records and README.md belong there")
            continue
        if p.name == RELEASES_README:
            continue
        if not RELEASE_FILE_RE.match(p.name):
            fails.append(f"{rel}: not a release record name (R-###.md); only R-###.md records and README.md "
                         f"belong in releases/")
            continue
        data, err = parse_frontmatter(p)
        if err is not None:
            fails.append(f"{rel}: release record unreadable: {err}")
            continue
        rid = data.get("id")
        if not isinstance(rid, str) or not RELEASE_ID_RE.match(rid.strip()):
            fails.append(f"{rel}: release id {rid!r} is not R-###")
            continue
        rid = rid.strip()
        if rid != p.stem:
            fails.append(f"{rel}: release id {rid} does not match its file name {p.stem}")
            continue
        items = data.get("items")
        if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
            fails.append(f"{rel}: release {rid} items must be a non-empty list of requirement ids, got {items!r}")
            continue
        kind = data.get("kind", DEFAULT_KIND)
        if not isinstance(kind, str) or kind not in DELIVERED_STATE:
            fails.append(f"{rel}: release {rid} kind {kind!r} is not kit or production")
            continue
        out[rid] = Release(p, rid, [i.strip() for i in items], kind, data.get("status"))
    return out, fails


def release_label_of(data: dict[str, Any]) -> str:
    """What the page and the view show: the release id only for a Released requirement, else 'unreleased'
    (a Verified or Reviewed requirement is never shown as released, whatever its release field says)."""
    rel = data.get("release")
    if data.get("status") == RELEASED and isinstance(rel, str) and rel.strip():
        return rel.strip()
    return UNRELEASED


def release_label(req: Requirement) -> str:
    return release_label_of(req.data)


def merging_pr(work: dict[str, Any]) -> str | None:
    """The pull request that merged a done work item: the `PR #n` its review_status STARTS with, as 'PR #n'."""
    rs = work.get("review_status")
    m = MERGING_PR_RE.match(rs) if isinstance(rs, str) else None
    return f"PR #{m.group(1)}" if m else None


def review_cell(work: dict[str, Any]) -> str | None:
    """The status page's Review PR text: the merging PR, plus '(review not recorded)' for the legacy marker."""
    pr = merging_pr(work)
    if pr is None:
        return None
    m = REVIEWED_RE.match(work.get("review_status") or "")
    return f"{pr} ({LEGACY_REVIEW})" if m and m.group(1) == LEGACY_REVIEW else pr


def check_releases(reqs: list[Requirement], releases: dict[str, Release], work_ids: set[str]) -> list[str]:
    """REQ-016 AC-2: the two-way link between requirements and release records; each line names both."""
    out: list[str] = []
    by_id = {r.id: r for r in reqs}
    for req in sorted(reqs, key=lambda r: r.id):
        raw = req.data.get("release")
        named = raw.strip() if isinstance(raw, str) else None
        if req.status == RELEASED:
            if "release" not in req.data or raw is None or (isinstance(raw, str) and not raw.strip()):
                out.append(f"{req.id}: status {RELEASED} names no release (add release: R-### naming the release "
                           f"record that lists it)")
                continue
            if named is None or not RELEASE_ID_RE.match(named):
                out.append(f"{req.id}: status {RELEASED}, but release {raw!r} is not a release record id (R-###)")
                continue
        elif named is None or not RELEASE_ID_RE.match(named):
            if "release" in req.data and raw is not None and not isinstance(raw, str):
                out.append(f"{req.id}: release {raw!r} is not a string")
            continue  # not released, no record named: a target label (e.g. V1) or nothing
        rec = releases.get(named)
        if rec is None:
            out.append(f"{req.id}: release {named} names no release record (releases/{named}.md does not exist "
                       f"or is unreadable)")
        elif req.id not in rec.items:
            out.append(f"{req.id}: names release {named}, but {rec.rel} does not list {req.id} in items")
        elif req.status == RELEASED and rec.status != DELIVERED_STATE[rec.kind]:
            out.append(f"{req.id}: status {RELEASED}, but {rec.rel} ({rec.kind} release) is at status "
                       f"{rec.status!r}; a {rec.kind} release has delivered only at {DELIVERED_STATE[rec.kind]!r}")
    for rid, rec in sorted(releases.items()):
        for item in rec.items:
            if REQ_ID_RE.match(item):
                req = by_id.get(item)
                if req is None:
                    out.append(f"{rec.rel}: lists {item}, which is no existing requirement")
                    continue
                back = req.data.get("release")
                if not (isinstance(back, str) and back.strip() == rid):
                    out.append(f"{item}: {rec.rel} lists {item}, but {item} does not name it back "
                               f"(release: {back!r}, want {rid})")
                elif req.status != RELEASED:
                    out.append(f"{item}: {rec.rel} lists {item}, but {item} is at status {req.status!r}, not "
                               f"{RELEASED}; list a requirement only once it is Released")
            elif WORK_ID_RE.match(item):
                if item not in work_ids:
                    out.append(f"{rec.rel}: lists {item}, which is no existing work item")
            else:
                out.append(f"{rec.rel}: item {item!r} is neither a requirement (REQ-###) nor a work item (W-###)")
    return out


def check_review_link(wi: WorkItem) -> list[str]:
    """REQ-016 AC-3: a done work item's review_status STARTS with the pull request that merged it, `PR #<n>`;
    Tier A/B continue with `; reviewed` or the legacy marker `; review not recorded`."""
    if wi.data.get("status") != "done":
        return []
    tier = wi.data.get("tier")
    if not isinstance(tier, str) or tier.strip() not in ALL_TIERS:
        return [f"{wi.id}: status done with tier {tier!r}; tier must be A, B or C to know which review link it needs"]
    tier = tier.strip()
    rs = wi.data.get("review_status")
    if not isinstance(rs, str):
        return [f"{wi.id}: status done, Tier {tier}, but review_status {rs!r} is not text naming the merging pull "
                f"request (PR #<n>)"]
    want = "'PR #<n>; reviewed (...)' or 'PR #<n>; review not recorded'" if tier in REVIEWED_TIERS else "'PR #<n>'"
    if not MERGING_PR_RE.match(rs):
        if re.search(r"(?<![A-Za-z0-9])PR ?#[1-9]\d*(?![0-9])", rs):
            why = "a PR is mentioned, but the value must START with the merging pull request"
        else:
            bare = re.search(r"(?<![A-Za-z0-9])#\d+", rs)
            why = (f"only a bare {bare.group(0)}, which reads as an issue, or PR #0; " if bare
                   else "no pull request number; ") + YAML_HINT
        return [f"{wi.id}: status done, Tier {tier}, but review_status names no pull request first ({why}); "
                f"write {want}"]
    if tier in REVIEWED_TIERS and not REVIEWED_RE.match(rs):
        return [f"{wi.id}: status done, Tier {tier}, review_status {rs[:60]!r} does not continue with "
                f"'; reviewed' or '; {LEGACY_REVIEW}'; write {want}"]
    return []


def find_orphan_work_items(work_items: list[WorkItem], req_ids: set[str]) -> list[str]:
    orphans = []
    for wi in work_items:
        for rid in wi.requirement_ids:
            if rid not in req_ids:
                orphans.append(f"{wi.id}: ORPHAN — links unknown requirement {rid}")
    return orphans


def release_lines(reqs: list[Requirement]) -> list[str]:
    """REQ-016 AC-2: each Released requirement with its record; each Verified/Reviewed one as unreleased."""
    out = []
    for req in sorted(reqs, key=lambda r: r.id):
        if req.status == RELEASED:
            out.append(f"{req.id}: RELEASED in {release_label(req)}")
        elif req.status in DONE_STATUSES:
            out.append(f"{req.id}: UNRELEASED ({req.status}, in no release yet)")
    return out


def render_view(root: Path, req_lines: list[str], orphan_lines: list[str],
                rel_lines: list[str] | None = None) -> str:
    body = [VIEW_HEADER.rstrip("\n"), ""]
    body.append("## Requirements")
    body.append("")
    if req_lines:
        for line in req_lines:
            body.append(f"- {line}")
    else:
        body.append("- (no requirements found)")
    body.append("")
    body.append("## Orphan work-item links")
    body.append("")
    if orphan_lines:
        for line in orphan_lines:
            body.append(f"- {line}")
    else:
        body.append("- none")
    body.append("")
    body.append("## Releases")
    body.append("")
    if rel_lines:
        for line in rel_lines:
            body.append(f"- {line}")
    else:
        body.append("- no requirement is Verified, Reviewed or Released")
    body.append("")
    return "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover - not all stdout wrappers support this
        pass

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help="Project OS root directory")
    parser.add_argument("--strict", action="store_true", help="Fail on any incomplete requirement, not just done ones")
    parser.add_argument("--write-view", action="store_true", help="Write ROOT/views/trace.md")
    parser.add_argument("--check-view", action="store_true", help="Exit 1 if ROOT/views/trace.md is stale or missing")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"{args.root}: not a directory")
        return 1

    reqs, req_parse_errors = load_requirements(root)
    work_items, wi_parse_errors = load_work_items(root)

    for err in req_parse_errors + wi_parse_errors:
        print(f"PARSE ERROR: {err}")

    req_ids = {r.id for r in reqs}
    orphan_lines = find_orphan_work_items(work_items, req_ids)

    dec_ids = decision_ids(root)
    by_id = {r.id: r for r in reqs}
    allowed_unpinned = load_unpinned_list(root)
    linked: dict[str, list[str]] = {}
    for wi in work_items:
        for rid in dict.fromkeys(wi.requirement_ids):
            linked.setdefault(rid, []).append(wi.id)
    warn_lines: list[str] = []

    req_lines: list[str] = []
    fail_lines: list[str] = []
    any_incomplete = False
    any_done_incomplete = False
    for wi in work_items:
        fail_lines += [f"FAIL {x}" for x in shared_ac_ids(wi, by_id)]
        warn_lines += orphan_evidence(root, wi, by_id)
        fail_lines += [f"FAIL {x}" for x in check_review_link(wi)]
    releases, release_fails = load_releases(root)
    fail_lines += [f"FAIL {x}" for x in release_fails]
    fail_lines += [f"FAIL {x}" for x in check_releases(reqs, releases, {w.id for w in work_items})]
    rel_lines = release_lines(reqs)

    for req in sorted(reqs, key=lambda r: r.id):
        fails, warns = check_status_fields(root, req, req_ids, dec_ids, by_id, linked.get(req.id))
        fail_lines += [f"FAIL {x}" for x in fails]
        warn_lines += warns
        if req.status in NO_EVIDENCE_STATUSES:
            req_lines.append(status_line(req, None))
            continue
        res = check_requirement(root, req, work_items, allowed_unpinned)
        fail_lines += [f"FAIL {x}" for x in res.failures]
        if res.reasons:
            any_incomplete = True
            if req.status in DONE_STATUSES:
                any_done_incomplete = True
                for ac_id, rel, hint in res.stale:
                    fail_lines.append(f"FAIL {req.id} {ac_id}: stale evidence {rel} at status {req.status} "
                                      f"(the criterion's text changed after it was proved){hint}")
        req_lines.append(status_line(req, res))

    for line in req_lines:
        print(line)
    for line in orphan_lines:
        print(line)
    for line in rel_lines:
        print(line)
    for line in warn_lines + fail_lines:
        print(line)

    exit_code = 0
    if orphan_lines or req_parse_errors or wi_parse_errors or fail_lines:
        exit_code = 1
    if args.strict and any_incomplete:
        exit_code = 1
    if any_done_incomplete:
        exit_code = 1

    if args.write_view or args.check_view:
        views_dir = root / "views"
        view_path = views_dir / "trace.md"
        expected = render_view(root, req_lines, orphan_lines, rel_lines)

        if args.check_view:
            if not view_path.is_file() or view_path.read_text(encoding="utf-8") != expected:
                print(f"{view_path}: stale or missing — run --write-view to regenerate")
                exit_code = 1

        if args.write_view:
            views_dir.mkdir(parents=True, exist_ok=True)
            view_path.write_text(expected, encoding="utf-8")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
