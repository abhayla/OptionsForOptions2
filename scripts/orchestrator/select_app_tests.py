"""Pick the tests_app files a backend change can break (issue #242, finding targeted-tests-miss-dependent-files).

select(changed_files, diff_text, tests_dir, read_source=None, route_files=None) -> ["tests_app/test_x.py", ...]
  read_source(rel_path) -> text of a backend file (default: the working tree under the repo root)
  route_files           -> rel paths of backend/ofo_app/routes/*.py (default: listed from the working tree)

Coarse and safe, file level (no call graph):
  A. a changed file under backend/ofo_app/routes/ that defines routes -> keys = EVERY route path it defines (with its
     router's prefix) + every class name it defines + its own module name.
     A changed non-route file under backend/ofo_app/ (store, helper, live_market, ...) -> keys = its module name as
     imported (`ofo_app.x`, `from ofo_app import x`) PLUS, for every route file that imports it, that route file's
     keys (one level of import reachability).
     A changed non-route file under backend/ofo/ (domain modules) is handled the same way (module key `ofo.x.y`; an
     `__init__.py` keys on its package).
     A changed migration under backend/ofo_app/alembic/ selects a FIXED set: every tests_app file named *migration*
     plus every one whose text mentions alembic, NEW_PINS or the migration replay helper (MIGRATION_TEXT).
     Only one filter: a file whose +/- lines are all comments, blank lines or docstrings selects nothing.
  B. a tests_app file is selected when it contains any key: a route path as a string literal / f-string prefix, a
     class name as a word, a module import.
  C. fail closed: a diff that cannot be read (binary, rename only, a changed file missing from the diff, an
     unparseable file, a route path that is not a literal) raises DiffNotParsed; the caller treats it as an error.
     MAX_FILES bounds what the CLI / atool will run against the production-host database.

Known blind spots (not chased): no call graph (a change two imports away from a test is not reached; a route handler's
helper in another module is reached only through the route file that imports it); module names built as strings
(f"ofo.x.{n}" is matched by its literal prefix only); non-Python files under backend/ (catalogue.yaml, JSON schemas)
select nothing; a selection above MAX_FILES is NOT truncated here, atool.py refuses it (the red run 40132982617 had its
file selected but over the cap).

CLI: python select_app_tests.py <worktree>   (diff = git diff origin/main...HEAD -- backend/; exit 3 if not parsed)
"""
import ast
import collections
import dataclasses
import os
import re
import subprocess
import sys

SCOPES = ("backend/ofo_app/", "backend/ofo/")
MIGRATIONS_DIR = "backend/ofo_app/alembic/"
ROUTES_DIR = "backend/ofo_app/routes/"
MAX_FILES = 12
#: a changed migration selects a FIXED set: every tests_app file named *migration* plus every file whose text mentions
#: alembic, NEW_PINS (the validator pins a migration publishes) or the migration replay helper
MIGRATION_TEXT = re.compile(r"\balembic\b|NEW_PINS|_migration_replay")
_METHODS = {"get", "post", "put", "delete", "patch", "websocket"}


