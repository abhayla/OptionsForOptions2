"""Reach check: verified evidence must test code the product calls.

Finding: verified-on-a-module-the-product-does-not-call.

Usage: python scripts/orchestrator/reach_check.py [--root DIR] [--baseline FILE | --no-baseline] [--json]

For every requirement whose status is Verified, or that an owning work item holds at in_review/done, each PASSING
evidence file (evidence/<W-id>/<AC-id>.md) names test files; each test file imports product modules (`ofo.*`,
`ofo_app.*`). The REACHED set is every product module transitively imported (by AST, import source never identifier
text) from the app entry modules. Per AC:
  REACHED     at least one named test file has EVERY subject module (below) in the reached set (printed nowhere);
  UNREACHED   every named test file has a subject module the app never reaches (those modules are listed);
  UNRESOLVED  the check cannot decide and fails closed: no python test file named, a named file missing or not
              parseable, an import it cannot resolve, a dynamic import (importlib.import_module, __import__) in a test
              file or in a reached module, or a test that imports no product module.
A test file's subject modules are its imports from the package named like its folder (tests/reconciliation/ ->
ofo.reconciliation.*), or all its imports when none match: shared helpers every test imports (ofo.engine) must not
make a test about an unreached module look reached.
Rules the resolver follows: `import a.b as c` and `from a import b` both resolve to module a.b when it exists;
relative imports resolve inside the package; importing a module also runs its parent packages' __init__ (re-exports);
imports under `if TYPE_CHECKING:` are not runtime imports and are skipped. Tests name files as `tests/x.py`,
`tests/x.py::name`, or a directory (every test_*.py below it); when the evidence names no python test, the work item's
`tests_required` line for that AC is used. Test helper modules imported by a test file are followed.
Output: one line per non-reached AC `UNREACHED|UNRESOLVED REQ-### W-### AC-n <test files> <modules>`, then counts.
Baseline (reach_check_baseline.json): accepted hits with a reason; exit 1 on a hit not in it AND on a baseline entry
that no longer occurs (the list only shrinks). Exit 2 on a setup fault (no entry module, unreadable baseline).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_ROOTS = ("ofo", "ofo_app")
#: App entry modules: the FastAPI app, and the processes started by name (`python -m ...`: feed, nightly jobs).
ENTRY_MODULES = ("ofo_app.main", "ofo_app.feed_main", "ofo_app.catalogue_load", "ofo_app.history_finalize")
#: Modules with a `__main__` guard that are test/dev seeding, not the product (allow-list: any other guarded module
#: not in ENTRY_MODULES is refused, so a new job cannot hide from the check).
NON_PRODUCT_RUNNERS = ("ofo_app.seed_execute_replay", "ofo_app.seed_test_catalogue")
DYNAMIC_NAMES = frozenset({"import_module", "__import__"})
SCOPE_WORK_STATUS = frozenset({"in_review", "done"})
BASELINE_NAME = "reach_check_baseline.json"
MIN_TEST_PATH_PARTS = 3  # tests/<area>/<file>.py
TEST_TOKEN = re.compile(r"(?:tests_app|tests)/[A-Za-z0-9_/.\-]*")


def _frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", text, re.M)
    return match.group(1).strip().strip("'\"") if match else None


def _frontmatter_list(text: str, key: str) -> list[str]:
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$((?:\n[ \t]*- .*)*)", text, re.M)
    if not match:
        return []
    inline = match.group(1).strip()
    if inline.startswith("["):
        return [p.strip().strip("'\"") for p in inline.strip("[]").split(",") if p.strip()]
    return [ln.strip()[2:].strip().strip("'\"") for ln in match.group(2).splitlines() if ln.strip()]


# --- product module index and import resolution -------------------------------------------------------------------

def build_index(root: Path) -> dict[str, tuple[Path | None, bool]]:
    """module name -> (file or None for a namespace directory, is_package) for backend/ofo and backend/ofo_app."""
    index: dict[str, tuple[Path | None, bool]] = {}
    for top in PRODUCT_ROOTS:
        base = root / "backend" / top
        if not base.is_dir():
            continue
        index[top] = (base / "__init__.py" if (base / "__init__.py").is_file() else None, True)
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(base).with_suffix("")
            parts = [top, *rel.parts]
            if parts[-1] == "__init__":
                index[".".join(parts[:-1])] = (path, True)
            else:
                index[".".join(parts)] = (path, False)
    return index


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _runtime_nodes(tree: ast.AST) -> Iterable[ast.AST]:
    """Every node except the body of an `if TYPE_CHECKING:` block."""
    stack = [tree]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            stack.extend(node.orelse)
            stack.append(node.test)
            continue
        stack.extend(ast.iter_child_nodes(node))


def _is_product(name: str) -> bool:
    return name.partition(".")[0] in PRODUCT_ROOTS


class _Scan:
    """What one source file imports: product modules found, plain names to follow, reasons it could not resolve."""

    def __init__(self, index: dict[str, tuple[Path | None, bool]]) -> None:
        self.index = index
        self.found: set[str] = set()
        self.plain: list[str] = []
        self.unresolved: list[str] = []

    def add_product(self, name: str) -> bool:
        if name in self.index:
            self.found.add(name)
            return True
        self.unresolved.append(f"unknown module {name}")
        return False

    def add_import(self, node: ast.Import) -> None:
        for alias in node.names:
            if _is_product(alias.name):
                self.add_product(alias.name)
            else:
                self.plain.append(alias.name)

    def add_from(self, node: ast.ImportFrom, module: str | None, package: str) -> None:
        if node.level and module is not None:  # inside backend: resolve against the package
            parts = package.split(".") if package else []
            keep = len(parts) - (node.level - 1)
            base = ".".join(parts[:keep] + ([node.module] if node.module else [])) if keep > 0 else ""
            if not base:
                self.unresolved.append(f"relative import beyond the package (level {node.level})")
                return
        else:  # absolute, or a relative import in a test file (a helper next to it)
            base = node.module or ""
        if base == "importlib" and any(a.name in DYNAMIC_NAMES for a in node.names):
            self.unresolved.append("dynamic import (importlib name imported)")
        if base and _is_product(base):
            if self.add_product(base):
                self.found.update(f"{base}.{a.name}" for a in node.names
                                  if a.name != "*" and f"{base}.{a.name}" in self.index)
            return
        self.plain.append(base)
        self.plain.extend(f"{base}.{a.name}" if base else a.name for a in node.names)


def scan_source(path: Path, module: str | None, is_pkg: bool, index: dict[str, tuple[Path | None, bool]]
                ) -> tuple[set[str], list[str], list[str]]:
    """(imported product modules, plain import names to follow, unresolved reasons) of one file.
    Raises SyntaxError/OSError."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    scan = _Scan(index)
    package = (module if is_pkg else module.rpartition(".")[0]) if module else ""
    for node in _runtime_nodes(tree):
        if isinstance(node, ast.Import):
            scan.add_import(node)
        elif isinstance(node, ast.ImportFrom):
            scan.add_from(node, module, package)
        elif (isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES) or (
                isinstance(node, ast.Attribute) and node.attr in DYNAMIC_NAMES):
            scan.unresolved.append("dynamic import (import_module / __import__)")
    return scan.found, scan.plain, sorted(set(scan.unresolved))


