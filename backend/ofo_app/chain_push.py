"""The Option Chain read and its live push (W-116; REQ-029 AC-1/AC-2/AC-4/AC-6/AC-8, REQ-049 AC-2). Framework-free.

# Adapted from abhayla/algochanakya@bf9faf7 backend/app/services/options/option_chain_live_engine.py (rows keyed by
# strike, CE/PE sides; the ATM pick ``min(strikes, key=abs(strike - spot))``, line 391) and
# backend/app/api/routes/optionchain.py (one chain answer for one underlying and expiry). Changed for this project:
# strikes and contracts come from the stored catalogue only (never from the feed or a computed step), money is Decimal
# and leaves as a 2-decimal string, the platform-wide snapshot/EOD fallbacks, IV and Greeks are dropped (IV is
# Advanced-only and engine-owned: REQ-029 AC-2, ADR-008/056), and the push is a per-connection class on the ONE shared
# fan-out (ADR-068), like ``live_push.StrategyPush``.

One :class:`ChainPush` serves one browser connection of the read-only chain socket. The client sends a
:class:`ChainRequest` ``{underlying, expiry, strikes_each_side}``. The push reads that expiry's contracts from the stored
catalogue (one short database read per applied request, never per push: finding db-role-limit-below-pool-size), picks
``strikes_each_side`` catalogue strikes either side of the ATM strike from the LIVE spot (no spot: no strikes and no
guessed ATM), subscribes those CE/PE contracts and the index on the shared ``FanOut`` and pushes :func:`chain_answer` -
the same function the REST read returns - at most once every ``MIN_PUSH_INTERVAL`` seconds and only when something the
screen shows changed. A new request is applied at most once a second too (latest wins), so a client cannot drive
catalogue reads or Kite subscription changes faster; it takes the new subscription BEFORE releasing the old one (the
order of ``StrategyPush._replace``, so a shared instrument such as the index is never dropped and re-added). Everything
is released when the connection ends, on every exit path.

Liveness is this connection's own: LIVE only while THIS push holds its subscription (finding
liveness-from-shared-subscribers); each cell carries its quote's OWN health as the provider gives it at the moment of the
answer, so a quote that went stale is never shown as available (REQ-049 AC-2; no new staleness rule here: finding
staleness-by-last-change-age). ``change`` is always null: the normalised feed carries no previous close for a contract,
and REQ-029 AC-2's change is never computed from anything else. No order, basket, margin or execute call exists here
(REQ-029 AC-6).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ofo.errors import render
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import PAISE  # money leaves the API as a 2-decimal string
from ofo_app.api_models import ApiModel, InstrumentId, Money
from ofo_app.catalogue_picker import PickableContract
from ofo_app.live_push import MIN_PUSH_INTERVAL, POLL_SECONDS, Channel, ChannelClosed, LiveFeed
from ofo_app.routes.outcome import HealthCode, MarketContext

log = logging.getLogger(__name__)

#: The most strikes either side of ATM a chain may ask for, and the default (design: "15 strikes either side at first
#: open", docs/design/screens-research-2026-10-19.md). It bounds one socket's subscription to 2 * 31 contracts + 1 index.
MAX_STRIKES_EACH_SIDE = 15
_SIDES = ("CE", "PE")

#: Why a chain answer has no rows (None when it has them). ``NOT_CONNECTED`` answers carry none either: then the state
#: says so and this is None.
RowsMissing = Literal["SPOT_MISSING", "EXPIRY_UNKNOWN", "CATALOGUE_EMPTY", "CATALOGUE_UNREADABLE"]


class ChainRequest(BaseModel):
    """What the chain socket's client sends (and the REST read's query): one underlying, one expiry, a strike count."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    underlying: Literal["NIFTY", "SENSEX"]
    expiry: datetime.date
    strikes_each_side: StrictInt = Field(default=MAX_STRIKES_EACH_SIDE, ge=1, le=MAX_STRIKES_EACH_SIDE)


class ChainCellOut(ApiModel):
    instrument_id: InstrumentId  # the catalogue's contract id (segment:token)
    ltp: Money | None  # the last price as given; None when there is none or the answer is not live
    change: Money | None  # always None: the feed carries no previous close (REQ-029 AC-2, never computed otherwise)
    oi: int | None
    volume: int | None
    health: HealthCode | None  # the quote's own health; None in the not-live answer
    at: datetime.datetime | None  # the quote's own time (aware)


