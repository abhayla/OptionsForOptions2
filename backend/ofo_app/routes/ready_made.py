"""W-125 (REQ-079 AC-2..AC-9; ADR-150 (2), ADR-157, ADR-015): load a catalogue template or a straddle / strangle quick pick
at strikes placed by a fixed rule. HELD for the Q211 legal answer (``held_switches.PLATFORM_STRIKES``).

``POST /api/strategies/load-template`` and ``POST /api/strategies/quick-pick``: the server reads the live spot and the
stored catalogue, places strikes with ``ofo.strategy.placement`` and answers legs the builder can edit. Nothing is saved
and no order is touched. With the switch off both routes refuse with the held reason BEFORE any market or database read
(a router-level dependency, like ``order_path_switch``). A refusal never echoes a request value.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from ofo.engine.legs import Action
from ofo.errors.explanations import render_explanation
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from ofo.strategy.loader import load_templates
from ofo.strategy.placement import (
    PlacedLeg,
    PlacementRefused,
    Refusal,
    expiry_slots,
    place_quick_pick,
    place_template,
)
from pydantic import ConfigDict

from ofo_app import held_switches
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money
from ofo_app.chain_push import ChainCatalogue, ChainReader, live_spot
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.chain import get_chain_reader
from ofo_app.routes.outcome import MarketContext, get_market_context
from ofo_app.routes.strategies import StrategyRefused

LOAD_PATH = "/api/strategies/load-template"
QUICK_PICK_PATH = "/api/strategies/quick-pick"
HELD_TEMPLATE = "ready_made_held"
#: placement refusal -> the catalogue message that says it (REQ-049 reason for the spot, AC-6 for the expiry)
_MESSAGE = {
    Refusal.SPOT_MISSING: "ready_made_spot_unavailable", Refusal.SPOT_STALE: "ready_made_spot_unavailable",
    Refusal.EXPIRY_MISSING: "ready_made_expiry_missing", Refusal.STRIKE_NOT_LISTED: "ready_made_strike_not_listed",
    Refusal.DISTANCE_NOT_OFFERED: "ready_made_distance_invalid",
}
_UNUSABLE_SPOT = (DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE)


def require_platform_strikes() -> None:
    """The held refusal (409, catalogue message ``ready_made_held``) while the switch is off; runs before the handler."""
    if not held_switches.held_on(held_switches.PLATFORM_STRIKES):
        raise StrategyRefused(HELD_TEMPLATE, Failure.CONFLICT)


router = APIRouter(route_class=ClosedRoute, dependencies=[Depends(require_platform_strikes)])


class PlacedLegOut(ApiModel):
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE"]
    strike: Money
    expiry: datetime.date
    instrument_id: InstrumentId
    symbol: Identifier
    label: CatalogueText  # "Strikes placed by a fixed rule - change them" until the user edits the strike (AC-4)


class ReadyMadeOut(ApiModel):
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[PlacedLegOut]


class LoadTemplateIn(ApiModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    template_id: Identifier
    expiry: datetime.date


class QuickPickIn(ApiModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    kind: Literal["straddle", "strangle"]
    distance: int  # index points; a straddle sends 0 (ignored); a strangle's must be one of the offered distances
    side: Literal["BUY", "SELL"]
    expiry: datetime.date


def _spot(ctx: MarketContext | None, underlying: str) -> tuple[Decimal | None, bool]:
    """(the live index value or None, whether its feed health is usable now). No context -> (None, False)."""
    value = live_spot(ctx, underlying)
    if value is None or ctx is None:
        return None, False
    quote = ctx.provider.underlying_quote(underlying)
    return value, quote is not None and quote.health not in _UNUSABLE_SPOT


def _gap(strikes: set[Decimal]) -> Decimal:
    ordered = sorted(strikes)
    gaps = [b - a for a, b in zip(ordered, ordered[1:], strict=False)]
    if not gaps:
        raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
    return min(gaps)


def _strikes(catalogue: ChainCatalogue) -> set[Decimal]:
    return {c.strike for c in catalogue.contracts if c.strike is not None}


def _out(underlying: str, placed: tuple[PlacedLeg, ...], catalogues: dict[datetime.date, ChainCatalogue]) -> ReadyMadeOut:
    label = render_explanation("ready_made_fixed_rule_label")
    legs = []
    for leg in placed:
        match = [c for c in catalogues[leg.expiry].contracts
                 if c.instrument_type == leg.instrument.value and c.strike == leg.strike]
        if leg.strike is None or len(match) != 1:  # a future, or a contract the stored list does not hold exactly once
            raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
        legs.append(PlacedLegOut(action=leg.action.value, instrument=leg.instrument.value,  # type: ignore[arg-type]
                                 strike=leg.strike.quantize(PAISE), expiry=leg.expiry, instrument_id=match[0].instrument_id,
                                 symbol=match[0].symbol, label=label))
    return ReadyMadeOut(underlying=underlying, legs=legs)  # type: ignore[arg-type]


def _refused(underlying: str, refusal: PlacementRefused) -> StrategyRefused:
    from ofo.errors import render  # noqa: PLC0415 - the catalogue renderer, with the underlying where the text has a slot
    template = _MESSAGE[refusal.reason]
    slots = {} if template == HELD_TEMPLATE else {"underlying": underlying}
    return StrategyRefused(template, message=render(template, **slots))


@router.post(LOAD_PATH, response_model=ReadyMadeOut)
async def load_template(
        body: LoadTemplateIn,
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        reader: Annotated[ChainReader, Depends(get_chain_reader)],
) -> ReadyMadeOut:
    template = next((t for t in load_templates() if t.id == body.template_id), None)
    if template is None:
        raise StrategyRefused("user_input_request_invalid")
    try:
        spot, fresh = _spot(ctx, body.underlying)
        near = await reader(body.underlying, body.expiry)
        if near.unreadable or body.expiry not in near.expiries:
            raise PlacementRefused(Refusal.EXPIRY_MISSING)
        slots = expiry_slots(body.expiry, near.expiries)
        catalogues = {body.expiry: near}
        for day in {d for d in slots.values() if d is not None and d != body.expiry}:
            catalogues[day] = await reader(body.underlying, day)
        placed = place_template(template, expiries=slots, spot=spot, spot_fresh=fresh,
                                strike_gap=_gap(_strikes(near)),
                                listed_strikes={d: _strikes(c) for d, c in catalogues.items()})
        return _out(body.underlying, placed, catalogues)
    except PlacementRefused as refusal:
        raise _refused(body.underlying, refusal) from None


@router.post(QUICK_PICK_PATH, response_model=ReadyMadeOut)
async def quick_pick(
        body: QuickPickIn,
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        reader: Annotated[ChainReader, Depends(get_chain_reader)],
) -> ReadyMadeOut:
    try:
        spot, fresh = _spot(ctx, body.underlying)
        catalogue = await reader(body.underlying, body.expiry)
        if catalogue.unreadable or body.expiry not in catalogue.expiries:
            raise PlacementRefused(Refusal.EXPIRY_MISSING)
        strikes = _strikes(catalogue)
        placed = place_quick_pick(body.kind, underlying=body.underlying, distance=body.distance,
                                  side=Action(body.side), expiry=body.expiry, spot=spot, spot_fresh=fresh,
                                  strike_gap=_gap(strikes), listed_strikes=strikes)
        return _out(body.underlying, placed, {body.expiry: catalogue})
    except PlacementRefused as refusal:
        raise _refused(body.underlying, refusal) from None
