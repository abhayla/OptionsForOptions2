"""The one spot resolver (REQ-155 AC-5, F-76, ADR-212): live feed, else a Kite REST index quote, else the last close.

``resolve_spot(feed, rest, last_close, now=...)`` is pure: each source arrives as a ``SourceReading`` carrying its
answer state (stated / absent / not found / failed / empty), its value and the time it was read; the caller does
the fetching.
The first usable source wins, in that order, and the answer is always labelled with its source and time. When no source
is usable there is NO value, and ``reasons`` holds one code per source (the screen says "Spot not available" with them);
a default spot is never made up.

Rules:
- the feed counts only while its tick is no older than ``windows.stale`` (the feed-health window in force,
  ``detection.feed_stale_seconds``); a tick
  dated more than ``CLOCK_SKEW_TOLERANCE`` (2 s, shared with the Execute gate) after the caller's clock is not fresh
  either (fail closed);
- a REST answer or a last close counts only when stated with a price above 0 (``is_live_price``): a 200 with no
  ``last_price`` is EMPTY, never 0;
- a value that is not finite (NaN, sNaN, Infinity) is ``not_finite``, checked before any comparison, never a spot and
  never an exception; a reading dated beyond the skew window in the future is refused for EVERY source (fail closed);
- the last close is labelled with its own date, never as live (ADR-212 / ADR-177).

Standard library only; no wall clock (the caller passes ``now``).
"""
from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from ofo.marketdata.feed_health import FeedWindows, market_closed_for
from ofo.marketdata.health import CLOCK_SKEW_TOLERANCE
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST

SOURCE_FEED: Final = "feed"
SOURCE_REST: Final = "rest_quote"
SOURCE_LAST_CLOSE: Final = "last_close"
#: the order of preference, and the label each source carries
SOURCE_ORDER: Final = (SOURCE_FEED, SOURCE_REST, SOURCE_LAST_CLOSE)
SPOT_NOT_AVAILABLE: Final = "spot_not_available"
#: the reason codes (the screen words them through the catalogue; this domain module holds codes, not sentences). A
#: source that answered but not usably carries its answer state's name: "not_found", "failed" or "empty".
REASON_ABSENT: Final = "absent"
REASON_NO_PRICE: Final = "no_price"
REASON_NO_TIME: Final = "no_time"
REASON_FUTURE: Final = "tick_in_future"
REASON_STALE: Final = "stale"
REASON_NOT_FINITE: Final = "not_finite"


class SourceState(enum.Enum):
    """How a source answered (every answer state is named; none is folded into another)."""
    STATED = "stated"
    ABSENT = "absent"        # nothing was held / the source was not asked (feed not connected, no close stored)
    NOT_FOUND = "not_found"  # asked, and the source does not know the instrument
    FAILED = "failed"        # the call or read raised / was refused
    EMPTY = "empty"          # answered, but without a usable price


@dataclass(frozen=True)
class SourceReading:
    state: SourceState
    value: Decimal | None = None
    at: datetime.datetime | None = None  # when the value was read (a last close: its close time)


