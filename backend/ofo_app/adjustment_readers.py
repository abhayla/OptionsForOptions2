"""The real readers behind POST /api/strategies/{id}/adjustment-approaches (REQ-155, W-196): the default seams.

- ``read_tracked``: the paper strategy from the paper book, owner-checked in the query (``paper_book.load_owned``);
  each open contract's identity from ``tracked_contracts.resolve``; entry = the paper fills' average; booked P&L
  from the same orders' net book (an unreadable book raises, never 0); paid so far via ``paper_charges`` (None when the
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

import dataclasses
import datetime
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from ofo.adjustment.approaches import ChainRow, EntryFacts, Position, PositionLeg, entry_facts_of
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.charges.round_trip import ChargesNotComputable
from ofo.engine import adjust_history as ah
from ofo.engine.black_scholes import Greeks, year_fraction
from ofo.engine.chain_values import chain_model
from ofo.engine.legs import Instrument
from ofo.engine.model import close_if_expiry_day
from ofo.instruments.models import INDEX_ROWS, is_lot_aligned
from ofo.marketdata.day_open import index_day_open
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.quote import is_live_price, planning_price_usable, priced
from ofo.marketdata.spot_source import SourceReading, SourceState, feed_is_live, feed_reading, resolve_spot
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST, SESSION_CLOSE
from ofo.tracking.orderbook import net_positions

from ofo_app import (
    live_market,
    paper_book,
    regime_inputs,
    scenario_mode,
    tracked_book,
    tracked_contracts,
)
from ofo_app.catalogue_store import StoredContract, load_catalogue, load_contracts
from ofo_app.db import get_sessionmaker
from ofo_app.errors import Failure
from ofo_app.outcome_oi import oi_of
from ofo_app.read_door import NO_TOKEN, read_quotes
from ofo_app.routes.adjustment import MarketInputs, Tracked
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import feed_windows_of, market_state, server_now, spot_judging_now

log = logging.getLogger(__name__)
_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)
_SATURDAY = 5
_CLOSE = SESSION_CLOSE  # one home: ofo.timeutil


async def read_roll_inputs(strategy_id: int, db: Any = None) -> tuple[Any, Any]:
    """ADR-243: the strategy's roll-basis inputs, read ONCE per request: (its plan's settings layer, its entry facts).
    Answer states, each fail closed with a named reason (never a default): plan absent -> None (follow the user); plan
    read failed -> ``layers.Unreadable("plan_read_failed")``; entry facts stored -> ``EntryFacts``; none stored ->
    None; unreadable -> ``layers.Unreadable``. The caller (``adjustment_check.roll_basis_of``) turns both into the
    basis in force; an unreadable plan refuses every roll, missing entry facts refuse only "Entry distance" rolls.
    ``db``: the request's own session (a request uses ONE connection, #682); None for a caller with no request."""
    if db is not None:
        return await _roll_inputs_on(db, strategy_id)
    async with get_sessionmaker()() as own:
        return await _roll_inputs_on(own, strategy_id)


async def _roll_inputs_on(db: Any, strategy_id: int) -> tuple[Any, Any]:
    from ofo.settings import layers  # noqa: PLC0415 - read path only

    from ofo_app import playbook_store  # noqa: PLC0415 - read path only
    try:
        plan = await playbook_store.plan_for(db, current_user_ref(), strategy_id)
        layer: Any = None if plan is None else layers.strategy_layer(plan.body)
    except Exception:
        log.exception("roll basis: the plan of strategy %s could not be read", strategy_id)
        layer = layers.Unreadable("plan_read_failed")
    return layer, await entry_facts_in(db, strategy_id)


async def entry_facts_in(db: Any, strategy_id: int) -> Any:
    """ADR-243: the strategy's stored entry facts, as every roll-basis caller reads them (the Compare route through
    ``read_roll_inputs``, the screen check, the playbook test, the worker's rebuild). Answer states: stored ->
    ``EntryFacts``; none stored -> None; unreadable -> ``layers.Unreadable`` (named, never a guess)."""
    from ofo.settings import layers  # noqa: PLC0415 - read path only

    from ofo_app import entry_facts_store  # noqa: PLC0415 - read path only
    try:
        return await entry_facts_store.read(db, strategy_id)
    except entry_facts_store.EntryFactsUnreadable as exc:
        return layers.Unreadable(str(exc))


class TrackedUnreadable(Exception):
    """The strategy exists for this user but its open legs cannot be read as option legs (named, never guessed)."""


class TrackedExited(TrackedUnreadable):
    """Every leg of the strategy is exited (no open leg): the strategy closed (GC-ADJ2 step 5, REQ-112 AC-2 lapse).
    ``closed_at``: the trade's own close time (its last exit, settle or stop order), None when no order states one."""

    def __init__(self, *args: object, closed_at: datetime.datetime | None = None) -> None:
        super().__init__(*args)
        self.closed_at = closed_at


def index_name(underlying: str) -> str | None:
    """``NSE:NIFTY 50`` / ``BSE:SENSEX`` from the one home of the index rows; None for any other underlying."""
    for (segment, _token), (name, owner) in INDEX_ROWS.items():
        if owner == underlying:
            return f"{segment.split('_')[0]}:{name}"
    return None


# ---- strategy ---------------------------------------------------------------------------------------------------

async def read_tracked(strategy_id: int, rates: ChargeRates | None, db: Any = None,
                       kinds: Mapping[tuple[str, datetime.date], str] | None = None) -> Tracked | None:
    """``db``: the request's own session (a request uses ONE connection, #682); None for the worker, which has no
    request and reads on a session of its own. ``kinds`` (#864): the worker's record of the expiry kind it read for
    (underlying, nearest expiry); a recorded kind spares the catalogue read, an absent or empty one reads it."""
    if db is not None:
        return await _tracked_on(db, strategy_id, rates, kinds)
    async with get_sessionmaker()() as own:
        found = await _tracked_on(own, strategy_id, rates, kinds)
        await own.commit()  # the worker's own session: keeps a stop base stored once (ADR-330), nothing else is written
        return found


