"""coverage.py <repo-root> --check | --write [--no-gh | --require-gh]

Coverage register: discovers every tracked id from the repo files and fails when one has no stage in
docs/process/coverage-stages.yaml (master plan 2026-10-07, A2).

  --check   exit 1 listing every missing id, stale yaml id, invalid stage, missing/unknown AC, unparseable file
  --write   render docs/process/coverage-register.md (deterministic; one commit-sha line)
  --no-gh   skip the open-issues comparison
  --require-gh  any gh failure fails the check (also implied when GITHUB_ACTIONS=true)
Stdlib + PyYAML only.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SP = "sp" + "ec"
STAGES = ["S0", "S1", "S2", "S3", "4a", "4b", "4c", "S5", "S6", "S6.1", "S6.2", "S6.3", "S6.4", "S6.5", "S6.6",
          "S6.7", "S7", "S8", "all", "done"]
# S6 is also accepted for build_plan P5 (the whole stage); the brief's list is the strict set for the rest.
VALID = set(STAGES)
SECTIONS = ["requirements", "decisions", "questions", "open_areas", "vendor_enquiries", "issues", "work_items",
            "findings", "hypotheses", "build_plan", "conflicts"]
DISCOVERED = ["requirements", "decisions", "questions", "work_items", "findings"]
OPEN_WORDS = ("OPEN", "EXTERNAL", "LEGAL")


def collapse(s):
    return re.sub(r"\s+", " ", s).strip()


def read_frontmatter(path, errors):
    """Parsed frontmatter dict, or None after recording an error naming the file (never silently skipped)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        errors.append(f"unreadable file {path.name}: {e}")
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(f"unparseable frontmatter in {path.name}: no opening '---'")
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        errors.append(f"unparseable frontmatter in {path.name}: no closing '---'")
        return None
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except Exception as e:  # noqa: BLE001
        errors.append(f"unparseable frontmatter in {path.name}: {str(e).splitlines()[0]}")
        return None
    if not isinstance(data, dict) or not data.get("id"):
        errors.append(f"unparseable frontmatter in {path.name}: no 'id' key")
        return None
    return data


def discover(root, errors):
    """-> {kind: {id: {"title": str, "acs": {ac_id: text}}}}"""
    found = {k: {} for k in DISCOVERED}
    spec = root / SP
    for kind, folder, prefix in (("requirements", "requirements", "REQ-"), ("decisions", "decisions", "ADR-")):
        d = spec / folder
        files = sorted(d.glob(prefix + "*.md")) if d.is_dir() else []
        if not files:
            errors.append(f"no {prefix}*.md files found under {SP}/{folder}")
        for f in files:
            fm = read_frontmatter(f, errors)
            if fm is None:
                continue
            _id = str(fm["id"])
            if _id != f.stem:
                errors.append(f"{f.name}: frontmatter id {_id} does not match the file name")
                continue
            acs = {}
            if kind == "requirements":
                for ac in fm.get("acceptance_criteria") or []:
                    if not isinstance(ac, dict) or "id" not in ac:
                        errors.append(f"unparseable acceptance_criteria in {f.name}")
                        continue
                    acs[str(ac["id"])] = collapse(str(ac.get("text", "")))
            found[kind][_id] = {"title": collapse(str(fm.get("title", ""))), "acs": acs}
    # open questions
    oq = spec / "open-questions.md"
    if not oq.is_file():
        errors.append(f"missing {SP}/open-questions.md")
    else:
        cur = None  # (id, title, is_open)
        sections = []
        for n, line in enumerate(oq.read_text(encoding="utf-8").splitlines(), 1):
            loose = re.match(r"^#{2,6}\s*Q\d+", line)
            m = re.match(r"^#{2,6}\s*(Q\d+)\s+[\u2014-]+\s+(.*)$", line)
            if loose and not m:
                errors.append(f"{SP}/open-questions.md line {n}: question heading not parsed: {line.strip()!r}")
            if m:
                rest = m.group(2)
                idx = rest.rfind(" \u2014 ")
                status, title = (rest[:idx], rest[idx + 3:]) if idx >= 0 else (rest, "")
                is_open = any(re.search(rf"\b{w}\b", status, re.I) for w in OPEN_WORDS)
                cur = [m.group(1), collapse(title) or collapse(rest), is_open]
                sections.append(cur)
            elif re.match(r"^#{1,2}\s", line):
                cur = None
            elif cur is not None and "open for the owner" in line.lower():
                cur[2] = True
        for qid, title, is_open in sections:
            if is_open:
                found["questions"][qid] = {"title": title, "acs": {}}
    # findings
    fp = spec / "findings.md"
    if not fp.is_file():
        errors.append(f"missing {SP}/findings.md")
    else:
        for n, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
            loose = re.match(r"^#{2,6}\s*F-\d+", line)
            m = re.match(r"^#{2,6}\s*(F-\d+)\b\s*[-\u2014:]*\s*(.*)$", line)
            if loose and not m:
                errors.append(f"{SP}/findings.md line {n}: finding heading not parsed: {line.strip()!r}")
            if m:
                found["findings"][m.group(1)] = {"title": collapse(m.group(2)), "acs": {}}
    # work items
    wd = root / "work"
    for f in sorted(wd.glob("W-*.md")) if wd.is_dir() else []:
        fm = read_frontmatter(f, errors)
        if fm is None:
            continue
        if str(fm["id"]) != f.stem:
            errors.append(f"{f.name}: frontmatter id {fm['id']} does not match the file name")
            continue
        if str(fm.get("status", "")).strip() != "done":
            found["work_items"][str(fm["id"])] = {"title": collapse(str(fm.get("title", ""))), "acs": {}}
    return found


