"""Lane R 27 Nov (finding pool-held-across-market-wait): a route that holds a request session (a ``db`` parameter) and
awaits a live-feed hold or a broker/REST read must give its pooled connection back first (``release_connection(db)``,
D-36 (c), D-38), or sit on the short reasoned allowlist below. Structural: the AST of every ``routes/*.py`` async
function (route or helper), no running app. FD3 item 5 (FD review F3): EVERY wait is checked, not only the first
release: walking back from a wait (round a loop's tail for a wait in a loop), the nearest earlier event must be a
``release_connection`` (a call that takes ``db`` counts as a use of the connection); no event at all is fine. Detection
limits: only a parameter named ``db`` is seen (a function that takes ``req`` with ``req.db`` is not), only the awaited
names in WAIT_NAMES, and a use of the connection that never names ``db`` is not seen; the runtime proof is
tests_app/test_pool_not_held_across_market_wait.py.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROUTES = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo_app" / "routes"
#: awaited calls that wait on the live feed, the market or the broker
WAIT_NAMES = frozenset({
    "hold_and_read", "_hold_until_ready", "_snapshot", "market_snapshot", "exit_snapshot", "live_exit_prices",
    "_server_exit_prices", "owner_kite_reads", "index_spot", "market_reader", "rest_reader", "read_market",
    "to_thread", "wait_for", "read_rest_spot", "get_rest_spot_reader",
    "entry_facts", "entry_facts_now", "index_spot_of", "read_quotes", "hold_until_priced",
    "_hold_and_read", "atm_iv_now", "record_basket_facts", "refuse_take_profit_at_loss", "_refuse_take_profit_at_loss"})
#: (file, function, awaited name) -> why the connection is held on purpose: NAME THE LOCK AND ITS PROOF
ALLOW: dict[tuple[str, str, str], str] = {
    ('paper.py', '_place_orders', 'record_basket_facts'):
        'FD3 item 4, left on purpose: ADR-283 (1) stores the basket facts IN THE FILL\'s transaction, under the strategy '
        'row lock (paper_store.place -> store.lock_strategy, held to the commit; proof: '
        'tests_app/test_paper_routes.py basket-facts cases). The market read sits inside adjustment_readers.'
        'record_basket_facts (Lane FR\'s file); it must be split into a read before the lock and a store under it '
        '(listed under "For the owner lane" in RESULTS-lane-fd3.md). Bounded: one feed hold, about 3 s'}
#: guarded = functions that wait AND release before every wait; pinned so a lost release or a new waiter shows
GUARDED_COUNT = 13  # FD3 item 5: counted with every wait checked (was 11, first release only)


def _name(call: ast.expr) -> str | None:
    func = call.func if isinstance(call, ast.Call) else None
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _uses_db(call: ast.Call) -> bool:
    """The call hands ``db`` on, or is a method of it (``db.execute``)."""
    def is_db(node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id == "db"
    func = call.func
    if isinstance(func, ast.Attribute) and is_db(func.value):
        return True
    return any(is_db(a) for a in call.args) or any(is_db(k.value) for k in call.keywords)


def _loops_of(fn: ast.AST) -> list[tuple[int, int]]:
    return [(n.lineno, n.end_lineno or n.lineno) for n in ast.walk(fn) if isinstance(n, ast.For | ast.AsyncFor | ast.While)]


def _held_at(wait: ast.Await, events: list[tuple[int, str]], loops: list[tuple[int, int]]) -> bool:
    """True when the connection may still be checked out at ``wait``: the nearest earlier event is a use of it. A wait
    in a loop also sees the loop's own tail (the previous round) before the loop's head."""
    line = wait.lineno
    before = [e for e in events if e[0] < line]
    inside = [(a, b) for a, b in loops if a <= line <= b]
    if inside:
        a, b = min(inside, key=lambda lb: lb[1] - lb[0])
        tail = [e for e in events if line < e[0] <= b]
        order = sorted((e for e in before if e[0] >= a), reverse=True) + sorted(tail, reverse=True)
        order += sorted((e for e in before if e[0] < a), reverse=True)
    else:
        order = sorted(before, reverse=True)
    return bool(order) and order[0][1] == "use"


def _scan() -> tuple[list[tuple[str, str]], list[tuple[str, str, str, int]], set[tuple[str, str, str]]]:
    guarded, bad, allowed = [], [], set()
    for path in sorted(ROUTES.glob("*.py")):
        for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            args = fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
            if "db" not in {a.arg for a in args}:
                continue
            awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)]
            waits = [n for n in awaits if _name(n.value) in WAIT_NAMES
                     or (isinstance(n.value.func, ast.Call) and _name(n.value.func) in WAIT_NAMES)]
            if not waits:
                continue
            events = [(n.lineno, "release" if _name(n.value) == "release_connection" else "use")
                      for n in awaits if _name(n.value) == "release_connection" or _uses_db(n.value)]
            loops = _loops_of(fn)
            clean = True
            for w in waits:
                if not _held_at(w, [e for e in events if e[0] != w.lineno or e[1] == "release"], loops):
                    continue
                name = _name(w.value) or ""
                if (path.name, fn.name, name) in ALLOW:
                    allowed.add((path.name, fn.name, name))
                    continue
                clean = False
                bad.append((path.name, fn.name, name, w.lineno))
            if clean:
                guarded.append((path.name, fn.name))
    return guarded, bad, allowed


def test_every_route_that_waits_on_the_market_releases_its_connection_first():
    guarded, bad, allowed = _scan()
    assert not bad, f"hold a pooled connection across a market or broker wait (release_connection(db) first): {bad}"
    assert len(guarded) == GUARDED_COUNT, guarded
    assert allowed == set(ALLOW), "an allowlist entry no longer needed (or renamed): remove it"
