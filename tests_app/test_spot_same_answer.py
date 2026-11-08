"""#639 item 1 (REQ-165 AC-5 "same answer"): the screen and the background worker read the feed spot by ONE rule
(``spot_source.feed_reading`` with ``feed_is_live``; findings staleness-by-last-change-age and
engine-input-chosen-per-caller). Same input -> same answer, for every answer state: fresh (a quiet index 10 s after its
last tick on a connected feed), feed stale, feed disconnected, market closed, no tick yet today. No database."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.marketdata.kite_provider import SOURCE
from ofo.marketdata.quote import NormalizedQuote
from ofo.marketdata.spot_source import resolve_spot
from ofo.rules.inputs import DataHealth
from ofo.settings import calc, defaults
from ofo.timeutil import IST
from ofo_app import adjustment_readers, background

NOW = datetime.datetime(2026, 11, 6, 11, 40, 10, tzinfo=IST)  # a Friday in market hours
WINDOWS = calc.feed_windows(defaults())
SPOT = Decimal("23420.00")


class _Feed:
    def __init__(self, closed: bool) -> None:
        self.closed = closed

    def market_closed(self, _now: datetime.datetime) -> bool:
        return self.closed


class _Provider:
    """The two things both callers ask: the feed's market state and its connection-aware health."""

    def __init__(self, health: DataHealth, closed: bool = False) -> None:
        self.feed, self._health = _Feed(closed), health

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(health=self._health)


def _index(at: datetime.datetime) -> NormalizedQuote:
    return NormalizedQuote(
        instrument_id="NSE_INDEX:256265", underlying="NIFTY", exchange="NSE", segment="NSE_INDEX", instrument_type=None,
        expiry=None, strike=None, ltp=SPOT, bid=None, ask=None, volume=None, oi=None, oi_change=None, iv=None,
        delta=None, gamma=None, theta=None, vega=None, timestamp=at, source=SOURCE, health=DataHealth.AVAILABLE)


def _worker_answer(provider: _Provider, quote: NormalizedQuote) -> Decimal | None:
    """The worker: ``feed_state`` decides first (a non-None state pauses: no spot); a FRESH read's spot is
    ``feed_spot``'s reading, resolved as ``state_from_market`` resolves it."""
    if background.feed_state(provider, NOW) is not None:
        return None
    reading = background.feed_spot(background.PriceRead(background.PriceState.FRESH, spot=quote), NOW)
    return resolve_spot(reading, None, None, now=NOW, windows=WINDOWS).value


def _screen_answer(provider: _Provider, quote: NormalizedQuote) -> Decimal | None:
    reading = adjustment_readers.screen_feed_reading(provider, quote, NOW)
    return resolve_spot(reading, None, None, now=NOW, windows=WINDOWS).value


QUIET = NOW - datetime.timedelta(seconds=10)  # 10 s after the last tick: past the 3 s window


@pytest.mark.parametrize(("state", "provider", "last_tick", "expected"), [
    ("fresh, quiet index", _Provider(DataHealth.AVAILABLE), QUIET, SPOT),
    ("feed stale", _Provider(DataHealth.STALE), QUIET, None),
    ("feed disconnected", _Provider(DataHealth.UNAVAILABLE), QUIET, None),
    ("market closed", _Provider(DataHealth.AVAILABLE, closed=True), QUIET, None),
    ("no tick yet today", _Provider(DataHealth.AVAILABLE), NOW - datetime.timedelta(days=1), None),
])
def test_the_screen_and_the_worker_give_the_same_feed_spot(state, provider, last_tick, expected):
    quote = _index(last_tick)
    assert _worker_answer(provider, quote) == expected, state
    assert _screen_answer(provider, quote) == expected, state
