"""REQ-114 AC-7 on the REAL path (chunk 1 Tier A review F1, class market-state-decided-per-surface): "Outside market
hours (ADR-119 calendar) silence is expected: the health check marks data market closed". The calendar is read by the
ONE quote-health path (``FeedState``), so a closed market is never AVAILABLE whatever frames arrive (ADR-015), and every
answer built on it inherits that. A KiteProvider fed the recorded full frame, then a heartbeat every second.

Answer states of the calendar (standing item d): open -> available; closed weekend / holiday / after hours / pre-open ->
stale + market closed; a date past the calendar's data (NO_CALENDAR) -> stale + market closed (fail closed)."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from ofo.instruments.parser import parse_instruments_csv
from ofo.market_calendar import Holidays, is_market_open
from ofo.marketdata.feed_health import FEED_HEALTHY, FEED_MARKET_CLOSED, FeedState, market_closed_for
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "kite_ws"
FRAME = (FIX / "full-frame-12080386-150720.bin").read_bytes()
IID = "NSE_FO:47189"  # the contract in the recorded full frame

SATURDAY = datetime.datetime(2026, 10, 24, 10, 0, tzinfo=IST)
WEDNESDAY = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)
DUSSEHRA = datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST)  # NSE F&O holiday (a Tuesday)
PAST_CALENDAR = datetime.datetime(2031, 3, 5, 10, 0, tzinfo=IST)  # a Wednesday in a year the data file does not list
PRE_OPEN = datetime.datetime(2026, 10, 21, 9, 14, 59, tzinfo=IST)
AFTER_CLOSE = datetime.datetime(2026, 10, 21, 15, 30, tzinfo=IST)


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now


def _provider_after_five_minutes_of_heartbeats(start: datetime.datetime) -> tuple[KiteProvider, Clock]:
    clock = Clock(start)
    provider = KiteProvider(list(parse_instruments_csv(FIX / "instruments-2026-10-08-subscribed.csv")), clock=clock)
    provider.subscribe([IID])
    provider.on_connected(start)
    provider.on_frame(FRAME, start + datetime.timedelta(seconds=1))
    for second in range(2, 300):
        provider.on_frame(b"\x00", start + datetime.timedelta(seconds=second))  # Kite's 1-byte heartbeat
    clock.now = start + datetime.timedelta(seconds=299, milliseconds=500)
    return provider, clock


def test_saturday_with_heartbeats_reads_market_closed_never_available():
    """AC-7: Saturday 10:00 IST, one data frame then heartbeats for 5 minutes: market closed, never available."""
    provider, clock = _provider_after_five_minutes_of_heartbeats(SATURDAY)
    assert provider.feed.market_closed(clock.now) is True
    assert provider.feed.health(clock.now) is DataHealth.STALE
    assert sorted({q.health.value for q in provider.book.quotes(clock.now)}) == ["stale"]
    assert provider.feed.phase(clock.now) == FEED_MARKET_CLOSED


def test_saturday_right_after_the_snapshot_frame_is_still_market_closed():
    """AC-7: even inside FEED_STALE of a price frame (Kite's connect-time snapshot) a closed market is not live."""
    clock = Clock(SATURDAY)
    provider = KiteProvider(list(parse_instruments_csv(FIX / "instruments-2026-10-08-subscribed.csv")), clock=clock)
    provider.subscribe([IID])
    provider.on_connected(SATURDAY)
    provider.on_frame(FRAME, SATURDAY)
    assert provider.book.get(IID, SATURDAY).health is DataHealth.STALE
    assert provider.feed.phase(SATURDAY) == FEED_MARKET_CLOSED


def test_wednesday_with_the_same_frames_stays_available():
    """AC-7 negative case: an open market with heartbeats keeps quiet contracts available (F-32)."""
    provider, clock = _provider_after_five_minutes_of_heartbeats(WEDNESDAY)
    assert provider.feed.market_closed(clock.now) is False
    assert provider.feed.health(clock.now) is DataHealth.AVAILABLE
    assert sorted({q.health.value for q in provider.book.quotes(clock.now)}) == ["available"]


@pytest.mark.parametrize("when", [DUSSEHRA, PAST_CALENDAR, PRE_OPEN, AFTER_CLOSE])
def test_every_closed_state_of_the_calendar_reads_market_closed(when):
    """AC-7 (standing item d): holiday, a date past the calendar (fail closed), pre-open and after hours: closed."""
    assert is_market_open(when) is False  # the calendar's own answer, independent of the feed
    feed = FeedState()
    feed.on_connected(when)
    feed.on_data(when)
    assert feed.market_closed(when) is True
    assert feed.health(when) is DataHealth.STALE
    assert feed.phase(when) == FEED_MARKET_CLOSED


def test_a_calendar_that_cannot_answer_reads_closed():
    """AC-7: an empty holiday table (unreadable data file) answers NO_CALENDAR for every date: closed (fail closed)."""
    empty: Holidays = {}
    feed = FeedState(market_open=lambda now: is_market_open(now, empty))
    feed.on_connected(WEDNESDAY)
    feed.on_data(WEDNESDAY)
    assert feed.health(WEDNESDAY) is DataHealth.STALE
    assert feed.phase(WEDNESDAY) == FEED_MARKET_CLOSED


def test_the_injected_calendar_is_the_one_read_and_open_keeps_the_feed_phases():
    """AC-7: the feed reads its injected calendar; open -> healthy on a fresh price frame."""
    feed = FeedState(market_open=lambda _now: True)
    feed.on_connected(SATURDAY)
    feed.on_data(SATURDAY)
    assert feed.health(SATURDAY) is DataHealth.AVAILABLE
    assert feed.phase(SATURDAY) == FEED_HEALTHY


def test_a_provider_without_a_feed_gets_the_calendar_answer():
    """AC-7 (CI fix F1): the one market-state function serves every provider shape - a relay or fake with no
    ``feed`` (bus mode's FeedRelay) reads the calendar; one with a feed reads that feed's answer."""
    class NoFeed:
        pass
    assert market_closed_for(NoFeed(), SATURDAY) is True
    assert market_closed_for(NoFeed(), WEDNESDAY) is False
    assert market_closed_for(None, PAST_CALENDAR) is True
    open_feed = type("P", (), {"feed": FeedState(market_open=lambda _now: True)})()
    assert market_closed_for(open_feed, SATURDAY) is False
