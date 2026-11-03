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

import asyncio
import contextlib
import datetime
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal
from typing import Any

from ofo.adjustment.approaches import ChainRow, Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.charges.round_trip import ChargesNotComputable
from ofo.engine import adjust_history as ah
from ofo.engine.black_scholes import Greeks, year_fraction
from ofo.engine.chain_values import chain_model
from ofo.engine.legs import Instrument
from ofo.instruments.models import INDEX_ROWS, is_lot_aligned
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.quote import planning_price_usable
from ofo.marketdata.spot_source import SourceReading, SourceState, resolve_spot
from ofo.timeutil import IST, SESSION_CLOSE
from ofo.tracking.orderbook import net_positions

from ofo_app import live_market, paper_book, scenario_mode, tracked_contracts
from ofo_app.db import get_sessionmaker
from ofo_app.live_push import no_listener
from ofo_app.routes.adjustment import MarketInputs, Tracked
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import feed_windows_of, market_state, read_booked, server_now

log = logging.getLogger(__name__)
_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)
_SATURDAY = 5
_CLOSE = SESSION_CLOSE  # one home: ofo.timeutil


class TrackedUnreadable(Exception):
    """The strategy exists for this user but its open legs cannot be read as option legs (named, never guessed)."""


class TrackedExited(TrackedUnreadable):
    """Every leg of the strategy is exited (no open leg): the strategy closed (GC-ADJ2 step 5, REQ-112 AC-2 lapse)."""


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
        raise TrackedExited("no open option leg")
    paid: Decimal | None = None
    if rates is not None:
        fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price, True) for o in orders]
        try:
            paid = paper_charges(fills, underlying, rates).shown
        except ChargesNotComputable:
            paid = None
    booked = await read_booked(strategy_id)  # None: could not be read (never 0)
    # expiry kind and today are set by the route from the market reader (the calendar and clock live there)
    # adjustments_used: the engine's adjustment history over the stored orders (the count the history page shows);
    # None when the history cannot be read (the compare's "-" with that reason, never 0)
    used = history_count(orders, lambda cid: found[cid].stored is not None
                         and found[cid].stored.listed.contract.instrument_type in _OPTION_TYPES)
    return Tracked(Position(underlying, lot, "", datetime.date.min, tuple(legs)), booked, paid,
                   adjustments_used=used)


def history_count(orders: Any, is_option: Any) -> int | None:
    """``adjustment_history(...).totals.adjustments_used`` over the stored paper orders (REQ-156 AC-2; the one
    counter the history page uses). No adjustment yet -> 0; the history cannot be read (a contract with no stored row,
    an order the engine refuses) -> None, logged; closed-and-reopened legs are never counted by guess."""
    try:
        history = ah.adjustment_history(
            [ah.HistoryOrder(str(o.order.contract_id), o.order.side, o.order.quantity, o.order.price,
                             o.order.kind, o.order.placed_at, is_option=bool(is_option(o.order.contract_id)))
             for o in orders], {}, adjustments_max=None)
    except (ValueError, KeyError, AttributeError, TypeError):
        log.exception("adjustment history unreadable: adjustments used not available")
        return None
    return history.totals.adjustments_used


class _GuardsUnreadable:
    """The answer of ``read_guards`` when the playbook could not be read (store error, malformed body): distinct from
    None (no playbook matches the shape) so the reply can say the limits were not applied."""

    def __repr__(self) -> str:
        return "GUARDS_UNREADABLE"


GUARDS_UNREADABLE = _GuardsUnreadable()


