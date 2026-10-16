"""W-081 wiring + #273: no platform estimate decides a margin block, and the basket has one production door.

Scan 1 (D1): the texts ``build_basket`` and ``KiteBasket`` appear in no backend file except their definition
(``ofo/execution/basket.py``) and the one production caller (``ofo_app/checked_basket.py``, whose margin source is
Zerodha's figures). A plain text match is deliberately strict: an import, an attribute, a string for ``getattr`` and a
comment all count. Shapes that reach them without the name are refused too: importing the basket MODULE (one line or
bracketed over several), the ``ofo.execution`` package as a namespace, ``import_module``/``__import__``, and the
``checked_basket`` module as a namespace.

This scan is the SECOND layer and cannot be complete (finding guard-by-banned-shapes: Python offers unbounded ways to
reach a name). The real guard is structural: ``build_basket`` reads Zerodha's two figures and calls ``check_margin``
itself (no verdict crosses its boundary), and a ``KiteBasket`` cannot be constructed, copied, pickled, replaced or
edited outside ``build_basket`` (tests/execution/test_kite_basket.py).

Scan 2 (D3): the platform's estimate never fills ``margin_required``. ``margin_estimate_from`` (and its old name
``margin_required_from``) is named only where it is defined and exported; a ``margin_required=`` keyword or a
``margin_required`` assignment whose value names the estimate or a planner is refused anywhere; and planner calls
(``.required_margin(``) are counted per file against an allow-list with reasons, so a new one in ``partial.py``
(where #273 lived) fails.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"

BASKET_ALLOWED = {
    "ofo/execution/basket.py": "defines build_basket and KiteBasket",
    "ofo_app/checked_basket.py": "the one production caller; its margin source is the real KiteMargin client",
}
#: Shapes that reach the basket module, ``build_basket`` or ``KiteBasket`` without the plain name: the module itself
#: (one-line or bracketed multi-line import, a module-path string), the ``ofo.execution`` package as a namespace, a
#: dynamic import, and the ``checked_basket`` module as a namespace (``vars(cb)[...]``).
_BASKET_MODULE_IMPORT = re.compile(
    r"import\s+ofo\.execution\.basket\b|from\s+ofo\.execution\s+import\s+[^\n]*\bbasket\b"
    r"|from\s+ofo\.execution\s+import\s*\([^)]*\bbasket\b|['\"]ofo\.execution\.basket['\"]"
    r"|^\s*import\s+ofo\.execution\s*(?:$|as\b|,)|from\s+ofo\s+import\s+[^\n]*\bexecution\b"
    r"|\bimport_module\s*\(|\b__import__\s*\("
    r"|import\s+ofo_app\.checked_basket\b|from\s+ofo_app\s+import\s+[^\n]*\bchecked_basket\b"
    r"|from\s+ofo_app\s+import\s*\([^)]*\bchecked_basket\b", re.MULTILINE)

ESTIMATE_NAMES = ("margin_estimate_from", "margin_required_from")
ESTIMATE_ALLOWED = {
    "ofo/execution/context.py": "defines the estimate",
    "ofo/execution/__init__.py": "re-exports it for display code",
}
#: planner calls ``.required_margin(`` allowed per file, each with its reason; any other count fails.
PLANNER_CALLS_ALLOWED = {
    "ofo/execution/context.py": (1, "margin_estimate_from"),
    "ofo/execution/partial.py": (2, "Assessment.margin_required display + _margin_or_unknown (Strategy Guard display)"),
}
_TAINT = re.compile(r"margin_estimate_from|margin_required_from|required_margin|planner", re.IGNORECASE)


def _files(root: Path):
    for path in sorted(root.rglob("*.py")):
        yield path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")


def basket_violations(root: Path) -> list[str]:
    out = []
    for rel, text in _files(root):
        if rel in BASKET_ALLOWED:
            continue
        if "build_basket" in text:
            out.append(f"{rel} names build_basket")
        if "KiteBasket" in text:
            out.append(f"{rel} names KiteBasket")
        if _BASKET_MODULE_IMPORT.search(text):
            out.append(f"{rel} imports the basket module itself")
    return out


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for e in node.elts for n in _target_names(e)]
    return []


def estimate_violations(root: Path) -> list[str]:
    out = []
    for rel, text in _files(root):
        if rel not in ESTIMATE_ALLOWED and any(name in text for name in ESTIMATE_NAMES):
            out.append(f"{rel} names the margin estimate helper")
        allowed, _reason = PLANNER_CALLS_ALLOWED.get(rel, (0, ""))
        calls = text.count(".required_margin(")
        if calls != allowed:
            out.append(f"{rel} has {calls} planner .required_margin( call(s), {allowed} allowed")
        out.extend(_tainted_fills(rel, text))
    return out


def _filled_value(node: ast.AST) -> ast.expr | None:
    """The value written into ``margin_required`` by this node (a keyword or an assignment), else None."""
    if isinstance(node, ast.keyword) and node.arg == "margin_required":
        return node.value
    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any("margin_required" in _target_names(t) for t in targets):
            return node.value
    return None


def _tainted_fills(rel: str, text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [f"{rel} does not parse; cannot prove it"]  # fail closed
    out = []
    for node in ast.walk(tree):
        value = _filled_value(node)
        if value is not None and _TAINT.search(ast.unparse(value)):
            out.append(f"{rel}:{getattr(node, 'lineno', '?')} fills margin_required from the platform estimate")
    return out


def test_the_backend_has_one_production_path_to_build_basket() -> None:
    assert basket_violations(BACKEND) == []


def test_no_platform_estimate_fills_margin_required() -> None:
    assert estimate_violations(BACKEND) == []


def test_allow_listed_files_exist() -> None:
    """A renamed or deleted allow-listed file would silently widen nothing, but would hide a stale list."""
    for rel in {*BASKET_ALLOWED, *ESTIMATE_ALLOWED, *PLANNER_CALLS_ALLOWED}:
        assert (BACKEND / rel).is_file(), rel


@pytest.mark.parametrize("planted", [
    "from ofo.execution.basket import build_basket\n",
    "import ofo.execution.basket as b\nx = b\n",
    "from ofo.execution import basket\n",
    "import importlib\nf = getattr(importlib.import_module('ofo.execution.basket'), 'x')\n",
    # round-2 reviewer plants (attacks/a6.py)
    "from ofo.execution import (\n    basket,\n)\ngetattr(basket, 'build_' + 'basket')\n",
    "import importlib\nm = importlib.import_module('ofo.execution.' + 'basket')\n",
    "import ofo.execution as e\nf = getattr(getattr(e, 'bas' + 'ket'), 'build_' + 'basket')\n",
    "from ofo_app import checked_basket as cb\nf = vars(cb)['build_' + 'basket']\n",
    "from ofo.execution.basket import KiteBasket, KiteOrder\nb = KiteBasket((KiteOrder(...),))\n",
    "from ofo_app.checked_basket import KiteBasket\nb = KiteBasket(orders)\n",
    "f = __import__('ofo.exec' + 'ution.basket')\n",
])
def test_a_second_build_basket_caller_fails_the_scan(tmp_path: Path, planted: str) -> None:
    (tmp_path / "ofo_app").mkdir()
    (tmp_path / "ofo_app" / "x.py").write_text(planted, encoding="utf-8")
    assert basket_violations(tmp_path) != []


@pytest.mark.parametrize("planted", [
    "ctx = make(margin_required=margin_required_from(planner, s))\n",
    "ctx = make(margin_required=margin_estimate_from(p, s))\n",
    "ctx = make(margin_required=planner.required_margin(s))\n",
    "ctx.margin_required = margin_estimate_from(p, s)\n",
    "margin_required: D = est.required_margin(s)\n",
])
def test_an_estimate_filling_margin_required_fails_the_scan(tmp_path: Path, planted: str) -> None:
    (tmp_path / "ofo").mkdir()
    (tmp_path / "ofo" / "x.py").write_text(planted, encoding="utf-8")
    assert estimate_violations(tmp_path) != []


@pytest.mark.parametrize("planted", [
    "ctx = make(margin_required=my_planner.estimate(s))\n",
    "ctx.margin_required = margin_planner.figure_for(s)\n",
])
def test_a_planner_figure_under_another_method_name_fails_the_taint_check(tmp_path: Path, planted: str) -> None:
    """Only the value check catches these (no estimate helper name, no `.required_margin(` call)."""
    (tmp_path / "ofo").mkdir()
    (tmp_path / "ofo" / "x.py").write_text(planted, encoding="utf-8")
    assert [v for v in estimate_violations(tmp_path) if "fills margin_required" in v] != []


def test_a_new_planner_call_in_partial_fails_the_scan(tmp_path: Path) -> None:
    """#273's shape: the old line `required = require_decimal(planner.required_margin(...))` put back in partial.py."""
    (tmp_path / "ofo" / "execution").mkdir(parents=True)
    text = (BACKEND / "ofo/execution/partial.py").read_text(encoding="utf-8")
    text += "\nrequired = require_decimal(planner.required_margin(Strategy(legs)), 'margin_required')\n"
    (tmp_path / "ofo" / "execution" / "partial.py").write_text(text, encoding="utf-8")
    assert any("partial.py has 3 planner" in v for v in estimate_violations(tmp_path))
