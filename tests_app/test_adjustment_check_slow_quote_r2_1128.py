"""I-107 (test plan 28 Nov 2026): the adjustment check awaited its Zerodha index quote with NO time limit (Lane Q2 real
case 27 Nov: one stalled quote held the page as long as Zerodha took). The route answers within the price budget with a
VISIBLE state: the quote cut (cancelled, FAILED, never a guessed figure), the reply still 200 with the check's own
shape, every rule judged on what is known and none on an invented spot. A quote that answers inside the budget is read
as before. Beside ``test_adjustment_check.py``; the plan-watch twin is in ``test_plan_watch.py``.
Slow fake quote: sleeps far past the budget (``price_budget.PRICE_BUDGET_S`` set to 0.05 s); a missing budget makes
``asyncio.wait_for(..., 5)`` raise instead of hanging the run.
Spec basis: REQ-119 AC-4, ADR-016 to ADR-019 (stale or missing is never live), ADR-330 (39).
"""
from __future__ import annotations

import asyncio
import dataclasses

from httpx import ASGITransport, AsyncClient
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import db as app_db
from ofo_app import price_budget
from ofo_app.adjustment_readers import read_market
from ofo_app.routes.adjustment import get_market_reader, get_rest_spot_reader
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401 - the fixture is used by name

OK = 200
HANG_CAP_S = 5
BUDGET_S = 0.05


async def _no_tick(tracked, ctx):
    """The real read with the feed's index tick taken away: the quote is then asked (ADR-330 (39))."""
    market = await read_market(tracked, ctx)
    return dataclasses.replace(market, feed=SourceReading(SourceState.ABSENT), feed_quote=None)


async def _check_with(sid: int, quote) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    _reset_engine()
    app = create_app()
    app.dependency_overrides[get_market_reader] = lambda: _no_tick
    app.dependency_overrides[get_rest_spot_reader] = lambda: quote
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await asyncio.wait_for(ac.get(f"/api/strategies/{sid}/adjustment-check"), HANG_CAP_S)
    await app_db.close_db()
    return r.status_code, r.json()


async def test_a_quote_that_never_answers_is_cut_cancelled_and_the_check_answers(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    monkeypatch.setattr(price_budget, "PRICE_BUDGET_S", BUDGET_S)
    seen = {"asked": 0, "cancelled": False, "held": None}

    async def hangs(_underlying):
        seen["asked"] += 1
        seen["held"] = app_db.get_engine().pool.checkedout()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            seen["cancelled"] = True
            raise
    status, out = await _check_with(sid, hangs)
    assert status == OK, out
    assert seen["asked"] == 1 and seen["cancelled"] is True, seen  # asked once, cancelled, not left running
    assert seen["held"] == 0, seen  # the stalled wait held no pooled connection
    assert out["strategy_type"] == "ic" and "results" in out  # the check's own shape, not a refusal
    # the visible state: the check says no rule was checked and why, never a guessed spot
    assert out["withheld"]["what_happened"] == "No adjustment opportunity checked: spot not available.", out["withheld"]
    assert out["withheld"]["next_action"] == "Wait for the spot price to come back."
    assert out["withheld"]["what_is_blocked"] == "Every rule of this playbook."
    assert [x for x in out["results"] if x["kind"] == "flag"] == []  # nothing is flagged on an invented spot


async def test_a_quote_inside_the_budget_is_read_as_before(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    monkeypatch.setattr(price_budget, "PRICE_BUDGET_S", HANG_CAP_S - 1)
    asked: list[str] = []

    async def prompt(underlying):
        asked.append(underlying)
        return SourceReading(SourceState.FAILED)  # an answer, not a hang: the budget has nothing to cut
    status, out = await _check_with(sid, prompt)
    assert status == OK, out
    assert asked == ["NIFTY"], asked
