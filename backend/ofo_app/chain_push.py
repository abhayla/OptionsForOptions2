"""The Option Chain read and its live push (W-116; REQ-029 AC-1/AC-2/AC-4/AC-6/AC-8, REQ-049 AC-2). Framework-free.

# Adapted from abhayla/algochanakya@bf9faf7 backend/app/services/options/option_chain_live_engine.py (rows keyed by
# strike, CE/PE sides; the ATM pick ``min(strikes, key=abs(strike - spot))``, line 391) and
# backend/app/api/routes/optionchain.py (one chain answer for one underlying and expiry). Changed for this project:
# strikes and contracts come from the stored catalogue only (never from the feed or a computed step), money is Decimal
# and leaves as a 2-decimal string, the platform-wide snapshot/EOD fallbacks, IV and Greeks are dropped (IV is
# Advanced-only and engine-owned: REQ-029 AC-2, ADR-008/056), and the push is a per-connection class on the ONE shared
# fan-out (ADR-068), like ``live_push.StrategyPush``.

One :class:`ChainPush` serves one browser connection of the read-only chain socket. The client sends a
:class:`ChainRequest` ``{underlying, expiry, strikes_each_side}``. The push reads that expiry's contracts from the
stored catalogue (one short database read per applied request, never per push: finding db-role-limit-below-pool-size),
picks ``strikes_each_side`` catalogue strikes either side of the ATM strike from the LIVE spot (no spot: no strikes and
no guessed ATM), subscribes those CE/PE contracts and the index on the shared ``FanOut`` and pushes :func:`chain_answer`
- the same function the REST read returns - only when something the screen shows changed. EVERY outbound message (a
push or the error reply to invalid client messages, coalesced into one) passes ONE gate of ``MIN_PUSH_INTERVAL``
seconds, so the socket never sends more than one message a second for any reason; a pending push takes the gate before
a pending error reply, and error replies go at most once every ``ERROR_REPLY_SECONDS`` (#439). Every subscription
change (an applied request, latest wins; a re-pick once the spot arrives) happens at most once a second, so a client
cannot drive catalogue reads or Kite subscription changes faster; when the live ATM leaves the window it re-centres
around it at most every ``RECENTRE_SECONDS``. A change takes the new subscription BEFORE releasing the old one (the
order of ``StrategyPush._replace``, so a shared instrument such as the index is never dropped and re-added). A contract
the provider does not know (KeyError) makes only THAT cell unavailable; the rest of the window still streams.
Everything is released when the connection ends, on every exit path.

REQ-029 AC-4: LTP and bid/ask stream at the push rate (a 0 bid or ask reads null, F-29); OI and OI change are refreshed
at most every ``OI_REFRESH_SECONDS``. IV is NOT carried: it needs the one calculation engine (ADR-008), so IV's lower
frequency is the remaining part of AC-4.

Liveness is this connection's own: LIVE only while THIS push holds its subscription (finding
liveness-from-shared-subscribers); each cell carries its quote's OWN health as the provider gives it at the moment of
the answer, so a quote that went stale is never shown as available (REQ-049 AC-2; no new staleness rule here: finding
staleness-by-last-change-age). ``change`` is always null: the normalised feed carries no previous close for a contract,
and REQ-029 AC-2's change is never computed from anything else. No order, basket, margin or execute call exists here
(REQ-029 AC-6).
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from ofo.chain_values import CellValues, ChainGreeks, cell_values, chain_greeks
from ofo.errors import render
from ofo.instruments import eligibility as el
from ofo.instruments.eligibility import EligibilityStatus
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import PAISE  # money leaves the API as a 2-decimal string
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ofo_app.api_models import ApiModel, InstrumentId, Money
from ofo_app.catalogue_picker import PickableContract
from ofo_app.live_push import MIN_PUSH_INTERVAL, POLL_SECONDS, Channel, ChannelClosed, LiveFeed
from ofo_app.routes.outcome import HealthCode, MarketContext

log = logging.getLogger(__name__)

#: The most strikes either side of ATM a chain may ask for (REQ-087 AC-3: 10, 20, 30 or 40; was 15 at W-116, design: "15 strikes either side at first
#: open", docs/design/screens-research-2026-10-19.md). It bounds one socket's subscription to 162 contracts (81
#: strikes, CE and PE) and the index.
MAX_STRIKES_EACH_SIDE = 40
#: REQ-087 AC-3: the user's choices for strikes either side of ATM, and the default for a user who never chose.
STRIKES_CHOICES = (10, 20, 30, 40)
DEFAULT_STRIKES_EACH_SIDE = 10
#: REQ-029 AC-4 / Q46: "OI and IV update at a lower frequency" than LTP and bid/ask. Q46 names no number; 5 s is the
#: orchestrator's technical decision (W-116 round 2). The same interval bounds how often the window re-centres.
OI_REFRESH_SECONDS = 5.0
RECENTRE_SECONDS = OI_REFRESH_SECONDS
#: #439: invalid client messages are answered with at most one error reply per this many seconds, and only in a slot no
#: data push needs (a pending push takes the one gate first). 5 s is the orchestrator's technical decision.
ERROR_REPLY_SECONDS = 5.0
_SIDES = ("CE", "PE")
#: (oi, oi_change) as last shown, per contract id
SlowValues = dict[str, tuple[int | None, int | None]]

#: Why a chain answer has no rows (None when it has them). ``NOT_CONNECTED`` answers carry none either: then the state
#: says so and this is None.
RowsMissing = Literal["SPOT_MISSING", "EXPIRY_UNKNOWN", "CATALOGUE_EMPTY", "CATALOGUE_UNREADABLE"]

#: REQ-030 AC-13/AC-16, ADR-132 (3): what Zerodha permits for one contract, read from the existing eligibility source
#: (``eligibility_from_zerodha.leg_statuses``, the same list the Execute gate trusts; no new source). A contract is
#: permitted ONLY when its status says tradable; a missing or unreadable status is "unknown", never permitted.
Permission = Literal["permitted", "not_listed", "restricted"]
#: Why a cell is not permitted (None when it is). The screen shows one fixed line per reason (ADR-132 (3)).
UnavailableReason = Literal["not_listed", "restricted", "unknown"]
_PERMISSIONS = ("permitted", "not_listed", "restricted")
#: The list-state reason codes (ADR-104 (a)): not in Zerodha's list today (expired, delisted, retired...).
_NOT_LISTED_REASONS = frozenset({el.REASON_NOT_IN_LIST, el.REASON_EXPIRED, el.REASON_DELISTED, el.REASON_RETIRED,
                                 el.REASON_NO_ZERODHA_ROW, el.REASON_INDEX, el.REASON_NO_EXPIRY})


class ChainRequest(BaseModel):
    """What the chain socket's client sends (and the REST read's query): one underlying, one expiry, a strike count."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    underlying: Literal["NIFTY", "SENSEX"]
    expiry: datetime.date
    strikes_each_side: StrictInt = Field(default=DEFAULT_STRIKES_EACH_SIDE, ge=1, le=MAX_STRIKES_EACH_SIDE)


