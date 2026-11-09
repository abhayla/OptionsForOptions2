"""The playbook check of one tracked strategy (GC-ADJ2 step 1C; REQ-158 AC-5, REQ-159 AC-2, REQ-160 AC-3, REQ-161 AC-4,
REQ-045 AC-1/AC-2/AC-7, F-71). Builds :class:`StrategyState` from the readers the adjustment-approaches route already
uses (never a second reader of the same source), resolves the playbook and runs ``playbook_eval.evaluate``.

Inputs and where each one's "not available" comes from (stated -> the value; absent / failed / not found / empty /
ambiguous -> None, so the evaluator answers NotChecked with its catalogue reason code):
- spot: ``resolve_spot``'s value (feed, REST quote, last close); not available -> None (``withheld_no_spot``).
- shorts' delta: ``MarketInputs.leg_greeks`` (the chain's engine Greeks); a symbol absent -> None
  (``missing_short_delta``). Shorts' LTP: the chain row's ``ltp``; unpriced -> None (``missing_short_price``).
- pnl: booked P&L plus the open legs marked at LTP (``adjust_money.closed_booked``, the engine's closing figure);
  booked unreadable or any open leg unpriced -> None (``missing_pnl``).
- max profit / max loss: the Before's gross whole-trade figures from ``routes.adjustment.price_after`` (the one
  engine, as the approaches route computes them); booked unreadable or several expiries -> None.
- expiry P&L at spot (T-02): the open legs' ``Strategy.expiry_pnl_at(spot)`` plus booked; no spot / booked -> None.
- premium_left: ``adjust_money.premium_left`` over the open option legs at LTP; any leg unpriced -> None.
- adjustment_cost (T-19, ADR-221): the cost of the CHEAPEST approach the playbook offers
  (``compare.offered_approaches``: ``approaches.applicable`` without "No change"), each built and priced by the
  approaches route's own path (``routes.adjustment.priced_approach``) and costed by ``compare.approach_cost``, the
  Compare's "This adjustment" cell (charges + half the bid-ask spread of each traded contract). Ties keep playbook
  order. Nothing offered / nothing priceable / no spot -> None with ``compare.NO_APPROACH_*`` as the reason code.
- margin: Zerodha's stated figure for the current legs through the approaches route's margin seam; only a CHECKED
  figure (``margin_block`` state ``stated``) counts; every other state -> None (``missing_margin``).
- days_left / hhmm: the answer clock (``MarketInputs.now``) in IST against the nearest leg expiry.
- expiry_kind: ``MarketInputs.expiry_kind``; prev_close: the last-close reading when STATED; day_open (T-13, GC-IC1
  5b): ``MarketInputs.day_open`` (``ofo.marketdata.day_open.index_day_open`` over the feed's own day values of the
  index, read with the index quote on both paths) when STATED (dated today IST); previous session / undated / no
  open / not held / feed not healthy / packet without day fields / not read -> None (``missing_day_open``).
  adjustments_used: ``Tracked.adjustments_used`` (not recorded -> None).
- prices_fresh (T-21): the market context's provider health: available -> True, stale -> False, anything else or no
  context -> None (``withheld_fresh_unknown``).

Playbook (REQ-158 AC-5): the strategy's own plan; else the user's active playbook of the type (``active_for`` falls
back to the type's system playbook); type None (Custom or an unmapped template) -> no playbook, no results, and the
tracking route keeps the platform 0.5% detection.

F-71 entry state: in scenario mode the scenario's ``position.entry`` (its clock, spot and ATM IV; the shorts' strikes;
every other entry input None). Otherwise, when the strategy's rule memory is empty (tracking just started), the first
check's own state is the entry state. The returned memory is written with ``playbook_store.put_rule_state``.
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from ofo.adjustment import level_watch
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import BASIS_CODES, Config, EntryFacts, ExitInputs, Position, RollBasis
from ofo.adjustment.compare import Cheapest, Column, MarginRead, cheapest_approach
from ofo.adjustment.offered import offered_now
from ofo.adjustment.strategy_type import strike_gap_of, type_of
from ofo.engine import adjust_money
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED
from ofo.engine.model import delta_at_intrinsic
from ofo.errors.explanations import (
    LEVEL_WATCH_LABEL_TEXT,
    PLAYBOOK_DAY_RULE_ACTION_TEXT,
    STOP_LABEL_TEXT,
    render_explanation,
)
from ofo.marketdata.day_open import STATED
from ofo.marketdata.forward import mid_price
from ofo.marketdata.spot_source import SourceState, SpotAnswer
from ofo.settings import layers
from ofo.timeutil import IST

from ofo_app import playbook_store
from ofo_app.routes.adjustment import (
    MarketInputs,
    Tracked,
    as_of_market,
    liquidity_inputs,
    price_after,
    priced_approach,
)

log = logging.getLogger(__name__)

#: a clock trigger's unit in the playbook body (T-10b): its value and threshold are HH:MM
CLOCK_UNIT: Final = "time"
#: a day rule's unit (GC-IC1 1a): its value is the nearest short's distance from spot in %
DAY_RULE_UNIT: Final = "%"
_HEALTH_FRESH: Final = "available"
_HEALTH_STALE: Final = "stale"


@dataclasses.dataclass(frozen=True)
class Resolved:
    source: str  # plan / active / system / none
    body: Mapping | None
    playbook_id: int | None
    status: str | None  # a system playbook's status only; None for the user's own (REQ-158 AC-2)
    is_system: bool
    #: ADR-250: a strategy PLAN accepted before the iron condor system version 2 (migration 0040) was saved; it keeps
    #: its own stops (per-stage T-06 / T-16) and gains no 2x-credit line. Read in ``resolve`` from the plan's
    #: ``accepted_at`` (kept on every re-save) against ``playbook_store.adr247_saved_at``; False for every other source
    saved_before_adr247: bool = dataclasses.field(kw_only=True)  # REQUIRED, no default (contract step 3 r3)

    @property
    def draft(self) -> bool:
        """Draft is a property of SYSTEM playbooks only: an own copy's status column defaults to 'draft'."""
        return self.is_system and self.status == "draft"

    @property
    def strategy_layer(self) -> layers.Layer:
        """ADR-245: the strategy layer of the three-layer settings is the strategy's PLAN copy only (REQ-161); a
        strategy following the user's active or the system playbook has none (``layers.strategy_layer``)."""
        return layers.strategy_layer(self.body) if self.source == "plan" else None