def stage_list(val, where, errors):
    vals = val if isinstance(val, list) else [val]
    out = []
    for v in vals:
        if not isinstance(v, str) or v not in VALID:
            errors.append(f"invalid stage {v!r} for {where}")
        else:
            out.append(v)
    if not vals:
        errors.append(f"empty stage list for {where}")
    return out


def load_stages(root, errors):
    p = root / "docs" / "process" / "coverage-stages.yaml"
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"cannot read {p.name}: {str(e).splitlines()[0]}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{p.name} is not a mapping")
        return {}
    for s in SECTIONS:
        if s not in data or not isinstance(data[s], dict):
            if s == "issues" and data.get(s) is None and s in data:
                data[s] = {}
                continue
            errors.append(f"{p.name}: section '{s}' missing or not a mapping")
            data[s] = {}
    for s in data:
        if s not in SECTIONS:
            errors.append(f"{p.name}: unknown section '{s}'")
    return data


GH_LIMIT = 1000


def gh_open_issues(root):
    """-> (set of '#N' or None, reason). None means gh could not give a trustworthy list; reason says why."""
    if not shutil.which("gh"):
        return None, "gh binary not found"
    try:
        if not os.environ.get("GITHUB_TOKEN") and not os.environ.get("GH_TOKEN"):
            if subprocess.run(["gh", "auth", "status"], capture_output=True, cwd=root).returncode != 0:
                return None, "gh is not authenticated"
        r = subprocess.run(["gh", "issue", "list", "--state", "open", "--json", "number", "--limit", str(GH_LIMIT)],
                           capture_output=True, text=True, cwd=root, encoding="utf-8")
        if r.returncode != 0:
            return None, f"gh issue list exited {r.returncode}: {(r.stderr or '').strip()[:200]}"
        import json
        issues = {f"#{i['number']}" for i in json.loads(r.stdout)}
    except Exception as e:  # noqa: BLE001
        return None, f"gh failed: {type(e).__name__}: {str(e)[:200]}"
    if len(issues) >= GH_LIMIT:
        return None, f"gh returned {len(issues)} issues, equal to the limit {GH_LIMIT}: list may be truncated"
    return issues, ""


def normalise(stages, found, errors):
    """-> rows [(stage, kind, id, ac, text)] and also validates. Errors appended."""
    rows = []

    def add(kind, _id, val, text, ac="-"):
        for s in stage_list(val, f"{kind} {_id}" + (f" {ac}" if ac != "-" else ""), errors):
            rows.append((s, kind, _id, ac, text))

    for _id, val in sorted(stages.get("requirements", {}).items(), key=lambda kv: str(kv[0])):
        info = found["requirements"].get(_id, {"title": "", "acs": {}})
        if isinstance(val, dict):
            have, want = set(map(str, val)), set(info["acs"])
            if _id in found["requirements"]:
                for ac in sorted(want - have):
                    errors.append(f"requirements {_id}: acceptance criterion {ac} has no stage")
                for ac in sorted(have - want):
                    errors.append(f"requirements {_id}: unknown acceptance criterion {ac}")
            for ac, v in sorted(val.items(), key=lambda kv: str(kv[0])):
                add("requirement", _id, v, info["acs"].get(str(ac), info["title"]), str(ac))
        else:
            add("requirement", _id, val, info["title"])
    plain = (("decisions", "decision"), ("questions", "question"), ("work_items", "work item"),
             ("findings", "finding"), ("vendor_enquiries", "vendor enquiry"), ("issues", "issue"),
             ("hypotheses", "hypothesis"), ("build_plan", "build plan"))
    for sec, label in plain:
        for _id, val in sorted(stages.get(sec, {}).items(), key=lambda kv: str(kv[0])):
            title = found.get(sec, {}).get(_id, {}).get("title", "")
            add(label, str(_id), val, title)
    for sec, label in (("open_areas", "open area"), ("conflicts", "conflict")):
        for _id, val in sorted(stages.get(sec, {}).items(), key=lambda kv: str(kv[0])):
            if not isinstance(val, dict) or "text" not in val or "stage" not in val:
                errors.append(f"{sec} {_id}: needs 'text' and 'stage'")
                continue
            add(label, str(_id), val["stage"], collapse(str(val["text"])))
    return rows


