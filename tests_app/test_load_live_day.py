"""Gap 1 of the 27 Nov live test day (Lane Q2): the pages poll, the routes must keep up, and nothing says "not live".

Load harness (a small one, kept in the repo so every release can run it): the real ``create_app`` on the PC's pool
(DB_POOL_SIZE 4, no overflow), scenario ADJ-01 seeded as 10 RUNNING paper strategies, and 2 simulated browsers (two
async clients: v1 has one owner reference, so "two users" are two sessions of it) each polling, for ROUNDS rounds,
the pages' routes for every strategy at once: plan-watch, adjustment-check, the paper book of the strategy and the
positions list. A stubbed REST quote ticks (its value moves every call), the scenario feed is the live one.

The budget is stated, and COUNTED, never timed (tests/test_no_wall_clock_asserts.py):
 - every request answers inside ROUTE_BOUND_S (a request not answered by then is a failed request, the bound raises);
 - the answers that say "not live" (a paused plan-watch line or a paused adjustment check) are NOT_LIVE_BUDGET = 0;
 - no request answers 5xx; the pool never has more than its size checked out.
Printed (not asserted): requests, answers by route, the slowest wait counted in loop turns is not used.
Spec basis: REQ-049 AC-4, ADR-212, REQ-170 AC-5 (a risk exit is not delayed by a busy page), REQ-165.
"""
from __future__ import annotations

import asyncio
import itertools
from decimal import Decimal

import pytest
from _scenario_catalogue import load_library
from httpx import ASGITransport, AsyncClient
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import db as app_db
from ofo_app import playbook_store
from ofo_app.routes.adjustment import get_rest_spot_reader
from test_adjustment_check import (
    _reset_engine,
    app_db_url,  # noqa: F401 - the fixture of the check tests
    seed_mod,
)

STRATEGIES = 10
BROWSERS = 2
ROUNDS = 3
POOL = 4
STALL_S = 8
STALLED_BOUND_S = 6  # above the 4 s price budget of plan-watch, below the stall
ROUTE_BOUND_S = 25  # per request; the pool timeout is 30 s, so a starved request raises TimeoutError here first
NOT_LIVE_BUDGET = 0
OK = 200
ALL_ROUTES = frozenset({"positions", "plan-watch", "adjustment-check", "paper-book"})
_RUN = itertools.count(1)


async def _seed_running(app_engine, monkeypatch) -> list[int]:
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-01")
    await load_library(app_engine)
    run = next(_RUN)
    ids = []
    for n in range(STRATEGIES):
        monkeypatch.setattr(seed_mod, "strategy_name", lambda _id, n=n: f"L{run}-{n}")  # 1..20 characters
        sid = await seed_mod.seed("ADJ-01")
        async with app_engine.begin() as conn:  # ADR-330 (11): only a strategy's own plan is watched
            system = await playbook_store.active_for(conn, "owner", "ic")
            await playbook_store.accept_plan(conn, "owner", sid, system.id)
        ids.append(sid)
    return ids


def _ticking_quote():
    """A REST quote that ticks: each call answers a new value (a stub of the vendor)."""
    counter = itertools.count()

    async def quote(_underlying: str) -> SourceReading:
        return SourceReading(SourceState.STATED, Decimal("23050") + Decimal(next(counter) % 7))
    return quote


def _not_live(route: str, body: dict) -> bool:
    if route == "plan-watch":
        return bool(body.get("paused")) or any(x["state"] == "paused" for x in body["lines"])
    if route == "adjustment-check":
        return bool(body.get("paused"))
    return False


def _sometimes_stalled(every: int, seconds: float):
    """The vendor's slow answer: every ``every``-th REST quote waits ``seconds`` before it answers (then ticks)."""
    counter, ticking = itertools.count(1), _ticking_quote()

    async def quote(underlying: str) -> SourceReading:
        if next(counter) % every == 0:
            await asyncio.sleep(seconds)
        return await ticking(underlying)
    return quote


async def test_ten_running_trades_two_browsers_polling_stay_inside_the_budget(app_db_url, monkeypatch):  # noqa: F811
    await _load(app_db_url, monkeypatch, _ticking_quote(), ROUTE_BOUND_S)


@pytest.mark.xfail(strict=True, reason="plan-watch waits out a stalled quote: with every 3rd quote stalled 8 s the "
                                       "pages (plan-watch, book, positions) miss the bound; fixed by "
                                       "origin/hotfix/plan-watch-load-1127 (the 4 s price budget)")
async def test_the_same_load_with_every_third_quote_stalled_8_seconds_still_answers_inside_6_seconds(
        app_db_url, monkeypatch):  # noqa: F811
    await _load(app_db_url, monkeypatch, _sometimes_stalled(3, STALL_S), STALLED_BOUND_S,
                ALL_ROUTES - {"adjustment-check"})


async def test_the_adjustment_check_under_the_same_stalled_quote_answers_inside_6_seconds(
        app_db_url, monkeypatch):  # noqa: F811
    await _load(app_db_url, monkeypatch, _sometimes_stalled(3, STALL_S), STALLED_BOUND_S,
                frozenset({"adjustment-check"}))


async def _load(app_engine, monkeypatch, quote, bound, routes=ALL_ROUTES) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", str(POOL))
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    _reset_engine()
    ids = await _seed_running(app_engine, monkeypatch)
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    app = create_app()
    app.dependency_overrides[get_rest_spot_reader] = lambda: quote
    seen: list[tuple[str, int, dict | None]] = []
    peak = [0]

    async def poll(ac: AsyncClient, route: str, path: str) -> None:
        r = await asyncio.wait_for(ac.get(path), bound)  # a starved request raises here
        peak[0] = max(peak[0], app_db.get_engine().pool.checkedout())
        seen.append((route, r.status_code, r.json() if r.status_code == OK else None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as a, \
            AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as b:
        for _ in range(ROUNDS):
            jobs = []
            for ac in (a, b):
                pages = [("positions", "/paper/strategies")] + [
                    (route, path.format(sid=sid)) for sid in ids for route, path in (
                        ("plan-watch", "/api/strategies/{sid}/plan-watch"),
                        ("adjustment-check", "/api/strategies/{sid}/adjustment-check"),
                        ("paper-book", "/paper/strategies/{sid}"))]
                jobs += [poll(ac, route, path) for route, path in pages if route in routes]
            await asyncio.gather(*jobs)
    await app_db.close_db()
    by_route: dict[str, list[int]] = {}
    for route, status, _body in seen:
        by_route.setdefault(route, []).append(status)
    print("LOADMEASURE requests=", len(seen), {k: sorted(set(v)) for k, v in by_route.items()}, "pool peak", peak[0])
    per_browser = ('positions' in routes) + (len(routes) - ('positions' in routes)) * STRATEGIES
    assert len(seen) == ROUNDS * BROWSERS * per_browser
    assert all(status == OK for _r, status, _b in seen), {k: sorted(set(v)) for k, v in by_route.items()}
    not_live = [r for r, _s, body in seen if body is not None and _not_live(r, body)]
    assert len(not_live) <= NOT_LIVE_BUDGET, (len(not_live), sorted(set(not_live)))
    assert peak[0] <= POOL
