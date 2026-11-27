"""Quote health that follows the FEED's state, not a contract's own age (W-059; F-32, finding
``staleness-by-last-change-age``).

RCA: ``health.evaluate_health`` marks a quote stale when its timestamp is older than ``stale_after`` (60 s), but a
change-only feed (Kite) sends nothing for a contract that has not changed. On 2026-10-08 the feed was never quiet for
more than 0.51 s while a median 59 of 1,091 contracts had no tick for over 60 s, so a healthy chain read as stale.

Rule here: while a feed is connected and a data frame or heartbeat arrived within ``FEED_STALE`` every contract on it
is available; beyond that every contract of that feed is stale; disconnected longer than the reconnect window, never
connected, or session ended: unavailable. A contract's own last change time is kept (``QuoteBook``) as information
and is never a health input, except the ONE index rule of ADR-330 (39) (``FeedState.quote_health``): in market hours an
index quote older than ``index_quote_max_age`` is STALE even on a live feed. Provider-agnostic: any provider with a
live connection can use ``FeedState``.

Outside market hours (ADR-119 calendar, REQ-114 AC-7) the feed is never live, whatever frames arrive: ``health`` is
STALE and ``phase`` is ``FEED_MARKET_CLOSED`` (a session ended or a capped socket still say so). The calendar is read
HERE, the one quote-health path, so every quote, answer and screen built on a ``FeedState`` inherits it (class
market-state-decided-per-surface); a date the calendar cannot answer reads closed (``is_market_open`` fails closed).
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ofo.engine.executable_price import Depth
from ofo.market_calendar import is_market_open, last_close, price_time
from ofo.marketdata.provider import (
    FEED_NOT_HEALTHY,
    NOT_HELD,
    PACKET_WITHOUT_DAY_FIELDS,
    DayStats,
    DayStatsAnswer,
)
from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedWindows:
    """The two feed-health windows in force (REQ-167 AC-5 "Detection (feed stale and reconnect windows)"): ``stale`` =
    how long a feed may be silent before its quotes read STALE (``detection.feed_stale_seconds``, about 6x the longest
    market-hours gap measured, F-32); ``reconnect`` = how long a dropped connection may be trying to reconnect before
    its quotes are UNAVAILABLE (``detection.feed_reconnect_window_seconds``). The numbers are written only in
    ``registry.json``; ``ofo.settings.calc.feed_windows`` builds this from the settings read."""

    stale: datetime.timedelta
    reconnect: datetime.timedelta
    #: ADR-330 (39): in market hours an INDEX quote older than this is not live, whatever the feed as a whole says
    #: (``detection.index_quote_max_age_seconds``; written only in ``registry.json``).
    index_quote_max_age: datetime.timedelta


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
#: outside market hours (ADR-119 calendar, REQ-114 AC-7): silence is expected, so the feed reads "market closed - last
#: price <time>" (``ofo.marketdata.disconnect.market_closed_message``), never "waiting" or "reconnecting".
FEED_MARKET_CLOSED = "market_closed"


class FeedState:
    """Connection and activity of ONE feed. Times are passed in (no clock here). ``market_open`` is the ADR-119
    calendar's answer for a time (tests inject one; production reads ``market_calendar.is_market_open``)."""

    def __init__(self, *, windows: FeedWindows,
                 market_open: Callable[[datetime.datetime], bool] = is_market_open) -> None:
        self.windows = windows
        self._market_open = market_open
        self.connected = False
        self.session_ended = False
        self.capped = False
        self._last_activity: datetime.datetime | None = None
        self._last_tick_frame: datetime.datetime | None = None  # a PRICE frame only; heartbeats never move it (``phase``)
        self._disconnected_at: datetime.datetime | None = None
        self._awaiting_data = False  # connected again but no data frame yet: old quotes are not current
        self._connected_at: datetime.datetime | None = None  # when the current connection opened (REQ-133 AC-3)
        self._last_logged_health: DataHealth | None = None  # diagnostic: last health written to the log
        #: diagnostic (no route): how many times the feed-wide health changed, per reason category
        self.health_changes: dict[str, int] = {}

    def apply_windows(self, windows: FeedWindows) -> None:
        """The windows in force NOW (REQ-167 AC-4): every judgement below reads ``self.windows`` when it runs, so a
        changed setting changes the next verdict with no restart. Called with each settings read of a request or tick
        (``outcome.ctx_in_force``)."""
        self.windows = windows

    @property
    def feed_stale(self) -> datetime.timedelta:
        return self.windows.stale

    @property
    def reconnect_window(self) -> datetime.timedelta:
        return self.windows.reconnect

    def on_connected(self, now: datetime.datetime) -> None:
        self.connected = True
        self._disconnected_at = None
        self._connected_at = now
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

    @property
    def last_price_at(self) -> datetime.datetime | None:
        """When the last PRICE frame arrived (a heartbeat is not a price); None if none ever did."""
        return self._last_tick_frame

    def market_closed(self, now: datetime.datetime) -> bool:
        """REQ-114 AC-7: the ADR-119 calendar says the market is not open at ``now`` (closed, or a date it cannot
        answer: fail closed). The ONE market-state answer every quote health, feed phase and price answer reads."""
        return self._market_open(now) is not True

    def phase(self, now: datetime.datetime) -> str:
        """One of ``FEED_HEALTHY / WAITING / RECONNECTING / ENDED / CAPPED / MARKET_CLOSED``. A closed market
        (``market_closed``) reads ``FEED_MARKET_CLOSED`` (REQ-114 AC-7) whatever frames arrive, unless the session
        ended or the feed is capped, which still say so. ``healthy`` only when a PRICE frame arrived within
        ``feed_stale``: heartbeats (1 byte, every second) prove the link, never prices, so they cannot keep it healthy
        (unlike ``health``, which a quiet contract may keep AVAILABLE on heartbeats, F-32)."""
        if self.session_ended:
            return FEED_ENDED
        if self.capped:
            return FEED_CAPPED
        if self.market_closed(now):
            return FEED_MARKET_CLOSED
        if not self.connected:
            return FEED_RECONNECTING
        fresh = self._last_tick_frame is not None and now - self._last_tick_frame <= self.feed_stale
        return FEED_HEALTHY if fresh and not self._awaiting_data else FEED_WAITING

    def awaiting_first_price(self, now: datetime.datetime) -> bool:
        """REQ-133 AC-3: connected (or reconnected) and no price frame yet, still inside ``feed_stale`` (the one
        staleness limit) of the connection opening. Then the screen waits for its first price; past the limit with no
        frame, the quotes read STALE as before (the alarm). A closed market, an ended session or a capped feed never
        waits: they say so."""
        if self.session_ended or self.capped or not self.connected or not self._awaiting_data:
            return False
        if self._connected_at is None or self.market_closed(now):
            return False
        return now - self._connected_at <= self.feed_stale

    def _not_connected(self, now: datetime.datetime) -> tuple[DataHealth, str, float]:
        if self._disconnected_at is None:
            return DataHealth.UNAVAILABLE, "never_connected", 0.0
        gone = now - self._disconnected_at
        health = DataHealth.STALE if gone <= self.reconnect_window else DataHealth.UNAVAILABLE
        return health, "disconnected", gone.total_seconds()

    def _health_and_reason(self, now: datetime.datetime) -> tuple[DataHealth, str, float]:
        """(health, reason category, seconds that belong to it) in ONE place; ``health`` returns the first and logs
        changes. Categories are single words/keys; their log text sits in ``_log_change`` (log text is not a
        user-facing producer)."""
        if self.session_ended:
            return DataHealth.UNAVAILABLE, "session_ended", 0.0
        if self.market_closed(now):
            # REQ-114 AC-7 / ADR-015: a closed market's last price is never shown as live
            return DataHealth.STALE, "market_closed", 0.0
        if not self.connected:
            return self._not_connected(now)
        if self._awaiting_data:
            return DataHealth.STALE, "awaiting_data", 0.0
        if self._last_activity is None or now - self._last_activity > self.feed_stale:
            quiet = 0.0 if self._last_activity is None else (now - self._last_activity).total_seconds()
            return DataHealth.STALE, "no_feed_activity", quiet
        return DataHealth.AVAILABLE, "live", 0.0

    def _log_change(self, old: str, new: str, category: str, seconds: float) -> None:
        if category == "session_ended":
            log.info("feed health %s -> %s: session ended", old, new)
        elif category == "market_closed":
            log.info("feed health %s -> %s: market closed", old, new)
        elif category == "never_connected":
            log.info("feed health %s -> %s: never connected", old, new)
        elif category == "disconnected":
            log.info("feed health %s -> %s: disconnected %.1f s ago", old, new, seconds)
        elif category == "awaiting_data":
            log.info("feed health %s -> %s: awaiting data after (re)connect", old, new)
        elif category == "no_feed_activity":
            log.info("feed health %s -> %s: no feed activity for %.1f s (limit %.1f s)", old, new, seconds,
                     self.feed_stale.total_seconds())
        else:
            log.info("feed health %s -> %s: live", old, new)

    def health(self, now: datetime.datetime) -> DataHealth:
        health, category, seconds = self._health_and_reason(now)
        if health is not self._last_logged_health:
            old = "none" if self._last_logged_health is None else self._last_logged_health.name
            self._log_change(old, health.name, category, seconds)
            self._last_logged_health = health
            self.health_changes[category] = self.health_changes.get(category, 0) + 1
        return health

    def quote_health(self, quote: NormalizedQuote, now: datetime.datetime) -> DataHealth:
        """ADR-330 (39), the ONE per-quote age rule: the feed's health, except that in market hours an index quote
        (``instrument_type`` None) whose own time is older than ``index_quote_max_age`` is STALE even while the feed
        as a whole is live (F-32: option frames keep arriving while the index sat silent). Options keep the feed's
        word (a quiet contract is not stale). Closed market: the feed already says STALE; ADR-330 (36) applies."""
        health = self.health(now)
        if (health is DataHealth.AVAILABLE and quote.instrument_type is None
                and now - quote.timestamp > self.windows.index_quote_max_age):
            return DataHealth.STALE
        return health


