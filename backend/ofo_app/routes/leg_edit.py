"""POST /api/strategies/leg-edit (W-148; REQ-076; ADR-008, ADR-068, ADR-092, ADR-150).

Adapted from this repo's own branch build/W-126-a1-leg-rows (backend/ofo_app/routes/leg_edit.py), REQ-076 controls only:
``step``, ``multiplier``, ``include``, ``price``, ``reset_prices``, ``reset_leg`` (REQ-077 AC-5: the same re-capture
for ONE leg) and ``read`` (changes no leg: it answers the current numbers, shape name, Hedge marks and which of
Shift / Width / Hedge apply, REQ-076 AC-8, REQ-078 AC-2), plus the REQ-078 moves ``shift``, ``width`` and ``hedge``
(W-158; ADR-186): the browser sends the control and its direction only, the server computes the strikes from the listed
strikes. Answer states of a move: today's instrument list loaded / not loaded (refused, controls all off, ADR-104);
shape allows the control / does not (refused by the server, whatever the browser sends); landing contract listed and
tradable from the stored eligibility / not listed, expired, not tradable, or no stored status (the whole move is
refused naming the leg, nothing changes).

The browser sends the builder's legs plus ONE edit; the server applies it with :mod:`ofo.strategy.leg_edit` against the
instrument file, re-captures the planned entry of every leg whose contract changed through the one capture path
(:func:`ofo_app.routes.planned_entry.capture_entries`), and answers the new legs plus the engine's outcome of the
INCLUDED legs (summary, payoff, table, margin and Greeks of the remaining legs). The browser computes nothing. A
refused edit changes nothing and answers with its catalogue text (422).

The tick (``included``) belongs to this request and reply only: it is never part of the saved definition or the
execution plan (REQ-076 AC-7); the saved form and the Execute request refuse the key.

Answer states of the price capture: priced (a live LTP, or the mid of bid and ask), unpriced (no live price, or not
connected: the leg comes back with ``planned_entry: null`` and no outcome is computed; ADR-020 Q185 "no fake prices").
Answer states of the freeze limit: stored and the quantity not below it (the leg's ``block`` is the ADR-081 text),
stored and above it (no block), not stored (no block; the order review warns).
"""
from __future__ import annotations

import datetime
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from ofo.charges import ChargeRates
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors import LegValue
from ofo.errors.explanations import render_explanation
from ofo.instruments.catalogue import Catalogue, ContractKind
from ofo.instruments.freeze_limits import StoredFreeze
from ofo.instruments.models import InstrumentId as ContractKey
from ofo.money import PAISE
from ofo.outcome.service import Margin
from ofo.strategy import leg_edit as edit
from ofo.strategy import shape_families, stored_form
from ofo.strategy.leg_edit import EditLeg, LegEditRefused, render_reason
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import Custom, match, protective_keys
from ofo.strategy.model import atm_strike
from ofo.timeutil import days_to_expiry
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from ofo_app.api_models import ApiModel, CatalogueText, Identifier, InstrumentId, Money, echo_seq
from ofo_app.errors import ClosedRoute
from ofo_app.live_push import LiveFeed
from ofo_app.outcome_margin import OutcomeMargin
from ofo_app.routes.outcome import (
    AnswerClock,
    LegIn,
    MarketContext,
    OutcomeRequest,
    OutcomeResponse,
    RequestSeq,
    get_answer_clock,
    get_margin_source,
    get_market_context,
    get_streaming,
    load_charge_rates,
    margin_for_request,
    outcome_response,
)
from ofo_app.routes.planned_entry import Reason, capture_entries, get_live_feed
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

MIN_SHAPE_LEGS = 2  # a shape needs at least 2 legs
MAX_HEDGE_LEGS = edit.MAX_HEDGE_LEGS
MOVES = ("shift", "width", "hedge")  # REQ-078: the controls that move strikes by one strike step per click
SHIFT_TOTAL_BOUND = 1_000_000  # index points; far beyond any strike
CATALOGUE_TTL_SECONDS = 60.0  # AC-10: never "yesterday's list": a stored list is reused for a minute, no longer
_catalogue_cache: dict = {"until": 0.0, "value": None}

Capture = Callable[[MarketContext | None, LiveFeed | None, str, list[str]], Awaitable[tuple]]
ContractIds = Callable[[list[str]], Awaitable[dict[str, int]]]
Tradable = Callable[[list[int]], Awaitable[list[bool]]]


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


