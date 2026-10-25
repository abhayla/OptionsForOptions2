"""REQ-052 AC-1 / ADR-066: no historical market data is shown to users.

History (the recorded minute bars and Kite's historical candles) is internal use only: gap-filling, tests and replays.
So no API route and no frontend page may reach a history reader. The scan is an ALLOW-LIST: the exact set of backend
modules that may import a history module is written below; any other importer fails, and so does any import shape the
scan cannot resolve (finding guard-as-forbidden-list). frontend/src may request no history/candles path and import no
history module (allowed set: empty). Source is read with ``ast`` (backend) or text (frontend); nothing is imported, so
the kit CI needs no FastAPI.

Out of scope (threat model): internal jobs, tests, scripts, forged imports built by importlib from a computed string
that a literal check cannot see (a non-literal call is flagged, not followed).
"""
import ast
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND_SRC = ROOT / "frontend" / "src"

# The history readers. Guard is named by import source (dotted module), not by identifier text.
HISTORY_MODULES = ("ofo.history", "ofo_app.history_finalize", "ofo_app.history_store", "ofo_app.kite_history")

# ALLOW-LIST: the only modules that may import a history module. Verified by grep on origin/main: nothing outside this
# set imports one (broker/kite_endpoints.py only names the history URL as a string in its endpoint table, no import).
ALLOWED_IMPORTERS = frozenset({
    "ofo.history",                  # package marker (the history package itself)
    "ofo.history.bars",             # minute-bar types
    "ofo.history.candles",          # candle parsing (imports bars)
    "ofo.history.finalize",         # gap-fill finaliser (internal job logic)
    "ofo.history.recorder",         # live-frame recorder (internal)
    "ofo.history.store",            # store contract + in-memory store
    "ofo_app.history_finalize",     # the finaliser job entry point (python -m ofo_app.history_finalize)
    "ofo_app.history_store",        # PostgreSQL store, used by the finaliser
    "ofo_app.kite_history",         # Kite historical client, used by the finaliser
})
# frontend/src may request or import no history at all.
ALLOWED_FRONTEND: frozenset[str] = frozenset()
# String literals that hold the word "history" for the USER'S OWN records, not market data (exact file + literal; the
# nav lists the user's executed-order history and fired-alert history pages). Anything else fails the word scan.
ALLOWED_FRONTEND_WORDS = frozenset({
    ("router/nav.js", "execution-history"),
    ("router/nav.js", "history"),
    ("router/nav.js", "History"),
    ("router/routes.js", "alerts-history"),  # route name of the Alerts > History page (fired alerts, REQ-009 AC-6)
    ("lib/brokerCapabilities.js", "intraday_product"),  # a broker flag name (REQ-117): MIS support
    ("pages/BrokerSettingsPage.vue", "history-statement"),  # test id of the "not available" sentence (ADR-066)
})

# The ONE request path exempt from the path scan (REQ-070 AC-5): the user's OWN strategy activity (the saved edits of a
# strategy they made), not market data, so ADR-066 does not apply. Exact (file, literal) pair: the same literal in any
# other file, any other history literal in this file, a concatenated or imported one, all still fail.
ALLOWED_FRONTEND_PATHS = frozenset({
    ("lib/strategyActivity.js", "/strategies/${id}/history"),
})

WIDE_PACKAGES = {"ofo", "ofo_app"}  # `from ofo_app import *` could pull a history module in: unresolvable, so flagged
# Dynamic-import sources, named by what the call RESOLVES to through the module's imports (not by identifier text):
DYNAMIC_ROOTS = ("importlib", "runpy")  # any attribute of these modules
DYNAMIC_BUILTINS = {"__import__", "builtins.__import__"}
LITERAL_CHECKED = {"importlib.import_module", "importlib.__import__", "runpy.run_module", "__import__",
                   "builtins.__import__"}  # calls whose target module name is read; every other dynamic call is flagged