class ChainRowOut(ApiModel):
    strike: Money
    ce: ChainCellOut | None  # None: the catalogue lists no call at this strike
    pe: ChainCellOut | None  # None: the catalogue lists no put at this strike


class ChainOut(ApiModel):
    state: Literal["LIVE", "NOT_CONNECTED"]
    underlying: Literal["NIFTY", "SENSEX"]
    expiry: datetime.date
    spot: Money | None  # the underlying index price (REQ-029 AC-8); None when missing or not live
    spot_at: datetime.datetime | None
    spot_health: HealthCode | None
    atm_strike: Money | None  # the catalogue strike nearest the live spot (REQ-029 AC-8); None without a live spot
    rows_missing: RowsMissing | None
    rows: list[ChainRowOut]  # ascending strike (REQ-029 AC-1: Calls | Strike | Puts)
    #: ADR-088: when the server produced THIS answer (aware)
    answered_at: datetime.datetime


@dataclass(frozen=True)
class ChainCatalogue:
    """The stored catalogue's answer for one request: the underlying's pickable expiries and that expiry's options."""

    expiries: tuple[datetime.date, ...]
    contracts: tuple[PickableContract, ...]
    unreadable: bool = False


ChainReader = Callable[[str, datetime.date], Awaitable[ChainCatalogue]]


async def stored_chain(underlying: str, expiry: datetime.date) -> ChainCatalogue:
    """The stored catalogue's contracts of one expiry (the reader of ``/api/catalogue/{u}/contracts``), in ONE short
    session that is closed before any push. A catalogue that cannot be read is said so, never an error and never an
    empty catalogue; only the exception class is logged."""
    from ofo_app import catalogue_picker as picker  # noqa: PLC0415 - late, like outcome.stored_contracts
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    try:
        async with get_sessionmaker()() as session:
            today = await picker.database_today(session)
            expiries = tuple(await picker.pickable_expiries(session, underlying, today))
            rows = await picker.pickable_contracts(session, underlying, today, expiry) if expiry in expiries else []
    except (SQLAlchemyError, OSError, RuntimeError) as exc:  # no database, a refused or lost connection
        log.warning("option chain: the catalogue could not be read: %s", type(exc).__name__)
        return ChainCatalogue((), (), unreadable=True)
    return ChainCatalogue(expiries, tuple(r for r in rows if r.instrument_type in _SIDES))


def strike_grid(catalogue: ChainCatalogue) -> list[Decimal]:
    """The catalogue's option strikes of the expiry, ascending, each once."""
    return sorted({c.strike for c in catalogue.contracts if c.instrument_type in _SIDES and c.strike is not None})


def atm_strike(grid: list[Decimal], spot: Decimal) -> Decimal:
    """The grid strike nearest the spot; on an exact tie the lower strike (legacy: the first of the sorted strikes)."""
    return min(grid, key=lambda s: (abs(s - spot), s))


def strike_window(grid: list[Decimal], atm: Decimal, each_side: int) -> tuple[Decimal, ...]:
    """``each_side`` grid strikes below and above ``atm`` (fewer at the grid's ends), with ``atm`` itself."""
    if not 1 <= each_side <= MAX_STRIKES_EACH_SIDE:  # the request model caps it; a direct caller is refused too
        raise ValueError(f"strikes_each_side must be 1..{MAX_STRIKES_EACH_SIDE}")
    i = grid.index(atm)
    return tuple(grid[max(0, i - each_side): i + each_side + 1])


def _spot_quote(ctx: MarketContext, underlying: str) -> NormalizedQuote | None:
    index_id = index_id_of(ctx, underlying)
    quote = None if index_id is None else ctx.provider.underlying_quote(underlying)
    if quote is not None and quote.instrument_id != index_id:  # never another instrument's quote as the index's
        return None
    return quote


def index_id_of(ctx: MarketContext, underlying: str) -> str | None:
    return getattr(ctx.provider, "index_id", lambda _u: None)(underlying)


def live_spot(ctx: MarketContext | None, underlying: str) -> Decimal | None:
    """The index price the ATM is picked from: a quote of the index itself with a live price, else None."""
    quote = None if ctx is None else _spot_quote(ctx, underlying)
    return quote.ltp if quote is not None and is_live_price(quote.ltp) else None


def pick_window(ctx: MarketContext | None, req: ChainRequest, catalogue: ChainCatalogue) -> tuple[Decimal, ...] | None:
    """The strikes to show around the ATM of the live spot; None when there is no live spot or no strike."""
    grid = strike_grid(catalogue)
    spot = live_spot(ctx, req.underlying)
    if spot is None or not grid:
        return None
    return strike_window(grid, atm_strike(grid, spot), req.strikes_each_side)


