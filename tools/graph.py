#!/usr/bin/env python3
"""graph.py - one project graph, built in memory from the records (REQ-067, W-094).

Covers: an agent greps and misses links that records already declare (work item -> requirement -> decision, work item
-> file, file -> file); the graph reads those declared fields once, through the kit's own loaders.

Subcommands (all read-only except `pin`, which edits only the `req_fp:` key of one work item; no graph file is ever
written, so parallel branches cannot conflict):

    graph.py build  [ROOT] [--json]     nodes and edges; one count line per edge kind
    graph.py lint   [ROOT] [--strict]   missing target, duplicate id, work-item depends_on cycle, missing affected path
    graph.py impact <id|path> [--root R]   everything downstream of a record or file
    graph.py why    <id> [--root R]        the upstream chain to the decisions
    graph.py pin <W-id> [--root R]      write req_fp: (requirement id -> fingerprint of statement + criteria texts)
    graph.py suspects [ROOT]            work items whose pinned requirement text changed (warn only, exit 0)
    graph.py brief <W-id> [--root R]    the work item's requirement, decisions, dependents, tests and applying findings
                                        as ids and paths with one line of why each, at most 60 lines
    graph.py tier <W-id> [--root R]     A, B or C from what the item's affected files are, plus the reason
    graph.py affected --base <ref> [--root R] [--committed-only]
                                        changed files -> work items -> requirements -> criteria -> tests; the first
                                        line names the diff (merge base...HEAD + working tree, unless --committed-only)

Optional project config `<claude folder>/project/graph.json`, either a list of extractors or an object with both keys:
    "extractors": [{"glob": "*.vue", "regex": "..."}]   import patterns (group 1 = specifier) that override the kit
                                                        defaults in <claude folder>/kit/graph-defaults.json
    "shared": ["config/", "docs/*.yml"]                 paths that make `affected` answer ALL (prefix ending in /, or glob)

Node ids: OD-n, ADR-n, REQ-n, REQ-n#AC-k, W-n, R-n, PL-n, F:<finding id>, file:<path>, test:<path>.
Edge: {src, dst, kind, origin: declared|derived, at: <record path>}. Direction: src depends on dst, except the kinds in
FLIPPED (tests, released-in), where dst depends on src. Paths always use forward slashes.
Without git, the file list comes from a folder walk. Exit codes: 0 ok; lint --strict 1 on any error; 2 usage or git error.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
import warnings
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_paths  # noqa: E402
import spec_text  # noqa: E402
import trace_check  # noqa: E402

_DOT_CLAUDE = "." + "claude"
DEFAULTS_REL = f"{_DOT_CLAUDE}/kit/graph-defaults.json"
FACTORY_DEFAULTS_REL = "templates/project-os/" + DEFAULTS_REL
PROJECT_CFG_REL = f"{_DOT_CLAUDE}/project/graph.json"
FACTORY_SHARED = ("tools/", "templates/", "factory/schemas/", "capabilities/hooks/")

FLIPPED = {"tests", "released-in"}          # dst depends on src (a test runs for a work item; a release holds a requirement)
CODE_KINDS = {"affects", "imports", "tests-module", "tests"}   # left out of `why`: code is not a justification
DONE_STATES = {"done", "dropped"}
REC_ID_RE = re.compile(r"^(OD-\d+|ADR-\d+|REQ-\d+(#AC-[\w.-]+)?|W-\d+|R-\d+|PL-\d+|F:.+)$")
TEXT_REF_RE = re.compile(r"\b(OD-\d+|ADR-\d+|REQ-\d+)\b")
ID_IN_TEXT_RE = re.compile(r"\b(OD-\d+|ADR-\d+|REQ-\d+|W-\d+|R-\d+|PL-\d+)\b")
JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".json")


def norm(p: str) -> str:
    p = str(p).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_test_path(p: str) -> bool:
    parts = p.split("/")
    base = parts[-1]
    return (any(x in ("tests", "test", "__tests__") for x in parts[:-1]) or base.startswith("test_")
            or base.endswith(("_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js")))


def path_id(p: str) -> str:
    p = norm(p)
    return ("test:" if is_test_path(p) else "file:") + p


class Graph:
    def __init__(self, root: Path):
        self.root = root
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.dups: list[tuple[str, str, str]] = []      # (id, first at, second at)
        self.problems: list[tuple[str, str]] = []       # records that could not be read: (path, reason)
        self.shared: list[str] = []                     # project-listed shared paths (graph.json "shared")
        self.warnings: list[str] = []                   # code files that could not be parsed
        self.status: dict[str, str] = {}                # work item id -> status
        self._seen: set[tuple] = set()

    def node(self, nid: str, kind: str, at: str = "", **extra) -> None:
        if nid in self.nodes and self.nodes[nid].get("record"):
            self.dups.append((nid, self.nodes[nid]["at"], at))     # never a silent overwrite (record-id-assumed-unique)
            return
        cur = self.nodes.get(nid, {})
        cur.update({"id": nid, "kind": kind, "at": at or cur.get("at", ""), "record": bool(at) or cur.get("record", False)}, **extra)
        self.nodes[nid] = cur

    def edge(self, src: str, dst: str, kind: str, origin: str, at: str) -> None:
        key = (src, dst, kind, origin, at)
        if key in self._seen:
            return
        self._seen.add(key)
        self.edges.append({"src": src, "dst": dst, "kind": kind, "origin": origin, "at": at})


def problem(root: Path, text: str) -> tuple[str, str]:
    """(path relative to the repository top with forward slashes, one-line reason) from a loader's `path: reason`."""
    path, _, reason = text.partition(": ")
    if not reason:
        path, reason = text, "unreadable"
    try:
        path = Path(path).resolve().relative_to(root.resolve()).as_posix() if Path(path).is_absolute() else norm(path)
    except ValueError:
        path = norm(path)
    return path, " ".join(reason.split())


def kind_of(nid: str) -> str:
    if nid.startswith(("OD-", "ADR-")):
        return "decision"
    if "#AC-" in nid:
        return "criterion"
    for pre, k in (("REQ-", "requirement"), ("W-", "work"), ("R-", "release"), ("PL-", "plan"), ("F:", "finding"),
                   ("file:", "file"), ("test:", "test")):
        if nid.startswith(pre):
            return k
    return "other"


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def repo_root(folder) -> Path:
    return kit_paths.repo_top(folder) or Path(folder).resolve()


def tracked_files(root: Path) -> list[str]:
    try:
        cp = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=60)
        if cp.returncode == 0:
            return sorted(norm(x) for x in cp.stdout.split("\0") if x)
    except (OSError, subprocess.SubprocessError):
        pass
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d != ".git"]
        out += [norm(os.path.relpath(os.path.join(dp, f), root)) for f in fn]
    return sorted(out)


