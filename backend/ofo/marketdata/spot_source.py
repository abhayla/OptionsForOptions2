"""The one spot resolver (REQ-155 AC-5, F-76, ADR-212): live feed, else a Kite REST index quote, else the last close.

``resolve_spot(feed, rest, last_close, now=...)`` is pure: each source arrives as a ``SourceReading`` carrying its
answer state (stated / absent / not found / failed / empty), its value and the time it was read; the caller does
the fetching.
The first usable source wins, in that order, and the answer is always labelled with its source and time. When no source
is usable there is NO value, and ``reasons`` holds one line per source (the screen says "Spot not available" with them);
a default spot is never made up.

Rules:
- the feed counts only while its tick is no older than ``FEED_STALE`` (the feed-health rule, not a new number); a tick
  dated in the future is not fresh either (fail closed);
- a REST answer or a last close counts only when stated with a price above 0 (``is_live_price``): a 200 with no
  ``last_price`` is EMPTY, never 0;
- the last close is labelled with its own date, never as live (ADR-212 / ADR-177).

Standard library only; no wall clock (the caller passes ``now``).
"""
from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.marketdata.feed_health import FEED_STALE
from ofo.marketdata.quote import is_live_price

SOURCE_FEED: Final = "feed"
SOURCE_REST: Final = "REST quote"
SOURCE_LAST_CLOSE: Final = "last close"
#: the order of preference, and the label each source carries
SOURCE_ORDER: Final = (SOURCE_FEED, SOURCE_REST, SOURCE_LAST_CLOSE)
SPOT_NOT_AVAILABLE: Final = "Spot not available"


class SourceState(enum.Enum):
    """How a source answered (every answer state is named; none is folded into another)."""
    STATED = "stated"
    ABSENT = "absent"        # nothing was held / the source was not asked (feed not connected, no close stored)
    NOT_FOUND = "not found"  # asked, and the source does not know the instrument
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
    label: str
    reasons: tuple[tuple[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.value is not None


def _why_not(name: str, reading: SourceReading | None, now: datetime.datetime) -> str | None:
    """None when ``reading`` is usable, else the reason in plain words."""
    if reading is None or reading.state is SourceState.ABSENT:
        return "no tick held" if name == SOURCE_FEED else "nothing held"
    if reading.state is not SourceState.STATED:
        return reading.state.value
    if not isinstance(reading.value, Decimal) or not is_live_price(reading.value):
        return "empty (no price)"
    if reading.at is None or reading.at.tzinfo is None:
        return "no time"
    return _feed_age_problem(now - reading.at) if name == SOURCE_FEED else None


def _feed_age_problem(age: datetime.timedelta) -> str | None:
    if age < datetime.timedelta(0):
        return "tick time is in the future"
    if age > FEED_STALE:
        return f"stale ({int(age.total_seconds())} s old, limit {int(FEED_STALE.total_seconds())} s)"
    return None


def _label(source: str, at: datetime.datetime, skipped: list[tuple[str, str]]) -> str:
    """Source and time, plus why each better source was not used (a fallback never hides that it is one)."""
    when = at.strftime("%d %b %Y %H:%M:%S") if source != SOURCE_LAST_CLOSE else at.strftime("%d %b %Y %H:%M")
    return f"{source}, {when}" + "".join(f" ({n}: {w})" for n, w in skipped)


def resolve_spot(feed: SourceReading | None, rest: SourceReading | None, last_close: SourceReading | None, *,
                 now: datetime.datetime) -> SpotAnswer:
    """Feed -> REST quote -> last close; the first usable one is returned, labelled with its source and time."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    reasons: list[tuple[str, str]] = []
    for name, reading in zip(SOURCE_ORDER, (feed, rest, last_close), strict=True):
        why = _why_not(name, reading, now)
        if why is None:
            assert reading is not None and reading.at is not None  # noqa: S101 - narrowed by _why_not
            return SpotAnswer(reading.value, name, reading.at, _label(name, reading.at, reasons), tuple(reasons))
        reasons.append((name, why))
    return SpotAnswer(None, None, None, SPOT_NOT_AVAILABLE, tuple(reasons))