async def get_edit_today() -> datetime.date:
    """Today's date on the database clock, the one every expiry judgement uses (the leg picker's). Tests override it."""
    from ofo_app import catalogue_picker  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async with get_sessionmaker()() as session:
        return await catalogue_picker.database_today(await session.connection())


async def get_list_current() -> bool:
    """AC-10 (ADR-104): whether today's instrument list is loaded (the latest load is at or after this session's publish
    time, database clock). False = Shift / Width / Hedge are off, never computed from yesterday's list. Tests
    override it."""
    from ofo_app import catalogue_picker  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async with get_sessionmaker()() as session:
        conn = await session.connection()
        return await catalogue_picker.list_is_current(conn, await catalogue_picker.database_today(conn))


def get_move_eligibility() -> Tradable:
    """AC-6 'not eligible': for each stored contract id, whether Zerodha's stored data lets it be traded today (the
    add-time check the save uses, ADR-104). No stored status is False: fail closed. Tests override it."""
    async def tradable(contract_ids: list[int]) -> list[bool]:
        from ofo_app import catalogue_picker  # noqa: PLC0415
        from ofo_app import eligibility_from_zerodha as elig  # noqa: PLC0415
        from ofo_app.db import get_sessionmaker  # noqa: PLC0415

        async with get_sessionmaker()() as session:
            conn = await session.connection()
            statuses = await elig.leg_statuses(conn, contract_ids, await catalogue_picker.database_today(conn))
        return [status is not None and status.tradable for status in statuses]
    return tradable


async def get_freeze_limits() -> dict[ContractKey, tuple[int, datetime.date]]:
    """The stored exchange freeze limit in force for every stored contract, as (limit, file date). Tests override it."""
    from ofo_app import freeze_read  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async with get_sessionmaker()() as session:
        stored = await freeze_read.limits_in_force(await session.connection())
    return {key: (v.freeze_limit, v.file_date) for key, v in stored.items()}


def get_contract_ids() -> ContractIds:
    """The stored internal contract id of each live instrument id (what Save Draft links a leg to, ADR-057). A contract
    with no live stored row is absent from the answer; its leg is then not savable. Tests override it."""
    async def lookup(instrument_ids: list[str]) -> dict[str, int]:
        from ofo_app import catalogue_store  # noqa: PLC0415
        from ofo_app.db import get_sessionmaker  # noqa: PLC0415

        found: dict[str, int] = {}
        async with get_sessionmaker()() as session:
            conn = await session.connection()
            for iid in instrument_ids:
                segment, _, token = iid.partition(":")
                stored = await catalogue_store.live_contract_id(conn, ContractKey(segment, int(token)))
                if stored is not None:
                    found[iid] = stored
        return found
    return lookup


def get_capture() -> Capture:
    """The planned-entry capture seam (the same helper the leg picker's route uses). Tests override it."""
    return capture_entries


# ---- request ---------------------------------------------------------------------------------------------------------

class EditLegIn(LegIn):
    """A builder leg: the outcome route's leg plus the multiplier's base lots, the tick and the typed mark. The entry
    may be absent (a contract with no live price yet). ``extra="forbid"`` keeps other state out."""

    planned_entry: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")  # type: ignore[assignment]
    captured_at: AwareDatetime | None = None  # type: ignore[assignment]
    base_lots: StrictInt = Field(gt=0, le=10000)  # strict like the shared leg's lots: true, 1.0, "2" refused
    included: StrictBool = True
    typed: StrictBool = False


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    control: Literal["step", "multiplier", "include", "price", "reset_prices", "reset_leg", "read",
                     "shift", "width", "hedge"]
    direction: Literal[1, -1] | None = None  # strict by _strict_direction: True and 1.0 are not 1
    index: StrictInt | None = Field(default=None, ge=0, lt=20)
    multiplier: StrictInt | None = Field(default=None, ge=edit.MULTIPLIER_MIN, le=edit.MULTIPLIER_MAX)  # '3', 2.5: 422
    included: StrictBool | None = None
    price: str | None = Field(default=None, max_length=64)  # the user's text: edit.set_typed_price is the one judge

    @field_validator("direction", mode="before")
    @classmethod
    def _strict_direction(cls, value: object) -> object:
        """A Literal[1, -1] alone accepts True and 1.0 (equal to 1); only a JSON integer is a direction."""
        if value is not None and type(value) is not int:
            raise ValueError("direction is the integer 1 or -1")
        return value

    @model_validator(mode="after")
    def _control_has_its_fields(self) -> EditIn:
        """Each control needs its own fields and nothing is guessed: a missing one is a plain 422, not a refusal."""
        needs = {"step": ("index", "direction"), "include": ("index", "included"), "price": ("index", "price"),
                 "multiplier": ("multiplier",), "reset_prices": (), "reset_leg": ("index",), "read": (),
                 "shift": ("direction",), "width": ("direction",), "hedge": ("direction",)}[self.control]
        given = {"index": self.index, "direction": self.direction, "included": self.included, "price": self.price,
                 "multiplier": self.multiplier}
        missing = [name for name in needs if given[name] is None]
        if missing:
            raise ValueError(f"{self.control} needs {missing}")
        return self


class LegEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    underlying: Underlying
    legs: list[EditLegIn] = Field(min_length=1, max_length=20)
    edit: EditIn
    shift_total: StrictInt | None = Field(default=None, ge=-SHIFT_TOTAL_BOUND, le=SHIFT_TOTAL_BOUND)  # AC-3/AC-9
    view: Literal["at_expiry", "estimated_now"] = "at_expiry"
    seq: RequestSeq | None = None  # REQ-119 AC-1: echoed unchanged as the reply's seq

    @model_validator(mode="after")
    def _index_is_inside_the_legs(self) -> LegEditIn:
        """A forged index is a plain 422 through the API's one error boundary (ofo_app/errors.py), never a guess."""
        if self.edit.index is not None and self.edit.index >= len(self.legs):
            raise ValueError("index outside legs")
        return self


# ---- response --------------------------------------------------------------------------------------------------------

class EditLegOut(ApiModel):
    instrument_id: InstrumentId
    contract_id: int | None  # the stored internal id of THIS contract (a stepped leg's new one); None = not savable
    lot_size: int
    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"]
    strike: Money | None
    expiry: datetime.date
    days_to_expiry: int | None  # REQ-135 AC-2: calendar days left from today (IST, the database clock); 0 on expiry day
    lots: int
    base_lots: int
    quantity: int
    planned_entry: Money | None
    captured_at: datetime.datetime | None
    price_source: Literal["captured", "typed", "none"]
    replaced_typed: bool  # AC-8: the leg had a typed price and moved, so the captured price replaced it
    included: bool
    hedge: bool  # the leg carries the Hedge mark (REQ-076 AC-8)
    price_reason: Reason | None  # why the leg is unpriced after this edit (the planned-entry route's codes); else None
    block: CatalogueText | None  # the ADR-092 reason when the quantity is not below the freeze limit (never split)


class ControlsOut(ApiModel):
    """REQ-078 AC-2/AC-10: which of the three move controls work on these legs right now."""

    shift: bool
    width: bool
    hedge: bool


class ControlReasonsOut(ApiModel):
    """Why a control is off (the catalogue text), else None."""

    shift: CatalogueText | None
    width: CatalogueText | None
    hedge: CatalogueText | None


class LegEditOut(ApiModel):
    legs: list[EditLegOut]
    controls: ControlsOut
    control_reasons: ControlReasonsOut
    shift_total: int | None  # index points moved by Shift clicks since the last reset; None = '-' (AC-3, AC-9)
    shape: Identifier | None  # the matched template id, None = Custom Strategy; a label only (REQ-076 AC-9)
    shape_name: CatalogueText | None  # the matched template's name from the reviewed catalogue; None = Custom Strategy
    outcome: OutcomeResponse | None  # None while any included leg has no planned entry, or no leg is included
    seq: int | None = None  # REQ-119 AC-1: the request's seq, unchanged; absent when the request sent none


# ---- the edit -----------------------------------------------------------------------------------------------------

def _contract_of(cat: Catalogue, item: EditLegIn, underlying: str, number: int, today: datetime.date):
    """The stored contract of a request leg. An expired contract is named as the contract it really is; an id the
    instrument file does not hold (or another underlying's) is refused by the leg's NUMBER, never by a made-up
    contract."""
    segment, _, token = item.instrument_id.partition(":")
    try:
        entry = cat.get(ContractKey(segment, int(token)))
    except ValueError:
        entry = None
    if entry is None or entry.contract.name != underlying:
        raise LegEditRefused("leg_edit_unknown_contract", number=number)
    c = entry.contract
    if c.expiry < today:  # a delisted contract is named by _entry_of, the one listedness check
        strike = None if c.instrument_type == "FUT" else c.strike
        shown = Leg(Action(item.action), Instrument(c.instrument_type), strike, c.expiry,
                    item.lots * c.lot_size, Decimal(0))
        raise LegEditRefused("leg_edit_strike_not_listed", leg=LegValue(number, shown, underlying))
    return c