# ---------------------------------------------------------------- records

def _read_records(g: Graph) -> None:
    root = g.root
    src = spec_text.Source(root)
    for rec in spec_text.adr_records(src) + spec_text.od_records(src):
        g.node(rec.id, "decision", rec.path)
        for key in ("supersedes", "amends"):
            for tgt in _as_list(rec.data.get(key)):
                if isinstance(tgt, str):
                    g.edge(rec.id, tgt.strip(), key, "declared", rec.path)
        ch = rec.data.get("changes")
        for clause in (ch.split(";") if isinstance(ch, str) else []):
            words = clause.split()
            verb = words[0].lower() if words else ""
            kind = ("supersedes" if verb.startswith("supersed") else "applies" if verb == "applies"
                    else "amends" if verb in ("amends", "narrows", "extends", "refines") else None)
            for m in ID_IN_TEXT_RE.finditer(clause if kind else ""):
                if m.group(1) != rec.id:
                    g.edge(rec.id, m.group(1), kind, "declared", rec.path)
    g.problems += [(p, r) for p, r in src.problems]

    reqs, errs = trace_check.load_requirements(root)
    g.problems += [problem(root, e) for e in errs]
    req_acs: dict[str, list[str]] = {}
    for r in reqs:
        at = r.path.relative_to(root).as_posix()
        g.node(r.id, "requirement", at, status=r.status)
        for ac in r.ac_ids:
            aid = f"{r.id}#{ac}"
            g.node(aid, "criterion", at)
            g.edge(aid, r.id, "criterion-of", "declared", at)
        req_acs.setdefault(r.id, []).extend(r.ac_ids)
        for dep in _as_list(r.data.get("depends_on")):
            g.edge(r.id, str(dep), "depends", "declared", at)
        for c in _as_list(r.data.get("confirmed_against")):
            m = re.match(r"\s*([A-Z]+-\d+)", str(c))
            if m:
                g.edge(r.id, m.group(1), "cites", "declared", at)
        text = " ".join([str(r.data.get("statement") or "")] +
                        [str(a.get("text") or "") for a in _as_list(r.data.get("acceptance_criteria")) if isinstance(a, dict)])
        for m in TEXT_REF_RE.finditer(text):
            if m.group(1) != r.id:
                g.edge(r.id, m.group(1), "cites", "derived", at)
        for key in ("supersedes", "amends"):
            for tgt in _as_list(r.data.get(key)):
                if isinstance(tgt, str):
                    g.edge(r.id, tgt.strip(), key, "declared", at)
        rel = r.data.get("release")
        if isinstance(rel, str) and rel.strip() and r.status == "Released":
            g.edge(r.id, rel.strip(), "released-in", "declared", at)
        for sp in _as_list(r.data.get("spec_refs")):
            if isinstance(sp, str) and ID_IN_TEXT_RE.fullmatch(sp.strip()):
                g.edge(r.id, sp.strip(), "cites", "declared", at)

    items, errs = trace_check.load_work_items(root)
    g.problems += [problem(root, e) for e in errs]
    for w in items:
        at = w.path.relative_to(root).as_posix()
        g.node(w.id, "work", at, status=str(w.data.get("status", "")))
        g.status.setdefault(w.id, str(w.data.get("status", "")))
        for rid in w.requirement_ids:
            g.edge(w.id, rid.strip(), "requirement-of", "declared", at)
        for dep in _as_list(w.data.get("depends_on")):
            g.edge(w.id, str(dep), "depends", "declared", at)
        for p in _as_list(w.data.get("affected")):
            if isinstance(p, str) and norm(p):
                q = norm(p)
                if not q.endswith("/") and (root / q).is_dir():
                    q += "/"                       # a directory entry matches every file under it
                g.edge(w.id, path_id(q), "affects", "declared", at)
        for entry in w.tests_required:
            for tp in trace_check.tests_required_paths(entry):
                if not tp.endswith("/"):
                    g.edge(w.id, "test:" + norm(tp), "tests", "declared", at)
            m = re.match(r"\s*(AC-[\w.-]+)", entry)
            if m:
                for rid in w.requirement_ids:
                    if m.group(1) in req_acs.get(rid, []):
                        g.edge(w.id, f"{rid}#{m.group(1)}", "acceptance", "declared", at)
        rel = w.data.get("release")
        if isinstance(rel, str) and rel.strip():
            g.edge(w.id, rel.strip(), "released-in", "declared", at)
        for key in ("supersedes", "amends"):
            for tgt in _as_list(w.data.get(key)):
                if isinstance(tgt, str):
                    g.edge(w.id, tgt.strip(), key, "declared", at)
        # evidence files: verifies edge from the evidence file to the criterion it checks
        evdir = root / "evidence" / w.id
        if evdir.is_dir():
            for ev in sorted(evdir.glob("AC-*.md")):
                eat = ev.relative_to(root).as_posix()
                ac = ev.stem
                for rid in w.requirement_ids:
                    if ac in req_acs.get(rid, []):
                        g.edge("file:" + eat, f"{rid}#{ac}", "verifies", "declared", eat)
                        g.edge("file:" + eat, w.id, "evidence-of", "declared", eat)

    rels, fails = trace_check.load_releases(root)
    g.problems += [problem(root, f) for f in fails]
    for rid, rel in rels.items():
        at = f"releases/{rel.path.name}"
        g.node(rid, "release", at)
        for it in rel.items:
            g.edge(it, rid, "released-in", "declared", at)

    for p in sorted((root / "plans").glob("PL-*.md")) if (root / "plans").is_dir() else []:
        data, err = trace_check.parse_frontmatter(p)
        at = p.relative_to(root).as_posix()
        if err:
            g.problems.append((at, err))
            continue
        pid = str(data.get("id") or p.stem)
        g.node(pid, "plan", at)
        for c in _as_list(data.get("covers")):
            g.edge(pid, str(c), "covers", "declared", at)

    fdir = root / "knowledge" / "findings"
    for p in sorted(fdir.glob("*.json")) if fdir.is_dir() else []:
        at = p.relative_to(root).as_posix()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            fid = str(data["id"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            g.problems.append((at, f"finding unreadable: {exc}"))
            continue
        g.node("F:" + fid, "finding", at)
        for sp in _as_list(data.get("spec_ref")):
            if not isinstance(sp, str):
                continue
            sp = norm(sp)
            m = re.fullmatch(r"spec/requirements/(REQ-\d+)\.md", sp)
            g.edge("F:" + fid, m.group(1) if m else path_id(sp), "finding-spec", "declared", at)

    rdir = root / "reviews"
    for p in sorted(rdir.glob("W-*-r*.md")) if rdir.is_dir() else []:
        at = p.relative_to(root).as_posix()
        data, err = trace_check.parse_frontmatter(p)
        if err:
            g.problems.append((at, err))
            continue
        if isinstance(data.get("work_item"), str):
            g.edge("file:" + at, data["work_item"].strip(), "reviews", "declared", at)


# ---------------------------------------------------------------- code

def _load_cfg(g: Graph) -> list[dict]:
    root = g.root
    out: list[dict] = []

    def read(rel: str, what: str):
        p = root / rel
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            shared = []
            if isinstance(data, dict) and what == "project":
                shared = data.get("shared", [])
                data = data.get("extractors", [])
                if not isinstance(shared, list) or not all(isinstance(x, str) for x in shared):
                    raise ValueError('"shared" must be a list of paths')
            ok = isinstance(data, list) and all(isinstance(x, dict) and isinstance(x.get("glob"), str)
                                                and isinstance(x.get("regex"), str) for x in data)
            if not ok:
                raise ValueError("expected a list of {glob, regex}")
            for x in data:
                re.compile(x["regex"])
            if what == "project":              # the kit defaults never reset the project's shared list
                g.shared = [norm(x) for x in shared if norm(x)]
            return data
        except (OSError, ValueError, re.error) as exc:
            g.warnings.append(f"WARN cannot parse {rel}: {exc}")
            return []

    proj = read(PROJECT_CFG_REL, "project")
    dflt = read(DEFAULTS_REL, "kit")
    if dflt is None:
        dflt = read(FACTORY_DEFAULTS_REL, "kit")
    proj = proj or []
    names = {x["glob"] for x in proj}
    out = list(proj) + [x for x in (dflt or []) if x["glob"] not in names]
    return out


def _py_targets(files: set[str], by_mod: dict[str, str], src: str, node: ast.AST) -> list[str]:
    here = src.rsplit("/", 1)[0] if "/" in src else ""
    found: list[str] = []

    def try_mod(parts: list[str], bases: list[str]) -> str | None:
        for base in bases:
            rel = "/".join(([base] if base else []) + parts)
            for cand in (rel + ".py", rel + "/__init__.py"):
                if cand in files:
                    return cand
        rel = "/".join(parts)                              # a source root such as src/ : accept a suffix match
        hits = [f for f in files if f.endswith("/" + rel + ".py") or f.endswith("/" + rel + "/__init__.py")]
        if not hits:
            return None
        top = src.split("/", 1)[0] if "/" in src else ""     # twins (tools/X.py, templates/.../tools/X.py): own top folder, then shortest
        return sorted(hits, key=lambda h: (h.split("/", 1)[0] != top, len(h), h))[0]

    if isinstance(node, ast.Import):
        for a in node.names:
            t = try_mod(a.name.split("."), ["", here])
            if t:
                found.append(t)
    elif isinstance(node, ast.ImportFrom):
        mod = node.module.split(".") if node.module else []
        if node.level:
            base = here
            for _ in range(node.level - 1):
                base = base.rsplit("/", 1)[0] if "/" in base else ""
            bases = [base]
        else:
            bases = ["", here]
        t = try_mod(mod, bases) if mod else None
        if t:
            found.append(t)
        for a in node.names:                              # `from pkg import module`
            t2 = try_mod(mod + [a.name], bases)
            if t2:
                found.append(t2)
    return found


def _js_target(files: set[str], src: str, spec: str) -> str | None:
    if not spec.startswith("."):
        return None
    here = src.rsplit("/", 1)[0] if "/" in src else ""
    rel = os.path.normpath(os.path.join(here, spec)).replace("\\", "/")
    if rel.startswith(".."):
        return None
    cands = [rel] + [rel + e for e in JS_EXTS] + [rel + "/index" + e for e in JS_EXTS]
    for c in cands:
        if c in files:
            return c
    return None


def _read_code(g: Graph, files: list[str]) -> None:
    fset = set(files)
    cfg = _load_cfg(g)
    for f in files:
        if f.endswith(".py"):
            try:
                text = (g.root / f).read_text(encoding="utf-8-sig")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    tree = ast.parse(text, filename=f)
            except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
                g.warnings.append(f"WARN cannot parse {f}: {type(exc).__name__}: {exc}")
                continue
            sid = path_id(f)
            g.node(sid, kind_of(sid))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for t in _py_targets(fset, {}, f, node):
                        if t == f:
                            continue
                        kind = "tests-module" if is_test_path(f) and not is_test_path(t) else "imports"
                        g.edge(sid, path_id(t), kind, "derived", f)
            continue
        rules = [r for r in cfg if fnmatch.fnmatch(f, r["glob"]) or fnmatch.fnmatch(f.rsplit("/", 1)[-1], r["glob"])]
        if not rules:
            continue
        try:
            text = (g.root / f).read_text(encoding="utf-8-sig")
            specs = [m.group(1) for r in rules for m in re.finditer(r["regex"], text) if m.groups()]
        except (OSError, UnicodeError, re.error, IndexError) as exc:
            g.warnings.append(f"WARN cannot parse {f}: {type(exc).__name__}: {exc}")
            continue
        sid = path_id(f)
        g.node(sid, kind_of(sid))
        for sp in specs:
            t = _js_target(fset, f, sp)
            if t and t != f:
                kind = "tests-module" if is_test_path(f) and not is_test_path(t) else "imports"
                g.edge(sid, path_id(t), kind, "derived", f)


def build(folder) -> Graph:
    root = repo_root(folder)
    g = Graph(root)
    _read_records(g)
    _read_code(g, tracked_files(root))
    for e in g.edges:                                   # every edge end gets a node; a record end not seen stays unrecorded
        for nid in (e["src"], e["dst"]):
            if nid not in g.nodes:
                g.nodes[nid] = {"id": nid, "kind": kind_of(nid), "at": "", "record": False}
    return g


# ---------------------------------------------------------------- lint

def lint_findings(g: Graph) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    for path, reason in g.problems:
        errors.append(f"ERROR cannot read record {path}: {reason}")
    for nid, a, b in g.dups:
        errors.append(f"ERROR duplicate id {nid}: {a} and {b}")
    for e in g.edges:
        if e["origin"] != "declared":
            continue
        for end in (e["src"], e["dst"]):
            if not end.startswith(("file:", "test:")) and not g.nodes[end]["record"]:
                errors.append(f"ERROR missing target {end} ({e['kind']} edge from {e['src']}, at {e['at']})")
    seen_missing = set()
    errors = [x for x in errors if not (x in seen_missing or seen_missing.add(x))]
    for e in g.edges:
        if e["kind"] == "affects" and e["src"].startswith("W-"):
            rel = e["dst"].split(":", 1)[1]
            if not (g.root / rel).exists():
                if g.status.get(e["src"]) in DONE_STATES:
                    notes.append(f"NOTE {e['src']} ({g.status[e['src']]}) affects {rel}, which no longer exists: history")
                else:
                    errors.append(f"ERROR {e['src']} affected path does not exist: {rel} (at {e['at']})")
    deps: dict[str, list[str]] = {}
    for e in g.edges:
        if e["kind"] == "depends" and e["src"].startswith("W-") and e["dst"].startswith("W-"):
            deps.setdefault(e["src"], []).append(e["dst"])
    state: dict[str, int] = {}
    reported: set[frozenset] = set()

    def walk(n: str, stack: list[str]) -> None:
        state[n] = 1
        stack.append(n)
        for d in deps.get(n, []):
            if state.get(d) == 1:
                cyc = stack[stack.index(d):] + [d]
                if frozenset(cyc) not in reported:
                    reported.add(frozenset(cyc))
                    errors.append("ERROR depends_on cycle: " + " -> ".join(cyc))
            elif state.get(d) is None:
                walk(d, stack)
        stack.pop()
        state[n] = 2

    for n in sorted(deps):
        if state.get(n) is None:
            walk(n, [])
    return errors, notes


# ---------------------------------------------------------------- queries

def _adj(g: Graph) -> tuple[dict, dict]:
    """(dependents, dependencies): node -> [(other, edge)]."""
    dependents: dict[str, list] = {}
    dependencies: dict[str, list] = {}
    for e in g.edges:
        if e["kind"] in FLIPPED:
            dep_on, dependent = e["src"], e["dst"]
        else:
            dep_on, dependent = e["dst"], e["src"]
        dependents.setdefault(dep_on, []).append((dependent, e))
        dependencies.setdefault(dependent, []).append((dep_on, e))
    for w, pre in dir_affects(g):                  # a work item affecting a directory affects each file node under it
        for nid in g.nodes:
            if nid.startswith(("file:", "test:")) and nid.split(":", 1)[1].startswith(pre):
                e = {"src": w, "dst": nid, "kind": "affects", "origin": "derived", "at": ""}
                dependents.setdefault(nid, []).append((w, e))
                dependencies.setdefault(w, []).append((nid, e))
    return dependents, dependencies


def dir_affects(g: Graph) -> list[tuple[str, str]]:
    """[(work item, directory prefix with trailing slash)] from declared affects edges naming a directory."""
    return [(e["src"], e["dst"].split(":", 1)[1]) for e in g.edges
            if e["kind"] == "affects" and e["src"].startswith("W-") and e["dst"].endswith("/")]


def resolve_target(g: Graph, arg: str, cwd: Path | None = None) -> str | None:
    if arg in g.nodes:
        return arg
    p = norm(arg)
    cwd = cwd or Path.cwd()
    try:
        ap = Path(arg)
        if ap.is_absolute():
            p = ap.resolve().relative_to(g.root.resolve()).as_posix()
        elif (cwd / ap).exists() and not (g.root / ap).exists():
            p = (cwd / ap).resolve().relative_to(g.root.resolve()).as_posix()
    except ValueError:
        pass
    for pre in ("file:", "test:"):
        if pre + p in g.nodes:
            return pre + p
    return None


def closure(start: str, adj: dict, skip_kinds: set[str] = frozenset()) -> list[tuple[str, list[str]]]:
    """Breadth-first: [(node, chain from start)]."""
    seen = {start}
    out = []
    q = deque([(start, [start])])
    while q:
        n, chain = q.popleft()
        for nxt, e in sorted(adj.get(n, []), key=lambda x: x[0]):
            if nxt in seen or e["kind"] in skip_kinds:
                continue
            seen.add(nxt)
            out.append((nxt, chain + [nxt]))
            q.append((nxt, chain + [nxt]))
    return out


def cmd_impact(g: Graph, arg: str) -> int:
    """Covers: an agent changes a record or file without knowing what is built on it."""
    nid = resolve_target(g, arg)
    if nid is None:
        print(f"graph impact: no such id or tracked path: {arg}")
        return 2
    dependents, _ = _adj(g)
    rows = closure(nid, dependents)
    print(f"impact of {nid}: {len(rows)} downstream")
    for n, chain in rows:
        print(f"  {n}  (via {' <- '.join(reversed(chain[:-1]))})" if len(chain) > 2 else f"  {n}")
    return 0


def cmd_why(g: Graph, arg: str) -> int:
    """Covers: an agent builds a feature without knowing which decision justifies it."""
    nid = resolve_target(g, arg)
    if nid is None:
        print(f"graph why: no such id or tracked path: {arg}")
        return 2
    _, dependencies = _adj(g)
    rows = closure(nid, dependencies, CODE_KINDS)
    decisions = [(n, c) for n, c in rows if kind_of(n) == "decision"]
    print(f"why {nid}: {len(rows)} upstream, {len(decisions)} decisions")
    for n, chain in rows:
        print(f"  {n}  ({' -> '.join(chain)})" if len(chain) > 2 else f"  {n}")
    return 0


def shared_reason(g: Graph, changed: list[str]) -> str | None:
    """The failsafe: a changed file that is kit-owned or project-listed shared means run everything."""
    kit_owned: set[str] = set()
    lock = kit_paths.lock_file(g.root)
    has_lock = lock.is_file()
    if has_lock:
        try:
            doc = kit_paths.read_lock(lock)
            for ent in (doc.get("files") if isinstance(doc, dict) else None) or []:
                if isinstance(ent, dict) and ent.get("owner") == "kit" and isinstance(ent.get("path"), str):
                    kit_owned.add(norm(ent["path"]))
        except Exception:
            has_lock = False
    patterns = g.shared
    for f in changed:
        if f in kit_owned:
            return f"{f} is kit-owned (a change to a kit file can break any work item)"
        if not has_lock and any(f.startswith(p) for p in FACTORY_SHARED):
            return f"{f} is a shared Factory path (tools, templates, schemas, hooks)"
        for pat in patterns:
            if f == pat or fnmatch.fnmatch(f, pat) or (pat.endswith("/") and f.startswith(pat)):
                return f"{f} is listed in {PROJECT_CFG_REL} (shared)"
    return None


def _git_lines(root: Path, *args: str) -> list[str]:
    cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=60)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or f"git {' '.join(args)} failed")
    return [norm(x) for x in cp.stdout.splitlines() if x.strip()]