async def read_guards(strategy_id: int, position: Position, spot: Decimal | None,
                      listed: list | None) -> dict[str, Any] | None | _GuardsUnreadable:
    """The ``guards`` of the strategy playbook (its own plan, else the active playbook of its type; ADR-230 (1)).
    Answer states: a mapping (limits; empty = none set), None (the shape matches no playbook), ``GUARDS_UNREADABLE``
    (store error or malformed body: logged by its class only; the route says the limits were not applied)."""
    from ofo_app import adjustment_check  # noqa: PLC0415 - it imports the route module's dataclasses
    try:
        async with get_sessionmaker()() as db:
            stype = adjustment_check.strategy_type(position, spot, listed)
            resolved = await adjustment_check.resolve(db, current_user_ref(), strategy_id, stype)
        return adjustment_check.guards_of_body(resolved.body)
    except Exception as exc:  # noqa: BLE001 - any failure of the read is "unreadable", never a silent skip
        log.warning("adjustment guards: strategy %s playbook unreadable (%s)", strategy_id, type(exc).__name__)
        return GUARDS_UNREADABLE


# ---- market -----------------------------------------------------------------------------------------------------

def _scenario() -> Any:
    return scenario_mode.current()


def listed_options(provider: Any, underlying: str) -> list:
    """Every listed CE / PE contract of ``underlying`` with an expiry, from the provider's instrument master (the one
    listing the screen and the background build the adjustment chain rows from)."""
    return [lc for lc in provider.instrument_master()
            if lc.contract.name == underlying and lc.contract.expiry is not None
            and lc.contract.instrument_type in _OPTION_TYPES]


def chain_rows(listed: Iterable[Any], expiry: datetime.date, quotes: Mapping[str, Any],
               greeks_of: Callable[[str, Any], Greeks | None],
               scn: Any) -> tuple[tuple[ChainRow, ...], dict[str, str], dict[str, Greeks]]:
    """THE one builder of the adjustment chain rows of one expiry: a row for EVERY listed contract of it (quoted or
    not), so an approach (T-19, the Compare) sees every strike it may trade. The screen's ``read_market`` and the
    background's ``market_inputs`` both call it; only the Greeks source differs (``greeks_of(instrument id, quote or
    None)``: the chain model on the screen, the shared per-option figures in the background). Scenario mode adds each
    row's tradable / low-OI state. Returns (rows, trading symbol -> instrument id, trading symbol -> per-unit
    Greeks)."""
    rows: list[ChainRow] = []
    ids: dict[str, str] = {}
    leg_greeks: dict[str, Greeks] = {}
    for lc in listed:
        c = lc.contract
        if c.expiry != expiry:
            continue
        iid = f"{c.exchange_segment}:{c.exchange_token}"
        symbol = lc.broker_refs[0].broker_symbol
        q = quotes.get(iid)
        g = greeks_of(iid, q)
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
        if g is not None:
            leg_greeks[symbol] = g
    return tuple(rows), ids, leg_greeks


#: F-92: the longest the Compare waits for the first live quote of a leg of the position that nobody else holds
#: (the paper book's own wait, ``routes.paper.FORWARD_WAIT_S``)
LEG_WAIT_S = 3.0
LEG_POLL_S = 0.05


async def chain_quotes(provider: Any, underlying: str, expiry: datetime.date, leg_ids: list[str],  # noqa: PLR0913
                       feed: Any, index_id: str | None = None) -> dict[str, Any]:
    """The held quotes of one expiry, plus the position's OWN legs (F-92). The feed's book lists only contracts somebody
    holds, so a leg nobody else holds (the far hedge: 400 points from spot) was absent although the paper book, which
    holds its legs for the read (``routes.paper._hold_until_ready``), priced it. A leg missing from the book is held on
    the shared fan-out until its first quote arrives or ``LEG_WAIT_S`` passes, and the hold is ALWAYS released (timeout,
    error, cancel). Answer states of a leg: quoted (read as is, no hold) / not held yet (held, then quoted) / no quote
    after the wait or no token or no feed or provider disconnected (stays absent: the row is unpriced, never 0) /
    stale and market closed (the quote the book holds, judged by the same planning rule as before).
    ``index_id``: the index of the underlying, held with the rest when the book has no index quote (the chain model's
    forward needs it); it is ready when ``provider.underlying_quote`` answers."""
    quotes = {q.instrument_id: q for q in provider.option_chain_snapshot(underlying, expiry)}
    missing = [i for i in dict.fromkeys(leg_ids) if i not in quotes]
    index_wait = index_id is not None and provider.underlying_quote(underlying) is None
    if index_wait:
        missing.append(index_id)

    def ready(snap: Mapping[str, Any]) -> bool:
        return (all(i in snap for i in missing if i != index_id)
                and (not index_wait or provider.underlying_quote(underlying) is not None))
    if not missing or feed is None:
        return quotes
    try:
        handle = feed.fanout.subscribe(no_listener, missing, max_queue=1)
    except KeyError:  # a contract the provider has no token for: nothing was subscribed, the unpriced answer stands
        return quotes
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + LEG_WAIT_S
        while True:
            await asyncio.sleep(LEG_POLL_S)
            quotes = {q.instrument_id: q for q in provider.option_chain_snapshot(underlying, expiry)}
            if ready(quotes) or not provider.status().connected or loop.time() >= deadline:
                return quotes
    finally:
        with contextlib.suppress(Exception):
            feed.fanout.unsubscribe(handle)