class DiffNotParsed(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Key:
    name: str  # a class name, a route path template, or a dotted module name
    kind: str  # "name" | "route" | "module"

    def regex(self) -> "re.Pattern[str]":
        if self.kind == "name":
            return re.compile(r"\b" + re.escape(self.name) + r"\b")
        if self.kind == "migration":
            return MIGRATION_TEXT
        if self.kind == "module" and "." not in self.name:
            return re.compile(r"\b" + re.escape(self.name) + r"\b")  # a top-level package: any mention
        if self.kind == "module":
            pkg, mod = self.name.rsplit(".", 1)
            p, m = re.escape(pkg), re.escape(mod)
            return re.compile(rf"\b{p}\.{m}\b|from {p} import (?:\([^)]*\b{m}\b[^)]*\)|[^\n]*\b{m}\b)")
        seg = r"(?:\{[^}/]*\}|[^/\"'{}\s?]+)"
        body = "".join(seg if p.startswith("{") else re.escape(p)
                       for p in re.split(r"(\{[^}]*\})", self.name) if p)
        return re.compile(r"[\"']" + body + r"[\"'?]")


def _norm(line: str) -> str:
    code = re.sub(r"\s+#.*$", "", line.strip())
    return "" if code.startswith("#") else code


DELETED = "deleted"  # parse_diff's value for a file the diff deletes (its hunk's new side starts at 0)


def parse_diff(diff_text: str) -> dict:
    """{path: [new-side line numbers of code changes], None if no hunk, DELETED if the diff deletes the file};
    raises DiffNotParsed on binary diffs."""
    if "Binary files" in diff_text or "GIT binary patch" in diff_text:
        raise DiffNotParsed("binary file in diff")
    out: dict = {}
    path = None
    hunk: list = []
    start = 0

    def flush() -> None:
        if path is None or not hunk or out[path] == DELETED:
            return
        plus_c = collections.Counter(_norm(t) for k, t, _ in hunk if k == "+")
        minus_c = collections.Counter(_norm(t) for k, t, _ in hunk if k == "-")
        left = {"+": plus_c & minus_c, "-": plus_c & minus_c}  # code present on both sides: comment-only / moved
        if out[path] is None:
            out[path] = []
        for k, t, n in hunk:
            v = _norm(t)
            if k == " " or not v:
                continue
            if left[k][v] > 0:
                left[k][v] -= 1
                continue
            out[path].append(n)

    for line in (l.rstrip("\r") for l in diff_text.split("\n")):
        if line.startswith("diff --git "):
            flush()
            hunk = []
            start = 0
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            path = m.group(2) if m else None
            if path is not None and path in out:  # the same path twice (delete + add): never guess which wins
                raise DiffNotParsed(f"{path} appears twice in the diff")
            if path is not None:
                out.setdefault(path, None)
        elif path is not None and line.startswith("deleted file mode"):
            out[path] = DELETED
        elif line.startswith("@@"):
            flush()
            hunk = []
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if not m:
                raise DiffNotParsed(f"bad hunk header: {line}")
            start = int(m.group(1))
        elif path is not None and start and line[:1] in ("+", "-", " ") and not line.startswith(("+++", "---")):
            hunk.append((line[0], line[1:], start))
            if line[0] != "-":
                start += 1
    flush()
    return out


def _docstring_lines(tree: ast.Module) -> set:
    lines: set = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            first = n.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def _module_name(rel: str) -> str:
    name = rel[len("backend/"):-len(".py")].replace("/", ".")
    return name[:-len(".__init__")] if name.endswith(".__init__") else name


def _string_constants(tree: ast.Module) -> dict:
    return {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str) for t in n.targets if isinstance(t, ast.Name)}


