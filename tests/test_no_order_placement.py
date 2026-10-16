"""W-080 AC-4 (REQ-073, ADR-054): no code path places an order through Kite's order-placement API; this test fails if
one is added.

Two layers, each a structural allow-list (run-discipline B8), neither a list of forbidden spellings:

1. RUNTIME (the guarantee): every Kite request goes through a door that refuses, BEFORE sending, anything not in
   ``ALLOWED_CALLS`` (``backend/ofo/broker/kite_endpoints.py``): the urllib door ``open_url``, the httpx classes in
   ``ofo_app/kite_http.py`` whose ``send()`` and last hop check every request (proven in ``tests/test_kite_http_guard.py``
   and ``tests_app/test_kite_http_guard.py``), and the websocket door ``ofo_app/kite_ws.py``.
2. STATIC (this file): ``scan_imports`` holds every backend module to an import ALLOW-list. A module may import only
   the standard-library modules in ``SAFE_STDLIB``, the packages in ``SAFE_PACKAGES``, the exact pairs in
   ``ALLOWED_IMPORTS``; only a door in ``NETWORK_DOORS`` may import its network module. An unknown module FAILS until
   someone adds it here deliberately. Process / FFI / dynamic-import escapes fail anywhere (``subprocess``, ``ctypes``,
   ``importlib`` outside ``EXEMPT``, ``builtins`` are simply not on the list; ``__import__``, ``__builtins__``,
   ``exec``, ``eval``, ``compile``, ``sys.modules`` / ``meta_path`` / ``path_hooks`` / ``_getframe``, ``os.system`` /
   ``popen`` / ``exec*`` / ``spawn*`` and the asyncio connection / subprocess calls are refused by name of their
   import source). Replacing a client's ``send`` / ``event_hooks`` / ``_transport`` outside a door fails. A file that
   does not parse fails (it cannot be shown clean).

The bar, plainly: ordinary and accidental additions are caught (a new HTTP library, a raw socket, a subprocess, an
``exec``, a guard swap). Deliberately obfuscated code (``getattr`` with a computed name, ``vars(sys)[...]``) is NOT
claimed: that is a code-review matter, and the runtime doors still refuse whatever reaches them. Planted examples are
written to a temp folder and never committed.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ofo.broker.kite_endpoints import ALLOWED_CALLS, ALLOWED_IMPORTS, EXEMPT, NETWORK_DOORS  # noqa: E402

# -- the allow-list -------------------------------------------------------------------------------------------------

#: standard-library modules any module may import whole (none opens a connection or runs other code by itself).
#: A submodule is NOT implied: ``logging.handlers`` (socket / HTTP handlers) and ``asyncio.subprocess`` are refused.
SAFE_STDLIB = frozenset({
    "__future__", "abc", "argparse", "asyncio", "base64", "binascii", "collections", "collections.abc", "contextlib",
    "csv", "dataclasses", "datetime", "decimal", "enum", "fractions", "functools", "gzip", "hashlib", "hmac",
    "inspect", "io", "itertools", "json", "logging", "math", "os", "os.path", "pathlib", "queue", "re", "secrets",
    "statistics", "struct", "sys", "threading", "time", "types", "typing", "unicodedata", "weakref",
})
#: packages whose every submodule is allowed: ours, and the third-party ones the app is built on. sqlalchemy is the DB
#: driver (a network client to PostgreSQL only, configured by DATABASE_URL), stated here on purpose.
SAFE_PACKAGES = frozenset({"ofo", "ofo_app", "alembic", "cryptography", "fastapi", "jsonschema", "pydantic",
                           "pydantic_settings", "sqlalchemy", "starlette", "yaml"})
#: submodules of a safe package that are NOT allowed (an HTTP client inside a web framework).
UNSAFE_SUBMODULES = frozenset({"starlette.testclient", "fastapi.testclient"})

#: names refused wherever they appear: dynamic import / code execution.
DYNAMIC_NAMES = frozenset({"__import__", "__builtins__", "exec", "eval", "compile"})
#: members refused by their import source (``import os as o; o.system`` and ``from os import system`` alike).
BANNED_MEMBERS = {
    "os": ("system", "popen", "exec", "spawn", "posix_spawn", "fork", "startfile"),  # prefixes
    "sys": ("modules", "meta_path", "path_hooks", "path_importer_cache", "_getframe"),
}
#: asyncio / event-loop calls that open a connection or a process; refused as an attribute on anything (a loop object
#: has no import source) and as an imported name.
NETWORK_CALLS = frozenset({
    "open_connection", "open_unix_connection", "create_connection", "create_unix_connection", "start_tls",
    "create_datagram_endpoint", "create_server", "create_unix_server", "start_server", "start_unix_server",
    "sock_connect", "create_subprocess_exec", "create_subprocess_shell", "subprocess_exec", "subprocess_shell",
})
#: client attributes that carry the guard or the wire; replacing one outside a door is refused.
GUARD_ATTRS = frozenset({"send", "_send_single_request", "event_hooks", "_event_hooks", "_transport", "_mounts",
                         "__class__"})


#: EXEMPT construct names that are not the attribute itself, and the source token proving the use is still there.
CONSTRUCT_OF = {"__class__": "module-freeze"}
USE_TOKEN = {"module-freeze": "__class__"}


def _exempt(name: str, construct: str) -> bool:
    return any(construct in reasons and (name == key or (key.endswith("/") and name.startswith(key)))
               for key, reasons in EXEMPT.items())


def _is_module(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _module_ok(mod: str, door_roots: frozenset[str]) -> bool:
    if any(mod == r or mod.startswith(r + ".") for r in door_roots):
        return True
    if any(mod == u or mod.startswith(u + ".") for u in UNSAFE_SUBMODULES):
        return False
    return mod.split(".")[0] in SAFE_PACKAGES or mod in SAFE_STDLIB


def _banned_member(module: str, member: str) -> bool:
    return any(member.startswith(p) for p in BANNED_MEMBERS.get(module, ()))


def _parse(source: str, name: str):
    try:
        return ast.parse(source), []
    except SyntaxError as exc:
        return None, [f"{name}: cannot be parsed ({exc.msg}), so it cannot be shown free of network access"]


def _dotted(node: ast.AST) -> list[str] | None:
    """``a.b.c`` -> ["a", "b", "c"]; None when the chain does not start at a plain name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return [node.id, *reversed(parts)]


