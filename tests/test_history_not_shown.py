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

DYNAMIC_IMPORTS = {"__import__", "import_module"}
WIDE_PACKAGES = {"ofo", "ofo_app"}  # `from ofo_app import *` could pull a history module in: unresolvable, so flagged


def _is_history(dotted: str) -> bool:
    return any(dotted == m or dotted.startswith(m + ".") for m in HISTORY_MODULES)


def _package_of(module: str, is_package: bool) -> list[str]:
    parts = module.split(".")
    return parts if is_package else parts[:-1]


def import_hits(source: str, module: str, is_package: bool = False) -> list[str]:
    """Every history import, or unresolvable import shape, in one backend module's source (empty = clean)."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            hits += [f"import {a.name}" for a in node.names if _is_history(a.name)]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                pkg = _package_of(module, is_package)
                if node.level - 1 > len(pkg):
                    hits.append(f"unresolvable relative import at line {node.lineno}")
                    continue
                pkg = pkg[: len(pkg) - (node.level - 1)]
                base = ".".join(pkg + ([node.module] if node.module else []))
            if _is_history(base):
                hits.append(f"from {base} import ...")
                continue
            for a in node.names:
                if a.name == "*" and base in WIDE_PACKAGES:
                    hits.append(f"star import from {base} at line {node.lineno}")
                elif _is_history(f"{base}.{a.name}"):
                    hits.append(f"from {base} import {a.name}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if name in DYNAMIC_IMPORTS:
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if _is_history(arg.value):
                        hits.append(f"{name}({arg.value!r})")
                else:
                    hits.append(f"non-literal {name}() at line {node.lineno}")
    return hits


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
    return {m: h for m, h in found.items() if m not in allowed}


# frontend: a path-like string literal with a history/candle segment, or an import of such a module
_HISTORY_WORD = r"(?:history|historical|candles?|ohlc\w*|kite_history|history_store|history_finalize)"
_PATH_LITERAL = re.compile(r"""['"`][^'"`\n]*/[^'"`\n]*\b""" + _HISTORY_WORD + r"""\b[^'"`\n]*['"`]""", re.IGNORECASE)
_IMPORT_FROM = re.compile(r"""\bfrom\s+['"]([^'"]+)['"]|\b(?:import|require)\s*\(\s*['"]([^'"]+)['"]""")
_DYNAMIC_IMPORT = re.compile(r"""\b(?:import|require)\s*\(\s*[^'"\s)]""")


def frontend_hits(text: str) -> list[str]:
    """Every history request path, history import, or unresolvable dynamic import in one frontend file."""
    hits = [f"path {m.group(0)}" for m in _PATH_LITERAL.finditer(text)]
    for m in _IMPORT_FROM.finditer(text):
        target = m.group(1) or m.group(2)
        if re.search(_HISTORY_WORD, target, re.IGNORECASE):
            hits.append(f"import {target}")
    hits += [f"non-literal import near {m.group(0)!r}" for m in _DYNAMIC_IMPORT.finditer(text)]
    return hits


def scan_frontend(src: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(p for p in src.rglob("*") if p.suffix in {".js", ".ts", ".vue", ".mjs", ".jsx", ".tsx"}):
        hits = frontend_hits(path.read_text(encoding="utf-8"))
        if hits:
            found[path.relative_to(src).as_posix()] = hits
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
    """AC-1 self-test: with the importer on the allow-list the scan passes, without it the scan fails (the check bites)."""
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
        "import { createRouter, createWebHistory } from 'vue-router'\nconst r = createRouter({ history: createWebHistory() })\n"
        "api.get('/api/strategies/live')\nconst label = 'Execution history'\n", encoding="utf-8")
    assert sorted(scan_frontend(tmp_path)) == sorted(f"pages/{n}" for n in planted)