@dataclasses.dataclass(frozen=True)
class CheckAnswer:
    strategy_type: str | None
    playbook: Resolved
    evaluation: pe.Evaluation | None


def _engine_legs(position: Position) -> tuple[Leg, ...]:
    return tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * position.lot, x.entry)
                 for x in position.legs)


def reference_spot(position: Position, spot: Decimal | None, gap: Decimal | None) -> Decimal | None:
    """The level the shape is read against: the spot answer, else the middle of the strikes on the strike grid (the
    leg editor's rule, ``routes.leg_edit._reference_spot``); None without a gap."""
    if spot is not None:
        return spot
    if gap is None:
        return None
    strikes = [x.strike for x in position.legs]
    return (((min(strikes) + max(strikes)) / 2) / gap).quantize(Decimal(1)) * gap


def listed_of(ctx: Any) -> list | None:
    """The instrument listing the strike gap (and so the strategy type) is read from: the market context's, None
    without one. Every route that resolves a playbook through ``strategy_type`` takes it from here (#633)."""
    return None if ctx is None else ctx.provider.instrument_master()


def strategy_type(position: Position, spot: Decimal | None, listed: list | None) -> str | None:
    gap = None if listed is None else strike_gap_of(listed, position.underlying, {x.expiry for x in position.legs})
    ref = reference_spot(position, spot, gap)
    legs = _engine_legs(position)
    found = type_of(legs, ref, gap)
    if found is None and spot is None and ref is not None and gap is not None:
        for nearby in (ref - gap, ref + gap):  # no spot: the middle of the strikes is only a guess (as the leg editor)
            if (found := type_of(legs, nearby, gap)) is not None:
                break
    return found


async def plan_saved_before_adr247(conn: Any, plan: Any) -> bool:
    """ADR-250: a plan accepted before the iron condor system version 2 (migration 0040) was saved (the plan's
    ``accepted_at`` survives every re-save). Version 2 absent -> True: keep its own stops."""
    cutoff = await playbook_store.adr247_saved_at(conn)
    return cutoff is None or plan.accepted_at < cutoff


async def resolve(conn: Any, user_ref: str, strategy_id: int, stype: str | None) -> Resolved:
    plan = await playbook_store.plan_for(conn, user_ref, strategy_id)
    if plan is not None:
        return Resolved("plan", plan.body, plan.playbook_id, None, False,
                        saved_before_adr247=await plan_saved_before_adr247(conn, plan))
    if stype is None:
        return Resolved("none", None, None, None, False, saved_before_adr247=False)
    pb = await playbook_store.active_for(conn, user_ref, stype)
    return Resolved("system" if pb.is_system else "active", pb.body, pb.id, pb.status if pb.is_system else None,
                    pb.is_system, saved_before_adr247=False)


def _limit_value(v: Any) -> Decimal | str:
    return pe.UNLIMITED if v is UNLIMITED else v


def _tighten(body: Mapping, today: datetime.date, expiry: datetime.date, hhmm: str) -> Decimal | None:
    """The due "Tighten every trigger by X%" day rule (``when: expiry``) on expiry day from its time on."""
    for rule in body.get("day_rules", []):
        if rule.get("on") and pe.day_rule_acts(rule) and rule.get("action") == pe.DAY_ACTION_TIGHTEN \
                and rule.get("when") == "expiry" and rule.get("percent") and today == expiry \
                and hhmm >= rule.get("at", "99:99"):
            return Decimal(rule["percent"])
    return None


def prices_fresh(ctx: Any) -> bool | None:
    if ctx is None:
        return None
    health = getattr(ctx.provider.status().health, "value", None)
    return True if health == _HEALTH_FRESH else False if health == _HEALTH_STALE else None


#: ADR-268 (1): an option price within one tick of its intrinsic value has no time value left (NSE/BSE option tick)
INTRINSIC_TICK: Final = Decimal("0.05")


def _abs_delta(market: MarketInputs, leg: Any, ltp: Decimal | None, spot: Decimal | None) -> Decimal | None:
    """The leg's absolute delta for the rule checks. Answer states: engine delta stated -> |delta|; no delta but the
    price is within one tick of intrinsic (ADR-268 (1)) -> 1 in the money, 0 out of the money; no delta and no
    price or no spot, or a price with time value left -> None ("delta not available")."""
    g = market.leg_greeks.get(leg.tradingsymbol)
    if g is not None and g.delta is not None:
        return abs(g.delta)
    if ltp is None or spot is None or leg.type not in ("CE", "PE"):
        return None
    return delta_at_intrinsic(Instrument(leg.type), leg.strike, spot, ltp, INTRINSIC_TICK)


class PlaybookGuards(dict):
    """A playbook's guards (a plain mapping for every existing reader) that also carry the body they came from, so the
    approaches route reads T-09 for A-27 (ADR-238 (4)) from the SAME playbook read, never a second one."""

    def __init__(self, guards: Mapping, body: Mapping) -> None:
        super().__init__(guards)
        self.body = body