class ChainCellOut(ApiModel):
    instrument_id: InstrumentId  # the catalogue's contract id (segment:token)
    ltp: Money | None  # the last price as given; None when there is none or the answer is not live
    bid: Money | None  # the best bid as given; None when there is none or it is 0 (F-29: 0 is "no price")
    ask: Money | None  # the best ask as given; None when there is none or it is 0 (F-29)
    change: Money | None  # always None: the feed carries no previous close (REQ-029 AC-2, never computed otherwise)
    oi: int | None  # on the socket refreshed at most every OI_REFRESH_SECONDS (REQ-029 AC-4, Q46)
    oi_change: int | None  # as the quote gives it, refreshed with ``oi``
    volume: int | None
    health: HealthCode | None  # the quote's own health; None in the not-live answer
    at: datetime.datetime | None  # the quote's own time (aware)
    #: REQ-030 AC-16: True only when Zerodha's eligibility says this contract is tradable now (fail closed)
    permitted: bool
    unavailable_reason: UnavailableReason | None  # why not, when it is not permitted (ADR-132 (3)); else None
    #: W-124 (REQ-087 AC-1/AC-4/AC-5, REQ-029 AC-3): server-computed extras; None = a dash on the screen, never 0.
    lot_size: int  # the instrument file's lot size: the "per lot" heading and multiplier (REQ-087 AC-1)
    per_lot: Money | None  # LTP x lot size
    intrinsic: Money | None  # against the spot (the index), labelled so
    time_value: Money | None  # LTP minus intrinsic
    breakeven: Money | None
    breakeven_pct: Money | None  # signed, against the spot
    delta: Money | None  # the engine's Greeks (not the vendor's), 4 dp
    gamma: Money | None
    theta: Money | None
    vega: Money | None


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
    #: instrument_id -> permission. A contract ABSENT here is "unknown" (the eligibility read failed): never permitted.
    permissions: Mapping[str, Permission] = field(default_factory=dict)