def _legs_of(cat: Catalogue, req: LegEditIn, today: datetime.date) -> list[EditLeg]:
    out = []
    for number, item in enumerate(req.legs, start=1):
        c = _contract_of(cat, item, req.underlying, number, today)
        entry = Decimal(item.planned_entry) if item.planned_entry is not None else Decimal(0)
        leg = Leg(Action(item.action), Instrument(c.instrument_type), None if c.instrument_type == "FUT" else c.strike,
                  c.expiry, item.lots * c.lot_size, entry)
        if item.planned_entry is not None and not stored_form.is_entry_price_text(item.planned_entry):
            # the stored form's own rule (a zero the save would refuse is refused here, the same price error)
            kind = ContractKind.FUTURE if c.instrument_type == "FUT" else ContractKind.OPTION
            raise LegEditRefused("leg_edit_price_not_tick", leg=LegValue(number, leg, req.underlying),
                                 tick=cat.tick_size(req.underlying, c.expiry, kind))
        out.append(EditLeg(leg, item.lots, item.base_lots, item.included, item.typed))
    return out


def _entry_of(cat: Catalogue, underlying: str, legs: list[EditLeg], index: int):
    """The listed catalogue entry of leg ``index`` (the contract the leg now names)."""
    leg = legs[index].leg
    for e in cat.all_entries():
        c = e.contract
        if (e.currently_listed and c.name == underlying and c.expiry == leg.expiry
                and c.instrument_type == leg.instrument.value and (leg.strike is None or c.strike == leg.strike)):
            return e
    raise LegEditRefused("leg_edit_strike_not_listed", leg=edit.leg_ref(underlying, legs, index))


def _live_spot(ctx: MarketContext | None, underlying: str) -> Decimal | None:
    """The live index level, or None (no feed, no price): the shape is read from the strikes, no spot invented."""
    quote = None if ctx is None else ctx.provider.underlying_quote(underlying)
    return quote.ltp if quote is not None and quote.ltp is not None and quote.ltp > 0 else None


def _reference_spot(ctx: MarketContext | None, underlying: str, legs: list[EditLeg], gap: Decimal) -> Decimal:
    """The spot the shape is read against: the live index when there is one, else the middle of the option strikes."""
    live = _live_spot(ctx, underlying)
    if live is not None:
        return live
    strikes = [x.leg.strike for x in legs if x.leg.strike is not None]
    mid = (min(strikes) + max(strikes)) / 2
    return (mid / gap).quantize(Decimal(1)) * gap


def shape_and_marks(cat: Catalogue, ctx: MarketContext | None, underlying: str, legs: list[EditLeg]):
    """(matched template or None, hedge-marked indexes). The Hedge marks are the matched template's ``protective`` legs
    (REQ-076 AC-8); a Custom Strategy has none, and nothing here changes a leg (AC-9)."""
    options = [x for x in legs if x.leg.instrument is not Instrument.FUT]
    if len(legs) < MIN_SHAPE_LEGS or not options:
        return None, frozenset()
    gap = min(cat.strike_gap(underlying, expiry) for expiry in {x.leg.expiry for x in options})
    spot = _reference_spot(ctx, underlying, legs, gap)
    templates = load_templates()
    found = match([x.leg for x in legs], spot=spot, strike_gap=gap, templates=templates)
    if isinstance(found, Custom) and _live_spot(ctx, underlying) is None:
        # no live index: the middle of the strikes is only a guess, so the neighbouring ATM strikes are tried too
        for nearby in (spot - gap, spot + gap):
            if not isinstance(again := match([x.leg for x in legs], spot=nearby, strike_gap=gap,
                                              templates=templates), Custom):
                found, spot = again, nearby
                break
    if isinstance(found, Custom):
        return None, frozenset()
    marks = protective_keys(found)
    atm = atm_strike(spot, gap)
    ranks = {e: i for i, e in enumerate(sorted({x.leg.expiry for x in legs}))}
    hedged = frozenset(i for i, x in enumerate(legs) if x.leg.strike is not None and (
        x.leg.action, x.leg.instrument, int((x.leg.strike - atm) / gap), ranks[x.leg.expiry]) in marks)
    return found.template, hedged


