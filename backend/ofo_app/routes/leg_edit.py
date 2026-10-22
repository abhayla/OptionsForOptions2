"""POST /api/strategies/leg-edit (W-126; REQ-076, REQ-077, REQ-078; ADR-008, ADR-068, ADR-150).

The browser sends the builder's legs plus ONE edit (a strike step, the multiplier, a tick, a typed price, Reset Prices,
or a Shift / Width / Hedge click with its direction); the server applies it with :mod:`ofo.strategy.leg_edit`
against the
instrument file, re-captures the planned entry of every leg whose contract changed through the one capture path
(:func:`ofo_app.routes.planned_entry.capture_entries`), and answers the new legs plus the engine's outcome of the
INCLUDED legs. The browser computes nothing. A refused edit changes nothing and answers with its catalogue text (422).

Answer states of the price capture: priced (a live LTP, or the mid of bid and ask), unpriced (no live price, or not
connected: the leg comes back with ``planned_entry: null`` and no outcome is computed; ADR-020 Q185 "no fake prices").
"""
from __future__ import annotations

import datetime
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from ofo.charges import ChargeRates
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors import LegValue
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId as ContractKey
from ofo.strategy import leg_edit as edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import Custom, match, protective_keys
from ofo.strategy.model import atm_strike
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from ofo_app.api_models import ApiModel, Identifier, InstrumentId, Money
from ofo_app.errors import ClosedRoute
from ofo_app.live_push import LiveFeed
from ofo_app.routes.outcome import (
    AnswerClock,
    LegIn,
    MarketContext,
    OutcomeRequest,
    OutcomeResponse,
    get_answer_clock,
    get_market_context,
    get_streaming,
    load_charge_rates,
    outcome_response,
)
from ofo_app.routes.planned_entry import capture_entries, get_live_feed

router = APIRouter(route_class=ClosedRoute)

MIN_SHAPE_LEGS = 2  # a shape needs at least 2 legs (REQ-078 AC-2)
CATALOGUE_TTL_SECONDS = 60.0  # AC-10: never "yesterday's list": a stored list is reused for a minute, no longer
_catalogue_cache: dict = {"until": 0.0, "value": None}

Capture = Callable[[MarketContext | None, LiveFeed | None, str, list[str]], Awaitable[tuple]]


async def get_edit_catalogue() -> Catalogue:
    """The stored instrument list as a domain Catalogue (REQ-076 AC-1). Tests override this dependency."""
    if time.monotonic() < _catalogue_cache["until"]:
        return _catalogue_cache["value"]
    from ofo_app import catalogue_store  # noqa: PLC0415 - late, like outcome.stored_contracts
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async with get_sessionmaker()() as session:
        value = await catalogue_store.load_catalogue(await session.connection())
    _catalogue_cache.update(until=time.monotonic() + CATALOGUE_TTL_SECONDS, value=value)
    return value


def get_capture() -> Capture:
    """The planned-entry capture seam (the same helper the leg picker's route uses). Tests override it."""
    return capture_entries


# ---- request ---------------------------------------------------------------------------------------------------------

class EditLegIn(LegIn):
    """A builder leg: the outcome route's leg plus the multiplier's base lots, the tick and the typed mark. The entry
    may be absent (a contract with no live price yet). ``extra="forbid"`` keeps other state out (REQ-076 AC-7)."""

    planned_entry: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")  # type: ignore[assignment]
    captured_at: AwareDatetime | None = None  # type: ignore[assignment]
    base_lots: int = Field(gt=0, le=10000)
    included: StrictBool = True
    typed: StrictBool = False


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control: Literal["step", "multiplier", "include", "price", "reset_prices", "shift", "width", "hedge"]
    direction: Literal[1, -1] | None = None
    index: int | None = Field(default=None, ge=0, lt=20)
    multiplier: int | None = Field(default=None, ge=edit.MULTIPLIER_MIN, le=edit.MULTIPLIER_MAX)
    included: StrictBool | None = None
    price: str | None = Field(default=None, pattern=r"^\d{1,7}(\.\d{1,2})?$")

    @model_validator(mode="after")
    def _control_has_its_fields(self) -> EditIn:
        """Each control needs its own fields and nothing is guessed: a missing one is a plain 422, not a refusal."""
        needs = {"step": ("index", "direction"), "shift": ("direction",), "width": ("direction",),
                 "hedge": ("direction",), "include": ("index", "included"), "price": ("index", "price"),
                 "multiplier": ("multiplier",), "reset_prices": ()}[self.control]
        given = {"index": self.index, "direction": self.direction, "included": self.included, "price": self.price,
                 "multiplier": self.multiplier}
        missing = [name for name in needs if given[name] is None]
        if missing:
            raise ValueError(f"{self.control} needs {missing}")
        return self


class LegEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[EditLegIn] = Field(min_length=1, max_length=20)
    edit: EditIn
    shift_total: int = Field(default=0, ge=-100000, le=100000,
                             description="index points moved by Shift since the last strike edit")
    ux_level: Literal["guided", "standard", "advanced"] = "standard"
    view: Literal["at_expiry", "estimated_now"] = "at_expiry"


