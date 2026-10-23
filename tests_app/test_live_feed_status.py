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
from ofo.marketdata.feed_health import FEED_CAPPED, FEED_RECONNECTING, FEED_STALE
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
    waiting = await broker_status(_Db(), "owner", clock)
    assert (waiting.live_market_data.state, waiting.live_market_data.fix) == ("partial", "live_feed_waiting")
    _frame(provider, clock.now)
    flowing = await broker_status(_Db(), "owner", clock)
    assert flowing.live_market_data.state == "connected"


# ---- W-135 (REQ-049 AC-4, #513 item 3): Reconnect advice only inside market hours -------------------------------
# 2026-10-22 is a Thursday, 2026-10-24 a Saturday. Fixed clocks, never the wall clock.
def _ist(day: int, hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, minute, tzinfo=IST)


@pytest.mark.parametrize(("at", "fix"), [
    (_ist(22, 15, 29), "live_feed_waiting"),        # last minute of the session: the Reconnect advice stands
    (_ist(22, 15, 30), "live_feed_market_closed"),  # SESSION_CLOSE is exclusive
    (_ist(22, 15, 31), "live_feed_market_closed"),
    (_ist(22, 9, 14), "live_feed_market_closed"),
    (_ist(22, 9, 15), "live_feed_waiting"),
    (_ist(24, 11, 0), "live_feed_market_closed"),   # Saturday
])
async def test_the_waiting_row_advises_reconnect_only_inside_market_hours(market, provider, clock, at, fix):
    clock.now = at
    provider.on_connected(at)  # connected, no price frame yet
    out = await broker_status(_Db(), "owner", clock)
    assert (out.live_market_data.state, out.live_market_data.fix) == ("partial", fix)


def test_after_hours_a_session_end_still_says_so_and_a_flowing_feed_stays_connected(market, provider, clock):
    clock.now = _ist(22, 16, 0)
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    closed = build_status((T0, False), LATER, live_market.current_state(), live_market.feed_phase(), False)
    assert closed.live_market_data.state == "connected"  # prices arriving is never relabelled
    provider.on_session_ended(clock.now)
    ended = build_status((T0, False), LATER, live_market.current_state(), live_market.feed_phase(), False)
    assert ended.live_market_data.fix == "live_feed_session_ended"  # a genuine 403: Reconnect is the right advice
    reconnecting = build_status((T0, False), LATER, live_market.current_state(), FEED_RECONNECTING, False)
    assert reconnecting.live_market_data.fix == "live_feed_market_closed"  # AC-7: closed in every phase but ended
    open_day = build_status((T0, False), LATER, live_market.current_state(), FEED_RECONNECTING, True)
    assert open_day.live_market_data.fix == "live_feed_reconnecting"


def test_after_hours_a_stopped_socket_after_a_session_end_still_says_log_in_again():
    """Row 7 verifier round 1 (mutation M5 survived): after a Zerodha-ended session the socket STOPS - the market
    state is SESSION_ENDED and the feed phase is None, not FEED_ENDED. After hours that row must still say the session
    ended (log in again), never 'market closed'."""
    out = build_status((T0, False), LATER, live_market.SESSION_ENDED, None, False)
    assert out.live_market_data.fix == "live_feed_session_ended"


def test_the_market_hours_check_has_one_home():
    from ofo.market_calendar import is_market_open as shared
    from ofo_app.routes import execute
    assert execute.market_open is shared


# ---- fix round 1: heartbeats never keep the row Connected --------------------------------------------------------


def _heartbeats_for(provider, clock, seconds: int) -> None:
    """Kite's 1-byte heartbeat, once a second, as the real socket delivers it."""
    for _ in range(seconds):
        clock.now = clock.now + datetime.timedelta(seconds=1)
        provider.on_frame(b"\x00", clock.now)


def test_one_price_frame_then_only_heartbeats_past_the_window_is_waiting_not_connected(market, provider, clock):
    """The verifier's probe shape: one price frame, then 70 s of heartbeats - the row must not stay Connected."""
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    assert _live_row()[:2] == ("connected", None)
    _heartbeats_for(provider, clock, 70)
    assert _live_row()[:2] == ("partial", "live_feed_waiting")


def test_after_unsubscribe_the_heartbeats_leave_the_row_idle(market, provider, clock):
    """The same probe with the subscription released (no screen open): idle, with its own fix, never Connected."""
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    provider.unsubscribe([INSTRUMENT_ID])
    _heartbeats_for(provider, clock, 70)
    assert _live_row()[:2] == ("partial", "live_feed_idle")


def test_connected_with_nothing_subscribed_is_idle_not_waiting(market, provider, clock):
    provider.unsubscribe([INSTRUMENT_ID])
    provider.on_connected(clock.now)
    assert _live_row()[:2] == ("partial", "live_feed_idle")


def test_price_frames_flowing_between_heartbeats_stay_connected(market, provider, clock):
    provider.on_connected(clock.now)
    for _ in range(10):
        _frame(provider, clock.now)
        _heartbeats_for(provider, clock, 1)
        assert _live_row()[:2] == ("connected", None)


