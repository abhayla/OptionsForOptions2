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
- adjustment_cost: the fixture convention ((ask - bid) x quantity + Rs 40 per open leg; no helper for the compare's
  "This adjustment" charges of closing and reopening the open legs exists yet); a leg without bid or ask -> None.
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
from ofo.adjustment.approaches import Position
from ofo.adjustment.strategy_type import strike_gap_of, type_of
from ofo.engine import adjust_money
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED
from ofo.marketdata.spot_source import SpotAnswer
from ofo.timeutil import IST

from ofo_app import playbook_store
from ofo_app.routes.adjustment import MarketInputs, Tracked, price_after

#: The scenario library's adjustment-cost convention (tests/adjust_scenarios_gen.py): Rs 40 a leg on top of the spread.
COST_PER_LEG: Final = Decimal(40)
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


def state_of(tracked: Tracked, market: MarketInputs, spot: SpotAnswer, margin: Mapping | None,  # noqa: PLR0913
             rates: Any, fresh: bool | None, body: Mapping | None = None) -> pe.StrategyState:
    position = tracked.position
    rows = {r.tradingsymbol: r for r in market.chain}
    ltp = {x.tradingsymbol: getattr(rows.get(x.tradingsymbol), "ltp", None) for x in position.legs}
    priced = all(v is not None for v in ltp.values())
    value = spot.value if spot.available else None
    shorts = tuple(pe.ShortLeg(x.strike, _abs_delta(market, x.tradingsymbol), ltp[x.tradingsymbol])
                   for x in position.legs if x.side == Action.SELL.value)
    qty = {x.tradingsymbol: x.lots * position.lot for x in position.legs}
    booked = tracked.booked
    pnl = None if booked is None or not priced else booked + adjust_money.closed_booked(
        (x.side, x.entry, ltp[x.tradingsymbol], qty[x.tradingsymbol]) for x in position.legs)
    left = adjust_money.premium_left((x.side, ltp[x.tradingsymbol], qty[x.tradingsymbol])
                                     for x in position.legs) if priced else None
    spreads = [(getattr(rows.get(x.tradingsymbol), "bid", None), getattr(rows.get(x.tradingsymbol), "ask", None))
               for x in position.legs]
    cost = None if any(b is None or a is None for b, a in spreads) else sum(
        ((a - b) * qty[x.tradingsymbol] + COST_PER_LEG for x, (b, a) in zip(position.legs, spreads, strict=True)),
        Decimal(0))
    before = price_after(position.legs, position, booked, tracked.paid_charges, (), rates, market)
    gross = None if before.after is None else before.after.gross
    expiry_pnl = None
    if value is not None and booked is not None:
        from ofo.engine.strategy import Strategy  # noqa: PLC0415 - engine type only here
        expiry_pnl = Strategy(_engine_legs(position)).expiry_pnl_at(value) + booked
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
        margin=stated_margin, premium_left=left, adjustment_cost=cost, atm_iv=market.vol,
        prev_close=last.value if last is not None and last.value is not None and last.state.name == "STATED" else None,
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


async def evaluate_and_remember(conn: Any, user_ref: str, strategy_id: int, body: Mapping,  # noqa: PLR0913
                                state: pe.StrategyState, scn: Any, position: Position) -> pe.Evaluation:
    stored = await playbook_store.rule_state(conn, user_ref, strategy_id)
    memory = {k: {"held_at_entry": h, "seen_clear": s} for k, (h, s) in stored.items()}
    entry = scenario_entry(scn, state, position)
    if scn is not None and entry is not None:
        state = dataclasses.replace(state, entry_atm_iv=entry.atm_iv)
    elif not memory:
        entry = state  # tracking just started: this first check is the entry state
    ev = pe.evaluate(body, state, memory, entry)
    for rid, mem in ev.memory.items():
        if memory.get(rid) != mem:
            await playbook_store.put_rule_state(conn, user_ref, strategy_id, rid, held_at_entry=mem["held_at_entry"],
                                                seen_clear=mem["seen_clear"])
    return ev
