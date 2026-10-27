"""W-125 (REQ-079 AC-2..AC-9; ADR-150 (2), ADR-157, ADR-015): load a catalogue template or a straddle / strangle
quick pick at strikes placed by a fixed rule. HELD for the Q211 legal answer (``held_switches.PLATFORM_STRIKES``).

``POST /api/strategies/load-template`` and ``POST /api/strategies/quick-pick``: the server reads the live spot and the
stored catalogue, places strikes with ``ofo.strategy.placement`` and answers legs the builder can edit. Nothing is saved
and no order is touched. With the switch off both routes refuse with the held reason BEFORE any market or database read
(a router-level dependency, like ``order_path_switch``). A refusal never echoes a request value.
"""
from __future__ import annotations

import asyncio
import datetime
import itertools
import time
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from ofo.engine.legs import Action
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from ofo.strategy.loader import load_templates
from ofo.strategy.placement import (
    Market,
    PlacedLeg,
    PlacementRefused,
    QuickPick,
    Refusal,
    expiry_slots,
    place_quick_pick,
    place_template,
)
from pydantic import ConfigDict

from ofo_app import held_switches
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money
from ofo_app.chain_push import ChainCatalogue, ChainReader, index_id_of, live_spot
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.live_push import LiveFeed
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.chain import get_chain_reader
from ofo_app.routes.leg_picker import WindowLease, get_feed
from ofo_app.routes.outcome import MarketContext, get_market_context
from ofo_app.routes.strategies import StrategyRefused
from ofo_app.underlying import Underlying

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
#: The routes' own hold on the index (finding live-read-without-own-subscription): a WindowLease like the picker's,
#: one per viewer and underlying, ended LEASE_SECONDS (30 s) after the last read. The same ONE shared fan-out: no second
#: vendor connection. Known bypass: with no live feed (None) nothing is held and the old context read answers.
INDEX_LEASE = WindowLease()
SPOT_WAIT_SECONDS = 3.0  # the most a request waits for the first index frame before refusing SPOT_MISSING
SPOT_POLL_SECONDS = 0.1


def _now() -> float:
    return time.monotonic()


def require_platform_strikes() -> None:
    """The held refusal (409, catalogue message ``ready_made_held``) while off; runs before the handler."""
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
    underlying: Underlying
    legs: list[PlacedLegOut]


class LoadTemplateIn(ApiModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Underlying
    template_id: Identifier
    expiry: datetime.date


class QuickPickIn(ApiModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Underlying
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


async def _hold_and_read(feed: LiveFeed | None, ctx: MarketContext | None, underlying: str,
                         viewer: str) -> tuple[Decimal | None, bool]:
    """Take the request's own short lease on the index, then read the spot, waiting at most ``SPOT_WAIT_SECONDS``
    (polling every ``SPOT_POLL_SECONDS``, never a busy loop) for the first frame. Answer states: usable -> placed; present but
    stale -> returned at once (SPOT_STALE); absent after the wait -> (None, False) (SPOT_MISSING); the provider refuses
    the index (unknown instrument / error) -> the lease holds nothing, no wait."""
    if feed is not None and ctx is not None:
        index_id = index_id_of(ctx, underlying)
        if index_id is not None:
            INDEX_LEASE.hold(feed, (viewer, underlying, "ready-made"), [index_id])
            if not INDEX_LEASE.ids_of((viewer, underlying, "ready-made")):
                return _spot(ctx, underlying)
    deadline = _now() + (SPOT_WAIT_SECONDS if feed is not None else 0.0)
    while True:
        spot, fresh = _spot(ctx, underlying)
        if spot is not None or _now() >= deadline:
            return spot, fresh
        await asyncio.sleep(SPOT_POLL_SECONDS)


def _gap(strikes: set[Decimal]) -> Decimal:
    ordered = sorted(strikes)
    gaps = [b - a for a, b in itertools.pairwise(ordered)]
    if not gaps:
        raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
    return min(gaps)


def _strikes(catalogue: ChainCatalogue) -> set[Decimal]:
    return {c.strike for c in catalogue.contracts if c.strike is not None}


def _out(underlying: str, placed: tuple[PlacedLeg, ...], catalogues: dict[datetime.date, ChainCatalogue],
         ) -> ReadyMadeOut:
    label = render_explanation("ready_made_fixed_rule_label")
    legs = []
    for leg in placed:
        match = [c for c in catalogues[leg.expiry].contracts
                 if c.instrument_type == leg.instrument.value and c.strike == leg.strike]
        if leg.strike is None or len(match) != 1:  # a future, or a contract the stored list does not hold exactly once
            raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
        legs.append(PlacedLegOut(action=leg.action.value, instrument=leg.instrument.value,  # type: ignore[arg-type]
                                 strike=leg.strike.quantize(PAISE), expiry=leg.expiry,
                                 instrument_id=match[0].instrument_id,
                                 symbol=match[0].symbol, label=label))
    return ReadyMadeOut(underlying=underlying, legs=legs)  # type: ignore[arg-type]


def _refused(underlying: str, refusal: PlacementRefused) -> StrategyRefused:
    template = _MESSAGE[refusal.reason]
    slots = {} if template == HELD_TEMPLATE else {"underlying": underlying}
    return StrategyRefused(template, message=render(template, **slots))


@router.post(LOAD_PATH, response_model=ReadyMadeOut)
async def load_template(
        body: LoadTemplateIn,
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        reader: Annotated[ChainReader, Depends(get_chain_reader)],
        feed: Annotated[LiveFeed | None, Depends(get_feed)],
        viewer: Annotated[str, Depends(current_user_ref)],
) -> ReadyMadeOut:
    template = next((t for t in load_templates() if t.id == body.template_id), None)
    if template is None:
        raise StrategyRefused("user_input_request_invalid")
    try:
        spot, fresh = await _hold_and_read(feed, ctx, body.underlying, viewer)
        near = await reader(body.underlying, body.expiry)
        if near.unreadable or body.expiry not in near.expiries:
            raise PlacementRefused(Refusal.EXPIRY_MISSING)
        slots = expiry_slots(body.expiry, near.expiries)
        catalogues = {body.expiry: near}
        for day in {d for d in slots.values() if d is not None and d != body.expiry}:
            catalogues[day] = await reader(body.underlying, day)
        placed = place_template(template, slots, Market(spot, fresh, _gap(_strikes(near))),
                                {d: _strikes(c) for d, c in catalogues.items()})
        return _out(body.underlying, placed, catalogues)
    except PlacementRefused as refusal:
        raise _refused(body.underlying, refusal) from None


@router.post(QUICK_PICK_PATH, response_model=ReadyMadeOut)
async def quick_pick(
        body: QuickPickIn,
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        reader: Annotated[ChainReader, Depends(get_chain_reader)],
        feed: Annotated[LiveFeed | None, Depends(get_feed)],
        viewer: Annotated[str, Depends(current_user_ref)],
) -> ReadyMadeOut:
    try:
        spot, fresh = await _hold_and_read(feed, ctx, body.underlying, viewer)
        catalogue = await reader(body.underlying, body.expiry)
        if catalogue.unreadable or body.expiry not in catalogue.expiries:
            raise PlacementRefused(Refusal.EXPIRY_MISSING)
        strikes = _strikes(catalogue)
        pick = QuickPick(body.kind, body.underlying, body.distance, Action(body.side), body.expiry)
        placed = place_quick_pick(pick, Market(spot, fresh, _gap(strikes)), strikes)
        return _out(body.underlying, placed, {body.expiry: catalogue})
    except PlacementRefused as refusal:
        raise _refused(body.underlying, refusal) from None
