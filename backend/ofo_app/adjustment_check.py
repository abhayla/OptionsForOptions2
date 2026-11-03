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
- expiry_kind: ``MarketInputs.expiry_kind``; prev_close: the last-close reading when STATED; day_open: no reader
  yet -> None (T-13 is never checked from here). adjustments_used: ``Tracked.adjustments_used`` (not recorded -> None).
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
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import Config, Position
from ofo.adjustment.compare import Cheapest, Column, MarginRead, cheapest_approach
from ofo.adjustment.offered import offered_now
from ofo.adjustment.strategy_type import strike_gap_of, type_of
from ofo.engine import adjust_money
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED
from ofo.errors.explanations import PLAYBOOK_DAY_RULE_ACTION_TEXT, render_explanation
from ofo.marketdata.spot_source import SourceState, SpotAnswer
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
    status: str | None
    is_system: bool


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


async def resolve(conn: Any, user_ref: str, strategy_id: int, stype: str | None) -> Resolved:
    plan = await playbook_store.plan_for(conn, user_ref, strategy_id)
    if plan is not None:
        return Resolved("plan", plan.body, plan.playbook_id, plan.body.get("status"), False)
    if stype is None:
        return Resolved("none", None, None, None, False)
    pb = await playbook_store.active_for(conn, user_ref, stype)
    return Resolved("system" if pb.is_system else "active", pb.body, pb.id, pb.status, pb.is_system)


def _limit_value(v: Any) -> Decimal | str:
    return pe.UNLIMITED if v is UNLIMITED else v


def _tighten(body: Mapping, today: datetime.date, expiry: datetime.date, hhmm: str) -> Decimal | None:
    """The due "Tighten every trigger by X%" day rule (``when: expiry``) on expiry day from its time on."""
    for rule in body.get("day_rules", []):
        if rule.get("on") and rule.get("when") == "expiry" and rule.get("percent") and today == expiry \
                and hhmm >= rule.get("at", "99:99"):
            return Decimal(rule["percent"])
    return None


def prices_fresh(ctx: Any) -> bool | None:
    if ctx is None:
        return None
    health = getattr(ctx.provider.status().health, "value", None)
    return True if health == _HEALTH_FRESH else False if health == _HEALTH_STALE else None


def _abs_delta(market: MarketInputs, symbol: str) -> Decimal | None:
    g = market.leg_greeks.get(symbol)
    return None if g is None or g.delta is None else abs(g.delta)


def guards_of_body(body: Mapping | None) -> dict[str, Any] | None:
    """The ``guards`` of a resolved playbook body (ADR-230 (1)); None when there is no body. The route's reader
    (``adjustment_readers.read_guards``) and T-19 both read guards through this."""
    return None if body is None else dict(body.get("guards", {}))


def cheapest_offered(body: Mapping | None, tracked: Tracked, market: MarketInputs, spot: Decimal | None,  # noqa: PLR0913 - the preferences value is a required parameter (GC-SET)
                     rates: Any, config: Config, *, before: Any = None) -> Cheapest:
    """ADR-221: the cheapest approach ``body`` offers, every one built and priced by the Compare's own path.
    ``before``: the Before already priced by the caller (``price_after`` of the current legs: it reads only the legs,
    the underlying and the lot, which ``as_of_market`` leaves unchanged), so the own legs are priced once per check;
    None prices it here."""
    offered = offered_now(body, tracked.adjustments_used)  # S-11: only exit and reduce at the limit
    if spot is None:  # nothing can be built without spot: none priceable (T-19 is withheld for no spot anyway)
        return cheapest_approach(offered, {}, market.chain)
    columns: dict[str, Column] = {}
    tracked = as_of_market(tracked, market)  # as the approaches route builds (market day, listed expiry kind)
    position = tracked.position  # the route's Before and guards, through the same helpers (#633, ADR-230 (1))
    if before is None:
        before = price_after(position.legs, position, tracked.booked, tracked.paid_charges, (), rates, market)
    limits, max_profit = liquidity_inputs(guards_of_body(body), before)
    for a in offered:
        built, priced = priced_approach(a, tracked, market, spot, rates, config, limits=limits, max_profit=max_profit)
        if built is not None and priced is not None:
            columns[a] = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None))
    return cheapest_approach(offered, columns, market.chain)