def changed_files(root: Path, base: str, worktree: bool = True) -> tuple[list[str], str]:
    """(changed files, the diff used). Committed changes since the merge base, plus staged, unstaged and untracked
    files unless worktree is False."""
    files = _git_lines(root, "diff", "--name-only", f"{base}...HEAD")
    sha = _git_lines(root, "rev-parse", "--short", base)[0]
    label = f"diff: {sha}...HEAD"
    if worktree:
        files += _git_lines(root, "diff", "--name-only", "HEAD") + _git_lines(root, "ls-files", "--others", "--exclude-standard")
        label += " + working tree"
    return sorted(set(files)), label


def affected_sets(g: Graph, changed: list[str]) -> dict[str, list[str]]:
    dependents, _ = _adj(g)
    nodes = {path_id(f) for f in changed}
    # code closure: files that import a changed file, and the tests of those
    code = set(nodes)
    q = deque(nodes)
    while q:
        n = q.popleft()
        for nxt, e in dependents.get(n, []):
            if e["kind"] in ("imports", "tests-module") and nxt not in code:
                code.add(nxt)
                q.append(nxt)
    works = {nxt for n in code for nxt, e in dependents.get(n, []) if e["kind"] == "affects"}
    works |= {w for w, pre in dir_affects(g) for n in code if n.split(":", 1)[1].startswith(pre)}
    works = sorted(works)
    reqs = sorted({e["dst"] for w in works for e in g.edges if e["src"] == w and e["kind"] == "requirement-of"})
    acs = sorted({e["dst"] for w in works for e in g.edges if e["src"] == w and e["kind"] == "acceptance"})
    tests = sorted({n for n in code if n.startswith("test:")} |
                   {e["dst"] for w in works for e in g.edges if e["src"] == w and e["kind"] == "tests"})
    return {"files": sorted(code), "work items": works, "requirements": reqs, "criteria": acs, "tests": tests}