def guards_of_body(body: Mapping | None) -> dict[str, Any] | None:
    """The ``guards`` of a resolved playbook body (ADR-230 (1)); None when there is no body. The route's reader
    (``adjustment_readers.read_guards``) and T-19 both read guards through this."""
    return None if body is None else PlaybookGuards(body.get("guards", {}), body)


def exit_inputs_of(guards: Mapping | None, position: Position, now: datetime.datetime) -> ExitInputs:
    """A-27's and A-35's playbook inputs at this check (ADR-238 (4), (5)): the clock in IST against the nearest leg
    expiry, the due tighten rule as the playbook check applies it, then ``playbook_eval.exit_inputs`` (the expiry-day
    rule's own T-09 reader). Guards with no body (no playbook, a test seam) -> no T-09."""
    body = getattr(guards, "body", None)
    ist = now.astimezone(IST)
    hhmm = ist.strftime("%H:%M")
    if not position.legs:
        return ExitInputs(None, None, hhmm)
    expiry = min(x.expiry for x in position.legs)
    tighten = _tighten(body, ist.date(), expiry, hhmm) if isinstance(body, Mapping) else None
    state = pe.StrategyState(stops=None, expiry_kind=position.expiry_kind or "weekly",  # type: ignore[arg-type]
                             days_left=(expiry - ist.date()).days, hhmm=hhmm, tighten_percent=tighten)
    return pe.exit_inputs(body, guards, state)


def cheapest_offered(body: Mapping | None, tracked: Tracked, market: MarketInputs, spot: Decimal | None,  # noqa: PLR0913 - the preferences value is a required parameter (GC-SET)
                     rates: Any, config: Config, *, roll_basis: RollBasis, before: Any = None) -> Cheapest:
    """ADR-221: the cheapest approach ``body`` offers, every one built and priced by the Compare's own path.
    ``before``: the Before already priced by the caller (``price_after`` of the current legs: it reads only the legs,
    the underlying and the lot, which ``as_of_market`` leaves unchanged), so the own legs are priced once per check;
    None prices it here. ``roll_basis`` (ADR-243, REQUIRED): the strategy's basis in force (``basis_in_force``), the
    same the Compare builds on."""
    offered = offered_now(body, tracked.adjustments_used)  # S-11: only exit and reduce at the limit
    if spot is None:  # nothing can be built without spot: none priceable (T-19 is withheld for no spot anyway)
        return cheapest_approach(offered, {}, market.chain)
    columns: dict[str, Column] = {}
    tracked = as_of_market(tracked, market)  # as the approaches route builds (market day, listed expiry kind)
    position = tracked.position  # the route's Before and guards, through the same helpers (#633, ADR-230 (1))
    if before is None:
        before = price_after(position.legs, position, tracked.booked, tracked.paid_charges, (), rates, market)
    guards = guards_of_body(body)
    limits, max_profit = liquidity_inputs(guards, before)
    exits = exit_inputs_of(guards, position, market.now)  # ADR-238: A-27 / A-35 read the same playbook
    for a in offered:
        built, priced = priced_approach(a, tracked, market, spot, rates, config, roll_basis=roll_basis, limits=limits,
                                        max_profit=max_profit, exits=exits)
        if built is not None and priced is not None:
            columns[a] = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None),
                                priced.adjustment_charges)
    return cheapest_approach(offered, columns, market.chain)


def mark_of(row: Any) -> Decimal | None:
    """ADR-266: a leg's mark. LTP inside a sound two-sided book (0 < bid <= ask) -> LTP; outside it -> the bid-ask mid
    (no per-option quote time exists, so "stale" = outside the book); no ltp -> None (unpriced, never a stand-in);
    bid or ask missing, zero or crossed -> the LTP (last trade, no live quote)."""
    if row is None or row.ltp is None:
        return None
    ltp, bid, ask = row.ltp, row.bid, row.ask
    if bid is None or ask is None or bid <= 0 or ask < bid or bid <= ltp <= ask:
        return ltp
    return mid_price(bid, ask)


