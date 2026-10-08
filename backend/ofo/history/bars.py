"""One-minute bars built from the live quote stream (W-062, REQ-051 AC-3/AC-4, ADR-067). Standard library only.

A bar is provisional (``LIVE``) until Kite's own candle replaces it (``KITE``) or a feed gap is filled from Kite's
candles (``BACKFILLED``). Money is ``Decimal`` at every boundary; no float anywhere in this package.

Rules (F-34): bucket by the exchange timestamp of the quote; an index quote's ltp is a price point; an option moves
open/high/low/close only on a trade, a trade being a quote whose cumulative volume rose since that instrument's
previous usable quote; the bar's volume is the sum of those rises; OI is the last OI seen in the minute; a minute with
no trade yields no bar. The first usable quote of an instrument (and the first after an unusable one) only seeds the
cumulative volume.
"""
from __future__ import annotations

import datetime
import enum
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
ONE_MINUTE = datetime.timedelta(minutes=1)


class BarSource(enum.Enum):
    LIVE = "live"
    BACKFILLED = "backfilled"
    KITE = "kite"


def minute_of(moment: datetime.datetime) -> datetime.datetime:
    """The IST start of the minute containing ``moment`` (must be timezone-aware)."""
    if moment.tzinfo is None:
        raise ValueError("a bar minute needs a timezone-aware time")
    return moment.astimezone(IST).replace(second=0, microsecond=0)


@dataclass(frozen=True)
class MinuteBar:
    instrument_id: str
    minute: datetime.datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    oi: int | None
    source: BarSource

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise ValueError("instrument_id must be a non-empty string")
        if self.minute.tzinfo is None or self.minute != minute_of(self.minute):
            raise ValueError(f"minute must be a timezone-aware start of a minute, got {self.minute!r}")
        for name in ("open", "high", "low", "close"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal, got {value!r}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("a bar needs low <= open, close <= high")
        for name in ("volume", "oi"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative int or None, got {value!r}")
        if not isinstance(self.source, BarSource):
            raise ValueError(f"source must be a BarSource, got {self.source!r}")


class _Open:
    __slots__ = ("minute", "open", "high", "low", "close", "volume", "oi", "priced", "index")

    def __init__(self, minute: datetime.datetime, index: bool) -> None:
        self.minute = minute
        self.open = self.high = self.low = self.close = None
        self.volume = 0
        self.oi = None
        self.priced = False
        self.index = index

    def price(self, p: Decimal) -> None:
        if not self.priced:
            self.open = self.high = self.low = p
            self.priced = True
        else:
            self.high = max(self.high, p)
            self.low = min(self.low, p)
        self.close = p


#: a quiet spell across ALL subscribed instruments longer than this is a feed gap (the longest healthy quiet spell
#: measured on 2026-10-08 was 1.0 s with 8 instruments, 0.51 s with 1,091; the laptop outage was 114 s).
FEED_GAP_AFTER = datetime.timedelta(seconds=5)


class MinuteBarBuilder:
    def __init__(self, *, gap_after: datetime.timedelta = FEED_GAP_AFTER) -> None:
        self._gap_after = gap_after
        self._last_seen: datetime.datetime | None = None
        self.gaps: list[tuple[datetime.datetime, datetime.datetime]] = []
        self._open: dict[str, _Open] = {}
        self._cum_volume: dict[str, int | None] = {}  # None = reseed on the next usable quote
        self.counters: Counter = Counter()

    def on_quote(self, quote: NormalizedQuote) -> list[MinuteBar]:
        """Take one quote; return the bars it caused to close (at most one)."""
        iid = quote.instrument_id
        self._watch_feed(quote.timestamp)
        if quote.health is not DataHealth.AVAILABLE or quote.ltp is None:
            self.counters["unusable"] += 1
            self._cum_volume[iid] = None
            return []
        minute = minute_of(quote.timestamp)
        current = self._open.get(iid)
        closed: list[MinuteBar] = []
        if current is not None and minute < current.minute:
            self.counters["late"] += 1
            return []
        if current is None or minute > current.minute:
            if current is not None:
                closed = self._close(iid, current)
            current = self._open[iid] = _Open(minute, quote.instrument_type is None)
        if current.index:  # an index: every quote is a price point
            current.price(quote.ltp)
            return closed
        previous = self._cum_volume.get(iid)
        if quote.volume is not None:
            self._cum_volume[iid] = quote.volume
            if previous is not None and quote.volume > previous:
                current.price(quote.ltp)
                current.volume += quote.volume - previous
        if quote.oi is not None:
            current.oi = quote.oi
        return closed

    def mark_gap(self, start: datetime.datetime, end: datetime.datetime) -> None:
        """A feed gap (from the feed-state events or the quote timestamps): nothing seen across it can be a trade."""
        self.gaps.append((start, end))
        for iid in self._cum_volume:
            self._cum_volume[iid] = None

    def _watch_feed(self, ts: datetime.datetime) -> None:
        if self._last_seen is not None and ts - self._last_seen > self._gap_after:
            self.mark_gap(self._last_seen, ts)
        if self._last_seen is None or ts > self._last_seen:
            self._last_seen = ts

    def flush(self, now: datetime.datetime) -> list[MinuteBar]:
        """Close every open minute that ended at or before ``now``."""
        out: list[MinuteBar] = []
        for iid, current in list(self._open.items()):
            if current.minute + ONE_MINUTE <= now:
                out.extend(self._close(iid, current))
                del self._open[iid]
        return out

    @staticmethod
    def _close(iid: str, current: _Open) -> list[MinuteBar]:
        if not current.priced:
            return []  # no trade in the minute: no bar (Kite skips such minutes too)
        return [MinuteBar(iid, current.minute, current.open, current.high, current.low, current.close,
                          None if current.index else current.volume, current.oi, BarSource.LIVE)]
