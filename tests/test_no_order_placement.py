"""W-080 AC-4 (REQ-073, ADR-054): no code path places an order through Kite's order-placement API; this test fails if
one is added.

Structural guarantee (run-discipline B8), not a forbidden-name list. An order can only be placed by an HTTP call to
Kite, so:
1. ``backend/ofo/broker/kite_endpoints.py`` declares the ONLY (method, path) pairs any module may call; none is a
   write under ``/orders`` or ``/gtt`` (read-only ``POST /charges/orders`` and ``GET /orders`` are fine);
2. no module outside that list (and the two plumbing modules) imports ``requests``/``httpx``/``aiohttp``/``urllib3``/
   ``urllib.request``/``http.client``/``kiteconnect``, calls ``__import__``/``import_module``, or names ``api.kite.trade``
   in code (docstrings and comments are not code), so a path built any way (``urljoin``, ``"/".join``, a base_url
   client, ``getattr(kite, "place_order")``) has no client to travel on;
3. each listed module carries no HTTP verb, request option or ``/``-path outside its own allow-list entries.
The planted-example tests build their code in a temp directory and never commit it.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ofo.broker.kite_endpoints import ALLOWED_CALLS, HTTP_PLUMBING_MODULES  # noqa: E402

BANNED_IMPORTS = ("requests", "httpx", "aiohttp", "urllib3", "urllib.request", "http.client", "kiteconnect")
DYNAMIC_IMPORTS = ("__import__", "import_module")
WRITE_VERBS = frozenset({"put", "delete", "patch", "request", "stream", "send", "options"})
PLACEMENT_PATH = re.compile(r"^/(orders|gtt)(/|$)")


def placement_in(calls) -> list[str]:
    """Allow-list entries that would place, modify or cancel: any non-GET under /orders or /gtt."""
    return [f"{m} {p}" for m, p in calls if m != "GET" and PLACEMENT_PATH.match(p)]


def _docstrings(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def _parse(source: str, name: str):
    try:
        return ast.parse(source), []
    except SyntaxError as exc:
        return None, [f"{name}: cannot be parsed ({exc.msg}), so it cannot be shown free of Kite HTTP"]


def _is_banned(module: str) -> bool:
    return any(module == b or module.startswith(b + ".") for b in BANNED_IMPORTS)


def scan_network(source: str, name: str = "<source>") -> list[str]:
    """Anything that gives a module a way to talk to Kite over HTTP."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    docs = _docstrings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            found += [f"{name}:{line}: import {a.name}" for a in node.names
                      if _is_banned(a.name)]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if _is_banned(mod):
                found.append(f"{name}:{line}: from {mod} import ...")
            found += [f"{name}:{line}: from {mod} import {a.name}" for a in node.names
                      if _is_banned(f"{mod}.{a.name}".strip("."))]
        elif isinstance(node, ast.Name) and node.id in DYNAMIC_IMPORTS:
            found.append(f"{name}:{line}: dynamic import {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in DYNAMIC_IMPORTS:
            found.append(f"{name}:{line}: dynamic import .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                and "api.kite.trade" in node.value:
            found.append(f"{name}:{line}: names the Kite API host")
    return found


def _fits(fragment: str, templates) -> bool:
    path = fragment.split("?")[0]
    for t in templates:
        for part in (p for p in re.split(r"\{[^}]*\}", t) if p):
            if len(path) > 1 and (path == part or part.startswith(path) or path.startswith(part)):
                return True
    return False


def scan_allowed_module(source: str, name: str, allowed) -> list[str]:
    """A module that may call Kite: only its own methods, paths and plain requests."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    docs = _docstrings(tree)
    methods = {m for m, _ in allowed}
    templates = [p for _, p in allowed]
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Attribute):
            if node.attr in WRITE_VERBS and _is_call_target(tree, node):
                found.append(f"{name}:{line}: HTTP verb .{node.attr}")
            elif node.attr == "post" and "POST" not in methods and _is_call_target(tree, node):
                found.append(f"{name}:{line}: HTTP verb .post not in this module's allow-list")
        elif isinstance(node, ast.Call):
            kw = {k.arg for k in node.keywords}
            fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if fn == "Request" and ("method" in kw or ("data" in kw and "POST" not in methods)):
                found.append(f"{name}:{line}: urllib Request with method/data")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            v = node.value
            if "/orders" in v or "/gtt" in v:
                found.append(f"{name}:{line}: order path {v!r}")
            elif v.startswith("/") and not _fits(v, templates):
                found.append(f"{name}:{line}: path {v!r} is not in the allow-list")
    return found


def _is_call_target(tree: ast.AST, attr: ast.Attribute) -> bool:
    return any(isinstance(n, ast.Call) and n.func is attr for n in ast.walk(tree))


def _backend_modules() -> dict[str, str]:
    return {p.relative_to(BACKEND).as_posix(): p.read_text(encoding="utf-8") for p in sorted(BACKEND.rglob("*.py"))}


# -- the real backend ---------------------------------------------------------------------------------------------


def test_allow_list_holds_no_placement_modify_or_cancel_path() -> None:
    all_calls = [c for calls in ALLOWED_CALLS.values() for c in calls]
    assert all_calls, "the allow-list must not be empty"
    assert placement_in(all_calls) == []
    assert all(m in ("GET", "POST") for m, _ in all_calls)


def test_no_other_module_can_talk_to_kite_over_http() -> None:
    modules = _backend_modules()
    assert len(modules) > 50, "the scan must actually see the backend"
    permitted = set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES)
    offenders = [f for name, src in modules.items() if name not in permitted for f in scan_network(src, name)]
    assert offenders == []


def test_listed_modules_exist_and_really_use_http() -> None:
    """A stale entry (module renamed or no longer calling Kite) is a finding, so the list cannot rot into a free pass."""
    modules = _backend_modules()
    for name in set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES):
        assert name in modules, f"{name} is listed but does not exist"
        assert scan_network(modules[name], name), f"{name} is listed but no longer uses HTTP"


def test_listed_modules_stay_inside_their_own_entries() -> None:
    modules = _backend_modules()
    for name, allowed in ALLOWED_CALLS.items():
        assert scan_allowed_module(modules[name], name, allowed) == []


# -- the checkers catch the shapes the old forbidden-list missed ---------------------------------------------------


@pytest.mark.parametrize("planted", [
    'import httpx\nhttpx.Client(base_url="https://api.kite.trade").post("orders/regular")\n',
    'import requests\nfrom urllib.parse import urljoin\nrequests.post(urljoin(ROOT, "orders/regular"))\n',
    'from kiteconnect import KiteConnect\nk = KiteConnect()\ngetattr(k, "place_order")()\n',
    'import kiteconnect\n',
    'import requests\nrequests.post("/".join([ROOT, "orders", "regular"]))\n',
    'import urllib.request\n',
    'from urllib import request\n',
    'from urllib.request import urlopen\n',
    'import http.client\n',
    'from http import client\n',
    'import aiohttp\n',
    'import urllib3\n',
    'import requests.adapters\n',
    'x = __import__("requests")\n',
    'from importlib import import_module\nimport_module("requests")\n',
    'mod = importlib.import_module("httpx")\n',
    'HOST = "https://api.kite.trade"\n',
    'url = f"{base}api.kite.trade/orders"\n',
    'def (:\n',
])
def test_network_scan_catches_planted_shapes(planted: str) -> None:
    assert scan_network(planted, "planted.py"), planted


@pytest.mark.parametrize("clean", [
    '"""Docs may say api.kite.trade, requests and httpx."""\nx = 1\n',
    'def f():\n    """POST https://api.kite.trade/orders"""\n    return 1\n',
    'from urllib.parse import urlencode, urlsplit\n',
    'URL = "/charges/orders"\nOTHER = "/margins/orders"\nREAD = "/orders/{id}/trades"\n',
    'import websockets\n',
])
def test_network_scan_does_not_flag_clean_code(clean: str) -> None:
    assert scan_network(clean, "clean.py") == []