async def _tracked_on(db: Any, strategy_id: int, rates: ChargeRates | None,
                      kinds: Mapping[tuple[str, datetime.date], str] | None = None) -> Tracked | None:
    paper = await paper_book.load_owned(db, current_user_ref(), strategy_id)  # owner check in the query
    real = not paper  # ADR-276: no paper order -> the real Zerodha book (fills + adopted holdings), same netter
    orders: Any = paper or await _real_rows(db, strategy_id)
    if not orders:
        return None  # not this user's, no such strategy, or nothing traded
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.order.contract_id
                                                                                   for o in orders}))}
    book = net_positions([o.order.as_paper() for o in orders], {})
    underlying, lot, legs = _legs_of(book, found)
    if not legs or underlying is None or lot is None:
        raise TrackedExited("no open option leg", closed_at=closed_at_of(orders))
    fresh = entry_stop_base(orders, found, _ENTRY_SOURCE)  # ADR-330 (1): from the entry orders only
    kind = await _stored_kind_or_empty(db, underlying, legs, kinds)  # R3: "" = not known; read BEFORE the backfill
    base = await stop_base_in_force(db, strategy_id, fresh)  # (a failed catalogue read rolls the session back)
    if real:  # paid charges and adjustments used before the app saw it: not readable yet ("not checked", ADR-276 (4))
        return Tracked(Position(underlying, lot, kind, datetime.date.min, tuple(legs)), book.booked, None,
                       adjustments_used=None, entered_at=entered_at(orders), real_book=True, stop_base=base,
                       entry_stop_base=fresh)
    paid, paid_exact = paid_of(orders, found, underlying, rates) if rates is not None else (None, None)
    booked = book.booked  # the same paper orders ``read_booked`` would read again on a second session
    # expiry kind and today are set by the route from the market reader (the calendar and clock live there)
    # adjustments_used: the engine's adjustment history over the stored orders (the count the history page shows);
    # None when the history cannot be read (the compare's "-" with that reason, never 0)
    used = history_count(orders, lambda cid: found[cid].stored is not None
                         and found[cid].stored.listed.contract.instrument_type in _OPTION_TYPES)
    return Tracked(Position(underlying, lot, kind, datetime.date.min, tuple(legs)), booked, paid,
                   adjustments_used=used, entered_at=entered_at(orders), paid_exact=paid_exact,
                   entry_position=entry_position_of(orders, found), stop_base=base, entry_stop_base=fresh)


async def _stored_kind_or_empty(db: Any, underlying: str, legs: Any,
                                kinds: Mapping[tuple[str, datetime.date], str] | None = None) -> str:
    """The position's expiry kind from the worker's record when it has one for the nearest leg (``kinds``, #864: the
    worker records only a non-empty kind), else from the stored catalogue (``stored_kind``), "" when it cannot be
    known or read (the live check then checks no stop: never the weekly row by default)."""
    nearest = min(x.expiry for x in legs)  # the check's own day: the nearest leg
    if kinds is not None and (kind := kinds.get((underlying, nearest))):
        return kind
    try:
        return await stored_kind(db, underlying, nearest)
    except CatalogueUnreadable:
        return ""


async def nearest_expiry(db: Any, strategy_id: int) -> datetime.date | None:
    """ADR-330 (19)(b): the nearest expiry among the strategy's OPEN contracts, from a light read (orders, contracts,
    the netted book): no stop-base backfill, no write. None: not this user's, nothing traded, or no open leg."""
    paper = await paper_book.load_owned(db, current_user_ref(), strategy_id)
    orders: Any = paper or await _real_rows(db, strategy_id)
    if not orders:
        return None
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.order.contract_id
                                                                                   for o in orders}))}
    book = net_positions([o.order.as_paper() for o in orders], {})
    expiries = [found[int(p.instrument_id)].stored.listed.contract.expiry for p in book.positions
                if p.net_quantity != 0 and found.get(int(p.instrument_id)) is not None
                and found[int(p.instrument_id)].stored is not None]
    return min(expiries, default=None)


async def nearest_expiries(db: Any, strategy_ids: Iterable[int]) -> dict[int, datetime.date | None]:
    """``nearest_expiry`` for many strategies in TWO statements whatever the count (W-13: the alert lists labelled each
    trade with 3 to 4 statements of its own): one paper-orders read (owner check in the query), one contract read.
    Same answer per strategy as ``nearest_expiry`` for a PAPER book (the nearest expiry among the open legs; a flat book
    or a contract that does not read -> None). A strategy that is not in the result has no paper order (a real book, not
    this user's, nothing traded): the caller asks ``nearest_expiry`` for it, one at a time."""
    ids = sorted(set(strategy_ids))
    papers = await paper_book.load_owned_many(db, current_user_ref(), ids)
    stored = await load_contracts(db, {o.order.contract_id for rows in papers.values() for o in rows})
    out: dict[int, datetime.date | None] = {}
    for sid, orders in papers.items():
        if not orders:
            continue
        book = net_positions([o.order.as_paper() for o in orders], {})
        expiries = []
        for p in book.positions:
            found = stored.get(int(p.instrument_id))
            if p.net_quantity != 0 and isinstance(found, StoredContract):
                expiries.append(found.listed.contract.expiry)
        out[sid] = min(expiries, default=None)
    return out


_ENTRY_SOURCE = "entry"  # = settings_in_force.BASE_ENTRY (imported lazily: that module imports the check)


def entry_stop_base(orders: Any, found: Mapping[int, Any], source: str) -> Any:
    """ADR-330 (1): the stop base worked out from the strategy's ENTRY orders only (kinds in
    the first batch, ``entry_batch``: ONE definition of "the trade as entered", shared with D-04's entry position),
    netted and priced by the engine (``compute_stop_base``). No entry order (empty, or none states a time), a book
    that is not whole-lot options, several expiries or an engine refusal -> None (not worked out): the stop lines
    then say "not checked", never a number from the live legs."""
    from ofo_app import settings_in_force as sif  # noqa: PLC0415 - it imports the check module

    entry = entry_batch(orders)
    if not entry:
        return None
    try:
        book = net_positions([o.order.as_paper() for o in entry], {})
        _, lot, legs = _legs_of(book, found)
    except (TrackedUnreadable, ValueError, KeyError, AttributeError, TypeError):
        log.warning("stop base: the entry orders cannot be read", exc_info=True)
        return None
    if lot is None or not legs:
        return None
    return sif.compute_stop_base(legs, lot, book.booked, datetime.datetime.now(datetime.UTC), source)


async def stop_base_in_force(db: Any, strategy_id: int, fresh: Any) -> Any:
    """The stop base the checks read. Answer states: STORED on the plan row (stated) -> that one, never recomputed;
    stored but not readable (failed) -> None, left as it is; plan with no base (absent, a plan saved before ADR-330)
    -> ``fresh`` stored ONCE with source "backfill" (a lost race reads the winner's); no plan -> ``fresh`` as it is
    (nothing to store it on); nothing worked out (empty, ambiguous) -> None."""
    from dataclasses import replace  # noqa: PLC0415

    from ofo_app import playbook_store  # noqa: PLC0415 - one import site with the check's own
    from ofo_app import settings_in_force as sif  # noqa: PLC0415

    plan = await playbook_store.plan_for(db, current_user_ref(), strategy_id)
    if plan is None:
        return fresh
    stored = getattr(plan, "stop_base", None)
    if stored is not None:
        return sif.stop_base_from_json(stored)
    if fresh is None:
        return None
    filled = replace(fresh, source=sif.BASE_BACKFILL)
    try:
        if await playbook_store.backfill_stop_base(db, strategy_id, filled.to_json()):
            return filled
        again = await playbook_store.plan_for(db, current_user_ref(), strategy_id)
        return sif.stop_base_from_json(getattr(again, "stop_base", None)) if again is not None else filled
    except Exception:  # noqa: BLE001 - a failed write must not stop the check; the figure is still the entry's
        log.warning("stop base: the backfill could not be stored (strategy %s)", strategy_id, exc_info=True)
        return filled


def _legs_of(book: Any, found: Mapping[int, Any]) -> tuple[str | None, int | None, list[PositionLeg]]:
    """(underlying, lot, open option legs) of a netted book; a leg that is not a whole-lot option is refused by name."""
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
    return underlying, lot, legs