def state_of(tracked: Tracked, market: MarketInputs, spot: SpotAnswer, margin: Mapping | None,  # noqa: PLR0913
             rates: Any, fresh: bool | None, body: Mapping | None = None, *,
             config: Config, user_values: Mapping[str, Decimal] | None,
             strategy_layer: layers.Layer, entry_facts: EntryFacts | layers.Unreadable | None,
             resolved: Resolved | None) -> pe.StrategyState:
    """The check's state for one strategy: the ONE function the screen check, the worker and the playbook test route
    pass through. ADR-245: the carry gap in force is resolved HERE (``carry_gap_of``: the plan's, else the user's own,
    else the admin value ``market.carry_gap_pct``), from two REQUIRED keyword arguments with no default, so a caller
    cannot skip the resolution or silently use the admin value. ``user_values``: the user's values as the store reads
    them (``user_preferences_store.UserValues``, own values on ``.own``), or None when the caller has no user read
    path; ``strategy_layer``: ``Resolved.strategy_layer`` (None = the strategy has no plan). ADR-243: the roll basis
    in force is resolved HERE too (``basis_in_force``) from the same two layers and ``entry_facts`` (REQUIRED, no
    default: the strategy's stored entry facts, ``adjustment_readers.entry_facts_in``; None = none stored), so the
    check's cheapest approach builds every roll exactly as the Compare does. Contract step 3: the stop lines are
    read HERE, once, from ``settings_in_force.stops_of`` (REQUIRED ``resolved``, no default; None = the stops are not
    supplied, so every stop answers "not checked"), and the evaluator compares the loss to them and nothing else."""
    gap = carry_gap_of(market.carry_gap_pct, user_values, strategy_layer)
    basis = basis_in_force(user_values, strategy_layer, entry_facts)
    position = tracked.position
    rows = {r.tradingsymbol: r for r in market.chain}
    ltp = {x.tradingsymbol: mark_of(rows.get(x.tradingsymbol)) for x in position.legs}
    priced = all(v is not None for v in ltp.values())
    value = spot.value if spot.available else None
    shorts = tuple(pe.ShortLeg(x.strike, _abs_delta(market, x, ltp[x.tradingsymbol], value), ltp[x.tradingsymbol],
                               x.type) for x in position.legs if x.side == Action.SELL.value)
    qty = {x.tradingsymbol: x.lots * position.lot for x in position.legs}
    booked = tracked.booked
    pnl = None if booked is None or not priced else adjust_money.pnl_now(
        booked, ((x.side, x.entry, ltp[x.tradingsymbol], qty[x.tradingsymbol]) for x in position.legs))
    left = adjust_money.premium_left((x.side, ltp[x.tradingsymbol], qty[x.tradingsymbol])
                                     for x in position.legs) if priced else None
    before = price_after(position.legs, position, booked, tracked.paid_charges, (), rates, market)  # once per check
    cheap = cheapest_offered(body, tracked, market, value, rates, config, roll_basis=basis, before=before)
    gross = None if before.after is None else before.after.gross
    expiry_pnl = None
    if value is not None and booked is not None:
        from ofo.engine.strategy import Strategy  # noqa: PLC0415 - engine type only here
        expiry_pnl = adjust_money.with_booked(booked, Strategy(_engine_legs(position)).expiry_pnl_at(value))
    now = market.now.astimezone(IST)
    expiry = min(x.expiry for x in position.legs)
    hhmm = now.strftime("%H:%M")
    stated_margin, margin_unreadable = margin_in(margin)
    last = market.last_close
    day = market.day_open
    kind = market.expiry_kind or position.expiry_kind or "weekly"
    stops = None
    if resolved is not None:
        from ofo_app import settings_in_force as sif  # noqa: PLC0415 - it imports this module
        credit = None if booked is None else adjust_money.net_credit_so_far(
            booked, ((x.side, x.entry, qty[x.tradingsymbol]) for x in position.legs))
        stops = sif.stops_of(resolved, sif.MoneyInputs(None if gross is None else gross.max_loss, credit,
                                                       stated_margin),
                             sif.StageAt(kind, (expiry - now.date()).days))
    return with_gamma(with_carry(pe.StrategyState(stops=stops,
        expiry_kind=market.expiry_kind or position.expiry_kind or "weekly",  # type: ignore[arg-type]
        days_left=(expiry - now.date()).days, hhmm=hhmm, spot=value, shorts=shorts, pnl=pnl,
        max_loss=None if gross is None else _limit_value(gross.max_loss),
        max_profit=None if gross is None else _limit_value(gross.max_profit),
        margin=stated_margin, margin_unreadable=margin_unreadable, premium_left=left, adjustment_cost=cheap.cost,
        adjustment_approach=cheap.approach,
        adjustment_cost_reason=cheap.reason, adjustment_unpriced=cheap.unpriced, atm_iv=market.vol,
        prev_close=(last.value if last is not None and last.value is not None and last.state is SourceState.STATED
                    else None),
        day_open=day.value if day is not None and day.reason == STATED else None,
        adjustments_used=tracked.adjustments_used, expiry_pnl_at_spot=expiry_pnl,
        tighten_percent=None if body is None else _tighten(body, now.date(), expiry, hhmm), prices_fresh=fresh,
        held=held_legs(position, market), today=now.date(), entry_day=entry_day(tracked),
        s02_delta_per_lot=market.s02_delta_per_lot, s12_percent=market.s12_percent,
        open_legs=tuple(pe.OpenLeg(x.type, x.side, x.strike, x.lots, x.entry, ltp[x.tradingsymbol])
                        for x in position.legs),
        lot_size=position.lot, underlying=position.underlying, expiry=expiry,
        entry_spot=entry_facts.entry_spot if isinstance(entry_facts, EntryFacts) else None,
        # ADR-270 (1): T-11's entry IV from the stored entry facts in every mode; a scenario's own entry IV still
        # replaces it after this build (its seed stores no IV)
        entry_atm_iv=entry_facts.entry_atm_iv if isinstance(entry_facts, EntryFacts) else None,
        **regime_fields(market)),
        body, tracked, market, gap), body, tracked, market)


def regime_fields(market: MarketInputs) -> dict[str, Decimal | None]:
    """ADR-280: the five market-wide inputs from ``MarketInputs.regime`` (``regime_inputs.RegimeInputs``); no read
    (None) -> every one None, so the triggers that read them answer not checked."""
    r = market.regime
    if r is None:
        return dict.fromkeys(("available_margin", "vix", "vix_prev_close", "vix_percentile", "adx"))
    return {"available_margin": r.available_margin, "vix": r.vix, "vix_prev_close": r.vix_prev_close,
            "vix_percentile": r.vix_percentile, "adx": r.adx}


def margin_in(margin: Mapping | None) -> tuple[Decimal | None, bool]:
    """(the stated margin, unreadable?) from ``routes.adjustment.margin_block``'s answer: "stated" with a finite
    number -> that figure; "failed", or "stated" with a figure that is not a finite number -> (None, True); anything
    else (empty, not available, no read) -> (None, False). Never a stand-in figure."""
    if margin is None:
        return None, False
    if margin.get("state") == "failed":
        return None, True
    if margin.get("state") != "stated":
        # "empty" (Zerodha stated no figure) and other non-stated blocks read "Margin not available" on T-14: still
        # not checked, never passed (accepted by the coordinator, B2 round 1). The worker's failed read is None here.
        return None, False
    try:
        value = Decimal(str(margin["value"]))
    except (KeyError, ArithmeticError, ValueError, TypeError):
        return None, True
    return (value, False) if value.is_finite() else (None, True)