def cmd_affected(g: Graph, base: str | None, worktree: bool = True, files: list[str] | None = None) -> int:
    """Covers: an agent re-verifies everything, or only what it remembers, after a change."""
    if files:
        if base:
            print("graph affected: give --base or --files, not both")
            return 2
        rels = []
        top = g.root.resolve()
        for f in files:
            if not norm(f):
                print("graph affected: an empty path was given in --files")
                return 2
            ap = Path(norm(f))
            if ap.is_absolute():
                try:
                    ap = ap.resolve().relative_to(top)
                except ValueError:
                    print(f"graph affected: {f} is outside the repository {top}")
                    return 2
            elif ".." in ap.parts:
                try:
                    ap = (top / ap).resolve().relative_to(top)
                except ValueError:
                    print(f"graph affected: {f} is outside the repository {top}")
                    return 2
            rels.append(norm(ap.as_posix()))
        changed, label, base = sorted(set(rels)), "files: given on the command line", "the given files"
    else:
        try:
            changed, label = changed_files(g.root, base, worktree)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"graph affected: cannot list changes since {base}: {exc}")
            return 2
    print(label)
    reason = shared_reason(g, changed)
    if reason:
        print(f"ALL: {reason}")
        return 0
    sets = affected_sets(g, changed)
    print(f"affected since {base}: {len(changed)} changed files")
    for label in ("work items", "requirements", "criteria", "tests"):
        print(f"{label}: {len(sets[label])}")
        for x in sets[label]:
            print(f"  {x}")
    return 0