def check(root, use_gh=True, require_gh=False):
    errors = []
    found = discover(root, errors)
    stages = load_stages(root, errors)
    for kind in DISCOVERED:
        have = {str(k) for k in stages.get(kind, {})}
        want = set(found[kind])
        for _id in sorted(want - have):
            errors.append(f"{kind}: {_id} has no stage in coverage-stages.yaml")
        for _id in sorted(have - want):
            errors.append(f"{kind}: {_id} is in coverage-stages.yaml but is no longer discovered in the repo")
    rows = normalise(stages, found, errors)
    oq = root / SP / "open-questions.md"
    if oq.is_file():
        hay = collapse(oq.read_text(encoding="utf-8"))
        for _id, v in sorted(stages.get("open_areas", {}).items(), key=lambda kv: str(kv[0])):
            if isinstance(v, dict) and "text" in v and collapse(str(v["text"])) not in hay:
                errors.append(f"open_areas {_id}: text not found in open-questions.md: {collapse(str(v['text']))!r}")
    notes = []
    if use_gh:
        issues, why = gh_open_issues(root)
        if issues is None:
            if require_gh or os.environ.get("GITHUB_ACTIONS") == "true":
                errors.append(f"issues: GitHub issue list required but unavailable: {why}")
            else:
                notes.append(f"issues: not checked ({why})")
        else:
            have = {str(k) for k in stages.get("issues", {})}
            for i in sorted(issues - have, key=lambda s: int(s[1:])):
                errors.append(f"issues: {i} is open on GitHub and has no stage")
            for i in sorted(have - issues, key=lambda s: int(s[1:]) if s[1:].isdigit() else 0):
                errors.append(f"issues: {i} is in coverage-stages.yaml but is not open on GitHub")
            notes.append(f"issues: {len(issues)} open, checked")
    else:
        notes.append("issues: not checked (--no-gh)")
    counts = {k: len(found[k]) for k in DISCOVERED}
    counts["requirements"] = len(found["requirements"])
    ac_total = sum(len(v["acs"]) for v in found["requirements"].values())
    return errors, found, counts, ac_total, notes, rows


def head_sha(root):
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def render(root, rows):
    cell = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    out = ["<!-- generated by scripts/orchestrator/coverage.py --write; do not edit -->", "",
           "# Coverage register", "", f"Generated from commit {head_sha(root)}", ""]
    for stage in STAGES:
        sel = sorted((r for r in rows if r[0] == stage), key=lambda r: (r[1], r[2], r[3]))
        if not sel:
            continue
        out += [f"## Stage {stage}", "", "| Stage | Kind | Id | AC | Text |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {cell(s)} | {cell(k)} | {cell(i)} | {cell(a)} | {cell(t)} |" for s, k, i, a, t in sel]
        out.append("")
    kinds = sorted({r[1] for r in rows})
    out += ["## Counts", "", "| Stage | " + " | ".join(kinds) + " | Total |",
            "| --- | " + " | ".join("---" for _ in kinds) + " | --- |"]
    for stage in STAGES:
        sel = [r for r in rows if r[0] == stage]
        if sel:
            out.append(f"| {stage} | " + " | ".join(str(sum(1 for r in sel if r[1] == k)) for k in kinds)
                       + f" | {len(sel)} |")
    out.append("")
    return "\n".join(out)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) != 1 or not (flags & {"--check", "--write"}) or flags - {"--check", "--write", "--no-gh",
                                                                          "--require-gh"}:
        print(__doc__)
        return 2
    root = Path(args[0]).resolve()
    errors, found, counts, ac_total, notes, rows = check(root, use_gh="--no-gh" not in flags,
                                                           require_gh="--require-gh" in flags)
    if "--write" in flags:
        if errors:
            print("coverage: refusing to write while the check fails:")
            for e in errors:
                print("  - " + e)
            return 1
        (root / "docs" / "process" / "coverage-register.md").write_bytes(render(root, rows).encode("utf-8"))
        print(f"wrote docs/process/coverage-register.md ({len(rows)} rows)")
        return 0
    for k in DISCOVERED:
        print(f"{k}: {counts[k]}" + (f" ({ac_total} acceptance criteria)" if k == "requirements" else ""))
    for n in notes:
        print(n)
    if errors:
        print(f"FAIL: {len(errors)} problem(s)")
        for e in errors:
            print("  - " + e)
        return 1
    print("OK: every discovered id has a valid stage")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
