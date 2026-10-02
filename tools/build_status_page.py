#!/usr/bin/env python3
"""build_status_page.py — render one project status page (REQ-008, OD-35) from the project's own data.

Usage:
    python tools/build_status_page.py ROOT --issues ISSUES.json --runs RUNS.json --out FILE
                                      [--title TEXT] [--now TEXT] [--sha TEXT]
    python tools/build_status_page.py ROOT --fetch --out FILE      (runs the gh commands below first)

Inputs (all read-only; nothing is read from a previously published page — status-artifact R1):
    spec/requirements/REQ-*.md, work/W-*.md, evidence/, views/build-order.md,
    knowledge/findings/*.json, owner-questions/OQ-*.md, .github/workflows/*.yml, git log,
    ISSUES.json  = gh issue list --state all --json number,title,state,labels,body,createdAt,closedAt
    RUNS.json    = gh run list --json databaseId,name,conclusion,createdAt,workflowName, each run carrying
                   a "jobs" list (gh run view ID --json jobs; each job has "steps" with conclusions)

The page is a pure function of those inputs plus two stamps (git sha, generation time), both
overridable (--sha, --now) so tests compare exact output. Every number is computed from the inputs;
one that cannot be computed reads `unmeasured` and names the command that would measure it (R2).
An issue's relates-to comes only from a `Relates-to:` line of its body naming EITHER requirement ids
(`Relates-to: REQ-006` or `Relates-to: REQ-006, REQ-007`) OR a section (`Relates-to: section <name>`); an
issue without one (the untouched form placeholder included) is counted and shown as UNMAPPED. "Needs you" comes only from owner-questions/.
The generated HTML is never committed (it depends on live issue and CI state).
Each requirement shows a computed health beside its stored status (REQ-014 AC-5), first match wins:
Changed - needs re-check (stale or unusable evidence fingerprint per trace_check, or a failing confirmed_against pin
per spec_dupes), Blocked (a work item delivering it is blocked or lists blockers), Parked (a parked issue's
Relates-to names it; work items have no parked status), Unpinned evidence (evidence without ac_fp), else OK.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory_lint  # noqa: E402  (frontmatter parser and the owner-question schema live there)
import spec_dupes  # noqa: E402  (`cites` is the one definition of "a requirement cites a decision")
import spec_text  # noqa: E402  (OD rows and decision records are read by the same parser the spec checks use)
import trace_check  # noqa: E402  (stale / unpinned evidence: the one definition, REQ-014)
import yaml  # noqa: E402

DONE = {"Verified", "Reviewed", "Released", "Delivered-before-trace"}   # REQ-014 AC-4
STATUS_ORDER = ["Draft", "Specified", "Approved", "Planned", "Implementing", "Implemented", "Testing", "Verified",
                "Reviewed", "Released", "Delivered-before-trace", "Superseded"]
# REQ-014 AC-5: one computed health per requirement, first match wins, in this order
H_CHANGED = "Changed - needs re-check"
H_BLOCKED = "Blocked"
H_PARKED = "Parked"
H_UNPINNED = "Unpinned evidence"
H_OK = "OK"
HEALTHS = [H_CHANGED, H_BLOCKED, H_PARKED, H_UNPINNED, H_OK]
PIN_LINE_RE = re.compile(r"^PIN (REQ-\d{3,})\b")
NO_REQUIREMENT = "no requirement"
UNMAPPED = "UNMAPPED"
ISSUE_LIMIT = 1000
GH_ISSUES_CMD = f"gh issue list --state all --limit {ISSUE_LIMIT} --json number,title,state,labels,body,createdAt,closedAt"
GH_RUNS_CMD = "gh run list --limit 10 --json databaseId,name,status,conclusion,createdAt,workflowName"
GH_JOBS_CMD = "gh run view <databaseId> --json jobs"
RELATES_LINE_RE = re.compile(r"^Relates-to:[ \t]*(.*?)[ \t]*$")
RELATES_REQS_RE = re.compile(r"^REQ-\d{3,}(?:[ \t]*,[ \t]*REQ-\d{3,})*$")
RELATES_SECTION_RE = re.compile(r"^section[ \t]+([^<\s].*)$")
STAGE_PATHS = ["spec/requirements", "work", "owner-questions", "evidence", "views/status-page.json"]
e = html.escape


def esc(v) -> str:
    return html.escape(str(v), quote=True)


# ---- reading the repo ------------------------------------------------------------------------------

def _fm(path: Path) -> dict | None:
    data, err = factory_lint.parse_frontmatter(path)
    return None if err else data


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def read_requirements(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "spec" / "requirements" / "REQ-*.md"))):
        d = _fm(Path(p)) or {}
        d.setdefault("id", Path(p).stem)
        out.append(d)
    return out


def read_works(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "work" / "W-*.md"))):
        d = _fm(Path(p)) or {}
        d.setdefault("id", Path(p).stem)
        out.append(d)
    return out


def read_findings(root: Path) -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(root / "knowledge" / "findings" / "*.json"))):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            d.setdefault("id", Path(p).stem)
            out.append(d)
    return out


def read_owner_questions(root: Path) -> tuple[list[dict], list[str]]:
    """(open questions, names of unreadable files). Answered ones are read and dropped."""
    open_qs: list[dict] = []
    bad: list[str] = []
    for p in sorted(glob.glob(str(root / "owner-questions" / "OQ-*.md"))):
        path = Path(p)
        data = _fm(path)
        if data is None or factory_lint.validate_data("owner-question", data, str(path)):
            bad.append(path.name)
            continue
        if data.get("status") == "open":
            open_qs.append(data)
    return open_qs, bad


def read_build_order(root: Path) -> list[dict] | None:
    p = root / "views" / "build-order.md"
    if not p.is_file():
        return None
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| REQ-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({"id": cells[0], "title": cells[1], "layer": cells[2], "risk": cells[3], "state": cells[4]})
    return rows


def read_workflow_jobs(root: Path) -> list[tuple[str, str, set[str]]]:
    """(workflow name, job display name, names a run may report for it)."""
    out = []
    wf_dir = root / ".github" / "workflows"
    for p in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            continue
        wf = data.get("name") if isinstance(data.get("name"), str) else p.stem
        for key, job in data["jobs"].items():
            name = job.get("name") if isinstance(job, dict) and isinstance(job.get("name"), str) else None
            if name and "${{" in name:
                name = name.split("${{")[0].strip() or None
            display = name or str(key)
            out.append((wf, display, {str(key), display}))
    return out


def recent_stage_changes(root: Path) -> list[str] | None:
    out = _git(root, "log", "-8", "--format=%h|%cs|%s", "--", *STAGE_PATHS)
    return None if out is None else [ln for ln in out.splitlines() if ln]


# ---- owner decisions (REQ-012) ---------------------------------------------------------------------

def rollup_status(statuses: list[str]) -> str:
    """No citing requirement -> 'no requirement'; otherwise the least-advanced status (STATUS_ORDER). A status that
    is not in the order counts as the least advanced, and is shown as written."""
    if not statuses:
        return NO_REQUIREMENT
    statuses = [s or "unknown" for s in statuses]  # a requirement with no status is shown as unknown, never blank
    return min(statuses, key=lambda x: STATUS_ORDER.index(x) if x in STATUS_ORDER else -1)


def _cell(text: str) -> str:
    return text.replace("\\|", "|")


def _od_title(decision: str) -> str:
    m = re.match(r"\*\*(.+?)\*\*", decision)
    if m:
        return m.group(1).strip()
    first = re.split(r"(?<=[.;])\s+", decision, maxsplit=1)[0]
    return first if len(first) <= 120 else first[:117] + "..."


def read_decisions(root: Path) -> tuple[list[dict], list[str]]:
    """(decisions, problems). One dict per well-formed decision: Factory OD rows (docs/spec/decisions.md) and project
    records (spec/decisions/*.md), each with the ids of the requirements citing it (spec_dupes.cites) and the
    rolled-up status. An OD row that is not exactly 5 cells is never rendered (its cells would be shifted): it is
    returned as a problem line instead."""
    src = spec_text.Source(root)
    reqs = spec_text.requirement_records(src)
    recs = spec_text.od_records(src) + spec_text.adr_records(src)
    out, problems = [], []
    known = {r.id.upper() for r in reqs + recs}
    for rec in recs:
        if rec.path == spec_text.OD_LOG and rec.data.get("cells") != spec_text.OD_CELLS:
            problems.append(f"{rec.id}: {rec.data.get('cells')} cells, expected {spec_text.OD_CELLS} "
                            f"(line {rec.data.get('line')} of {spec_text.OD_LOG}; write a literal pipe as \\|)")
            continue
        if rec.path == spec_text.OD_LOG:
            cells = [_cell(c) for c in spec_text.od_cells(rec.raw)] + [""] * 5
            row = {"id": rec.id, "date": cells[1], "title": _od_title(cells[2]), "words": cells[3], "changes": cells[4]}
        else:
            d = rec.data
            row = {"id": rec.id, "date": str(d.get("date") or "—"), "title": str(d.get("title") or rec.id),
                   "words": str(d.get("owner_words") or "—"), "changes": str(d.get("changes") or "—")}
        citing = [r for r in reqs if spec_dupes.covers(r, rec)]  # deliberate only; mentions omitted
        citing.sort(key=lambda r: spec_dupes.id_number(r.id))
        row["cited"] = ", ".join(r.id for r in citing) or "—"
        row["status"] = rollup_status([str(r.data.get("status") or "unknown") for r in citing])
        text = spec_dupes.relations_text(rec)
        why = spec_dupes.exemption(spec_dupes.parse_relations(text, known, rec.id)[0]) if text else None
        if not citing and why is not None:  # REQ-013 AC-3: every exemption is shown with its reason
            row["status"] = f"{NO_REQUIREMENT} (exempt: {why})"
        out.append(row)
    out.sort(key=lambda r: (r["id"].rsplit("-", 1)[0], spec_dupes.id_number(r["id"])))
    return out, problems


# ---- computed health (REQ-014 AC-5) ----------------------------------------------------------------

def evidence_results(root: Path) -> dict[str, "trace_check.Result"]:
    """requirement id -> trace_check's result (stale / unpinned / hard failures). Requirements whose status demands
    no evidence (Delivered-before-trace, Superseded) are absent."""
    reqs, _ = trace_check.load_requirements(root)
    works, _ = trace_check.load_work_items(root)
    allowed = trace_check.load_unpinned_list(root)
    return {r.id: trace_check.check_requirement(root, r, works, allowed) for r in reqs
            if r.status not in trace_check.NO_EVIDENCE_STATUSES}


def pin_failing(root: Path, amends: list[str]) -> set[str]:
    """Requirement ids with a failing confirmed_against pin (spec_dupes: missing, stale, orphan or malformed pin, or
    the amends rule asking for a new one)."""
    src = spec_text.Source(root)
    failures, _ = spec_dupes.check_pins(spec_text.load_records(src))
    return {m.group(1) for m in map(PIN_LINE_RE.match, failures + list(amends)) if m}


def health(rid: str, results: dict, pins: set[str], works: list[dict], parked: set[str]) -> str:
    """First match wins: Changed - needs re-check (stale evidence, an unusable ac_fp, or a failing pin), Blocked (a
    work item delivering it is blocked or lists blockers), Parked (a parked issue's Relates-to names it), Unpinned
    evidence (any of its evidence lacks ac_fp), else OK."""
    res = results.get(rid)
    if (res is not None and (res.stale or res.failures)) or rid in pins:
        return H_CHANGED
    if any(w.get("status") == "blocked" or w.get("blockers") for w in works):
        return H_BLOCKED
    if rid in parked:
        return H_PARKED
    if res is not None and res.unpinned:
        return H_UNPINNED
    return H_OK


# ---- CI gates (AC-6) -------------------------------------------------------------------------------

def _step_executed(step: dict) -> bool:
    return (step.get("conclusion") or "") not in ("", "skipped")


def _job_matches(run_name: str, names: set[str]) -> bool:
    return any(run_name == n or run_name.startswith(n + " (") for n in names)


def _completed(run: dict) -> bool:
    """A run that has not finished says nothing about which steps ran."""
    if "status" in run and run.get("status") != "completed":
        return False
    return bool(run.get("conclusion"))


def classify_gates(root: Path, all_runs: list[dict] | None) -> dict:
    """Step-level gates. Each entry of 'gates' is (label, kind, workflow):
        (`<job> / <step>`, 'skipped-every-time')  a step skipped in every completed run where its job ran
        (`<job>`, 'skipped-every-time')           a job with no step detail that was skipped in every run
        (`<job>`, 'never-run')                    a workflow job with no runs
    A step that executed at least once is never listed. Steps are keyed by name plus occurrence within the
    job, so two steps with the same name are judged separately (the second is labelled `<name> (#2)`).
    Runs that have not completed are ignored."""
    if all_runs is None:
        return {"state": "unmeasured", "reason": "no runs file", "gates": []}
    runs = [r for r in all_runs if _completed(r)]
    not_completed = len(all_runs) - len(runs)
    if all_runs and not runs:
        return {"state": "unmeasured", "reason": "no completed runs in the window", "gates": []}
    wf_jobs = read_workflow_jobs(root)
    detailed = [r for r in runs if isinstance(r.get("jobs"), list)]
    if runs and not detailed:
        return {"state": "unmeasured", "reason": "runs carry no job detail", "gates": []}
    dates = sorted((r.get("createdAt") or "")[:10] for r in runs if r.get("createdAt"))
    window = (len(runs), dates[0] if dates else "", dates[-1] if dates else "")
    # (workflow, job) -> {"steps": {(step name, occurrence): [executed?]}, "jobs": [executed?] for jobs without steps}
    seen: dict[tuple[str, str], dict] = {(wf, disp): {"steps": {}, "jobs": []} for wf, disp, _n in wf_jobs}
    for r in detailed:
        wf = r.get("workflowName") or r.get("name") or ""
        for job in r["jobs"]:
            jname = job.get("name") or ""
            key = next(((w, d) for w, d, names in wf_jobs if w == wf and _job_matches(jname, names)), (wf, jname))
            rec = seen.setdefault(key, {"steps": {}, "jobs": []})
            steps = job.get("steps") or []
            if steps:
                occurrence: dict[str, int] = {}
                for s in steps:
                    nm = s.get("name") or ""
                    occurrence[nm] = occurrence.get(nm, 0) + 1
                    rec["steps"].setdefault((nm, occurrence[nm]), []).append(_step_executed(s))
            else:
                rec["jobs"].append((job.get("conclusion") or "") not in ("", "skipped"))
    wf_no_detail = {(r.get("workflowName") or r.get("name") or "") for r in runs if not isinstance(r.get("jobs"), list)}
    gates = []
    for (wf, name), rec in sorted(seen.items(), key=lambda kv: kv[0][1]):
        if not rec["steps"] and not rec["jobs"]:
            if wf not in wf_no_detail:
                gates.append((name, "never-run", wf))
            continue
        for (step, nth), ran in rec["steps"].items():
            if not any(ran):
                label = step if nth == 1 else f"{step} (#{nth})"
                gates.append((f"{name} / {label}", "skipped-every-time", wf))
        if rec["jobs"] and not any(rec["jobs"]):
            gates.append((name, "skipped-every-time", wf))
    gates.sort(key=lambda g: g[0])
    return {"state": "measured", "gates": gates, "window": window, "no_detail": len(runs) - len(detailed),
            "not_completed": not_completed}


# ---- issues and findings (AC-4) --------------------------------------------------------------------

def relates_to(body: str | None) -> str:
    for line in (body or "").splitlines():
        m = RELATES_LINE_RE.match(line.strip())
        if not m:
            continue
        value = m.group(1)
        if RELATES_REQS_RE.match(value):
            return ", ".join(x.strip() for x in value.split(","))
        s = RELATES_SECTION_RE.match(value)
        if s:
            return f"section {s.group(1).strip()}"
    return UNMAPPED


def issue_status(issue: dict) -> str:
    if str(issue.get("state", "")).upper() == "CLOSED":
        return "closed"
    names = {(lb.get("name") if isinstance(lb, dict) else str(lb)) for lb in issue.get("labels") or []}
    return "parked" if "parked" in names else "deferred" if "deferred" in names else "open"


# ---- html helpers ----------------------------------------------------------------------------------

def unmeasured(cmd: str, what: str = "") -> str:
    return (f'<p class="muted"><span class="pill">unmeasured</span> {esc(what)} '
            f'Measure it with <code>{esc(cmd)}</code>.</p>')


def ul(items: list[str], empty: str) -> str:
    return "<ul>" + "".join(items) + "</ul>" if items else f'<p class="muted">{esc(empty)}</p>'


def table(cols: list[tuple[str, str]], data: list[dict], tid: str) -> str:
    th = "".join(f'<th scope="col"><button type="button" data-k="{k}">{esc(lbl)}</button></th>' for k, lbl in cols)
    tr = "".join("<tr>" + "".join(f'<td data-k="{k}">{esc(d[k])}</td>' for k, _ in cols) + "</tr>" for d in data)
    return f'<div class="tw"><table id="{tid}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def filters(qid: str, label: str, selects: list[tuple[str, str, list[str]]]) -> str:
    sel = "".join(
        f'<select id="{sid}" aria-label="{esc(lbl)}"><option value="">{esc(lbl)}</option>'
        + "".join(f"<option>{esc(o)}</option>" for o in opts) + "</select>"
        for sid, lbl, opts in selects)
    return (f'<div class="flt"><input id="{qid}" type="search" placeholder="{esc(label)}" '
            f'aria-label="{esc(label)}">{sel}</div>')


def sec(title: str, body: str, count: str, open_: bool = False) -> str:
    sid = re.sub(r"[^a-z]+", "-", title.lower()).strip("-")
    return (f'<details class="sec" id="sec-{sid}"{" open" if open_ else ""}><summary><span>{esc(title)}</span>'
            f'<span class="ct">{esc(count)}</span></summary><div class="bd">{body}</div></details>')


def tile(key: str, value: str, label: str) -> str:
    return f'<div class="tile" data-tile="{key}"><b>{esc(value)}</b><span>{esc(label)}</span></div>'


CSS = """
/* layout: stamp header, then stacked expandable sections; each table scrolls inside its own box */
:root{--bg:#f6f7f5;--panel:#ffffff;--fg:#1d2320;--muted:#5d6862;--line:#dfe3df;--accent:#2f6f5e;--ok:#2e7d4f;--warn:#a86a00;--bad:#b3261e;--chip:#eef2ef;--sans:"IBM Plex Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121614;--panel:#1a1f1c;--fg:#e4e9e6;--muted:#9aa6a0;--line:#2c3430;--accent:#7cc4ad;--ok:#6fcf97;--warn:#f2b54a;--bad:#f28b82;--chip:#232a26;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121614;--panel:#1a1f1c;--fg:#e4e9e6;--muted:#9aa6a0;--line:#2c3430;--accent:#7cc4ad;--ok:#6fcf97;--warn:#f2b54a;--bad:#f28b82;--chip:#232a26;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.5}
.wrap{max-width:1100px;margin:0 auto;padding-inline:16px;padding-block:20px 48px;display:grid;gap:14px}
h1{font-size:1.5rem;margin:0;text-wrap:balance}.muted{color:var(--muted)}code,.mono{font-family:var(--mono);font-size:.9em}
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.tile{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.tile b{display:block;font-size:1.4rem;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}
.sec{background:var(--panel);border:1px solid var(--line);border-radius:8px}
.sec>summary{cursor:pointer;padding:10px 14px;display:flex;justify-content:space-between;gap:12px;font-weight:600}
.sec>summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ct{color:var(--muted);font-weight:400;font-variant-numeric:tabular-nums}.bd{padding:0 14px 14px;min-width:0;overflow-wrap:anywhere}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th button{all:unset;cursor:pointer;font-weight:600}th button:focus-visible{outline:2px solid var(--accent)}
th button[aria-sort=ascending]::after{content:" \\25B2"}th button[aria-sort=descending]::after{content:" \\25BC"}
td[data-k=status]{white-space:nowrap}.flt{display:flex;flex-wrap:wrap;gap:8px;margin-block:8px}
input,select{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);max-width:100%}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--chip);font-size:.8rem}
li{margin-block:4px}
""".strip()

JS = """
function cmpCells(x, y) {
  var num = /^-?\\d+(\\.\\d+)?$/;
  if (num.test(x) && num.test(y)) { return parseFloat(x) - parseFloat(y); }
  return x.localeCompare(y, undefined, { numeric: true });
}
function wireTable(tid, qid, selects) {
  var t = document.getElementById(tid);
  if (!t) { return; }
  var body = t.tBodies[0];
  t.querySelectorAll("th button").forEach(function (b, ix) {
    b.addEventListener("click", function () {
      var dir = b.getAttribute("aria-sort") === "ascending" ? -1 : 1;
      t.querySelectorAll("th button").forEach(function (x) { x.removeAttribute("aria-sort"); });
      b.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
      var rows = Array.from(body.rows);
      rows.sort(function (a, c) { return cmpCells(a.cells[ix].textContent, c.cells[ix].textContent) * dir; });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
  var q = document.getElementById(qid);
  function apply() {
    var s = q ? (q.value || "").toLowerCase() : "";
    Array.from(body.rows).forEach(function (r) {
      var ok = r.textContent.toLowerCase().indexOf(s) >= 0;
      selects.forEach(function (pair) {
        var v = document.getElementById(pair[0]).value;
        if (v && pair[1] === "cov") {
          var st = r.querySelector('td[data-k="status"]');
          var t = st ? st.textContent : "";
          var kind = t === "no requirement" ? "not covered" : t.indexOf("no requirement (exempt") === 0 ? "exempt" : "covered";
          ok = ok && kind === v;
        } else if (v) { var c = r.querySelector('td[data-k="' + pair[1] + '"]'); ok = ok && !!c && c.textContent === v; }
      });
      r.hidden = !ok;
    });
  }
  if (q) { q.addEventListener("input", apply); }
  selects.forEach(function (pair) { document.getElementById(pair[0]).addEventListener("change", apply); });
}
wireTable("t-req", "q-req", [["f-req-status", "status"], ["f-req-layer", "layer"], ["f-req-health", "health"], ["f-req-release", "release"]__SECTION__]);
wireTable("t-od", "q-od", [["f-od-cov", "cov"], ["f-od-status", "status"]]);
wireTable("t-next", null, []);
wireTable("t-iss", "q-iss", [["f-iss-type", "type"], ["f-iss-status", "status"]]);
""".strip()


# ---- the page --------------------------------------------------------------------------------------

def render(root: Path, issues: list[dict] | None, runs: list[dict] | None, *, now: str | None = None,
           sha: str | None = None, title: str | None = None) -> tuple[str, dict]:
    root = Path(root)
    title = title or f"{root.resolve().name} Status"
    now = now or datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if sha is None:
        out = _git(root, "rev-parse", "--short", "HEAD")
        sha = out.strip() if out and out.strip() else None
    sha_html = esc(sha) if sha else "unmeasured</span> <span class=\"muted\">(git rev-parse --short HEAD)"

    reqs, works, findings = read_requirements(root), read_works(root), read_findings(root)
    w_of: dict[str, list[dict]] = {}
    for w in works:
        for rid in w.get("requirement_ids") or []:
            w_of.setdefault(rid, []).append(w)
    by_req = {r["id"]: r for r in reqs}
    has_section = any(r.get("section") for r in reqs)

    rows = []
    for r in reqs:
        ws = w_of.get(r["id"], [])
        rows.append({
            "id": r["id"], "title": r.get("title", ""), "section": r.get("section") or "—",
            "layer": r.get("layer") or "unset", "status": r.get("status", ""),
            "work": ", ".join(w["id"] for w in ws) or "none",
            "wstatus": ", ".join(str(w.get("status")) for w in ws) or "—",
            "tier": ", ".join(str(w.get("tier")) for w in ws) or "—",
            "deps": ", ".join(r.get("depends_on") or []) or "—",
            "acs": len(r.get("acceptance_criteria") or []),
            # REQ-016 AC-4: the release that delivered it (or unreleased) and the pull request(s) that merged its
            # done work items; a done work item naming no `PR #n` says so, never a blank
            "release": trace_check.release_label_of(r),
            "review": ", ".join(dict.fromkeys(
                trace_check.review_cell(w) or f"{w.get('id')}: no PR named" for w in ws if w.get("status") == "done"))
            or "—",
        })
    # headline (REQ-014): "done" = verified + delivered-before-trace, shown split; Superseded is out of the total
    n_dbt = sum(1 for r in rows if r["status"] == "Delivered-before-trace")
    n_sup = sum(1 for r in rows if r["status"] == "Superseded")
    n_done = sum(1 for r in rows if r["status"] in DONE)
    n_total = len(rows) - n_sup
    done_word = "verified" if not n_dbt else f"done ({n_done - n_dbt} verified, {n_dbt} delivered before trace)"
    decisions, dec_problems = read_decisions(root)
    n_dec_exempt = sum(1 for d in decisions if d["status"].startswith(NO_REQUIREMENT + " (exempt"))
    n_dec_cov = sum(1 for d in decisions if not d["status"].startswith(NO_REQUIREMENT))
    dec_count = (f"{len(decisions)} decisions · {n_dec_cov} covered · "
                 f"{len(decisions) - n_dec_cov - n_dec_exempt} not covered"
                 + (f" · {n_dec_exempt} exempt (no-requirement)" if n_dec_exempt else ""))
    if decisions:
        dec_body = (filters("q-od", "Filter decisions", [
            ("f-od-cov", "Covered or not", ["covered", "not covered"] + (["exempt"] if n_dec_exempt else [])),
            ("f-od-status", "Any status", sorted({d["status"] for d in decisions}))])
            + table([("id", "ID"), ("date", "Date"), ("title", "Decision"), ("words", "Owner's words"),
                     ("changes", "Changes"), ("cited", "Cited by"), ("status", "Status")], decisions, "t-od"))
    else:
        dec_body = '<p class="muted">No decision records (docs/spec/decisions.md or spec/decisions/*.md).</p>'
    if dec_problems:
        dec_body = ('<p class="muted" data-problems="decisions"><span class="pill">Data problems</span> '
                    + esc("; ".join(dec_problems)) + " — not shown in the table; fix the row, "
                    "<code>python tools/spec_dupes.py .</code> reports it.</p>") + dec_body
        dec_count += f" · {len(dec_problems)} data problems"
    # coverage (REQ-013 AC-3/AC-4/AC-6): the same counts spec_dupes prints, from the one definition
    cov = spec_dupes.trace_report(root)
    n_cov_dec = len(cov["decisions_uncovered"])
    n_cov_sec = "n/a" if cov["sections_uncovered"] is None else len(cov["sections_uncovered"])
    cov_text = (f"COVERAGE ({cov['mode']} mode, {'blocking' if cov['mode'] == 'block' else 'not blocking'}): "
                f"{n_cov_dec} decisions need a requirement and have none"
                + (f" ({', '.join(cov['decisions_uncovered'])})" if n_cov_dec else "")
                + f"; {n_cov_sec} requirement sections of the master spec are cited by no requirement"
                + (f" ({', '.join('§' + str(n) for n in cov['sections_uncovered'])})"
                   if cov["sections_uncovered"] else "")
                + ". Measured by python tools/spec_dupes.py .")
    dec_body = (f'<p class="muted" data-coverage="{n_cov_dec}/{n_cov_sec}/{esc(cov["mode"])}">'
                f'<span class="pill">coverage</span> {esc(cov_text)}</p>') + dec_body
    dec_count += f" · coverage gaps: {n_cov_dec} decisions, {n_cov_sec} spec sections"
    blocked_works = [w for w in works if w.get("status") == "blocked"]
    open_qs, bad_qs = read_owner_questions(root)

    # issues + findings rows
    iss_rows: list[dict] = []
    n_unmapped_issues = n_open = n_parked = 0
    parked_issues: list[dict] = []
    if issues is not None:
        for i in sorted(issues, key=lambda x: x.get("number", 0)):
            rel = relates_to(i.get("body"))
            st = issue_status(i)
            n_unmapped_issues += rel == UNMAPPED
            n_open += str(i.get("state", "")).upper() != "CLOSED"
            row = {"id": f"#{i.get('number')}", "type": "issue", "title": i.get("title", ""), "rel": rel,
                   "status": st, "opened": (i.get("createdAt") or "")[:10]}
            iss_rows.append(row)
            if st == "parked":
                n_parked += 1
                parked_issues.append(row)
    n_unmapped_findings = 0
    for f in findings:
        wm = re.search(r"W-\d{3,}", (f.get("first_seen") or {}).get("where", "") or "")
        target = next((w for w in works if wm and w["id"] == wm.group(0)), None)
        rel = ", ".join(target.get("requirement_ids") or []) if target else ""
        rel = rel or UNMAPPED
        n_unmapped_findings += rel == UNMAPPED
        text = str(f.get("class", ""))
        iss_rows.append({"id": f["id"], "type": "finding", "title": text if len(text) <= 160 else text[:157] + "...",
                         "rel": rel, "status": (f.get("detection") or {}).get("status") or "unmeasured",
                         "opened": (f.get("first_seen") or {}).get("date", "")})
    n_unguarded = sum(1 for f in findings if (f.get("detection") or {}).get("status") == "unguarded")

    # computed health beside the stored status (REQ-014 AC-5)
    ev_results = evidence_results(root)
    pins = pin_failing(root, cov["amends"])
    parked_reqs = {rid for p in parked_issues for rid in re.findall(r"REQ-\d{3,}", p["rel"])}
    for row in rows:
        row["health"] = health(row["id"], ev_results, pins, w_of.get(row["id"], []), parked_reqs)
    n_health = {h: sum(1 for r in rows if r["health"] == h) for h in HEALTHS}

    gates = classify_gates(root, runs)
    n_skipped = sum(1 for g in gates["gates"] if g[1] == "skipped-every-time")
    n_never = sum(1 for g in gates["gates"] if g[1] == "never-run")
    build = read_build_order(root)
    recent = recent_stage_changes(root)

    # -- blockers
    blockers = []
    for w in blocked_works:
        blockers.append(f'<li>{esc(w["id"])}: {esc(w.get("title", ""))} — {esc(w.get("next_action", ""))}</li>')
    for w in works:
        if w.get("status") != "blocked" and w.get("blockers"):
            blockers.append(f'<li>{esc(w["id"])}: {esc("; ".join(str(b) for b in w["blockers"]))}</li>')
    for p in parked_issues:
        blockers.append(f'<li>{esc(p["id"])} (parked): {esc(p["title"])}</li>')
    n_blockers = len(blockers)
    blockers_body = ul(blockers, "No blocked work items or parked issues.")
    if issues is None:
        blockers_body += unmeasured(GH_ISSUES_CMD, "Parked issues not counted.")

    # -- dependencies
    deps = []
    for r in reqs:
        for d in r.get("depends_on") or []:
            state = by_req[d].get("status", "") if d in by_req else "unknown requirement"
            deps.append(f"<li>{esc(r['id'])} needs {esc(d)} ({esc(state)})</li>")

    # -- needs you
    needs = [f'<li data-oq="{esc(q["id"])}"><b>{esc(q["id"])}</b> (asked {esc(q.get("asked", ""))}): {esc(q["question"])}'
             f'<br>Recommendation: {esc(q["recommendation"])}<br><span class="muted">Spec basis: {esc(q["spec_basis"])}</span></li>'
             for q in open_qs]
    needs_body = ul(needs, "Nothing is waiting on you (owner-questions/ holds no open question).")
    if bad_qs:
        needs_body += (f'<p class="muted"><span class="pill">{len(bad_qs)} unreadable</span> '
                       f'{esc(", ".join(bad_qs))} — run <code>python tools/factory_lint.py .</code></p>')

    # -- build next
    if build is None:
        build_body, build_count = unmeasured("python tools/build_order.py .", "views/build-order.md is missing."), "unmeasured"
    else:
        n_next = sum(1 for b in build if b["state"] == "next")
        build_count = f"{n_next} next"
        build_body = table([("id", "ID"), ("title", "Requirement"), ("layer", "Layer"), ("risk", "Risk"),
                            ("state", "State")], build, "t-next") if build else '<p class="muted">Nothing left to build.</p>'

    # -- issues and findings
    at_limit = issues is not None and len(issues) >= ISSUE_LIMIT
    issues_label = f"at least {len(issues)} issues (fetch limit reached)" if at_limit else (
        f"{len(issues)} issues" if issues is not None else "")
    if issues is None:
        iss_note = unmeasured(GH_ISSUES_CMD, "Issues were not supplied; only findings are listed.")
        iss_count = f"issues unmeasured · {len(findings)} findings"
    else:
        iss_note = ""
        iss_count = (f"{issues_label} · {len(findings)} findings · {n_unmapped_issues} issues unmapped"
                     f" · {n_unmapped_findings} findings unmapped")
    statuses = sorted({r["status"] for r in iss_rows})
    iss_body = (iss_note + filters("q-iss", "Filter issues and findings", [
        ("f-iss-type", "Any type", ["issue", "finding"]), ("f-iss-status", "Any status", statuses)])
        + table([("id", "ID"), ("type", "Type"), ("title", "Title"), ("rel", "Relates to"), ("status", "Status"),
                 ("opened", "Opened")], iss_rows, "t-iss"))

    # -- never-run gates
    if gates["state"] == "unmeasured":
        gates_body = unmeasured(f"{GH_RUNS_CMD} and, for each run, {GH_JOBS_CMD}",
                                f"CI history has no per-job step detail ({gates['reason']}).")
        gates_count = "unmeasured"
    else:
        n_runs, first, last = gates["window"]
        items = []
        for gate, kind, wf in gates["gates"]:
            words = "never ran (skipped every time)" if kind == "skipped-every-time" else "never run"
            items.append(f'<li data-gate="{esc(gate)}" data-state="{kind}" data-workflow="{esc(wf)}">'
                         f'<b>{esc(gate)}</b>: {words}</li>')
        gates_body = f'<p class="muted">Window: {n_runs} runs ({esc(first)} to {esc(last)}).</p>'
        gates_body += ul(items, "Every gate executed at least one step in the window.")
        if gates.get("not_completed"):
            gates_body += (f'<p class="muted">{gates["not_completed"]} runs had not completed and were ignored.</p>')
        if gates["no_detail"]:
            gates_body += unmeasured(GH_JOBS_CMD, f"{gates['no_detail']} runs had no job detail and were not counted per job.")
        gates_count = str(len(gates["gates"]))

    # -- recent stage changes
    if recent is None:
        recent_body, recent_count = unmeasured("git log -8 -- spec/requirements work owner-questions evidence"), "unmeasured"
    else:
        recent_body = ul([f"<li>{esc(l.replace('|', ' · '))}</li>" for l in recent], "No stage change recorded yet.")
        recent_count = str(len(recent))

    # -- overall tiles
    def n(v):
        return str(v) if issues is not None else "unmeasured"
    tiles = "".join([
        tile("verified", f"{n_done}/{n_total}", "requirements " + done_word),
        tile("delivered-before-trace", str(n_dbt), "delivered before trace (counted as done)"),
        tile("superseded", str(n_sup), "superseded (not in the total)"),
        tile("decisions", str(len(decisions)), "owner decisions"),
        tile("decisions-covered", str(n_dec_cov), "decisions covered by a requirement"),
        tile("decisions-uncovered", str(len(decisions) - n_dec_cov - n_dec_exempt), "decisions not covered"),
        tile("needs-you", str(len(open_qs)), "need you"),
        tile("blocked", str(len(blocked_works)), "blocked work items"),
        tile("parked", n(n_parked), "parked issues"),
        tile("open-issues", n(n_open), "open issues"),
        tile("unmapped", n(n_unmapped_issues), "issues unmapped"),
        tile("unguarded", str(n_unguarded), "unguarded findings"),
    ] + [tile("health-" + re.sub(r"[^a-z]+", "-", h.lower()).strip("-"), str(n_health[h]), f"health: {h}")
         for h in HEALTHS])
    overall = f'<div class="strip">{tiles}</div>'
    if issues is None:
        overall += unmeasured(GH_ISSUES_CMD, "Health 'Parked' comes from parked issues; none were supplied, so no "
                                             "requirement can show Parked.")
    if at_limit:
        overall += (f'<p class="muted"><span class="pill">at least {len(issues)} issues (fetch limit reached)</span> '
                    f'counts of issues are lower bounds.</p>')
    if issues is None:
        overall += unmeasured(GH_ISSUES_CMD, "Issue counts need the issues file.")

    req_cols = [("id", "ID"), ("title", "Requirement")] + ([("section", "Section")] if has_section else []) + [
        ("layer", "Layer"), ("status", "Status"), ("health", "Health"), ("work", "Work item"),
        ("wstatus", "Work status"), ("tier", "Tier"), ("deps", "Depends on"), ("acs", "ACs"), ("release", "Release"),
        ("review", "Review PR")]
    req_selects = [
        ("f-req-status", "Any status", sorted({r["status"] for r in rows})),
        ("f-req-layer", "Any layer", sorted({r["layer"] for r in rows})),
        ("f-req-health", "Any health", HEALTHS),
        ("f-req-release", "Any release", sorted({r["release"] for r in rows}))]
    if has_section:
        req_selects.append(("f-req-section", "Any section", sorted({r["section"] for r in rows if r["section"] != "—"})))
    req_body = filters("q-req", "Filter requirements", req_selects) + table(req_cols, rows, "t-req")

    js = JS.replace("__SECTION__", ', ["f-req-section", "section"]' if has_section else "")
    page = (
        f"<title>{esc(title)}</title>\n<style>\n{CSS}\n</style>\n"
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@400;600&display=swap">\n'
        f'<div class="wrap">\n<header><h1>{esc(title)}</h1><p class="muted">Generated from the repo at '
        f'<span class="mono" id="stamp-sha">{sha_html}</span> · updated <span id="stamp-time">{esc(now)}</span></p></header>\n'
        + "\n".join([
            sec("Overall", overall, f"{n_done}/{n_total} {done_word}", True),
            sec("Needs you", needs_body, str(len(open_qs)), True),
            sec("Requirements", req_body, f"{n_done} of {n_total} {done_word}", True),
            sec("Owner decisions", dec_body, dec_count),
            sec("Blockers", blockers_body, str(n_blockers)),
            sec("Dependencies", ul(deps, "No requirement depends on another."), str(len(deps))),
            sec("Build next", build_body, build_count),
            sec("Issues and findings", iss_body, iss_count),
            sec("Never-run gates", gates_body, gates_count),
            sec("Recent stage changes", recent_body, recent_count),
        ])
        + f"\n</div>\n<script>\n{js}\n</script>\n")
    summary = {"requirements": len(rows), "verified": n_done, "delivered_before_trace": n_dbt,
               "superseded": n_sup, "decisions": len(decisions),
               "decisions_covered": n_dec_cov, "issues": len(issues) if issues is not None else None,
               "findings": len(findings), "unmapped_issues": n_unmapped_issues, "unmapped_findings": n_unmapped_findings,
               "unguarded": n_unguarded, "needs_you": len(open_qs), "blocked": len(blocked_works),
               "never_run": n_never, "skipped_every_time": n_skipped, "health": n_health}
    return page, summary


# ---- fetching live inputs (the only impure part; render() never calls it) ---------------------------

def _gh_json(args: list[str], root: Path):
    cmd = "gh " + " ".join(args)
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(root))
    except FileNotFoundError:
        raise SystemExit(f"build_status_page.py: `{cmd}` could not run: the gh command is not installed or not on PATH")
    if r.returncode != 0:
        raise SystemExit(f"build_status_page.py: `{cmd}` failed: {(r.stderr or '').strip()}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"build_status_page.py: `{cmd}` did not return JSON ({exc})")


def fetch_gh_inputs(root: Path, run_limit: int = 10) -> tuple[list[dict], list[dict]]:
    issues = _gh_json(["issue", "list", "--state", "all", "--limit", str(ISSUE_LIMIT), "--json",
                       "number,title,state,labels,body,createdAt,closedAt"], root)
    runs = _gh_json(["run", "list", "--limit", str(run_limit), "--json",
                     "databaseId,name,status,conclusion,createdAt,workflowName"], root)
    for run in runs:
        run["jobs"] = _gh_json(["run", "view", str(run["databaseId"]), "--json", "jobs"], root).get("jobs", [])
    return issues, runs


def _load_json(path: str | None):
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the project status page from repo data, issues and CI runs.")
    ap.add_argument("root")
    ap.add_argument("--issues", help="gh issue list --state all --json ... output")
    ap.add_argument("--runs", help="gh run list output, each run carrying a jobs list")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--now", help="generation stamp text (default: the system clock)")
    ap.add_argument("--sha", help="git sha text (default: git rev-parse --short HEAD)")
    ap.add_argument("--fetch", action="store_true", help="run the gh commands for --issues and --runs first")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.fetch:
        issues, runs = fetch_gh_inputs(root)
    else:
        issues, runs = _load_json(a.issues), _load_json(a.runs)
    page, s = render(root, issues, runs, now=a.now, sha=a.sha, title=a.title)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    issue_txt = "issues unmeasured" if s["issues"] is None else f"{s['issues']} issues ({s['unmapped_issues']} unmapped)"
    print(f"wrote {out}: {s['requirements']} requirements ({s['verified']} verified), {issue_txt}, "
          f"{s['findings']} findings ({s['unguarded']} unguarded), {s['needs_you']} need you, "
          f"{s['blocked']} blocked work items, {s['never_run'] + s['skipped_every_time']} never-run gates "
          f"({s['never_run']} never run, {s['skipped_every_time']} skipped every time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
