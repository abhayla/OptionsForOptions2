"""The leg picker's server reads (REQ-080 AC-1, AC-2, AC-5, AC-6, AC-7, AC-8; ADR-012, ADR-015, ADR-056, ADR-061).

Reads only: no order, basket, margin or execute call is reachable from here (REQ-080 AC-3 is the browser's part, and the
picker never places an order, ADR-002). Three ``GET`` routes, each a door route minting one response model:

- ``/api/leg-picker/strikes?underlying&expiry&width``: the strikes around the ATM of the live spot (``width`` strikes
  either side, 10 / 20 / 30 / 40, default 10) with each CE and PE cell's LTP and OI from the platform's own feed
  (``chain_push``: the catalogue reader, the ATM pick and the spot read) and IV and delta from the ENGINE
  (``ofo.engine.chain_values.chain_greeks``). A cell without a trustworthy price is null (never a stale or zero price as
  current, ADR-015); the list carries ONE reason code (REQ-049) the screen words.
- ``/api/leg-picker/futures?underlying``: every listed futures expiry with its LTP and, per option expiry, the forward
  the engine prices it with and which one was used (parity or spot fallback, ADR-061: never silent).
- ``/api/leg-picker/depth?instrument_id``: 5 bid and ask levels, the day's open / high / low / previous close and the
  last trade time of one contract, or ``NOT_AVAILABLE`` with a reason code, never an empty or old table.

A GET holds no socket of its own, so the strikes read keeps ONE short lease on the shared fan-out (the picker's window,
at most ``2 x (2 x 40 + 1)`` option contracts and the index): the same request again reuses it, a different one takes
the new window BEFORE releasing the old (a shared id is never dropped and re-added, like ``ChainPush._take``), and it
ends ``LEASE_SECONDS`` after the last read. Reading twice never grows the subscription count (finding
liveness-from-shared-subscribers: a quote is live only while a holder streams it).
"""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from ofo.engine.chain_values import ChainGreeks, chain_greeks
from ofo.marketdata.forward import ExpiryForward, ForwardUnavailable, parity_forward
from ofo.marketdata.kite_provider import IST
from ofo.marketdata.provider import NotSupported
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from pydantic import AfterValidator
from sqlalchemy.exc import SQLAlchemyError

from ofo_app.api_models import ApiModel, CatalogueText, InstrumentId, Money
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import (
    ChainCatalogue,
    ChainReader,
    _spot_quote,
    atm_strike,
    index_id_of,
    stored_chain,
    strike_grid,
)
from ofo_app.errors import ClosedRoute
from ofo_app.live_push import LiveFeed
from ofo_app.routes import live
from ofo_app.routes.outcome import AnswerClock, HealthCode, get_answer_clock, market_state
from ofo_app.underlying import Underlying

STRIKES_PATH = "/api/leg-picker/strikes"
FUTURES_PATH = "/api/leg-picker/futures"
DEPTH_PATH = "/api/leg-picker/depth"
WIDTHS = (10, 20, 30, 40)  # REQ-080 AC-1: strikes each side of ATM
DEFAULT_WIDTH = 10
LEASE_SECONDS = 30.0  # the picker's window is held this long after its last read
_SIDES = ("CE", "PE")
_DELTA_STEP = Decimal("0.0001")
_PERCENT = Decimal(100)

#: Why the list has no usable prices (REQ-049 reason, one per list; None when every cell is priced). Order = priority.
ListReason = Literal["CATALOGUE_UNREADABLE", "CATALOGUE_EMPTY", "EXPIRY_UNKNOWN", "NOT_CONNECTED", "SPOT_MISSING",
                     "FEED_STALE", "WAITING_FOR_PRICES", "SOME_PRICES_MISSING"]
#: Why one contract's depth cannot be shown (REQ-080 AC-8).
DepthReason = Literal["NO_SESSION", "FEED_STALE", "NOT_STREAMING", "NO_DEPTH_RECEIVED", "DEPTH_EMPTY"]

router = APIRouter(route_class=ClosedRoute)


def _listed_width(value: int) -> int:
    """An allow-list, not a range: only the picker's own widths (a query string gives an int, which ``Literal`` of
    ints would refuse)."""
    if value not in WIDTHS:
        raise ValueError(f"width must be one of {WIDTHS}")
    return value