def window_ids(catalogue: ChainCatalogue, window: tuple[Decimal, ...] | None) -> list[str]:
    """The contract ids of the window's strikes, ascending strike, CE before PE."""
    if not window:
        return []
    wanted = set(window)
    chosen = [c for c in catalogue.contracts if c.instrument_type in _SIDES and c.strike in wanted]
    chosen.sort(key=lambda c: (c.strike, _SIDES.index(c.instrument_type)))
    return [c.instrument_id for c in chosen]


def _rows_missing(catalogue: ChainCatalogue, expiry: datetime.date, window: tuple | None) -> RowsMissing | None:
    if catalogue.unreadable:
        return "CATALOGUE_UNREADABLE"
    if not catalogue.expiries:
        return "CATALOGUE_EMPTY"
    if expiry not in catalogue.expiries:
        return "EXPIRY_UNKNOWN"
    if not strike_grid(catalogue):
        return "CATALOGUE_EMPTY"
    return "SPOT_MISSING" if window is None else None


def _cell(contract: PickableContract, quote: NormalizedQuote | None) -> ChainCellOut:
    if quote is None or quote.instrument_id != contract.instrument_id:  # held, but no quote yet: shown as such
        return ChainCellOut(instrument_id=contract.instrument_id, ltp=None, change=None, oi=None, volume=None,
                            health="unavailable", at=None)
    ltp = quote.ltp.quantize(PAISE) if is_live_price(quote.ltp) else None
    return ChainCellOut(instrument_id=contract.instrument_id, ltp=ltp, change=None, oi=quote.oi, volume=quote.volume,
                        health=quote.health.value, at=quote.timestamp)


def _rows(ctx: MarketContext, req: ChainRequest, catalogue: ChainCatalogue,
          window: tuple[Decimal, ...]) -> list[ChainRowOut]:
    quotes = {q.instrument_id: q for q in ctx.provider.option_chain_snapshot(req.underlying, req.expiry)}
    by_strike: dict[Decimal, dict[str, PickableContract]] = {s: {} for s in window}
    for c in catalogue.contracts:
        if c.strike in by_strike and c.instrument_type in _SIDES:
            by_strike[c.strike][c.instrument_type] = c
    out = []
    for strike in window:
        sides = by_strike[strike]
        ce, pe = sides.get("CE"), sides.get("PE")
        out.append(ChainRowOut(strike=strike.quantize(PAISE),
                               ce=None if ce is None else _cell(ce, quotes.get(ce.instrument_id)),
                               pe=None if pe is None else _cell(pe, quotes.get(pe.instrument_id))))
    return out


def chain_answer(ctx: MarketContext | None, req: ChainRequest, catalogue: ChainCatalogue,  # noqa: PLR0913
                 window: tuple[Decimal, ...] | None, *, live: bool,
                 now: Callable[[], datetime.datetime]) -> ChainOut:
    """The ONE answer behind the REST read and the socket push. Not live (no feed, the page's own socket is down, or this
    connection holds nothing): NOT_CONNECTED, no rows, no number; only the spot's last value time is kept."""
    spot_quote = None if ctx is None else _spot_quote(ctx, req.underlying)
    answered_at = now() if ctx is None else ctx.clock()
    if ctx is None or not live:
        return ChainOut(state="NOT_CONNECTED", underlying=req.underlying, expiry=req.expiry, spot=None,
                        spot_at=None if spot_quote is None else spot_quote.timestamp, spot_health=None,
                        atm_strike=None, rows_missing=None, rows=[], answered_at=answered_at)
    spot = live_spot(ctx, req.underlying)
    grid = strike_grid(catalogue)
    missing = _rows_missing(catalogue, req.expiry, window)
    return ChainOut(
        state="LIVE", underlying=req.underlying, expiry=req.expiry,
        spot=None if spot is None else spot.quantize(PAISE),
        spot_at=None if spot_quote is None else spot_quote.timestamp,
        spot_health="unavailable" if spot_quote is None else spot_quote.health.value,
        atm_strike=atm_strike(grid, spot).quantize(PAISE) if spot is not None and grid else None,
        rows_missing=missing, rows=[] if missing is not None or window is None else _rows(ctx, req, catalogue, window),
        answered_at=answered_at)