def state_of(tracked: Tracked, market: MarketInputs, spot: SpotAnswer, margin: Mapping | None,  # noqa: PLR0913
             rates: Any, fresh: bool | None, body: Mapping | None = None, *,
             config: Config) -> pe.StrategyState:
    position = tracked.position
    rows = {r.tradingsymbol: r for r in market.chain}
    ltp = {x.tradingsymbol: getattr(rows.get(x.tradingsymbol), "ltp", None) for x in position.legs}
    priced = all(v is not None for v in ltp.values())
    value = spot.value if spot.available else None
    shorts = tuple(pe.ShortLeg(x.strike, _abs_delta(market, x.tradingsymbol), ltp[x.tradingsymbol])
                   for x in position.legs if x.side == Action.SELL.value)
    qty = {x.tradingsymbol: x.lots * position.lot for x in position.legs}
    booked = tracked.booked
    pnl = None if booked is None or not priced else adjust_money.pnl_now(
        booked, ((x.side, x.entry, ltp[x.tradingsymbol], qty[x.tradingsymbol]) for x in position.legs))
    left = adjust_money.premium_left((x.side, ltp[x.tradingsymbol], qty[x.tradingsymbol])
                                     for x in position.legs) if priced else None
    before = price_after(position.legs, position, booked, tracked.paid_charges, (), rates, market)  # once per check
    cheap = cheapest_offered(body, tracked, market, value, rates, config, before=before)
    gross = None if before.after is None else before.after.gross
    expiry_pnl = None
    if value is not None and booked is not None:
        from ofo.engine.strategy import Strategy  # noqa: PLC0415 - engine type only here
        expiry_pnl = adjust_money.with_booked(booked, Strategy(_engine_legs(position)).expiry_pnl_at(value))
    now = market.now.astimezone(IST)
    expiry = min(x.expiry for x in position.legs)
    hhmm = now.strftime("%H:%M")
    stated_margin = Decimal(margin["value"]) if margin is not None and margin.get("state") == "stated" else None
    last = market.last_close
    return pe.StrategyState(
        expiry_kind=market.expiry_kind or position.expiry_kind or "weekly",  # type: ignore[arg-type]
        days_left=(expiry - now.date()).days, hhmm=hhmm, spot=value, shorts=shorts, pnl=pnl,
        max_loss=None if gross is None else _limit_value(gross.max_loss),
        max_profit=None if gross is None else _limit_value(gross.max_profit),
        margin=stated_margin, premium_left=left, adjustment_cost=cheap.cost, adjustment_approach=cheap.approach,
        adjustment_cost_reason=cheap.reason, adjustment_unpriced=cheap.unpriced, atm_iv=market.vol,
        prev_close=(last.value if last is not None and last.value is not None and last.state is SourceState.STATED
                    else None),
        adjustments_used=tracked.adjustments_used, expiry_pnl_at_spot=expiry_pnl,
        tighten_percent=None if body is None else _tighten(body, now.date(), expiry, hhmm), prices_fresh=fresh)


def scenario_entry(scn: Any, state: pe.StrategyState, position: Position) -> pe.StrategyState | None:
    """The scenario's ``position.entry`` as the F-71 entry state (None: the scenario states none)."""
    entry = (scn.data.get("position") or {}).get("entry") if scn is not None else None
    if not entry:
        return None
    clock = datetime.datetime.fromisoformat(entry["clock"]).astimezone(IST)
    expiry = min(x.expiry for x in position.legs)
    return pe.StrategyState(expiry_kind=state.expiry_kind, days_left=(expiry - clock.date()).days,
                            hhmm=clock.strftime("%H:%M"), spot=Decimal(str(entry["spot"])),
                            shorts=tuple(pe.ShortLeg(s.strike, None, None) for s in state.shorts),
                            atm_iv=None if entry.get("atm_iv") is None else Decimal(str(entry["atm_iv"])),
                            prices_fresh=True)