Width = Annotated[int, AfterValidator(_listed_width)]


# ---- response models ------------------------------------------------------------------------------------------------

class PickerCellOut(ApiModel):
    instrument_id: InstrumentId
    lot_size: int  # from the catalogue's instrument row, never retyped
    ltp: Money | None  # None: no live price, a stale feed or a zero price (ADR-015)
    oi: int | None
    iv_percent: Money | None  # the engine's implied volatility in percent, 2 decimals; None: not computable now
    delta: Money | None  # the engine's delta, 4 decimals; None: not computable now
    health: HealthCode  # the quote's own health; "unavailable" when no quote is held
    at: datetime.datetime | None  # the quote's own time


class PickerRowOut(ApiModel):
    strike: Money
    is_atm: bool
    ce: PickerCellOut | None  # None: the catalogue lists no call at this strike
    pe: PickerCellOut | None


class StrikesOut(ApiModel):
    state: Literal["LIVE", "NOT_LIVE"]
    reason: ListReason | None
    underlying: Underlying
    expiry: datetime.date
    width: int
    spot: Money | None
    atm_strike: Money | None
    rows: list[PickerRowOut]  # ascending strike
    answered_at: datetime.datetime
    market_closed: bool


class FutureOut(ApiModel):
    expiry: datetime.date
    instrument_id: InstrumentId
    lot_size: int
    ltp: Money | None
    health: HealthCode | None
    ltp_reason: Literal["NOT_OFFERED", "NO_QUOTE", "NOT_LIVE"] | None  # why ``ltp`` is None (None when it is not)


class ForwardOut(ApiModel):
    expiry: datetime.date
    forward: Money | None  # "Forward used for pricing" (REQ-080 AC-6); None: the engine cannot price this expiry now
    source: Literal["parity", "spot_fallback"] | None  # which forward the engine used (ADR-061)
    label: CatalogueText | None  # "estimated from spot" on the fallback
    strikes_used: int
    reason: Literal["SPOT_MISSING", "NOT_PRICEABLE"] | None


class FuturesOut(ApiModel):
    state: Literal["LIVE", "NOT_LIVE"]
    reason: Literal["CATALOGUE_UNREADABLE", "CATALOGUE_EMPTY", "NOT_CONNECTED", "SPOT_MISSING"] | None
    underlying: Underlying
    spot: Money | None
    futures: list[FutureOut]
    forwards: list[ForwardOut]
    answered_at: datetime.datetime


class DepthLevelOut(ApiModel):
    price: Money
    quantity: int


class DepthOut(ApiModel):
    state: Literal["AVAILABLE", "NOT_AVAILABLE"]
    reason: DepthReason | None
    instrument_id: InstrumentId
    bids: list[DepthLevelOut]  # best first; empty ONLY with state NOT_AVAILABLE
    asks: list[DepthLevelOut]
    day_open: Money | None
    day_high: Money | None
    day_low: Money | None
    prev_close: Money | None  # where the data carries it (F-47)
    last_trade_at: datetime.datetime | None
    read_at: datetime.datetime  # when the server read the depth


# ---- the window lease -----------------------------------------------------------------------------------------------

def _ignore(_quote: Any) -> None:
    """The fan-out listener: reads take the provider's current quotes (with their health at that moment)."""


@dataclass
class _Lease:
    feed: LiveFeed
    key: tuple[str, datetime.date, int]
    ids: tuple[str, ...]
    handle: int | None
    unknown: frozenset[str]