def _shown_state(body: ChainOut) -> tuple:
    """What the screen shows (never ``answered_at``, which moves on every read)."""
    return body.model_dump_json(exclude={"answered_at"}),


def _ignore(_quote: Any) -> None:
    """The fan-out listener: the push reads the provider's current quotes (with their health at this moment) at each
    answer, so the queued ticks only need draining."""


class ChainPush:
    def __init__(self, channel: Channel, feed: LiveFeed | None, *, monotonic: Callable[[], float],  # noqa: PLR0913
                 now: Callable[[], datetime.datetime], reader: ChainReader = stored_chain,
                 poll: float = POLL_SECONDS) -> None:
        self._channel = channel
        self._feed = feed
        self._monotonic = monotonic
        self._now = now
        self._reader = reader
        self._poll = poll
        self._req: ChainRequest | None = None
        self._catalogue: ChainCatalogue | None = None
        self._window: tuple[Decimal, ...] | None = None
        self._handle: int | None = None
        self._pending: ChainRequest | None = None
        self._last_apply: float | None = None
        self._shown: tuple | None = None
        self._last_push: float | None = None
        self.pushes = 0

    @property
    def _ctx(self) -> MarketContext | None:
        return None if self._feed is None else self._feed.ctx

    def _release(self) -> None:
        if self._handle is not None and self._feed is not None:
            self._feed.fanout.unsubscribe(self._handle)
        self._handle = None

    async def _error(self) -> None:
        await self._channel.send(render("user_input_request_invalid"))

    async def _receive(self, raw: Any) -> None:
        if isinstance(raw, dict) and "fallback" in raw:  # the REST read's flag; it means nothing on the socket (#234)
            await self._error()
            return
        try:
            req = ChainRequest.model_validate(raw)
        except ValidationError:
            await self._error()
            return
        self._pending = None if req == self._req else req  # the latest wins; the current one again cancels a pending

    async def _maybe_apply(self) -> None:
        if self._pending is None:
            return
        if self._last_apply is not None and self._monotonic() - self._last_apply < MIN_PUSH_INTERVAL:
            return  # at most one applied request (catalogue read, subscription change) a second
        req, self._pending = self._pending, None
        self._last_apply = self._monotonic()
        catalogue = await self._reader(req.underlying, req.expiry)
        await self._take(req, catalogue)

    async def _take(self, req: ChainRequest, catalogue: ChainCatalogue) -> None:
        """Subscribe the request's window and index, THEN release what was held (a shared id is never dropped)."""
        window = pick_window(self._ctx, req, catalogue)
        new_handle = None
        if self._ctx is not None:
            index_id = index_id_of(self._ctx, req.underlying)
            ids = window_ids(catalogue, window) + ([index_id] if index_id else [])
            if ids:
                try:
                    new_handle = self._feed.fanout.subscribe(_ignore, ids)
                except KeyError:  # an id the provider does not know: nothing was subscribed, the old one stays
                    await self._error()
                    return
        self._release()
        self._handle, self._req, self._catalogue, self._window = new_handle, req, catalogue, window

    async def _maybe_push(self) -> None:
        if self._req is None or self._catalogue is None:
            return
        if self._last_push is not None and self._monotonic() - self._last_push < MIN_PUSH_INTERVAL:
            return
        if self._window is None and self._handle is not None:  # no spot when applied: pick once the spot arrives
            if pick_window(self._ctx, self._req, self._catalogue) is not None:
                await self._take(self._req, self._catalogue)
        body = chain_answer(self._ctx, self._req, self._catalogue, self._window, live=self._handle is not None,
                            now=self._now)
        shown = _shown_state(body)
        if shown == self._shown:  # nothing the screen shows changed: no push
            return
        await self._channel.send(body)
        self._shown = shown
        self.pushes += 1
        self._last_push = self._monotonic()

    async def run(self) -> None:
        recv: asyncio.Future | None = None
        try:
            while True:
                if recv is None:
                    recv = asyncio.ensure_future(self._channel.receive())
                done, _ = await asyncio.wait({recv}, timeout=self._poll)
                if done:
                    task, recv = recv, None
                    try:
                        raw = task.result()
                    except ChannelClosed:
                        return
                    await self._receive(raw)
                await self._maybe_apply()
                if self._handle is not None and self._feed is not None:
                    self._feed.fanout.pump_one(self._handle)
                await self._maybe_push()
        finally:
            if recv is not None:
                recv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await recv
            self._release()
