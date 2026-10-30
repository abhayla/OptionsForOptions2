"""POST /api/strategies/{id}/adjustment-approaches (REQ-155 AC-2..AC-8, ADR-214; goal contract GC-ADJ1 "API").

One request answers the Before (the current legs' whole-trade figures) and every approach of a tracked iron condor:
the exact trades, the After legs, the closed legs, the whole-trade After from the one engine
(``whole_trade.whole_trade_after``: booked P&L in; adjustment, paid and open-exit charges as their own lines),
POP under the held switch ``probability_of_profit`` (never a second switch), Zerodha's basket margin for the After legs
with its state, the spot with its source and time, and a refusal (naming the leg) per approach that cannot be built.
The browser computes nothing. Suggest-only (ADR-003): nothing here places, changes or cancels an order.

Answer states of every outside source (standing item d):
- spot: feed / REST index quote / last close / none (``resolve_spot``); none -> no After at all, each source's reason.
- margin: CHECKED -> value + time; any other state (failed, timed out, not signed in, busy, no basket) -> "Margin not
  available" with Zerodha's reason; empty (CHECKED without a figure) -> not available, never 0; a margin read that
  raises for one approach -> that approach alone says not available.
- booked P&L: stated -> in every figure; could not be read -> no whole-trade figure, the reason shown, never 0.
- charge rates: stated -> three lines; unreadable or not computable -> charges not available, the gross figures still
  shown, the after-charges figures withheld.
- chain row: per ``ofo.adjustment.approaches`` (refusal naming the leg, or a low-OI warning).

Seams (FastAPI dependencies; tests and scenario mode override them): the tracked-strategy reader, the market reader
(chain rows, POP inputs, feed and last-close spot readings), the REST index spot reader, the per-approach margin and the
held-switch environment (``held_switches``' own ``environ`` seam).
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from ofo.adjustment.approaches import (
    APPROACH_IDS,
    ApproachLegs,
    ChainRow,
    Position,
    PositionLeg,
    build_approach,
    load_config,
)
from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import charge_segment, to_paise_up
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED, MultiExpiryError
from ofo.engine.pop import Why
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import WholeTradeAfter, WholeTradeFigures, whole_trade_after
from ofo.errors.explanations import approach_name_id, render_explanation
from ofo.marketdata.spot_source import SourceReading, SpotAnswer, resolve_spot
from ofo.money import PAISE
from ofo.outcome.service import MARGIN_CHECKED, Margin
from ofo.timeutil import IST
from pydantic import BaseModel, ConfigDict, Field

from ofo_app.api_models import AdjustApproachesOut
from ofo_app.config import app_env
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.held_switches import PROBABILITY_OF_PROFIT, held_on
from ofo_app.outcome_margin import OutcomeMargin, PlannedOrderIn, margin_answer
from ofo_app.routes.outcome import MarketContext, get_margin_source, get_market_context, load_charge_rates
from ofo_app.routes.strategies import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_CONFIG = load_config()
_DEV_TIMING = frozenset({"development", "test"})


# ---- inputs the seams hand over ----------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Tracked:
    """A tracked strategy as the builder needs it. ``booked`` None = the book could not be read (never 0);
    ``paid_charges`` None = the charges already paid could not be priced."""

    position: Position
    booked: Decimal | None
    paid_charges: Decimal | None


@dataclasses.dataclass(frozen=True)
class MarketInputs:
    """The chain of the position's expiry, POP's inputs (None -> the named reason) and the spot readings."""

    chain: tuple[ChainRow, ...]
    instrument_ids: Mapping[str, str]  # tradingsymbol -> instrument id (the margin basket's key)
    forward: Decimal | None
    years: Decimal | None
    vol: Decimal | None
    feed: SourceReading | None
    last_close: SourceReading | None
    now: datetime.datetime
    expiry_kind: str | None = None  # weekly / monthly from the listed expiries (None: keep the tracked value)


TrackedReader = Callable[[int, ChargeRates | None], Awaitable[Tracked | None]]
MarketReader = Callable[[Tracked, MarketContext | None], Awaitable[MarketInputs]]
RestSpotReader = Callable[[str], Awaitable[SourceReading]]
ApproachMargin = Callable[[list[PlannedOrderIn]], Awaitable[Margin]]


def get_tracked_reader() -> TrackedReader:
    """The paper book reader (``adjustment_readers.read_tracked``); tests override it."""
    from ofo_app.adjustment_readers import read_tracked  # noqa: PLC0415 - it imports this module's dataclasses
    return read_tracked


def get_market_reader() -> MarketReader:
    """The market reader over the outcome's market context (``adjustment_readers.read_market``)."""
    from ofo_app.adjustment_readers import read_market  # noqa: PLC0415 - as above
    return read_market