STAR_SOURCES = {"importlib", "runpy", "builtins"}
# Loaders that take a FILE PATH, not a module name: the scan cannot see which module they load, so they are flagged
# ("path-loader ...") and only the folders listed here may use them (Alembic loads its sibling migration by path).
PATH_LOADERS = {"importlib.util.spec_from_file_location", "importlib.util.module_from_spec"}
PATH_LOADER_FOLDERS = ("ofo_app.alembic.versions.",)


def _is_history(dotted: str) -> bool:
    return any(dotted == m or dotted.startswith(m + ".") for m in HISTORY_MODULES)


def _package_of(module: str, is_package: bool) -> list[str]:
    parts = module.split(".")
    return parts if is_package else parts[:-1]


def _from_hits(node: ast.ImportFrom, module: str, is_package: bool) -> list[str]:
    base = node.module or ""
    if node.level:
        pkg = _package_of(module, is_package)
        if node.level - 1 > len(pkg):
            return [f"unresolvable relative import at line {node.lineno}"]
        pkg = pkg[: len(pkg) - (node.level - 1)]
        base = ".".join(pkg + ([node.module] if node.module else []))
    if _is_history(base):
        return [f"from {base} import ..."]
    star = base in WIDE_PACKAGES and any(a.name == "*" for a in node.names)
    hits = [f"star import from {base} at line {node.lineno}"] if star else []
    return hits + [f"from {base} import {a.name}" for a in node.names if _is_history(f"{base}.{a.name}")]


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> dotted import source, for absolute imports (``import importlib.util`` binds ``importlib``)."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _resolve(expr: ast.AST, aliases: dict[str, str]) -> str:
    """The dotted import source an expression names ('' when it is not a plain name/attribute chain)."""
    if isinstance(expr, ast.Name):
        return aliases.get(expr.id, expr.id)
    if isinstance(expr, ast.Attribute):
        base = _resolve(expr.value, aliases)
        return f"{base}.{expr.attr}" if base else ""
    return ""


def _is_dynamic(dotted: str) -> bool:
    return dotted in DYNAMIC_BUILTINS or any(dotted == r or dotted.startswith(r + ".") for r in DYNAMIC_ROOTS)


def _str_value(expr: ast.AST | None) -> str | None:
    return expr.value if isinstance(expr, ast.Constant) and isinstance(expr.value, str) else None


def _absolute(name: str, package: str | None) -> str | None:
    """importlib.util.resolve_name for a literal: None when a relative name has no literal package."""
    if not name.startswith("."):
        return name
    if not package:
        return None
    dots = len(name) - len(name.lstrip("."))
    parts = package.split(".")
    if dots - 1 >= len(parts):
        return None
    return ".".join(parts[: len(parts) - (dots - 1)] + [name[dots:]] * bool(name[dots:]))


def _arg(node: ast.Call, pos: int, *kws: str) -> ast.AST | None:
    if len(node.args) > pos:
        return node.args[pos]
    return next((k.value for k in node.keywords if k.arg in kws), None)


def _is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _unreadable_args(node: ast.Call, dotted: str) -> bool:
    """True when a call's arguments cannot be read statically (not a checked importer, starred, or ``**kw``)."""
    return (dotted not in LITERAL_CHECKED or any(isinstance(a, ast.Starred) for a in node.args)
            or any(k.arg is None for k in node.keywords))


def _package_problem(node: ast.Call, dotted: str) -> tuple[str | None, str | None]:
    """(package, problem) for ``import_module`` / ``__import__``: a non-literal package or level is a problem."""
    if dotted.endswith("import_module"):
        pkg_node = _arg(node, 1, "package")
        package = _str_value(pkg_node)
        bad = pkg_node is not None and package is None and not _is_none_constant(pkg_node)
        return package, ("non-literal package in" if bad else None)
    if dotted.endswith("__import__"):
        level = _arg(node, 4, "level")
        bad = level is not None and not (isinstance(level, ast.Constant) and level.value == 0)
        return None, ("relative or non-literal level in" if bad else None)
    return None, None