def window_ids(listed: Iterable[Any], underlying: str, expiry: datetime.date, spot: Decimal | None,
               each_side: int) -> list[str]:
    """The instrument ids of the near-the-money calls and puts of ``expiry`` (``chain_push.window_strikes``, the rule
    the background worker also uses). Answer states: spot live -> the window; no spot / no live price / expiry not
    listed -> [] (legs only, as before); a window strike without a contract -> skipped."""
    from ofo_app.chain_push import window_strikes  # noqa: PLC0415 - chain_push imports the app layer
    by_key = {(lc.contract.strike, lc.contract.instrument_type):
              f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"
              for lc in listed if lc.contract.name == underlying and lc.contract.expiry == expiry}
    grid = sorted({k[0] for k in by_key if k[0] is not None})
    window = window_strikes(grid, spot, each_side)
    return [i for k in window for side in ("CE", "PE") if (i := by_key.get((k, side))) is not None]


async def _window_spot(ctx: Any, underlying: str, spot_q: Any, now: datetime.datetime) -> Decimal | None:
    """The spot the window is centred on: the SAME answer the routes resolve (``resolve_spot``: feed, else the REST
    index quote, else the last close), so a user with only a strategy open (nobody holds the index on the feed) still
    gets a window. The REST quote is asked only when the feed's own reading is not usable. None: no spot at all."""
    feed = (SourceReading(SourceState.ABSENT) if spot_q is None
            else SourceReading(SourceState.STATED, spot_q.ltp, spot_q.timestamp))
    answer = resolve_spot(feed, None, None, now=now, windows=feed_windows_of(ctx))
    if answer.available:
        return answer.value
    try:
        rest = await read_rest_spot(underlying)
    except Exception as exc:  # noqa: BLE001 - a REST failure is "no REST spot", never a failed check
        log.warning("adjustment window: REST spot unreadable (%s)", type(exc).__name__)
        rest = SourceReading(SourceState.FAILED)
    closed = market_state(ctx, now).closed
    last_close = read_last_close(spot_q, closed, _scenario(), now)
    return resolve_spot(feed, rest, last_close, now=now, windows=feed_windows_of(ctx)).value


def own_leg_ids(position: Position, listed: Iterable[Any]) -> list[str]:
    """The instrument ids of the position's legs (by trading symbol, the key the chain rows and the margin use)."""
    wanted = {x.tradingsymbol for x in position.legs}
    return [f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed
            if lc.broker_refs[0].broker_symbol in wanted]