def market_closed_for(source: object, now: datetime.datetime) -> bool:
    """REQ-114 AC-7: the ONE market-state answer for ANY provider shape. A provider (or relay) with a
    ``FeedState`` answers through ``FeedState.market_closed`` (the same answer its quote healths read); one without
    (the bus-mode ``FeedRelay``, a test fake, no provider at all) gets the calendar ``FeedState`` defaults to
    (fail closed)."""
    closed = getattr(getattr(source, "feed", None), "market_closed", None)
    return (not is_market_open(now)) if closed is None else bool(closed(now))


def awaiting_first_price_for(source: object, now: datetime.datetime) -> bool:
    """REQ-133 AC-3 for ANY provider shape: a provider with a ``FeedState`` answers through
    ``FeedState.awaiting_first_price``; one without (a relay, a test fake, no provider) never waits."""
    waiting = getattr(getattr(source, "feed", None), "awaiting_first_price", None)
    return False if waiting is None else waiting(now) is True


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
class Frame:
    """One packet's quote, depth and day values (the three always travel together), and ``spell``: the calendar close
    (``last_close``) of the closed spell it is the figure for; None when it is not tied to one."""

    quote: NormalizedQuote
    depth: Depth | None = None
    day_stats: DayStats | None = None
    spell: datetime.datetime | None = None