def _fromlist_names(node: ast.Call, dotted: str, base: str) -> list[str] | None:
    """The module names a ``__import__`` fromlist adds to ``base``; None when it is not a literal list of strings."""
    fromlist = _arg(node, 3, "fromlist") if dotted.endswith("__import__") else None
    if fromlist is None:
        return []
    items = fromlist.elts if isinstance(fromlist, (ast.List, ast.Tuple)) else None
    if items is None or not all(_str_value(i) is not None for i in items):
        return None
    return [f"{base}.{_str_value(i)}" for i in items]


def _module_base(node: ast.Call, dotted: str) -> tuple[str | None, str]:
    """(absolute module name, "") when the call names its module by literals; else (None, why not)."""
    if _unreadable_args(node, dotted):
        return None, "unresolvable"
    name = _str_value(_arg(node, 0, "name", "mod_name", "module_name"))
    if name is None:
        return None, "non-literal"
    package, problem = _package_problem(node, dotted)
    if problem:
        return None, problem
    base = _absolute(name, package)
    return (base, "") if base is not None else (None, "unresolvable relative name in")


def _dynamic_call_hits(node: ast.Call, dotted: str) -> list[str]:
    """A dynamic import is read only when its module name (and fromlist/package/level) are literals; else flagged."""
    line = f"{dotted}() at line {node.lineno}"
    if dotted in PATH_LOADERS:
        return [f"path-loader {line}"]
    base, problem = _module_base(node, dotted)
    if base is None:
        return [f"{problem} {line}"]
    more = _fromlist_names(node, dotted, base)
    if more is None:
        return [f"non-literal fromlist in {line}"]
    hit = next((n for n in [base, *more] if _is_history(n)), None)
    return [f"{dotted}({hit!r})"] if hit else []


def _dynamic_hits(tree: ast.AST, aliases: dict[str, str]) -> list[str]:
    """Calls AND bare references (``f = importlib.import_module``, ``getattr(importlib, ...)``) that resolve to a
    dynamic-import source by import. Fail closed: a reference we cannot follow is flagged."""
    hits: list[str] = []
    inner: set[int] = set()  # nodes that are only the base of a longer chain, or the callee of a call (handled once)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            inner.add(id(node.value))
        elif isinstance(node, ast.Call):
            inner.add(id(node.func))
            dotted = _resolve(node.func, aliases)
            if _is_dynamic(dotted):
                hits += _dynamic_call_hits(node, dotted)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner:
            if _is_dynamic(_resolve(node, aliases)):
                hits.append(f"reference to {_resolve(node, aliases)} (not a direct call) at line {node.lineno}")
        elif (isinstance(node, ast.ImportFrom) and not node.level and node.module in STAR_SOURCES
              and any(a.name == "*" for a in node.names)):
            hits.append(f"star import from {node.module} at line {node.lineno}")
    return hits


def import_hits(source: str, module: str, is_package: bool = False) -> list[str]:
    """Every history import, or unresolvable import shape, in one backend module's source (empty = clean)."""
    hits: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [f"import {a.name}" for a in node.names if _is_history(a.name)]
        elif isinstance(node, ast.ImportFrom):
            hits += _from_hits(node, module, is_package)
    return hits + _dynamic_hits(tree, _aliases(tree))


def scan_backend(backend: Path) -> dict[str, list[str]]:
    """Dotted module name -> hits, for every module under ``backend`` that has any."""
    found: dict[str, list[str]] = {}
    for path in sorted(backend.rglob("*.py")):
        rel = path.relative_to(backend).with_suffix("")
        is_package = rel.name == "__init__"
        module = ".".join(rel.parent.parts if is_package else rel.parts)
        hits = import_hits(path.read_text(encoding="utf-8"), module, is_package)
        if hits:
            found[module] = hits
    return found