def with_gamma(state: pe.StrategyState, body: Mapping | None, tracked: Tracked,
               market: MarketInputs) -> pe.StrategyState:
    """``state`` with T-14's 1% repricing figures (design decision 8, ``ofo.adjustment.gamma``) when the body has
    T-14 switched on, in live and test-data mode alike (ADR-278 supersedes ADR-253's scenario-only gate). The model is
    the check's own (``carry_model``), so the screen and the worker value it alike."""
    t14 = ((body or {}).get("triggers") or {}).get("T-14") or {}
    if not t14.get("on"):
        return state
    from ofo.adjustment import gamma  # noqa: PLC0415 - engine valuation only here
    return dataclasses.replace(state, gamma=gamma.gamma_figures(carry_model(tracked, market)))


def held_legs(position: Position, market: MarketInputs) -> tuple[pe.HeldLeg, ...]:
    """S-02 (ADR-240 (3)): every open leg with its per-unit engine Greeks from ``MarketInputs.leg_greeks`` (the
    chain's engine Greeks; a symbol absent -> None, so S-02 is not checked, never a delta of 0)."""
    return tuple(pe.HeldLeg(market.leg_greeks.get(x.tradingsymbol), x.side, x.lots) for x in position.legs)


def entry_day(tracked: Tracked) -> datetime.date | None:
    """S-12: the IST date of the strategy's first order (``Tracked.entered_at``); None when not known."""
    at = getattr(tracked, "entered_at", None)
    return None if at is None or at.tzinfo is None else at.astimezone(IST).date()


def carry_model(tracked: Tracked, market: MarketInputs) -> Any:
    """GC-IC1 1b: the gated engine model of the open legs for the carry check's gap figures (``ofo.adjustment.carry``),
    built from the check's own market read: the expiry's forward object and each leg's engine IV (absent -> the leg
    has no IV, so the figures say not known). None when the forward was refused or the model refuses (a second
    expiry has no forward here, so no figure is claimed). One function: the screen and the worker both call it."""
    from ofo.engine.inputs import LegInput, SpotReading, StrategyInput  # noqa: PLC0415 - engine types only here
    from ofo.engine.model import model_inputs  # noqa: PLC0415
    fwd, position = market.forward_model, tracked.position
    if fwd is None:
        return None
    rows = {r.tradingsymbol: r for r in market.chain}
    legs = tuple(LegInput(position.underlying, x.tradingsymbol, Action(x.side), Instrument(x.type), x.strike, x.expiry,
                          x.lots * position.lot, x.entry, getattr(rows.get(x.tradingsymbol), "ltp", None),
                          market.leg_ivs.get(x.tradingsymbol)) for x in position.legs)
    try:
        reading = SpotReading(fwd.spot, fwd.spot_timestamp, fwd.spot_health)  # the reading the forward was read on
        return model_inputs(StrategyInput(position.underlying, reading, fwd.valuation_time, fwd.rate, legs,
                                          days_in_year=fwd.days_in_year),
                            {fwd.expiry: fwd})
    except (ValueError, ArithmeticError):  # SpotRefused / ForwardUnavailable / a leg the input refuses
        return None


def with_carry(state: pe.StrategyState, body: Mapping | None, tracked: Tracked,
               market: MarketInputs, gap: GapInForce) -> pe.StrategyState:
    """``state`` with today's carry day kinds and, only when a carry rule is due, its figures (GC-IC1 1b), valued at
    ``gap``: the carry gap in force for this strategy (``carry_gap_of``, ADR-245), never ``market``'s admin value."""
    from ofo.adjustment import carry  # noqa: PLC0415
    now = market.now.astimezone(IST)
    state = dataclasses.replace(state, carry_days=pe.carry_day_kinds(now.date()))
    if not pe.carry_due(body, state):
        return state
    figs = carry.carry_figures(carry_model(tracked, market), tracked.booked, state.margin, now,
                               gap_pct=gap.value, gap_source=gap.source, gap_setting_reason=gap.reason)
    return dataclasses.replace(state, carry=figs)


def carry_record(figs: pe.CarryFigures) -> dict[str, str | None]:
    """The carry check's record content: money as strings (``Decimal`` text), None + reason when not known."""
    def text(v: Decimal | None) -> str | None:
        return None if v is None else format(v, "f")
    return {"gap_pct": text(figs.gap_pct), "gap_up": text(figs.up), "gap_down": text(figs.down),
            "gap_reason": figs.gap_reason, "margin": text(figs.margin), "margin_reason": figs.margin_reason,
            "next_open": None if figs.next_open is None else figs.next_open.isoformat(),
            "gap_source": figs.gap_source, "gap_setting_reason": figs.gap_setting_reason}


@dataclasses.dataclass(frozen=True)
class GapInForce:
    """The carry gap for one strategy (ADR-245): the value, where it came from, or the reason no value is read."""

    value: Decimal | None
    source: str | None
    reason: str | None


#: the user layer's reason detail when the values handed in are not the store's own-values record (logs only)
USER_VALUES_WITHOUT_OWN: Final = "user_values_without_own"


def user_layer(user_values: Mapping[str, Decimal] | None) -> layers.Layer:
    """The user layer: the user's OWN values (``user_preferences_store.UserValues.own``), never the merged mapping
    (a merged value equal to the default cannot say whose it is). Answer states:
    - None: the caller has no user read path -> no user layer (the next layer);
    - a record whose ``.own`` is a mapping -> that mapping (a key absent -> the next layer);
    - anything else (a plain merged mapping, an ``.own`` that is not a mapping, a wrong type) -> ``Unreadable``: the
      resolver refuses with ``layers.USER_UNREADABLE`` (fail closed), never the admin default."""
    if user_values is None:
        return None
    own = getattr(user_values, "own", None)
    if isinstance(own, Mapping):
        return own
    return layers.Unreadable(USER_VALUES_WITHOUT_OWN)


