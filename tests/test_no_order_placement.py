"""W-080 AC-4 (REQ-073, ADR-054): no code path places an order through Kite's order-placement API; this test fails if
one is added.

The guarantee is at RUNTIME (round 7, run-discipline B8): the egress gate ``ofo.broker.egress`` refuses every
non-loopback, non-database connect and every process spawn unless it happens inside a Kite door after the door's URL
check (``check_call`` against ``ALLOWED_CALLS``). Planted real calls prove it: ``tests/test_egress_gate.py`` and
``tests_app/test_egress_gate_doors.py``.

This file is the second layer, three source checks over every backend module:

1. a network library (a door's own library, or a raw socket / TLS / HTTP / process module) is imported only by its
   door in ``NETWORK_DOORS``;
2. ``ALLOWED_CALLS`` holds no write under ``/orders`` or ``/gtt``;
3. no module uses another module's ``_private`` name (as an attribute of an imported name, an imported name, or a
   keyword passed to an imported name, such as a door's ``_test_transport`` seam) unless the file is on ``PRIVATE_ALLOWED`` with a reason. That is how the gate's own state (``egress._door``,
   ``egress._allow_endpoints``) is kept to the doors: reaching it takes a literal private name.

Dynamic constructs (``exec``, ``setattr``, ``sys.modules``, ``importlib``, ``ctypes``, ``gc``) are held to their own
per-file allow-lists by ``tests/test_door_names_private.py``. Planted examples are written to a temp folder and never
committed.
"""  # noqa: E501
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from ofo.broker.kite_endpoints import ALLOWED_CALLS, NETWORK_DOORS  # noqa: E402

#: modules that open a connection or a process; besides the doors' own libraries, none may be imported anywhere.
RAW_NETWORK = frozenset({"socket", "ssl", "http.client", "urllib.request", "subprocess", "asyncio.subprocess",
                         "requests", "aiohttp", "httpcore", "urllib3", "ftplib", "smtplib", "xmlrpc.client"})
NETWORK_MODULES = RAW_NETWORK | frozenset(r for roots in NETWORK_DOORS.values() for r in roots)

#: Backend file -> (the other modules' private names it may use, reason). Frozen from the real uses on 2026-10-16;
#: adding a use means adding it here with its reason (and a reviewer reading why).
PRIVATE_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "ofo/broker/kite_http.py": (frozenset({"ofo.broker.egress._door", "ofo.broker.egress._test_mode"}),
                                "the urllib Kite door opens door context after check_call; loopback passes only in "
                                "the one egress test mode"),
    "ofo_app/kite_http.py": (frozenset({"ofo.broker.egress._door", "ofo.broker.egress._test_mode"}),
                             "the httpx Kite door opens door context after check_call; its test seam asks test mode"),
    "ofo_app/kite_ws.py": (frozenset({"ofo.broker.egress._door", "ofo.broker.egress._test_mode"}),
                           "the websocket Kite door opens door context after check_ws_url; "
                           "its test seam asks test mode"),
    "ofo_app/__init__.py": (frozenset({"ofo.broker.egress._allow_endpoints"}),
                            "sets the database endpoints once, at app import"),
    "ofo/errors/explanations.py": (frozenset({"ofo.errors.slots._require_exact", "sys._getframe"}),
                                   "same package's slot validator; user_words() reads its caller's module "
                                   "(door guard)"),
    "ofo/errors/gate_slots.py": (frozenset({"ofo.errors.slots._IST", "ofo.errors.slots._MONTHS",
                                            "ofo.errors.slots._require_exact", "ofo.errors.slots._validate_money"}),
                                 "same package's slot formatting helpers"),
    "ofo/errors/templates.py": (frozenset({"ofo.errors.model._build", "ofo.errors.model._claim_render_token"}),
                                "same package's error-object builder and render token"),
    "ofo/execution/partial.py": (frozenset({"ofo.execution.send_guard._BrokerSink", "ofo.execution.send_guard._Transport",
                                            "ofo.strategy.guard._decision"}),
                                 "type protocols of the send guard and the guard's decision helper"),
    "ofo/execution/safety.py": (frozenset({"ofo.engine.metrics._Unlimited", "ofo.engine.metrics._upper_tail_slope"}),
                                "the engine's unlimited marker and tail slope (one engine owns the maths, ADR-008)"),
    "ofo/strategy/guard.py": (frozenset({"ofo.engine.metrics._Unlimited"}), "the engine's unlimited marker"),
    "ofo/strategy/modification.py": (frozenset({"ofo.engine.metrics._Unlimited"}), "the engine's unlimited marker"),
    "ofo_app/catalogue_store.py": (frozenset({"ofo.instruments.catalogue.Catalogue._in_scope"}),
                                   "the domain catalogue's own scope rule, reused so the store and domain agree"),
    "ofo_app/entitlement_store.py": (frozenset({"ofo.entitlements.ledger._restore"}),
                                     "rebuilds a ledger from stored rows (the ledger's own restore)"),
}