# ---------------------------------------------------------------- build / lint commands

def counts(g: Graph) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in g.edges:
        c = out.setdefault(e["kind"], {"total": 0, "declared": 0, "derived": 0, "from_work": 0})
        c["total"] += 1
        c[e["origin"]] += 1
        if e["src"].startswith("W-"):
            c["from_work"] += 1
    return out


def cmd_build(g: Graph, as_json: bool) -> int:
    """Covers: an agent greps and misses links that records already declare."""
    for w in g.warnings:
        print(w, file=sys.stderr if as_json else sys.stdout)
    if as_json:
        print(json.dumps({"nodes": sorted(g.nodes.values(), key=lambda n: n["id"]), "edges": g.edges}, indent=1))
        return 0
    print(f"nodes: {len(g.nodes)}")
    for kind, c in sorted(counts(g).items()):
        print(f"{kind}: {c['total']} (declared {c['declared']}, derived {c['derived']}; from work items {c['from_work']})")
    return 0


def cmd_lint(g: Graph, strict: bool) -> int:
    """Covers: an agent leaves a dangling link, a duplicate id or a dependency cycle in the records."""
    errors, notes = lint_findings(g)
    for w in g.warnings:
        print(w)
    for line in errors + notes:
        print(line)
    print(f"graph lint: {len(errors)} errors, {len(notes)} notes")
    return 1 if strict and errors else 0


# ---------------------------------------------------------------- pins and suspects (REQ-068)

REQ_FP_RE = re.compile(r"^[0-9a-f]{12}$")


def requirement_fp(text: str) -> str | None:
    """Fingerprint of one requirement file's statement plus all its criteria texts (spec_text.fingerprint:
    whitespace and case changes do not change it). None when the file has no readable frontmatter."""
    data = spec_text.parse_frontmatter(text)[0] if text else None
    if not isinstance(data, dict):
        return None
    texts = [str(data.get("statement") or "")]
    for ac in _as_list(data.get("acceptance_criteria")):
        if isinstance(ac, dict):
            texts.append(str(ac.get("text") or ""))
    return spec_text.fingerprint(*texts)


def _fm_close(lines: list[str]) -> int | None:
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return i
    return None


def set_req_fp(text: str, pins: dict[str, str]) -> str:
    """The work item text with its frontmatter `req_fp:` block set to `pins`; every other byte is kept."""
    lines = text.splitlines(keepends=True)
    close = _fm_close(lines)
    if close is None:
        raise ValueError("no frontmatter")
    nl = "\r\n" if lines[close].endswith("\r\n") else "\n"
    block = ["req_fp:" + nl] + [f'  {rid}: "{fp}"{nl}' for rid, fp in pins.items()]
    for i in range(1, close):
        if lines[i].startswith("req_fp:"):
            j = i + 1
            while j < close and lines[j][:1] in (" ", "\t"):
                j += 1
            return "".join(lines[:i] + block + lines[j:])
    return "".join(lines[:close] + block + lines[close:])