def _with_parents(module: str) -> list[str]:
    parts = module.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


def reached_closure(root: Path, index: dict[str, tuple[Path | None, bool]], entries: Iterable[str]
                    ) -> tuple[set[str], dict[str, list[str]]]:
    """Every product module transitively imported from the entry modules, and {module: reasons} for the ones whose
    imports could not be fully resolved (dynamic import, unknown module, unparseable file)."""
    reached: set[str] = set()
    problems: dict[str, list[str]] = {}
    queue = list(entries)
    while queue:
        name = queue.pop()
        for mod in _with_parents(name):
            if mod in reached or mod not in index:
                continue
            reached.add(mod)
            path, is_pkg = index[mod]
            if path is None:
                continue
            try:
                found, _plain, bad = scan_source(path, mod, is_pkg, index)
            except (SyntaxError, OSError, UnicodeDecodeError) as exc:
                problems[mod] = [f"unreadable: {type(exc).__name__}"]
                continue
            if bad:
                problems[mod] = bad
            queue.extend(found)
    return reached, problems


# --- tests, evidence, requirements ---------------------------------------------------------------------------------

def _clean_token(tok: str) -> str:
    return tok.rstrip(".-/") if not tok.endswith(".py") else tok


def named_test_files(root: Path, text: str) -> tuple[list[str], list[str]]:
    """(test python files named by `text`, tokens naming a python test that does not exist). Directories expand."""
    files: list[str] = []
    missing: list[str] = []
    for raw in TEST_TOKEN.findall(text):
        tok = _clean_token(raw)
        if tok.endswith(".py"):
            (files if (root / tok).is_file() else missing).append(tok)
        elif (root / tok).is_dir():
            files.extend(p.relative_to(root).as_posix() for p in sorted((root / tok).rglob("test_*.py")))
    return sorted(set(files)), sorted(set(missing))


