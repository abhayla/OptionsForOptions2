# ruff: noqa: E501, PLR2004, SIM102
"""REQ-167 AC-4 structural guard: every app-layer caller of a settings-taking calculation passes values that came from
the settings reader (the same class as the rate-context guard; a calculation must never run on a silent default).

Spec basis: REQ-167 AC-4 "Each wired calculation reads the value in force when it runs"; ADR-222 (1), (9).

Scans the source of ``backend/ofo_app`` (no import of the app; this tree never imports ofo_app). For every call of
``outcome_response``, ``build_outcome``, ``from_entries`` and ``place_quick_pick`` the settings argument must be a plain
name that is (a) a parameter whose annotation is ``Depends(get_calc_settings)``, (b) a local assigned from an
expression that calls ``get_settings_reader`` (the live push reads at its tick), or (c) the ``settings`` parameter of
``outcome_response`` itself. Any other shape (a literal, ``defaults()``, ``None``, an attribute, a missing argument)
fails the test: it fails closed on shapes it cannot resolve.

Forward quality (REQ-167 AC-5, the three forward settings): every call of ``parity_forward``, ``read_snapshot``,
``chain_model`` and ``chain_greeks`` must pass ``quality`` as ``<ctx>.forward_quality`` where ``<ctx>`` is a parameter of
the calling function (and, in a route handler, the parameter declared ``Depends(get_market_context)``, the per-request
dependency that applies ``with_rate_in_force``, which builds the value from the settings read), or, in the three leg
picker helpers that pass it through, their own ``quality`` parameter (checked at THEIR callers, the same way). A literal,
``defaults()``, ``None``, a missing argument or any other shape fails. Known limit: a non-route helper that receives a
context is not traced to its caller (the route-level check above covers every route).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

APP = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo_app"
SETTINGS_CALLS = {"outcome_response", "build_outcome", "from_entries"}
PASS_THROUGH = {"outcome_response"}  # its own ``settings`` parameter is checked at ITS callers


def _name(call: ast.Call) -> str | None:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _functions(tree: ast.AST):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _from_reader(fn: ast.AST, name: str) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            if "get_settings_reader" in ast.dump(n.value):
                return True
    return False


def _depends_param(fn: ast.AST, name: str) -> bool:
    a = fn.args
    for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
        if arg.arg == name and arg.annotation is not None and "get_calc_settings" in ast.dump(arg.annotation):
            return True
    return False


def _resolvable(fn: ast.AST, value: ast.AST) -> bool:
    if not isinstance(value, ast.Name):
        return False
    if fn.name in PASS_THROUGH and value.id == "settings":
        return True
    return _depends_param(fn, value.id) or _from_reader(fn, value.id)


QUALITY_CALLS = {"parity_forward": 5, "chain_model": 5, "chain_greeks": 5, "read_snapshot": None}
QUALITY_PASS_THROUGH = {"strikes_answer", "futures_answer", "_forward"}  # their own ``quality`` parameter
QUALITY_PASS_CALLS = {"strikes_answer", "futures_answer", "_forward"}  # callers must pass ``quality=`` resolvably


def _params(fn: ast.AST) -> dict[str, ast.arg]:
    a = fn.args
    return {x.arg: x for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]}


def _is_route(fn: ast.AST) -> bool:
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)
               and d.func.value.id == "router" for d in fn.decorator_list)


def _quality_ok(fn: ast.AST, value: ast.AST | None) -> bool:  # noqa: PLR0911
    if value is None:
        return False
    params = _params(fn)
    if isinstance(value, ast.IfExp):  # ``DEFAULT_QUALITY if ctx is None else ctx.forward_quality`` (a route, no context)
        return (_is_route(fn) and isinstance(value.body, ast.Name) and value.body.id == "DEFAULT_QUALITY"
                and _quality_ok(fn, value.orelse))
    if isinstance(value, ast.Name):
        return value.id == "quality" and "quality" in params and fn.name in QUALITY_PASS_THROUGH
    if isinstance(value, ast.Attribute) and value.attr == "forward_quality" and isinstance(value.value, ast.Name):
        arg = params.get(value.value.id)
        if arg is None:
            return False
        if _is_route(fn):
            return arg.annotation is not None and "get_market_context" in ast.dump(arg.annotation)
        return True
    return False


def known_feed_default_reads(text: str, where: str) -> list[str]:
    """Known gap, named (not silent): the paper monitor's ``provider_prices`` reads ``feed.ctx`` (built with the registry
    defaults) exactly as it reads the rate; both are wired to the settings in force in one later step (the sockets and
    the monitor have no request to read settings in). Exactly this one call is allowed, nothing else in the app."""
    if where != "paper_monitor.py":
        return []
    return [p for p in quality_violations(text, where) if p.startswith("paper_monitor.py:68 read_snapshot()")]


def quality_violations(source: str, where: str = "") -> list[str]:
    bad = []
    for fn in _functions(ast.parse(source)):
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            name = _name(call)
            if name not in QUALITY_CALLS and name not in QUALITY_PASS_CALLS:
                continue
            kw = {k.arg: k.value for k in call.keywords}
            index = QUALITY_CALLS.get(name)
            value = kw.get("quality") if index is None or "quality" in kw else (
                call.args[index] if len(call.args) > index else None)
            if not _quality_ok(fn, value):
                bad.append(f"{where}:{call.lineno} {name}() quality does not come from the settings reader")
    return bad


def violations(source: str, where: str = "") -> list[str]:
    tree = ast.parse(source)
    bad = []
    for fn in _functions(tree):
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            name = _name(call)
            if name in SETTINGS_CALLS:
                kw = {k.arg: k.value for k in call.keywords}
                if "settings" not in kw or not _resolvable(fn, kw["settings"]):
                    bad.append(f"{where}:{call.lineno} {name}() settings does not come from the reader")
            elif name == "place_quick_pick":
                arg = call.args[3] if len(call.args) > 3 else None
                ok = (isinstance(arg, ast.Call) and _name(arg) == "quick_pick_distances" and len(arg.args) == 1
                      and _resolvable(fn, arg.args[0]))
                if not ok:
                    bad.append(f"{where}:{call.lineno} place_quick_pick() distances do not come from the reader")
    return bad


def test_every_app_caller_passes_values_from_the_settings_reader():
    found = 0
    problems: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(f"{n}(" in text for n in (*SETTINGS_CALLS, "place_quick_pick")):
            found += 1
        problems += violations(text, path.name)
    assert found >= 4, "the scan found almost no callers: the guard is not looking at the app"
    assert not problems, problems


@pytest.mark.parametrize("body", [
    "async def f():\n    return outcome_response(req, ctx)\n",  # missing
    "async def f():\n    return outcome_response(req, ctx, settings=defaults())\n",  # a default, not the reader
    "async def f(s):\n    return outcome_response(req, ctx, settings=s)\n",  # an unannotated parameter
    "async def f():\n    return build_outcome(d, snap, settings=None)\n",
    "async def f(s: Annotated[dict, Depends(get_market_context)]):\n    return from_entries(d, None, st, v, settings=s)\n",
    "async def f(c):\n    return place_quick_pick(p, m, strikes, quick_pick_distances(c))\n",
])
def test_the_guard_refuses_shapes_that_do_not_come_from_the_reader(body):
    assert violations(body), body


@pytest.mark.parametrize("body", [
    "async def f(s: Annotated[dict, Depends(get_calc_settings)]):\n    return outcome_response(req, ctx, settings=s)\n",
    "async def f():\n    s = await get_settings_reader()()\n    return build_outcome(d, snap, settings=s)\n",
    "async def f(c: Annotated[dict, Depends(get_calc_settings)]):\n"
    "    return place_quick_pick(p, m, strikes, quick_pick_distances(c))\n",
])
def test_the_guard_accepts_the_reader_shapes(body):
    assert not violations(body), body


QUALITY_BAD = [
    "def f(ctx):\n    return read_snapshot(p, u, ids, v, r, quality=defaults())\n",  # a default
    "def f(ctx):\n    return read_snapshot(p, u, ids, v, r)\n",  # missing
    "def f(ctx):\n    return parity_forward(c, s, e, v, r)\n",  # missing
    "def f(ctx):\n    return parity_forward(c, s, e, v, r, None)\n",
    "def f(ctx):\n    return chain_model(c, s, e, v, r, forward_quality(defaults()))\n",
    "def f(ctx):\n    return chain_greeks(c, s, e, v, r, ForwardQuality(1, 2, 3))\n",
    "def f(quality):\n    return read_snapshot(p, u, ids, v, r, quality=quality)\n",  # not a pass-through helper
    "def f():\n    return read_snapshot(p, u, ids, v, r, quality=ctx.forward_quality)\n",  # ctx is no parameter
    "def f(ctx):\n    return read_snapshot(p, u, ids, v, r, quality=get().forward_quality)\n",
    "@router.get('/x')\nasync def f(ctx: Annotated[MarketContext, Depends(get_feed_ctx)]):\n"
    "    return read_snapshot(p, u, ids, v, r, quality=ctx.forward_quality)\n",  # a route's other dependency
    "def f(feed):\n    return strikes_answer(feed, u, e, w, c, n, quality=DEFAULT_QUALITY)\n",  # not a route
    "def f(feed):\n    return futures_answer(feed, u, c, n)\n",
]
QUALITY_GOOD = [
    "def f(ctx):\n    return read_snapshot(p, u, ids, v, ctx.rate, quality=ctx.forward_quality)\n",
    "def f(ctx):\n    return parity_forward(c, s, e, v, ctx.rate, ctx.forward_quality)\n",
    "def f(ctx):\n    return chain_model(c, s, e, v, r, ctx.forward_quality, market_closed=x)\n",
    "def strikes_answer(feed, quality):\n    return chain_greeks(c, s, e, v, r, quality)\n",
    "@router.get('/x')\nasync def f(ctx: Annotated[MarketContext | None, Depends(get_market_context)]):\n"
    "    return strikes_answer(feed, quality=DEFAULT_QUALITY if ctx is None else ctx.forward_quality)\n",
]


@pytest.mark.parametrize("body", QUALITY_BAD)
def test_the_quality_guard_refuses_shapes_that_do_not_come_from_the_reader(body):
    assert quality_violations(body), body


@pytest.mark.parametrize("body", QUALITY_GOOD)
def test_the_quality_guard_accepts_the_reader_shapes(body):
    assert not quality_violations(body), body


def test_every_app_caller_of_a_forward_calculation_passes_the_quality_in_force():
    found = 0
    problems: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        found += sum(f"{n}(" in text for n in QUALITY_CALLS)
        problems += [p for p in quality_violations(text, path.name) if p not in known_feed_default_reads(text, path.name)]
    assert found >= 6, "the scan found almost no forward callers: the guard is not looking at the app"
    assert not problems, problems