def cmd_pin(root: Path, wid: str) -> int:
    """Covers: a work item starts from a requirement and later forgets which version it started from."""
    path = root / "work" / f"{wid}.md"
    if not path.is_file():
        print(f"graph pin: no work item {wid} ({path.as_posix()})", file=sys.stderr)
        return 1
    raw = path.read_bytes().decode("utf-8")
    data = spec_text.parse_frontmatter(raw)[0]
    if not isinstance(data, dict):
        print(f"graph pin: {wid} has no readable frontmatter", file=sys.stderr)
        return 1
    pins: dict[str, str] = {}
    for rid in _as_list(data.get("requirement_ids")):
        rp = root / "spec" / "requirements" / f"{rid}.md"
        fp = requirement_fp(rp.read_bytes().decode("utf-8")) if isinstance(rid, str) and rp.is_file() else None
        if fp is None:
            print(f"graph pin: {wid} lists {rid}, which has no readable requirement file; nothing written",
                  file=sys.stderr)
            return 1
        pins[rid] = fp
    if not pins:
        print(f"graph pin: {wid} lists no requirement; nothing to pin")
        return 0
    new = set_req_fp(raw, pins)
    if new != raw:
        path.write_bytes(new.encode("utf-8"))
    print(f"graph pin: {wid} " + ("pinned " if new != raw else "already pinned ") +
          ", ".join(f"{r}={f}" for r, f in pins.items()))
    return 0


def suspect_class(pins: dict, now: dict, status: str, verification: str) -> str | None:
    """REASSESS / RE-BRIEF when any pinned fingerprint differs from `now` (id -> fingerprint or None), else None."""
    if not any(now.get(r) != fp for r, fp in pins.items()):
        return None
    return "REASSESS" if status == "done" or verification.startswith("verified") else "RE-BRIEF"


def compute_suspects(root: Path) -> dict:
    """{'lines': [...], 'reassess': n, 'rebrief': n, 'unpinned': n, 'legacy': n}. Dependencies come first."""
    items, _errs = trace_check.load_work_items(root)
    rels, _fails = trace_check.load_releases(root)
    by_id = {w.id: w for w in items}
    indeg = {w: 0 for w in by_id}
    kids: dict[str, list[str]] = {w: [] for w in by_id}
    for w in items:
        for d in _as_list(w.data.get("depends_on")):
            if isinstance(d, str) and d in by_id and d != w.id:
                indeg[w.id] += 1
                kids[d].append(w.id)
    order: list[str] = []
    ready = sorted(w for w, n in indeg.items() if n == 0)
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for k in kids[cur]:
            indeg[k] -= 1
            if indeg[k] == 0:
                ready.append(k)
        ready.sort()
    order += sorted(set(by_id) - set(order))        # a dependency cycle: the rest by id (graph lint reports it)
    fp_cache: dict[str, str | None] = {}

    def today(rid: str) -> str | None:
        if rid not in fp_cache:
            rp = root / "spec" / "requirements" / f"{rid}.md"
            fp_cache[rid] = requirement_fp(rp.read_bytes().decode("utf-8")) if rp.is_file() else None
        return fp_cache[rid]

    out: dict = {"lines": [], "reassess": 0, "rebrief": 0, "unpinned": 0, "legacy": 0}
    for wid in order:
        w = by_id[wid]
        status = str(w.data.get("status", ""))
        ver = str(w.data.get("verification_status", "")).strip().lower()
        raw = w.data.get("req_fp")
        pins = {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) and raw else {}
        if not pins:
            if status == "done":
                out["legacy"] += 1
            elif status != "dropped":
                out["unpinned"] += 1
                out["lines"].append(f"UNPINNED {wid} (open, no req_fp: run `python tools/graph.py pin {wid}`)")
            continue
        if status == "dropped":
            continue
        cls = suspect_class(pins, {r: today(r) for r in pins}, status, ver)
        if cls is None:
            continue
        changed = [r for r, fp in pins.items() if today(r) != fp]
        out["reassess" if cls == "REASSESS" else "rebrief"] += 1
        evdir = root / "evidence" / wid
        evid = sorted(p.relative_to(root).as_posix() for p in evdir.glob("AC-*.md")) if evdir.is_dir() else []
        relids = sorted(r.id for r in rels.values() if wid in r.items or any(c in r.items for c in changed))
        out["lines"].append(f"{cls} {wid} ({', '.join(changed)} changed since pinned) evidence: "
                            f"{', '.join(evid) or 'none'}; release: {', '.join(relids) or 'none'}")
    return out


def suspects_lines(root: Path) -> list[str]:
    r = compute_suspects(root)
    tail = [f"suspects: {r['reassess']} reassess, {r['rebrief']} re-brief, {r['unpinned']} unpinned"]
    if r["legacy"]:
        tail.insert(0, f"({r['legacy']} done work items have no req_fp: legacy history, not listed)")
    return r["lines"] + tail


def cmd_suspects(root: Path) -> int:
    """Covers: a requirement changes after work started from it and nobody is told. Warns only (exit 0)."""
    for line in suspects_lines(root):
        print(line)
    return 0


# ---------------------------------------------------------------- brief and tier (REQ-069, W-097)

BRIEF_MAX = 60
TIER_PATHS_REL = f"{_DOT_CLAUDE}/kit/tier-paths.json"
TIER_PROJECT_REL = f"{_DOT_CLAUDE}/project/tier-paths.json"
FACTORY_TIER_REL = "templates/project-os/" + TIER_PATHS_REL
KIT_B_PREFIXES = ("tools/", "capabilities/hooks/", f"{_DOT_CLAUDE}/hooks/", "templates/project-os/tools/",
                  f"templates/project-os/{_DOT_CLAUDE}/hooks/")
CODE_EXTS = (".py",) + JS_EXTS[:-1]                 # .json is data, not code
DOC_EXTS = (".md", ".txt", ".rst")                  # docs and records: never A or B
TIER_RANK = {"C": 0, "B": 1, "A": 2}
_GLOB_CACHE: dict[str, "re.Pattern"] = {}


def glob_match(pat: str, path: str) -> bool:
    """POSIX glob where `*` and `?` stay inside one path segment and `**` crosses segments (`**/` may match nothing)."""
    rx = _GLOB_CACHE.get(pat)
    if rx is None:
        out, i = "", 0
        while i < len(pat):
            c = pat[i]
            if pat.startswith("**/", i):
                out += "(?:.*/)?"
                i += 3
                continue
            if pat.startswith("**", i):
                out += ".*"
                i += 2
                continue
            out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
        rx = _GLOB_CACHE[pat] = re.compile(out + r"\Z")
    return rx.match(norm(path)) is not None
WID_RE = re.compile(r"^W-\d+$")


def work_affected(g: Graph, wid: str) -> list[str]:
    """Affected file paths of a work item: declared entries, a directory entry expanded to the tracked files under it."""
    _, deps = _adj(g)
    out = []
    for n, e in deps.get(wid, []):
        if e["kind"] == "affects" and n.startswith(("file:", "test:")) and not n.endswith("/"):
            out.append(n.split(":", 1)[1])
    return sorted(set(out))


