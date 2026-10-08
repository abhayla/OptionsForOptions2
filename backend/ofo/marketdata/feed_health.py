"""Quote health that follows the FEED's state, not a contract's own age (W-059; F-32, finding
``staleness-by-last-change-age``).

RCA: ``health.evaluate_health`` marks a quote stale when its timestamp is older than ``stale_after`` (60 s), but a
change-only feed (Kite) sends nothing for a contract that has not changed. On 2026-10-08 the feed was never quiet for
more than 0.51 s while a median 59 of 1,091 contracts had no tick for over 60 s, so a healthy chain read as stale.

Rule here: while a feed is connected and a data frame or heartbeat arrived within ``FEED_STALE`` every contract on it
is available; beyond that every contract of that feed is stale; disconnected longer than the reconnect window, never
connected, or session ended: unavailable. A contract's own last change time is kept (``QuoteBook``) as information
and is never a health input. Provider-agnostic: any provider with a live connection can use ``FeedState``.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

#: about 6x the longest market-hours gap measured on the feed (0.51 s, F-32). orchestrator default, not a spec number.
FEED_STALE = datetime.timedelta(seconds=3)
#: how long a dropped connection may be trying to reconnect before its quotes are unavailable (backoff caps at 30 s).
RECONNECT_WINDOW = datetime.timedelta(seconds=30)


class FeedState:
    """Connection and activity of ONE feed. Times are passed in (no clock here)."""

    def __init__(self, *, feed_stale: datetime.timedelta = FEED_STALE,
                 reconnect_window: datetime.timedelta = RECONNECT_WINDOW) -> None:
        self.feed_stale = feed_stale
        self.reconnect_window = reconnect_window
        self.connected = False
        self.session_ended = False
        self._last_activity: datetime.datetime | None = None
        self._disconnected_at: datetime.datetime | None = None

    def on_connected(self, now: datetime.datetime) -> None:
        self.connected = True
        self._disconnected_at = None
        self._last_activity = now  # a fresh connection starts the 'something must arrive' clock

    def on_activity(self, now: datetime.datetime) -> None:
        """A data frame or a heartbeat arrived."""
        self._last_activity = now

    def on_disconnected(self, now: datetime.datetime) -> None:
        self.connected = False
        self._disconnected_at = now

    def on_session_ended(self, now: datetime.datetime) -> None:
        self.connected = False
        self.session_ended = True
        self._disconnected_at = now

    def health(self, now: datetime.datetime) -> DataHealth:
        if self.session_ended:
            return DataHealth.UNAVAILABLE
        if not self.connected:
            if self._disconnected_at is None:
                return DataHealth.UNAVAILABLE  # never connected
            return (DataHealth.STALE if now - self._disconnected_at <= self.reconnect_window
                    else DataHealth.UNAVAILABLE)
        if self._last_activity is None or now - self._last_activity > self.feed_stale:
            return DataHealth.STALE
        return DataHealth.AVAILABLE


def with_feed_health(quote: NormalizedQuote, feed: DataHealth) -> NormalizedQuote:
    """The quote with its health from the feed's state; its own validation and declared delay still count."""
    if feed is not DataHealth.AVAILABLE:
        health = feed
    elif quote.validation_errors:
        health = DataHealth.UNHEALTHY
    elif quote.source.declared_delay_seconds > Decimal("0"):
        health = DataHealth.DELAYED
    else:
        health = DataHealth.AVAILABLE
    return dataclasses.replace(quote, health=health)


@dataclass(frozen=True)
class BookEntry:
    quote: NormalizedQuote
    last_changed_at: datetime.datetime  # information only; never a health input


class QuoteBook:
    """The latest quote per instrument, with the feed's health applied when read."""

    def __init__(self, feed: FeedState) -> None:
        self.feed = feed
        self._entries: dict[str, BookEntry] = {}

    def update(self, quote: NormalizedQuote) -> None:
        self._entries[quote.instrument_id] = BookEntry(quote, quote.timestamp)

    def __len__(self) -> int:
        return len(self._entries)

    def last_changed_at(self, instrument_id: str) -> datetime.datetime | None:
        e = self._entries.get(instrument_id)
        return e.last_changed_at if e else None

    def get(self, instrument_id: str, now: datetime.datetime) -> NormalizedQuote | None:
        e = self._entries.get(instrument_id)
        return with_feed_health(e.quote, self.feed.health(now)) if e else None

    def quotes(self, now: datetime.datetime) -> list[NormalizedQuote]:
        health = self.feed.health(now)
        return [with_feed_health(e.quote, health) for e in self._entries.values()]
