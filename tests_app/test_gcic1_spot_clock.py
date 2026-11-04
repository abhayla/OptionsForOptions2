"""GC-IC1 step 9 live fix: every route that resolves the spot judges the feed and REST readings against a clock read
AFTER those readings arrived (finding freshness-judged-on-request-start-clock, third site). No database, no Kite.

Live 2026-11-04 09:18:58: a request that took 3 s over the DB tunnel judged a quote stamped 2.5 s after it began against
``market.now`` (read at the start) -> ``tick_in_future``, so all 15 approaches were refused for no spot.
The fake clock below stays at the request start until a reader runs, then moves 3 s on (the slow reads)."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app.routes import adjustment as route
from ofo_app.routes import adjustment_check as check_route
from ofo_app.routes import adjustment_plan as plan_route
from ofo_app.routes import outcome, playbooks
from test_adjustment_approaches_route import IC_IDS, client_for, load, market_of, post

S = datetime.timedelta
SPOT = D("24500.00")
T0 = datetime.datetime(2026, 11, 4, 3, 48, 55, tzinfo=datetime.UTC)


class Clock:
    """The server clock: the request start until ``slow_reads()`` is called, then ``took`` later."""

    def __init__(self, start: datetime.datetime, took: float = 3.0):
        self.start, self.took, self.moved = start, S(seconds=took), False

    def __call__(self) -> datetime.datetime:
        return self.start + (self.took if self.moved else S(0))

    def slow_reads(self) -> None:
        self.moved = True


def _readings(t0, feed_after=2.5, rest_after=2.5):
    return (SourceReading(SourceState.STATED, SPOT, t0 + S(seconds=feed_after)),
            SourceReading(SourceState.STATED, SPOT, t0 + S(seconds=rest_after)))


def _rest_reader(clock, rest):
    async def rest_reader(_underlying):
        clock.slow_reads()  # the DB / REST reads of the request take 3 s
        return rest
    return rest_reader


def _market(t0, feed):
    return route.MarketInputs((), {}, None, None, None, feed, SourceReading(SourceState.ABSENT), t0)


def _compare(monkeypatch, feed_after, rest_after, *, feed_ok=False):
    sc = load(IC_IDS[0])
    t0 = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    clock = Clock(t0)
    monkeypatch.setattr(outcome, "server_now", clock)
    feed, rest = _readings(t0, feed_after, rest_after)
    market = dataclasses.replace(market_of(sc), feed=feed if feed_ok else SourceReading(SourceState.ABSENT), now=t0)
    c = client_for(sc)

    async def market_reader(_t, _ctx):
        return market
    c.app.dependency_overrides[route.get_market_reader] = lambda: market_reader
    c.app.dependency_overrides[route.get_rest_spot_reader] = lambda: _rest_reader(clock, rest)
    return post(c).json()["spot"]


# --- the Compare route (the defect, then the answer states) -------------------------------------------------------

def test_compare_accepts_a_rest_quote_stamped_2_5_s_after_a_3_s_request_began(monkeypatch):
    spot = _compare(monkeypatch, 2.5, 2.5)
    assert spot["value"] is not None and spot["source"] == "rest_quote"


def test_compare_accepts_a_feed_tick_stamped_2_5_s_after_the_request_began(monkeypatch):
    spot = _compare(monkeypatch, 2.5, 2.5, feed_ok=True)
    assert spot["value"] is not None and spot["source"] == "feed"


def test_compare_still_refuses_a_stamp_5_s_after_the_judging_moment_as_future(monkeypatch):
    spot = _compare(monkeypatch, 8.1, 8.1, feed_ok=True)  # judged at +3.0 s: 5.1 s ahead
    assert spot["value"] is None
    assert "future" in str(spot).lower()


def test_compare_still_refuses_a_feed_tick_older_than_the_stale_window_at_the_judging_moment(monkeypatch):
    spot = _compare(monkeypatch, -10.0, 2.5, feed_ok=True)  # 13 s old at +3.0 s, window 3 s -> stale; REST answers
    assert spot["source"] == "rest_quote"


def test_compare_feed_and_rest_absent_gives_no_spot(monkeypatch):
    sc = load(IC_IDS[0])
    t0 = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    clock = Clock(t0)
    monkeypatch.setattr(outcome, "server_now", clock)
    c = client_for(sc)
    market = dataclasses.replace(market_of(sc), feed=SourceReading(SourceState.ABSENT),
                                 last_close=SourceReading(SourceState.ABSENT), now=t0)

    async def market_reader(_t, _ctx):
        return market
    c.app.dependency_overrides[route.get_market_reader] = lambda: market_reader
    c.app.dependency_overrides[route.get_rest_spot_reader] = lambda: _rest_reader(
        clock, SourceReading(SourceState.ABSENT))
    spot = post(c).json()["spot"]
    assert spot["value"] is None and spot["source"] is None


# --- the other routes: the spot handed on is judged at the later clock ------------------------------------------

class _Stop(Exception):
    pass


async def test_check_route_judges_the_spot_at_the_later_clock(monkeypatch):
    clock = Clock(T0)
    monkeypatch.setattr(outcome, "server_now", clock)
    _feed, rest = _readings(T0)
    seen = {}

    def stop(_position, spot, _listed):
        seen["spot"] = spot
        raise _Stop

    monkeypatch.setattr(check, "strategy_type", stop)

    async def tracked(_sid, _rates):
        return SimpleNamespace(position=SimpleNamespace(underlying="NIFTY"))

    async def market(_t, _c):
        return _market(T0, SourceReading(SourceState.ABSENT))

    with pytest.raises(_Stop):
        await check_route.adjustment_check(
            1, None, "u", tracked, market, _rest_reader(clock, rest), None, None, None, None)
    assert seen["spot"] == SPOT


async def test_plan_route_judges_the_spot_at_the_later_clock(monkeypatch):
    clock = Clock(T0)
    monkeypatch.setattr(outcome, "server_now", clock)
    _feed, rest = _readings(T0)

    async def no_plan(*_a):
        return None

    monkeypatch.setattr(plan_route.store, "plan_for", no_plan)
    seen = {}
    monkeypatch.setattr(plan_route.check, "strategy_type", lambda _p, spot, _l: seen.setdefault("spot", spot))

    async def market(_t, _c):
        return _market(T0, SourceReading(SourceState.ABSENT))

    tracked = SimpleNamespace(position=SimpleNamespace(underlying="NIFTY"))
    await plan_route._type_of(None, "u", 1, tracked, market, _rest_reader(clock, rest), None)
    assert seen["spot"] == SPOT


async def test_playbook_preview_judges_the_spot_at_the_later_clock(monkeypatch):
    clock = Clock(T0)
    monkeypatch.setattr(outcome, "server_now", clock)
    _feed, rest = _readings(T0)

    async def tracked_reader(_id, _rates):
        return SimpleNamespace(position=SimpleNamespace(underlying="NIFTY"))

    async def market_reader(_t, _c):
        return _market(T0, SourceReading(SourceState.ABSENT))

    async def margin(*_a):
        return None

    monkeypatch.setattr(playbooks, "current_margin", margin)
    seams = playbooks._Seams(tracked_reader, market_reader, _rest_reader(clock, rest), None, None, None, None)
    read = playbooks._Read()
    await playbooks._read_one(SimpleNamespace(id=1), seams, None, read)
    assert read.spot.value == SPOT and read.spot.source == "rest_quote"


async def test_window_spot_rest_branch_judges_at_the_later_clock(monkeypatch):
    clock = Clock(T0)
    monkeypatch.setattr(outcome, "server_now", clock)
    _feed, rest = _readings(T0)

    async def slow_rest(_u):
        clock.slow_reads()
        return rest

    monkeypatch.setattr(readers, "read_rest_spot", slow_rest)
    monkeypatch.setattr(readers, "screen_feed_reading", lambda *_a: SourceReading(SourceState.ABSENT))
    monkeypatch.setattr(readers, "market_state", lambda *_a: SimpleNamespace(closed=False))
    monkeypatch.setattr(readers, "read_last_close", lambda *_a: SourceReading(SourceState.ABSENT))
    ctx = SimpleNamespace(clock=clock, provider=None, feed_windows=outcome.feed_windows_of(None))
    assert await readers._window_spot(ctx, "NIFTY", None, T0) == SPOT