def entry_batch(orders: Any) -> list[Any]:
    """The ONE definition of "the trade as entered" (D-04's entry position and ADR-330 (1)'s stop base): every order
    with the first order's ``placed_at``. A later basket, whatever its kind, and every adjustment is NOT part of it
    (plan question Q4 (a): an adjustment does not move the stop base; reversing that is a change here, in this one
    function, and it moves D-04's entry position with it). No order states a time -> [] (never a guess)."""
    times = [getattr(o.order, "placed_at", None) for o in orders]
    if not times or not all(isinstance(t, datetime.datetime) for t in times):
        return []
    first = min(times)
    return [o for o in orders if o.order.placed_at == first]


def entry_position_of(orders: Any, found: Mapping[int, Any]) -> Position | None:
    """D-04: the position the first batch of orders opened (every order with the first order's ``placed_at``), read as
    ``_tracked_on`` reads the book. None when no order states a time, the first batch is not whole-lot options, or it
    nets to nothing: the caller then keeps the current shape (never a guess)."""
    batch = entry_batch(orders)
    if not batch:
        return None
    try:
        underlying, lot, legs = _legs_of(net_positions([o.order.as_paper() for o in batch], {}), found)
    except TrackedUnreadable:
        return None
    return None if not legs or underlying is None or lot is None else Position(underlying, lot, "", datetime.date.min,
                                                                                 tuple(legs))


def paid_of(orders: Any, found: Mapping[int, Any], underlying: str,
            rates: ChargeRates) -> tuple[Decimal | None, Decimal | None]:
    """(shown, exact) charges paid on every stored order, read the way the trade page reads them
    (``paper.paid_exact_of``): the option flag is the contract's own type. A futures fill, or a contract with no
    stored row, has no rate here: (None, None), so the review says "before charges" like the page,
    never a figure built from option rates."""

    def is_option(contract_id: int) -> bool:
        stored = found[contract_id].stored
        return stored is not None and stored.listed.contract.instrument_type in _OPTION_TYPES

    fills = [PaperFill(o.order.kind, o.order.side, o.order.quantity, o.order.price, is_option(o.order.contract_id))
             for o in orders]
    try:
        got = paper_charges(fills, underlying, rates)
    except ChargesNotComputable:
        return None, None
    return got.shown, got.total


async def _real_rows(db: Any, strategy_id: int) -> list[Any]:
    """The real book as rows shaped like the paper book's (``.order``); [] when not this user's or nothing held."""
    try:  # the read-only real book: tracking reaches no order module (REQ-073 AC-6)
        rows = await tracked_book.real_book(db, current_user_ref(), strategy_id)
    except tracked_book.RealBookUnreadable as exc:
        raise TrackedUnreadable(str(exc)) from exc
    return [] if rows is None else [SimpleNamespace(order=o) for o in rows]


def entered_at(orders: Any) -> datetime.datetime | None:
    """S-12 (ADR-240 (3)): the strategy's entry time = its first stored order's ``placed_at`` (the trade's own time on
    the app's clock, the scenario's clock in scenario mode); None when no order states one (never a guess). Never the
    row's ``created_at``: that is the DB's insertion clock, so against a scenario's check day it made S-12's "entry
    session" depend on the real date (Stage D core proof, PATH-01: placed 3 Nov, inserted 6 Nov, checked 6 Nov)."""
    times = [p for p in (getattr(getattr(o, "order", None), "placed_at", None) for o in orders)
             if isinstance(p, datetime.datetime)]
    return min(times) if times else None


_CLOSING_KINDS = ("exit", "settle", "stop")


def closed_at_of(orders: Any) -> datetime.datetime | None:
    """The trade's close time (owner Q2b: "the trade closed at HH:MM"): the ``placed_at`` of its last exit, settle
    or stop order, on the app's clock; None when no such order states one (never a guess, never the worker's notice
    time)."""
    times = [p for p in (getattr(o.order, "placed_at", None) for o in orders if o.order.kind in _CLOSING_KINDS)
             if isinstance(p, datetime.datetime)]
    return max(times) if times else None


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


async def read_guards(strategy_id: int, tracked: Tracked, spot: Decimal | None,
                      listed: list | None, db: Any = None) -> dict[str, Any] | None | _GuardsUnreadable:
    """The ``guards`` of the strategy playbook (its own plan, else the active playbook of its type; ADR-230 (1)).
    Answer states: a mapping (limits; empty = none set), None (the shape matches no playbook), ``GUARDS_UNREADABLE``
    (store error or malformed body: logged by its class only; the route says the limits were not applied).
    ``db``: the request's own session (a request uses ONE connection, #682); None for a caller with no request."""
    try:
        if db is not None:
            return await _guards_on(db, strategy_id, tracked, listed)
        async with get_sessionmaker()() as own:
            return await _guards_on(own, strategy_id, tracked, listed)
    except Exception as exc:  # noqa: BLE001 - any failure of the read is "unreadable", never a silent skip
        log.warning("adjustment guards: strategy %s playbook unreadable (%s)", strategy_id, type(exc).__name__)
        return GUARDS_UNREADABLE


async def _guards_on(db: Any, strategy_id: int, tracked: Tracked, listed: list | None) -> dict[str, Any] | None:
    from ofo_app import adjustment_check  # noqa: PLC0415 - it imports the route module's dataclasses
    stype = adjustment_check.entry_type(tracked, listed)  # D-04: the one door the server's limit uses
    resolved = await adjustment_check.resolve(db, current_user_ref(), strategy_id, stype)
    return adjustment_check.guards_of_body(resolved.body)


# ---- market -----------------------------------------------------------------------------------------------------

def _scenario() -> Any:
    return scenario_mode.current()


def listed_options(provider: Any, underlying: str) -> list:
    """Every listed CE / PE contract of ``underlying`` with an expiry, from the provider's instrument master (the one
    listing the screen and the background build the adjustment chain rows from)."""
    return [lc for lc in provider.instrument_master()
            if lc.contract.name == underlying and lc.contract.expiry is not None
            and lc.contract.instrument_type in _OPTION_TYPES]


def chain_rows(listed: Iterable[Any], expiry: datetime.date, quotes: Mapping[str, Any],  # noqa: PLR0913
               greeks_of: Callable[[str, Any], Greeks | None],
               scn: Any, closed: bool = False) -> tuple[tuple[ChainRow, ...], dict[str, str], dict[str, Greeks]]:
    """THE one builder of the adjustment chain rows of one expiry: a row for EVERY listed contract of it (quoted or
    not), so an approach (T-19, the Compare) sees every strike it may trade. The screen's ``read_market`` and the
    background's ``market_inputs`` both call it; only the Greeks source differs (``greeks_of(instrument id, quote or
    None)``: the chain model on the screen, the shared per-option figures in the background). Scenario mode adds each
    row's tradable / low-OI state. Returns (rows, trading symbol -> instrument id, trading symbol -> per-unit
    Greeks). Each row's ``oi`` is the strike drawer's one OI rule (``outcome_oi.oi_of``; ``closed`` = the one
    market-state answer): None = no usable OI, so the Compare's OI flag reads "OI not known" (fail closed)."""
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
                             None if g is None else g.delta, True, tradable, low_oi, blocked,
                             oi=oi_of(q, closed),
                             health=None if q is None else q.health))  # ADR-241: the mid only on a live book
        ids[symbol] = iid
        if g is not None:
            leg_greeks[symbol] = g
    return tuple(rows), ids, leg_greeks


