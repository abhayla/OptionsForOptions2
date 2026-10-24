"""Leg edits of the Strategy Builder: strike step, multiplier, include tick, typed price (REQ-076, W-148).

Adapted from this repo's own branch build/W-126-a1-leg-rows (backend/ofo/strategy/leg_edit.py), REQ-076 parts only: the
Shift / Width / Hedge moves are REQ-078 (row 30) and are not here.

Spec: REQ-076 AC-1 (strikes come from the instrument file, listed and not expired), AC-2 (a stepped leg is a new
contract, so only its planned entry is captured again), AC-4/AC-5 (multiplier; quantity = lots x the file's lot size;
a leg above its freeze limit is blocked, never split, ADR-092), AC-6 (an unticked leg leaves every number);
REQ-077 AC-2 (a typed price is a positive multiple of the file's tick size). ADR-008: this module computes no money; it
moves strikes and the engine prices them. Every function is pure: it returns new legs and never changes its input.

A stepped leg is a new contract: :class:`Moved` names the indexes so the caller re-captures their planned entries
through the one capture path, then calls :func:`with_entries`.

Answer states (run-discipline B4 (d)): strike listed / not listed (refused, names the leg), expired expiry (not
listed), no further listed strike (the stepper's edge), futures leg (no strike), lot size or tick size known / the
file has no such contract (refused, fail closed), freeze limit stored below the quantity (block) / above it (no
block) / not stored (no block here; the order review warns).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from ofo.engine.executable_price import round_to_tick
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors import LegValue, UserFacing, UserFacingError, render
from ofo.instruments.catalogue import Catalogue, ContractKind
from ofo.instruments.freeze_limits import StoredFreeze, largest_allowed_units
from ofo.money import PAISE

MULTIPLIER_MIN, MULTIPLIER_MAX = 1, 50  # REQ-076 AC-4: whole numbers 1 to 50
_TYPED_PRICE = re.compile(r"-?[0-9]{1,30}(\.[0-9]{1,30})?")  # ASCII digits only; the shape check, the rules come after


class LegEditRefused(UserFacing, ValueError):
    """An edit the rules refuse; nothing changed. Carries the catalogue template, its slots and the rendered message."""

    def __init__(self, template: str, **slots: object) -> None:
        self.template = template
        self.message = render(template, **slots)
        super().__init__(template)


@dataclass(frozen=True)
class EditLeg:
    """A leg in the Builder: the engine leg (``entry_price`` is the planned entry, ``quantity`` = lots x lot size) plus
    the user's lots, base lots (what the multiplier multiplies), tick state and whether the price was typed."""

    leg: Leg
    lots: int
    base_lots: int
    included: bool = True
    typed: bool = False


@dataclass(frozen=True)
class Moved:
    legs: list[EditLeg]
    moved: frozenset[int]  # indexes whose contract changed: their planned entries are re-captured


def leg_ref(underlying: str, legs: list[EditLeg], index: int, strike: Decimal | None = None) -> LegValue:
    leg = legs[index].leg
    return LegValue(index + 1, leg if strike is None else replace(leg, strike=strike), underlying)


@dataclass(frozen=True)
class Listing:
    """What the leg picker offers on one day: the instrument file and today's date (both required, so the expiry check
    cannot be skipped)."""

    cat: Catalogue
    today: date

    def strikes(self, underlying: str, expiry: date, instrument: Instrument) -> tuple[Decimal, ...]:
        """The strikes offered for one underlying, expiry and option type, ascending: listed in the instrument file and
        not expired (REQ-035 AC-8)."""
        if expiry < self.today:
            return ()
        return tuple(sorted({e.contract.strike for e in self.cat.all_entries()
                             if e.currently_listed and e.contract.name == underlying and e.contract.expiry == expiry
                             and e.contract.instrument_type == instrument.value}))


def step_strike(listing: Listing, underlying: str, legs: list[EditLeg], index: int, direction: int) -> Moved:
    """REQ-076 AC-1: the next LISTED strike above / below (never strike + a typed constant). A strike that is not
    listed is refused, never rounded; the first / last listed strike has no further step."""
    leg = legs[index].leg
    if leg.strike is None:
        raise LegEditRefused("leg_edit_futures_no_stepper", leg=leg_ref(underlying, legs, index))
    grid = listing.strikes(underlying, leg.expiry, leg.instrument)
    if leg.strike not in grid:
        raise LegEditRefused("leg_edit_strike_not_listed", leg=leg_ref(underlying, legs, index))
    at = grid.index(leg.strike) + direction
    if not 0 <= at < len(grid):
        raise LegEditRefused("leg_edit_no_further_strike", leg=leg_ref(underlying, legs, index))
    out = list(legs)
    out[index] = replace(legs[index], leg=replace(leg, strike=grid[at]), typed=False)
    return Moved(out, frozenset({index}))