def carry_gap_of(admin: Decimal | None, user_values: Mapping[str, Decimal] | None,
                 strategy: layers.Layer) -> GapInForce:
    """``other.carry_gap_percent`` in force for one strategy through the ONE resolver (``ofo.settings.layers``):
    the plan's, else the user's, else the admin default. A layer that exists but cannot be read -> no value and its
    reason code (fail closed, never the next layer); an admin value not read -> ``DEFAULT_UNREADABLE``."""
    admin_layer: layers.Layer = layers.Unreadable("not read") if admin is None else {layers.CARRY_GAP_PERCENT: admin}
    try:
        got = layers.resolve(layers.CARRY_GAP_PERCENT, admin_layer, user_layer(user_values), strategy)
    except layers.LayerUnreadable as exc:
        return GapInForce(None, None, exc.code)
    return GapInForce(got.value, got.source, None)


def admin_of(user_values: Mapping[str, Decimal] | None, key: str) -> Decimal | None:
    """The ADMIN layer of ``key`` from the request's one values read (``user_preferences_store.UserValues.admin``).
    No admin value for the key (the caller has no user read path, or the record carries no admin row for it) -> the
    REGISTRY default: with no admin row the admin layer IS the registry's default (``settings_in_force``), so a user
    who changed nothing gets today's rule, never every roll refused. An admin value that is present but not a Decimal
    -> None: the resolver refuses with ``layers.DEFAULT_UNREADABLE`` (fail closed)."""
    from ofo import settings  # noqa: PLC0415 - the checked-in registry, loaded once

    admin = getattr(user_values, "admin", None)
    if not isinstance(admin, Mapping) or key not in admin:
        return settings.defaults().get(key)
    found = admin[key]
    return found if isinstance(found, Decimal) else None


def basis_in_force(user_values: Mapping[str, Decimal] | None, strategy: layers.Layer,
                   entry: EntryFacts | layers.Unreadable | None) -> RollBasis:
    """ADR-243: the ONE resolution of a strategy's roll basis, used by the Compare route and by ``state_of`` (the
    screen check, the worker, the playbook test): the admin layer (``admin_of``), the user's own, the plan's, with
    the stored entry facts."""
    return roll_basis_of(admin_of(user_values, layers.ROLL_BASIS), user_values, strategy, entry)


def roll_basis_of(admin: Decimal | None, user_values: Mapping[str, Decimal] | None, strategy: layers.Layer,
                  entry: EntryFacts | layers.Unreadable | None) -> RollBasis:
    """``adjustments.roll_basis`` in force for one strategy (ADR-243) through the ONE resolver (``layers``):
    the plan's, else the user's own, else the admin default; with the strategy's entry facts stored at its first fill
    (``entry_facts_store``). Answer states:
    - basis read: 1 -> target delta, 2 -> entry distance (with its source);
    - a layer that exists but cannot be read, or a value with no basis code -> ``reason`` set: every roll refused;
    - entry facts present -> the entry spot and each side's STORED distance carried; absent (None: not stored, e.g. a
      strategy first filled before migration 0039) or unreadable -> no distance: under "Entry distance" every roll is
      refused naming the leg (never the target delta silently); under "Target delta" they are not used."""
    admin_layer: layers.Layer = layers.Unreadable("not read") if admin is None else {layers.ROLL_BASIS: admin}
    facts = entry if isinstance(entry, EntryFacts) else None
    if isinstance(entry, layers.Unreadable):
        log.warning("roll basis: entry facts unreadable: %s", entry.detail)
    spot, call, put = (None, None, None) if facts is None else (facts.entry_spot, facts.call_distance,
                                                                facts.put_distance)
    try:
        got = layers.resolve(layers.ROLL_BASIS, admin_layer, user_layer(user_values), strategy)
    except layers.LayerUnreadable as exc:
        return RollBasis(None, None, spot, exc.code, call, put)
    code = BASIS_CODES.get(got.value)
    if code is None:
        return RollBasis(None, got.source, spot, layers.DEFAULT_UNREADABLE, call, put)
    return RollBasis(code, got.source, spot, None, call, put)


def _entry_greeks(leg: Any, clock: datetime.datetime, spot: Decimal, atm_iv: Decimal | None) -> Any:
    """An open leg's per-unit engine Greeks AT ENTRY (ADR-008): entry spot and clock, the entry ATM IV, else the vol the
    engine solves from the leg's own entry (fill) price. Not an option, past expiry, or no vol -> None (not checked)."""
    from ofo import settings  # noqa: PLC0415 - the checked-in registry
    from ofo.engine.model import greeks_at_price  # noqa: PLC0415 - the engine's one pricing door

    if leg.type not in ("CE", "PE"):
        return None
    # shortcut: the registry's default interest rate, not a per-user override; delta moves ~0.001 per 1 % of rate
    rate = settings.defaults()[settings.RISK_FREE_RATE]
    try:
        return greeks_at_price(Instrument(leg.type), spot, leg.strike, leg.expiry, clock, rate, leg.entry, atm_iv)
    except ValueError:  # the engine's refusals (no IV for this price, expiry passed): the rule is not checked at entry
        return None