def get_rest_spot_reader() -> RestSpotReader:
    """The REST index quote (``adjustment_readers.read_rest_spot``; scenario mode answers through the same client)."""
    from ofo_app.adjustment_readers import read_rest_spot  # noqa: PLC0415 - as above
    return read_rest_spot


def get_approach_margin(ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                        source: Annotated[OutcomeMargin | None, Depends(get_margin_source)]) -> ApproachMargin:
    """Zerodha's basket margin for one approach's After legs, through the outcome's own margin path (ADR-099)."""
    async def read(legs: list[PlannedOrderIn]) -> Margin:
        return await margin_answer(source, ctx, legs)
    return read


def get_held_environ() -> Mapping[str, str] | None:
    """``held_switches``' own seam: None reads the process environment."""
    return None


# ---- request / reply ----------------------------------------------------------------------------------------------

class ApproachesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approaches: list[str] | None = Field(default=None, max_length=32)
    view: str = Field(default="at_expiry", pattern=r"^(at_expiry|estimated_now)$")


def _money(value: Decimal | object) -> str:
    return "UNLIMITED" if value is UNLIMITED else value  # type: ignore[return-value]  # Money serializes as text


def _figures(f: WholeTradeFigures) -> dict:
    return {"max_profit": _money(f.max_profit), "max_loss": _money(f.max_loss),
            "breakevens": [_money(b) for b in f.breakevens],
            "loss_regions": [[None if x is None else _money(x) for x in r[:2]] for r in f.loss_regions]}


_POP_TEXT = {Why.NO_VOLATILITY: "adjust_pop_no_volatility", Why.NO_FORWARD: "adjust_pop_no_forward",
             Why.MIXED_EXPIRIES: "adjust_pop_different_expiries",
             Why.SPOT_STALE_OR_MISSING: "adjust_pop_spot_stale_or_missing"}


def pop_block(after: WholeTradeAfter, pop_on: bool) -> dict:
    """The held switch first: OFF -> "-" with the held reason, never a figure (ADR-156 / ADR-165)."""
    if not pop_on:
        return {"value": None, "not_available": True, "reason": render_explanation("adjust_pop_held")}
    if after.pop is None:
        why = after.pop_unavailable or Why.NO_VOLATILITY
        return {"value": None, "not_available": True, "reason": render_explanation(_POP_TEXT[why])}
    return {"value": _money(after.pop), "not_available": False, "reason": None}


def margin_block(margin: Margin | None) -> dict:
    """CHECKED with a figure -> stated; CHECKED without one -> empty (never 0); anything else -> not available."""
    if margin is None:
        return {"state": "failed", "value": None, "at": None,
                "reason": render_explanation("adjust_margin_not_available",
                                             reason=render_explanation("outcome_margin_unreadable"))}
    if margin.state == MARGIN_CHECKED:
        if margin.broker_needed is None or margin.checked_at is None:
            return {"state": "empty", "value": None, "at": None, "reason": render_explanation("adjust_margin_empty")}
        return {"state": "stated", "value": _money(margin.needed if margin.needed is not None
                                                     else margin.broker_needed),
                "at": margin.checked_at, "reason": None}
    return {"state": margin.state.lower(), "value": None, "at": None,
            "reason": render_explanation("adjust_margin_not_available", reason=margin.reason)}


def _spot_block(answer: SpotAnswer) -> dict:
    reasons = [{"source": s, "reason": r} for s, r in answer.reasons]
    if not answer.available:
        why = dict(answer.reasons)
        text = render_explanation("adjust_spot_not_available", feed=why.get("feed", "absent"),
                                  rest=why.get("rest_quote", "absent"), close=why.get("last_close", "absent"))
        return {"value": None, "source": None, "source_text": None, "at": None, "reasons": reasons, "text": text}
    return {"value": _money(answer.value), "source": answer.source,
            "source_text": render_explanation(f"adjust_spot_from_{answer.source}"), "at": answer.at,
            "reasons": reasons, "text": None}


