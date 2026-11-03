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

import dataclasses
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
from ofo.marketdata.day_open import index_day_open
from ofo.marketdata.forward import ForwardUnavailable, parity_forward
from ofo.marketdata.quote import planning_price_usable
from ofo.marketdata.spot_source import SourceReading, SourceState, feed_is_live, feed_reading, resolve_spot
from ofo.timeutil import IST, SESSION_CLOSE
from ofo.tracking.orderbook import net_positions

from ofo_app import live_market, paper_book, scenario_mode, tracked_contracts
from ofo_app.db import get_sessionmaker
from ofo_app.live_push import hold_and_read
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
                   adjustments_used=used, entered_at=entered_at(orders))


def entered_at(orders: Any) -> datetime.datetime | None:
    """S-12 (ADR-240 (3)): the strategy's entry time = its first stored order's ``created_at``; None when no order
    states one (never a guess)."""
    times = [o.created_at for o in orders if isinstance(getattr(o, "created_at", None), datetime.datetime)]
    return min(times) if times else None


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
                             None if g is None else g.delta, True, tradable, low_oi, blocked,
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
    the ones missing are held on the shared fan-out (``live_push.hold_and_read``, the paper book's own helper) until
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
    if not missing or feed is None:
        return first

    def done(snap: FrozenRead) -> bool:
        return all(i in snap.quotes or i in snap.later for i in missing if i != index_id) and (
            not index_wait or snap.index is not None)
    held = await hold_and_read(feed.fanout, missing, read, done, lambda: provider.status().connected, LEG_WAIT_S,
                               LEG_POLL_S)
    return first if held is None else held


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
                            SourceReading(SourceState.ABSENT), now)
    now = ctx.clock()
    position = tracked.position
    underlying, expiry = position.underlying, position.legs[0].expiry
    provider = ctx.provider
    listed = listed_options(provider, underlying)
    scn = _scenario()
    expiry_kind = _expiry_kind(provider, underlying, expiry, listed, scn)
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
    rows, ids, leg_greeks = chain_rows(listed, expiry, quotes, model_greeks, scn)
    later_rows: tuple[ChainRow, ...] = ()
    reach: dict[datetime.date, ReachModel] = {}  # GC-IC1 round 5: which strikes a second pass holds, never a price
    if (rm := reach_model(quotes, spot_q, expiry, now, ctx, model.greeks)) is not None:
        reach[expiry] = rm
    if later is not None:  # that expiry's OWN chain model (its forward, its time), from the same frozen read
        later_model = chain_model(list(frozen.later.values()), spot_q, later, now, ctx.rate, ctx.forward_quality,
                                  market_closed=closed)
        if (rm := reach_model(frozen.later, spot_q, later, now, ctx, later_model.greeks)) is not None:
            reach[later] = rm

        def later_greeks(iid: str, _q: Any) -> Greeks | None:
            g = later_model.greeks.get(iid)
            return None if g is None else Greeks(g.delta, g.gamma if g.gamma_exact is None else g.gamma_exact,
                                                 g.theta, g.vega)
        later_rows, later_symbols, _ = chain_rows(listed, later, frozen.later, later_greeks, scn)
        ids = {**ids, **later_symbols}
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
    feed = screen_feed_reading(provider, spot_q, now)
    return MarketInputs(tuple(rows) + later_rows, ids, forward, years, vol, feed,
                        read_last_close(spot_q, closed, scn, now), now, expiry_kind, leg_greeks, fwd_model, leg_ivs,
                        index_day_open(frozen.day, now), reach, ctx.carry_gap_pct)


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
