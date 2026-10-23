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

from ofo.engine.executable_price import Depth
from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

#: about 6x the longest market-hours gap measured on the feed (0.51 s, F-32). orchestrator default, not a spec number.
FEED_STALE = datetime.timedelta(seconds=3)
#: how long a dropped connection may be trying to reconnect before its quotes are unavailable (backoff caps at 30 s).
RECONNECT_WINDOW = datetime.timedelta(seconds=30)
#: most instruments whose last quote TIME is kept after unsubscribe (oldest removal evicted first). A time is a few
#: dozen bytes; one day's NIFTY+SENSEX chains are about 1-2 thousand contracts, so 20,000 covers many days of churn.
MAX_KEPT_TIMES = 20_000


#: What the live feed is doing, in closed words (REQ-015 AC-4 live row, REQ-049 window): ``healthy`` = connected and
#: a price frame inside ``feed_stale``; ``waiting`` = connected but no price frame yet (a heartbeat alone proves
#: nothing about prices) or frames stopped beyond ``feed_stale``; ``reconnecting`` = not connected (backoff, or never
#: connected); ``ended`` = the Zerodha session ended (403).
FEED_HEALTHY, FEED_WAITING, FEED_RECONNECTING, FEED_ENDED = "healthy", "waiting", "reconnecting", "ended"
#: connected with nothing subscribed (the caller knows the subscriptions): nothing is expected to arrive.
FEED_IDLE = "idle"
#: the feed refused this user's socket over Zerodha's connection cap (REQ-113 AC-6, ADR-170): no prices will arrive.
FEED_CAPPED = "capped"


class FeedState:
    """Connection and activity of ONE feed. Times are passed in (no clock here)."""

    def __init__(self, *, feed_stale: datetime.timedelta = FEED_STALE,
                 reconnect_window: datetime.timedelta = RECONNECT_WINDOW) -> None:
        self.feed_stale = feed_stale
        self.reconnect_window = reconnect_window
        self.connected = False
        self.session_ended = False
        self.capped = False
        self._last_activity: datetime.datetime | None = None
        self._last_tick_frame: datetime.datetime | None = None  # a PRICE frame only; heartbeats never move it (``phase``)
        self._disconnected_at: datetime.datetime | None = None
        self._awaiting_data = False  # connected again but no data frame yet: old quotes are not current

    def on_connected(self, now: datetime.datetime) -> None:
        self.connected = True
        self._disconnected_at = None
        self._last_activity = now  # a fresh connection starts the 'something must arrive' clock
        self._awaiting_data = True

    def on_activity(self, now: datetime.datetime) -> None:
        """A heartbeat arrived: the link is alive, but it proves nothing about prices."""
        self._last_activity = now

    def on_data(self, now: datetime.datetime) -> None:
        """A well-formed data frame with at least one tick arrived: quotes are current again."""
        self._last_activity = now
        self._last_tick_frame = now
        self._awaiting_data = False

    def on_disconnected(self, now: datetime.datetime) -> None:
        """Only the connected -> disconnected transition starts the outage clock; a failed retry must not restart it."""
        if self.connected:
            self.connected = False
            self._disconnected_at = now

    def on_session_ended(self, now: datetime.datetime) -> None:
        self.connected = False
        self.session_ended = True
        self._disconnected_at = now

    def set_capped(self, capped: bool) -> None:
        """The feed's own word that it refused this user's socket over a Zerodha cap (read from its status)."""
        self.capped = capped

    def phase(self, now: datetime.datetime) -> str:
        """One of ``FEED_HEALTHY / WAITING / RECONNECTING / ENDED``. ``healthy`` only when a PRICE frame arrived within
        ``feed_stale``: heartbeats (1 byte, every second) prove the link, never prices, so they cannot keep it healthy
        (unlike ``health``, which a quiet contract may keep AVAILABLE on heartbeats, F-32)."""
        if self.session_ended:
            return FEED_ENDED
        if self.capped:
            return FEED_CAPPED
        if not self.connected:
            return FEED_RECONNECTING
        fresh = self._last_tick_frame is not None and now - self._last_tick_frame <= self.feed_stale
        return FEED_HEALTHY if fresh and not self._awaiting_data else FEED_WAITING

    def health(self, now: datetime.datetime) -> DataHealth:
        if self.session_ended:
            return DataHealth.UNAVAILABLE
        if not self.connected:
            if self._disconnected_at is None:
                return DataHealth.UNAVAILABLE  # never connected
            return (DataHealth.STALE if now - self._disconnected_at <= self.reconnect_window
                    else DataHealth.UNAVAILABLE)
        if self._awaiting_data or self._last_activity is None or now - self._last_activity > self.feed_stale:
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
    # the 5+5 levels of the SAME full frame as ``quote`` (its exchange time is ``quote.timestamp``); None when the last
    # packet carried no depth (quote / ltp mode) - never an empty Depth, which would read as "no liquidity"
    depth: Depth | None = None


