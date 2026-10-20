"""The Execute gate judges live-data freshness on a clock read AFTER the quote (GC-3L, 2026-10-19).

RCA: ``_execute`` read ``req.now`` once at request start, then read Zerodha's margin and positions over the network,
and only then ``_data_health`` judged each quote with ``0 <= req.now - frame_time <= stale_after``. On a live market
the index ticks every second, so the latest frame is newer than ``req.now`` and every ENTRY/EXIT was refused as
``MARKET_DATA_103`` (measured live 2026-10-19 09:4x IST, strategy 11, three presses, codes=DATA_UNHEALTHY x3).

Class: every live-data freshness judgement in the Execute route (LEG_PRICES via ``priced.quote_times``,
UNDERLYING_PRICE via ``req.quotes.underlying_price``) compared with a clock read before the quote. The return route
(``execution_return``) makes no freshness judgement (no ``_health`` caller there).

These run on the real route function with no database (the list load is monkeypatched), like the ADR-023 clock tests
in ``test_execute_route.py``. The replay/e2e seam pins ``req.clock`` to ``req.now`` (``lambda: AT``), which can never
produce a frame time after the request clock: that is why this ordering never showed in a replay test.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.execution.context import DataHealth, DataInput
from ofo.marketdata.health import HealthThresholds
from ofo_app import eligibility_from_zerodha as elig
from ofo_app.execute_replay import AT, replay_list_stamp
from ofo_app.routes import execute as route

S = datetime.timedelta(seconds=1)
SKEW = HealthThresholds().clock_skew_tolerance
STALE_AFTER = HealthThresholds().stale_after


@pytest.fixture(autouse=True)
def _list_loaded(monkeypatch):
    async def _loaded_at(conn):
        return AT

    monkeypatch.setattr(elig, "list_loaded_at", _loaded_at)


def _req(spot_at: datetime.datetime | None, check_at: datetime.datetime) -> SimpleNamespace:
    quote = None if spot_at is None else (D("23131.85"), spot_at)
    return SimpleNamespace(db=None, now=AT, clock=lambda: check_at, list_stamp=replay_list_stamp,
                           quotes=SimpleNamespace(underlying_price=lambda u: quote))


async def _health(spot_at, check_at, leg_times=()) -> dict:
    return await route._data_health(_req(spot_at, check_at), SimpleNamespace(quote_times=tuple(leg_times)), "NIFTY")


async def test_1_an_index_tick_a_moment_after_the_request_started_is_healthy():
    health = await _health(AT + S, AT + S + S / 2)
    assert health[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY
    later = AT + SKEW + 2 * S  # beyond the skew of req.now, so only the after-quote clock passes it
    slow = await _health(later, later + S / 2)
    assert slow[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY


async def test_2_a_leg_tick_after_the_request_started_is_healthy_when_the_check_clock_is_later():
    health = await _health(AT, AT + 3 * S, leg_times=(AT + 2 * S, AT - 5 * S))
    assert health[DataInput.LEG_PRICES] is DataHealth.HEALTHY
    later = AT + SKEW + 2 * S  # beyond the skew of req.now, so only the after-quote clock passes it
    slow = await _health(AT, later + S, leg_times=(later, AT - 5 * S))
    assert slow[DataInput.LEG_PRICES] is DataHealth.HEALTHY


async def test_3_a_frame_beyond_the_skew_tolerance_after_the_check_clock_is_refused():
    check = AT + 10 * S
    future = check + SKEW + S  # 3 s ahead of the check clock: a bad clock or a bad packet
    health = await _health(future, check, leg_times=(future,))
    assert health[DataInput.UNDERLYING_PRICE] is DataHealth.STALE
    assert health[DataInput.LEG_PRICES] is DataHealth.STALE
    within = await _health(check + SKEW, check, leg_times=(check + SKEW,))  # the edge of the tolerance: fresh
    assert within[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY
    assert within[DataInput.LEG_PRICES] is DataHealth.HEALTHY


async def test_4_older_than_stale_after_is_stale_and_just_inside_is_healthy():
    check = AT + 10 * S
    old = await _health(check - STALE_AFTER - S, check, leg_times=(check - STALE_AFTER - S,))
    assert old[DataInput.UNDERLYING_PRICE] is DataHealth.STALE
    assert old[DataInput.LEG_PRICES] is DataHealth.STALE
    recent = await _health(check - STALE_AFTER + S, check, leg_times=(check - STALE_AFTER + S,))
    assert recent[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY
    assert recent[DataInput.LEG_PRICES] is DataHealth.HEALTHY


async def test_5_no_quote_is_unavailable():
    health = await _health(None, AT + S)
    assert health[DataInput.UNDERLYING_PRICE] is DataHealth.UNAVAILABLE
    assert health[DataInput.LEG_PRICES] is DataHealth.UNAVAILABLE


async def test_6_a_pinned_clock_judges_recorded_frames_as_before():
    """The replay seam (``get_execute_clock`` -> ``lambda: AT``): the check clock IS ``req.now``."""
    health = await _health(AT - S, AT, leg_times=(AT - S,))
    assert health[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY
    assert health[DataInput.LEG_PRICES] is DataHealth.HEALTHY


async def test_7_the_check_clock_is_read_after_the_index_quote():
    """A live-shaped ordering: time moves on while the quote is read (the margin/positions reads before it, then the
    feed). A clock read before the quote sees the tick 5 s in the future (beyond the skew) and refuses it."""
    world = {"t": AT}

    def _spot(underlying):
        world["t"] += 5 * S  # the tick that arrived while the route read Zerodha
        return D("23135.90"), world["t"]

    req = SimpleNamespace(db=None, now=AT, clock=lambda: world["t"], quotes=SimpleNamespace(underlying_price=_spot),
                          list_stamp=replay_list_stamp)
    health = await route._data_health(req, SimpleNamespace(quote_times=()), "NIFTY")
    assert health[DataInput.UNDERLYING_PRICE] is DataHealth.HEALTHY