ChainReader = Callable[[str, datetime.date], Awaitable[ChainCatalogue]]


def permission_of(status: EligibilityStatus | None) -> Permission | None:
    """One contract's permission from its eligibility status. None (no status: no load, no row) -> None = unknown.
    Tradable -> permitted. Not tradable for a list reason -> not_listed; any other reason (Zerodha's own refusal text,
    ADR-058/059 restrictions) -> restricted. Anything but an explicit ``tradable is True`` is never permitted."""
    if status is None:
        return None
    if status.tradable is True:
        return "permitted"
    return "not_listed" if status.reason in _NOT_LISTED_REASONS else "restricted"


def permissions_for(contracts: Sequence[PickableContract],
                    statuses: Sequence[EligibilityStatus | None]) -> dict[str, Permission]:
    """instrument_id -> permission for each contract, in order; a contract with no status is left out (unknown)."""
    out: dict[str, Permission] = {}
    for contract, status in zip(contracts, statuses, strict=True):
        permission = permission_of(status)
        if permission is not None:
            out[contract.instrument_id] = permission
    return out


async def _read_permissions(session: Any, contracts: Sequence[PickableContract],
                            today: datetime.date) -> dict[str, Permission]:
    """The eligibility of the shown contracts, read in the catalogue's own session. A read that fails says nothing
    (every contract is then "unknown"): never an error and never a guessed "permitted"."""
    from ofo_app.eligibility_from_zerodha import leg_statuses  # noqa: PLC0415 - late, like the catalogue reader

    try:
        statuses = await leg_statuses(session, [c.contract_id for c in contracts], today)
    except (SQLAlchemyError, OSError, RuntimeError) as exc:
        log.warning("option chain: eligibility could not be read: %s", type(exc).__name__)
        return {}
    return permissions_for(contracts, statuses)


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
            options = tuple(r for r in rows if r.instrument_type in _SIDES)
            permissions = await _read_permissions(session, options, today)
    except (SQLAlchemyError, OSError, RuntimeError) as exc:  # no database, a refused or lost connection
        log.warning("option chain: the catalogue could not be read: %s", type(exc).__name__)
        return ChainCatalogue((), (), unreadable=True)
    return ChainCatalogue(expiries, options, permissions)


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


def _given_money(value: Decimal | None) -> Decimal | None:
    """A price as given, 2 decimals; None when absent or 0 (the one zero rule, F-29)."""
    return value.quantize(PAISE) if value is not None and is_live_price(value) else None


def _permission(catalogue: ChainCatalogue, contract: PickableContract) -> tuple[bool, UnavailableReason | None]:
    """(permitted, reason) of one cell. Permitted only on an explicit "permitted"; a missing or odd value is unknown."""
    value = catalogue.permissions.get(contract.instrument_id)
    if value == "permitted":
        return True, None
    return False, value if value in _PERMISSIONS else "unknown"  # type: ignore[return-value]


