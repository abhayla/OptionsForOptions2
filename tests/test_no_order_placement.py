"""W-080 AC-4 (REQ-073, ADR-054): no code path places an order through Kite's order-placement API; this test fails if
one is added.

The guarantee is STRUCTURAL and lives at runtime, not in this scan: every Kite HTTP request goes through
``ofo.broker.kite_http.check_call`` (urllib door ``open_url``, and the httpx factory ``ofo_app.kite_http`` whose clients
carry a request hook), which refuses BEFORE sending anything not in ``ALLOWED_CALLS`` in
``backend/ofo/broker/kite_endpoints.py``. Those are proven by ``tests/test_kite_http_guard.py`` and
``tests_app/test_kite_http_guard.py``. A static scan cannot see every way a client reaches a module (one passed in as a
parameter, a path built with ``urljoin`` or ``"/".join``), so THIS file is only the second layer, and it says what it
checks and no more:
1. the allow-list holds no write under ``/orders`` or ``/gtt`` (read-only ``POST /charges/orders``, ``GET /orders``
   are fine);
2. no module outside the allow-list and the plumbing modules imports an HTTP library, calls ``__import__`` /
   ``import_module``, names ``api.kite.trade`` or uses ``KITE_API_ROOT`` / ``KITE_API_URL``;
3. no module carries a string that looks like an order or gtt path (``orders/..``, ``/orders``) unless it is its own
   allow-listed path, and a listed module carries no HTTP verb or ``/``-path outside its own entries.
It does NOT prove no client was handed in some other way; the factory's refusal is what covers that. The planted
examples are built in memory and never committed.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ofo.broker.kite_endpoints import ALLOWED_CALLS, DOOR_CONSUMERS, HTTP_PLUMBING_MODULES  # noqa: E402

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


ORDER_STRING = re.compile(r"(^|/)(orders|gtt)/|/(orders|gtt)$")
ROOT_NAMES = ("KITE_API_ROOT", "KITE_API_URL")


def _template_parts(templates) -> list[str]:
    return [p for t in templates for p in re.split(r"\{[^}]*\}", t) if p]


def _is_own_path(value: str, templates) -> bool:
    """The constant IS one of this module's allow-listed paths (whole, or a literal piece of one)."""
    whole = [re.compile(re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(t))) for t in templates]
    return any(rx.fullmatch(value.split("?")[0]) for rx in whole) or value in _template_parts(templates)


def scan_order_strings(source: str, name: str, allowed=()) -> list[str]:
    """Any code string that looks like an order / gtt path, unless it is the module's own allow-listed path."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    docs = _docstrings(tree)
    templates = [p for _, p in allowed]
    return [f"{name}:{getattr(n, 'lineno', 0)}: order path {n.value!r}" for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
            and ORDER_STRING.search(n.value) and not _is_own_path(n.value, templates)]


def scan_root_use(source: str, name: str) -> list[str]:
    """Use of the Kite API root constant (the way an unlisted module would reach the host with a handed-in client)."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    found = []
    for n in ast.walk(tree):
        used = (n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute)
                else [a.name for a in n.names if a.name in ROOT_NAMES] if isinstance(n, ast.ImportFrom) else None)
        if used in ROOT_NAMES or (isinstance(used, list) and used):
            found.append(f"{name}:{getattr(n, 'lineno', 0)}: uses the Kite API root")
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
            if _is_own_path(v, templates):
                continue
            if ORDER_STRING.search(v) or "/orders" in v or "/gtt" in v:
                found.append(f"{name}:{line}: order path {v!r}")
            elif v.startswith("/") and not _fits(v, templates):
                found.append(f"{name}:{line}: path {v!r} is not in the allow-list")
    return found


def _is_call_target(tree: ast.AST, attr: ast.Attribute) -> bool:
    return any(isinstance(n, ast.Call) and n.func is attr for n in ast.walk(tree))