# ---- response --------------------------------------------------------------------------------------------------------

class EditLegOut(ApiModel):
    instrument_id: InstrumentId
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    lots: int
    base_lots: int
    quantity: int
    planned_entry: Money | None
    captured_at: datetime.datetime | None
    price_source: Literal["captured", "typed", "none"]
    included: bool
    hedge: bool  # the leg carries the Hedge mark (REQ-076 AC-8)


class ControlsOut(ApiModel):
    shift: bool
    width: bool
    hedge: bool


class LegEditOut(ApiModel):
    legs: list[EditLegOut]
    shape: Identifier | None  # the matched template id, None = Custom Strategy; a label only (REQ-076 AC-9)
    controls: ControlsOut
    shift_total: int
    outcome: OutcomeResponse | None  # None while any included leg has no planned entry


# ---- the edit -----------------------------------------------------------------------------------------------------

def _contract_of(cat: Catalogue, instrument_id: str, underlying: str):
    segment, _, token = instrument_id.partition(":")
    try:
        entry = cat.get(ContractKey(segment, int(token)))
    except ValueError:
        entry = None
    if entry is None or not entry.currently_listed or entry.contract.name != underlying:
        raise LegEditRefused("leg_edit_strike_not_listed", leg=_unknown_ref(underlying, instrument_id))
    return entry.contract


def _unknown_ref(underlying: str, instrument_id: str):
    placeholder = Leg(Action.BUY, Instrument.CE, Decimal(1), datetime.date(2000, 1, 1), 1, Decimal(0))
    return LegValue(1, placeholder, underlying)


def _legs_of(cat: Catalogue, req: LegEditIn) -> list[EditLeg]:
    out = []
    for item in req.legs:
        c = _contract_of(cat, item.instrument_id, req.underlying)
        entry = Decimal(item.planned_entry) if item.planned_entry is not None else Decimal(0)
        leg = Leg(Action(item.action), Instrument(c.instrument_type), None if c.instrument_type == "FUT" else c.strike,
                  c.expiry, item.lots * c.lot_size, entry)
        out.append(EditLeg(leg, item.lots, item.base_lots, item.included, item.typed))
    return out


def _id_of(cat: Catalogue, underlying: str, leg: Leg) -> str:
    for e in cat.all_entries():
        c = e.contract
        if (e.currently_listed and c.name == underlying and c.expiry == leg.expiry
                and c.instrument_type == leg.instrument.value and (leg.strike is None or c.strike == leg.strike)):
            return f"{c.exchange_segment}:{c.exchange_token}"
    raise LegEditRefused("leg_edit_strike_not_listed", leg=_unknown_ref(underlying, "none"))


def _reference_spot(ctx: MarketContext | None, underlying: str, legs: list[EditLeg], gap: Decimal) -> Decimal:
    """The spot the shape is read against: the live index when there is one, else the middle of the option strikes."""
    quote = None if ctx is None else ctx.provider.underlying_quote(underlying)
    if quote is not None and quote.ltp is not None and quote.ltp > 0:
        return quote.ltp
    strikes = [x.leg.strike for x in legs if x.leg.strike is not None]
    mid = (min(strikes) + max(strikes)) / 2
    return (mid / gap).quantize(Decimal(1)) * gap


def shape_and_controls(cat: Catalogue, ctx: MarketContext | None, underlying: str, legs: list[EditLeg]):
    """(template id or None, hedge-marked indexes, which controls apply). Shift: any shape with an option leg; Width
    and Hedge: by the catalogue's shape (REQ-078 AC-2); the Hedge marks are the catalogue's `protective` legs."""
    options = [x for x in legs if x.leg.instrument is not Instrument.FUT]
    if len(legs) < MIN_SHAPE_LEGS or not options:
        return None, frozenset(), ControlsOut(shift=False, width=False, hedge=False)
    gap = edit.strike_step(cat, underlying, legs)
    spot = _reference_spot(ctx, underlying, legs, gap)
    found = match([x.leg for x in legs], spot=spot, strike_gap=gap, templates=load_templates())
    if isinstance(found, Custom):
        return None, frozenset(), ControlsOut(shift=True, width=False, hedge=False)
    marks = protective_keys(found)
    atm = atm_strike(spot, gap)
    ranks = {e: i for i, e in enumerate(sorted({x.leg.expiry for x in legs}))}
    hedged = frozenset(i for i, x in enumerate(legs) if x.leg.strike is not None and (
        x.leg.action, x.leg.instrument, int((x.leg.strike - atm) / gap), ranks[x.leg.expiry]) in marks)
    shorts = {x.leg.instrument for x in legs if x.leg.action is Action.SELL}
    width_ok = bool(shorts & {Instrument.CE, Instrument.PE}) and len(options) == len(legs) and (
        found.template.width_adjustable)
    hedge_ok = bool(hedged) and len(legs) % 2 == 0 and len(legs) <= edit.MAX_HEDGE_LEGS
    return found.template.id, hedged, ControlsOut(shift=True, width=width_ok, hedge=hedge_ok)


