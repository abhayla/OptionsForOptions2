"""#353 (REQ-073 AC-4, ADR-054): every Kite door call names its calling module, and only its own.

The runtime check (``check_call(..., caller=)``) allows a call only for the module listed for it in ``ALLOWED_CALLS``.
This scan proves the identity each call site passes is the calling FILE's own: a door call (resolved by import
source, so a renamed alias or a module-attribute call is still found) must pass ``caller=<CONST>`` where ``CONST`` is
imported from ``ofo.broker.kite_endpoints`` and equals that file's path. Anything the scan cannot resolve fails
closed: no ``caller``, a ``**kwargs`` call, a literal or computed caller, a constant imported from elsewhere, or a door
name used as a value (``functools.partial(open_url, ...)``, ``getattr``). The doors themselves forward a parameter,
and ``ofo_app/kite_margin.py``'s ``urllib_transport`` is the one listed forwarder (its ``caller`` parameter).

Out of scope (ADR-098): a module that lies about its own name at runtime, forged code objects.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ofo.broker import kite_endpoints
from ofo.broker.kite_endpoints import ALLOWED_CALLS, NETWORK_DOORS

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"
ENDPOINTS = "ofo.broker.kite_endpoints"
#: the door callables, by import source: calling any of them needs the caller's identity.
DOOR_CALLABLES = frozenset({
    "ofo.broker.kite_http.check_call", "ofo.broker.kite_http.open_url",
    "ofo_app.kite_http.KiteClient", "ofo_app.kite_http.KiteAsyncClient",
    "ofo_app.kite_http.kite_client", "ofo_app.kite_http.kite_async_client",
    "ofo_app.kite_margin.urllib_transport",
})
#: (file, function) that forwards its own ``caller`` parameter to a door - the closed list.
FORWARDERS = frozenset({("ofo_app/kite_margin.py", "urllib_transport")})
#: identity wrappers (#353 round 2): each calls a door AS ITS OWN MODULE, so outside that module it may only be handed
#: to that module's client as ``transport=`` (bare, or ``functools.partial(wrapper, timeout=...)``); any other use
#: (a call, a value, another client) borrows the module's identity. wrapper -> its client class.
IDENTITY_WRAPPERS = {
    "ofo_app.kite_margin.margin_transport": "ofo_app.kite_margin.KiteMargin",
    "ofo_app.kite_reads.reads_transport": "ofo_app.kite_reads.KiteReads",
}
DOOR_MODULES = frozenset(name.rpartition(".")[0] for name in [*DOOR_CALLABLES, *IDENTITY_WRAPPERS])
DYNAMIC_IMPORTS = frozenset({"importlib.import_module", "importlib.__import__", "builtins.__import__"})


def _imports(tree: ast.Module, rel: str) -> dict[str, str]:
    """local name -> fully qualified name, for every import in the module and its own top-level functions/classes."""
    module = rel.removesuffix(".py").replace("/", ".")
    out: dict[str, str] = {node.name: f"{module}.{node.name}" for node in tree.body
                           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out[a.asname] = a.name
                else:
                    out[a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _qualified(expr: ast.expr, imports: dict[str, str]) -> str | None:
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name) or expr.id not in imports:
        return None
    return ".".join([imports[expr.id], *reversed(parts)])


def _annotation_nodes(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations.append(node.returns)
            args = node.args
            annotations += [a.annotation for a in args.posonlyargs + args.args + args.kwonlyargs]
            annotations += [a.annotation for a in (args.vararg, args.kwarg) if a is not None]
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for annotation in annotations:
            if annotation is not None:
                ids.update(id(n) for n in ast.walk(annotation))
    return ids


def _enclosing_functions(tree: ast.Module) -> dict[int, ast.FunctionDef | ast.AsyncFunctionDef]:
    owner: dict[int, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                owner[id(inner)] = node  # innermost wins: ast.walk visits outer functions first
    return owner


def _caller_ok(rel: str, call: ast.Call, imports: dict[str, str], function) -> str | None:  # noqa: PLR0911 - one reason each
    """None when the call passes this file's own identity; otherwise why not."""
    if any(k.arg is None for k in call.keywords):
        return "a **kwargs door call cannot be resolved"
    given = [k.value for k in call.keywords if k.arg == "caller"]
    if not given:
        return "no caller="
    value = given[0]
    if not isinstance(value, ast.Name):
        return "caller= is not a plain name"
    if function is not None and (rel, function.name) in FORWARDERS:
        params = {a.arg for a in function.args.kwonlyargs + function.args.args}
        return None if value.id == "caller" and "caller" in params else "a forwarder passes only its caller parameter"
    source = imports.get(value.id, "")
    if not source.startswith(ENDPOINTS + "."):
        return f"caller={value.id} is not imported from {ENDPOINTS}"
    const = source[len(ENDPOINTS) + 1:]
    if getattr(kite_endpoints, const, None) != rel:
        return f"caller={value.id} is not this file's own identity"
    return None


