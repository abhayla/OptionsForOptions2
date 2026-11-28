"""REQ-049 AC-4, Lane Q1 phase 2: route latency budgets, as structure first and wall time second.

(a) a cold margin reads Zerodha's funds and basket together: one round trip, not two (BLOCKED, see the xfail);
(b) query ceilings per route (counted from cursor events: not flaky), set to today's counts (no request memo): a guard
    against an N+1 creeping in, not a target;
(c) wall-time budgets with instant prices and a warm margin: each route <= 300 ms alone; 10 concurrent plan-watch
    requests, one per strategy, all <= CONCURRENT_BUDGET_MS. The budget comes from the step-1 measurement (before any
    fix: median 555 ms, max 795 ms for 10; the requests serialise on the event loop, wall ~ N x single), set loosely
    (observed max 795 to 2994 ms on a shared 4-core box) so a loaded machine does not flake;
    it is a guard, and it passed before the fixes too.

Real PostgreSQL, the app's real routes, the scenario mode's instant quotes (the price reads are free here).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import db as app_db
from ofo_app import scenario_mode
from ofo_app.routes import outcome
from sqlalchemy import event
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401
from test_plan_watch import _arm

BROKER_ROUND_TRIP = 0.3  # seconds per Zerodha call (funds, basket), a stub
COLD_MARGIN_MAX_MS = 450.0  # one round trip plus slack; two serial calls are ~600
SINGLE_MAX_MS = 200.0  # Lane H: measured 60 to 100 ms warm on a 4-core box (was 300)
CONCURRENT_BUDGET_MS = 2500.0  # 10 concurrent plan-watch; Lane H: measured 600 to 840 ms (was 4000)
LINE = re.compile(r"request (\w+) (\S+) (\d+) ([\d.]+)ms(?: db=([\d.]+)ms/(\d+)q)?(?: price=([\d.]+)ms)?"
                  r"(?: margin=([\d.]+)ms)?")
# FD3 item 6: each of the three adjustment routes runs ONE statement more than when the ceilings were set (23 / 19 /
# 18): the position's expiry kind is read from the stored catalogue by the one rule
# (adjustment_readers._stored_kind_or_empty -> stored_kind -> load_catalogue; commit b00d304, Lane N items 1, 2, 4).
# MEASURED: with that read stubbed out the counts are exactly 23 / 19 / 18 again, so it is the only added statement. It
# is needed for correctness (ADR-330 (19)(b): the kind decides which stop rows apply; an unknown kind fails closed), so
# the ceilings rise by one, not the guard's meaning: a second added statement still fails.
# FD5 item 1: plan-watch runs ONE more (25): the armed lines read the position's kind (``strategy_store.kinds_of``,
# FD3 round 2 / R6, ADR-330 (64): a real or unreadable position has no paper stop). MEASURED: with
# ``_stored_kind_or_empty`` stubbed out the batch of one row counts 24 (was 23), so the kind read is the only
# statement added; it runs only when the strategy has armed rows. Needed for correctness, so the ceiling rises by one.
# FD5: every route that reads the expiry kind from the stored catalogue runs TWO more statements (22 / 21 / 27): the
# read runs in a SAVEPOINT (``stored_kind``: ``begin_nested`` = SAVEPOINT + RELEASE) so a failed catalogue read can no
# longer ``rollback()`` the caller's order-key claim and strategy lock (review F1 / N6). MEASURED: the paper book route
# (no kind read) stays at 11. A deliberate price of correctness, not a second read: one more statement still fails.
# Lane B3 (I-48): plan-watch 27 -> 26: the screen-isolation read ran twice per request (``watch_of`` and ``run_check``);
# it now runs once, in ``run_check``. The batch of NINE rows has its own ceiling in test_plan_watch_batch_b3_1128.py
# (219 -> 162 statements).
CEILINGS = {  # route -> most statements one request may run: today's counts, an N+1 regression guard
    "plan-watch": 26,
    "adjustment-check": 22,
    "adjustment-plan": 21,
    "paper/strategies/{id}": 11,
}


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


class _Rig:
    def __init__(self) -> None:
        self.ids: list[int] = []
        self.client: AsyncClient
        self.margin_source: object
        self.statements = 0
        self.broker_calls = 0
        self.handler = _Lines()

    def urls(self, sid: int) -> dict[str, str]:
        return {"plan-watch": f"/api/strategies/{sid}/plan-watch",
                "adjustment-check": f"/api/strategies/{sid}/adjustment-check",
                "adjustment-plan": f"/api/strategies/{sid}/adjustment-plan",
                "paper/strategies/{id}": f"/paper/strategies/{sid}"}

    async def get(self, url: str) -> tuple[float, float, int]:
        """(total ms, margin ms, statements) of one GET, from its own request log line."""
        self.handler.lines.clear()
        before = self.statements
        r = await self.client.get(url)
        assert r.status_code == 200, (url, r.status_code, r.text[:300])  # noqa: PLR2004
        m = LINE.match(self.handler.lines[-1])
        assert m, self.handler.lines
        return float(m.group(4)), float(m.group(8) or 0.0), self.statements - before


@pytest.fixture
async def rig(app_db_url, monkeypatch):  # noqa: F811
    r = _Rig()
    for _ in range(10):  # ten strategies of the ONE active scenario (another scenario's strategy is refused)
        r.ids.append(await _seeded(app_db_url, monkeypatch, "ADJ-01"))
    for sid in r.ids:
        await _arm(app_db_url, sid)
    real_transport = scenario_mode.Scenario.margin_transport

    def slow_transport(self, method, url, headers, body):
        r.broker_calls += 1
        time.sleep(BROKER_ROUND_TRIP)  # runs in a worker thread (asyncio.to_thread)
        return real_transport(self, method, url, headers, body)

    monkeypatch.setattr(scenario_mode.Scenario, "margin_transport", slow_transport)
    from ofo_app.main import create_app  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    r.margin_source = app.dependency_overrides[outcome.get_margin_source]()
    event.listen(app_db.get_engine().sync_engine, "before_cursor_execute",
                 lambda *_a: setattr(r, "statements", r.statements + 1))
    logging.getLogger("ofo_app.request").addHandler(r.handler)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r.client = ac
        yield r
    logging.getLogger("ofo_app.request").removeHandler(r.handler)
    await app_db.close_db()


async def _warm(rig: _Rig, sid: int) -> None:
    for url in rig.urls(sid).values():  # imports, the margin cache, the pool
        await rig.get(url)


@pytest.mark.xfail(strict=True, reason=(
    "BLOCKED, not built: reading funds and basket together changes answers pinned by test_outcome_margin.py (a funds "
    "failure makes NO basket call; D-36 round 2: funds 0.2 s + basket 0.2 s under one 0.3 s bound is 'could not be "
    "read'). Needs an owner decision; see the Q1 phase 2 report. Remove this mark if it is built."))
async def test_cold_margin_reads_funds_and_basket_together(rig: _Rig) -> None:
    sid = rig.ids[0]
    await _warm(rig, sid)
    rig.margin_source._cache.clear()
    rig.broker_calls = 0
    _total, margin_ms, _q = await rig.get(rig.urls(sid)["adjustment-check"])
    assert rig.broker_calls == 2, rig.broker_calls  # noqa: PLR2004 - funds and basket, each read once
    assert margin_ms <= COLD_MARGIN_MAX_MS, f"cold margin step {margin_ms:.0f} ms: funds, then basket"


@pytest.mark.parametrize("route", sorted(CEILINGS))
async def test_query_ceiling(rig: _Rig, route: str) -> None:
    sid = rig.ids[0]
    await _warm(rig, sid)
    _total, _margin, statements = await rig.get(rig.urls(sid)[route])
    assert statements <= CEILINGS[route], f"{route}: {statements} statements, ceiling {CEILINGS[route]}"


async def test_single_route_budget(rig: _Rig) -> None:
    sid = rig.ids[0]
    await _warm(rig, sid)
    for route, url in rig.urls(sid).items():
        total, _margin, _q = await rig.get(url)
        assert total <= SINGLE_MAX_MS, f"{route}: {total:.0f} ms alone, budget {SINGLE_MAX_MS:.0f}"


async def test_ten_concurrent_plan_watch_budget(rig: _Rig) -> None:
    for sid in rig.ids:
        await _warm(rig, sid)
    rig.handler.lines.clear()
    codes = await asyncio.gather(*[rig.client.get(rig.urls(sid)["plan-watch"]) for sid in rig.ids])
    assert {c.status_code for c in codes} == {200}
    times = [float(LINE.match(x).group(4)) for x in rig.handler.lines]
    assert len(times) == len(rig.ids)
    assert max(times) <= CONCURRENT_BUDGET_MS, f"10 concurrent plan-watch: max {max(times):.0f} ms"


async def test_batch_plan_watch_query_ceiling(rig: _Rig) -> None:
    """Lane H: a batch of one row costs what the single route costs (no extra statements per request)."""
    sid = rig.ids[0]
    await _warm(rig, sid)
    await rig.get(f"/api/plan-watch?strategy_ids={sid}")
    _total, _margin, statements = await rig.get(f"/api/plan-watch?strategy_ids={sid}")
    assert statements <= CEILINGS["plan-watch"], f"batch of one row: {statements} statements"