PLACEMENT_PATH = re.compile(r"^/(orders|gtt)(/|$)")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _module_of(name: str) -> str:
    return name.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def _is_network(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in NETWORK_MODULES)


def _door_may(name: str, module: str) -> bool:
    return any(module == r or module.startswith(r + ".") for r in NETWORK_DOORS.get(name, ()))


def scan_module(source: str, name: str) -> list[str]:  # noqa: C901, PLR0912
    """Network imports outside their door, and other modules' private names, in one module (``name`` is the path
    relative to ``backend/``). A file that does not parse fails: it cannot be shown clean."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{name}: cannot be parsed ({exc.msg})"]
    own = _module_of(name)
    permitted = PRIVATE_ALLOWED.get(name, (frozenset(), ""))[0]
    found: list[str] = []
    bound: dict[str, str] = {}  # local name -> the module (or module.Name) it is bound to

    def flag(node: ast.AST, what: str) -> None:
        found.append(f"{name}:{getattr(node, 'lineno', 0)}: {what}")

    def network(node: ast.AST, module: str) -> None:
        if _is_network(module) and not _door_may(name, module):
            flag(node, f"imports {module}, a network module outside its door")

    def private(node: ast.AST, token: str) -> None:
        if token not in permitted:
            flag(node, f"uses another module's private name {token}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                network(node, a.name)
                bound[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                flag(node, "relative import (the scan resolves absolute imports only)")
                continue
            network(node, mod)
            for a in node.names:
                network(node, f"{mod}.{a.name}")
                if _is_private(a.name) and mod != own:
                    private(node, f"{mod}.{a.name}")
                bound[a.asname or a.name] = f"{mod}.{a.name}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):  # a private keyword (a test seam) passed to an imported name
            head = node.func
            while isinstance(head, ast.Attribute):
                head = head.value
            if isinstance(head, ast.Name) and head.id in bound and bound[head.id] != own:
                for kw in node.keywords:
                    if kw.arg and _is_private(kw.arg):
                        private(node, f"{bound[head.id]}({kw.arg}=)")
        if isinstance(node, ast.Attribute) and _is_private(node.attr):
            head, chain = node.value, [node.attr]
            while isinstance(head, ast.Attribute):
                chain.append(head.attr)
                head = head.value
            if isinstance(head, ast.Name) and head.id in bound:
                target = bound[head.id]
                if target != own:
                    private(node, ".".join([target, *reversed(chain[1:])]) + "." + node.attr)
    return sorted(set(found))


def placement_in(calls) -> list[str]:
    """Allow-list entries that would place, modify or cancel: any non-GET under /orders or /gtt."""
    return [f"{m} {p}" for m, p in calls if m != "GET" and PLACEMENT_PATH.match(p)]


def _modules_under(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.py"))}


def scan_tree(root: Path) -> list[str]:
    return [f for name, src in _modules_under(root).items() for f in scan_module(src, name)]


# -- the real backend -----------------------------------------------------------------------------------------------


def test_allow_list_holds_no_placement_modify_or_cancel_path() -> None:
    all_calls = [c for calls in ALLOWED_CALLS.values() for c in calls]
    assert all_calls, "the allow-list must not be empty"
    assert placement_in(all_calls) == []
    assert all(m in ("GET", "POST") for m, _ in all_calls)


def test_every_backend_module_passes_the_scan() -> None:
    assert len(_modules_under(BACKEND)) > 50, "the scan must actually see the backend"  # noqa: PLR2004
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


def test_private_allowances_are_real() -> None:
    """Each allowance names a file that exists and still uses every listed name (a stale allowance is a hole)."""
    modules = _modules_under(BACKEND)
    for name, (tokens, reason) in PRIVATE_ALLOWED.items():
        assert name in modules and reason, name
        for token in tokens:
            assert token.rsplit(".", 1)[1] in modules[name], f"{name}: {token} is no longer used"


def test_listed_modules_go_through_a_door() -> None:
    modules = _modules_under(BACKEND)
    for name in ALLOWED_CALLS:
        assert name in modules, f"{name} is listed but does not exist"
        assert any(d in modules[name] for d in ("ofo.broker.kite_http", "ofo_app.kite_http")), name


# -- planted modules -------------------------------------------------------------------------------------------------

PLANTED = {
    "httpx_outside_door": "import httpx\n",
    "websockets_outside_door": "from websockets.asyncio.client import connect\n",
    "urllib_request": "import urllib.request\n",
    "from_urllib_import_request": "from urllib import request\n",
    "from_http_import_client": "from http import client\n",
    "socket": "import socket\n",
    "ssl_alias": "import ssl as s\n",
    "subprocess": "import subprocess\n",
    "requests": "import requests\n",
    "door_state": "from ofo.broker import egress\nwith egress._door():\n    pass\n",
    "door_state_import": "from ofo.broker.egress import _DOOR, _SENTINEL\n_DOOR.set(_SENTINEL)\n",
    "endpoint_state": "import ofo.broker.egress as e\ne._allow_endpoints(['postgresql://x@192.0.2.1:443/db'])\n",
    "test_seam": "from ofo_app.kite_http import KiteClient\nKiteClient(_test_transport=t)._transport\n",
    "test_mode": "from ofo.broker import egress\negress._enter_test_mode(['curl'])\n",
    "relative": "from .kite_http import kite_client\n",
    "unparsable": "def (:\n",
}


@pytest.mark.parametrize("key", sorted(PLANTED))
def test_planted_module_fails_the_scan(tmp_path: Path, key: str) -> None:
    (tmp_path / "ofo_app").mkdir()
    (tmp_path / "ofo_app" / "clean.py").write_text("import json\n", encoding="utf-8")
    (tmp_path / "ofo_app" / f"{key}.py").write_text(PLANTED[key], encoding="utf-8")
    found = scan_tree(tmp_path)
    assert found and all(f.startswith(f"ofo_app/{key}.py") for f in found), (key, found)


@pytest.mark.parametrize("door, source", [
    ("ofo_app/kite_http.py", "import requests\n"),   # a door may import only its own network module
    ("ofo_app/kite_ws.py", "import httpx\n"),
    ("ofo/broker/kite_http.py", "import socket\n"),
    ("ofo_app/kite_http.py", "from ofo.broker import egress\negress._allow_endpoints([])\n"),  # only its own names
])
def test_doors_are_held_to_their_own_entry(door: str, source: str) -> None:
    assert scan_module(source, door), (door, source)


@pytest.mark.parametrize("clean", [
    '"""Docs may say socket, api.kite.trade, _door and requests."""\nx = 1\n',
    "from urllib.parse import urlencode, urlsplit\nfrom urllib.error import HTTPError\n",
    "from http import HTTPStatus\nimport asyncio\nimport os\n",
    "from ofo.broker.kite_http import open_url\nfrom ofo_app.kite_http import kite_client\n",
    "self._x = 1\nother._legs\nobj._private_attr()\n",   # attributes of objects, not of imported names
    "from ofo_app.clean import _helper\n",              # a module's own private names
    "import json\njson.__name__\n",                     # dunders are not private names
])
def test_clean_code_passes_the_scan(clean: str) -> None:
    assert scan_module(clean, "ofo_app/clean.py") == []


def test_the_doors_may_import_their_own_network_module() -> None:
    assert scan_module("import httpx as _httpx\n", "ofo_app/kite_http.py") == []
    assert scan_module("import urllib.request as _urllib_request\n", "ofo/broker/kite_http.py") == []
    assert scan_module("from websockets.asyncio.client import connect\n", "ofo_app/kite_ws.py") == []


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