def test_imports(root: Path, rel: str, index: dict[str, tuple[Path | None, bool]]
                 ) -> tuple[set[str], list[str]]:
    """Product modules a test file imports, following its helper modules; plus unresolved reasons (named)."""
    seen: set[Path] = set()
    found: set[str] = set()
    reasons: list[str] = []
    queue = [root / rel]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            mods, plain, bad = scan_source(path, None, False, index)
        except (SyntaxError, OSError, UnicodeDecodeError) as exc:
            reasons.append(f"{path.relative_to(root).as_posix()} unreadable: {type(exc).__name__}")
            continue
        found |= mods
        reasons += [f"{path.relative_to(root).as_posix()}: {r}" for r in bad]
        for dotted in plain:
            for cand in _helper_candidates(root, path, dotted):
                if cand.is_file():
                    queue.append(cand)
                    break
    return found, sorted(set(reasons))


def _helper_candidates(root: Path, path: Path, dotted: str) -> list[Path]:
    """Files a plain import of `dotted` could mean inside the test trees (next to the importer, or from the root)."""
    name = dotted.lstrip(".")
    if not name or name.split(".")[0] in PRODUCT_ROOTS:
        return []
    rel = Path(*name.split("."))
    out: list[Path] = []
    for cand in (path.parent / f"{rel}.py", root / f"{rel}.py"):
        try:
            top = cand.resolve().relative_to(root.resolve()).parts[0]
        except (ValueError, IndexError):
            continue
        if top in ("tests", "tests_app"):
            out.append(cand)
    return out