GET_ONLY = frozenset({("GET", "/instruments/historical/{token}/minute")})


@pytest.mark.parametrize("planted", [
    'c.put("/instruments/historical/1/minute")\n',
    'c.delete("/x")\n',
    'c.patch("/x")\n',
    'c.request("POST", "/x")\n',
    'c.post("/instruments/historical/1/minute")\n',
    'u = "/orders/regular"\n',
    'u = f"{b}/orders/amo/{i}"\n',
    'u = "/gtt/triggers"\n',
    'u = "/portfolio/positions"\n',
    'u = "/"\n',
    'r = urllib.request.Request(url, data=b"x")\n',
    'r = urllib.request.Request(url, method="DELETE")\n',
])
def test_allowed_module_scan_catches_planted_shapes(planted: str) -> None:
    assert scan_allowed_module(planted, "planted.py", GET_ONLY), planted


def test_allowed_module_scan_passes_its_own_entries() -> None:
    ok = ('u = f"{b}/instruments/historical/{t}/minute?from={s}"\nr = c.get(u)\n'
          'req = urllib.request.Request(u, headers=h)\n')
    assert scan_allowed_module(ok, "ok.py", GET_ONLY) == []


@pytest.mark.parametrize("calls", [
    {("POST", "/orders/regular")}, {("PUT", "/orders/regular/1")}, {("DELETE", "/orders/amo/1")},
    {("POST", "/gtt/triggers")}, {("PATCH", "/orders")}, {("POST", "/orders")},
])
def test_placement_checker_flags_write_entries(calls) -> None:
    assert placement_in(calls)


@pytest.mark.parametrize("calls", [
    {("POST", "/charges/orders")}, {("POST", "/margins/orders")}, {("POST", "/margins/basket")},
    {("GET", "/orders")}, {("GET", "/orders/{id}/trades")}, {("GET", "/orders/{id}")},
])
def test_placement_checker_does_not_flag_read_only_entries(calls) -> None:
    assert placement_in(calls) == []


def test_scan_of_a_planted_tree_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("import httpx\n", encoding="utf-8")
    found = [f for p in sorted(tmp_path.glob("*.py")) for f in scan_network(p.read_text(encoding="utf-8"), p.name)]
    assert len(found) == 1 and found[0].startswith("bad.py:1")