def _entry_state(clock: datetime.datetime, spot: Decimal, atm_iv: Decimal | None, state: pe.StrategyState,
                 position: Position) -> pe.StrategyState:
    """An F-71 entry state (round 3, finding rule-entry-baseline-taken-at-first-check): the entry's clock and spot,
    each short with its engine delta AT ENTRY and its entry premium as its price, every open leg with its engine
    Greeks (S-02), the entry ATM IV as both IVs. A
    rule still not computable here (no P&L, no margin at entry) counts as not held, never as the first check."""
    clock = clock.astimezone(IST)
    expiry = min(x.expiry for x in position.legs)
    greeks = {id(x): _entry_greeks(x, clock, spot, atm_iv) for x in position.legs}
    shorts = tuple(pe.ShortLeg(x.strike, None if greeks[id(x)] is None else abs(greeks[id(x)].delta), x.entry, x.type)
                   for x in position.legs if x.side == Action.SELL.value)
    held = tuple(pe.HeldLeg(greeks[id(x)], x.side, x.lots) for x in position.legs)  # F-71: every leg, S-02 reads them
    return pe.StrategyState(stops=None, expiry_kind=state.expiry_kind, days_left=(expiry - clock.date()).days,
                            hhmm=clock.strftime("%H:%M"), spot=spot, shorts=shorts, held=held,
                            atm_iv=atm_iv, entry_atm_iv=atm_iv, prices_fresh=True,
                            adjustments_used=state.adjustments_used, s02_delta_per_lot=state.s02_delta_per_lot)


def scenario_entry(scn: Any, state: pe.StrategyState, position: Position) -> pe.StrategyState | None:
    """The scenario's ``position.entry`` as the F-71 entry state (None: the scenario states none)."""
    entry = (scn.data.get("position") or {}).get("entry") if scn is not None and position.legs else None
    if not entry:
        return None
    return _entry_state(datetime.datetime.fromisoformat(entry["clock"]), Decimal(str(entry["spot"])),
                        None if entry.get("atm_iv") is None else Decimal(str(entry["atm_iv"])), state, position)


def rule_marker(adjustments_used: int | None, stored: Mapping[int, Any]) -> int:
    """ADR-258: the rule-memory starting point a check reads and writes = the adjustments made so far (ADR-255 count).
    A count that could not be read (None) keeps the newest stored starting point (0 when none): never a re-baseline
    on an unread count, so a crossing is never hidden as "already true" by a read failure."""
    if isinstance(adjustments_used, int) and not isinstance(adjustments_used, bool) and adjustments_used >= 0:
        return adjustments_used
    return max(stored, default=0)


def _own_facts(facts: Any, position: Position) -> bool:
    """The strategy has its OWN readable entry facts with a time (stated); anything else is not a baseline."""
    return isinstance(facts, EntryFacts) and isinstance(facts.at, datetime.datetime) and bool(position.legs)


def entry_baseline(scn: Any, state: pe.StrategyState, position: Position, facts: Any,
                   marker: int) -> pe.StrategyState | None:
    """The ONE entry baseline of a rule with no stored memory (issue 65, finding rule-entry-baseline-taken-at-first-
    check; screen, recorder, worker and playbook test all call it). The source follows what the strategy HAS, never the
    process mode (GC-ICGUIDE g04b: a builder-entered strategy checked in scenario mode took the file's entry). Order:
    - after an adjustment basket (``marker`` > 0, ADR-258) -> None: the first check is the new starting point;
    - stored entry facts with their time (``EntryFacts.at``) -> the spot and clock of the first fill, in any mode;
    - scenario mode with a stated file entry -> the file's entry (a seeded strategy has no facts of its own);
    - else (absent, unreadable, no time, no legs, no stated entry) -> None: the first check is the baseline
      (the known gap, test_rule_entry_baseline::test_known_gap_no_entry_facts...).
    The caller passes ``None`` -> this check's state."""
    if marker > 0:
        return None
    if _own_facts(facts, position):
        return _entry_state(facts.at, facts.entry_spot, None, state, position)
    return scenario_entry(scn, state, position)


def with_entry_iv(scn: Any, state: pe.StrategyState, position: Position, facts: Any) -> pe.StrategyState:
    """T-11's entry ATM IV follows the same choice as ``entry_baseline``: a strategy with its own facts keeps the
    facts' IV (``state_of`` set it; None when the facts carry none); only one without them takes the file's IV."""
    if _own_facts(facts, position):
        return state
    entry = scenario_entry(scn, state, position)
    return state if entry is None else dataclasses.replace(state, entry_atm_iv=entry.atm_iv)


async def _evaluate_stored(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                           state: pe.StrategyState, scn: Any, position: Position, *,
                           gap_until: str) -> tuple[pe.Evaluation, dict, int]:
    stored = await playbook_store.rule_states(conn, user_ref, strategy_id)
    marker = rule_marker(state.adjustments_used, stored)
    memory = {k: {"held_at_entry": h, "seen_clear": s} for k, (h, s) in stored.get(marker, {}).items()}
    facts = None
    if scn is not None or (not memory and marker == 0):
        from ofo_app.adjustment_readers import entry_facts_in  # noqa: PLC0415 - read path only
        facts = await entry_facts_in(conn, strategy_id)
    state = with_entry_iv(scn, state, position, facts)
    base = entry_baseline(scn, state, position, facts, marker)
    ev = pe.evaluate(body, state, memory, base or state, gap_until=gap_until)
    return ev, memory, marker


async def evaluate_stored(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                          state: pe.StrategyState, scn: Any, position: Position, *,
                          gap_until: str) -> tuple[pe.Evaluation, dict]:
    """The playbook evaluated against the STORED rule memory of the current starting point (ADR-258), writing nothing
    (the screen check's path; review round 2, finding 3: the background worker is the one writer of adjustment state,
    ADR-237 (6)). A rule with no memory takes its entry from ``entry_baseline``. Returns (evaluation, memory read)."""
    ev, memory, _marker = await _evaluate_stored(conn, user_ref, strategy_id, body, state, scn, position,
                                                 gap_until=gap_until)
    return ev, memory