# ---- pricing (engine time) ----------------------------------------------------------------------------------------

def _strategy(legs: Sequence[PositionLeg], lot: int) -> Strategy:
    return Strategy(tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * lot, x.entry)
                          for x in legs))


def _charges(orders: Sequence[ChargeOrder], rates: ChargeRates) -> Decimal:
    return to_paise_up(charges_for_orders(list(orders), rates).total) if orders else Decimal(0)


def _closed_booked(built: ApproachLegs) -> Decimal:
    """The booked P&L of the legs this approach closes, at the planned exit: (exit - entry) x signed quantity."""
    return sum(((c.exit - c.entry) * c.quantity * (1 if c.side == "BUY" else -1) for c in built.closed), Decimal(0))


@dataclasses.dataclass(frozen=True)
class Priced:
    after: WholeTradeAfter | None
    charges_known: bool
    reason: Any = None  # an ExplanationText when no whole-trade figure is given


def price_after(legs: Sequence[PositionLeg], position: Position, booked: Decimal | None, paid: Decimal | None,  # noqa: PLR0913
                own_orders: Sequence[ChargeOrder], rates: ChargeRates | None, market: MarketInputs) -> Priced:
    """The whole-trade After of ``legs`` (``booked`` already includes the legs this approach closes)."""
    if booked is None:
        return Priced(None, False, render_explanation("adjust_booked_unknown"))
    segment = charge_segment(position.underlying)
    known = rates is not None and paid is not None
    adjustment = exits = Decimal(0)
    if known:
        try:
            adjustment = _charges(own_orders, rates)  # type: ignore[arg-type]
            exits = _charges([ChargeOrder(segment, "SELL" if x.side == "BUY" else "BUY", x.lots * position.lot,
                                          x.entry) for x in legs], rates)  # type: ignore[arg-type]
        except ValueError:
            known = False
    try:
        open_legs = _strategy(legs, position.lot) if legs else None  # None: every leg exited (A-31)
        after = whole_trade_after(open_legs, booked_pnl=booked.quantize(PAISE),
                                  paid_charges=paid if known else Decimal(0),  # type: ignore[arg-type]
                                  adjustment_charges=adjustment if known else Decimal(0),
                                  open_exit_charges=exits if known else Decimal(0),
                                  forward=market.forward, years=market.years, vol=market.vol)
    except MultiExpiryError:
        return Priced(None, known, render_explanation("adjust_needs_one_expiry"))
    return Priced(after, known)


def _after_block(priced: Priced, pop_on: bool) -> dict:
    if priced.after is None:
        return {"after": None, "charges": None, "pop": None, "after_reason": priced.reason}
    a = priced.after
    charges = ({"this_adjustment": _money(a.adjustment_charges), "paid_so_far": _money(a.paid_charges),
                "open_exit": _money(a.open_exit_charges), "not_available": None} if priced.charges_known else
               {"this_adjustment": None, "paid_so_far": None, "open_exit": None,
                "not_available": render_explanation("adjust_charges_unknown")})
    return {"after": {"gross": _figures(a.gross), "after_charges": _figures(a.after_charges)
                      if priced.charges_known else None, "booked_pnl": _money(a.booked_pnl)},
            "charges": charges, "pop": pop_block(a, pop_on), "after_reason": None}


def _trade_orders(built: ApproachLegs, underlying: str) -> list[ChargeOrder]:
    segment = charge_segment(underlying)
    return [ChargeOrder(segment, t.action, t.quantity, t.price) for t in built.trades]


def _leg_out(x: Any) -> dict:
    return dataclasses.asdict(x)


# ---- route --------------------------------------------------------------------------------------------------------