#: F-92: the longest the Compare waits for the first live quote of a leg of the position that nobody else holds
#: (the paper book's own wait, ``routes.paper.FORWARD_WAIT_S``)
LEG_WAIT_S = 3.0
LEG_POLL_S = 0.05


@dataclasses.dataclass(frozen=True)
class FrozenRead:
    """ONE read of the market taken while the hold is on (GC-IC1 round 3): the option quotes of the expiry the book
    lists and the index quote (None: not quoted). ``read_market`` builds EVERYTHING from this and never asks the
    provider again after the release, because a released contract is parked (``QuoteBook.park``) and reads as None."""

    quotes: Mapping[str, Any]
    index: Any
    #: GC-IC1 5b: the index's day values (``latest_day_stats``) read in the SAME read as ``index``, inside the hold
    #: (a released index is parked and its day values read NOT_HELD); None = no index quote, nothing asked
    day: Any = None
    #: ADR-239 (2): the option quotes of the NEXT listed expiry (A-04), read in the SAME read; empty = not asked
    later: Mapping[str, Any] = dataclasses.field(default_factory=dict)


async def held_read(provider: Any, underlying: str, expiry: datetime.date, leg_ids: list[str],  # noqa: PLR0913
                    feed: Any, index_id: str | None = None, now: datetime.datetime | None = None,
                    later: datetime.date | None = None) -> FrozenRead:
    """The frozen read of one expiry plus the contracts in ``leg_ids`` (the position's legs, the near-the-money window,
    the roll range, a second pass's landing strikes). The feed's book lists only contracts somebody holds (F-92), so
    the ones missing are held on the shared fan-out (``read_door.read_quotes``, the one read door) until
    they are quoted or ``LEG_WAIT_S`` passes, and the read is taken INSIDE the hold. Answer states per contract:
    quoted at once (no hold) / quoted after the wait / never quoted (absent: unpriced, never 0) / no token (KeyError:
    nothing held, the first read stands) / no feed (the first read stands) / provider disconnected (the read so far).
    The index: quoted / not (``index`` None: no forward, the chain model names its reason). ``index_id``: held with the
    rest when the first read has no index quote. ``now``: the check's clock, for the index's day values. ``later``:
    the next listed expiry (A-04, ADR-239 (2)), snapshotted in the SAME read (its ids may be in ``leg_ids``); never a
    read of its own after a release (finding live-subscription-lost-on-release-reacquire)."""
    def read() -> FrozenRead:
        index = provider.underlying_quote(underlying)
        more = {} if later is None else {q.instrument_id: q for q in provider.option_chain_snapshot(underlying, later)}
        return FrozenRead({q.instrument_id: q for q in provider.option_chain_snapshot(underlying, expiry)}, index,
                          None if index is None else provider.latest_day_stats(index.instrument_id, now), more)
    first = read()
    missing = [i for i in dict.fromkeys(leg_ids) if i not in first.quotes and i not in first.later]
    index_wait = index_id is not None and first.index is None
    if index_wait:
        missing.append(index_id)  # type: ignore[arg-type]
    if feed is None:
        return first
    if not missing:  # everything quoted: the door only keeps the standing hold (no wait), the first read stands
        await read_quotes(feed, list(dict.fromkeys(leg_ids)), lambda: first, lambda _s: True,
                          lambda: provider.status().connected, 0.0, LEG_POLL_S)
        return first

    def done(snap: FrozenRead) -> bool:
        return all(i in snap.quotes or i in snap.later for i in missing if i != index_id) and (
            not index_wait or snap.index is not None)
    held = await read_quotes(feed, missing, read, done, lambda: provider.status().connected, LEG_WAIT_S,
                               LEG_POLL_S)
    return first if held is NO_TOKEN else held


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


def screen_feed_reading(provider: Any, spot_q: Any, now: datetime.datetime) -> SourceReading:
    """The screen's feed spot reading by the worker's rule (#639 item 1, REQ-165 AC-5 "same answer"): a quiet index on
    a live feed is current (``spot_source.feed_reading`` with ``feed_is_live``), never refused by its last-change age;
    a stale / disconnected feed, a closed market or no tick yet today keeps the last change for the age window."""
    return feed_reading(spot_q, now, feed_live=feed_is_live(provider, now))


async def _window_spot(ctx: Any, underlying: str, spot_q: Any, now: datetime.datetime) -> Decimal | None:
    """The spot the window is centred on: the SAME answer the routes resolve (``resolve_spot``: feed, else the REST
    index quote, else the last close), so a user with only a strategy open (nobody holds the index on the feed) still
    gets a window. The REST quote is asked only when the feed's own reading is not usable. None: no spot at all."""
    feed = screen_feed_reading(ctx.provider, spot_q, now)
    answer = resolve_spot(feed, None, None, now=now, windows=feed_windows_of(ctx))  # feed only: no await before it
    if answer.available:
        return answer.value
    try:
        rest = await read_rest_spot(underlying)
    except Exception as exc:  # noqa: BLE001 - a REST failure is "no REST spot", never a failed check
        log.warning("adjustment window: REST spot unreadable (%s)", type(exc).__name__)
        rest = SourceReading(SourceState.FAILED)
    closed = market_state(ctx, now).closed
    last_close = read_last_close(spot_q, closed, _scenario(), now)
    judged = spot_judging_now(ctx)  # after the REST read: the live feed is re-stamped at the same instant
    feed = screen_feed_reading(ctx.provider, spot_q, judged)
    return resolve_spot(feed, rest, last_close, now=judged, windows=feed_windows_of(ctx)).value


def own_leg_ids(position: Position, listed: Iterable[Any]) -> list[str]:
    """The instrument ids of the position's legs (by trading symbol, the key the chain rows and the margin use)."""
    wanted = {x.tradingsymbol for x in position.legs}
    return [f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed
            if lc.broker_refs[0].broker_symbol in wanted]


def leg_prices_state(ctx: Any, quotes: Mapping[str, Any], ids: Mapping[str, str],
                     position: Position) -> tuple[datetime.datetime | None, bool]:
    """ADR-272: (oldest own-leg price time, stale?). Stale = the check's own ``prices_fresh`` is not True (stale OR
    unknown) or any own leg has no quote / a quote that is not AVAILABLE. Unknown age is stale (fail closed)."""
    from ofo_app.adjustment_check import prices_fresh  # noqa: PLC0415 - that module imports this one's types
    own = [quotes.get(ids.get(x.tradingsymbol, "")) for x in position.legs]
    stamps = [q.timestamp for q in own if q is not None]
    return (min(stamps, default=None),
            prices_fresh(ctx) is not True or any(q is None or q.health is not DataHealth.AVAILABLE for q in own))