async def read_market(tracked: Tracked, ctx: Any) -> MarketInputs:
    if ctx is None:  # not connected: no chain, no feed spot (the REST reader and the reasons still answer)
        now = server_now()
        return MarketInputs((), {}, None, None, None, SourceReading(SourceState.ABSENT),
                            SourceReading(SourceState.ABSENT), now)
    now = ctx.clock()
    position = tracked.position
    underlying, expiry = position.underlying, position.legs[0].expiry
    provider = ctx.provider
    listed = listed_options(provider, underlying)
    scn = _scenario()
    expiry_kind = _expiry_kind(provider, underlying, expiry, listed, scn)
    live = live_market.current_feed()  # F-92: the position's own legs are held for the read, like the paper book's
    spot_q = provider.underlying_quote(underlying)
    window_spot = await _window_spot(ctx, underlying, spot_q, now)
    # REQ-165 AC-5 / REQ-155: the chain model needs near-the-money quotes for its forward, so the window is held too
    # (GC-IC1: without a chain screen open for the expiry there was no forward, no Greeks, no ATM IV)
    from ofo_app.chain_push import index_id_of  # noqa: PLC0415 - chain_push imports the app layer
    wanted = own_leg_ids(position, listed) + window_ids(listed, underlying, expiry, window_spot,
                                                              ctx.chain_strikes_each_side)
    # nobody holds the index: hold it for the read too
    held_index = index_id_of(ctx, underlying) if spot_q is None else None
    quotes = await chain_quotes(provider, underlying, expiry, wanted, live, held_index)
    spot_q = provider.underlying_quote(underlying)  # the held index's first quote, if it came
    closed = market_state(ctx, now).closed
    model = chain_model(list(quotes.values()), spot_q, expiry, now, ctx.rate, ctx.forward_quality, market_closed=closed)

    def model_greeks(iid: str, _q: Any) -> Greeks | None:  # the chain's engine Greeks per unit (chain_model)
        g = model.greeks.get(iid)
        return None if g is None else Greeks(g.delta, g.gamma if g.gamma_exact is None else g.gamma_exact, g.theta,
                                             g.vega)
    rows, ids, leg_greeks = chain_rows(listed, expiry, quotes, model_greeks, scn)
    forward = fwd_model = None
    try:
        fwd_model = parity_forward(list(quotes.values()), spot_q, expiry, now, ctx.rate, ctx.forward_quality)
        forward = fwd_model.forward
    except (ForwardUnavailable, ValueError, ArithmeticError):
        forward = fwd_model = None
    leg_ivs = {sym: model.greeks[iid].iv for sym, iid in ids.items()  # the chain model's IV of each own leg (1b)
               if iid in model.greeks and sym in {x.tradingsymbol for x in position.legs}}
    try:
        years = year_fraction(now, expiry)
    except ValueError:
        years = None
    vol = _atm_vol(rows, ids, model.greeks, forward)
    feed = (SourceReading(SourceState.ABSENT) if spot_q is None
            else SourceReading(SourceState.STATED, spot_q.ltp, spot_q.timestamp))
    return MarketInputs(tuple(rows), ids, forward, years, vol, feed, read_last_close(spot_q, closed, scn, now), now,
                        expiry_kind, leg_greeks, fwd_model, leg_ivs)


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


def future_expiries(provider: Any, underlying: str) -> frozenset[datetime.date]:
    """The expiries of every listed non-option contract (the index futures) of ``underlying``."""
    return frozenset(lc.contract.expiry for lc in provider.instrument_master()
                     if lc.contract.name == underlying and lc.contract.instrument_type not in _OPTION_TYPES
                     and lc.contract.expiry is not None)


def _expiry_kind(provider: Any, underlying: str, expiry: datetime.date, listed: list, scn: Any) -> str:
    return expiry_kind_of(expiry, listed, future_expiries(provider, underlying), scn)


def expiry_kind_of(expiry: datetime.date, listed: Iterable[Any], futures: frozenset[datetime.date], scn: Any) -> str:
    """THE one expiry-kind rule (the screen's ``read_market`` and the background's ``market_inputs`` both call it).
    Monthly = the expiry a FUTURE of the underlying also expires on (index futures are monthly only); with no
    future listed, the last listed option expiry of its month. Scenario mode: the scenario's own stated kind."""
    if scn is not None and scn.data.get("expiry_kind") in ("weekly", "monthly"):
        return str(scn.data["expiry_kind"])
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
