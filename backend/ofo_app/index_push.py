"""The live NIFTY 50 / SENSEX push of the Underlying/index view (W-114; REQ-072 AC-2, REQ-049 AC-2/AC-4).
Framework-free.

One :class:`IndexPush` serves one browser connection of the read-only index socket. On connect it subscribes the two
index instruments (the catalogue's ``provider.index_id``) on the ONE shared fan-out (never a vendor connection per
browser), then at most once every ``MIN_PUSH_INTERVAL`` seconds, and only when a row's value, time or health (or the
state) changed since the last push, it sends :func:`indices_answer` - the same function the REST read returns. The first
push goes at once. When the connection ends, on every exit path, its subscription is released (``finally``).

Health is the quote's OWN health as the provider gives it (the same rule as option prices, REQ-072 AC-2), read at every
poll, so a feed that goes stale while no tick arrives still changes the row. No new staleness rule is added here:
per-instrument staleness is a known open gap (finding staleness-by-last-change-age). The client sends nothing this
socket needs: any client message is answered with one catalogue message (``user_input_request_invalid``) and changes
nothing. The REST read's ``fallback`` answer is not live whoever else holds the indices (finding
liveness-from-shared-subscribers): no number is ever sent as live from a page whose own socket is down.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
from collections.abc import Callable
from typing import Any, Literal

from ofo.errors import render
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo.marketdata.quote import is_live_price
from ofo.money import PAISE  # money leaves the API as a 2-decimal string

from ofo_app.api_models import ApiModel, InstrumentId, Money
from ofo_app.live_push import MIN_PUSH_INTERVAL, POLL_SECONDS, Channel, ChannelClosed, LiveFeed
from ofo_app.routes.outcome import HealthCode, MarketContext, label_time, market_state
from ofo_app.underlying import Underlying

#: The two indices of the view, in the order the message lists them (NIFTY then SENSEX).
UNDERLYINGS: tuple[str, ...] = tuple(SUPPORTED_UNDERLYINGS)


class IndexOut(ApiModel):
    underlying: Underlying
    instrument_id: InstrumentId | None  # (segment, exchange token), REQ-072 AC-1; None when the catalogue lacks it
    value: Money | None  # the last price as given (stale on a closed market); None: none, or socket not holding
    at: datetime.datetime | None  # the quote's own time (aware); kept in the not-live answer as "last value time"
    health: HealthCode | None  # the quote's own health; None in the not-live answer


class IndicesOut(ApiModel):
    state: Literal["LIVE", "NOT_CONNECTED"]
    indices: list[IndexOut]
    #: ADR-088: when the server produced THIS answer (aware)
    answered_at: datetime.datetime
    #: REQ-114 AC-7 / ADR-177: the market is closed at ``answered_at`` (the screen shows the one market-closed banner)
    market_closed: bool
    #: when the feed's last price frame arrived (None: none yet); the market-closed and reconnecting texts show it
    last_price_at: datetime.datetime | None


def index_ids(ctx: MarketContext) -> dict[str, str | None]:
    """The catalogue id of each index, None for one the catalogue does not know."""
    reader = getattr(ctx.provider, "index_id", lambda _u: None)
    return {u: reader(u) for u in UNDERLYINGS}


def _row(ctx: MarketContext, underlying: Underlying, instrument_id: str | None,
         held: bool, closed: bool) -> IndexOut:
    """One index row. ``held``: the page's socket holds the indices. ``closed``: the market is closed (the one
    market-state answer); the row then keeps the last value with its time and its stale health (REQ-072 AC-2 "a stale
    ... index value is shown as such"), while the answer's state is never LIVE (``indices_answer``)."""
    quote = None if instrument_id is None else ctx.provider.underlying_quote(underlying)
    if quote is not None and quote.instrument_id != instrument_id:  # never another instrument's quote as this index's
        quote = None
    at = None if quote is None else quote.timestamp
    if not held:  # not held: the last value time only, never a number from a socket that is down (REQ-049 AC-4)
        return IndexOut(underlying=underlying, instrument_id=instrument_id, value=None, at=at, health=None)
    if quote is None:  # unknown index or no quote: shown as unavailable, no number (REQ-072 AC-2 "missing ... as such")
        return IndexOut(underlying=underlying, instrument_id=instrument_id, value=None, at=None, health="unavailable")
    value = quote.ltp.quantize(PAISE) if is_live_price(quote.ltp) else None
    health = quote.health.value
    if closed and health == "available":  # fail closed: a closed market's value is never labelled available
        health = "stale"
    return IndexOut(underlying=underlying, instrument_id=instrument_id, value=value, at=at, health=health)


def indices_answer(ctx: MarketContext | None, *, live: bool,
                   now: Callable[[], datetime.datetime]) -> IndicesOut:
    """The ONE answer behind the REST read and the socket push. ``ctx`` None (no live feed): NOT_CONNECTED, every value
    null. ``live`` False (the page's own socket is down, or nothing holds the indices): NOT_CONNECTED with each
    index's last value time kept. Market closed while held: NOT_CONNECTED, each row's last value kept as stale."""
    if ctx is None:
        rows = [IndexOut(underlying=u, instrument_id=None, value=None, at=None, health=None) for u in UNDERLYINGS]
        answered_at = now()
        state = market_state(None, answered_at)
        return IndicesOut(state="NOT_CONNECTED", indices=rows, answered_at=answered_at, market_closed=state.closed,
                          last_price_at=state.last_price_at)
    answered_at = ctx.clock()
    state = market_state(ctx, answered_at)
    # ADR-015 / REQ-114 AC-7: the ONE place the index answer decides "live" - held by the page's socket AND the market
    # open by the one market-state answer. A closed market (weekend, holiday, after hours, past the calendar) is never
    # LIVE: the not-live answer, each row's last value kept as stale with its time, the market-closed banner shown.
    shown_live = live and not state.closed
    rows = [_row(ctx, u, i, live, state.closed) for u, i in index_ids(ctx).items()]
    # ADR-200 (4): closed, the banner's time is the index quotes' own last-price time, never a reconnect frame's
    return IndicesOut(state="LIVE" if shown_live else "NOT_CONNECTED", indices=rows, answered_at=answered_at,
                      market_closed=state.closed, last_price_at=label_time(state, (r.at for r in rows)))


def _shown_state(body: IndicesOut) -> tuple:
    """What the page shows: the state and each row (never ``answered_at``, which moves on every read)."""
    return (body.state, body.market_closed, body.last_price_at,
            tuple((r.underlying, r.instrument_id, r.value, r.at, r.health) for r in body.indices))


def _ignore(_quote: Any) -> None:
    """The fan-out listener: the push reads the provider's current quote (with its health at this moment) each poll, so
    the queued ticks only need draining."""


class IndexPush:
    def __init__(self, channel: Channel, feed: LiveFeed | None, *, monotonic: Callable[[], float],
                 now: Callable[[], datetime.datetime], poll: float = POLL_SECONDS) -> None:
        self._channel = channel
        self._feed = feed
        self._monotonic = monotonic
        self._now = now
        self._poll = poll
        self._handle: int | None = None
        self._live = False
        self._shown: tuple | None = None
        self._last_push: float | None = None
        self.pushes = 0

    def _subscribe(self) -> None:
        if self._feed is None:
            return
        ids = [i for i in index_ids(self._feed.ctx).values() if i is not None]
        if not ids:
            return
        try:
            self._handle = self._feed.fanout.subscribe(_ignore, ids)
        except KeyError:  # an id the provider does not know: nothing was subscribed, and nothing is shown as live
            self._handle = None
            return
        self._live = True

    def _release(self) -> None:
        if self._handle is not None and self._feed is not None:
            self._feed.fanout.unsubscribe(self._handle)
        self._handle = None
        self._live = False

    def _answer(self) -> IndicesOut:
        ctx = None if self._feed is None else self._feed.ctx
        return indices_answer(ctx, live=self._live, now=self._now)

    async def _maybe_push(self) -> None:
        if self._last_push is not None and self._monotonic() - self._last_push < MIN_PUSH_INTERVAL:
            return
        body = self._answer()
        shown = _shown_state(body)
        if shown == self._shown:  # nothing the page shows changed: no push
            return
        await self._channel.send(body)
        self._shown = shown
        self.pushes += 1
        self._last_push = self._monotonic()

    async def run(self) -> None:
        recv: asyncio.Future | None = None
        try:
            self._subscribe()
            while True:
                if recv is None:
                    recv = asyncio.ensure_future(self._channel.receive())
                done, _ = await asyncio.wait({recv}, timeout=self._poll)
                if done:
                    task, recv = recv, None
                    try:
                        task.result()
                    except ChannelClosed:
                        return
                    await self._channel.send(render("user_input_request_invalid"))  # nothing a client sends is read
                if self._handle is not None and self._feed is not None:
                    self._feed.fanout.pump_one(self._handle)
                await self._maybe_push()
        finally:
            if recv is not None:
                recv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await recv
            self._release()