def _extras(contract: PickableContract, ltp: Decimal | None, spot: Decimal | None,
            greeks: Mapping[str, ChainGreeks]) -> dict[str, Any]:
    """The W-124 fields of one cell: the pure maths of ``ofo.chain_values`` (per-lot, intrinsic, time value, breakeven)
    and the engine's Greeks for this contract when its price gave an implied volatility."""
    v: CellValues = cell_values(contract.instrument_type, contract.strike, ltp, spot, contract.lot_size)
    g = greeks.get(contract.instrument_id)
    return {"lot_size": contract.lot_size, "per_lot": v.per_lot, "intrinsic": v.intrinsic, "time_value": v.time_value,
            "breakeven": v.breakeven, "breakeven_pct": v.breakeven_pct,
            "delta": None if g is None else g.delta, "gamma": None if g is None else g.gamma,
            "theta": None if g is None else g.theta, "vega": None if g is None else g.vega}


def _cell(contract: PickableContract, quote: NormalizedQuote | None, slow: SlowValues | None,  # noqa: PLR0913
          catalogue: ChainCatalogue, spot: Decimal | None = None,
          greeks: Mapping[str, ChainGreeks] | None = None) -> ChainCellOut:
    permitted, reason = _permission(catalogue, contract)
    if quote is None:  # held, but no quote yet, or a contract the provider does not know: shown as such
        return ChainCellOut(instrument_id=contract.instrument_id, ltp=None, bid=None, ask=None, change=None, oi=None,
                            oi_change=None, volume=None, health="unavailable", at=None, permitted=permitted,
                            unavailable_reason=reason, **_extras(contract, None, spot, {}))
    oi, oi_change = (quote.oi, quote.oi_change) if slow is None else slow.get(contract.instrument_id,
                                                                              (quote.oi, quote.oi_change))
    return ChainCellOut(instrument_id=contract.instrument_id, ltp=_given_money(quote.ltp), bid=_given_money(quote.bid),
                        ask=_given_money(quote.ask), change=None, oi=oi, oi_change=oi_change, volume=quote.volume,
                        health=quote.health.value, at=quote.timestamp, permitted=permitted, unavailable_reason=reason,
                        **_extras(contract, _given_money(quote.ltp), spot, greeks or {}))


def window_quotes(ctx: MarketContext, req: ChainRequest) -> dict[str, NormalizedQuote]:
    return {q.instrument_id: q for q in ctx.provider.option_chain_snapshot(req.underlying, req.expiry)}


def _rows(ctx: MarketContext, req: ChainRequest, catalogue: ChainCatalogue,  # noqa: PLR0913
          window: tuple[Decimal, ...], slow: SlowValues | None,
          unknown: frozenset[str]) -> list[ChainRowOut]:
    every = window_quotes(ctx, req)
    spot = live_spot(ctx, req.underlying)
    greeks = (chain_greeks(every.values(), _spot_quote(ctx, req.underlying), req.expiry, ctx.clock(), ctx.rate)
              if spot is not None else {})
    quotes = {i: q for i, q in every.items() if i not in unknown}
    by_strike: dict[Decimal, dict[str, PickableContract]] = {s: {} for s in window}
    for c in catalogue.contracts:
        if c.strike in by_strike and c.instrument_type in _SIDES:
            by_strike[c.strike][c.instrument_type] = c
    out = []
    for strike in window:
        sides = by_strike[strike]
        ce, pe = sides.get("CE"), sides.get("PE")
        out.append(ChainRowOut(strike=strike.quantize(PAISE),
                               ce=None if ce is None else _cell(ce, quotes.get(ce.instrument_id), slow, catalogue, spot, greeks),
                               pe=None if pe is None else _cell(pe, quotes.get(pe.instrument_id), slow, catalogue, spot,
                                                                greeks)))
    return out