def roll_ids(listed: Iterable[Any], position: Position, spot: Decimal | None,
             points: Mapping[str, Decimal]) -> list[str]:
    """The strikes a roll of each short searches (``approaches._Builder.roll_distance``), held in the SAME hold as the
    window so the search sees no gap it made itself (GC-IC1 round 3, review finding 2): for each SELL leg, every listed
    strike of its type and expiry from the short to the spot and one past it (inward, A-01), and from the short out
    past its wing by ``points[underlying]`` (outward, A-05; ``roll_points_without_delta``). No spot: outward only. A
    strike still unquoted after the hold is a gap the roll refuses by name, never steps over."""
    legs = position.legs
    out: list[str] = []
    for short in (x for x in legs if x.side == "SELL"):
        by_strike = {lc.contract.strike: f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"
                     for lc in listed if lc.contract.name == position.underlying and lc.contract.expiry == short.expiry
                     and lc.contract.instrument_type == short.type and lc.contract.strike is not None}
        up = short.type == "CE"  # outward: a call rolls up, a put down
        wings = [x.strike for x in legs if x.side == "BUY" and x.type == short.type and x.expiry == short.expiry
                 and (x.strike > short.strike if up else x.strike < short.strike)]
        reach = points.get(position.underlying, Decimal(0))
        far = (max(wings, default=short.strike) + reach) if up else (min(wings, default=short.strike) - reach)
        grid = sorted(by_strike)
        keep = {k for k in grid if (short.strike < k <= far if up else far <= k < short.strike)}
        if spot is not None:
            inward = [k for k in grid if min(short.strike, spot) <= k <= max(short.strike, spot) and k != short.strike]
            keep |= set(inward)
            beyond = [k for k in grid if (k < spot if up else k > spot) and k not in keep]  # one past the spot
            if beyond:
                keep.add(max(beyond) if up else min(beyond))
        out += [by_strike[k] for k in sorted(keep)]
    return out


def next_expiry(listed: Iterable[Any], underlying: str, expiry: datetime.date) -> datetime.date | None:
    """ADR-239 (2): the first listed option expiry of ``underlying`` after ``expiry``; None = none listed."""
    return min((lc.contract.expiry for lc in listed if lc.contract.name == underlying and lc.contract.expiry > expiry),
               default=None)


def later_ids(listed: Iterable[Any], position: Position, spot: Decimal | None, later: datetime.date | None,
              each_side: int) -> list[str]:
    """The next expiry's contracts A-04 may trade and price from (ADR-239 (2)): its near-the-money window (that
    expiry's own forward and Greeks) and each short's roll range read ON that expiry (``roll_ids`` with the legs
    moved there). None listed -> []."""
    if later is None:
        return []
    moved = dataclasses.replace(position, legs=tuple(dataclasses.replace(x, expiry=later) for x in position.legs))
    return (window_ids(listed, position.underlying, later, spot, each_side)
            + roll_ids(listed, moved, spot, _roll_points()))


#: GC-IC1 round 5: the most strikes the delta reach holds per short per expiry (the hold never grows without bound)
REACH_MAX_STRIKES = 30


@dataclasses.dataclass(frozen=True)
class ReachModel:
    """One expiry's model, used ONLY to choose which strikes the second pass holds (GC-IC1 round 5, second review):
    the expiry's gated model (``ofo.engine.model.expiry_model``, the frozen read's spot and parity forward) at a
    conservative IV. It never gives a price: a planned price is the quote's LTP, else its bid / ask mid (ADR-068 (1));
    a model delta here only widens the hold."""

    em: Any  # ofo.engine.model.ExpiryModel
    vol: Decimal

    def delta(self, kind: str, strike: Decimal) -> Decimal | None:
        """The engine's per-unit delta of ``kind`` at ``strike`` (None: the engine refuses it, never a guess)."""
        from ofo.engine.model import greeks  # noqa: PLC0415 - the engine owns the delta
        try:
            return greeks(self.em, Instrument(kind), strike, self.vol).greeks.delta
        except (ValueError, ArithmeticError):
            return None


def conservative_iv(model_greeks: Mapping[str, Any]) -> Decimal | None:
    """The HIGHEST implied volatility the frozen chain model solved for the expiry's quoted strikes: the widest delta
    reach (a higher IV keeps a far strike's delta larger, so the walk goes further). None: no IV at all."""
    return max((g.iv for g in model_greeks.values()), default=None)


def reach_model(quotes: Mapping[str, Any], spot_q: Any, expiry: datetime.date,  # noqa: PLR0913 - one read's parts
                now: datetime.datetime, ctx: Any,
                model_greeks: Mapping[str, Any]) -> ReachModel | None:
    """The expiry's ``ReachModel`` from the SAME frozen read as its chain model. None (no reach: today's behaviour)
    when no IV was solved, the spot is refused or the forward is unavailable."""
    from ofo.engine.model import SpotRefused, expiry_model  # noqa: PLC0415
    from ofo.scenario.spot import spot_reading  # noqa: PLC0415
    vol = conservative_iv(model_greeks)
    if vol is None:
        return None
    try:
        fwd = parity_forward(list(quotes.values()), spot_q, expiry, now, ctx.rate, ctx.forward_quality)
        return ReachModel(expiry_model(spot_reading(spot_q), fwd), vol)
    except (SpotRefused, ForwardUnavailable, ValueError, ArithmeticError):
        return None


def delta_reach_ids(rows: Iterable[ChainRow], ids: Mapping[str, str], position: Position,
                    models: Mapping[datetime.date, ReachModel], target: Decimal) -> list[str]:
    """Every strike a delta-based roll can land on (GC-IC1 round 5): for each short, on each expiry with a model that is
    not before its own (the position's and the next, A-04), the listed strikes walked outward from the short to ONE
    past the first whose model |delta| is at or under ``target`` (none within ``REACH_MAX_STRIKES``: the capped walk,
    so the builder refuses by name), plus the same strikes shifted by the wing width (where the wing lands). A strike
    not listed (no row, or no instrument id) is skipped. No model -> nothing (today's behaviour)."""
    rows = [r for r in rows if r.listed]
    out: list[str] = []
    for short in (x for x in position.legs if x.side == "SELL"):
        up = short.type == "CE"
        wings = [x.strike for x in position.legs if x.side == "BUY" and x.type == short.type
                 and x.expiry == short.expiry and (x.strike > short.strike if up else x.strike < short.strike)]
        width = ((min(wings) if up else max(wings)) - short.strike) if wings else None
        for expiry, model in models.items():
            if expiry < short.expiry:
                continue
            by_strike = {r.strike: r.tradingsymbol for r in rows if r.type == short.type and r.expiry == expiry}
            walk = sorted((k for k in by_strike if (k > short.strike if up else k < short.strike)),
                          key=lambda k: abs(k - short.strike))
            reach = walk[:REACH_MAX_STRIKES]
            for i, k in enumerate(reach):
                d = model.delta(short.type, k)
                if d is not None and abs(d) <= target:
                    reach = walk[:min(i + 2, REACH_MAX_STRIKES)]  # one past the first fit
                    break
            strikes = list(reach) + ([k + width for k in reach] if width is not None else [])
            out += [iid for k in strikes if (sym := by_strike.get(k)) is not None
                    and (iid := ids.get(sym)) is not None]
    return list(dict.fromkeys(out))


def _roll_points() -> Mapping[str, Decimal]:
    """The roll range the hold covers: the registry's ``roll_points_without_delta`` defaults (REQ-168 AC-1). A user who
    set a longer distance gets a gap past it, which the roll refuses by name and the second pass holds (never a
    strike picked past it)."""
    from ofo.adjustment import preferences  # noqa: PLC0415 - one home of the keys
    from ofo.settings import defaults  # noqa: PLC0415
    d = defaults()
    return {"NIFTY": d[preferences.ROLL_POINTS_NIFTY], "SENSEX": d[preferences.ROLL_POINTS_SENSEX]}