async def evaluate_stored(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                          state: pe.StrategyState, scn: Any, position: Position, *,
                          gap_until: str) -> tuple[pe.Evaluation, dict]:
    """The playbook evaluated against the STORED rule memory, writing nothing (the screen check's path; review round
    2, finding 3: the background worker is the one writer of adjustment state, ADR-237 (6)).
    Returns (evaluation, memory read)."""
    stored = await playbook_store.rule_state(conn, user_ref, strategy_id)
    memory = {k: {"held_at_entry": h, "seen_clear": s} for k, (h, s) in stored.items()}
    entry = scenario_entry(scn, state, position)
    if scn is not None and entry is not None:
        state = dataclasses.replace(state, entry_atm_iv=entry.atm_iv)
    elif not memory:
        entry = state  # tracking just started: this first check is the entry state
    return pe.evaluate(body, state, memory, entry, gap_until=gap_until), memory


async def evaluate_and_remember(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                                state: pe.StrategyState, scn: Any, position: Position, *,
                                gap_until: str) -> pe.Evaluation:
    """``evaluate_stored``, then the changed rule memory written (the background worker only, ADR-237 (6))."""
    ev, memory = await evaluate_stored(conn, user_ref, strategy_id, body, state, scn, position, gap_until=gap_until)
    for rid, mem in ev.memory.items():
        if memory.get(rid) != mem:
            await playbook_store.put_rule_state(conn, user_ref, strategy_id, rid, held_at_entry=mem["held_at_entry"],
                                                seen_clear=mem["seen_clear"])
    return ev


def stage_name_text(name: str | None) -> Any:
    """A playbook stage's name as catalogue text ("Last day" has a space, so it can never be an Identifier); None
    for no stage. A name the slot refuses reads "current" (``stage_words``), never a 500."""
    return None if name is None else render_explanation("adjust_check_stage_name", name=pe.stage_words(name))


def stage_out(name: str | None, index: int | None) -> dict[str, Any]:
    """The reply's stage object, shared by every route that echoes the evaluated stage."""
    return {"name": stage_name_text(name), "index": index}


def trigger_words(body: Mapping | None, trigger_id: str | None) -> tuple[str | None, str | None]:
    """(label, unit) of a trigger as the evaluated body holds them; (None, None) for a body or trigger without them.
    A day rule (GC-IC1 1a, ``day:<when>:<index>``): its action's catalogue words and "%" (its value is a distance
    from spot in %)."""
    action = pe.day_rule_action(body, trigger_id)
    if action is not None:
        words = PLAYBOOK_DAY_RULE_ACTION_TEXT.get(str(action))
        return (words, DAY_RULE_UNIT) if words is not None else (None, None)
    trig =(body or {}).get("triggers", {}).get(trigger_id) if isinstance(body, Mapping) else None
    if not isinstance(trig, Mapping):
        return None, None
    label, unit = trig.get("label"), trig.get("unit")
    return (label if isinstance(label, str) else None), (unit if isinstance(unit, str) else None)


def condition_line(trigger_id: str, label: str | None, unit: str | None, value: str, threshold: str) -> Any:
    """GC-ADJ2 item 1: "Spot within this % of a short strike: 0.3416 % (rule 0.5000 %)" from the trigger's own label
    and unit. A label the slot refuses or a body without one -> the trigger id (fail visible); a unit that is empty
    or not a plain unit -> the line without it."""
    def line(lab: str, un: str | None) -> Any:
        if un == CLOCK_UNIT:  # a clock trigger: HH:MM value and threshold, no unit word
            return render_explanation("adjust_condition_line_time", label=lab, value=value, threshold=threshold)
        if un:
            return render_explanation("adjust_condition_line", label=lab, value=value, unit=un, threshold=threshold)
        return render_explanation("adjust_condition_line_plain", label=lab, value=value, threshold=threshold)

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