def _need_index(e: EditIn, legs: list[EditLeg]) -> int:
    if e.index is None or not 0 <= e.index < len(legs):  # unreachable: LegEditIn refuses a forged index first
        raise RuntimeError(f"leg edit '{e.control}' reached the edit with index {e.index} for {len(legs)} legs: "
                           "the request check (LegEditIn) should have refused it")
    return e.index


def _controls(template, hedged: frozenset[int], legs: list[EditLeg], current: bool):
    """REQ-078 AC-2/AC-10: ``{control: template id of the reason it is off, or None}`` for shift, width and hedge.
    Off when today's list is not loaded, when there are fewer than 2 legs or no option leg, or when the matched
    shape does not allow the control (Custom Strategy: Shift only). The same answer gates the moves in
    :func:`apply_edit`, so the browser's word is never trusted."""
    off: dict[str, str | None] = {"shift": None, "width": None, "hedge": None}
    if not current:
        off = dict.fromkeys(off, "leg_edit_list_not_loaded_today")
    elif all(x.leg.instrument is Instrument.FUT for x in legs):
        off = dict.fromkeys(off, "leg_edit_shift_needs_option_leg")
    elif len(legs) < MIN_SHAPE_LEGS:  # each control says its own reason (REQ-078 AC-2)
        off = {"shift": "leg_edit_shift_needs_option_leg", "width": "leg_edit_width_needs_two_legs",
               "hedge": "leg_edit_hedge_needs_two_legs"}
    else:
        if template is None or not template.width_adjustable:
            off["width"] = "leg_edit_width_not_applicable"
        if template is None or len(legs) % 2 or len(legs) > MAX_HEDGE_LEGS:
            off["hedge"] = "leg_edit_hedge_not_applicable"
        elif not hedged:
            # a shape of a Hedge family that has no Hedge-marked leg (Long Iron Condor / Butterfly): the shapes sentence
            # would name its own family as unsupported, so the reason states the condition only (ADR-003)
            in_family = template.family_plural in shape_families.control_families(shape_families.HEDGE)
            off["hedge"] = "leg_edit_hedge_no_hedge_legs" if in_family else "leg_edit_hedge_not_applicable"
    return off


Gate = tuple[dict[str, str | None], frozenset[int]]  # (the reason each control is off, the Hedge-marked indexes)


def _apply_move(cat: Catalogue, req: LegEditIn, legs: list[EditLeg], today: datetime.date, gate: Gate | None,
                spot: Decimal | None):
    """REQ-078: shift / width / hedge by one strike step, refused with the reason when its control is off."""
    e = req.edit
    if gate is None:  # unreachable: the route always passes it for a move
        raise RuntimeError(f"leg edit '{e.control}' reached apply_edit without its control check")
    off, hedged = gate
    if off[e.control] is not None:
        raise LegEditRefused(off[e.control])
    listing, direction = edit.Listing(cat, today), e.direction or 1
    if e.control == "shift":
        moved = edit.shift(listing, req.underlying, legs, direction)
    elif e.control == "width":
        moved = edit.width(listing, req.underlying, legs, direction, spot)
    else:
        moved = edit.hedge(listing, req.underlying, legs, hedged, direction)
    return moved.legs, moved.moved


def apply_edit(cat: Catalogue, req: LegEditIn, legs: list[EditLeg], today: datetime.date, gate: Gate | None = None,
               spot: Decimal | None = None):
    """Apply the one edit; ``(legs, indexes whose contract changed)``. Raises LegEditRefused. A move (shift / width /
    hedge) needs ``gate`` (:func:`_controls` and the Hedge marks, computed by the server from the legs as sent);
    ``spot`` is the live index level for Width's last-step case (None: no price, ADR-186 (5))."""
    e, name = req.edit, req.underlying
    if e.control in MOVES:
        return _apply_move(cat, req, legs, today, gate, spot)
    if e.control == "include":
        return edit.include_leg(legs, _need_index(e, legs), bool(e.included)), frozenset()
    if e.control == "multiplier":
        return edit.apply_multiplier(cat, name, legs, e.multiplier or 1), frozenset()
    if e.control == "price":
        return edit.set_typed_price(cat, name, legs, _need_index(e, legs), e.price), frozenset()
    if e.control in ("reset_prices", "reset_leg", "read"):  # REQ-077 AC-5: every leg, or ONE leg; read: none
        return legs, _recaptured(e, legs)
    moved = edit.step_strike(edit.Listing(cat, today), name, legs, _need_index(e, legs), e.direction or 1)
    return moved.legs, moved.moved