async def read_market(tracked: Tracked, ctx: Any, *, extra_ids: Iterable[str] = ()) -> MarketInputs:
    """The screen check's market: ONE frozen read (``held_read``) of the legs, the near-the-money window, the roll
    range, the index and ``extra_ids`` (the approaches route's second pass), taken while held; the chain model, the
    forward, the Greeks, the ATM vol, the feed spot reading and the last close all come from that read only. Nothing
    asks the provider for a quote after the release (GC-IC1 round 3)."""
    if ctx is None:  # not connected: no chain, no feed spot (the REST reader and the reasons still answer)
        now = server_now()
        return MarketInputs((), {}, None, None, None, SourceReading(SourceState.ABSENT),
                            SourceReading(SourceState.ABSENT), now, prices_stale=True)
    now = ctx.clock()
    position = tracked.position
    underlying, expiry = position.underlying, min(x.expiry for x in position.legs)  # the worker's primary_expiry (#863)
    provider = ctx.provider
    listed = listed_options(provider, underlying)
    scn = _scenario()
    expiry_kind = _expiry_kind(provider, underlying, expiry, listed, scn)  # the nearest leg's
    live = live_market.current_feed()  # F-92: the position's own legs are held for the read, like the paper book's
    first_index = provider.underlying_quote(underlying)  # only to centre the window; never used after the hold
    window_spot = await _window_spot(ctx, underlying, first_index, now)
    # REQ-165 AC-5 / REQ-155: the chain model needs near-the-money quotes for its forward, so the window is held too;
    # the roll range so a roll never steps over an unheld strike (GC-IC1)
    from ofo_app.chain_push import index_id_of  # noqa: PLC0415 - chain_push imports the app layer
    wanted = (own_leg_ids(position, listed) + window_ids(listed, underlying, expiry, window_spot,
                                                         ctx.chain_strikes_each_side)
              + roll_ids(listed, position, window_spot, _roll_points()) + list(extra_ids))
    later = next_expiry(listed, underlying, expiry)  # A-04 (ADR-239 (2)): read in the SAME hold, never after it
    wanted += later_ids(listed, position, window_spot, later, ctx.chain_strikes_each_side)
    frozen = await held_read(provider, underlying, expiry, wanted, live, index_id_of(ctx, underlying), now, later)
    quotes, spot_q = frozen.quotes, frozen.index
    closed = market_state(ctx, now).closed
    model = chain_model(list(quotes.values()), spot_q, expiry, now, ctx.rate, ctx.forward_quality, market_closed=closed)

    def model_greeks(iid: str, _q: Any) -> Greeks | None:  # the chain's engine Greeks per unit (chain_model)
        g = model.greeks.get(iid)
        return None if g is None else Greeks(g.delta, g.gamma if g.gamma_exact is None else g.gamma_exact, g.theta,
                                             g.vega)
    rows, ids, leg_greeks = chain_rows(listed, expiry, quotes, model_greeks, scn, closed)
    later_rows: tuple[ChainRow, ...] = ()
    reach: dict[datetime.date, ReachModel] = {}  # GC-IC1 round 5: which strikes a second pass holds, never a price
    if (rm := reach_model(quotes, spot_q, expiry, now, ctx, model.greeks)) is not None:
        reach[expiry] = rm
    if later is not None:  # that expiry's OWN chain model (its forward, its time), from the same frozen read
        later_model = chain_model(list(frozen.later.values()), spot_q, later, now, ctx.rate, ctx.forward_quality,
                                  market_closed=closed, decay_until=_today_close(expiry, now))
        if (rm := reach_model(frozen.later, spot_q, later, now, ctx, later_model.greeks)) is not None:
            reach[later] = rm

        def later_greeks(iid: str, _q: Any) -> Greeks | None:
            g = later_model.greeks.get(iid)
            return None if g is None else Greeks(g.delta, g.gamma if g.gamma_exact is None else g.gamma_exact,
                                                 g.theta, g.vega)
        later_rows, later_symbols, later_leg_greeks = chain_rows(listed, later, frozen.later, later_greeks, scn, closed)
        # C12: a two-expiry After's later legs get their Greeks after and their engine IV (``leg_ivs``)
        ids, leg_greeks = {**ids, **later_symbols}, {**later_leg_greeks, **leg_greeks}
    forward = fwd_model = None
    try:
        fwd_model = parity_forward(list(quotes.values()), spot_q, expiry, now, ctx.rate, ctx.forward_quality)
        forward = fwd_model.forward
    except (ForwardUnavailable, ValueError, ArithmeticError):
        forward = fwd_model = None
    leg_ivs = {sym: model.greeks[iid].iv for sym, iid in ids.items()  # the chain model's IV of each own leg (1b)
               if iid in model.greeks and sym in {x.tradingsymbol for x in position.legs}}
    leg_ivs |= {} if later is None else {sym: later_model.greeks[iid].iv for sym, iid in later_symbols.items()
                                         if iid in later_model.greeks}
    try:
        years = year_fraction(now, expiry)
    except ValueError:
        years = None
    vol = _atm_vol(rows, ids, model.greeks, forward)
    feed = screen_feed_reading(provider, spot_q, now)
    return MarketInputs(tuple(rows) + later_rows, ids, forward, years, vol, feed,
                        read_last_close(spot_q, closed, scn, now), now, expiry_kind, leg_greeks, fwd_model, leg_ivs,
                        index_day_open(frozen.day, now), reach, ctx.carry_gap_pct, ctx.s02_delta_per_lot,
                        ctx.s12_percent, spot_q, feed_is_live(provider, now),
                        *leg_prices_state(ctx, quotes, ids, position),
                        regime=await regime_inputs.read_regime(position.underlying),  # ADR-280: margin, VIX, ADX
                        leg_decay_left=None if _today_close(expiry, now) is None else _decay_left(
                            ids, model.greeks, later_symbols if later is not None else {},
                            later_model.greeks if later is not None else {}))


def _today_close(expiry: datetime.date, now: datetime.datetime) -> datetime.datetime | None:
    """D-12 (ADR-320 (1)): the position's nearest expiry is today and its close is ahead -> today's close, else None."""
    return close_if_expiry_day(expiry, now)  # the engine's one expiry-day check (expiry_day_close calls it too)


def _decay_left(ids: Mapping[str, str], greeks: Mapping[str, Any], later_ids: Mapping[str, str],
                later_greeks: Mapping[str, Any]) -> dict[str, Decimal]:
    """D-12: trading symbol -> the chain model's per-unit Decay left today, for every contract that has one."""
    out = {}
    for symbols, model in ((ids, greeks), (later_ids, later_greeks)):
        for sym, iid in symbols.items():
            g = model.get(iid)
            if g is not None and g.decay_left_today is not None:
                out[sym] = g.decay_left_today
    return out