def scan_imports(source: str, name: str) -> list[str]:
    """Every import, dynamic construct and guard swap in one module, against the allow-list (``name`` is the path
    relative to ``backend/``; it decides door roots and exemptions)."""
    tree, bad = _parse(source, name)
    if tree is None:
        return bad
    door_roots = NETWORK_DOORS.get(name, frozenset())
    if _exempt(name, "importlib"):
        door_roots = door_roots | {"importlib.util"}
    found: list[str] = []
    bound: dict[str, str] = {}  # local name -> module it is bound to

    def flag(node: ast.AST, what: str) -> None:
        found.append(f"{name}:{getattr(node, 'lineno', 0)}: {what}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    target, local = a.name, a.asname
                else:  # ``import a.b`` binds ``a``: everything loaded under ``a`` becomes reachable
                    target, local = a.name.split(".")[0], a.name.split(".")[0]
                own = any(a.name == r or a.name.startswith(r + ".") for r in door_roots)  # a door's own module
                if not (_module_ok(a.name, door_roots) and (own or _module_ok(target, door_roots))):
                    flag(node, f"import {a.name} is not on the import allow-list")
                bound[local] = target
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                flag(node, "relative import cannot be resolved by the scan; use an absolute import")
                continue
            for a in node.names:
                full = f"{mod}.{a.name}"
                if (mod, a.name) in ALLOWED_IMPORTS or (mod, "*") in ALLOWED_IMPORTS and a.name != "*":
                    continue
                if a.name == "*":
                    if mod.split(".")[0] not in ("ofo", "ofo_app"):
                        flag(node, f"from {mod} import * hides what is imported")
                    continue
                if not _module_ok(mod, door_roots):
                    flag(node, f"from {mod} import {a.name} is not on the import allow-list")
                elif _banned_member(mod, a.name) or (mod.split(".")[0] == "asyncio" and a.name in NETWORK_CALLS):
                    flag(node, f"from {mod} import {a.name} opens a process, connection or the import system")
                elif mod.split(".")[0] not in SAFE_PACKAGES and _is_module(full) and not _module_ok(full, door_roots):
                    flag(node, f"from {mod} import {a.name}: submodule {full} is not on the import allow-list")
                elif _is_module(full):
                    bound[a.asname or a.name] = full
        elif isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES:
            flag(node, f"{node.id} (dynamic import or code execution)")
        elif isinstance(node, ast.Attribute):
            if node.attr in NETWORK_CALLS:
                flag(node, f".{node.attr} opens a connection or a process")
            if node.attr in GUARD_ATTRS and isinstance(node.ctx, (ast.Store, ast.Del)) and name not in NETWORK_DOORS                     and not _exempt(name, CONSTRUCT_OF.get(node.attr, node.attr)):
                flag(node, f"replaces .{node.attr} of an object (a client's guard or transport)")
        elif isinstance(node, ast.Call):
            fn = node.func
            setter = (isinstance(fn, ast.Name) and fn.id in ("setattr", "delattr")) or \
                     (isinstance(fn, ast.Attribute) and fn.attr in ("__setattr__", "__delattr__"))
            arg = node.args[1] if setter and len(node.args) > 1 else None
            if isinstance(arg, ast.Constant) and arg.value in GUARD_ATTRS and name not in NETWORK_DOORS:
                flag(node, f"replaces .{arg.value} of an object via {ast.unparse(fn)}")

    # attribute chains on a bound module: submodules and banned members by import source
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain = _dotted(node)
        if not chain or chain[0] not in bound:
            continue
        module = bound[chain[0]]
        for attr in chain[1:]:
            if _banned_member(module, attr) and not _exempt(name, f"{module}.{attr}"):
                flag(node, f"{module}.{attr} opens a process or reaches the import system")
                break
            candidate = f"{module}.{attr}"
            if module.split(".")[0] not in SAFE_PACKAGES and _is_module(candidate):
                if not _module_ok(candidate, door_roots):
                    flag(node, f"{candidate} is reached through {chain[0]} and is not on the import allow-list")
                    break
                module = candidate
            else:
                break
    return sorted(set(found))


def placement_in(calls) -> list[str]:
    """Allow-list entries that would place, modify or cancel: any non-GET under /orders or /gtt."""
    return [f"{m} {p}" for m, p in calls if m != "GET" and PLACEMENT_PATH.match(p)]


PLACEMENT_PATH = re.compile(r"^/(orders|gtt)(/|$)")
WRITE_VERBS = frozenset({"put", "delete", "patch", "request", "stream", "send", "options"})


def _docstrings(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def _template_parts(templates) -> list[str]:
    return [p for t in templates for p in re.split(r"\{[^}]*\}", t) if p]


def _is_own_path(value: str, templates) -> bool:
    whole = [re.compile(re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(t))) for t in templates]
    return any(rx.fullmatch(value.split("?")[0]) for rx in whole) or value in _template_parts(templates)


def _fits(fragment: str, templates) -> bool:
    path = fragment.split("?")[0]
    for t in templates:
        for part in (p for p in re.split(r"\{[^}]*\}", t) if p):
            if len(path) > 1 and (path == part or part.startswith(path) or path.startswith(part)):
                return True
    return False


ORDER_STRING = re.compile(r"(^|/)(orders|gtt)/|/(orders|gtt)$")


def _is_call_target(tree: ast.AST, attr: ast.Attribute) -> bool:
    return any(isinstance(n, ast.Call) and n.func is attr for n in ast.walk(tree))


def scan_allowed_module(source: str, name: str, allowed) -> list[str]:
    """A module listed in ALLOWED_CALLS: only its own methods, paths and plain requests (its allow-list binds it)."""
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


def _modules_under(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.py"))}


def scan_tree(root: Path) -> list[str]:
    return [f for name, src in _modules_under(root).items() for f in scan_imports(src, name)]


# -- the real backend -----------------------------------------------------------------------------------------------


def test_allow_list_holds_no_placement_modify_or_cancel_path() -> None:
    all_calls = [c for calls in ALLOWED_CALLS.values() for c in calls]
    assert all_calls, "the allow-list must not be empty"
    assert placement_in(all_calls) == []
    assert all(m in ("GET", "POST") for m, _ in all_calls)


def test_every_backend_module_passes_the_import_allow_list() -> None:
    modules = _modules_under(BACKEND)
    assert len(modules) > 50, "the scan must actually see the backend"
    assert scan_tree(BACKEND) == []


def test_doors_exist_and_really_import_their_network_module() -> None:
    """A stale door entry (module renamed, or no longer the one importing its library) is a finding."""
    modules = _modules_under(BACKEND)
    for door, roots in NETWORK_DOORS.items():
        assert door in modules, f"{door} is a listed door but does not exist"
        tree = ast.parse(modules[door])
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                   {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert any(i == r or i.startswith(r + ".") for i in imported for r in roots), door


def test_exemptions_are_still_used() -> None:
    modules = _modules_under(BACKEND)
    for key, reasons in EXEMPT.items():
        names = [n for n in modules if n == key or (key.endswith("/") and n.startswith(key))]
        assert names, f"EXEMPT {key} matches no module"
        for construct in reasons:
            token = USE_TOKEN.get(construct, construct.split(".")[-1])
            assert any(token in modules[n] for n in names), f"EXEMPT {key} {construct} is no longer used"


def test_listed_modules_go_through_a_door_and_stay_inside_their_own_entries() -> None:
    modules = _modules_under(BACKEND)
    doors = ("ofo.broker.kite_http", "ofo_app.kite_http")
    for name, allowed in ALLOWED_CALLS.items():
        assert name in modules, f"{name} is listed but does not exist"
        assert any(d in modules[name] for d in doors), f"{name} is listed but no longer uses a Kite door"
        assert scan_allowed_module(modules[name], name, allowed) == []


# -- planted modules: the round-5 bypasses and the rest of the class ------------------------------------------------

PLANTED = {
    "b1_urllib": 'import urllib\nurllib.request.urlopen(urllib.request.Request("https://api.kite."+"trade/orde"'
                 '+"rs/regular", data=b"x", method="POST"))\n',
    "b2_http_client": 'import http\nhttp.client.HTTPSConnection("api.kite."+"trade").request("POST","/orde"+"rs/regular")\n',
    "b3_socket_ssl": 'import socket, ssl\ns = ssl.create_default_context().wrap_socket(socket.create_connection(('
                     '"api.kite."+"trade", 443)), server_hostname="x")\ns.sendall(b"POST /orders/regular")\n',
    "b4_sys_modules": 'import sys\nsys.modules["requ"+"ests"].post("https://x/y")\n',
    "subprocess": 'import subprocess\nsubprocess.run(["curl", "-X", "POST", "u"])\n',
    "asyncio_open_connection": 'import asyncio\nasync def f():\n    await asyncio.open_connection("h", 443)\n',
    "base64_exec": 'import base64\nexec(base64.b64decode(b"aW1wb3J0IHJlcXVlc3Rz"))\n',
    "loop_create_connection": 'import asyncio\nasyncio.get_running_loop().create_connection(P, "h", 443)\n',
    "from_asyncio_import": 'from asyncio import open_connection\n',
    "asyncio_subprocess_attr": 'import asyncio\nasyncio.subprocess.PIPE\n',
    "ctypes": 'import ctypes\n',
    "dunder_import": 'm = __import__("requ" + "ests")\n',
    "importlib": 'import importlib\nimportlib.import_module("x")\n',
    "importlib_util": 'import importlib.util\n',
    "builtins": 'import builtins\nbuiltins.exec("x")\n',
    "dunder_builtins": '__builtins__["exec"]("x")\n',
    "eval": 'eval("1")\n',
    "compile": 'c = compile("x", "f", "exec")\n',
    "os_system": 'import os\nos.system("curl")\n',
    "os_alias_popen": 'import os as o\no.popen("curl")\n',
    "from_os_import": 'from os import execv\n',
    "sys_meta_path": 'import sys\nsys.meta_path.insert(0, F())\n',
    "sys_getframe": 'import sys\nsys._getframe(1)\n',
    "logging_handlers_import": 'import logging.handlers\n',
    "logging_handlers_from": 'from logging import handlers\n',
    "logging_handlers_attr": 'import logging\nlogging.handlers.HTTPHandler("api.kite.trade", "/orders/regular")\n',
    "urllib_parse_binds_urllib": 'import urllib.parse\n',
    "from_http_import_client": 'from http import client\n',
    "from_urllib_import_request": 'from urllib import request\n',
    "httpx_outside_door": 'import httpx\n',
    "requests": 'import requests\n',
    "websockets_outside_door": 'from websockets.asyncio.client import connect\n',
    "unknown_module": 'import anyio\n',
    "starlette_testclient": 'from starlette.testclient import TestClient\n',
    "relative": 'from .kite_http import kite_client\n',
    "star_import": 'from os import *\n',
    "send_swap": 'c.send = f\n',
    "event_hooks_swap": 'c = kite_client()\nc.event_hooks = {}\n',
    "transport_swap": 'c._transport = t\n',
    "class_swap": 'c.__class__ = Plain\n',
    "setattr_send": 'setattr(c, "send", f)\n',
    "object_setattr_send": 'object.__setattr__(c, "send", f)\n',
    "unparsable": 'def (:\n',
}


@pytest.mark.parametrize("key", sorted(PLANTED))
def test_planted_module_fails_the_scan(tmp_path: Path, key: str) -> None:
    (tmp_path / "ofo_app").mkdir()
    (tmp_path / "ofo_app" / "clean.py").write_text("import json\n", encoding="utf-8")
    (tmp_path / "ofo_app" / f"{key}.py").write_text(PLANTED[key], encoding="utf-8")
    found = scan_tree(tmp_path)
    assert found and all(f.startswith(f"ofo_app/{key}.py") for f in found), (key, found)


@pytest.mark.parametrize("door, source", [
    ("ofo_app/kite_http.py", "import requests\n"),          # a door may import only its own network module
    ("ofo_app/kite_ws.py", "import httpx\n"),
    ("ofo_app/kite_http.py", 'exec("x")\n'),                # doors are not exempt from the dynamic bans
    ("ofo/broker/kite_http.py", "import socket\n"),
    ("ofo/errors/explanations.py", "import sys\nsys.modules\n"),  # an exemption covers only its own construct
    ("ofo_app/alembic/versions/0099_x.py", "import subprocess\n"),
])
def test_doors_and_exemptions_are_held_to_their_own_entry(door: str, source: str) -> None:
    assert scan_imports(source, door), (door, source)


@pytest.mark.parametrize("clean", [
    '"""Docs may say exec, eval, socket, api.kite.trade and requests."""\nx = 1\n',
    'from urllib.parse import urlencode, urlsplit\n',
    'from urllib.error import HTTPError, URLError\n',
    'from http import HTTPStatus\n',
    'import os\nos.environ.get("X")\nos.path.join("a", "b")\n',
    'import asyncio\nasyncio.run(main())\nasyncio.wait_for(x, 1)\n',
    'import re\nP = re.compile("a")\n',
    'import sqlalchemy.ext.asyncio\nfrom sqlalchemy import text\n',
    'from collections.abc import Mapping\nimport collections\n',
    'from ofo.broker.kite_http import open_url\nfrom ofo_app.kite_http import kite_client\n',
    'object.__setattr__(self, name, value)\nobject.__setattr__(self, "price", 1)\n',
    'self.sent = 1\nself._fetch = transport\n',
    'from logging.config import fileConfig\n',
])
def test_clean_code_passes_the_scan(clean: str) -> None:
    assert scan_imports(clean, "ofo_app/clean.py") == []


def test_the_doors_may_import_their_own_network_module() -> None:
    assert scan_imports("import httpx\n", "ofo_app/kite_http.py") == []
    assert scan_imports("import urllib.request\nfrom urllib.parse import urlsplit\n", "ofo/broker/kite_http.py") == []
    assert scan_imports("from websockets.asyncio.client import connect\n", "ofo_app/kite_ws.py") == []
    assert scan_imports("import importlib.util\n", "ofo_app/alembic/versions/0002_audit_store.py") == []


# -- the allow-list of Kite calls -----------------------------------------------------------------------------------

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
