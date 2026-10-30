"""The real readers behind POST /api/strategies/{id}/adjustment-approaches (REQ-155, W-196): the default seams.

- ``read_tracked``: the paper strategy from the paper book, owner-checked in the query (``paper_book.load_owned``);
  each open contract's identity from ``tracked_contracts.resolve``; entry = the paper fills' average; booked P&L via
  ``routes.outcome.read_booked`` (None = could not be read, never 0); paid so far via ``paper_charges`` (None when the
  rates are unreadable or the orders cannot be priced, never 0). A contract that cannot be resolved, a non-option leg
  or a quantity that is not whole lots raises ``TrackedUnreadable`` (the route answers "not available"; it is not a
  "not found", and no leg is guessed).
- ``read_market``: the chain of the position's expiry from the SAME market context the outcome and leg-edit routes
  use (``outcome.get_market_context``; scenario mode feeds it): every listed contract of that expiry, its quote
  (none -> unpriced, never 0), the engine's delta (``chain_model``), listed / tradable / low-OI state (scenario: the
  scenario row; live: tradable as listed, low-OI ``unknown`` because Zerodha publishes no threshold, AC-8 warning);
  POP inputs: ``parity_forward``, ``year_fraction`` and the ATM call's implied volatility (each None when refused);
  the feed spot reading from the provider's index quote. The last close (ADR-212): the index quote the feed holds
  from the closed session (``planning_price_usable``) with its own time;
  scenario mode: the scenario's ``market.prev_close`` dated to the session before the scenario clock
  (null -> ABSENT). Market open or nothing held: ABSENT.
- ``read_rest_spot``: ``KiteReads.fetch_index_quote`` (the door's ``%20`` path) with the owner's session; in scenario
  mode the same client over the scenario's REST answer as its transport. Every answer state is named: no session ->
  ABSENT, a Kite error -> FAILED, the name missing from the reply -> NOT_FOUND, no ``last_price`` -> EMPTY.
"""
from __future__ import annotations

import datetime
import json
import logging
from decimal import Decimal
from typing import Any

from ofo.adjustment.approaches import ChainRow, Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.charges.round_trip import ChargesNotComputable
from ofo.engine.black_scholes import year_fraction
from ofo.engine.chain_values import chain_model
from ofo.engine.legs import Instrument
from ofo.instruments.models import INDEX_ROWS, is_lot_aligned
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.quote import planning_price_usable
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo.timeutil import IST
from ofo.tracking.orderbook import net_positions

from ofo_app import live_market, paper_book, scenario_mode, tracked_contracts
from ofo_app.db import get_sessionmaker
from ofo_app.routes.adjustment import MarketInputs, Tracked
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import market_state, read_booked, server_now

log = logging.getLogger(__name__)
_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)
_SATURDAY = 5
_CLOSE = datetime.time(15, 30)


class TrackedUnreadable(Exception):
    """The strategy exists for this user but its open legs cannot be read as option legs (named, never guessed)."""


def index_name(underlying: str) -> str | None:
    """``NSE:NIFTY 50`` / ``BSE:SENSEX`` from the one home of the index rows; None for any other underlying."""
    for (segment, _token), (name, owner) in INDEX_ROWS.items():
        if owner == underlying:
            return f"{segment.split('_')[0]}:{name}"
    return None


# ---- strategy ---------------------------------------------------------------------------------------------------

async def read_tracked(strategy_id: int, rates: ChargeRates | None) -> Tracked | None:
    async with get_sessionmaker()() as db:
        orders = await paper_book.load_owned(db, current_user_ref(), strategy_id)  # owner check in the query
        if not orders:
            return None  # not this user's, or no such strategy
        found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.order.contract_id
                                                                                         for o in orders}))}
    book = net_positions([o.order.as_paper() for o in orders], {})
    legs: list[PositionLeg] = []
    underlying = lot = None
    for p in book.positions:
        if p.net_quantity == 0:
            continue
        tc = found.get(int(p.instrument_id))
        if tc is None or tc.stored is None:
            raise TrackedUnreadable(f"contract {p.instrument_id} has no stored row")
        lc = tc.stored.listed
        c = lc.contract
        if c.instrument_type not in _OPTION_TYPES or p.average is None or c.lot_size <= 0 \
                or not is_lot_aligned(abs(p.net_quantity), c.lot_size):
            raise TrackedUnreadable(f"contract {p.instrument_id} is not a whole-lot option leg")
        underlying, lot = c.name, c.lot_size
        legs.append(PositionLeg("BUY" if p.net_quantity > 0 else "SELL", c.instrument_type, c.strike, c.expiry,
                                abs(p.net_quantity) // c.lot_size, p.average, lc.broker_refs[0].broker_symbol))
    if not legs or underlying is None or lot is None:
        raise TrackedUnreadable("no open option leg")
    paid: Decimal | None = None
    if rates is not None:
        fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price, True) for o in orders]
        try:
            paid = paper_charges(fills, underlying, rates).shown
        except ChargesNotComputable:
            paid = None
    booked = await read_booked(strategy_id)  # None: could not be read (never 0)
    # expiry kind and today are set by the route from the market reader (the calendar and clock live there)
    return Tracked(Position(underlying, lot, "", datetime.date.min, tuple(legs)), booked, paid)


# ---- market -----------------------------------------------------------------------------------------------------

def _scenario() -> Any:
    return scenario_mode.current()