class QuoteBook:
    """The latest quote per instrument, with the feed's health applied when read."""

    def __init__(self, feed: FeedState) -> None:
        self.feed = feed
        self._entries: dict[str, BookEntry] = {}
        self._ended_times: dict[str, datetime.datetime] = {}  # times only, never a price
        # released but the vendor not yet told: unreadable, restored if taken again before the send (gate 4a D-1)
        self._parked: dict[str, BookEntry] = {}

    def remove(self, instrument_id: str) -> None:
        """Drop the quote (no stale price outlives its subscription, REQ-049 AC-4) but keep its TIME only (ADR-077:
        "The platform keeps each contract's last price TIME (never the price) after its subscription ends")."""
        self._parked.pop(instrument_id, None)
        self._end(instrument_id, self._entries.pop(instrument_id, None))

    def park(self, instrument_id: str) -> None:
        """Like ``remove`` (unreadable at once, time kept), but the quote can come back with ``restore`` while the
        vendor subscription was never actually dropped: a quiet contract would otherwise read 'no price' until it
        next changes."""
        entry = self._entries.pop(instrument_id, None)
        if entry is not None:
            self._parked[instrument_id] = entry
        self._end(instrument_id, entry)

    def restore(self, instrument_id: str) -> None:
        entry = self._parked.pop(instrument_id, None)
        if entry is not None and instrument_id not in self._entries:
            self._entries[instrument_id] = entry
            self._ended_times.pop(instrument_id, None)

    def parked_ids(self) -> list[str]:
        return list(self._parked)

    def forget_parked(self, instrument_id: str) -> None:
        """The vendor was told to drop it: the parked quote can never come back (its time stays kept)."""
        self._parked.pop(instrument_id, None)

    def _end(self, instrument_id: str, entry: BookEntry | None) -> None:
        if entry is None:
            return
        self._ended_times.pop(instrument_id, None)
        self._ended_times[instrument_id] = entry.quote.timestamp  # newest removal last
        while len(self._ended_times) > MAX_KEPT_TIMES:  # bounded: oldest removal evicted first
            del self._ended_times[next(iter(self._ended_times))]

    def ended_time(self, instrument_id: str) -> datetime.datetime | None:
        """The time of the last quote held for an instrument whose subscription ended; None if none was kept."""
        return self._ended_times.get(instrument_id)

    def update_parked(self, quote: NormalizedQuote, depth: Depth | None = None) -> bool:
        """A tick for a released instrument whose unsubscribe is not out yet: kept for ``restore``, never readable.
        False when the instrument is not parked."""
        if quote.instrument_id not in self._parked:
            return False
        self._parked[quote.instrument_id] = BookEntry(quote, quote.timestamp, depth)
        return True

    def update(self, quote: NormalizedQuote, depth: Depth | None = None) -> None:
        self._parked.pop(quote.instrument_id, None)
        self._ended_times.pop(instrument_id := quote.instrument_id, None)  # held again: the quote itself speaks
        self._entries[instrument_id] = BookEntry(quote, quote.timestamp, depth)

    def __len__(self) -> int:
        return len(self._entries)

    def last_changed_at(self, instrument_id: str) -> datetime.datetime | None:
        e = self._entries.get(instrument_id)
        return e.last_changed_at if e else None

    def get(self, instrument_id: str, now: datetime.datetime) -> NormalizedQuote | None:
        e = self._entries.get(instrument_id)
        return with_feed_health(e.quote, self.feed.health(now)) if e else None

    def latest_depth(self, instrument_id: str, now: datetime.datetime) -> Depth | None:
        """The 5-level depth of the instrument's latest packet, or None: not held (never seen, removed or parked), the
        latest packet was not a full frame, or the quote is not AVAILABLE (feed stale / disconnected / ended, or the
        quote itself invalid or delayed). Staleness is the feed's (``FeedState``), the one limit the quote already
        uses; a contract's own age is never a limit (a quiet contract keeps its depth, F-32)."""
        e = self._entries.get(instrument_id)
        if e is None or e.depth is None:
            return None
        quote = with_feed_health(e.quote, self.feed.health(now))
        return e.depth if quote.health is DataHealth.AVAILABLE else None

    def quotes(self, now: datetime.datetime) -> list[NormalizedQuote]:
        health = self.feed.health(now)
        return [with_feed_health(e.quote, health) for e in self._entries.values()]