def load_scope(root: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    """({in-scope REQ: owning W ids}, {W id: text}). In scope: requirement Verified, or an owning W in_review/done."""
    owners: dict[str, set[str]] = {}
    work_text: dict[str, str] = {}
    scoped: set[str] = set()
    for path in sorted((root / "work").glob("W-*.md")):
        text = path.read_text(encoding="utf-8")
        wid = _frontmatter_value(text, "id") or path.stem
        work_text[wid] = text
        for req in _frontmatter_list(text, "requirement_ids"):
            owners.setdefault(req, set()).add(wid)
            if _frontmatter_value(text, "status") in SCOPE_WORK_STATUS:
                scoped.add(req)
    req_dir = root / ("sp" + "ec") / "requirements"
    for path in sorted(req_dir.glob("REQ-*.md")):
        text = path.read_text(encoding="utf-8")
        rid = _frontmatter_value(text, "id") or path.stem
        if _frontmatter_value(text, "status") == "Verified":
            scoped.add(rid)
    return {r: owners.get(r, set()) for r in sorted(scoped)}, work_text


def _tests_required_line(work_text: str, ac: str) -> str:
    match = re.search(rf"^[ \t]*-[ \t]*['\"]?{re.escape(ac)}:(.*)$", work_text, re.M)
    return match.group(1) if match else ""


def unclassified_runners(index: dict[str, tuple[Path | None, bool]]) -> list[str]:
    """Product modules with an `if __name__ == "__main__"` guard that are neither an entry nor a known seed script."""
    out = []
    for name, (path, _pkg) in sorted(index.items()):
        if path is None or name in ENTRY_MODULES or name in NON_PRODUCT_RUNNERS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            out.append(name)
            continue
        for node in tree.body:
            test = node.test if isinstance(node, ast.If) else None
            if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__":
                out.append(name)
    return out


def find_hits(root: Path) -> list[dict[str, str]]:
    index = build_index(root)
    entries = [m for m in ENTRY_MODULES if m in index]
    if not entries:
        raise SystemExit(f"reach_check: none of the entry modules {ENTRY_MODULES} exists under {root}")
    loose = unclassified_runners(index)
    if loose:
        raise SystemExit(f"reach_check: modules with a __main__ guard are neither an entry nor a seed script: {loose}")
    reached, problems = reached_closure(root, index, entries)
    scope, work_text = load_scope(root)
    hits: list[dict[str, str]] = []
    ctx = _Ctx(root, index, reached, problems)
    for req, works in scope.items():
        for wid in sorted(works):
            for ev in sorted((root / "evidence" / wid).glob("AC-*.md")) if (root / "evidence" / wid).is_dir() else []:
                text = ev.read_text(encoding="utf-8")
                if _frontmatter_value(text, "result") != "pass":
                    continue
                ac = _frontmatter_value(text, "ac") or ev.stem
                hit = _judge(ctx, text, work_text.get(wid, ""), ac)
                if hit:
                    hits.append({"req": req, "work": wid, "ac": ac, **hit,
                                 "key": f"{hit['kind']} {req} {wid} {ac}"})
    return hits


def _subject_modules(rel: str, imported: set[str], index: dict[str, tuple[Path | None, bool]]) -> set[str]:
    """The modules a test file is ABOUT: its imports from the package named like its folder (tests/reconciliation/
    -> ofo.reconciliation.*), else all of them. Shared helpers (ofo.engine, ofo.money) are imported by almost every
    test and the app reaches them, so counting them would let any test pass; a package imported only as the base of a
    `from pkg import module` is dropped when one of its modules is in the set."""
    leaves = {m for m in imported if m not in PRODUCT_ROOTS}
    leaves = {m for m in leaves if not (index[m][1] and any(o.startswith(m + ".") for o in leaves))}
    parts = Path(rel).parts
    if len(parts) >= MIN_TEST_PATH_PARTS and parts[0] == "tests":
        area = {f"{top}.{parts[1]}" for top in PRODUCT_ROOTS}
        own = {m for m in leaves if any(m == a or m.startswith(a + ".") for a in area)}
        if own:
            return own
    return leaves


class _Ctx:
    """Everything one run shares: the tree, the module index, the reached set and its problems, the import cache."""

    def __init__(self, root: Path, index: dict[str, tuple[Path | None, bool]], reached: set[str],
                 problems: dict[str, list[str]]) -> None:
        self.root, self.index, self.reached, self.problems = root, index, reached, problems
        self.cache: dict[str, tuple[set[str], list[str]]] = {}


def _undecided(subject: set[str], reasons: list[str], problems: dict[str, list[str]]) -> str | None:
    """Why the AC cannot be called UNREACHED (None when it can): fail-closed reasons, in order."""
    if reasons:
        return "; ".join(reasons)
    if not subject:
        return "test imports no product module"
    if problems:
        names = ", ".join(f"{m} ({r[0]})" for m, r in sorted(problems.items()))
        return f"a reached module has an unresolvable import: {names}"
    return None


def _judge(ctx: _Ctx, evidence: str, work: str, ac: str) -> dict[str, str] | None:
    files, missing = named_test_files(ctx.root, evidence)
    if not files and not missing:
        files, missing = named_test_files(ctx.root, _tests_required_line(work, ac))
    tests = ", ".join(files + missing) or "-"
    if missing or not files:
        why = f"named test file missing: {missing}" if missing else "evidence names no python test file"
        return {"kind": "UNRESOLVED", "tests": tests, "modules": "-", "detail": why}
    subject: set[str] = set()
    reasons: list[str] = []
    for rel in files:
        if rel not in ctx.cache:
            ctx.cache[rel] = test_imports(ctx.root, rel, ctx.index)
        mods, why = ctx.cache[rel]
        own = _subject_modules(rel, mods, ctx.index)
        if own and own <= ctx.reached:
            return None  # one test file whose every subject module the app reaches backs this AC
        subject |= own - ctx.reached
        reasons += why
    names = ",".join(sorted(subject)) or "-"
    undecided = _undecided(subject, reasons, ctx.problems)
    if undecided:
        return {"kind": "UNRESOLVED", "tests": tests, "modules": names if subject else "-", "detail": undecided}
    return {"kind": "UNREACHED", "tests": tests, "modules": names, "detail": "no app entry reaches them"}


# --- baseline and output -------------------------------------------------------------------------------------------

def load_baseline(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError("baseline must be an object with an `entries` list")
    out: dict[str, dict[str, str]] = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"key", "reason", "issue"} or not all(
                isinstance(v, str) and v.strip() for v in item.values()):
            raise ValueError(f"baseline entry needs exactly a non-empty key, reason and issue: {item!r}")
        if item["key"] in out:
            raise ValueError(f"duplicate baseline entry {item['key']}")
        out[item["key"]] = item
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--baseline", type=Path, default=None)
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    baseline: dict[str, dict[str, str]] = {}
    if not args.no_baseline:
        path = args.baseline or (root / "scripts" / "orchestrator" / BASELINE_NAME)
        try:
            baseline = load_baseline(path)
        except (OSError, ValueError) as exc:
            print(f"reach_check: cannot use the baseline {path}: {exc}", file=sys.stderr)
            return 2
    hits = find_hits(root)
    keys = {h["key"] for h in hits}
    new = [h for h in hits if h["key"] not in baseline]
    stale = sorted(k for k in baseline if k not in keys)
    counts = {"UNREACHED": 0, "UNRESOLVED": 0}
    for h in hits:
        counts[h["kind"]] += 1
    if args.json:
        print(json.dumps({"hits": hits, "new": [h["key"] for h in new], "stale": stale, "counts": counts}, indent=1))
    else:
        for h in hits:
            tag = "" if h["key"] in baseline else "  [NEW]"
            print(f"{h['kind']} {h['req']} {h['work']} {h['ac']} {h['tests']} {h['modules']}{tag}")
        for k in stale:
            print(f"STALE baseline entry no longer occurs: {k}")
        print(f"reach_check: UNREACHED {counts['UNREACHED']}, UNRESOLVED {counts['UNRESOLVED']}, "
              f"new {len(new)}, stale baseline {len(stale)}")
    return 1 if new or stale else 0


if __name__ == "__main__":
    sys.exit(main())