def scan_source(rel: str, source: str) -> list[str]:
    """Every door call or door reference in ``source`` (file ``rel`` under backend/) that breaks the rule."""
    if rel in NETWORK_DOORS:
        return []  # the doors forward the identity they were given; their own tests cover them
    tree = ast.parse(source)
    imports = _imports(tree, rel)
    annotations = _annotation_nodes(tree)
    owner = _enclosing_functions(tree)
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _qualified(node.func, imports)
            if name in DOOR_CALLABLES:
                why = _caller_ok(rel, node, imports, owner.get(id(node)))
                if why:
                    problems.append(f"{rel}:{node.lineno} {name}: {why}")
            elif (isinstance(node.func, ast.Name) and node.func.id == "getattr" and node.args
                  and _qualified(node.args[0], imports) in DOOR_MODULES):
                problems.append(f"{rel}:{node.lineno} getattr on a door module: a dynamic lookup cannot be resolved")
        elif isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in called and id(node) not in annotations:
            name = _qualified(node, imports)
            if name in DOOR_CALLABLES and not _is_inner_part(node, tree):
                problems.append(f"{rel}:{node.lineno} {name} used as a value: its caller cannot be resolved")
    return problems + _unresolved_imports(rel, tree, imports) + _wrapper_misuse(rel, tree, imports)


def _unresolved_imports(rel: str, tree: ast.Module, imports: dict[str, str]) -> list[str]:
    """Fail closed on imports the scan does not resolve (none exist in backend/ today): a relative import, or a
    dynamic import (importlib.import_module / __import__) that could reach a door under another name."""
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            problems.append(f"{rel}:{node.lineno} a relative import cannot be resolved by the scan: import absolutely")
        if isinstance(node, ast.Call) and (_qualified(node.func, imports) in DYNAMIC_IMPORTS or (
                isinstance(node.func, ast.Name) and node.func.id == "__import__")):
            problems.append(f"{rel}:{node.lineno} a dynamic import cannot be resolved by the scan")
    return problems


def _wrapper_handed_over(keyword: ast.keyword, client: str | None, imports: dict[str, str]) -> int | None:
    """The node id of an identity wrapper given to its own client as ``transport=`` (bare or partial with only
    ``timeout=``), else None."""
    value = keyword.value
    if (isinstance(value, ast.Call) and _qualified(value.func, imports) == "functools.partial"
            and len(value.args) == 1 and all(k.arg == "timeout" for k in value.keywords)):
        value = value.args[0]
    if (keyword.arg == "transport" and isinstance(value, (ast.Name, ast.Attribute))
            and IDENTITY_WRAPPERS.get(_qualified(value, imports) or "") == client):
        return id(value)
    return None


def _wrapper_misuse(rel: str, tree: ast.Module, imports: dict[str, str]) -> list[str]:
    """Every use of an identity wrapper outside its own module that is not its own client's ``transport=``."""
    allowed = {_wrapper_handed_over(k, _qualified(node.func, imports), imports)
               for node in ast.walk(tree) if isinstance(node, ast.Call) for k in node.keywords}
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        name = _qualified(node, imports)
        if name not in IDENTITY_WRAPPERS or _is_inner_part(node, tree):
            continue
        own = name.rpartition(".")[0].replace(".", "/") + ".py"
        if rel != own and id(node) not in allowed:
            problems.append(f"{rel}:{node.lineno} {name} is {own}'s identity: only its client may take it as "
                            "transport=")
    return problems