def _move_gate(cat: Catalogue, req: LegEditIn, ctx: MarketContext | None, legs: list[EditLeg],
               list_current: bool) -> Gate | None:
    """AC-2/AC-10: for a move, the server decides from the legs as sent whether the control applies; else None."""
    if req.edit.control not in MOVES:
        return None
    template, hedged = shape_and_marks(cat, ctx, req.underlying, legs)
    return _controls(template, hedged, legs, list_current), hedged


async def _check_landing(tradable: Tradable, underlying: str, new_legs: list[EditLeg], moved: frozenset[int],
                         stored_of: dict[int, int]) -> None:
    """AC-6 'not eligible': the whole move is refused if any landing contract is not tradable from the stored data. A
    contract with no stored row has no eligibility either: refused (fail closed)."""
    order = [i for i in sorted(moved) if i in stored_of]
    verdicts = dict(zip(order, await tradable([stored_of[i] for i in order]), strict=True))
    for i in sorted(moved):
        if not verdicts.get(i, False):
            raise LegEditRefused("leg_edit_landing_not_tradable", leg=edit.leg_ref(underlying, new_legs, i))


def _next_shift_total(req: LegEditIn, cat: Catalogue, today: datetime.date, legs: list[EditLeg]) -> int | None:
    """AC-3/AC-9 (ADR-186 (2)): only Shift adds to the total; a manual step, Width or Hedge resets it ('-')."""
    control = req.edit.control
    if control == "shift":
        step = int(edit.shift_step(edit.Listing(cat, today), req.underlying, legs))
        return (req.shift_total or 0) + (req.edit.direction or 1) * step
    return None if control in ("step", "width", "hedge") else req.shift_total


def _recaptured(e: EditIn, legs: list[EditLeg]) -> frozenset[int]:
    """The legs whose planned entry is captured again without a move: all (reset_prices), one (reset_leg), none."""
    if e.control == "reset_prices":
        return frozenset(range(len(legs)))
    return frozenset({_need_index(e, legs)}) if e.control == "reset_leg" else frozenset()


def _freeze_blocks(cat: Catalogue, underlying: str, legs: list[EditLeg],
                   stored: dict[ContractKey, tuple[int, datetime.date]]):
    """The ADR-092 block reason per leg index: the stored limit in force for the leg's contract, the lot size from the
    same contract's row (never typed), the symbol Zerodha trades it under."""
    limits, symbols = {}, {}
    for i in range(len(legs)):
        entry = _entry_of(cat, underlying, legs, i)
        if entry.id in stored:
            limit, file_date = stored[entry.id]
            limits[i] = StoredFreeze(limit, entry.contract.lot_size, file_date)
            (ref,) = entry.broker_refs.values()  # the one broker row (the store refuses any other count); no name here
            symbols[i] = ref.broker_symbol
    return edit.freeze_blocks(legs, limits, symbols)


