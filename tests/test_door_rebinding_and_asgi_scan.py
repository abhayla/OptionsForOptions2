"""Issue #200 (REQ-065 AC-2 remainder after W-070; findings guard-by-banned-shapes, sealed-object-mutable-after-seal).

ADR-003 Q235: the door's checks "are flagged in CI when code reaches into their internals"; deliberately replacing a
checker at runtime "is out of scope, and the CI source scan flags it". Two scans over every product file under
backend/ (backend/ofo and backend/ofo_app, the W-065 socket door route in routes/live.py included):

1. **Module rebinding (N1-N3).** No product file assigns to, or deletes, an attribute of a name bound by an import
   (``errors.KITE_LOGIN_PAGE = ...``, ``errors._check_location = ...``, ``del errors.WWW_AUTHENTICATE``), whatever
   the module, through ``=``, ``+=``, an annotation, ``del``, a ``for``/``with`` target or a tuple target, also through a
   plain copy of the name (``e = errors; e.X = ...``). It is an allow-list: ``REBIND_ALLOWED`` names each file and
   dotted target that may do it, with a reason (one entry: the wording checker freezing its own module class).
2. **The ASGI send path (N5).** No product file calls a response object as an ASGI app (a call on the result of a
   response maker, directly or through a name), touches the ASGI handles of a request (``.scope``, ``_send``,
   ``_receive``, ``__call__``, as an attribute, a name or a string), or writes into a ``scope`` (``scope[...] = ``,
   ``del scope[...]``, ``scope.update(...)``). ``ASGI_ALLOWED`` lets only the door module (errors.py) do it.

The runtime half of N5 (the seal marks only the response actually sent) is tested in tests_app/test_response_door.py.
"""
import ast
from pathlib import Path

import pytest

from test_door_names_private import _fold

pytestmark = pytest.mark.repo_scan

BACKEND = Path(__file__).resolve().parents[1] / "backend"

#: Files allowed to assign to / delete an attribute of an import-bound name: path -> (dotted targets, reason).
REBIND_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "ofo/wording.py": (frozenset({"_this_module.__class__"}),
                       "ADR-056: the wording checker imports ITSELF and swaps its own module class once, at import, for "
                       "the read-only _FrozenModule (the guard that refuses rebinding of the checker's names)"),
}

#: Files allowed to use the ASGI send path: path -> (kinds, reason).
ASGI_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "ofo_app/errors.py": (frozenset({"asgi-call", "scope-write"}),
                          "the door itself: _send_frozen stamps the seal into the scope and _Boundary sends its own "
                          "500 response as an ASGI app"),
}

ASGI_HANDLES = frozenset({"scope", "_send", "_receive", "__call__"})
SCOPE_MUTATORS = frozenset({"update", "setdefault", "pop", "popitem", "clear", "__setitem__", "__delitem__"})
RESPONSE_MAKERS = frozenset({"respond", "typed_redirect", "handle_error"})


def _product_files() -> list[Path]:
    return [p for p in BACKEND.rglob("*.py") if "__pycache__" not in p.parts]


def _root(node: ast.AST) -> ast.AST:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node


def _targets(node: ast.AST) -> list[ast.AST]:
    """Every assignment / deletion target the statement writes, tuples and starred targets unpacked."""
    if isinstance(node, ast.Assign):
        raw = list(node.targets)
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor, ast.comprehension)):
        raw = [node.target]
    elif isinstance(node, ast.Delete):
        raw = list(node.targets)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        raw = [i.optional_vars for i in node.items if i.optional_vars is not None]
    else:
        return []
    out: list[ast.AST] = []
    while raw:
        t = raw.pop()
        if isinstance(t, (ast.Tuple, ast.List)):
            raw.extend(t.elts)
        elif isinstance(t, ast.Starred):
            raw.append(t.value)
        else:
            out.append(t)
    return out


