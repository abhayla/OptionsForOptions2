"""Leg edits of the Strategy Builder: strike step, multiplier, include tick, typed price, Shift / Width / Hedge (W-126).

Spec: REQ-076 AC-1 (strikes come from the instrument file), AC-4/AC-5 (multiplier; quantity = lots x the file's lot size),
AC-6 (an unticked leg leaves every number); REQ-077 AC-2 (a typed price is a positive multiple of the file's tick size);
REQ-078 AC-3..AC-8 (Shift, Width, Hedge by one strike step; the whole move is refused when any leg would land on an
unlisted strike; sides, lots, expiry and type never change). ADR-008: this module computes no money; it moves strikes and
the engine prices them. Every function is pure: it returns new legs and never changes its input.

A moved leg is a new contract: :class:`Moved` names the indexes so the caller re-captures their planned entries
(REQ-078 AC-8) through the one capture path, then calls :func:`with_entries`.

Answer states (run-discipline B4 (d)): strike listed / not listed (refused, names the leg), no further listed strike (the
stepper's edge), futures leg (no strike), tick size known / the file has no such contract (refused, fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Mapping

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED  # noqa: F401 - re-exported for the callers that test "Unlimited"
from ofo.errors import LegValue, UserFacing, render
from ofo.instruments.catalogue import Catalogue, ContractKind

MULTIPLIER_MIN, MULTIPLIER_MAX = 1, 50  # REQ-076 AC-4: whole numbers 1 to 50
OPTIONS = (Instrument.CE, Instrument.PE)
MAX_HEDGE_LEGS = 4  # REQ-078 AC-5: an even number of legs, at most 4


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


def _ref(underlying: str, legs: list[EditLeg], index: int, strike: Decimal | None = None) -> LegValue:
    leg = legs[index].leg
    return LegValue(index + 1, leg if strike is None else replace(leg, strike=strike), underlying)


def listed_strikes(cat: Catalogue, underlying: str, expiry, instrument: Instrument) -> tuple[Decimal, ...]:
    """The strikes the instrument file lists today for one underlying, expiry and option type, ascending."""
    return tuple(sorted({e.contract.strike for e in cat.all_entries()
                         if e.currently_listed and e.contract.name == underlying and e.contract.expiry == expiry
                         and e.contract.instrument_type == instrument.value}))


def _land(cat: Catalogue, underlying: str, legs: list[EditLeg], targets: Mapping[int, Decimal]) -> Moved:
    """Move each leg in ``targets`` to its new strike; if any lands on an unlisted strike the whole move is refused."""
    out = list(legs)
    for index, strike in sorted(targets.items()):
        leg = legs[index].leg
        if strike not in listed_strikes(cat, underlying, leg.expiry, leg.instrument):
            raise LegEditRefused("leg_edit_strike_not_listed", leg=_ref(underlying, legs, index, strike))
        out[index] = replace(legs[index], leg=replace(leg, strike=strike), typed=False)
    return Moved(out, frozenset(targets))


def _gap(cat: Catalogue, underlying: str, legs: list[EditLeg]) -> Decimal:
    """The strike step: the file's strike gap for the legs' expiry (the smallest gap across their expiries)."""
    expiries = {x.leg.expiry for x in legs if x.leg.instrument in OPTIONS}
    return min(cat.strike_gap(underlying, expiry) for expiry in expiries)


def step_strike(cat: Catalogue, underlying: str, legs: list[EditLeg], index: int, direction: int) -> Moved:
    """REQ-076 AC-1: the next LISTED strike above / below (never strike + a typed constant)."""
    leg = legs[index].leg
    if leg.strike is None:
        raise LegEditRefused("leg_edit_futures_no_stepper", leg=_ref(underlying, legs, index))
    grid = listed_strikes(cat, underlying, leg.expiry, leg.instrument)
    if leg.strike not in grid:
        raise LegEditRefused("leg_edit_strike_not_listed", leg=_ref(underlying, legs, index))
    at = grid.index(leg.strike) + direction
    if not 0 <= at < len(grid):
        raise LegEditRefused("leg_edit_no_further_strike", leg=_ref(underlying, legs, index))
    return _land(cat, underlying, legs, {index: grid[at]})


def shift(cat: Catalogue, underlying: str, legs: list[EditLeg], direction: int) -> Moved:
    """REQ-078 AC-3: every option leg by one strike step; futures legs stay."""
    options = [i for i, x in enumerate(legs) if x.leg.instrument in OPTIONS]
    if not options:
        raise LegEditRefused("leg_edit_needs_option_leg")
    step = direction * _gap(cat, underlying, legs)
    return _land(cat, underlying, legs, {i: legs[i].leg.strike + step for i in options})


def width(cat: Catalogue, underlying: str, legs: list[EditLeg], direction: int) -> Moved:
    """REQ-078 AC-4: every call leg one step up and every put leg one step down (reversed for -1); the distance between
    the highest short put and the lowest short call never goes below 0."""
    puts = [x.leg.strike for x in legs if x.leg.instrument is Instrument.PE and x.leg.action is Action.SELL]
    calls = [x.leg.strike for x in legs if x.leg.instrument is Instrument.CE and x.leg.action is Action.SELL]
    if not puts and not calls:
        raise LegEditRefused("leg_edit_width_not_applicable")
    step = _gap(cat, underlying, legs)
    if direction < 0 and puts and calls and min(calls) - max(puts) < 2 * step:
        raise LegEditRefused("leg_edit_width_below_zero")
    targets = {i: x.leg.strike + (direction * step if x.leg.instrument is Instrument.CE else -direction * step)
               for i, x in enumerate(legs) if x.leg.instrument in OPTIONS}
    return _land(cat, underlying, legs, targets)


def hedge(cat: Catalogue, underlying: str, legs: list[EditLeg], protective: frozenset[int], direction: int) -> Moved:
    """REQ-078 AC-5: only the legs marked Hedge move, one step away from (+1) or towards (-1) their short leg; the
    distance is never below one step; an even number of legs, at most 4."""
    if not protective or len(legs) % 2 or len(legs) > MAX_HEDGE_LEGS:
        raise LegEditRefused("leg_edit_hedge_not_applicable")
    step = _gap(cat, underlying, legs)
    targets: dict[int, Decimal] = {}
    for i in sorted(protective):
        leg = legs[i].leg
        away = step if leg.instrument is Instrument.CE else -step  # a call hedge sits above its short, a put hedge below
        new = leg.strike + direction * away
        primaries = [x.leg.strike for j, x in enumerate(legs) if j not in protective and x.leg.instrument is leg.instrument]
        if primaries and (new - min(primaries, key=lambda s: abs(s - leg.strike))) * (1 if away > 0 else -1) < step:
            raise LegEditRefused("leg_edit_hedge_below_minimum", leg=_ref(underlying, legs, i, new))
        targets[i] = new
    return _land(cat, underlying, legs, targets)


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


def include_leg(legs: list[EditLeg], index: int, included: bool) -> list[EditLeg]:
    """REQ-076 AC-6: the tick; the unticked leg is left out of every number (:func:`included_legs`)."""
    if type(included) is not bool:
        raise ValueError("included must be a bool")
    return [replace(x, included=included) if i == index else x for i, x in enumerate(legs)]


def included_legs(legs: list[EditLeg]) -> list[EditLeg]:
    return [x for x in legs if x.included]


def set_typed_price(cat: Catalogue, underlying: str, legs: list[EditLeg], index: int, price: Decimal) -> list[EditLeg]:
    """REQ-077 AC-1/AC-2: a typed planned entry must be a positive multiple of the file's tick size for that contract."""
    leg = legs[index].leg
    kind = ContractKind.FUTURE if leg.instrument is Instrument.FUT else ContractKind.OPTION
    tick = cat.tick_size(underlying, leg.expiry, kind)
    if type(price) is not Decimal or not price.is_finite() or price <= 0 or price % tick != 0:
        raise LegEditRefused("leg_edit_price_not_tick", leg=_ref(underlying, legs, index), tick=tick)
    return [replace(x, leg=replace(x.leg, entry_price=price), typed=True) if i == index else x
            for i, x in enumerate(legs)]


def with_entries(legs: list[EditLeg], entries: Mapping[int, Decimal]) -> list[EditLeg]:
    """REQ-077 AC-5 / REQ-078 AC-8: the freshly captured planned entries replace the old ones (and any typed mark)."""
    return [replace(x, leg=replace(x.leg, entry_price=entries[i]), typed=False) if i in entries else x
            for i, x in enumerate(legs)]