async def read_market_more(tracked: Tracked, ctx: Any, extra_ids: Iterable[str]) -> MarketInputs | None:
    """The approaches route's ONE second pass (GC-IC1 round 3, review finding 3): the landing strikes the builder
    could not price are held with the rest in one more frozen read (at most one more ``LEG_WAIT_S``). None: nothing to
    hold (no ids, not connected, no live feed): the first read stands."""
    extra = list(dict.fromkeys(extra_ids))
    if not extra or ctx is None or live_market.current_feed() is None:
        return None
    return await read_market(tracked, ctx, extra_ids=extra)


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
    """THE one expiry-kind rule (the screen's ``read_market``, the background's ``market_inputs``, the plan sheet and
    ``stored_kind`` all call it). Monthly = the expiry a FUTURE of the underlying also expires on (index futures are
    monthly only); weekly = an expiry inside the listed futures that none of them sits on. "" = NOT KNOWN, never a
    default: no future listed, or the expiry lies after the last listed future (a far month whose own future is not
    listed yet). Scenario mode: the scenario's own stated kind. ``listed`` is kept for the callers' signature."""
    if scn is not None and scn.data.get("expiry_kind") in ("weekly", "monthly"):
        return str(scn.data["expiry_kind"])
    if not futures:
        return ""
    if expiry in futures:
        return "monthly"
    return "" if expiry > max(futures) else "weekly"


class CatalogueUnreadable(Exception):
    """The stored catalogue could not be read (a database error): the expiry kind is then NOT KNOWN, with a reason."""


async def stored_kind(db: Any, underlying: str, expiry: datetime.date, *, scn: Any = None,
                      load: Callable[..., Any] | None = None) -> str:
    """The expiry kind of ``expiry`` from the STORED catalogue (the day's instrument list the app keeps), by the one
    rule ``expiry_kind_of``; "" = not known. The read runs in a SAVEPOINT: a database error rolls back only that
    savepoint (the transaction stays usable for the next read) and raises ``CatalogueUnreadable``. It never calls
    ``db.rollback()``: that would drop the CALLER's order-key claim and strategy row lock, and the orders would then
    commit with no key row."""
    scn = _scenario() if scn is None else scn

    async def listed() -> list[Any]:
        catalogue = await (load(db) if load is not None else load_catalogue(db, underlying))  # FD5 item 4: one name
        return [e for e in catalogue.all_entries()
                if e.currently_listed and e.contract.name == underlying and e.contract.expiry is not None]
    try:
        if db is None:
            entries = await listed()
        else:
            async with db.begin_nested():
                entries = await listed()
    except Exception as exc:  # any failed read means "kind not known", with its own reason
        log.warning("expiry kind: catalogue not read", exc_info=True)
        raise CatalogueUnreadable from exc
    futures = frozenset(e.contract.expiry for e in entries if e.contract.is_future())
    return expiry_kind_of(expiry, [e for e in entries if e.contract.is_option()], futures, scn)


async def atm_iv_now(ctx: Any, underlying: str, expiry: datetime.date, spot: Decimal) -> Decimal | None:
    """ADR-270 (1): the check's ATM IV of ``expiry`` at this moment (the entry IV a first fill stores): the SAME steps
    ``read_market`` takes for its ``vol`` (one held read of the near-the-money window around ``spot``, the chain model,
    the parity forward, ``_atm_vol``), with no position. None: not connected, no forward, or no call the model prices
    (never a guess)."""
    if ctx is None or not ctx.provider.status().connected:
        return None
    from ofo_app.chain_push import index_id_of  # noqa: PLC0415 - chain_push imports the app layer
    now, provider = ctx.clock(), ctx.provider
    listed = listed_options(provider, underlying)
    wanted = window_ids(listed, underlying, expiry, spot, ctx.chain_strikes_each_side)
    frozen = await held_read(provider, underlying, expiry, wanted, live_market.current_feed(),
                             index_id_of(ctx, underlying), now)
    closed = market_state(ctx, now).closed
    model = chain_model(list(frozen.quotes.values()), frozen.index, expiry, now, ctx.rate, ctx.forward_quality,
                        market_closed=closed)
    rows, ids, _ = chain_rows(listed, expiry, frozen.quotes, lambda _i, _q: None, _scenario(), closed)
    try:
        forward = parity_forward(list(frozen.quotes.values()), frozen.index, expiry, now, ctx.rate,
                                 ctx.forward_quality).forward
    except (ForwardUnavailable, ValueError, ArithmeticError):
        return None
    return _atm_vol(list(rows), ids, model.greeks, forward)


async def entry_facts_now(ctx: Any, underlying: str, sold: Iterable[Any], confirmed: bool = False,
                          feed: Any = None) -> EntryFacts | None:
    """ADR-243 + ADR-270 (1): the entry facts a FIRST fill stores (paper and real alike), from the SOLD legs' listed
    contracts ``sold`` (``.instrument_type``, ``.strike``, ``.expiry``): the index's live spot now, each side's short
    distance (``entry_facts_of``) and the entry ATM IV of the nearest sold option expiry (``atm_iv_now``). Answer
    states: no context / no quote / a quote that is not a positive price -> None (nothing stored, never a guessed
    spot); the IV not readable (no forward, unpriced chain, a read that fails) -> the facts with ``entry_atm_iv``
    None. ADR-330 (39): the spot is the index's LIVE price (``priced``: AVAILABLE and above 0), the one rule a leg's
    price follows; a not-live value (old, or the feed not connected; never a flagged quote) is stored only when the
    user confirmed the not-live line (``confirmed``, ``_index_value_not_live``: its own flag rule), never
    silently (K2 F1: a ticked first fill with the feed down stores the held value, as ``record_basket_facts``
    does). ``feed``: when given, an index nobody holds yet is held on the shared fan-out until its first quote
    (``_index_quote_held``); None = the caller's book as it is."""
    if ctx is None:
        return None
    quote = await _index_quote_held(ctx, feed, underlying) if ctx.provider.status().connected else None
    ltp = quote.ltp if quote is not None and priced(quote) else None
    if ltp is None and confirmed:
        held = _index_value_not_live(ctx, underlying)
        ltp = None if held is None else held[0]
    if not isinstance(ltp, Decimal) or ltp <= 0:
        return None
    sold = list(sold)
    facts = entry_facts_of(ltp, [(c.instrument_type, c.strike) for c in sold])
    expiries = sorted(c.expiry for c in sold if c.instrument_type in _OPTION_TYPES and c.expiry is not None)
    if not expiries:
        return facts
    try:
        iv = await atm_iv_now(ctx, underlying, expiries[0], ltp)
    except Exception as exc:  # noqa: BLE001 - an unreadable IV is "not known at entry", never a failed fill
        log.warning("entry ATM IV unreadable (%s)", type(exc).__name__)
        iv = None
    return dataclasses.replace(facts, entry_atm_iv=iv)


def index_hold_refusal(quote: Any) -> str | None:
    """Why ``quote`` may not be HELD as the index value of a not-live save (ADR-330 (28), (39)); None = it may. An old
    quote (STALE / DELAYED) keeps its value and its time and may be held on the user's confirmation; a quote the feed
    flagged (``validation_errors``, health UNHEALTHY, e.g. ``crossed_quote``) or with no price above 0 may not
    (ADR-200 (4): no valid price stays unpriced with its reason)."""
    if quote is None:
        return "no_quote"
    if quote.validation_errors:
        return quote.validation_errors[0]
    if quote.health is DataHealth.UNHEALTHY:
        return "unhealthy"
    return None if is_live_price(quote.ltp) else "no_price"


