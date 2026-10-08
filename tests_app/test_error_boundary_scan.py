"""W-024 round 9 part 6: in backend/ofo_app, response bodies come only from the boundary handler (ofo_app/errors.py)
or the catalogue (REQ-065 AC-2, ADR-003 Q226).

The scan covers every file in backend/ofo_app except errors.py itself. It flags:
- a response constructor (`JSONResponse`, `Response`, `PlainTextResponse`, `HTMLResponse`, `StreamingResponse`,
  `HTTPException`) or a route's `return` value holding an f-string, a `str()`/`repr()`/`format()` call, `%` formatting,
  an `except ... as e` name, or a sentence (two or more words);
- an exception handler registered anywhere but errors.py (`add_exception_handler`, `@app.exception_handler`), so the
  one handler stays the only one.
A status token such as {"status": "unhealthy"} is a single word, not a sentence, and passes.
"""

from __future__ import annotations

import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
DOOR = "errors.py"
RESPONSES = frozenset({"JSONResponse", "Response", "PlainTextResponse", "HTMLResponse", "StreamingResponse",
                       "HTTPException"})
TEXT_CALLS = frozenset({"str", "repr", "format"})
ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"})
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
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mod) and isinstance(sub.left, ast.Constant):
            bad.append("% formatting")
        elif isinstance(sub, ast.Name) and sub.id in bound:
            bad.append(f"exception name {sub.id!r}")
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _sentence(sub.value):
            bad.append(f"sentence {sub.value[:40]!r}")
    return bad


def _is_route(fn: ast.AST) -> bool:
    return isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        isinstance(d, ast.Call) and _name(d.func) in ROUTE_METHODS for d in fn.decorator_list)


def scan(source: str, rel: str) -> list[str]:
    if rel == DOOR:
        return []
    found: list[str] = []

    def walk(node: ast.AST, bound: frozenset[str], route: bool) -> None:
        for child in ast.iter_child_nodes(node):
            names = bound | {child.name} if isinstance(child, ast.ExceptHandler) and child.name else bound
            in_route = route or _is_route(child)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_route(child):
                in_route = False
            if isinstance(child, ast.Call):
                callee = _name(child.func)
                if callee in RESPONSES:
                    for arg in [*child.args, *(k.value for k in child.keywords)]:
                        found.extend(f"{rel}:{child.lineno} {callee}: {b}" for b in _bad_parts(arg, names))
                if callee in {"add_exception_handler", "exception_handler"}:
                    found.append(f"{rel}:{child.lineno} exception handler registered outside {DOOR}")
            if isinstance(child, ast.Return) and route and child.value is not None:
                found.extend(f"{rel}:{child.lineno} route return: {b}" for b in _bad_parts(child.value, names))
            walk(child, names, in_route)

    walk(ast.parse(source), frozenset(), False)
    return found


def test_ofo_app_builds_no_error_body_outside_the_boundary() -> None:
    rows = []
    for path in sorted(APP.rglob("*.py")):
        rows.extend(scan(path.read_text(encoding="utf-8"), path.relative_to(APP).as_posix()))
    assert not rows, "error text built outside ofo_app/errors.py:\n" + "\n".join(rows)


def test_scan_covers_the_routes_package() -> None:
    assert (APP / "routes" / "health.py").is_file()
    assert any(p.name == "health.py" for p in APP.rglob("*.py"))


# --- mutation samples: each must be flagged ---------------------------------------------------------------------

SAMPLES = (
    'from fastapi.responses import JSONResponse\n'
    'def f():\n    try:\n        pass\n    except ValueError as exc:\n'
    '        return JSONResponse(status_code=500, content={"error": str(exc)})\n',
    'def f(e):\n    return JSONResponse(content={"error": f"failed: {e}"})\n',
    'def f():\n    try:\n        pass\n    except ValueError as exc:\n        raise HTTPException(400, detail=exc.args)\n',
    'def f():\n    raise HTTPException(status_code=404, detail="Leg expired before execution")\n',
    '@router.get("/x")\nasync def x():\n    try:\n        pass\n    except ValueError as exc:\n'
    '        return {"error": "%s" % exc}\n',
    '@router.get("/x")\nasync def x():\n    return {"error": "leg expired before execution"}\n',
    'def make(app):\n    app.add_exception_handler(ValueError, handler)\n',
)


def test_scan_kills_every_sample() -> None:
    for src in SAMPLES:
        assert scan(src, "routes/sample.py"), src


def test_scan_passes_status_tokens_and_the_door_itself() -> None:
    ok = 'def f():\n    return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "down"})\n'
    assert scan(ok, "routes/sample.py") == []
    assert scan(SAMPLES[0], DOOR) == []


def test_mutant_without_the_except_name_rule_misses_exc_args() -> None:
    """Mutation: forget except-bound names -> `detail=exc.args` escapes (so the rule above is load-bearing)."""
    src = SAMPLES[2]
    tree = ast.parse(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and _name(n.func) == "HTTPException")
    assert _bad_parts(call.keywords[0].value, frozenset()) == []
    assert _bad_parts(call.keywords[0].value, frozenset({"exc"})) == ["exception name 'exc'"]