async def evaluate_and_remember(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                                state: pe.StrategyState, scn: Any, position: Position, *,
                                gap_until: str) -> pe.Evaluation:
    """``evaluate_stored``, then the changed rule memory written at its starting point (the background worker only,
    ADR-237 (6))."""
    ev, memory, marker = await _evaluate_stored(conn, user_ref, strategy_id, body, state, scn, position,
                                                gap_until=gap_until)
    for rid, mem in ev.memory.items():
        if memory.get(rid) != mem:
            await playbook_store.put_rule_state(conn, user_ref, strategy_id, rid, held_at_entry=mem["held_at_entry"],
                                                seen_clear=mem["seen_clear"], adjustment_no=marker)
    return ev


def stage_name_text(name: str | None) -> Any:
    """A playbook stage's name as catalogue text ("Last day" has a space, so it can never be an Identifier); None
    for no stage. A name the slot refuses reads "current" (``stage_words``), never a 500."""
    return None if name is None else render_explanation("adjust_check_stage_name", name=pe.stage_words(name))


def stage_out(name: str | None, index: int | None) -> dict[str, Any]:
    """The reply's stage object, shared by every route that echoes the evaluated stage."""
    return {"name": stage_name_text(name), "index": index}


SIT_S12 = pe.situation_rule_id(pe.BIG_WIN_EARLY)  # its value is a % of max profit


def trigger_words(body: Mapping | None, trigger_id: str | None) -> tuple[str | None, str | None]:
    """(label, unit) of a trigger as the evaluated body holds them; (None, None) for a body or trigger without them.
    A day rule (GC-IC1 1a, ``day.<when>.<HHMM>.<n>``): its action's catalogue words and "%" (its value is a distance
    from spot in %)."""
    if trigger_id == pe.sl.CREDIT_RULE:  # contract step 3: the 2x-credit stop line, catalogue words, rupees
        return STOP_LABEL_TEXT["credit_x"], "Rs"
    watched = level_watch.direction_of(trigger_id)  # GC-IC1 4c (A-37): its words by direction; no unit
    if watched is not None:
        return LEVEL_WATCH_LABEL_TEXT[watched], None
    situation = pe.situation_of(body, trigger_id)  # GC-IC1 6a: S-02 / S-12 read as the playbook names them
    if situation is not None:
        name = situation.get("name")
        return (name if isinstance(name, str) else None), (DAY_RULE_UNIT if trigger_id == SIT_S12 else None)
    action = pe.day_rule_action(body, trigger_id)
    if action is not None:
        words = PLAYBOOK_DAY_RULE_ACTION_TEXT.get(str(action))
        return (words, DAY_RULE_UNIT) if words is not None else (None, None)
    trig =(body or {}).get("triggers", {}).get(trigger_id) if isinstance(body, Mapping) else None
    if not isinstance(trig, Mapping):
        return None, None
    label, unit = trig.get("label"), trig.get("unit")
    return (label if isinstance(label, str) else None), (unit if isinstance(unit, str) else None)


def condition_line(trigger_id: str, label: str | None, unit: str | None, value: str, threshold: str,  # noqa: PLR0913
                   beyond: tuple[str, Decimal, Decimal] | None = None) -> Any:
    """GC-ADJ2 item 1: "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)" from the trigger's own label
    and unit. A label the slot refuses or a body without one -> the trigger id (fail visible); a unit that is empty
    or not a plain unit -> the line without it."""
    def line(lab: str, un: str | None) -> Any:
        if un == CLOCK_UNIT:  # a clock trigger: HH:MM value and threshold, no unit word
            return render_explanation("adjust_condition_line_time", label=lab, value=value, threshold=threshold)
        if un:
            return render_explanation("adjust_condition_line", label=lab, value=value, unit=un, threshold=threshold)
        return render_explanation("adjust_condition_line_plain", label=lab, value=value, threshold=threshold)

    if beyond is not None and beyond[0] in ("CE", "PE"):  # ADR-268 (2): never "0 %" for a breached short
        try:
            return render_explanation(f"adjust_condition_line_t01_beyond_{beyond[0].lower()}",
                                      label=label if label is not None else trigger_id, strike=beyond[1],
                                      points=beyond[2])
        except (TypeError, ValueError):  # a refused slot: the plain line below (fail visible)
            pass
    try:
        return line(label if label is not None else trigger_id, unit)
    except (TypeError, ValueError):  # the slot refused the label or the unit: the id, with no unit (fail visible)
        pass
    try:
        return line(trigger_id, None)
    except (TypeError, ValueError):  # the value itself is refused: the trigger id alone, never a 500
        return render_explanation("adjust_condition_line_id", label=trigger_id)


def condition_line_t19(label: str | None, value: str, threshold: str, approach: str, cost: Decimal,  # noqa: PLR0913
                       unpriced: int = 0) -> Any:
    """ADR-221: the T-19 line with the cheapest approach that could be priced and its Compare cost, saying how many
    offered approaches could not be priced (left out); an approach or label the slot refuses -> the plain condition
    line (fail visible, never a guessed name). The check reply and the opportunities list both draw it here."""
    slots = {"label": label if label is not None else "T-19", "value": value, "threshold": threshold,
             "approach": approach, "cost": cost}
    try:
        if unpriced > 0:
            return render_explanation("adjust_condition_line_t19_unpriced", **slots, count=unpriced)
        return render_explanation("adjust_condition_line_t19", **slots)
    except (TypeError, ValueError):
        return condition_line("T-19", label, None, value, threshold)
