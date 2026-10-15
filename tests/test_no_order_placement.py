"""W-080 AC-4 (REQ-073, ADR-054): no code path places an order through Kite's order-placement API; this test fails if
one is added.

The scan reads every ``backend/**/*.py`` with ``ast`` (comments and docstrings are not code) and reports:
- a call or attribute named like a Kite order method (``place_order``, ``modify_order``, ``cancel_order``,
  ``exit_order``, ``place_gtt``, ``modify_gtt``, ``delete_gtt``, ``convert_position``);
- any string literal (also the pieces of an f-string) that names the order endpoint: ``/orders`` followed by ``/``,
  a ``?`` or the end of the string, or ``/gtt/triggers``;
- an import of ``kiteconnect`` (the SDK that carries the order methods).
Fail closed: a file that cannot be parsed is a finding. The allow-list test proves the scan catches planted examples,
generated in a temp directory and never committed.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ORDER_METHODS = frozenset({"place_order", "modify_order", "cancel_order", "exit_order", "place_gtt", "modify_gtt",
                           "delete_gtt", "convert_position"})
ORDER_ENDPOINT = re.compile(r"/(orders)(/|\?|$)|/gtt/triggers")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def scan_source(source: str, name: str = "<source>") -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{name}: cannot be parsed ({exc.msg}), so it cannot be shown free of order placement"]
    docs = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Attribute) and node.attr in ORDER_METHODS:
            found.append(f"{name}:{line}: attribute .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in ORDER_METHODS:
            found.append(f"{name}:{line}: name {node.id}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ORDER_METHODS:
            found.append(f"{name}:{line}: definition {node.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                and ORDER_ENDPOINT.search(node.value):
            found.append(f"{name}:{line}: order endpoint string {node.value!r}")
        elif isinstance(node, ast.Import) and any(a.name.split(".")[0] == "kiteconnect" for a in node.names):
            found.append(f"{name}:{line}: import kiteconnect")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "kiteconnect":
            found.append(f"{name}:{line}: import from kiteconnect")
    return found


def scan_tree(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        found += scan_source(path.read_text(encoding="utf-8"), str(path.relative_to(root)))
    return found


def test_backend_has_no_order_placement_path() -> None:
    files = list(BACKEND.rglob("*.py"))
    assert len(files) > 50, "the scan must actually see the backend"
    assert scan_tree(BACKEND) == []


@pytest.mark.parametrize("planted", [
    'import requests\nrequests.post(f"{BASE}/orders/regular", data=x)\n',
    'requests.put(BASE + "/orders/regular/123")\n',
    'url = "https://api.kite.trade/orders/amo"\n',
    'def f(kite):\n    return kite.place_order(variety="regular")\n',
    'kite.modify_order(1)\n',
    'kite.cancel_order(1, 2)\n',
    'fn = place_order\n',
    'def place_order(x):\n    pass\n',
    'from kiteconnect import KiteConnect\n',
    'import kiteconnect.exceptions\n',
    'requests.post(BASE + "/gtt/triggers")\n',
    'x = "/orders"\n',
])
def test_scan_catches_planted_placement(planted: str) -> None:
    assert scan_source(planted, "planted.py"), planted


@pytest.mark.parametrize("clean", [
    '"""Docs may say place_order and /orders/regular."""\nx = 1\n',
    'def f():\n    """calls /orders/regular never"""\n    return 1\n',
    'x = "https://kite.zerodha.com/connect/basket"\n',
    'y = "/user/margins"\n',
    'z = "reorders"\n',
])
def test_scan_does_not_flag_clean_code(clean: str) -> None:
    assert scan_source(clean, "clean.py") == []


def test_scan_fails_closed_on_unparseable_file(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    assert scan_tree(tmp_path)


def test_scan_tree_finds_a_planted_file(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("kite.place_order(1)\n", encoding="utf-8")
    found = scan_tree(tmp_path)
    assert len(found) == 1 and found[0].startswith("bad.py:1")
