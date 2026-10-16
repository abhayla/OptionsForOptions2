"""W-024 round 9 part 6: in backend/ofo_app, response bodies come only from the boundary (ofo_app/errors.py) or a
typed `ApiModel` (REQ-065 AC-2, ADR-003 Q226).

Layer 1, structural (fix round, review MAJOR-2; fails closed) - outside errors.py, a file may not:
- import, name or construct a Response class, `HTTPException` / `StarletteHTTPException` / `WebSocketException`, or
  `BaseHTTPMiddleware` (by import of the name, of its module, or by any reference to the name: alias, attribute, call,
  raise);
- declare a route (`.get/.post/... /api_route` decorator, `add_api_route`) without `response_model=`, which must be an
  `ApiModel` (asserted at runtime over the real app in tests_app/test_api_models.py); declare a websocket route; call
  a Starlette websocket sender (`send_text/send_json/send_bytes`); register middleware or an exception handler.
Layer 2, the earlier body scan, kept as a second layer: a response constructor's arguments, a route's return value
and a background task's arguments hold no f-string, `str()`/`repr()`/`format()`/`.join()`, `%` or `+` string
building, `except ... as e` name, or sentence.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
DOOR = "errors.py"
BANNED_NAMES = frozenset({
    "Response", "JSONResponse", "ORJSONResponse", "UJSONResponse", "RedirectResponse", "StreamingResponse",
    "PlainTextResponse", "HTMLResponse", "FileResponse", "ClosedResponse", "SealedRedirect", "HTTPException", "StarletteHTTPException",
    "WebSocketException", "BaseHTTPMiddleware",
})
BANNED_MODULES = frozenset({"fastapi.responses", "starlette.responses", "starlette.exceptions",
                            "starlette.middleware.base", "fastapi.exceptions"})
RESPONSES = BANNED_NAMES - {"BaseHTTPMiddleware"}
TEXT_CALLS = frozenset({"str", "repr", "format", "join"})
ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "api_route", "add_api_route"})
WEBSOCKET = frozenset({"websocket", "websocket_route", "add_websocket_route", "send_text", "send_json", "send_bytes"})
REGISTRATIONS = frozenset({"middleware", "add_middleware", "add_exception_handler", "exception_handler"})
_WORD = re.compile(r"[A-Za-z]")
#: The one allowed naming of a banned name (W-080): the Kite door's OUTBOUND client annotates the reply Kite sends us
#: as ``httpx.Response``; that is the type of a reply we RECEIVE, never a body we build. Allowed only in this file,
#: only as the attribute ``Response`` of a name bound once, by ``import httpx [as alias]``, and only inside a type
#: annotation (a parameter, a return type, an annotated assignment). A construction ``_httpx.Response(...)``, an import
#: of ``Response`` from any module, any other attribute, or the same annotation in any other file is still refused.
OUTBOUND_ANNOTATIONS = {"kite_http.py": ("httpx", "Response")}


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _sentence(text: str) -> bool:
    return sum(1 for token in text.split() if _WORD.search(token)) >= 2


def _bad_parts(node: ast.AST, bound: frozenset[str]) -> list[str]:
    bad = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            bad.append("f-string")
        elif isinstance(sub, ast.Call) and _name(sub.func) in TEXT_CALLS:
            bad.append(f"{_name(sub.func)}()")
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.Mod, ast.Add)) and any(
                isinstance(side, ast.Constant) and isinstance(side.value, str) for side in (sub.left, sub.right)):
            bad.append("string building")
        elif isinstance(sub, ast.Name) and sub.id in bound:
            bad.append(f"exception name {sub.id!r}")
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _sentence(sub.value):
            bad.append(f"sentence {sub.value[:40]!r}")
    return bad


def _is_route(fn: ast.AST) -> bool:
    return isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        isinstance(d, ast.Call) and _name(d.func) in ROUTE_METHODS | {"websocket"} for d in fn.decorator_list)


def _bindings(tree: ast.AST) -> dict[str, list[ast.AST]]:
    """Every node that binds a name anywhere in the file (imports, assignments, defs, arguments, ``except as``)."""
    out: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.asname or a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            names = [node.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names = [node.name]
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names = list(node.names)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            names = [node.name]
        for name in names:
            out.setdefault(name, []).append(node)
    return out


def _allowed_outbound(tree: ast.AST, rel: str) -> set[int]:
    """The ids of the annotation nodes ``<httpx alias>.Response`` that OUTBOUND_ANNOTATIONS allows in ``rel``."""
    if rel not in OUTBOUND_ANNOTATIONS:
        return set()
    module, attr = OUTBOUND_ANNOTATIONS[rel]
    bindings = _bindings(tree)
    aliases = {name for name, nodes in bindings.items() if len(nodes) == 1 and isinstance(nodes[0], ast.Import)
               and any(a.name == module and (a.asname or a.name) == name for a in nodes[0].names)}
    annotations: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
    # An annotation that runs code (a call, a walrus, a lambda) is not a plain type name: nothing inside it is allowed.
    plain = [ann for ann in annotations
             if not any(isinstance(sub, (ast.Call, ast.NamedExpr, ast.Lambda)) for sub in ast.walk(ann))]
    return {id(sub) for ann in plain for sub in ast.walk(ann)
            if isinstance(sub, ast.Attribute) and sub.attr == attr and isinstance(sub.value, ast.Name)
            and sub.value.id in aliases}


def structural(source: str, rel: str) -> list[str]:
    """Layer 1."""
    if rel == DOOR:
        return []
    found: list[str] = []
    tree = ast.parse(source)
    outbound = _allowed_outbound(tree, rel)
    decorators = {id(d) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  for d in n.decorator_list}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) \
                and node.value.attr in ROUTE_METHODS | {"websocket"}:
            found.append(f"{rel}:{line} route method {node.value.attr} aliased: routes are declared as decorators")
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in BANNED_MODULES:
                found.append(f"{rel}:{line} imports {module}")
            for alias in node.names:
                if alias.name in BANNED_NAMES or f"{module}.{alias.name}" in BANNED_MODULES:
                    found.append(f"{rel}:{line} imports {alias.name}")
        elif isinstance(node, ast.Import):
            found.extend(f"{rel}:{line} imports {a.name}" for a in node.names if a.name in BANNED_MODULES)
        elif isinstance(node, (ast.Name, ast.Attribute)) and _name(node) in BANNED_NAMES and id(node) not in outbound:
            found.append(f"{rel}:{line} uses {_name(node)}")
        elif isinstance(node, ast.Call):
            callee = _name(node.func)
            is_route_call = callee in {"add_api_route", "api_route"} or (callee in ROUTE_METHODS and id(node) in decorators)
            if is_route_call and not any(k.arg == "response_model" for k in node.keywords):
                found.append(f"{rel}:{line} route without response_model ({callee})")
            if callee in WEBSOCKET:
                found.append(f"{rel}:{line} websocket {callee} outside {DOOR}")
            if callee in REGISTRATIONS:
                found.append(f"{rel}:{line} {callee} outside {DOOR}")
    return found


def body_scan(source: str, rel: str) -> list[str]:
    """Layer 2 (the earlier scan)."""
    if rel == DOOR:
        return []
    found: list[str] = []

    def walk(node: ast.AST, bound: frozenset[str], route: bool) -> None:
        for child in ast.iter_child_nodes(node):
            names = bound | {child.name} if isinstance(child, ast.ExceptHandler) and child.name else bound
            in_route = _is_route(child) if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else route
            if isinstance(child, ast.Call):
                callee = _name(child.func)
                if callee in RESPONSES or callee == "add_task":
                    for arg in [*child.args, *(k.value for k in child.keywords)]:
                        found.extend(f"{rel}:{child.lineno} {callee}: {b}" for b in _bad_parts(arg, names))
            if isinstance(child, ast.Return) and route and child.value is not None:
                found.extend(f"{rel}:{child.lineno} route return: {b}" for b in _bad_parts(child.value, names))
            walk(child, names, in_route)

    walk(ast.parse(source), frozenset(), False)
    return found


def scan(source: str, rel: str) -> list[str]:
    return structural(source, rel) + body_scan(source, rel)


def test_ofo_app_builds_no_error_body_outside_the_boundary() -> None:
    rows = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        rows.extend(scan(path.read_text(encoding="utf-8"), rel))
    assert not rows, "response text built outside ofo_app/errors.py:\n" + "\n".join(rows)


def test_scan_covers_the_routes_package() -> None:
    assert any(p.name == "health.py" for p in APP.rglob("*.py"))


# --- samples: each must be refused ------------------------------------------------------------------------------

#: The reviewer's probe shapes (scratchpad probe/scanprobe.py), all 14; 11 escaped the round-6 scan.
REVIEWER_SHAPES = {
    "var_then_return": '@router.get("/x")\nasync def x():\n    try:\n        pass\n    except ValueError as exc:\n'
                       '        msg = f"Leg failed: {exc}"\n        return {"error": msg}\n',
    "helper_fn": 'def body(e):\n    return {"error": f"failed {e}"}\n@router.get("/x")\nasync def x():\n    try:\n'
                 '        pass\n    except ValueError as exc:\n        return body(exc)\n',
    "alias_exc": '@router.get("/x")\nasync def x():\n    try:\n        pass\n    except ValueError as exc:\n'
                 '        err = exc\n        return {"error": err.args}\n',
    "concat": '@router.get("/x")\nasync def x(name):\n    return {"error": "Expired:" + name}\n',
    "join": '@router.get("/x")\nasync def x(w):\n    return {"error": " ".join(["Leg", "expired", w])}\n',
    "route_add_api_route": 'def x():\n    return {"error": "leg expired before execution"}\napp.add_api_route("/x", x)\n',
    "websocket_send": '@router.websocket("/ws")\nasync def ws(sock):\n    try:\n        pass\n'
                      '    except Exception as exc:\n        await sock.send_text(str(exc))\n',
    "middleware": '@app.middleware("http")\nasync def mw(request, call_next):\n    try:\n'
                  '        return await call_next(request)\n    except Exception as exc:\n'
                  '        return ORJSONResponse({"error": str(exc)})\n',
    "redirect_resp": 'def f(e):\n    return RedirectResponse(url=f"/err?msg={e}")\n',
    "starlette_exc": 'def f():\n    raise StarletteHTTPException(404, detail="Leg expired before execution")\n',
    "ws_exc": 'def f(e):\n    raise WebSocketException(code=1008, reason=str(e))\n',
    "pydantic_model": '@router.get("/x")\nasync def x():\n    try:\n        pass\n    except ValueError as exc:\n'
                      '        return ErrorOut(error=exc.args[0])\n',
    "decorated_alias": 'get = router.get\n@get("/x")\nasync def x():\n    return {"error": "leg expired before execution"}\n',
    "background": '@router.post("/x")\nasync def x(bg):\n    bg.add_task(notify, f"Order failed {1}")\n'
                  '    return {"ok": True}\n',
}
OWN_SAMPLES = (
    'from ofo_app.errors import ClosedResponse\n',
    'def f(r):\n    return SealedRedirect(r)\n',
    'def f(r):\n    return errors.ClosedResponse(r)\n',
    'from fastapi.responses import JSONResponse\n',
    'import starlette.responses\n',
    'from fastapi import HTTPException as H\n',
    'from fastapi import responses\n',
    'def f(r):\n    return r.JSONResponse({})\n',
    'def make(app):\n    app.add_exception_handler(ValueError, handler)\n',
    'def make(app):\n    app.add_middleware(Thing)\n',
)


def test_every_reviewer_shape_is_refused() -> None:
    missed = [name for name, src in REVIEWER_SHAPES.items() if not scan(src, "routes/sample.py")]
    assert missed == []


def test_structural_layer_alone_refuses_eleven_or_more_of_the_reviewer_shapes() -> None:
    refused = [name for name, src in REVIEWER_SHAPES.items() if structural(src, "routes/sample.py")]
    assert len(refused) >= 11, refused


def test_own_samples_are_refused() -> None:
    for src in OWN_SAMPLES:
        assert structural(src, "routes/sample.py"), src


def test_a_typed_route_and_the_door_pass() -> None:
    ok = ('from ofo_app.api_models import ApiModel\n'
          '@router.get("/health", response_model=HealthOut)\nasync def h():\n    return HealthOut(status="healthy")\n')
    assert scan(ok, "routes/sample.py") == []
    assert scan(REVIEWER_SHAPES["middleware"], DOOR) == []


def test_mutant_without_the_response_model_rule_lets_the_route_shapes_through(monkeypatch) -> None:
    """Mutation: drop the response_model rule (treat every route as typed) -> route-only shapes escape layer 1."""
    import sys

    monkeypatch.setattr(sys.modules[__name__], "ROUTE_METHODS", frozenset())
    assert structural(REVIEWER_SHAPES["concat"], "routes/sample.py") == []


# --- the outbound-client allowance (W-080): the reply Kite sends us, annotated in kite_http.py only ---------------

KITE_HTTP = APP / "kite_http.py"
_ANNOTATED = 'import httpx as _httpx\ndef get(url: str) -> _httpx.Response:\n    ...\n'


def test_the_real_kite_door_passes_only_because_of_the_outbound_allowance(monkeypatch) -> None:
    """The live file passes; with the allowance removed (mutation) its httpx.Response annotations are flagged, so the
    allowance is what lets them through and nothing else is."""
    source = KITE_HTTP.read_text(encoding="utf-8")
    assert structural(source, "kite_http.py") == []
    monkeypatch.setattr(sys.modules[__name__], "OUTBOUND_ANNOTATIONS", {})
    flagged = structural(source, "kite_http.py")
    assert flagged and all(row.endswith("uses Response") for row in flagged), flagged


def test_a_planted_starlette_response_in_the_kite_door_is_still_flagged() -> None:
    planted = KITE_HTTP.read_text(encoding="utf-8") + "\nfrom starlette.responses import Response\n"
    rows = structural(planted, "kite_http.py")
    assert any("imports starlette.responses" in r for r in rows) and any("imports Response" in r for r in rows), rows


OUTBOUND_STILL_REFUSED = {
    "construction": 'import httpx as _httpx\ndef f():\n    return _httpx.Response(200)\n',
    "value_not_annotation": 'import httpx as _httpx\nREPLY = _httpx.Response\n',
    "from_httpx_import": 'from httpx import Response\ndef get(url: str) -> Response:\n    ...\n',
    "alias_rebound": 'import httpx as _httpx\nimport starlette.responses as _httpx\ndef g() -> _httpx.Response:\n'
                     '    ...\n',
    "alias_assigned": 'import httpx as _httpx\n_httpx = fastapi.responses\ndef g() -> _httpx.Response:\n    ...\n',
    "other_module": 'import starlette.responses as _httpx\ndef g() -> _httpx.Response:\n    ...\n',
    "other_banned_attr": 'import httpx as _httpx\ndef g() -> _httpx.JSONResponse:\n    ...\n',
    "bare_name_annotation": 'def g() -> Response:\n    ...\n',
    # Tier A review (GC-2a): the module check (``a.name == module``) needs its own killing plant - fastapi's Response
    # IS starlette's, and no import rule names fastapi
    "fastapi_alias": 'import fastapi as _httpx\ndef g() -> _httpx.Response:\n    ...\n',
    "construct_in_return_annotation": 'import httpx as _httpx\ndef g() -> _httpx.Response(200):\n    ...\n',
    "construct_in_annassign": 'import httpx as _httpx\nx: _httpx.Response(200, text="e") = None\n',
    "walrus_in_annotation": 'import httpx as _httpx\ndef g() -> (R := _httpx.Response):\n    ...\n',
    "lambda_in_annotation": 'import httpx as _httpx\ndef g() -> (lambda: _httpx.Response)():\n    ...\n',
}


def test_the_outbound_allowance_is_narrow() -> None:
    assert structural(_ANNOTATED, "kite_http.py") == []
    assert structural(_ANNOTATED, "routes/sample.py"), "the allowance is for kite_http.py only"
    missed = [name for name, src in OUTBOUND_STILL_REFUSED.items() if not structural(src, "kite_http.py")]
    assert missed == []
