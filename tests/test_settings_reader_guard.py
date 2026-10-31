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
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

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