@dataclass(frozen=True)
class SpotAnswer:
    """``value`` is None exactly when nothing was usable; ``reasons`` then holds (source, why) for all three (when a
    fallback source won, only the better sources that were skipped)."""
    value: Decimal | None
    source: str | None
    at: datetime.datetime | None
    reasons: tuple[tuple[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.value is not None


def _why_not(name: str, reading: SourceReading | None, now: datetime.datetime, windows: FeedWindows) -> str | None:
    """None when ``reading`` is usable, else the reason in plain words."""
    if reading is None or reading.state is SourceState.ABSENT:
        return REASON_ABSENT
    if reading.state is not SourceState.STATED:
        return reading.state.name.lower()
    return _price_problem(reading.value) or _time_problem(name, reading.at, now, windows)


def _price_problem(value: object) -> str | None:
    """None when a STATED reading's value is a live price, else the reason."""
    if not isinstance(value, Decimal):
        return REASON_NO_PRICE
    if not value.is_finite():  # before any comparison: comparing a NaN raises
        return REASON_NOT_FINITE
    return None if is_live_price(value) else REASON_NO_PRICE


def _time_problem(name: str, at: datetime.datetime | None, now: datetime.datetime,
                  windows: FeedWindows) -> str | None:
    """None when a STATED reading's time is aware, not in the future and (for the feed) fresh, else the reason."""
    if at is None or at.tzinfo is None:
        return REASON_NO_TIME
    if at - now > CLOCK_SKEW_TOLERANCE:  # a stamp a moment after the caller's clock is a fresh quote, not a future one
        return REASON_FUTURE
    return _feed_age_problem(now - at, windows) if name == SOURCE_FEED else None


def _feed_age_problem(age: datetime.timedelta, windows: FeedWindows) -> str | None:
    if age < -CLOCK_SKEW_TOLERANCE:
        return REASON_FUTURE
    if age > windows.stale:
        return REASON_STALE
    return None


def feed_is_live(provider: Any, now: datetime.datetime) -> bool:
    """The connection-aware liveness both callers pass to ``feed_reading``: the market is open (``market_closed_for``,
    the one market-state answer) and the provider's feed health is AVAILABLE (not stale, not disconnected). The
    background worker's ``feed_state`` returns None exactly when this is True."""
    if market_closed_for(provider, now):
        return False
    return provider.status().health is DataHealth.AVAILABLE


def feed_reading(quote: NormalizedQuote | None, now: datetime.datetime, *, feed_live: bool) -> SourceReading:
    """The feed spot reading, ONE rule for the screen and the background worker (#639 item 1, REQ-165 AC-5; findings
    staleness-by-last-change-age and engine-input-chosen-per-caller).

    A quote's timestamp is its LAST CHANGE: Kite sends a packet only when the price changes, so a quiet index on a live
    feed keeps an old stamp while its price is current. Freshness is therefore judged by the CONNECTION, not by that
    age: a quote on a live feed is stamped ``now``. Answer states:
    - no quote held -> ABSENT;
    - live (``feed_live``: the feed is connected and current and the market is open, the caller's connection-aware
      answer) and the quote's own health AVAILABLE and its last change today (IST), not in the future -> STATED at
      ``now`` (fresh, however quiet);
    - feed stale / disconnected / market closed (``feed_live`` False), the quote's own health not AVAILABLE, or no tick
      yet today (a last change on an earlier IST day) -> STATED with its own last change, so ``resolve_spot``'s age
      window judges it (an old stamp is refused as stale: fail closed);
    - a last change in the future or with no timezone -> kept as is, so ``resolve_spot`` refuses it."""
    if quote is None:
        return SourceReading(SourceState.ABSENT)
    at = quote.timestamp
    if (feed_live and quote.health is DataHealth.AVAILABLE and at is not None and at.tzinfo is not None
            and at <= now and at.astimezone(IST).date() == now.astimezone(IST).date()):
        at = now
    return SourceReading(SourceState.STATED, quote.ltp, at)


def resolve_spot(feed: SourceReading | None, rest: SourceReading | None, last_close: SourceReading | None, *,
                 now: datetime.datetime, windows: FeedWindows) -> SpotAnswer:
    """Feed -> REST quote -> last close; the first usable one is returned, labelled with its source and time."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    reasons: list[tuple[str, str]] = []
    for name, reading in zip(SOURCE_ORDER, (feed, rest, last_close), strict=True):
        why = _why_not(name, reading, now, windows)
        if why is None:
            assert reading is not None and reading.at is not None  # noqa: S101 - narrowed by _why_not
            return SpotAnswer(reading.value, name, reading.at, tuple(reasons))
        reasons.append((name, why))
    return SpotAnswer(None, None, None, tuple(reasons))
