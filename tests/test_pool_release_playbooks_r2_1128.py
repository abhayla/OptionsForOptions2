"""I-105 (test plan 28 Nov 2026): the playbooks route (POST /api/playbooks/test) must not hold a database connection
while its strategies' market reads wait on the broker. ``test_pool_release_before_market_wait.py`` sees only a function
that awaits a WAIT name itself; ``playbooks._tested`` reaches the waits through helpers (``_read_bounded`` ->
``_read_one`` -> ``market_reader`` / ``index_spot_of``), so the old scan never looked at it. Here the reach is
TRANSITIVE inside a module: a function with a ``db`` parameter that calls (or hands to ``gather``) a helper that waits
is "waiting" at that call, and ``release_connection(db)`` must come first (source order, same function). Structural,
no running app; the runtime proof is ``tests_app/test_playbook_test_pool.py``.
Spec basis: D-36 (c), D-38 (release the pooled connection before a broker or feed wait); Lane R finding
pool-held-across-market-wait.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from test_pool_release_before_market_wait import ROUTES, WAIT_NAMES

pytestmark = pytest.mark.repo_scan


def _called(node: ast.AST) -> set[str]:
    names = set()
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            func = call.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _functions(path: pathlib.Path) -> dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    return {f.name: f for f in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(f, (ast.AsyncFunctionDef, ast.FunctionDef))}


def _waiting(funcs: dict) -> set[str]:
    """Names of the module's functions that reach a WAIT name, directly or through another function of the module."""
    waiting: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name not in waiting and _called(fn) & (WAIT_NAMES | waiting):
                waiting.add(name)
                changed = True
    return waiting


def _first_line(fn: ast.AST, names: set[str]) -> int | None:
    lines = [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
             and (getattr(c.func, "id", None) in names or getattr(c.func, "attr", None) in names)]
    return min(lines, default=None)


def _scan(path: pathlib.Path) -> list[tuple[str, str, int | None, int | None]]:
    """(file, function, first wait-reaching call line, release line) for each function with a ``db`` parameter that
    reaches a wait."""
    funcs = _functions(path)
    waiting = _waiting(funcs)
    out = []
    for name, fn in funcs.items():
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        args = fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
        if "db" not in {a.arg for a in args}:
            continue
        wait_at = _first_line(fn, (WAIT_NAMES | waiting) - {name})
        if wait_at is None:
            continue
        out.append((path.name, name, wait_at, _first_line(fn, {"release_connection"})))
    return out


def test_the_playbooks_route_releases_its_connection_before_any_market_reach():
    found = {(f, fn): (w, r) for f, fn, w, r in _scan(ROUTES / "playbooks.py")}
    assert ("playbooks.py", "_tested") in found, "the scan no longer sees the function that reads the market"
    wait_at, released_at = found[("playbooks.py", "_tested")]
    assert released_at is not None and released_at < wait_at, found
    bad = {k: v for k, v in found.items() if v[1] is None or v[1] > v[0]}
    # test_playbook only hands the database to _tested (which releases); nothing else here may wait first
    assert set(bad) <= {("playbooks.py", "test_playbook")}, bad


def test_the_scan_catches_a_playbooks_route_that_lost_its_release(tmp_path):
    """Mutation: the real source with the one ``release_connection(db)`` call of ``_tested`` removed is flagged."""
    source = (ROUTES / "playbooks.py").read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    line = next(x for x in lines if x.strip().startswith("await release_connection(db)  # D-36"))
    assert line in source, "the release line moved: update this mutation"
    mutant = tmp_path / "playbooks.py"
    mutant.write_text(source.replace(line, "", 1), encoding="utf-8")
    found = {(f, fn): (w, r) for f, fn, w, r in _scan(mutant)}
    wait_at, released_at = found[("playbooks.py", "_tested")]
    assert released_at is None or released_at > wait_at, "the scan did not see the missing release"
