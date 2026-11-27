"""Lane J2 item 5 (Lane Q2 leftover 1): the adjustment check waited for its Zerodha quote with no limit; one stalled
quote held the page (and a database connection's worth of work) for as long as Zerodha took. Now both price reads share
ONE budget, and a read that has not answered by then is cut and answered as NOT LIVE (the market as when not connected,
the REST quote as FAILED), never as a guessed price.
Spec basis: REQ-119 AC-4 (a stalled price source never holds a screen: the answer says prices are not live); ADR-016 to
ADR-019 (fail closed with a reason). No database, no Kite: injected readers and a short budget.
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import price_budget

BUDGET = 0.2
STALL = 5.0
UP_TO = 1.0  # a guard, not an assert on time: a read cut at the budget returns long before the stall would


class _Reader:
    def __init__(self, seconds: float, value):
        self.seconds, self.value, self.calls = seconds, value, 0

    async def __call__(self, *_args):
        self.calls += 1
        await asyncio.sleep(self.seconds)
        return self.value


def _not_live_market():
    async def not_live(tracked, ctx):
        assert ctx is None  # the not-connected read: no chain, no feed spot
        return "NOT_LIVE_MARKET"
    return not_live


async def _budgeted(market, rest):
    return price_budget.budgeted(market, rest, budget_s=BUDGET, not_live_market=_not_live_market())


async def test_fast_readers_are_untouched():
    market, rest = _Reader(0.0, "MARKET"), _Reader(0.0, SourceReading(SourceState.STATED, Decimal("23400"), None))
    m, r = await _budgeted(market, rest)
    assert await m("tracked", "ctx") == "MARKET"
    assert (await r("NIFTY")).state is SourceState.STATED


async def test_a_stalled_market_read_is_cut_at_the_budget_and_answered_as_not_live(caplog):
    market, rest = _Reader(STALL, "MARKET"), _Reader(0.0, SourceReading(SourceState.STATED, Decimal("23400"), None))
    m, r = await _budgeted(market, rest)
    with caplog.at_level(logging.WARNING, logger="ofo_app.price_budget"):
        async with asyncio.timeout(UP_TO):
            assert await m("tracked", "ctx") == "NOT_LIVE_MARKET"
    assert (await r("NIFTY")).state is SourceState.FAILED  # a STATED spot beside a not-live market is never offered
    assert rest.calls == 0
    assert any("market read over" in x.getMessage() for x in caplog.records)


async def test_a_stalled_quote_is_cut_at_the_budget_and_answered_as_failed(caplog):
    market, rest = _Reader(0.0, "MARKET"), _Reader(STALL, SourceReading(SourceState.STATED, Decimal("23400"), None))
    m, r = await _budgeted(market, rest)
    assert await m("tracked", "ctx") == "MARKET"
    with caplog.at_level(logging.WARNING, logger="ofo_app.price_budget"):
        async with asyncio.timeout(UP_TO):
            assert (await r("NIFTY")).state is SourceState.FAILED
    assert any("index quote over the budget" in x.getMessage() for x in caplog.records)


async def test_the_two_reads_share_one_budget_not_one_each():
    stated = SourceReading(SourceState.STATED, Decimal("1"), None)
    market, rest = _Reader(BUDGET * 0.6, "MARKET"), _Reader(BUDGET * 0.6, stated)
    m, r = await _budgeted(market, rest)
    async with asyncio.timeout(UP_TO):
        assert await m("tracked", "ctx") == "MARKET"
        assert (await r("NIFTY")).state is SourceState.FAILED  # 0.12 s used by the market, 0.12 s needed: over 0.2


async def test_no_budget_left_means_the_quote_is_not_asked_at_all():
    market, rest = _Reader(0.0, "MARKET"), _Reader(0.0, SourceReading(SourceState.STATED, Decimal("1"), None))
    m, r = await _budgeted(market, rest)
    await m("tracked", "ctx")
    await asyncio.sleep(BUDGET + 0.05)
    assert (await r("NIFTY")).state is SourceState.FAILED and rest.calls == 0


async def test_the_adjustment_check_route_hands_run_check_readers_that_are_cut_at_the_budget(monkeypatch):
    """The wiring (the load harness of tests_app/test_load_live_day.py does not reach the REST quote while the scenario
    feed holds a spot, so it cannot prove this): whatever readers the route gets, ``run_check`` gets budgeted ones."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.routes import adjustment_check as route  # noqa: PLC0415
    seen: dict = {}

    async def fake_run_check(*_a, market_reader, rest_reader, **_k):
        seen.update(market=market_reader, rest=rest_reader)
        return SimpleNamespace(out="OUT")
    monkeypatch.setattr(route, "run_check", fake_run_check)
    monkeypatch.setattr(price_budget, "PRICE_BUDGET_S", BUDGET)
    stalled_market = _Reader(STALL, "MARKET")
    out = await route.adjustment_check(
        1, db=None, user_ref="owner", tracked_reader=None, market_reader=stalled_market,
        rest_reader=_Reader(STALL, SourceReading(SourceState.STATED, Decimal("1"), None)), margin_of=None, ctx=None,
        rates=None, prefs=None, user_values=None)
    assert out == "OUT"
    async with asyncio.timeout(UP_TO):
        market = await seen["market"](None, None)  # the real not-connected read: no chain, prices stale
        assert market.prices_stale is True
        assert (await seen["rest"]("NIFTY")).state is SourceState.FAILED