def apply_edit(cat: Catalogue, ctx: MarketContext | None, req: LegEditIn, legs: list[EditLeg]):
    """Apply the one edit; ``(legs, indexes whose contract changed, shift_total)``. Raises LegEditRefused."""
    e, name = req.edit, req.underlying
    total = req.shift_total
    if e.control == "include":
        return edit.include_leg(legs, _need_index(e, legs), bool(e.included)), frozenset(), total
    if e.control == "multiplier":
        return edit.apply_multiplier(cat, name, legs, e.multiplier or 1), frozenset(), total
    if e.control == "price":
        price = Decimal(e.price) if e.price is not None else Decimal(0)
        return edit.set_typed_price(cat, name, legs, _need_index(e, legs), price), frozenset(), total
    if e.control == "reset_prices":
        return legs, frozenset(range(len(legs))), total
    direction = e.direction or 1
    if e.control == "step":
        moved = edit.step_strike(cat, name, legs, _need_index(e, legs), direction)
        total = 0  # REQ-078 AC-9: a manual strike edit resets the Shift total
    elif e.control == "shift":
        moved = edit.shift(cat, name, legs, direction)
        total += direction * int(edit.strike_step(cat, name, legs))
    elif e.control == "width":
        _, _, controls = shape_and_controls(cat, ctx, name, legs)
        if not controls.width:
            raise LegEditRefused("leg_edit_width_not_applicable")
        moved = edit.width(cat, name, legs, direction)
    else:
        _, hedged, controls = shape_and_controls(cat, ctx, name, legs)
        if not controls.hedge:
            raise LegEditRefused("leg_edit_hedge_not_applicable")
        moved = edit.hedge(cat, name, legs, hedged, direction)
    return moved.legs, moved.moved, total


def _need_index(e: EditIn, legs: list[EditLeg]) -> int:
    if e.index is None or e.index >= len(legs):  # a forged index: a plain validation error, never a guess
        raise RequestValidationError(
            [{"loc": ("body", "edit", "index"), "msg": "index outside legs", "type": "value_error"}])
    return e.index


@router.post("/api/strategies/leg-edit", response_model=LegEditOut, response_model_exclude_unset=True)
async def leg_edit(req: LegEditIn,  # noqa: PLR0913 - FastAPI dependencies, one per input
                   cat: Annotated[Catalogue, Depends(get_edit_catalogue)],
                   ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                   feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                   capture: Annotated[Capture, Depends(get_capture)],
                   now: Annotated[AnswerClock, Depends(get_answer_clock)],
                   streaming: Annotated[Callable[[str], bool] | None, Depends(get_streaming)],
                   rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> LegEditOut:
    legs = _legs_of(cat, req)
    new_legs, moved, shift_total = apply_edit(cat, ctx, req, legs)
    ids = [_id_of(cat, req.underlying, x.leg) for x in new_legs]
    stamps: dict[int, datetime.datetime | None] = {i: x.captured_at for i, x in enumerate(req.legs)}
    unpriced = {i for i, x in enumerate(req.legs) if x.planned_entry is None}
    recapture = sorted(moved | unpriced) if req.edit.control == "reset_prices" else sorted(moved)
    if recapture:
        valuation, got = await capture(ctx, feed, req.underlying, [ids[i] for i in recapture])
        entries = {}
        for i in recapture:
            price = got.get(ids[i])
            if price is None:
                unpriced.add(i)
                stamps[i] = None
            else:
                entries[i] = price.price
                unpriced.discard(i)
                stamps[i] = valuation
        new_legs = edit.with_entries(new_legs, entries)
    shape, hedged, controls = shape_and_controls(cat, ctx, req.underlying, new_legs)
    out_legs = [{
        "instrument_id": ids[i], "action": x.leg.action.value, "instrument": x.leg.instrument.value,
        "strike": x.leg.strike, "expiry": x.leg.expiry, "lots": x.lots, "base_lots": x.base_lots,
        "quantity": x.leg.quantity, "planned_entry": None if i in unpriced else x.leg.entry_price,
        "captured_at": None if i in unpriced else stamps[i],
        "price_source": "none" if i in unpriced else ("typed" if x.typed else "captured"),
        "included": x.included, "hedge": i in hedged} for i, x in enumerate(new_legs)]
    outcome = None
    shown = [i for i, x in enumerate(new_legs) if x.included]
    if shown and not any(i in unpriced for i in shown):
        outcome_req = OutcomeRequest(
            underlying=req.underlying, ux_level=req.ux_level, view=req.view,
            legs=[{"instrument_id": ids[i], "action": new_legs[i].leg.action.value, "lots": new_legs[i].lots,
                   "planned_entry": f"{new_legs[i].leg.entry_price:f}", "captured_at": stamps[i] or now()}
                  for i in shown])
        outcome = outcome_response(outcome_req, ctx, streaming, now=now, rates=rates)
    return LegEditOut.model_validate({"legs": out_legs, "shape": shape, "controls": controls.model_dump(),
                                      "shift_total": shift_total, "outcome": outcome})
