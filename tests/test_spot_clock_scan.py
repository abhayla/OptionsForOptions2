"""GC-IC1 step 9 repo scan (finding freshness-judged-on-request-start-clock): the routes answer the spot ONLY through
``outcome.judge_spot`` (one instant read after the slow reads, the live feed re-stamped at it); no route file calls
``resolve_spot`` itself. The two files that do (``routes/outcome.py`` and ``adjustment_readers.py``) pass
``now=spot_judging_now(...)`` or a name assigned from it earlier in the SAME function. The ONE exception is a feed-only
call (second argument the literal ``None``) with no ``await`` before it in its function. Fails closed on shapes it
cannot read: ``*args`` / ``**kwargs``, a missing ``now``, an alias import of ``resolve_spot``."""
import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads backend source text

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
HELPER = "spot_judging_now"
REST_POSITION = 2  # resolve_spot(feed, rest, ...): the second positional is the REST reading
MAY_CALL = {"outcome.py", "adjustment_readers.py"}


def _files():
    return [*sorted((BACKEND / "routes").glob("*.py")), BACKEND / "adjustment_readers.py"]


def _name_of(fn: ast.expr) -> str | None:
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None


def _is_helper_call(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Call) and _name_of(node.func) == HELPER


def _assigned_from_helper_before(func: ast.AST | None, name: str, line: int) -> bool:
    if func is None:
        return False
    return any(isinstance(n, ast.Assign) and n.lineno < line and _is_helper_call(n.value)
               and any(isinstance(t, ast.Name) and t.id == name for t in n.targets) for n in ast.walk(func))


def _await_before(func: ast.AST | None, line: int) -> bool:
    if func is None:
        return True  # module level or unknown: cannot show there is no await, so fail closed
    return any(isinstance(n, ast.Await) and n.lineno < line for n in ast.walk(func))


def _call_problem(node: ast.Call, func: ast.AST | None, name: str) -> str | None:
    where = f"{name}:{node.lineno}"
    if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
        return f"{where} *args / **kwargs: cannot be read"
    rest = node.args[1] if len(node.args) >= REST_POSITION else None
    if isinstance(rest, ast.Constant) and rest.value is None:
        if _await_before(func, node.lineno):
            return f"{where} feed-only resolve_spot after an awaited read (or outside a function)"
        return None
    now = next((k.value for k in node.keywords if k.arg == "now"), None)
    ok = _is_helper_call(now) or (isinstance(now, ast.Name)
                                  and _assigned_from_helper_before(func, now.id, node.lineno))
    return None if ok else f"{where} now= is not {HELPER}(...) (or a name assigned from it in the same function)"


def problems(source: str, name: str = "<src>") -> list[str]:
    out: list[str] = []
    tree = ast.parse(source)
    owner: dict[int, ast.AST] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                owner[id(n)] = fn  # innermost function wins (walk order is outer first, inner overwrites)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out += [f"{name}:{node.lineno} resolve_spot imported under another name" for a in node.names
                    if a.name == "resolve_spot" and a.asname not in (None, "resolve_spot")]
        if isinstance(node, ast.Call) and _name_of(node.func) == "resolve_spot":
            found = _call_problem(node, owner.get(id(node)), name)
            out += [found] if found else []
    return out


def test_every_resolve_spot_call_uses_the_judging_clock_helper():
    found = {p.name: problems(p.read_text(encoding="utf-8"), p.name) for p in _files()}
    assert [x for v in found.values() for x in v] == []


def test_only_the_judge_and_the_window_reader_call_resolve_spot():
    callers = {p.name for p in _files() if "resolve_spot(" in p.read_text(encoding="utf-8")}
    assert callers == MAY_CALL


def test_the_routes_answer_the_spot_through_judge_spot():
    for name in ("adjustment.py", "adjustment_check.py", "adjustment_plan.py", "playbooks.py"):
        assert "judge_spot(" in (BACKEND / "routes" / name).read_text(encoding="utf-8"), name


@pytest.mark.parametrize("src", [
    "def f():\n    resolve_spot(f, r, c, now=market.now, windows=w)",
    "def f():\n    resolve_spot(f, r, c, windows=w)",
    "def f():\n    resolve_spot(f, r, c, now=now, windows=w)",
    "def f():\n    resolve_spot(\n f, r, c,\n now=market.now,\n windows=w)",
    "def f():\n    resolve_spot(*a)",
    "def f():\n    resolve_spot(f, r, c, **kw)",
    "from x import resolve_spot as rs",
    "def f():\n    m.resolve_spot(f, r, c, now=when, windows=w)",
    "async def f():\n    x = await g()\n    resolve_spot(f, None, None, now=now, windows=w)",
    "def f():\n    judged = spot_judging_now(c)\n    resolve_spot(f, r, c, now=other, windows=w)",
    "def f():\n    resolve_spot(f, r, c, now=judged, windows=w)\n    judged = spot_judging_now(c)",
    "resolve_spot(f, None, None, now=now, windows=w)",
])
def test_the_detector_flags_each_bad_shape(src):
    assert problems(src)


@pytest.mark.parametrize("src", [
    "def f():\n    resolve_spot(f, r, c, now=spot_judging_now(ctx), windows=w)",
    "def f():\n    resolve_spot(\n f, r, c,\n now=outcome.spot_judging_now(ctx),\n windows=w)",
    "async def f():\n    resolve_spot(f, None, None, now=now, windows=w)\n    x = await g()",
    "async def f():\n    x = await g()\n    judged = spot_judging_now(c)\n"
    "    resolve_spot(f, r, c, now=judged, windows=w)",
])
def test_the_detector_passes_the_good_shapes(src):
    assert problems(src) == []