def disallowed(found: dict[str, list[str]], allowed: frozenset[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for m, h in found.items():
        if m in allowed:
            continue
        kept = [x for x in h if not x.startswith("path-loader ")] if m.startswith(PATH_LOADER_FOLDERS) else h
        if kept:
            out[m] = kept
    return out


# frontend: a path-like string literal with a history/candle segment, or an import of such a module
_HISTORY_WORD = r"(?:history|historical|intraday|candles?|ohlc\w*|kite_history|history_store|history_finalize)"
_PATH_LITERAL = re.compile(r"""['"`][^'"`\n]*/[^'"`\n]*\b""" + _HISTORY_WORD + r"""\b[^'"`\n]*['"`]""", re.IGNORECASE)
# any string literal WITHOUT whitespace (a key, path, kind or id; prose labels have spaces) holding a history word,
# the word delimited by non-letters so ``kite_history`` and ``/historical`` match but ``createWebHistory`` does not
_LITERAL = re.compile(r"""'([^'\n\s]*)'|"([^"\n\s]*)"|`([^`\n\s]*)`""")
_WORD = re.compile(r"(?<![A-Za-z])" + _HISTORY_WORD + r"(?![A-Za-z])", re.IGNORECASE)
_CONCAT = re.compile(r"""(['"`])\s*\+\s*\1""")  # 'his' + 'tory' -> 'history'
_IMPORT_FROM = re.compile(r"""\bfrom\s+['"]([^'"]+)['"]|\b(?:import|require)\s*\(\s*['"]([^'"]+)['"]""")
_DYNAMIC_IMPORT = re.compile(r"""\b(?:import|require)\s*\(\s*[^'"\s)]""")


def frontend_hits(text: str) -> list[str]:
    """Every history request path, history import, or unresolvable dynamic import in one frontend file."""
    hits = [f"path {m.group(0)}" for m in _PATH_LITERAL.finditer(text)]
    for source in (text, _CONCAT.sub("", text)):  # also the text with adjacent literals joined
        for m in _LITERAL.finditer(source):
            lit = next(g for g in m.groups() if g is not None)
            if _WORD.search(lit) and f"word {lit}" not in hits:
                hits.append(f"word {lit}")
    for m in _IMPORT_FROM.finditer(text):
        target = m.group(1) or m.group(2)
        if re.search(_HISTORY_WORD, target, re.IGNORECASE):
            hits.append(f"import {target}")
    hits += [f"non-literal import near {m.group(0)!r}" for m in _DYNAMIC_IMPORT.finditer(text)]
    return hits


def _frontend_allowed(rel: str, hit: str) -> bool:
    """True when a hit is an exact exempt (file, literal): a word hit in the words list, or a word/path hit whose whole
    literal (path hits carry their quotes) is in the paths list."""
    if hit.startswith("word "):
        return (rel, hit[5:]) in ALLOWED_FRONTEND_WORDS | ALLOWED_FRONTEND_PATHS
    return hit.startswith("path ") and len(hit) > 7 and hit[5] in "'\"`" and (rel, hit[6:-1]) in ALLOWED_FRONTEND_PATHS


def scan_frontend(src: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(p for p in src.rglob("*") if p.suffix in {".js", ".ts", ".vue", ".mjs", ".jsx", ".tsx"}):
        rel = path.relative_to(src).as_posix()
        hits = [h for h in frontend_hits(path.read_text(encoding="utf-8")) if not _frontend_allowed(rel, h)]
        if hits:
            found[rel] = hits
    return found


def test_only_the_allow_listed_modules_import_a_history_reader():
    """AC-1: no module outside the allow-list (so no route, no app entry point) imports a history reader."""
    bad = disallowed(scan_backend(BACKEND), ALLOWED_IMPORTERS)
    assert bad == {}, f"history readers imported outside the allow-list (ADR-066, internal use only): {bad}"


def test_no_route_or_app_entry_is_allow_listed_and_the_list_has_no_stale_entry():
    """AC-1: the allow-list names no route module and not the app's main, and every entry is a real module."""
    assert not [m for m in ALLOWED_IMPORTERS if m.startswith("ofo_app.routes") or m == "ofo_app.main"]
    assert list((BACKEND / "ofo_app" / "routes").glob("*.py")), "routes folder not found: the scan would be vacuous"
    assert (BACKEND / "ofo_app" / "main.py").exists()
    for module in ALLOWED_IMPORTERS:
        rel = Path(*module.split("."))
        assert (BACKEND / rel).with_suffix(".py").exists() or (BACKEND / rel / "__init__.py").exists(), module


def test_the_frontend_requests_and_imports_no_history():
    """AC-1: no frontend/src file requests a history/candles path or imports a history module."""
    assert any(FRONTEND_SRC.rglob("*.vue")), "frontend/src not found: the scan would be vacuous"
    bad = {f: h for f, h in scan_frontend(FRONTEND_SRC).items() if f not in ALLOWED_FRONTEND}
    assert bad == {}, f"frontend shows or requests history (ADR-066): {bad}"


def test_the_backend_scan_flags_planted_routes_in_every_import_shape(tmp_path):
    """AC-1 self-test: a planted route is flagged in each import shape, and a clean route is not."""
    routes = tmp_path / "ofo_app" / "routes"
    routes.mkdir(parents=True)
    planted = {
        "from_import": "from ofo_app.kite_history import KiteHistory\n",
        "alias": "import ofo_app.history_store as h\n",
        "from_package": "from ofo_app import kite_history\n",
        "relative": "from .. import history_finalize\n",
        "relative_module": "from ..history_store import PostgresHistoryStore\n",
        "domain": "from ofo.history.store import HistoryStore\n",
        "domain_package": "from ofo import history\n",
        "literal_dynamic": "import importlib\nimportlib.import_module('ofo_app.kite_history')\n",
        "computed_dynamic": "import importlib\nimportlib.import_module(name)\n",
        "star": "from ofo_app import *\n",
        "too_far": "from .... import x\n",
    }
    for name, source in planted.items():
        (routes / f"{name}.py").write_text(source, encoding="utf-8")
    (routes / "clean.py").write_text("from ofo_app.kite_reads import KiteReads\nimport os\n", encoding="utf-8")
    found = disallowed(scan_backend(tmp_path), ALLOWED_IMPORTERS)
    assert sorted(found) == sorted(f"ofo_app.routes.{n}" for n in planted)


def test_the_allow_list_check_is_what_flags_a_planted_importer(tmp_path):
    """AC-1 self-test: allow-listed, the planted importer passes; not allow-listed, it fails (the check bites)."""
    (tmp_path / "ofo_app").mkdir()
    (tmp_path / "ofo_app" / "planted.py").write_text("from ofo_app.kite_history import KiteHistory\n", encoding="utf-8")
    found = scan_backend(tmp_path)
    assert found == {"ofo_app.planted": ["from ofo_app.kite_history import ..."]}
    assert disallowed(found, ALLOWED_IMPORTERS) == found
    assert disallowed(found, ALLOWED_IMPORTERS | {"ofo_app.planted"}) == {}


def test_the_frontend_scan_flags_planted_pages_and_passes_normal_code(tmp_path):
    """AC-1 self-test: a planted page requesting history is flagged in each shape; routing code is not."""
    pages = tmp_path / "pages"
    pages.mkdir()
    planted = {
        "fetch.vue": "<script>\nfetch('/api/history/candles')\n</script>\n",
        "axios.js": "export const f = () => axios.get('/api/candles', { params: {} })\n",
        "template.js": "export const f = (t) => api.get(`/api/instruments/${t}/historical`)\n",
        "import.vue": "<script>\nimport { x } from '@/services/kite_history'\n</script>\n",
        "dynamic.js": "export const f = (n) => import(n)\n",
    }
    for name, source in planted.items():
        (pages / name).write_text(source, encoding="utf-8")
    (pages / "clean.js").write_text(
        "import { createRouter, createWebHistory } from 'vue-router'\n"
        "const r = createRouter({ history: createWebHistory() })\n"
        "api.get('/api/strategies/live')\nconst label = 'Execution history'\n", encoding="utf-8")
    assert sorted(scan_frontend(tmp_path)) == sorted(f"pages/{n}" for n in planted)


# ---- issue #409: every dynamic-import shape and history word the first scan missed (planted source, not repo files)
# Each case below fails if the rule it names is removed: resolve-by-import-source (_aliases/_resolve), literal
# package/fromlist reading (_dynamic_call_hits), reference flagging (_dynamic_hits), the word scan (_LITERAL/_WORD).
@pytest.mark.parametrize("source", [
    "from importlib import import_module as im\nim('ofo_app.kite_history')\n",              # aliased by import source
    "from importlib import import_module\nimport_module('.kite_history', package='ofo_app')\n",  # relative literal
    "import importlib\nimportlib.import_module('.kite_history', 'ofo_app')\n",               # positional package
    "__import__('ofo_app', fromlist=['kite_history'])\n",                                    # fromlist
    "__import__('ofo_app', None, None, ['history_store'])\n",                                # positional fromlist
    "import builtins\nbuiltins.__import__('ofo_app.kite_history')\n",
    "import importlib as il\nil.import_module('ofo.history.store')\n",                        # module alias
    "import importlib\ngetattr(importlib, 'import_module')('ofo_app.kite_history')\n",       # getattr on the module
    "import importlib\nf = importlib.import_module\nf('ofo_app.kite_history')\n",            # bare reference
    "import runpy\nrunpy.run_module('ofo_app.kite_history')\n",
    "from runpy import run_module as r\nr('ofo_app.history_store')\n",
    "import runpy\nrunpy.run_path('x.py')\n",                                                # path: cannot resolve
    "import importlib\nimportlib.import_module(name)\n",                                      # computed (fail closed)
    "import importlib\nimportlib.import_module(*args)\n",
    "import importlib\nimportlib.import_module('.x')\n",                                      # relative, no package
    "__import__('ofo_app', fromlist=names)\n",                                               # computed fromlist
    "__import__('ofo_app', level=1)\n",
    "from importlib import *\n",
    "import importlib.util\nimportlib.util.spec_from_file_location('m', p)\n",  # path loader outside Alembic
])
def test_the_backend_scan_flags_every_dynamic_import_shape(source):
    assert import_hits(source, "ofo_app.routes.planted"), source
    assert disallowed({"ofo_app.routes.planted": import_hits(source, "ofo_app.routes.planted")}, ALLOWED_IMPORTERS)


@pytest.mark.parametrize("source", [
    "def im(x):\n    return x\nim('ofo_app.kite_history')\n",  # same name, not from importlib: not dynamic
    "import importlib\nimportlib.import_module('ofo_app.kite_reads')\n",  # resolvable, not a history module
    "__import__('os')\n",
    "import runpy\nrunpy.run_module('ofo_app.other')\n",
    "import_module = len\nimport_module('ofo_app.kite_history')\n",
    "from ofo_app.kite_reads import KiteReads\n",
])
def test_the_backend_scan_passes_resolvable_non_history_and_unrelated_calls(source):
    assert import_hits(source, "ofo_app.routes.planted") == [], source


def test_path_loaders_are_allowed_only_in_the_alembic_versions_folder():
    source = ("import importlib.util\ns = importlib.util.spec_from_file_location('m', p)\n"
              "m = importlib.util.module_from_spec(s)\n")
    found = {"ofo_app.alembic.versions.0099_x": import_hits(source, "ofo_app.alembic.versions.0099_x"),
             "ofo_app.routes.x": import_hits(source, "ofo_app.routes.x")}
    assert sorted(disallowed(found, ALLOWED_IMPORTERS)) == ["ofo_app.routes.x"]


@pytest.mark.parametrize("text", [
    "api.get('candles')",
    "const u = '/api/' + 'history'",
    "const u = '/api/hi' + 'story'",
    "params: { kind: 'historical' }",
    "params: { kind: 'intraday' }",
    "fetch(`/api/instruments/${t}/intraday`)",
    "const k = \"kite_history\"",
])
def test_the_frontend_scan_flags_every_history_word_shape(text):
    assert frontend_hits(text), text


@pytest.mark.parametrize("text", [
    "const r = createRouter({ history: createWebHistory() })",
    "const label = 'Execution history'",
    "const n = 'createWebHistory'",
    "api.get('/api/strategies/live')",
    "const k = 'candlestick-free'.length",
])
def test_the_frontend_scan_passes_routing_prose_and_unrelated_words(text):
    assert frontend_hits(text) == [], text


def test_an_unlisted_user_history_literal_is_still_flagged_by_file_and_literal(tmp_path):
    (tmp_path / "router").mkdir()
    (tmp_path / "router" / "nav.js").write_text("['history', 'History']\n['intraday', 'x']\n", encoding="utf-8")
    (tmp_path / "other.js").write_text("['history', 'History']\n", encoding="utf-8")
    assert scan_frontend(tmp_path) == {"router/nav.js": ["word intraday"], "other.js": ["word history", "word History"]}


# ---- REQ-070 AC-5 exemption self-tests: the user's own strategy activity route, one exact (file, literal) pair
_ACTIVITY_FILE = "lib/strategyActivity.js"
_ACTIVITY_LITERAL = "/strategies/${id}/history"


def _plant(root: Path, rel: str, source: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(source, encoding="utf-8")


def test_the_activity_route_literal_passes_only_in_its_named_file(tmp_path):
    """The exemption is exact: the literal passes in lib/strategyActivity.js, and fails in any other file."""
    source = f"export const f = (c, id) => c.get(`{_ACTIVITY_LITERAL}`)\n"
    _plant(tmp_path, _ACTIVITY_FILE, source)
    _plant(tmp_path, "lib/other.js", source)
    _plant(tmp_path, "pages/Other.vue", f"<script>\nconst u = `{_ACTIVITY_LITERAL}`\n</script>\n")
    found = scan_frontend(tmp_path)
    assert sorted(found) == ["lib/other.js", "pages/Other.vue"]
    # both the path hit and the word hit stay flagged: neither check alone is what holds the line
    assert all(h == [f"path `{_ACTIVITY_LITERAL}`", f"word {_ACTIVITY_LITERAL}"] for h in found.values())


def test_a_market_data_history_path_in_the_activity_file_is_still_flagged(tmp_path):
    """Any other history literal in the named file fails, even next to the exempt one."""
    _plant(tmp_path, _ACTIVITY_FILE,
           f"export const a = (c, id) => c.get(`{_ACTIVITY_LITERAL}`)\n"
           "export const b = (c) => c.get('/api/history/candles')\n")
    hits = scan_frontend(tmp_path)[_ACTIVITY_FILE]
    assert hits and all("candles" in h for h in hits)
    _plant(tmp_path, _ACTIVITY_FILE, "export const b = (c, id) => c.get(`/instruments/${id}/history`)\n")
    other = "/instruments/${id}/history"
    assert scan_frontend(tmp_path)[_ACTIVITY_FILE] == [f"path `{other}`", f"word {other}"]


def test_a_concatenated_or_imported_history_in_the_activity_file_is_still_flagged(tmp_path):
    _plant(tmp_path, _ACTIVITY_FILE, "export const u = '/strategies/' + 'history'\n")
    assert scan_frontend(tmp_path)[_ACTIVITY_FILE]
    _plant(tmp_path, _ACTIVITY_FILE, "import { x } from '@/lib/kite_history'\n")
    assert scan_frontend(tmp_path)[_ACTIVITY_FILE]
    _plant(tmp_path, _ACTIVITY_FILE, "export const f = (n) => import(n)\n")
    assert scan_frontend(tmp_path)[_ACTIVITY_FILE]


def test_removing_the_exemption_makes_the_repo_scan_fail_on_the_activity_file(monkeypatch):
    """The exemption is load-bearing and is the only one: with it gone the real activity file is flagged."""
    assert ALLOWED_FRONTEND_PATHS == {(_ACTIVITY_FILE, _ACTIVITY_LITERAL)}
    monkeypatch.setattr(sys.modules[__name__], "ALLOWED_FRONTEND_PATHS", frozenset())
    assert _ACTIVITY_FILE in scan_frontend(FRONTEND_SRC)