def _routes_and_classes(rel: str, source: str) -> tuple:
    """(route paths with their router's prefix, class names) of a module; DiffNotParsed on an unresolvable path."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise DiffNotParsed(f"{rel}: {e}") from e
    consts = _string_constants(tree)
    prefixes = {}  # router variable -> prefix
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            if getattr(f, "id", getattr(f, "attr", "")) == "APIRouter":
                pre = ""
                for kw in n.value.keywords:
                    if kw.arg == "prefix":
                        if not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)):
                            raise DiffNotParsed(f"{rel}: router prefix is not a literal")
                        pre = kw.value.value
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        prefixes[t.id] = pre
    routes, classes = [], []
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n in tree.body:
            classes.append(n.name)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in n.decorator_list:
            if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _METHODS
                    and isinstance(d.func.value, ast.Name)):
                continue
            var = d.func.value.id
            if var not in prefixes:
                continue
            arg = d.args[0] if d.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                path = arg.value
            elif isinstance(arg, ast.Name) and arg.id in consts:
                path = consts[arg.id]
            else:
                raise DiffNotParsed(f"{rel}: route decorator on {n.name} has no literal path")
            routes.append(prefixes[var] + path)
    return routes, classes


def _read_tree(root):
    return lambda rel: open(os.path.join(str(root), rel), encoding="utf-8").read()


def _list_routes(root) -> list:
    d = os.path.join(str(root), ROUTES_DIR)
    return sorted(ROUTES_DIR + n for n in os.listdir(d) if n.endswith(".py") and n != "__init__.py")


def _route_keys(rel: str, source: str) -> list:
    routes, classes = _routes_and_classes(rel, source)
    if not routes:
        return []
    return ([Key(p, "route") for p in routes] + [Key(c, "name") for c in classes]
            + [Key(_module_name(rel), "module")])


def keys_for(changed_files, diff_text: str, root, read_source=None, route_files=None) -> list:
    read_source = read_source or _read_tree(root)
    parsed = parse_diff(diff_text)
    keys: list = []
    route_cache: dict = {}

    def routes_of(rel: str) -> list:
        if rel not in route_cache:
            try:
                route_cache[rel] = _route_keys(rel, read_source(rel))
            except OSError as e:
                raise DiffNotParsed(f"{rel}: {e}") from e
        return route_cache[rel]

    def _module_and_importers(f: str) -> list:
        mod = Key(_module_name(f), "module")
        found = [mod]
        for rf in (route_files if route_files is not None else _list_routes(root)):
            if rf != f and mod.regex().search(read_source(rf)):
                found += routes_of(rf)  # one level of import reachability
        return found

    for f in changed_files:
        if not (f.startswith(SCOPES) and f.endswith(".py")):
            continue
        if f not in parsed:
            raise DiffNotParsed(f"{f} changed but is absent from the diff")
        if parsed[f] is None:
            raise DiffNotParsed(f"{f} has no hunk in the diff (rename or mode change only)")
        if parsed[f] == DELETED:  # no source left to read
            if f.startswith(MIGRATIONS_DIR):
                keys.append(Key("migration", "migration"))  # the fixed set, as for a changed migration
            elif f.startswith(ROUTES_DIR):
                raise DiffNotParsed(f"{f} deleted: its route paths cannot be read back")
            else:
                keys += _module_and_importers(f)  # key on the module name: a test still importing it runs
            continue
        try:
            source = read_source(f)
            real = set(parsed[f]) - _docstring_lines(ast.parse(source))
        except (OSError, SyntaxError) as e:
            raise DiffNotParsed(f"{f}: {e}") from e
        if not real:
            continue  # only comments, blank lines, docstrings
        if f.startswith(MIGRATIONS_DIR):
            keys.append(Key("migration", "migration"))  # fixed set, see migration_tests()
            continue
        own = routes_of(f) if f.startswith(ROUTES_DIR) else []
        if own:
            keys += own
            continue
        keys += _module_and_importers(f)
    return list(dict.fromkeys(keys))


def select_by_key(changed_files, diff_text: str, tests_dir, read_source=None, route_files=None) -> dict:
    tests_dir = os.fspath(tests_dir)
    root = os.path.dirname(os.path.abspath(tests_dir))
    base = os.path.basename(os.path.abspath(tests_dir))
    texts = {}
    for n in sorted(os.listdir(tests_dir)):
        if n.startswith("test_") and n.endswith(".py"):
            texts[f"{base}/{n}"] = open(os.path.join(tests_dir, n), encoding="utf-8").read()
    def hit(k: Key, p: str, t: str) -> bool:
        return bool(k.regex().search(t)) or (k.kind == "migration" and "migration" in os.path.basename(p))

    return {k.name: [p for p, t in texts.items() if hit(k, p, t)]
            for k in keys_for(changed_files, diff_text, root, read_source, route_files)}


def select(changed_files, diff_text: str, tests_dir, read_source=None, route_files=None) -> list:
    chosen: set = set()
    for files in select_by_key(changed_files, diff_text, tests_dir, read_source, route_files).values():
        chosen.update(files)
    return sorted(chosen)


def main(argv: list) -> int:
    wt = os.path.abspath(argv[0] if argv else ".")
    names = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD", "--", "backend/"], cwd=wt,
                           capture_output=True, text=True)
    diff = subprocess.run(["git", "diff", "origin/main...HEAD", "--", "backend/"], cwd=wt, capture_output=True,
                          text=True, encoding="utf-8")
    if names.returncode or diff.returncode:
        print(f"route tests: git diff failed (rc {names.returncode}/{diff.returncode}) - run the route files by hand")
        return 3
    try:
        picked = select(names.stdout.splitlines(), diff.stdout, os.path.join(wt, "tests_app"))
    except DiffNotParsed as e:
        print(f"route tests: diff not parsed - run the route files by hand ({e})")
        return 3
    print(f"{len(picked)} files\n" + "\n".join(picked))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