def test_a_price_frame_after_a_reconnect_is_needed_again(market, provider, clock):
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    provider.on_disconnected(clock.now)
    provider.on_connected(clock.now)  # back up with the OLD price frame still inside the window
    assert _live_row()[:2] == ("partial", "live_feed_waiting")
    _frame(provider, clock.now)
    assert _live_row()[:2] == ("connected", None)


def test_the_quiet_contract_rule_is_unchanged_health_still_counts_heartbeats(provider, clock):
    """F-32: ``health`` (contract availability) keeps its heartbeat rule; only the status row's phase is stricter."""
    from ofo.rules.inputs import DataHealth
    provider.on_connected(clock.now)
    _frame(provider, clock.now)
    _heartbeats_for(provider, clock, 70)
    assert provider.feed.health(clock.now) is DataHealth.AVAILABLE


@pytest.mark.parametrize("open_now", [True, False])
def test_a_capped_feed_says_live_prices_are_not_available_in_and_out_of_market_hours(open_now):
    """REQ-113 AC-6 (ADR-170): the feed phase ``capped`` reads its own fix at any hour, never waiting, never
    'market closed'."""
    out = build_status((T0, False), LATER, live_market.current_state(), FEED_CAPPED, open_now)
    assert (out.live_market_data.state, out.live_market_data.fix) == ("partial", "live_feed_capped")
    assert out.order_execution.fix == "live_data_not_connected"


# ---- row 11 fix round 1 (REQ-114 AC-7, ADR-177): a closed market with the socket backing off reads market closed ----
SATURDAY_10 = _ist(24, 10, 0)  # Sat 2026-10-24
DUSSEHRA_10 = _ist(20, 10, 0)  # the 2026-10-20 holiday (a Tuesday)
WEDNESDAY_10 = _ist(21, 10, 0)  # an open trading day


def _backing_off_at(provider, clock, at):
    """A price frame arrived at AT (Fri 15:07:20 IST), then the socket dropped at ``at`` and is backing off."""
    provider.on_connected(AT)
    _frame(provider, AT)
    clock.now = at
    provider.on_disconnected(at)


async def test_core_saturday_10am_backoff_reads_market_closed_with_the_banner_text(market, provider, clock):
    """AC-7 (CORE, verify r1 MAJOR): Sat 10:00 IST, socket in back-off: the REAL feed_phase() and the REAL route read
    market closed - not reconnecting - and the reply carries the ADR-177 text with the last price's time in IST."""
    from ofo.marketdata.feed_health import FEED_MARKET_CLOSED
    _backing_off_at(provider, clock, SATURDAY_10)
    assert market.running() and live_market.feed_phase() == FEED_MARKET_CLOSED
    out = await broker_status(_Db(), "owner", clock)
    assert (out.live_market_data.state, out.live_market_data.fix) == ("partial", "live_feed_market_closed")
    assert out.live_market_closed.what_happened == "Market closed. Prices are from 03:07:20 PM."  # AT, 15:07:20 IST


@pytest.mark.parametrize(("at", "fix"), [
    (DUSSEHRA_10, "live_feed_market_closed"),   # holiday
    (SATURDAY_10, "live_feed_market_closed"),   # weekend
    (_ist(21, 8, 0), "live_feed_market_closed"),  # closed by hours
    (_ist(21, 16, 0), "live_feed_market_closed"),
    (WEDNESDAY_10, "live_feed_reconnecting"),   # open day: backing off IS a fault
    (datetime.datetime(2027, 1, 5, 10, 0, tzinfo=IST), "live_feed_market_closed"),  # no calendar data: never open
])
async def test_a_backing_off_socket_reads_by_the_calendar_in_every_answer_state(market, provider, clock, at, fix):
    """Standing item (d): open / closed by hours / weekend / holiday / a date with no calendar data."""
    _backing_off_at(provider, clock, at)
    out = await broker_status(_Db(), "owner", clock)
    assert (out.live_market_data.state, out.live_market_data.fix) == ("partial", fix)
    assert (out.live_market_closed is not None) == (fix == "live_feed_market_closed")


async def test_a_market_closed_reply_with_no_price_ever_has_no_time_text(market, provider, clock):
    """No price frame ever arrived: the fix says market closed; no time is invented (no text)."""
    clock.now = SATURDAY_10
    provider.on_disconnected(clock.now)
    out = await broker_status(_Db(), "owner", clock)
    assert out.live_market_data.fix == "live_feed_market_closed" and out.live_market_closed is None


async def test_a_session_end_on_a_closed_day_still_says_log_in_again(market, provider, clock):
    """Closed in every phase EXCEPT ENDED: a genuine 403 on Saturday is still a session to renew."""
    _backing_off_at(provider, clock, SATURDAY_10)
    provider.on_session_ended(clock.now)
    out = await broker_status(_Db(), "owner", clock)
    assert out.live_market_data.fix == "live_feed_session_ended" and out.live_market_closed is None