@router.post("/api/strategies/{strategy_id}/adjustment-approaches", response_model=AdjustApproachesOut)
async def adjustment_approaches(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, body: ApproachesIn,
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        held_environ: Annotated[Mapping[str, str] | None, Depends(get_held_environ)]) -> AdjustApproachesOut:
    started = time.perf_counter()
    from ofo_app.adjustment_readers import TrackedUnreadable  # noqa: PLC0415 - as above
    try:
        tracked = await tracked_reader(strategy_id, rates if isinstance(rates, ChargeRates) else None)
    except TrackedUnreadable as exc:  # the strategy is this user's but its legs cannot be read: named, not guessed
        log.warning("adjustment approaches: strategy %s unreadable: %s", strategy_id, exc)
        raise StrategyRefused("user_input_request_not_available", Failure.CONFLICT) from None
    if tracked is None:  # not this user's, or no such strategy: nothing priced (attack 1)
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    rates = rates if isinstance(rates, ChargeRates) else None
    market = await market_reader(tracked, ctx)
    tracked = dataclasses.replace(tracked, position=dataclasses.replace(
        tracked.position, today=market.now.astimezone(IST).date(),
        expiry_kind=market.expiry_kind or tracked.position.expiry_kind))
    spot = resolve_spot(market.feed, await rest_reader(tracked.position.underlying), market.last_close, now=market.now)
    pop_on = held_on(PROBABILITY_OF_PROFIT, held_environ)
    asked = list(dict.fromkeys(body.approaches)) if body.approaches is not None else list(APPROACH_IDS)
    reply: dict[str, Any] = {"strategy_id": strategy_id, "view": body.view, "spot": _spot_block(spot),
                             "pop_switch_on": pop_on}
    position = tracked.position
    engine = 0.0
    if not spot.available:  # AC-5: no After at all
        reply |= {"before": None, "approaches": []}
        built_list: list[tuple[str, ApproachLegs | None]] = []
    else:
        t0 = time.perf_counter()
        before = price_after(position.legs, position, tracked.booked, tracked.paid_charges, (), rates, market)
        reply["before"] = _after_block(before, pop_on)
        built_list = [(a, build_approach(position, market.chain, spot.value, a, _CONFIG)  # type: ignore[arg-type]
                       if a in APPROACH_IDS else None) for a in asked]
        priced: dict[str, Priced] = {}
        for a, built in built_list:
            if built is not None and built.refusal is None:
                booked = None if tracked.booked is None else tracked.booked + _closed_booked(built)
                priced[a] = price_after(built.after, position, booked, tracked.paid_charges,
                                        _trade_orders(built, position.underlying), rates, market)
        engine = time.perf_counter() - t0
        out = []
        for a, built in built_list:
            if built is None:  # attack 2: refused by name, the others still answer
                out.append({"id": a, "refusal": render_explanation("adjust_unknown_approach", approach=a)})
                continue
            item: dict[str, Any] = {"id": built.id, "name": render_explanation(approach_name_id(built.id)),
                                    "kind": built.kind, "side": built.side,
                                    "step_basis": built.step_basis,
                                    "step_value": None if built.step_value is None else _money(built.step_value),
                                    "refusal": built.refusal_message, "warnings": list(built.warning_messages)}
            if built.refusal_message is None:
                item |= {"trades": [_leg_out(t) for t in built.trades],
                         "after_legs": [_leg_out(x) for x in built.after],
                         "closed_legs": [_leg_out(c) for c in built.closed], **_after_block(priced[a], pop_on)}
                item["margin"] = await _margin(margin_of, built, market)
            out.append(item)
        reply["approaches"] = out
    total = time.perf_counter() - started
    log.info("adjustment approaches strategy=%s approaches=%s engine_s=%.4f total_s=%.4f",
             strategy_id, len(built_list), engine, total)
    if app_env() in _DEV_TIMING:
        reply["timing"] = {"engine_seconds": Decimal(f"{engine:.4f}"), "total_seconds": Decimal(f"{total:.4f}"),
                           "approaches": len(built_list)}
    return AdjustApproachesOut.model_validate(reply)


async def _margin(margin_of: ApproachMargin, built: ApproachLegs, market: MarketInputs) -> dict:
    """AC-6: the After legs' basket margin; one approach's failure never touches another's (attack 4)."""
    if not built.after:  # every leg exits (A-31): nothing stays open, so no margin is needed (no figure, not 0)
        return {"state": "not_needed", "value": None, "at": None, "reason": None}
    try:
        legs = [PlannedOrderIn(market.instrument_ids[x.tradingsymbol], x.side, x.lots, x.entry) for x in built.after]
        return margin_block(await margin_of(legs))
    except Exception:  # noqa: BLE001 - one approach's margin read failing is that approach's "not available"
        log.warning("adjustment margin read failed for %s", built.id)
        return margin_block(None)