def _import_bound(tree: ast.AST) -> set[str]:
    """Names the file binds by an import, plus plain copies of them (``e = errors``, ``s = errors.sub``)."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bound |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            bound |= {a.asname or a.name for a in node.names if a.name != "*"}
    for _ in range(10):
        before = len(bound)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                root = _root(node.value)
                if isinstance(node.value, (ast.Name, ast.Attribute)) and isinstance(root, ast.Name) and root.id in bound:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    bound |= {t.id for t in targets if isinstance(t, ast.Name)}
        if len(bound) == before:
            break
    return bound


def _text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse handles every expression ast.parse produces
        return "<expr>"


def rebinding_uses(source: str) -> list[tuple[int, str]]:
    """(line, dotted target) for every attribute of an import-bound name the source assigns to or deletes."""
    tree = ast.parse(source)
    bound = _import_bound(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for target in _targets(node):
            if isinstance(target, ast.Attribute):
                root = _root(target)
                if isinstance(root, ast.Name) and root.id in bound:
                    found.append((target.lineno, _text(target)))
    return found


def rebinding_violations(source: str, where: str, allowed: dict[str, tuple[frozenset[str], str]] | None = None) -> list[str]:
    ok = (REBIND_ALLOWED if allowed is None else allowed).get(where, (frozenset(), ""))[0]
    return [f"{where}:{line} assigns to or deletes {dotted} (a name bound by an import)"
            for line, dotted in rebinding_uses(source) if dotted not in ok]


def _docstrings(tree: ast.AST) -> set[int]:
    return {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}


def _maker_call(node: ast.AST) -> bool:
    """A call (awaited or not) of a door response maker or of anything named ...Response / ...Redirect."""
    if isinstance(node, ast.Await):
        node = node.value
    if not isinstance(node, ast.Call):
        return False
    leaf = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
    return leaf in RESPONSE_MAKERS or leaf.lower().endswith(("response", "redirect"))


def _is_scope(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "scope") or (isinstance(node, ast.Attribute) and node.attr == "scope")


def asgi_uses(source: str) -> list[tuple[int, str, str]]:
    """(line, kind, detail): kind `asgi-call` (a response object called as an ASGI app), `handle` (an ASGI handle named:
    attribute, name or string) or `scope-write` (a write into a scope)."""
    tree = ast.parse(source)
    docs = _docstrings(tree)
    responses: set[str] = set()
    for node in ast.walk(tree):  # names bound to a response object
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None and _maker_call(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            responses |= {t.id for t in targets if isinstance(t, ast.Name)}
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Call):
            func = node.func.value if isinstance(node.func, ast.Await) else node.func
            if _maker_call(func) or (isinstance(func, ast.Name) and func.id in responses):
                found.append((line, "asgi-call", _text(node)))
            if isinstance(node.func, ast.Attribute) and node.func.attr in SCOPE_MUTATORS and _is_scope(node.func.value):
                found.append((line, "scope-write", _text(node)))
        if isinstance(node, ast.Attribute) and node.attr in ASGI_HANDLES:
            found.append((line, "handle", node.attr))
        elif isinstance(node, ast.Name) and node.id in ASGI_HANDLES - {"scope"}:
            found.append((line, "handle", node.id))
        elif isinstance(node, ast.alias) and {node.name.split(".")[-1], node.asname} & (ASGI_HANDLES - {"scope"}):
            found.append((line, "handle", node.name))
        elif isinstance(node, ast.keyword) and node.arg in ASGI_HANDLES - {"scope"}:
            found.append((line, "handle", str(node.arg)))
        elif isinstance(node, ast.arg) and node.arg in ASGI_HANDLES - {"scope"}:
            found.append((line, "handle", node.arg))
        elif isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.Call)) and id(node) not in docs:
            text = _fold(node)
            if text in ASGI_HANDLES:
                found.append((line, "handle", f"the string {text!r}"))
        for target in _targets(node):
            if isinstance(target, ast.Subscript) and _is_scope(target.value):
                found.append((target.lineno, "scope-write", _text(target)))
    return found


def asgi_violations(source: str, where: str, allowed: dict[str, tuple[frozenset[str], str]] | None = None) -> list[str]:
    ok = (ASGI_ALLOWED if allowed is None else allowed).get(where, (frozenset(), ""))[0]
    return [f"{where}:{line} {kind}: {detail}" for line, kind, detail in asgi_uses(source) if kind not in ok]


def _scan(path: Path) -> tuple[str, str]:
    return path.relative_to(BACKEND).as_posix(), path.read_text(encoding="utf-8")


# --- the real backend ------------------------------------------------------------------------------------------------

def test_the_scans_walk_every_product_file_including_the_socket_door_route() -> None:
    """AC-2 (#200): the walk covers both packages and the W-065 socket door route (routes/live.py)."""
    names = {_scan(p)[0] for p in _product_files()}
    assert len(names) > 50
    assert {"ofo_app/routes/live.py", "ofo_app/errors.py", "ofo_app/live_push.py", "ofo/errors/model.py"} <= names


def test_no_product_file_assigns_to_or_deletes_an_attribute_of_an_imported_name() -> None:
    """AC-2 (#200 N1-N3): the module-rebinding allow-list scan is clean on the real backend."""
    bad = [v for p in _product_files() for v in rebinding_violations(_scan(p)[1], _scan(p)[0])]
    assert bad == []


def test_no_product_file_but_the_door_uses_the_asgi_send_path() -> None:
    """AC-2 (#200 N5): the ASGI send-path scan is clean on the real backend outside its allow-list."""
    bad = [v for p in _product_files() for v in asgi_violations(_scan(p)[1], _scan(p)[0])]
    assert bad == []


def test_every_asgi_allowance_is_real_and_used() -> None:
    """A stale allowance is a hole: each allowed file exists and really uses every kind it is allowed."""
    for where, (kinds, reason) in ASGI_ALLOWED.items():
        assert reason
        used = {kind for _, kind, _ in asgi_uses((BACKEND / where).read_text(encoding="utf-8"))}
        assert kinds <= used, where
    for where, (targets, reason) in REBIND_ALLOWED.items():
        assert reason and targets <= {d for _, d in rebinding_uses((BACKEND / where).read_text(encoding="utf-8"))}


def test_no_route_file_gets_an_asgi_or_rebinding_allowance() -> None:
    assert not [w for w in {*ASGI_ALLOWED, *REBIND_ALLOWED} if w.startswith("ofo_app/routes/")]


# --- the verifier's probes (issue #200), as product-file fixtures --------------------------------------------------------

N1 = """
from fastapi import APIRouter
from ofo_app import errors
from ofo_app.routes.broker import BrokerRedirectOut

errors.KITE_LOGIN_PAGE = "https://evil.example/steal"

async def go():
    return errors.typed_redirect(BrokerRedirectOut(redirect="connected"), "https://evil.example/steal?v=3")
"""
N2 = """
from ofo_app import errors
errors._check_location = lambda location: None
"""
N3 = """
import ofo_app.errors
ofo_app.errors.WWW_AUTHENTICATE = 'Basic realm="You should buy NIFTY..."'
"""
N5 = """
from fastapi import Request
from ofo_app.errors import respond

async def nowhere(message):
    return None

async def endpoint(request: Request):
    await respond(MODEL, 200)(request.scope, request.receive, nowhere)
    await request._send({"type": "http.response.start", "status": 200, "headers": [(b"x-evil", b"unminted")]})
"""


@pytest.mark.parametrize("source, expected", [
    (N1, "errors.KITE_LOGIN_PAGE"),
    (N2, "errors._check_location"),
    (N3, "ofo_app.errors.WWW_AUTHENTICATE"),
])
def test_n1_n2_n3_each_probe_is_flagged_in_a_route_file(source: str, expected: str) -> None:
    """AC-2 (#200 N1-N3): each verifier probe, as a product file, is a violation naming its target."""
    bad = rebinding_violations(source, "ofo_app/routes/planted.py")
    assert any(expected in v for v in bad), bad


def test_n5_the_probe_is_flagged_on_every_count() -> None:
    """AC-2 (#200 N5): the probe is flagged as an ASGI call of a response, for `.scope` and for `_send`."""
    kinds = {(k, d) for _, k, d in asgi_uses(N5)}
    assert any(k == "asgi-call" for k, _ in kinds)
    assert ("handle", "scope") in kinds and ("handle", "_send") in kinds
    assert asgi_violations(N5, "ofo_app/routes/planted.py")


@pytest.mark.parametrize("source", [
    "from ofo_app import errors\ndel errors.WWW_AUTHENTICATE",
    "from ofo_app import errors\nerrors.STATUS_BY_CLASS += 1",
    "from ofo_app import errors\nerrors.X: str = 'y'",
    "from ofo_app import errors\ne = errors\ne.KITE_LOGIN_PAGE = 'x'",
    "from ofo_app import errors\ne = errors\nf = e\nf._check_location = None",
    "from ofo_app import errors as E\nE.WWW_AUTHENTICATE = 'x'",
    "import ofo_app.errors as E\nE.WWW_AUTHENTICATE = 'x'",
    "from ofo_app.errors import ClosedResponse\nClosedResponse.__call__ = None",
    "from ofo_app import errors\na, errors.KITE_LOGIN_PAGE = 1, 'x'",
    "from ofo_app import errors\nfor errors.KITE_LOGIN_PAGE in ['x']:\n    pass",
    "from ofo_app import errors\nwith open('f') as errors.KITE_LOGIN_PAGE:\n    pass",
    "import json\njson.dumps = None",
    "from ofo_app import errors\nerrors.log.disabled = True",
    "from ofo_app import errors\ndef f():\n    errors.KITE_LOGIN_PAGE = 'x'",
])
def test_the_rebinding_scan_refuses_every_write_shape(source: str) -> None:
    assert rebinding_violations(source, "ofo_app/planted.py")


@pytest.mark.parametrize("source", [
    "from ofo_app import errors\nx = errors.KITE_LOGIN_PAGE",
    "class A:\n    def __init__(self):\n        self.x = 1",
    "def f(o):\n    o.x = 1\n    del o.x",
    "from dataclasses import dataclass\n@dataclass\nclass P:\n    a: int = 0\np = P()\np.a = 2",
])
def test_the_rebinding_scan_passes_ordinary_attribute_writes(source: str) -> None:
    assert rebinding_violations(source, "ofo_app/planted.py") == []


def test_a_rebinding_allowance_covers_only_its_own_file_and_target() -> None:
    allowed = {"ofo_app/x.py": (frozenset({"errors.A"}), "reason")}
    src = "from ofo_app import errors\nerrors.A = 1\nerrors.B = 2"
    assert rebinding_violations(src, "ofo_app/x.py", allowed) == ["ofo_app/x.py:3 assigns to or deletes errors.B "
                                                                  "(a name bound by an import)"]
    assert len(rebinding_violations(src, "ofo_app/y.py", allowed)) == 2


@pytest.mark.parametrize("source", [
    "async def f(scope, receive, send):\n    await respond(m, 200)(scope, receive, send)",
    "async def f(s, r, x):\n    resp = respond(m, 200)\n    await resp(s, r, x)",
    "async def f(s, r, x):\n    resp = await handle_error(q, e)\n    await resp(s, r, x)",
    "async def f(s, r, x):\n    await typed_redirect(m, '/a')(s, r, x)",
    "async def f(s, r, x):\n    await ClosedResponse(m)(s, r, x)",
    "async def f(s, r, x):\n    await JSONResponse({})(s, r, x)",
    "def f(request):\n    return request.scope",
    "def f(request):\n    return request._send",
    "def f(request):\n    return request._receive",
    "def f(r):\n    return r.__call__",
    "def f(request):\n    return getattr(request, 'scope')",
    "def f(x):\n    return x['scope']",  # the string is an ASGI handle name: flagged, fail closed
    "def f(request):\n    return getattr(request, 'sc' + 'ope')",
    "def f(request):\n    return getattr(request, f'_{\"send\"}')",
    "from starlette.requests import _send",
    "def f(_send):\n    pass",
    "def f():\n    return _receive",
    "def f(scope):\n    scope['ofo.door'] = 1",
    "def f(request):\n    request.scope['ofo.door'] = 1",
    "def f(scope):\n    del scope['k']",
    "def f(scope):\n    scope.update({'k': 1})",
    "def f(scope):\n    scope.setdefault('k', 1)",
    "def f(scope):\n    scope.__setitem__('k', 1)",
])
def test_the_asgi_scan_refuses_every_shape(source: str) -> None:
    assert asgi_violations(source, "ofo_app/routes/planted.py")


@pytest.mark.parametrize("source", [
    "async def f(socket):\n    msg = await socket.receive()\n    await socket.send(msg)",
    "def f():\n    return respond(m, 200)",
    "def f(x):\n    return x['scopes']",
    "class C:\n    def __call__(self):\n        return 1",
    "def f(handler, a, b, c):\n    return handler(a, b, c)",
])
def test_the_asgi_scan_passes_ordinary_code(source: str) -> None:
    assert asgi_violations(source, "ofo_app/planted.py") == []


def test_the_door_allowance_does_not_cover_handles() -> None:
    """errors.py is allowed the ASGI call and the scope write only; a `.scope` or `_send` there would still be flagged."""
    assert "handle" not in ASGI_ALLOWED["ofo_app/errors.py"][0]
    assert asgi_violations("def f(request):\n    return request._send", "ofo_app/errors.py")


def test_a_planted_route_file_is_caught_by_the_real_scans(tmp_path: Path) -> None:
    """AC-2 (#200): N1, N2, N3 and N5 planted as files beside the real routes fail the same check the backend test runs."""
    root = tmp_path / "ofo_app" / "routes"
    root.mkdir(parents=True)
    for name, source in (("n1.py", N1), ("n2.py", N2), ("n3.py", N3), ("n5.py", N5)):
        (root / name).write_text(source, encoding="utf-8")
    bad = {}
    for p in root.glob("*.py"):
        where = p.relative_to(tmp_path).as_posix()
        text = p.read_text(encoding="utf-8")
        bad[p.name] = rebinding_violations(text, where) + asgi_violations(text, where)
    assert all(bad[n] for n in ("n1.py", "n2.py", "n3.py", "n5.py")), bad