@dataclass(frozen=True)
class BookEntry:
    quote: NormalizedQuote
    last_changed_at: datetime.datetime  # information only; never a health input
    # the 5+5 levels of the SAME full frame as ``quote`` (its exchange time is ``quote.timestamp``); None when the last
    # packet carried no depth (quote / ltp mode) - never an empty Depth, which would read as "no liquidity"
    depth: Depth | None = None
    day_stats: DayStats | None = None  # the day values of the SAME packet; None when it carried none
    #: ADR-330 (36): the NEWEST quote made by the close (in session or exactly at the close) with its depth and day
    #: values; a frame stamped earlier that arrives late never replaces it.
    close_quote: NormalizedQuote | None = None
    close_depth: Depth | None = None
    close_day_stats: DayStats | None = None
    #: the FIRST frame received after a close (its ``spell`` = that close), kept while the contract has no frame made by
    #: the close (a restart after 15:30, a strike first opened after hours); a later frame never replaces it.
    after: Frame | None = None
    #: the figure SERVED while the market is closed, with its spell: once shown it never moves until the next open.
    served: Frame | None = None


def made_by_the_close(quote: NormalizedQuote) -> bool:
    """ADR-330 (36): the ONE cut-off. True when the quote's time is at or before the close of its trading day: inside
    the session or exactly at the close. A frame after the close, before the open, or on a holiday or weekend is not
    (``price_time`` puts it at an earlier close). A date the calendar cannot answer cannot be cut: True, as before."""
    made = price_time(quote.timestamp)
    return made is None or made >= quote.timestamp


