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

APP = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
DOOR = "errors.py"
BANNED_NAMES = frozenset({
    "Response", "JSONResponse", "ORJSONResponse", "UJSONResponse", "RedirectResponse", "StreamingResponse",
    "PlainTextResponse", "HTMLResponse", "FileResponse", "HTTPException", "StarletteHTTPException",
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


def structural(source: str, rel: str) -> list[str]:
    """Layer 1."""
    if rel == DOOR:
        return []
    found: list[str] = []
    tree = ast.parse(source)
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
        elif isinstance(node, (ast.Name, ast.Attribute)) and _name(node) in BANNED_NAMES:
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