def load_tier_globs(root: Path) -> list[str]:
    """Tier A globs: the kit list (the Factory's template copy when the project has none) plus the project's own list."""
    globs: list[str] = []
    kit = root / TIER_PATHS_REL
    if not kit.is_file():
        kit = root / FACTORY_TIER_REL
    for p in (kit, root / TIER_PROJECT_REL):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read {p.relative_to(root).as_posix()}: {exc}")
        if not isinstance(data, list) or not all(isinstance(x, str) and x for x in data):
            raise ValueError(f"{p.relative_to(root).as_posix()} must be a JSON list of glob strings")
        globs += [norm(x) for x in data]
    return globs


def declared_tier(g: Graph, wid: str) -> str | None:
    items, _ = trace_check.load_work_items(g.root)
    for w in items:
        if w.id == wid:
            t = str(w.data.get("tier") or "").strip().upper()
            return t if t in TIER_RANK else None
    return None


def tier_of(g: Graph, wid: str) -> tuple[str, str]:
    """(tier, reason). Inputs are the affected paths, the tier-A globs and the import edges; nothing else.
    Test files and docs are classified first and never reach A or B; an empty footprint answers the declared tier."""
    files = work_affected(g, wid)
    if not files:
        d = declared_tier(g, wid)
        if d:
            return d, "declared tier (no affected files to measure)"
        return "B", "unknown footprint: no affected files declared"
    globs = load_tier_globs(g.root)
    prod = [f for f in files if not is_test_path(f) and not f.endswith(DOC_EXTS)]

    def listed(rows: list[str]) -> str:
        return ", ".join(rows[:3]) + (f" and {len(rows) - 3} more" if len(rows) > 3 else "")

    hit_a = [(f, pat) for f in prod for pat in globs if glob_match(pat, f)]
    if hit_a:
        fs = sorted({f for f, _ in hit_a})
        return "A", f"{listed(fs)} match tier-A path {hit_a[0][1]}"
    kit = [f for f in prod if f.startswith(KIT_B_PREFIXES)]
    if kit:
        return "B", f"{listed(kit)} {'is a' if len(kit) == 1 else 'are'} kit tool or hook"
    dependents, _ = _adj(g)
    coded = []
    for f in prod:
        if f.endswith(CODE_EXTS):
            imp = sorted(d.split(":", 1)[1] for d, e in dependents.get("file:" + f, []) if e["kind"] == "imports")
            if imp:
                coded.append(f"{f} (imported by {imp[0]}" + (f" +{len(imp) - 1}" if len(imp) > 1 else "") + ")")
    if coded:
        return "B", f"code with dependents: {listed(coded)}"
    return "C", "only docs, records, text and test files, or code nothing imports"


def tier_note(g: Graph, wid: str, suggested: str) -> str | None:
    d = declared_tier(g, wid)
    if d and TIER_RANK[d] > TIER_RANK[suggested]:
        return f"NOTE declared tier {d} is higher than suggested {suggested}: keep the declared tier"
    return None


def applies_match(entry: str, files: list[str], kinds: set[str]) -> str | None:
    """Why a finding's applies_to entry matches the item: a record kind, a path prefix or a glob; None when it does not."""
    e = norm(entry)
    if e in kinds:
        return f"applies to {e}"
    for f in files:
        if f == e or (e.endswith("/") and f.startswith(e)) or glob_match(e, f):
            return f"applies_to {e} matches {f}"
    return None


def load_findings(root: Path) -> list[dict]:
    out = []
    fdir = root / "knowledge" / "findings"
    for p in sorted(fdir.glob("*.json")) if fdir.is_dir() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            d["_path"] = p.relative_to(root).as_posix()
            out.append(d)
    return out


def _spec_text(d: dict) -> str:
    return " ".join([str(d.get("class") or "")] + [x for x in _as_list(d.get("spec_ref")) if isinstance(x, str)])


def finding_hits(root: Path, files: list[str], reqs: list[dict], near: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """[(finding path, why)]: an applies_to match, or unguarded and naming the requirement or its section."""
    out = []
    kinds = {"work-item", "work"}
    for d in load_findings(root):
        why = None
        for a in _as_list(d.get("applies_to")):
            if isinstance(a, str) and a.strip():
                why = applies_match(a, files, kinds)
                if why:
                    break
                hop = applies_match(a, sorted(near or {}), set())
                if hop:
                    f = hop.rsplit(" ", 1)[1]
                    why = f"{hop} (one import from {near[f]})"
                    break
        det = d.get("detection")
        if not why and isinstance(det, dict) and det.get("status") == "unguarded":
            txt = _spec_text(d)
            for r in reqs:
                sec = str(r.get("section") or "")
                if re.search(rf"\b{re.escape(r['id'])}\b", txt):
                    why = f"unguarded; names {r['id']}"
                elif sec and re.search(rf"(?<![\w-]){re.escape(sec)}(?![\w-])", txt):
                    why = f"unguarded; names section {sec}"
                if why:
                    break
        if why:
            out.append((d["_path"], why))
    return out


def _short(text, n: int = 80) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 3].rstrip() + "..."