def _on(t: datetime.datetime, close: datetime.datetime) -> bool:
    """True when ``t`` is on the calendar day of ``close`` (IST) and at or before it: a frame of that trading day made
    by its close, including one received before the open."""
    return t <= close and t.astimezone(close.tzinfo).date() == close.date()


def _figure(e: BookEntry, close: datetime.datetime) -> Frame:
    """THE ONE RULE (Lane N A2, ADR-330 (36), ADR-212): the figure of a closed spell ending at ``close``, used by every
    read (price, depth, day values). In order: (0) the figure already served for this spell; (1) the latest frame if it
    was made by this close on this day (a pre-open frame of the day counts); (2) the newest frame made by this day's
    close; (3) the first frame received after this close; (4) none of those: the figure of the contract's own last
    close (an earlier session's, kept with its own date-time). The caller stores the answer as ``served``, so (4) is
    frozen at its first read and a later frame never replaces it."""
    if e.served is not None and e.served.spell == close:
        return e.served
    held = e.close_quote is not None and _on(e.close_quote.timestamp, close)
    if _on(e.quote.timestamp, close) and not (held and e.quote.timestamp < e.close_quote.timestamp):  # type: ignore[union-attr]
        return Frame(e.quote, e.depth, e.day_stats, close)  # a late older-stamped frame never beats the newer close
    if held:
        return Frame(e.close_quote, e.close_depth, e.close_day_stats, close)
    if e.after is not None and e.after.spell == close:
        return e.after
    own = last_close(e.quote.timestamp)
    if own is not None and own < close:
        return _figure(e, own)
    return Frame(e.quote, e.depth, e.day_stats, close)


