"""Lane R 27 Nov (finding pool-held-across-market-wait): a route that holds a request session (a ``db`` parameter) and
awaits a live-feed hold or a broker/REST read must give its pooled connection back first (``release_connection(db)``,
D-36 (c), D-38), or sit on the short reasoned allowlist below. Structural: the AST of every ``routes/*.py`` async
function, no running app. Detection limits: only a parameter named ``db`` is seen (a function that takes ``req`` with
``req.db`` is not), and only the awaited names in WAIT_NAMES; the runtime proof is
tests_app/test_pool_not_held_across_market_wait.py.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROUTES = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo_app" / "routes"
#: awaited calls that wait on the live feed or the broker
WAIT_NAMES = frozenset({
    "hold_and_read", "_hold_until_ready", "_snapshot", "market_snapshot", "exit_snapshot", "live_exit_prices",
    "_server_exit_prices", "owner_kite_reads", "index_spot", "market_reader", "rest_reader", "read_market",
    "to_thread", "wait_for", "read_rest_spot", "get_rest_spot_reader"})
#: (file, function) -> why the connection is held on purpose or is not this lane's to change
ALLOW = {
    ("adjustment_history.py", "adjustment_history"): "open item for Lane J (adjustment*.py is not this lane's): "
                                                    "holds the connection across paper.market_snapshot",
}
# Seen by hand, not by this scan (takes ``req``, not ``db``): execution_return._return keeps its connection on purpose,
# the strategy row lock (store.lock_strategy, held to commit) makes one return close a plan once.
#: guarded = functions that wait AND release first; pinned so a lost release or a new waiter shows
GUARDED_COUNT = 10


def _name(call: ast.expr) -> str | None:
    func = call.func if isinstance(call, ast.Call) else None
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _scan() -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    guarded, bad, allowed = [], [], []
    for path in sorted(ROUTES.glob("*.py")):
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            args = fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
            if "db" not in {a.arg for a in args}:
                continue
            awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)]
            waits = [n.lineno for n in awaits if _name(n.value) in WAIT_NAMES
                     or (isinstance(n.value.func, ast.Call) and _name(n.value.func) in WAIT_NAMES)]
            if not waits:
                continue
            released = [n.lineno for n in awaits if _name(n.value) == "release_connection"]
            key = (path.name, fn.name)
            if released and min(released) < min(waits):
                guarded.append(key)
            elif key in ALLOW:
                allowed.append(key)
            else:
                bad.append(key)
    return guarded, bad, allowed


def test_every_route_that_waits_on_the_market_releases_its_connection_first():
    guarded, bad, allowed = _scan()
    assert not bad, f"hold a pooled connection across a market or broker wait (release_connection(db) first): {bad}"
    assert len(guarded) == GUARDED_COUNT, guarded
    assert set(allowed) == set(ALLOW), "an allowlist entry no longer needed (or renamed): remove it"