class WindowLease:
    """The one subscription of the picker's current window (see the module docstring)."""

    def __init__(self) -> None:
        self._lease: _Lease | None = None
        self._timer: asyncio.TimerHandle | None = None

    @property
    def held_ids(self) -> frozenset[str]:
        lease = self._lease
        return frozenset() if lease is None or lease.handle is None else frozenset(lease.ids) - lease.unknown

    def hold(self, feed: LiveFeed, key: tuple[str, datetime.date, int], ids: list[str]) -> _Lease:
        """Hold ``ids`` for ``key``. The same feed and key again changes nothing; otherwise the new window is taken
        first and the old one released after. A contract the provider does not know is left out and remembered."""
        current = self._lease
        if current is not None and current.feed is feed and current.key == key and current.ids == tuple(ids):
            self._arm()
            return current
        handle, unknown = self._subscribe(feed, ids)
        self.release()
        self._lease = _Lease(feed, key, tuple(ids), handle, unknown)
        self._arm()
        return self._lease

    @staticmethod
    def _subscribe(feed: LiveFeed, ids: list[str]) -> tuple[int | None, frozenset[str]]:
        fanout = feed.fanout
        try:
            return fanout.subscribe(_ignore, ids, max_queue=1), frozenset()
        except KeyError:
            pass
        unknown: set[str] = set()
        singles: list[int] = []  # one id at a time finds the unknown ones; the final handle holds every known id
        try:
            for i in ids:
                try:
                    singles.append(fanout.subscribe(_ignore, [i], max_queue=1))
                except KeyError:
                    unknown.add(i)
            known = [i for i in ids if i not in unknown]
            handle = fanout.subscribe(_ignore, known, max_queue=1) if known else None
        finally:
            for single in singles:  # the final handle holds the known ids, so no vendor unsubscribe happens here
                fanout.unsubscribe(single)
        return handle, frozenset(unknown)

    def release(self) -> None:
        lease, self._lease = self._lease, None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if lease is not None and lease.handle is not None:
            lease.feed.fanout.unsubscribe(lease.handle)

    def _arm(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        try:
            self._timer = asyncio.get_running_loop().call_later(LEASE_SECONDS, self.release)
        except RuntimeError:  # a direct call outside the event loop (a test): the route always runs inside it
            self._timer = None


LEASE = WindowLease()


# ---- the strikes read -----------------------------------------------------------------------------------------------

def _priced(quote: NormalizedQuote | None) -> bool:
    """A quote's price counts only when the quote is AVAILABLE (the feed's own health) and the price is above 0."""
    return quote is not None and quote.health is DataHealth.AVAILABLE and is_live_price(quote.ltp)


def _cell(contract: PickableContract, quote: NormalizedQuote | None, greeks: ChainGreeks | None) -> PickerCellOut:
    if quote is None:
        return PickerCellOut(instrument_id=contract.instrument_id, lot_size=contract.lot_size, ltp=None, oi=None,
                             iv_percent=None, delta=None, health="unavailable", at=None)
    priced = _priced(quote)
    return PickerCellOut(
        instrument_id=contract.instrument_id, lot_size=contract.lot_size,
        ltp=quote.ltp.quantize(PAISE) if priced and quote.ltp is not None else None,
        oi=quote.oi if quote.health is DataHealth.AVAILABLE else None,
        iv_percent=None if greeks is None or not priced else (greeks.iv * _PERCENT).quantize(PAISE),
        delta=None if greeks is None or not priced else greeks.delta.quantize(_DELTA_STEP),
        health=quote.health.value, at=quote.timestamp)


def _catalogue_reason(catalogue: ChainCatalogue, expiry: datetime.date) -> ListReason | None:
    if catalogue.unreadable:
        return "CATALOGUE_UNREADABLE"
    if not catalogue.expiries or not strike_grid(catalogue):
        return "CATALOGUE_EMPTY"
    return None if expiry in catalogue.expiries else "EXPIRY_UNKNOWN"


def window_of(catalogue: ChainCatalogue, spot: Decimal, width: int) -> tuple[Decimal, ...]:
    """``width`` catalogue strikes either side of the ATM strike and the ATM itself (fewer at the grid's ends). The
    picker's widths go past ``chain_push.MAX_STRIKES_EACH_SIDE``, so this slices the same grid and ATM pick itself."""
    grid = strike_grid(catalogue)
    i = grid.index(atm_strike(grid, spot))
    return tuple(grid[max(0, i - width): i + width + 1])


def _window_contracts(catalogue: ChainCatalogue, window: tuple[Decimal, ...]) -> list[PickableContract]:
    """The window's CE and PE contracts, ascending strike, CE before PE."""
    wanted = set(window)
    chosen = [c for c in catalogue.contracts if c.instrument_type in _SIDES and c.strike in wanted]
    return sorted(chosen, key=lambda c: (c.strike, _SIDES.index(c.instrument_type)))


def _list_reason(spot_quote: NormalizedQuote | None, cells: list[PickerCellOut]) -> ListReason | None:
    if spot_quote is None:
        return "SPOT_MISSING"
    if spot_quote.health is not DataHealth.AVAILABLE:
        return "FEED_STALE"
    priced = sum(c.ltp is not None for c in cells)
    if priced == 0:
        return "WAITING_FOR_PRICES"
    return None if priced == len(cells) else "SOME_PRICES_MISSING"


def strikes_answer(feed: LiveFeed | None, underlying: str, expiry: datetime.date, width: int,  # noqa: PLR0913
                   catalogue: ChainCatalogue, now: AnswerClock) -> StrikesOut:
    """The strikes read. Every answer state: catalogue unreadable / empty / expiry unknown (no rows), no feed, no live
    spot (no rows and no guessed ATM), spot stale (rows, no price), a quote missing for some contracts (those cells
    null), a contract the provider does not know (that cell unavailable), every cell priced."""
    ctx = None if feed is None else feed.ctx
    answered_at = now() if ctx is None else ctx.clock()
    head = {"underlying": underlying, "expiry": expiry, "width": width, "answered_at": answered_at,
            "market_closed": market_state(ctx, answered_at).closed}
    missing = _catalogue_reason(catalogue, expiry)
    spot_quote = None if ctx is None else _spot_quote(ctx, underlying)
    spot = None if spot_quote is None or not is_live_price(spot_quote.ltp) else spot_quote.ltp
    if missing is not None or feed is None or ctx is None or spot is None:
        reason = missing or ("NOT_CONNECTED" if ctx is None else "SPOT_MISSING")
        return StrikesOut(state="NOT_LIVE" if ctx is None else "LIVE", reason=reason, spot=None, atm_strike=None,
                          rows=[], **head)
    window = window_of(catalogue, spot, width)
    contracts = _window_contracts(catalogue, window)
    index_id = index_id_of(ctx, underlying)
    LEASE.hold(feed, (underlying, expiry, width),
               [c.instrument_id for c in contracts] + ([index_id] if index_id else []))
    live_ids = LEASE.held_ids
    quotes = {q.instrument_id: q for q in ctx.provider.option_chain_snapshot(underlying, expiry)
              if q.instrument_id in live_ids}
    usable = [q for q in quotes.values() if _priced(q)]
    greeks = chain_greeks(usable, spot_quote if spot_quote.health is DataHealth.AVAILABLE else None, expiry,
                          answered_at, ctx.rate)
    cell_of = {c.instrument_id: _cell(c, quotes.get(c.instrument_id), greeks.get(c.instrument_id)) for c in contracts}
    atm = atm_strike(strike_grid(catalogue), spot)
    rows = []
    for strike in window:
        sides = {c.instrument_type: cell_of[c.instrument_id] for c in contracts if c.strike == strike}
        rows.append(PickerRowOut(strike=strike.quantize(PAISE), is_atm=strike == atm, ce=sides.get("CE"),
                                 pe=sides.get("PE")))
    return StrikesOut(state="LIVE", reason=_list_reason(spot_quote, list(cell_of.values())), spot=spot.quantize(PAISE),
                      atm_strike=atm.quantize(PAISE), rows=rows, **head)


# ---- the futures read -----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FuturesCatalogue:
    """The stored catalogue's answer for one underlying: its option expiries and its listed futures."""

    option_expiries: tuple[datetime.date, ...]
    futures: tuple[PickableContract, ...]
    unreadable: bool = False


FuturesReader = Callable[[str], Awaitable[FuturesCatalogue]]


async def stored_futures(underlying: str) -> FuturesCatalogue:
    """Every pickable contract of the underlying, split into option expiries and futures, in ONE short session. A
    catalogue that cannot be read is said so (never an empty list); only the exception class is logged."""
    from ofo_app import catalogue_picker as picker  # noqa: PLC0415 - late, like chain_push.stored_chain
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    try:
        async with get_sessionmaker()() as session:
            today = await picker.database_today(session)
            rows = await picker.pickable_contracts(session, underlying, today)
    except (SQLAlchemyError, OSError, RuntimeError):
        return FuturesCatalogue((), (), unreadable=True)
    expiries = tuple(sorted({r.expiry for r in rows if r.instrument_type in _SIDES}))
    return FuturesCatalogue(expiries, tuple(r for r in rows if r.instrument_type == "FUT"))


def _future_ltp(ctx: Any, underlying: str, contract: PickableContract) -> FutureOut:
    head = {"expiry": contract.expiry, "instrument_id": contract.instrument_id, "lot_size": contract.lot_size}
    if ctx is None:
        return FutureOut(**head, ltp=None, health=None, ltp_reason="NOT_LIVE")
    try:
        quote = ctx.provider.futures_quote(underlying, contract.expiry)
    except NotSupported:  # Kite's provider offers no futures quote in V1 (kite_provider.futures_quote)
        return FutureOut(**head, ltp=None, health=None, ltp_reason="NOT_OFFERED")
    if quote is None:
        return FutureOut(**head, ltp=None, health=None, ltp_reason="NO_QUOTE")
    if not _priced(quote) or quote.ltp is None:
        return FutureOut(**head, ltp=None, health=quote.health.value, ltp_reason="NO_QUOTE")
    return FutureOut(**head, ltp=quote.ltp.quantize(PAISE), health=quote.health.value, ltp_reason=None)


def _forward(ctx: Any, underlying: str, expiry: datetime.date, spot_quote: NormalizedQuote | None,
             valuation: datetime.datetime) -> ForwardOut:
    """The forward the engine prices ``expiry`` with: ADR-061's own function over this expiry's held quotes (with fewer
    than 3 usable strikes it answers the spot fallback and says so). Refused states carry a reason, never a number."""
    if ctx is None or spot_quote is None:
        return ForwardOut(expiry=expiry, forward=None, source=None, label=None, strikes_used=0, reason="SPOT_MISSING")
    try:
        fwd: ExpiryForward = parity_forward(ctx.provider.option_chain_snapshot(underlying, expiry), spot_quote, expiry,
                                            valuation, ctx.rate)
    except ForwardUnavailable:
        return ForwardOut(expiry=expiry, forward=None, source=None, label=None, strikes_used=0,
                          reason="NOT_PRICEABLE")
    return ForwardOut(expiry=expiry, forward=fwd.forward.quantize(PAISE),
                      source="parity" if fwd.source == "parity" else "spot_fallback", label=fwd.label,
                      strikes_used=fwd.strikes_used, reason=None)


def futures_answer(feed: LiveFeed | None, underlying: str, catalogue: FuturesCatalogue, now: AnswerClock) -> FuturesOut:
    ctx = None if feed is None else feed.ctx
    answered_at = now() if ctx is None else ctx.clock()
    spot_quote = None if ctx is None else _spot_quote(ctx, underlying)
    spot = None if spot_quote is None or not is_live_price(spot_quote.ltp) else spot_quote.ltp
    reason: Literal["CATALOGUE_UNREADABLE", "CATALOGUE_EMPTY", "NOT_CONNECTED", "SPOT_MISSING"] | None
    if catalogue.unreadable:
        reason = "CATALOGUE_UNREADABLE"
    elif not catalogue.futures and not catalogue.option_expiries:
        reason = "CATALOGUE_EMPTY"
    elif ctx is None:
        reason = "NOT_CONNECTED"
    else:
        reason = None if spot is not None else "SPOT_MISSING"
    return FuturesOut(
        state="NOT_LIVE" if ctx is None else "LIVE", reason=reason, underlying=underlying,
        spot=None if spot is None else spot.quantize(PAISE),
        futures=[_future_ltp(ctx, underlying, c) for c in catalogue.futures],
        forwards=[_forward(ctx, underlying, e, spot_quote, answered_at) for e in catalogue.option_expiries],
        answered_at=answered_at)


# ---- the depth read -------------------------------------------------------------------------------------------------

def _not_available(instrument_id: str, reason: DepthReason, read_at: datetime.datetime) -> DepthOut:
    return DepthOut(state="NOT_AVAILABLE", reason=reason, instrument_id=instrument_id, bids=[], asks=[], day_open=None,
                    day_high=None, day_low=None, prev_close=None, last_trade_at=None, read_at=read_at)


def depth_answer(feed: LiveFeed | None, instrument_id: str, now: AnswerClock) -> DepthOut:
    """One contract's depth. Every answer state: no feed or session ended (NO_SESSION), the feed not healthy
    (FEED_STALE), nobody streams the contract (NOT_STREAMING), no full packet yet or a provider without depth
    (NO_DEPTH_RECEIVED: a quote-only packet is not "no liquidity"), both sides empty (DEPTH_EMPTY), levels (AVAILABLE).
    A zero-priced or zero-quantity level never reaches here (``depth_from_levels`` drops it)."""
    if feed is None:
        return _not_available(instrument_id, "NO_SESSION", now())
    ctx = feed.ctx
    read_at = ctx.clock()
    status = ctx.provider.status()
    if status.session_ended or not status.connected:
        return _not_available(instrument_id, "NO_SESSION", read_at)
    if status.health is not DataHealth.AVAILABLE:
        return _not_available(instrument_id, "FEED_STALE", read_at)
    if feed.fanout.subscriber_count(instrument_id) == 0:
        return _not_available(instrument_id, "NOT_STREAMING", read_at)
    reader = getattr(ctx.provider, "latest_depth", None)  # a provider without depth (the test replay) has none
    depth = None if reader is None else reader(instrument_id, read_at)
    if depth is None:
        return _not_available(instrument_id, "NO_DEPTH_RECEIVED", read_at)
    if not depth.bids and not depth.asks:
        return _not_available(instrument_id, "DEPTH_EMPTY", read_at)
    stats_reader = getattr(ctx.provider, "latest_day_stats", None)
    stats = None if stats_reader is None else stats_reader(instrument_id, read_at)
    last_trade = None if stats is None or stats.last_trade_ts is None else datetime.datetime.fromtimestamp(
        stats.last_trade_ts, IST)
    return DepthOut(
        state="AVAILABLE", reason=None, instrument_id=instrument_id,
        bids=[DepthLevelOut(price=lv.price.quantize(PAISE), quantity=lv.quantity) for lv in depth.bids],
        asks=[DepthLevelOut(price=lv.price.quantize(PAISE), quantity=lv.quantity) for lv in depth.asks],
        day_open=_money(stats, "day_open"), day_high=_money(stats, "day_high"), day_low=_money(stats, "day_low"),
        prev_close=_money(stats, "prev_close"), last_trade_at=last_trade, read_at=read_at)


def _money(stats: Any, name: str) -> Decimal | None:
    value = None if stats is None else getattr(stats, name)
    return None if value is None else value.quantize(PAISE)


# ---- routes ---------------------------------------------------------------------------------------------------------

def get_feed() -> LiveFeed | None:
    """The running app's shared feed (or None): tests override this dependency."""
    return live.current_feed()


def get_picker_reader() -> ChainReader:
    """The stored-catalogue seam of the strikes read: tests override this dependency with a fake catalogue."""
    return stored_chain


def get_futures_reader() -> FuturesReader:
    return stored_futures


@router.get(STRIKES_PATH, response_model=StrikesOut)
async def leg_picker_strikes(  # noqa: PLR0913 - one query parameter or seam each
        underlying: Annotated[Underlying, Query()],
        expiry: Annotated[datetime.date, Query()],
        feed: Annotated[LiveFeed | None, Depends(get_feed)],
        now: Annotated[AnswerClock, Depends(get_answer_clock)],
        reader: Annotated[ChainReader, Depends(get_picker_reader)],
        width: Annotated[Width, Query(description="strikes either side of ATM: 10, 20, 30 or 40")] = DEFAULT_WIDTH,
) -> StrikesOut:
    return strikes_answer(feed, underlying, expiry, width, await reader(underlying, expiry), now)


@router.get(FUTURES_PATH, response_model=FuturesOut)
async def leg_picker_futures(
        underlying: Annotated[Underlying, Query()],
        feed: Annotated[LiveFeed | None, Depends(get_feed)],
        now: Annotated[AnswerClock, Depends(get_answer_clock)],
        reader: Annotated[FuturesReader, Depends(get_futures_reader)],
) -> FuturesOut:
    return futures_answer(feed, underlying, await reader(underlying), now)


@router.get(DEPTH_PATH, response_model=DepthOut)
async def leg_picker_depth(
        instrument_id: Annotated[InstrumentId, Query()],
        feed: Annotated[LiveFeed | None, Depends(get_feed)],
        now: Annotated[AnswerClock, Depends(get_answer_clock)],
) -> DepthOut:
    return depth_answer(feed, instrument_id, now)