def chain_answer(ctx: MarketContext | None, req: ChainRequest, catalogue: ChainCatalogue,  # noqa: PLR0913
                 window: tuple[Decimal, ...] | None, *, live: bool,
                 now: Callable[[], datetime.datetime], slow: SlowValues | None = None,
                 unknown: frozenset[str] = frozenset()) -> ChainOut:
    """The ONE answer behind the REST read and the socket push. Not live (no feed, the page's own socket is down, or
    this connection holds nothing): NOT_CONNECTED, no rows, no number; only the spot's last value time is kept.
    ``slow``: the OI values the socket last showed (None: as the quotes give them); ``unknown``: contracts the provider
    does not know, shown unavailable."""
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
        rows_missing=missing,
        rows=[] if missing is not None or window is None else _rows(ctx, req, catalogue, window, slow, unknown),
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
        self._last_take: float | None = None  # every subscription change: an applied request, a re-pick, a re-centre
        self._shown: tuple | None = None
        self._last_send: float | None = None  # EVERY outbound message: a push or an error reply
        self._error_due = False  # invalid client messages since the last error reply: answered with ONE error, gated
        self._error_since: float | None = None  # when the pending error reply became due: aged ones beat a push
        self._last_error: float | None = None  # the last error reply: at most one every ERROR_REPLY_SECONDS
        self._unknown: set[str] = set()  # contracts of the request the provider does not know: shown unavailable
        self._slow: SlowValues = {}
        self._last_slow: float | None = None
        self.pushes = 0

    @property
    def _ctx(self) -> MarketContext | None:
        return None if self._feed is None else self._feed.ctx

    def _release(self) -> None:
        if self._handle is not None and self._feed is not None:
            self._feed.fanout.unsubscribe(self._handle)
        self._handle = None

    def _since(self, mark: float | None) -> float | None:
        return None if mark is None else self._monotonic() - mark

    def _gate_open(self) -> bool:
        """ONE gate for every outbound message (a push, an error reply): at most one a second, whatever the reason."""
        since = self._since(self._last_send)
        return since is None or since >= MIN_PUSH_INTERVAL

    async def _emit(self, message: Any) -> None:
        await self._channel.send(message)
        self._last_send = self._monotonic()

    def _take_message(self, raw: Any) -> None:
        try:  # extra="forbid": the REST read's ``fallback`` flag, or any unknown key, is refused here (#234)
            req = ChainRequest.model_validate(raw)
        except ValidationError:
            if not self._error_due:
                self._error_since = self._monotonic()
            self._error_due = True  # answered through the one gate: 50 bad messages in a second get ONE reply
            return
        self._pending = req  # the latest wins; the current one again is a refresh (AC-16): re-read

    def _may_take(self, interval: float) -> bool:
        since = self._since(self._last_take)
        return since is None or since >= interval

    async def _maybe_apply(self) -> None:
        if self._pending is None or not self._may_take(MIN_PUSH_INTERVAL):
            return  # at most one subscription change (catalogue read, Kite subscribe) a second
        req, self._pending = self._pending, None
        self._last_take = self._monotonic()
        catalogue = await self._reader(req.underlying, req.expiry)
        if req != self._req:
            self._unknown = set()
        self._take(req, catalogue)

    def _subscribe_known(self, ids: list[str]) -> int | None:
        """Subscribe ``ids`` on the fan-out. A contract the provider does not know (KeyError) is remembered and left
        out, so THAT cell reads unavailable and the rest of the window still streams; None when no id is known."""
        assert self._feed is not None  # noqa: S101 - called only with a feed
        fanout = self._feed.fanout
        ids = [i for i in ids if i not in self._unknown]
        if not ids:
            return None
        try:
            return fanout.subscribe(_ignore, ids)
        except KeyError:
            pass
        singles: list[int] = []  # one id at a time finds the unknown ones; the known stay held by the final handle
        try:
            for i in ids:
                try:
                    singles.append(fanout.subscribe(_ignore, [i]))
                except KeyError:
                    self._unknown.add(i)
            known = [i for i in ids if i not in self._unknown]
            return fanout.subscribe(_ignore, known) if known else None
        finally:
            for handle in singles:  # the final handle holds every known id, so no vendor unsubscribe happens here
                fanout.unsubscribe(handle)

    def _take(self, req: ChainRequest, catalogue: ChainCatalogue) -> None:
        """Subscribe the request's window and index, THEN release what was held (a shared id is never dropped)."""
        self._last_take = self._monotonic()
        window = pick_window(self._ctx, req, catalogue)
        new_handle = None
        if self._feed is not None:
            index_id = index_id_of(self._feed.ctx, req.underlying)
            new_handle = self._subscribe_known(window_ids(catalogue, window) + ([index_id] if index_id else []))
        self._release()
        self._handle, self._req, self._catalogue, self._window = new_handle, req, catalogue, window

    def _maybe_repick(self) -> None:
        """No spot when applied: pick once the spot arrives. The live ATM left the window: re-centre around it. Both
        are subscription changes, so each is tried at most once a second / once every RECENTRE_SECONDS."""
        if self._req is None or self._catalogue is None or self._handle is None:
            return
        if self._window is None:
            if self._may_take(MIN_PUSH_INTERVAL) and pick_window(self._ctx, self._req, self._catalogue) is not None:
                self._take(self._req, self._catalogue)
            return
        if not self._may_take(RECENTRE_SECONDS):
            return
        spot, grid = live_spot(self._ctx, self._req.underlying), strike_grid(self._catalogue)
        if spot is not None and grid and atm_strike(grid, spot) not in self._window:
            self._take(self._req, self._catalogue)

    def _slow_values(self) -> SlowValues:
        """OI and OI change as last shown, refreshed from the quotes at most every OI_REFRESH_SECONDS; a contract not
        shown yet takes its quote's value at once."""
        ctx, req = self._ctx, self._req
        if ctx is None or req is None:
            return self._slow
        since = self._since(self._last_slow)
        quotes = window_quotes(ctx, req)
        if since is None or since >= OI_REFRESH_SECONDS:
            self._slow = {i: (q.oi, q.oi_change) for i, q in quotes.items()}
            self._last_slow = self._monotonic()
        else:
            for i, q in quotes.items():
                self._slow.setdefault(i, (q.oi, q.oi_change))
        return self._slow

    def _error_may_go(self) -> bool:
        since = self._since(self._last_error)
        return since is None or since >= ERROR_REPLY_SECONDS

    async def _maybe_send(self) -> None:
        """One message through the one gate. A pending data push takes the slot FIRST (#439: a client sending one
        invalid message a second must not starve its own pushes); a pending error reply goes only in a slot no push
        needs, and at most once every ERROR_REPLY_SECONDS (the invalid messages in between are coalesced into it).
        An error reply that has waited ERROR_REPLY_SECONDS takes the next slot even over a pending push
        (never lost)."""
        if not self._gate_open():
            return
        waited = self._since(self._error_since) if self._error_due else None
        if waited is not None and waited >= ERROR_REPLY_SECONDS and self._error_may_go():
            await self._send_error()  # an error reply that has waited ERROR_REPLY_SECONDS takes this slot (never lost)
            return
        if self._req is not None and self._catalogue is not None:
            live = self._handle is not None
            body = chain_answer(self._ctx, self._req, self._catalogue, self._window, live=live, now=self._now,
                                slow=self._slow_values() if live else None, unknown=frozenset(self._unknown))
            shown = _shown_state(body)
            if shown != self._shown:  # something the screen shows changed: the push wins the slot
                await self._emit(body)
                self._shown = shown
                self.pushes += 1
                return
        if self._error_due and self._error_may_go():
            await self._send_error()

    async def _send_error(self) -> None:
        self._error_due, self._error_since = False, None
        await self._emit(render("user_input_request_invalid"))
        self._last_error = self._monotonic()

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
                    self._take_message(raw)
                await self._maybe_apply()
                self._maybe_repick()
                if self._handle is not None and self._feed is not None:
                    self._feed.fanout.pump_one(self._handle)
                await self._maybe_send()
        finally:
            if recv is not None:
                recv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await recv
            self._release()