def _is_inner_part(node: ast.expr, tree: ast.Module) -> bool:
    """True when ``node`` is the ``value`` of a larger Attribute (``a`` in ``a.b``): the outer node is judged."""
    return any(isinstance(n, ast.Attribute) and n.value is node for n in ast.walk(tree))


def _backend_files() -> dict[str, str]:
    return {p.relative_to(BACKEND).as_posix(): p.read_text(encoding="utf-8") for p in sorted(BACKEND.rglob("*.py"))}


def test_every_kite_door_call_passes_its_own_module_identity() -> None:
    """REQ-073 AC-4 (#353): the whole backend passes the scan."""
    problems = [p for rel, source in _backend_files().items() for p in scan_source(rel, source)]
    assert problems == []


def test_the_allow_list_names_only_real_modules_each_with_its_own_door_call() -> None:
    """REQ-073 AC-4 (#353): each key is an existing file, each CALLER_* constant is a key and every key has one, and
    every listed module really calls a door with its identity (a stale entry is a hole)."""
    files = _backend_files()
    constants = {getattr(kite_endpoints, n) for n in kite_endpoints.__all__ if n.startswith("CALLER_")}
    assert constants == set(ALLOWED_CALLS)
    for rel in ALLOWED_CALLS:
        assert rel in files, f"{rel} is listed but does not exist"
        tree = ast.parse(files[rel])
        imports = _imports(tree, rel)
        own = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _qualified(n.func, imports) in DOOR_CALLABLES
               and any(k.arg == "caller" and isinstance(k.value, ast.Name)
                       and getattr(kite_endpoints, imports.get(k.value.id, "").rpartition(".")[2], None) == rel
                       for k in n.keywords)]
        assert own, f"{rel} is listed but never calls a door as itself"


# -- planted modules: each shape the scan must refuse -----------------------------------------------------------------

GOOD = "from ofo.broker.kite_endpoints import CALLER_KITE_READS\nfrom ofo.broker.kite_http import check_call\n"
PLANTED = {
    "no_caller": "from ofo.broker.kite_http import check_call\ncheck_call('GET', 'u')\n",
    "renamed_alias_no_caller": "from ofo.broker.kite_http import open_url as fetch\nfetch('u')\n",
    "module_attribute_no_caller": "from ofo.broker import kite_http\nkite_http.check_call('GET', 'u')\n",
    "dotted_import_no_caller": "import ofo.broker.kite_http\nofo.broker.kite_http.open_url('u')\n",
    "literal_caller": "from ofo.broker.kite_http import check_call\n"
                      "check_call('GET', 'u', caller='ofo_app/kite_reads.py')\n",
    "another_modules_constant": "from ofo.broker.kite_endpoints import CALLER_KITE_MARGIN\n"
                                "from ofo.broker.kite_http import check_call\n"
                                "check_call('GET', 'u', caller=CALLER_KITE_MARGIN)\n",
    "constant_from_elsewhere": "from somewhere import CALLER_KITE_READS\nfrom ofo.broker.kite_http import check_call\n"
                               "check_call('GET', 'u', caller=CALLER_KITE_READS)\n",
    "computed_caller": GOOD + "check_call('GET', 'u', caller=CALLER_KITE_READS + '')\n",
    "kwargs_call": GOOD + "check_call('GET', 'u', **{'caller': CALLER_KITE_READS})\n",
    "partial_of_door": "import functools\nfrom ofo.broker.kite_http import open_url\n"
                       "f = functools.partial(open_url, caller=None)\n",
    "getattr_lookup": "from ofo.broker import kite_http\ngetattr(kite_http, 'check_call')('GET', 'u')\n",
    "httpx_client_no_caller": "from ofo_app.kite_http import KiteClient\nKiteClient()\n",
    "factory_another_module": "from ofo.broker.kite_endpoints import CALLER_KITE_CLIENT\n"
                              "from ofo_app import kite_http\nkite_http.kite_async_client(caller=CALLER_KITE_CLIENT)\n",
    "margin_transport_reuse": "from ofo.broker.kite_endpoints import CALLER_KITE_READS\n"
                              "from ofo_app.kite_margin import urllib_transport\n"
                              "urllib_transport('GET', 'u', {}, None, caller=CALLER_KITE_READS)\n",
    "fake_forwarder": "from ofo_app.kite_margin import urllib_transport\n"
                      "def urllib_transport2(caller):\n    urllib_transport('GET', 'u', {}, None, caller=caller)\n",
    # #353 round 2: the identity wrappers outside their module, other than their own client's transport=
    "reads_transport_called": "from ofo_app.kite_reads import reads_transport\n"
                              "reads_transport('GET', 'https://api.kite.trade/orders', {}, None)\n",
    "margin_transport_called": "from ofo_app import kite_margin\n"
                               "kite_margin.margin_transport('GET', 'https://api.kite.trade/user/margins', {}, None)\n",
    "wrapper_as_value": "from ofo_app.kite_reads import reads_transport as t\nsend = t\n",
    "wrapper_to_another_client": "from ofo_app.kite_margin import KiteMargin\n"
                                 "from ofo_app.kite_reads import reads_transport\n"
                                 "KiteMargin(api_key='k', access_token='t', transport=reads_transport)\n",
    "wrapper_partial_other_keyword": "import functools\nfrom ofo_app.kite_reads import KiteReads, reads_transport\n"
                                     "KiteReads(api_key='k', access_token='t',\n"
                                     "          transport=functools.partial(reads_transport, headers={}))\n",
    "relative_import": "from ..broker.kite_http import check_call\n",
    "importlib": "import importlib\nimportlib.import_module('ofo.broker.kite_http')\n",
    "dunder_import": "__import__('ofo.broker.kite_http')\n",
}