def _next_entry(previous: BookEntry | None, quote: NormalizedQuote, depth: Depth | None,
                day_stats: DayStats | None) -> BookEntry:
    """The entry once ``quote`` arrives: the latest frame, the newest made-by-the-close frame, the first frame after
    each close, and whatever was already served (kept)."""
    close_q, close_d, close_s = (None, None, None) if previous is None else (
        previous.close_quote, previous.close_depth, previous.close_day_stats)
    after = None if previous is None else previous.after
    if made_by_the_close(quote):
        if close_q is None or quote.timestamp >= close_q.timestamp:
            close_q, close_d, close_s = quote, depth, day_stats
    else:
        spell = last_close(quote.timestamp)
        if after is None or after.spell != spell:
            after = Frame(quote, depth, day_stats, spell)
    return BookEntry(quote, quote.timestamp, depth, day_stats, close_q, close_d, close_s, after,
                     None if previous is None else previous.served)


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

    def update_parked(self, quote: NormalizedQuote, depth: Depth | None = None,
                      day_stats: DayStats | None = None) -> bool:
        """A tick for a released instrument whose unsubscribe is not out yet: kept for ``restore``, never readable.
        False when the instrument is not parked."""
        if quote.instrument_id not in self._parked:
            return False
        self._parked[quote.instrument_id] = _next_entry(self._parked[quote.instrument_id], quote, depth, day_stats)
        return True

    def update(self, quote: NormalizedQuote, depth: Depth | None = None, day_stats: DayStats | None = None) -> None:
        parked = self._parked.pop(quote.instrument_id, None)
        self._ended_times.pop(instrument_id := quote.instrument_id, None)  # held again: the quote itself speaks
        self._entries[instrument_id] = _next_entry(self._entries.get(instrument_id) or parked, quote, depth, day_stats)

    def __len__(self) -> int:
        return len(self._entries)

    def last_changed_at(self, instrument_id: str) -> datetime.datetime | None:
        e = self._entries.get(instrument_id)
        return e.last_changed_at if e else None

    def get(self, instrument_id: str, now: datetime.datetime) -> NormalizedQuote | None:
        e = self._entries.get(instrument_id)
        if not e:
            return None
        served = self._frame(instrument_id, e, now).quote
        return with_feed_health(served, self.feed.quote_health(served, now))

    def _frame(self, instrument_id: str, e: BookEntry, now: datetime.datetime) -> Frame:
        """ADR-330 (36), the one place a read picks the frame: in market hours the latest; while closed ``_figure``,
        stored as ``served`` the first time so what was shown never moves until the next open."""
        if not self.feed.market_closed(now):
            return Frame(e.quote, e.depth, e.day_stats)
        close = last_close(now)
        if close is None:  # the calendar cannot answer: the newest frame made by the close, else the latest (as before)
            if e.close_quote is None:
                return Frame(e.quote, e.depth, e.day_stats)
            return Frame(e.close_quote, e.close_depth, e.close_day_stats)
        frame = _figure(e, close)
        if e.served is None or e.served.spell != close:
            self._entries[instrument_id] = dataclasses.replace(e, served=dataclasses.replace(frame, spell=close))
        return frame

    def latest_depth(self, instrument_id: str, now: datetime.datetime) -> Depth | None:
        """The 5-level depth of the instrument's latest packet, or None: not held (never seen, removed or parked), the
        latest packet was not a full frame, or the quote is not AVAILABLE (feed stale / disconnected / ended, or the
        quote itself invalid or delayed). Health is ``FeedState.quote_health``: the feed's word, so an option's own
        age is not a limit (a quiet contract keeps its depth, F-32); an index quote older than the index age limit is
        not AVAILABLE (ADR-330 (39)). Lane N A2: an ORDER input, so it reads the latest frame and only while the
        market is open; closed, the health is STALE and it is None (never a price from a frame the screen hides)."""
        e = self._entries.get(instrument_id)
        if e is None or e.depth is None:
            return None
        quote = with_feed_health(e.quote, self.feed.quote_health(e.quote, now))
        return e.depth if quote.health is DataHealth.AVAILABLE else None

    def depth_after_close(self, instrument_id: str,
                          now: datetime.datetime) -> tuple[Depth | None, DayStats | None] | None:
        """READ-ONLY display (REQ-080 AC-7, ADR-200 (1)): outside market hours, the depth and day values of the frame
        ``get`` serves (the at-close or first-after-close frame, ADR-330 (36)), held for a sound quote
        (``quote.planning_price_usable``), or None (market open, not held, or the quote
        not sound). NEVER an order input: the Execute price reads ``latest_depth``, which stays AVAILABLE-only."""
        from ofo.marketdata.quote import planning_price_usable  # noqa: PLC0415 - one rule, read where it is used
        e = self._entries.get(instrument_id)
        if e is None or not self.feed.market_closed(now):
            return None
        # the SAME frame ``get`` serves (``_frame``): a depth price never comes from a later frame than the quote's
        frame = self._frame(instrument_id, e, now)
        if not planning_price_usable(with_feed_health(frame.quote, self.feed.health(now)), market_closed=True):
            return None
        return frame.depth, frame.day_stats

    def latest_day_stats(self, instrument_id: str, now: datetime.datetime) -> DayStatsAnswer:
        """The day values of the instrument's latest packet, or the reason there are none: not held (never seen,
        removed or parked), the quote is not AVAILABLE (the feed's health, as for depth), or the latest packet was an
        ltp packet (or a zero index packet) that carries no day fields. Lane N A2: closed market -> FEED_NOT_HEALTHY
        (STALE), so no day value of a later frame shows; the closed-market display reads ``depth_after_close``."""
        e = self._entries.get(instrument_id)
        if e is None:
            return DayStatsAnswer.unavailable(NOT_HELD)
        if with_feed_health(e.quote, self.feed.quote_health(e.quote, now)).health is not DataHealth.AVAILABLE:
            return DayStatsAnswer.unavailable(FEED_NOT_HEALTHY)
        if e.day_stats is None:
            return DayStatsAnswer.unavailable(PACKET_WITHOUT_DAY_FIELDS)
        return DayStatsAnswer(e.day_stats)

    def quotes(self, now: datetime.datetime) -> list[NormalizedQuote]:
        served = [self._frame(iid, e, now).quote for iid, e in list(self._entries.items())]
        return [with_feed_health(q, self.feed.quote_health(q, now)) for q in served]
