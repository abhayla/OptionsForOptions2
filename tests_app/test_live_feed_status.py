# ruff: noqa: PLC0415
"""REQ-015 AC-4 (W-130): the Settings "live market data" row follows the provider's FEED health, not the socket task.

Core: a running socket task whose provider has had no price frame yet (or is in reconnect backoff) used to answer
``connected``; it now answers ``partial`` with a named fix. Every state below is built from a REAL ``KiteProvider``
driven by its own callbacks and the recorded full frame (tests/fixtures/kite_ws) - never a hand-set flag. No database,
no network.
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib

import pytest
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.feed_health import FEED_STALE
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import broker_sync, live_market
from ofo_app.routes.broker_status import broker_status, build_status

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
INSTRUMENT_ID = "NSE_FO:47189"
AT = datetime.datetime.fromtimestamp(1792143440, IST)  # the recorded frame's exchange time
T0 = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=datetime.UTC)
LATER = T0 + datetime.timedelta(minutes=5)


class _Socket:
    """A socket whose task stays alive like KiteSocket.run does through every drop and backoff."""

    def stop(self) -> None:
        pass

    async def run(self) -> str:
        await asyncio.sleep(3600)
        return "stopped"


class _Clock:
    def __init__(self) -> None:
        self.now = AT

    def __call__(self) -> datetime.datetime:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def provider(clock):
    p = KiteProvider(list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv")), clock=clock)
    p.subscribe([INSTRUMENT_ID])
    return p


@pytest.fixture
async def market(provider, clock):
    m = live_market.LiveMarket()
    m.attach(provider, _Socket(), clock)
    live_market.set_current(m)
    yield m
    live_market.set_current(None)
    m._task.cancel()
    await asyncio.gather(m._task, return_exceptions=True)


@pytest.fixture(autouse=True)
def _clean_sync():
    broker_sync.forget()
    yield
    broker_sync.forget()


def _live_row():
    out = build_status((T0, False), LATER, live_market.current_state(), live_market.feed_phase())
    return out.live_market_data.state, out.live_market_data.fix, out


def _frame(provider, at) -> None:
    provider.on_frame((FIXTURES / "full-frame-12080386-150720.bin").read_bytes(), at)


def test_core_a_running_socket_with_no_frame_yet_is_partial_waiting_not_connected(market, provider, clock):
    """THE CORE: the socket task is running (the old test for Connected) and the socket is open, but no price frame has
    arrived. Before W-130 this answered connected."""
    provider.on_connected(clock.now)
    assert market.running() and live_market.current_session() is not None  # what the old code looked at
    state, fix, out = _live_row()
    assert (state, fix) == ("partial", "live_feed_waiting")
    assert (out.order_execution.state, out.order_execution.fix) == ("partial", "live_data_not_connected")


def test_a_heartbeat_alone_is_still_waiting(market, provider, clock):
    """A 1-byte heartbeat proves the link, not prices (finding first-live-frame-before-first-price)."""
    provider.on_connected(clock.now)
    provider.on_frame(b"\x00", clock.now)
    assert _live_row()[:2] == ("partial", "live_feed_waiting")


def test_frames_flowing_is_connected(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    state, fix, out = _live_row()
    assert (state, fix) == ("connected", None)
    assert out.order_execution.state == "connected"


def test_frames_stopped_beyond_the_window_is_waiting_again(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    clock.now = clock.now + FEED_STALE + datetime.timedelta(seconds=1)
    assert _live_row()[:2] == ("partial", "live_feed_waiting")


def test_a_frame_just_inside_the_window_is_still_connected(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    clock.now = clock.now + FEED_STALE
    assert _live_row()[:2] == ("connected", None)


def test_socket_in_backoff_is_partial_reconnecting(market, provider, clock):
    """The task is alive through the drop and the backoff; the provider says not connected."""
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    provider.on_disconnected(clock.now)
    assert market.running()
    assert _live_row()[:2] == ("partial", "live_feed_reconnecting")


def test_a_provider_that_never_connected_is_reconnecting_not_connected(market):
    assert _live_row()[:2] == ("partial", "live_feed_reconnecting")


def test_session_ended_by_403_is_partial_session_ended(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    provider.on_session_ended(clock.now)
    assert _live_row()[:2] == ("partial", "live_feed_session_ended")


async def test_a_finished_socket_task_has_no_phase_and_names_the_state_fix(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    market._task.cancel()
    await asyncio.gather(market._task, return_exceptions=True)
    market.state = live_market.SESSION_ENDED
    assert live_market.feed_phase() is None
    assert _live_row()[:2] == ("partial", "live_feed_session_ended")


def test_a_provider_without_feed_state_never_reads_connected(clock):
    """Fail closed: a running market whose provider keeps no feed state (a replay) is not 'Connected'."""
    m = live_market.LiveMarket()

    class _NoFeed:
        pass

    from decimal import Decimal

    from ofo_app.live_push import LiveFeed
    from ofo_app.routes.outcome import MarketContext
    m.feed = LiveFeed(MarketContext(_NoFeed(), clock, Decimal("0.065")), None)
    m.state = live_market.LIVE
    m._task = type("T", (), {"done": lambda self: False})()
    live_market.set_current(m)
    try:
        assert live_market.feed_phase() is None
        assert _live_row()[:2] == ("partial", "live_feed_not_running")
    finally:
        live_market.set_current(None)


def test_no_market_is_off(clock):
    live_market.set_current(None)
    assert live_market.feed_phase() is None
    assert _live_row()[:2] == ("partial", "live_feed_off")


class _Db:
    """The route's database: one active, unexpired session row."""

    async def execute(self, _stmt, _params):
        class _R:
            def one_or_none(self):
                return (T0, False)
        return _R()


async def test_the_route_answers_from_the_feed_not_the_task(market, provider, clock):
    """Through the real route function with a running socket and no frame yet: waiting, then connected after a frame."""
    provider.on_connected(clock.now)
    waiting = await broker_status(_Db(), "owner")
    assert (waiting.live_market_data.state, waiting.live_market_data.fix) == ("partial", "live_feed_waiting")
    _frame(provider, clock.now)
    flowing = await broker_status(_Db(), "owner")
    assert flowing.live_market_data.state == "connected"