def _index_value_not_live(ctx: Any, underlying: str) -> tuple[Decimal, datetime.datetime | None] | None:
    """ADR-330 (28): the last index value the app holds with ITS time, for a save the user confirmed as "prices are not
    live": the feed book's last quote (any age), else, with the market closed, the last close. None: no positive value
    at all (the refusal stays)."""
    if ctx is None:
        return None
    quote = ctx.provider.underlying_quote(underlying)
    reason = index_hold_refusal(quote)
    if reason is None and isinstance(quote.ltp, Decimal):
        return quote.ltp, quote.price_at
    if reason != "no_quote":
        log.warning("index value not held on confirmation: %s", reason)
        return None  # a flagged quote is not rescued by an older close
    now = ctx.clock()
    if market_state(ctx, now).closed:
        close = read_last_close(quote, True, _scenario(), now)
        if close.state is SourceState.STATED and isinstance(close.value, Decimal) and close.value > 0:
            return close.value, close.at
    return None


def _index_not_held_reason(ctx: Any, quote: Any) -> str:
    """The reason the index value is refused, for the refusal's ``.reason`` (the user's text is the template)."""
    if ctx is None or not ctx.provider.status().connected:
        return "not_connected"
    return index_hold_refusal(quote) or "not_live_not_confirmed"


async def _index_quote_held(ctx: Any, feed: Any, underlying: str) -> Any:
    """The index quote now. The API process holds only what a page socket subscribed, so an index nobody holds is held
    on the shared fan-out until its first quote or ``LEG_WAIT_S`` passes (``read_door.read_quotes``); ``feed`` None =
    no hold (the book as it is). The caller has checked the feed is connected."""
    from ofo_app.chain_push import index_id_of  # noqa: PLC0415 - chain_push imports the app layer

    provider = ctx.provider
    index_id = index_id_of(ctx, underlying)

    def read() -> Any:
        return provider.underlying_quote(underlying)
    quote = read()
    if quote is None and feed is not None and index_id is not None:
        held = await read_quotes(feed, [index_id], read, lambda q: q is not None,
                                 lambda: provider.status().connected, LEG_WAIT_S, LEG_POLL_S)
        quote = quote if held is NO_TOKEN else held
    return quote


async def _index_spot_held(ctx: Any, feed: Any, underlying: str,
                           confirmed: bool = False) -> tuple[Decimal, datetime.datetime | None]:
    """The index's live spot for the fill's starting point (ADR-283 (1)). The API process holds only what a page
    socket subscribed, so an index nobody holds is held on the shared fan-out until its first quote or ``LEG_WAIT_S``
    passes (``read_door.read_quotes``). Answer states: held / quoted within the wait -> the spot; no
    context / not connected / never quoted / not a positive price -> ``StrategyRefused`` (nothing stored), unless the
    user confirmed the not-live line (``confirmed``, ADR-330 (28)): then the last held value
    (``_index_value_not_live``). Returns ``(spot, at)``: the value and the time of the quote it came from (FR 3.4;
    None when the quote states none)."""
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415 - write path only

    spot = quote = at = None
    if ctx is not None and ctx.provider.status().connected:
        quote = await _index_quote_held(ctx, feed, underlying)
        # ADR-330 (39): the quote's own health carries the one index age rule (``FeedState.quote_health``); a value
        # that rule calls not live is not a live spot, whatever the feed as a whole says: it needs the user's tick
        live = quote is not None and quote.health is DataHealth.AVAILABLE
        spot, at = (quote.ltp, quote.price_at) if live else (None, None)
    if (not isinstance(spot, Decimal) or spot <= 0) and confirmed:
        held_value = _index_value_not_live(ctx, underlying)
        spot, at = (None, None) if held_value is None else held_value
    if not isinstance(spot, Decimal) or spot <= 0:
        refused = StrategyRefused("paper_index_price_unavailable", Failure.CONFLICT)
        refused.reason = _index_not_held_reason(ctx, quote)  # type: ignore[attr-defined]
        raise refused
    return spot, at


async def record_basket_facts(db: Any, ctx: Any, feed: Any, strategy_id: int,
                              basket: tuple[str, Any, Any, Mapping[int, Decimal], bool]) -> None:
    """ADR-283 (1): stores the market state at this basket's fill, in the fill's transaction. ``basket`` = (underlying,
    every order of the book after the fill, the order clock, contract id -> this basket's fill price, whether the user
    confirmed the "prices are not live" line, ADR-330 (28)). Basket number =
    the adjustments made so far after it (ADR-255, ``history_count``; 0 = the entry). Answer states: not connected / no
    positive spot (after the index is held, ``_index_spot_held``) -> REFUSED, nothing stored; the count unreadable ->
    nothing stored (the checks keep the newest starting point); no open leg (the basket closed the strategy) ->
    nothing stored (no check); a kept leg's price not read live -> stored as None (its rules not held); the ATM IV
    unreadable -> None."""
    from ofo.tracking import paper  # noqa: PLC0415 - the paper screen's prices

    from ofo_app import entry_facts_store  # noqa: PLC0415 - write path only
    from ofo_app.routes.tracking import _snapshot  # noqa: PLC0415 - the paper screen's own market read

    underlying, book, clock, filled, prices_not_live_confirmed = basket
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, sorted({o.order.contract_id
                                                                                 for o in book}))}

    def is_option(cid: int) -> bool:
        tc = found.get(cid)
        return tc is not None and tc.stored is not None and tc.stored.listed.contract.instrument_type in _OPTION_TYPES

    used = history_count(book, is_option)
    open_ = [(int(p.instrument_id), p.net_quantity) for p in net_positions([o.order.as_paper() for o in book],
                                                                           {}).positions if p.net_quantity != 0]
    if used is None or not open_ or not all(is_option(cid) for cid, _ in open_):
        return
    # after the no-facts returns: an exit needs no spot
    spot, spot_at = await _index_spot_held(ctx, feed, underlying, prices_not_live_confirmed)
    kept = [cid for cid, _ in open_ if cid not in filled and found[cid].identity is not None]
    prices: dict[int, Decimal | None] = dict(filled)
    if kept:
        try:
            snapshot = await _snapshot(ctx, feed, underlying, sorted({found[c].identity for c in kept}))
            got = {c: paper.display_price(snapshot, found[c].identity) for c in kept}
            prices.update({c: p.price if paper.is_live(p) else None for c, p in got.items()})
        except Exception:
            log.exception("basket facts: kept legs' prices not read")
    legs = {}
    for cid, qty in open_:
        c = found[cid].stored.listed.contract
        legs[(c.instrument_type, c.strike, c.expiry, "BUY" if qty > 0 else "SELL")] = prices.get(cid)
    try:
        iv = await atm_iv_now(ctx, underlying, min(k[2] for k in legs), spot)
    except Exception as exc:  # noqa: BLE001 - an unreadable IV is "not known at the fill", never a failed fill
        log.warning("basket ATM IV unreadable (%s)", type(exc).__name__)
        iv = None
    await entry_facts_store.record_basket(db, strategy_id, used,
                                          entry_facts_store.BasketFacts(clock, spot, iv, legs, spot_at))


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