def brief_lines(g: Graph, wid: str) -> list[str] | None:
    """Covers: a builder or checker starts without the requirement, decisions, dependents, tests and findings that apply
    (design R7: ids and paths with one line of why, never file contents; the agent loads a file when it needs it)."""
    if wid not in g.nodes or not g.nodes[wid].get("record") or g.nodes[wid]["kind"] != "work":
        return None
    dependents, deps = _adj(g)
    files = work_affected(g, wid)
    rids = sorted({n for n, e in deps.get(wid, []) if e["kind"] == "requirement-of"})
    reqs, _ = trace_check.load_requirements(g.root)
    rmap = {r.id: r for r in reqs}
    items, _ = trace_check.load_work_items(g.root)
    mine = [w for w in items if w.id == wid]
    secs: list[tuple[str, list[str], str]] = []

    own = {m.group(1) for w in mine for t in w.tests_required for m in [re.match(r"\s*(AC-[\w.-]+)", t)] if m}
    req_rows = []
    for rid in rids:
        req_rows.append(f"{rid}  {_short(rmap[rid].data.get('title'), 70) if rid in rmap else 'not found'}")
        if rid in rmap:
            others = []
            for a in _as_list(rmap[rid].data.get("acceptance_criteria")):
                if isinstance(a, dict):
                    (req_rows.append(f"{rid}#{a.get('id')}  {_short(a.get('text'))}") if a.get("id") in own
                     else others.append(str(a.get("id"))))
            if others:
                req_rows.append(f"{rid}  other criteria: {', '.join(others)}")
    secs.append(("Requirement", req_rows, f"graph.py why {wid}"))

    dec_rows = []
    for n, chain in closure(wid, deps, CODE_KINDS):
        if kind_of(n) == "decision" and len(chain) <= 3:       # cited by the item or its requirement, not the whole chain
            via = chain[-2] if len(chain) > 2 else wid
            dec_rows.append((n, f"{n}  cited by {via}"))
    dec_rows = [r for _, r in sorted(dec_rows, key=lambda x: (x[0].split("-")[0], int(x[0].split("-")[1])))]
    secs.append(("Decisions", dec_rows, f"graph.py why {wid}"))

    dep_rows, test_rows, seen = [], [], set()
    for f in files:
        for d, e in sorted(dependents.get(path_id(f), []), key=lambda x: x[0]):
            p = d.split(":", 1)[1] if d.startswith(("file:", "test:")) else d
            if e["kind"] in ("imports", "tests-module") and (d, f) not in seen:
                seen.add((d, f))
                (dep_rows if e["kind"] == "imports" else test_rows).append((p, f"{p}  imports {f}"))
    rank = lambda x: (x[0].count("/"), x[0])            # direct importers only, shallow paths first
    dep_rows = [r for _, r in sorted(dep_rows, key=rank)]
    test_rows = [r for _, r in sorted(test_rows, key=rank)]
    for d, e in sorted(dependents.get(wid, []), key=lambda x: x[0]):
        if e["kind"] == "depends" and d.startswith("W-"):
            dep_rows.append(f"{d}  depends_on {wid}")
    secs.append(("Dependents", dep_rows, f"graph.py impact {wid}"))

    tr = [f"{_short(t, 100)}  (tests_required)" for w in mine for t in w.tests_required]
    secs.append(("Tests", tr + test_rows, f"graph.py impact {wid}"))

    near = {}                                           # files one import away from the footprint (either direction)
    for f in files:
        for d, e in dependents.get(path_id(f), []) + deps.get(path_id(f), []):
            if e["kind"] in ("imports", "tests-module") and d.startswith(("file:", "test:")) and d != path_id(f):
                near.setdefault(d.split(":", 1)[1], f)
    for f in files:
        near.pop(f, None)
    fr = finding_hits(g.root, files, [dict(rmap[r].data, id=r) for r in rids if r in rmap], near)
    secs.append(("Findings", [f"{p}  {why}" for p, why in fr], "knowledge/findings/INDEX.md"))

    avail = BRIEF_MAX - 1 - len(secs)
    rows = [max(len(r), 1) for _, r, _ in secs]
    quota = [0] * len(secs)
    left = avail
    while left > 0 and any(quota[i] < rows[i] for i in range(len(secs))):
        for i in range(len(secs)):
            if left > 0 and quota[i] < rows[i]:
                quota[i] += 1
                left -= 1
    out = [f"brief {wid}: {g.nodes[wid]['at']}  tier {tier_of(g, wid)[0]}"]
    for (name, r, more), q in zip(secs, quota):
        out.append(f"{name}:")
        if not r:
            out.append("  (none)")
        elif len(r) <= q:
            out += [f"  {x}" for x in r]
        else:
            keep = max(q - 1, 0)
            out += [f"  {x}" for x in r[:keep]]
            out.append(f"  ... {len(r) - keep} more ({more})")
    return [x[:200] for x in out]


def cmd_brief(g: Graph, wid: str) -> int:
    lines = brief_lines(g, wid) if WID_RE.match(wid) else None
    if lines is None:
        print(f"graph brief: no such work item: {wid}")
        return 2
    print("\n".join(lines))
    return 0


def cmd_tier(g: Graph, wid: str) -> int:
    """Covers: the review tier is chosen by hand and by feel; here it comes only from the affected paths, the kit and
    project tier-A path lists (tier-paths.json) and the import edges, never from a model's own confidence.
    The kit list holds only generic paths; money and order maths live in the project's own tier-paths.json."""
    if not WID_RE.match(wid) or wid not in g.nodes or g.nodes[wid]["kind"] != "work" or not g.nodes[wid].get("record"):
        print(f"graph tier: no such work item: {wid}")
        return 2
    try:
        t, why = tier_of(g, wid)
    except ValueError as exc:
        print(f"graph tier: {exc}")
        return 2
    print(f"{t}  {why}")
    note = tier_note(g, wid, t)
    if note:
        print(note)
    return 0


def utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(prog="graph.py", description="One project graph, built in memory from the records.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("root", nargs="?", default=".")
    b.add_argument("--json", action="store_true")
    li = sub.add_parser("lint")
    li.add_argument("root", nargs="?", default=".")
    li.add_argument("--strict", action="store_true")
    for name in ("impact", "why"):
        q = sub.add_parser(name)
        q.add_argument("target")
        q.add_argument("--root", default=".")
    pn = sub.add_parser("pin")
    pn.add_argument("work_item")
    pn.add_argument("--root", default=".")
    su = sub.add_parser("suspects")
    su.add_argument("root", nargs="?", default=".")
    for name in ("brief", "tier"):
        q = sub.add_parser(name)
        q.add_argument("work_item")
        q.add_argument("--root", default=".")
    a = sub.add_parser("affected")
    a.add_argument("--base", help="ref to diff against (required unless --files)")
    a.add_argument("--files", nargs="+", metavar="PATH", help="a changed-file set given directly instead of --base")
    a.add_argument("--committed-only", action="store_true", help="ignore staged, unstaged and untracked files")
    a.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if args.cmd == "pin":
        return cmd_pin(repo_root(args.root), args.work_item)
    if args.cmd == "suspects":
        return cmd_suspects(repo_root(args.root))
    g = build(args.root)
    if args.cmd == "build":
        return cmd_build(g, args.json)
    if args.cmd == "lint":
        return cmd_lint(g, args.strict)
    if args.cmd == "impact":
        return cmd_impact(g, args.target)
    if args.cmd == "why":
        return cmd_why(g, args.target)
    if args.cmd == "brief":
        return cmd_brief(g, args.work_item)
    if args.cmd == "tier":
        return cmd_tier(g, args.work_item)
    if not args.files and not args.base:
        ap.error("affected needs --base or --files")
    if args.files and args.base:
        print("graph affected: give --base or --files, not both")
        return 2
    return cmd_affected(g, args.base, not args.committed_only, args.files)


def _run() -> int:
    try:
        code = main()
        sys.stdout.flush()
        return code
    except BrokenPipeError:                      # `graph.py ... | head`: the reader left; exit quietly
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return 0


if __name__ == "__main__":
    utf8_stdout()
    sys.exit(_run())