async def read_market(tracked: Tracked, ctx: Any) -> MarketInputs:
    if ctx is None:  # not connected: no chain, no feed spot (the REST reader and the reasons still answer)
        now = server_now()
        return MarketInputs((), {}, None, None, None, SourceReading(SourceState.ABSENT),
                            SourceReading(SourceState.ABSENT), now)
    now = ctx.clock()
    position = tracked.position
    underlying, expiry = position.underlying, position.legs[0].expiry
    provider = ctx.provider
    listed = [lc for lc in provider.instrument_master()
              if lc.contract.name == underlying and lc.contract.expiry is not None
              and lc.contract.instrument_type in _OPTION_TYPES]
    scn = _scenario()
    expiry_kind = _expiry_kind(provider, underlying, expiry, listed, scn)
    quotes = {q.instrument_id: q for q in provider.option_chain_snapshot(underlying, expiry)}
    spot_q = provider.underlying_quote(underlying)
    closed = market_state(ctx, now).closed
    model = chain_model(list(quotes.values()), spot_q, expiry, now, ctx.rate, market_closed=closed)
    rows: list[ChainRow] = []
    ids: dict[str, str] = {}
    for lc in listed:
        c = lc.contract
        if c.expiry != expiry:
            continue
        iid = f"{c.exchange_segment}:{c.exchange_token}"
        symbol = lc.broker_refs[0].broker_symbol
        q = quotes.get(iid)
        g = model.greeks.get(iid)
        tradable, low_oi, blocked = True, "unknown", None
        if scn is not None:
            row = scn.rows_by_id.get(iid) or {}
            tradable = bool(row.get("tradable", True))
            low_oi = (row.get("low_oi") or {}).get("state", "unknown")
            blocked = (row.get("low_oi") or {}).get("blocked")
        rows.append(ChainRow(c.strike, c.instrument_type, expiry, symbol, None if q is None else q.ltp,
                             None if q is None else q.bid, None if q is None else q.ask,
                             None if g is None else g.delta, True, tradable, low_oi, blocked))
        ids[symbol] = iid
    forward = None
    try:
        forward = parity_forward(list(quotes.values()), spot_q, expiry, now, ctx.rate).forward
    except (ForwardUnavailable, ValueError, ArithmeticError):
        forward = None
    try:
        years = year_fraction(now, expiry)
    except ValueError:
        years = None
    vol = _atm_vol(rows, ids, model.greeks, forward)
    feed = (SourceReading(SourceState.ABSENT) if spot_q is None
            else SourceReading(SourceState.STATED, spot_q.ltp, spot_q.timestamp))
    return MarketInputs(tuple(rows), ids, forward, years, vol, feed, read_last_close(spot_q, closed, scn, now), now,
                        expiry_kind)


def read_last_close(spot_q: Any, market_closed: bool, scn: Any, now: datetime.datetime) -> SourceReading:
    """ADR-212 last close of the index, with its date. Scenario: ``market.prev_close`` (null / missing -> ABSENT) on the
    last weekday before the scenario clock, at the 15:30 close. Live: the quote the feed holds from the closed session
    (never in market hours); none held or not sound -> ABSENT."""
    if scn is not None:
        stated = scn.data["market"].get("prev_close")
        if stated is None:
            return SourceReading(SourceState.ABSENT)
        day = ist_today(now) - datetime.timedelta(days=1)
        while day.weekday() >= _SATURDAY:
            day -= datetime.timedelta(days=1)
        return SourceReading(SourceState.STATED, Decimal(str(stated)), datetime.datetime.combine(day, _CLOSE, IST))
    if spot_q is None or not market_closed or not planning_price_usable(spot_q, market_closed=True):
        return SourceReading(SourceState.ABSENT)
    return SourceReading(SourceState.STATED, spot_q.ltp, spot_q.timestamp)


def _expiry_kind(provider: Any, underlying: str, expiry: datetime.date, listed: list, scn: Any) -> str:
    """Monthly = the expiry a FUTURE of the underlying also expires on (index futures are monthly only); with no
    future listed, the last listed option expiry of its month. Scenario mode: the scenario's own stated kind."""
    if scn is not None and scn.data.get("expiry_kind") in ("weekly", "monthly"):
        return str(scn.data["expiry_kind"])
    futures = {lc.contract.expiry for lc in provider.instrument_master()
               if lc.contract.name == underlying and lc.contract.instrument_type not in _OPTION_TYPES
               and lc.contract.expiry is not None}
    if futures:
        return "monthly" if expiry in futures else "weekly"
    same_month = sorted({lc.contract.expiry for lc in listed
                         if (lc.contract.expiry.year, lc.contract.expiry.month) == (expiry.year, expiry.month)})
    return "monthly" if same_month and expiry == same_month[-1] else "weekly"


def _atm_vol(rows: list[ChainRow], ids: dict[str, str], greeks: Any, level: Decimal | None) -> Decimal | None:
    """The implied volatility of the call nearest the forward (the ATM IV); None when nothing gives one."""
    if level is None:
        return None
    calls = [r for r in rows if r.type == Instrument.CE.value and ids.get(r.tradingsymbol) in greeks]
    if not calls:
        return None
    atm = min(calls, key=lambda r: (abs(r.strike - level), -r.strike))
    return greeks[ids[atm.tradingsymbol]].iv


# ---- REST spot ----------------------------------------------------------------------------------------------------

async def read_rest_spot(underlying: str) -> SourceReading:
    """The REST index quote through ``live_market.index_spot`` (the Kite composition root owns the client); in
    scenario mode the scenario's REST answer is that client's transport."""
    name = index_name(underlying)
    if name is None:
        return SourceReading(SourceState.NOT_FOUND)
    scn = _scenario()
    answer = None
    if scn is not None:
        status, reply = scn.rest_index_quote()
        answer = (status, json.dumps(reply))
    return await live_market.index_spot(name, answer)


def ist_today(now: datetime.datetime) -> datetime.date:
    return now.astimezone(IST).date()