def apply_multiplier(cat: Catalogue, underlying: str, legs: list[EditLeg], multiplier: int) -> list[EditLeg]:
    """REQ-076 AC-4/AC-5: lots = base lots x multiplier; quantity = lots x the lot size read from the file."""
    if type(multiplier) is not int or not MULTIPLIER_MIN <= multiplier <= MULTIPLIER_MAX:
        raise ValueError(f"multiplier must be a whole number {MULTIPLIER_MIN}..{MULTIPLIER_MAX}")
    out = []
    for x in legs:
        kind = ContractKind.FUTURE if x.leg.instrument is Instrument.FUT else ContractKind.OPTION
        lots = x.base_lots * multiplier
        quantity = lots * cat.lot_size(underlying, x.leg.expiry, kind)
        out.append(replace(x, lots=lots, leg=replace(x.leg, quantity=quantity)))
    return out


def freeze_blocks(legs: list[EditLeg], limits: Mapping[int, StoredFreeze],
                  symbols: Mapping[int, str]) -> dict[int, UserFacingError]:
    """REQ-076 AC-5 / ADR-092: for each leg (by index) whose units are not below its stored freeze limit, the ADR-081
    block text with the limit and the largest allowed order; a leg is never split. The rule is the order review's
    (:mod:`ofo.execution.freeze`): allowed exactly when units are BELOW the limit. A leg with no stored limit is not
    blocked here (the order review warns)."""
    out: dict[int, UserFacingError] = {}
    for index, stored in limits.items():
        units = legs[index].leg.quantity
        if not units < stored.limit:
            top = largest_allowed_units(stored)
            out[index] = render("freeze_limit_exceeded", contract=symbols[index], units=units,
                                lots=units // stored.lot, max_units=top, max_lots=top // stored.lot,
                                limit=stored.limit)
    return out


def include_leg(legs: list[EditLeg], index: int, included: bool) -> list[EditLeg]:
    """REQ-076 AC-6: the tick; the unticked leg is left out of every number (:func:`included_legs`)."""
    if type(included) is not bool:
        raise ValueError("included must be a bool")
    return [replace(x, included=included) if i == index else x for i, x in enumerate(legs)]


def included_legs(legs: list[EditLeg]) -> list[EditLeg]:
    return [x for x in legs if x.included]


def typed_price_of(text: object) -> Decimal | None:
    """The price as the user typed it: plain digits with an optional sign and fraction, nothing else; a Decimal passes
    through. Anything else (a float, an int, 'abc', '1e2', ' 5', 'NaN') is None, never guessed."""
    if type(text) is Decimal:
        return text if text.is_finite() else None
    if type(text) is str and _TYPED_PRICE.fullmatch(text):
        return Decimal(text)
    return None


def set_typed_price(cat: Catalogue, underlying: str, legs: list[EditLeg], index: int, price: object) -> list[EditLeg]:
    """REQ-077 AC-1/AC-2: a typed planned entry is a positive multiple of the file's tick size for that contract, with
    at most two decimals. ``price`` is the user's text (or a Decimal); every refusal is the one price error and the
    legs stay as they were. The stored price is the 2-decimal value (81.3 becomes 81.30)."""
    leg = legs[index].leg
    kind = ContractKind.FUTURE if leg.instrument is Instrument.FUT else ContractKind.OPTION
    tick = cat.tick_size(underlying, leg.expiry, kind)
    value = typed_price_of(price)
    if (value is None or value <= 0 or value != value.quantize(PAISE)
            or round_to_tick(value, tick, Action.BUY) != value):
        raise LegEditRefused("leg_edit_price_not_tick", leg=leg_ref(underlying, legs, index), tick=tick)
    return [replace(x, leg=replace(x.leg, entry_price=value.quantize(PAISE)), typed=True) if i == index else x
            for i, x in enumerate(legs)]


def with_entries(legs: list[EditLeg], entries: Mapping[int, Decimal]) -> list[EditLeg]:
    """REQ-076 AC-2 / REQ-077 AC-5: the freshly captured planned entries replace the old ones (and any typed mark)."""
    return [replace(x, leg=replace(x.leg, entry_price=entries[i]), typed=False) if i in entries else x
            for i, x in enumerate(legs)]