DOOR_MODULES = frozenset({"ofo.broker.kite_http", "ofo_app.kite_http"})
_DOOR_PARENTS = frozenset({"ofo.broker", "ofo_app"})


def scan_door_imports(source: str, name: str) -> list[str]:
    """Any import of a Kite door module (every import form). Relative imports and dynamic imports that cannot be
    resolved to a plain module name are flagged too: fail closed."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    found: list[str] = []
    for n in ast.walk(tree):
        line = getattr(n, "lineno", 0)
        hit = False
        if isinstance(n, ast.Import):
            hit = any(a.name in DOOR_MODULES or a.name.endswith("kite_http") for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            names = [a.name for a in n.names]
            hit = (mod in DOOR_MODULES or mod.endswith("kite_http") or "kite_http" in names
                   or (n.level > 0 and ("*" in names or mod == "")) or (mod in _DOOR_PARENTS and "*" in names))
        elif isinstance(n, ast.Call):
            fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if fn in DYNAMIC_IMPORTS:
                arg = n.args[0] if n.args else None
                literal = isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                hit = not literal or "kite_http" in arg.value
        if hit:
            found.append(f"{name}:{line}: imports a Kite door (or an import that cannot be resolved)")
    return found


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


def test_no_module_carries_an_order_path_or_the_api_root_outside_the_list() -> None:
    modules = _backend_modules()
    permitted = set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES)
    paths = [f for name, src in modules.items() for f in scan_order_strings(src, name, ALLOWED_CALLS.get(name, ()))]
    roots = [f for name, src in modules.items() if name not in permitted for f in scan_root_use(src, name)]
    assert paths == [] and roots == []


def test_listed_modules_exist_and_really_use_http() -> None:
    """A stale entry (module renamed or no longer calling Kite) is a finding, so the list cannot rot into a free pass."""
    modules = _backend_modules()
    for name in set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES):
        assert name in modules, f"{name} is listed but does not exist"
        uses = scan_network(modules[name], name) or "kite_http" in modules[name]
        assert uses, f"{name} is listed but no longer uses HTTP or the Kite door"


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


# -- round 3: the plants the first static layer missed, and the order-path rule --------------------------------------

P1_HANDED_IN_CLIENT = (
    "from ofo_app.kite_client import KITE_API_ROOT\n"
    "async def place(client, body):\n"
    "    return await client.post(KITE_API_ROOT + \"/orders/regular\", data=body)\n")
P7_RELATIVE_URLJOIN = "from urllib.parse import urljoin\nu = urljoin(ROOT, \"orders/regular\")\n"
P8_BASE_URL_CLIENT = "def f(c):\n    return c.post(\"orders/regular\")\n"


def test_static_layer_catches_p1_handed_in_client_with_the_api_root() -> None:
    assert scan_root_use(P1_HANDED_IN_CLIENT, "unlisted.py")
    assert scan_order_strings(P1_HANDED_IN_CLIENT, "unlisted.py")


def test_static_layer_catches_p7_relative_urljoin() -> None:
    assert scan_order_strings(P7_RELATIVE_URLJOIN, "kite_history.py", ALLOWED_CALLS["ofo_app/kite_history.py"])
    assert scan_allowed_module(P7_RELATIVE_URLJOIN, "kite_history.py", ALLOWED_CALLS["ofo_app/kite_history.py"])


def test_static_layer_catches_p8_relative_path_on_a_base_url_client() -> None:
    assert scan_order_strings(P8_BASE_URL_CLIENT, "x.py")
    assert scan_allowed_module(P8_BASE_URL_CLIENT, "kite_client.py", ALLOWED_CALLS["ofo_app/kite_client.py"])


@pytest.mark.parametrize("value", ["orders/regular", "/orders", "/orders/amo", "gtt/triggers", "/gtt", "a/orders/b",
                                   "/orders/regular/{id}"])
def test_order_string_rule_flags(value: str) -> None:
    assert scan_order_strings(f"x = {value!r}\n", "m.py")


@pytest.mark.parametrize("value", ["reorders", "/api/disorders", "orders_total", "border/x"])
def test_order_string_rule_leaves_other_words_alone(value: str) -> None:
    assert scan_order_strings(f"x = {value!r}\n", "m.py") == []


def test_a_module_does_not_flag_its_own_allow_listed_read_only_paths() -> None:
    allowed = frozenset({("POST", "/margins/orders"), ("POST", "/margins/basket"), ("GET", "/user/margins"),
                         ("GET", "/orders/{id}/trades")})
    src = ('A = "/margins/orders"\nB = "/margins/basket"\nC = "/user/margins"\n'
           'D = f"{r}/orders/{i}/trades"\n')
    assert scan_allowed_module(src, "kite_margin.py", allowed) == []
    assert scan_order_strings(src, "kite_margin.py", allowed) == []
    assert scan_allowed_module('X = "/orders/regular"\n', "kite_margin.py", allowed)  # its own list still binds it



# -- round 5: only listed modules may import a Kite door ---------------------------------------------------------------


def test_only_listed_modules_import_a_kite_door() -> None:
    modules = _backend_modules()
    permitted = set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES) | set(DOOR_CONSUMERS)
    offenders = [f for name, src in modules.items() if name not in permitted for f in scan_door_imports(src, name)]
    assert offenders == []


VERIFIER_MODULE = (
    "from ofo.broker.kite_http import open_url\n"
    'H = "https://api.kite%2Etrade/"\n'
    'open_url(H + "orde" + "rs/regular", method="POST")\n')


@pytest.mark.parametrize("planted", [
    VERIFIER_MODULE,
    "import ofo.broker.kite_http\n",
    "import ofo.broker.kite_http as k\n",
    "from ofo.broker import kite_http\n",
    "from ofo_app import kite_http as kh\n",
    "from ofo_app.kite_http import kite_client\n",
    "from .kite_http import open_url\n",
    "from . import kite_http\n",
    "from .. import *\n",
    "from ofo_app import *\n",
    'import importlib\nimportlib.import_module("ofo.broker.kite_http")\n',
    'x = __import__("ofo_app.kite_http")\n',
    'import importlib\nimportlib.import_module(name)\n',
    "def (:\n",
])
def test_door_import_scan_catches_planted_shapes(planted: str) -> None:
    assert scan_door_imports(planted, "planted.py"), planted


def test_door_import_scan_does_not_flag_clean_code() -> None:
    assert scan_door_imports("import json\nfrom ofo.broker import kite_endpoints\n", "clean.py") == []


def test_planted_verifier_module_in_a_tree_is_named(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "sneaky.py").write_text(VERIFIER_MODULE, encoding="utf-8")
    found = [f for p in sorted(tmp_path.glob("*.py")) for f in scan_door_imports(p.read_text(encoding="utf-8"), p.name)]
    assert len(found) == 1 and found[0].startswith("sneaky.py:1")


def test_a_door_consumer_is_not_exempt_from_the_http_library_scans() -> None:
    """DOOR_CONSUMERS only skips the door-import scan: a listed consumer that imports urllib is still flagged."""
    planted = "from ofo_app.kite_http import kite_async_client\nimport urllib.request\n"
    assert scan_door_imports(planted, "ofo_app/routes/broker.py")  # the door import itself is what the list allows
    modules = {"ofo_app/routes/broker.py": planted}
    permitted = set(ALLOWED_CALLS) | set(HTTP_PLUMBING_MODULES)  # consumers are NOT in the network-scan exemption
    assert "ofo_app/routes/broker.py" in DOOR_CONSUMERS
    flagged = [f for n, src in modules.items() if n not in permitted for f in scan_network(src, n)]
    assert flagged, "urllib import in a door consumer must still be flagged"