@router.post("/api/strategies/leg-edit", response_model=LegEditOut, response_model_exclude_unset=True)
async def leg_edit(req: LegEditIn,  # noqa: PLR0913 - FastAPI dependencies, one per input
                   cat: Annotated[Catalogue, Depends(get_edit_catalogue)],
                   today: Annotated[datetime.date, Depends(get_edit_today)],
                   limits: Annotated[dict[ContractKey, tuple[int, datetime.date]], Depends(get_freeze_limits)],
                   ctx: Annotated[MarketContext | None, Depends(get_market_context)],
                   feed: Annotated[LiveFeed | None, Depends(get_live_feed)],
                   capture: Annotated[Capture, Depends(get_capture)],
                   contract_ids: Annotated[ContractIds, Depends(get_contract_ids)],
                   list_current: Annotated[bool, Depends(get_list_current)],
                   tradable: Annotated[Tradable, Depends(get_move_eligibility)],
                   now: Annotated[AnswerClock, Depends(get_answer_clock)],
                   streaming: Annotated[Callable[[str], bool] | None, Depends(get_streaming)],
                   rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
                   margin_source: Annotated[OutcomeMargin | None, Depends(get_margin_source)]) -> LegEditOut:
    legs = _legs_of(cat, req, today)
    new_legs, moved = apply_edit(cat, req, legs, today, _move_gate(cat, req, ctx, legs, list_current),
                                 _live_spot(ctx, req.underlying))
    entries_of = [_entry_of(cat, req.underlying, new_legs, i) for i in range(len(new_legs))]
    ids = [f"{e.contract.exchange_segment}:{e.contract.exchange_token}" for e in entries_of]
    stored_ids = await contract_ids(ids)
    if req.edit.control in MOVES:
        stored_of = {i: stored_ids[ids[i]] for i in moved if ids[i] in stored_ids}
        await _check_landing(tradable, req.underlying, new_legs, moved, stored_of)
    shift_total = _next_shift_total(req, cat, today, legs)
    stamps: dict[int, datetime.datetime | None] = {i: x.captured_at for i, x in enumerate(req.legs)}
    unpriced = {i for i, x in enumerate(req.legs) if x.planned_entry is None}
    reasons: dict[int, Reason] = {}
    recapture = sorted(moved | unpriced) if req.edit.control == "reset_prices" else sorted(moved)
    if req.edit.control == "price" and req.edit.index is not None:  # REQ-077 AC-4: a typed price carries its own time
        stamps[req.edit.index] = now()
        unpriced.discard(req.edit.index)
    if recapture:
        valuation, got = await capture(ctx, feed, req.underlying, [ids[i] for i in recapture])
        entries = {}
        for i in recapture:
            price = got.get(ids[i])
            if price is None:  # AC-2: no live price -> the stepped leg is unpriced, never the old price
                unpriced.add(i)
                reasons[i] = "not_connected" if valuation is None else "no_live_price"  # AC-5: the screen says why
                stamps[i] = None
            else:
                entries[i] = price.price
                unpriced.discard(i)
                stamps[i] = valuation
        new_legs = edit.with_entries(new_legs, entries)
    template, hedged = shape_and_marks(cat, ctx, req.underlying, new_legs)
    blocks = _freeze_blocks(cat, req.underlying, new_legs, limits)
    off_now = _controls(template, hedged, new_legs, list_current)
    out_legs = [{
        "instrument_id": ids[i], "contract_id": stored_ids.get(ids[i]), "lot_size": entries_of[i].contract.lot_size,
        "action": x.leg.action.value, "instrument": x.leg.instrument.value,
        "strike": x.leg.strike, "expiry": x.leg.expiry,
        "days_to_expiry": days_to_expiry(x.leg.expiry, today), "lots": x.lots, "base_lots": x.base_lots,
        "quantity": x.leg.quantity, "planned_entry": None if i in unpriced else x.leg.entry_price.quantize(PAISE),
        "captured_at": None if i in unpriced else stamps[i],
        "price_source": "none" if i in unpriced else ("typed" if x.typed else "captured"),
        "replaced_typed": legs[i].typed and i in moved,
        "included": x.included, "hedge": i in hedged, "price_reason": reasons.get(i) if i in unpriced else None,
        "block": blocks.get(i)} for i, x in enumerate(new_legs)]
    outcome = None
    shown = [i for i, x in enumerate(new_legs) if x.included]
    if shown and not any(i in unpriced for i in shown):
        outcome_req = OutcomeRequest(
            underlying=req.underlying, view=req.view,
            legs=[{"instrument_id": ids[i], "action": new_legs[i].leg.action.value, "lots": new_legs[i].lots,
                   "planned_entry": f"{new_legs[i].leg.entry_price:f}", "captured_at": stamps[i] or now()}
                  for i in shown])
        margin: Margin = await margin_for_request(outcome_req, ctx, margin_source)
        outcome = outcome_response(outcome_req, ctx, streaming, now=now, rates=rates, margin=margin)
    name = None if template is None else render_explanation("catalogue_template_name", text=template.name)
    reply = {"legs": out_legs, "controls": {name: why is None for name, why in off_now.items()},
             "control_reasons": {name: None if why is None else render_reason(why) for name, why in off_now.items()},
             "shift_total": shift_total, "shape": None if template is None else template.id, "shape_name": name,
             "outcome": outcome}
    return echo_seq(LegEditOut.model_validate(reply), req.seq)  # REQ-119 AC-1
