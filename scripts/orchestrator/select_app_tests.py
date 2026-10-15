"""Pick the tests_app files a backend route / response-model change can break (issue #242, finding
targeted-tests-miss-dependent-files).

select(changed_files, diff_text, tests_dir, read_source=None) -> ["tests_app/test_x.py", ...]
(read_source(rel_path) -> text of a changed file; default reads the working tree under the repo root)

Precision first: keys come from what the diff CHANGED, not from every name in a touched file.
  - a class (response model, dataclass) with a real +/- line in a hunk  -> its name
  - a route function with a real +/- line (decorator included)          -> its route path
  - a private helper with a real +/- line                               -> the routes / public functions that use it
  - a public function with a real +/- line                              -> its name
A "real" line is one whose code changes: blank lines, comment lines and trailing-comment edits do not count.
A test file is selected when it names a changed class/function (word match) or writes an exact route path as a
string ("/strategies", f"/strategies/{sid}", "/strategies/3").
A diff the parser cannot read (binary, rename only, a changed backend file missing from the diff) raises
DiffNotParsed: never a silent empty selection.

CLI: python select_app_tests.py <worktree>   (diff = git diff origin/main...HEAD -- backend/; exit 3 if not parsed)
"""
import ast
import collections
import dataclasses
import os
import re
import subprocess
import sys

SCOPE = "backend/ofo_app/"
_METHODS = {"get", "post", "put", "delete", "patch", "websocket"}


class DiffNotParsed(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Key:
    name: str  # a class/function name, or a route path template
    kind: str  # "name" | "route"

    def regex(self) -> "re.Pattern[str]":
        if self.kind == "name":
            return re.compile(r"\b" + re.escape(self.name) + r"\b")
        seg = r"(?:\{[^}/]*\}|[^/\"'{}\s?]+)"
        body = "".join(seg if p.startswith("{") else re.escape(p)
                       for p in re.split(r"(\{[^}]*\})", self.name) if p)
        return re.compile(r"[\"']" + body + r"[\"'?]")


def _norm(line: str) -> str:
    code = re.sub(r"\s+#.*$", "", line.strip())
    return "" if code.startswith("#") else code


def parse_diff(diff_text: str) -> dict:
    """{path: [new-side line numbers of real changes], None if no hunk}; raises DiffNotParsed on binary diffs."""
    if "Binary files" in diff_text or "GIT binary patch" in diff_text:
        raise DiffNotParsed("binary file in diff")
    out: dict = {}
    path = None
    hunk: list = []
    start = 0

    def flush() -> None:
        if path is None or not hunk:
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
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            path = m.group(2) if m else None
            if path is not None:
                out.setdefault(path, None)
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


def _decorator_routes(node: ast.AST, prefix: str) -> list:
    paths = []
    for d in getattr(node, "decorator_list", []):
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _METHODS
                and d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str)):
            paths.append(prefix + d.args[0].value)
    return paths


def _router_prefix(tree: ast.Module) -> str:
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            f = n.value.func
            if getattr(f, "id", getattr(f, "attr", "")) == "APIRouter":
                for kw in n.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return str(kw.value.value)
    return ""


def _span(node: ast.AST) -> tuple:
    first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return first, node.end_lineno


def _file_keys(source: str, lines: list) -> list:
    tree = ast.parse(source)
    prefix = _router_prefix(tree)
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    changed: set = set()  # names of top-level nodes with a real change
    keys: list = []
    for n in tree.body:
        if not isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a, b = _span(n)
        if any(a <= ln <= b for ln in lines):
            changed.add(n.name)
    uses = {name: {x.id for x in ast.walk(f) if isinstance(x, ast.Name)} for name, f in funcs.items()}
    grew = True
    while grew:  # a changed private helper reaches whatever calls it
        grew = False
        for name in list(funcs):
            if name not in changed and any(h in uses[name] for h in changed if h.startswith("_") and h in funcs):
                changed.add(name)
                grew = True
    for n in tree.body:
        if not isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or n.name not in changed:
            continue
        if isinstance(n, ast.ClassDef):
            keys.append(Key(n.name, "name"))
        elif _decorator_routes(n, prefix):
            keys += [Key(p, "route") for p in _decorator_routes(n, prefix)]
        elif not n.name.startswith("_"):
            keys.append(Key(n.name, "name"))
    return keys


def _read_tree(root):
    return lambda rel: open(os.path.join(str(root), rel), encoding="utf-8").read()


def keys_for(changed_files, diff_text: str, root, read_source=None) -> list:
    read_source = read_source or _read_tree(root)
    parsed = parse_diff(diff_text)
    keys: list = []
    for f in changed_files:
        if not (f.startswith(SCOPE) and f.endswith(".py")):
            continue
        if f not in parsed:
            raise DiffNotParsed(f"{f} changed but is absent from the diff")
        if parsed[f] is None:
            raise DiffNotParsed(f"{f} has no hunk in the diff (rename or mode change only)")
        if not parsed[f]:
            continue
        try:
            source = read_source(f)
            keys += _file_keys(source, parsed[f])
        except (OSError, SyntaxError) as e:
            raise DiffNotParsed(f"{f}: {e}") from e
    return list(dict.fromkeys(keys))


def select_by_key(changed_files, diff_text: str, tests_dir, read_source=None) -> dict:
    tests_dir = os.fspath(tests_dir)
    root = os.path.dirname(os.path.abspath(tests_dir))
    base = os.path.basename(os.path.abspath(tests_dir))
    texts = {}
    for n in sorted(os.listdir(tests_dir)):
        if n.startswith("test_") and n.endswith(".py"):
            texts[f"{base}/{n}"] = open(os.path.join(tests_dir, n), encoding="utf-8").read()
    return {k.name: [p for p, t in texts.items() if k.regex().search(t)]
            for k in keys_for(changed_files, diff_text, root, read_source)}


def select(changed_files, diff_text: str, tests_dir, read_source=None) -> list:
    chosen: set = set()
    for files in select_by_key(changed_files, diff_text, tests_dir, read_source).values():
        chosen.update(files)
    return sorted(chosen)


def main(argv: list) -> int:
    wt = os.path.abspath(argv[0] if argv else ".")
    names = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD", "--", "backend/"], cwd=wt,
                           capture_output=True, text=True).stdout.splitlines()
    diff = subprocess.run(["git", "diff", "origin/main...HEAD", "--", "backend/"], cwd=wt, capture_output=True,
                          text=True, encoding="utf-8").stdout
    try:
        by_key = select_by_key(names, diff, os.path.join(wt, "tests_app"))
    except DiffNotParsed as e:
        print(f"route tests: diff not parsed - run the route files by hand ({e})")
        return 3
    for k, v in by_key.items():
        print(f"{k}: {len(v)} files")
    print("\n".join(select(names, diff, os.path.join(wt, "tests_app"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