@pytest.mark.parametrize("key", sorted(PLANTED))
def test_a_planted_call_site_fails_the_scan(key: str) -> None:
    """REQ-073 AC-4 (#353 attack 3, B4 c): every unresolvable or wrong-identity shape fails closed; the planted file
    is the reads module or a route (``margin_transport_reuse`` from the reads module's own constant is a route)."""
    rel = "ofo_app/routes/planted.py" if key != "another_modules_constant" else "ofo_app/kite_reads.py"
    assert scan_source(rel, PLANTED[key]) != [], key


def test_a_new_module_calling_a_listed_read_without_being_listed_fails() -> None:
    """REQ-073 AC-4 (#353 attack 3): a new module borrowing the reads module's constant to fetch positions fails."""
    source = ("from ofo.broker.kite_endpoints import CALLER_KITE_READS\nfrom ofo_app.kite_reads import reads_transport\n"
              "from ofo.broker.kite_http import open_url\n"
              "open_url('https://api.kite.trade/portfolio/positions', caller=CALLER_KITE_READS)\n")
    assert scan_source("ofo_app/positions_helper.py", source) != []


def test_the_own_identity_and_the_listed_forwarder_pass() -> None:
    """The allowed shapes: the file's own constant, and the one forwarder passing its own caller parameter."""
    assert scan_source("ofo_app/kite_reads.py", GOOD + "check_call('GET', 'u', caller=CALLER_KITE_READS)\n") == []
    forwarder = ("from ofo.broker.kite_http import open_url as kite_open_url\n"
                 "def urllib_transport(method, url, headers, body, *, caller, timeout=20):\n"
                 "    return kite_open_url(url, caller=caller)\n")
    assert scan_source("ofo_app/kite_margin.py", forwarder) == []
    assert scan_source("ofo_app/kite_reads.py", forwarder) != []  # the same forwarder elsewhere is not listed


def test_an_identity_wrapper_passes_only_as_its_own_clients_transport() -> None:
    """#353 round 2 (review finding 3): ``reads_transport`` / ``margin_transport`` handed to their own client as
    ``transport=`` (bare or ``functools.partial(..., timeout=...)``) pass anywhere; inside their own module any use
    passes."""
    route = ("import functools\nfrom ofo_app.kite_margin import KiteMargin, margin_transport\n"
             "from ofo_app.kite_reads import KiteReads, reads_transport\n"
             "KiteMargin(api_key='k', access_token='t', transport=functools.partial(margin_transport, timeout=5))\n"
             "KiteReads(api_key='k', access_token='t', transport=reads_transport)\n")
    assert scan_source("ofo_app/live_market.py", route) == []
    own = "def reads_transport(method, url, headers, body):\n    return None\nx = reads_transport\n"
    assert scan_source("ofo_app/kite_reads.py", own) == []
