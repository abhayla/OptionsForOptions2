"""Leg edits of the Strategy Builder: strike step, multiplier, include tick, typed price (REQ-076, W-148).

Adapted from this repo's own branch build/W-126-a1-leg-rows (backend/ofo/strategy/leg_edit.py): REQ-076 parts, and the
REQ-078 Shift / Width / Hedge moves (W-158; ADR-186), all landing through the one rule :func:`_land`.

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

from ofo.charges.calculator import MAX_PRICE
from ofo.engine.executable_price import round_to_tick
from ofo.engine.legs import Action, Instrument, Leg
from ofo.errors import LegValue, UserFacing, UserFacingError, render
from ofo.instruments.catalogue import Catalogue, ContractKind
from ofo.instruments.freeze_limits import StoredFreeze, largest_allowed_units
from ofo.money import PAISE
from ofo.strategy import shape_families

MULTIPLIER_MIN, MULTIPLIER_MAX = 1, 50  # REQ-076 AC-4: whole numbers 1 to 50
OPTIONS = (Instrument.CE, Instrument.PE)
MAX_HEDGE_LEGS = 4  # REQ-078 AC-5: Hedge needs an even number of legs, at most 4
_TYPED_PRICE = re.compile(r"-?[0-9]{1,30}(\.[0-9]{1,30})?")  # ASCII digits only; the shape check, the rules come after


#: the not-applicable texts of the controls that name the shapes they apply to (REQ-078 AC-2), by catalogue template
_SHAPE_TEXT_CONTROL = {"leg_edit_width_not_applicable": shape_families.WIDTH,
                       "leg_edit_hedge_not_applicable": shape_families.HEDGE}


def render_reason(template: str, **slots: object) -> str:
    """The catalogue text of a refusal; the Width / Hedge not-applicable texts get the shape families from the
    strategy catalogue's data (never typed in code)."""
    control = _SHAPE_TEXT_CONTROL.get(template)
    if control is not None:
        slots.setdefault("shapes", shape_families.control_families(control))
    return render(template, **slots)


class LegEditRefused(UserFacing, ValueError):
    """An edit the rules refuse; nothing changed. Carries the catalogue template, its slots and the rendered message."""

    def __init__(self, template: str, **slots: object) -> None:
        self.template = template
        self.message = render_reason(template, **slots)
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


def _land(listing: Listing, underlying: str, legs: list[EditLeg], targets: Mapping[int, Decimal]) -> Moved:
    """The one landing rule (REQ-078 AC-6, REQ-076 AC-1): move each leg in ``targets`` to its new strike. If ANY target
    is not a listed, unexpired strike of that leg's expiry and type the whole move is refused (nothing changes) and the
    text names that leg. A moved leg is a new contract, so its typed mark goes."""
    out = list(legs)
    for index, strike in sorted(targets.items()):
        leg = legs[index].leg
        if strike <= 0:  # no strike exists below zero: the text cannot show it, so it is the "no further strike" answer
            raise LegEditRefused("leg_edit_no_further_strike", leg=leg_ref(underlying, legs, index))
        if strike not in listing.strikes(underlying, leg.expiry, leg.instrument):
            raise LegEditRefused("leg_edit_landing_not_listed", strikes=(strike,), kind=leg.instrument,
                                 expiry=leg.expiry, number=index + 1)
        out[index] = replace(legs[index], leg=replace(leg, strike=strike), typed=False)
    return Moved(out, frozenset(targets))


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
    return _land(listing, underlying, legs, {index: grid[at]})


def leg_steps(listing: Listing, underlying: str, legs: list[EditLeg]) -> dict[int, Decimal]:
    """REQ-078 AC-3: one strike step of each option leg (by index) = the strike gap the instrument file gives for THAT
    leg's own expiry (a calendar's two expiries may list different gaps). An option leg on an expired expiry, or an
    expiry the file has no strikes for, is refused naming that leg: a step is never read from a list that does not
    hold the leg."""
    steps: dict[int, Decimal] = {}
    for index, x in enumerate(legs):
        if x.leg.instrument not in OPTIONS:
            continue
        if not listing.strikes(underlying, x.leg.expiry, x.leg.instrument):
            raise LegEditRefused("leg_edit_strike_not_listed", leg=leg_ref(underlying, legs, index))
        steps[index] = listing.cat.strike_gap(underlying, x.leg.expiry)
    return steps


def reference_step(legs: list[EditLeg], steps: Mapping[int, Decimal]) -> Decimal:
    """The one step a whole-strategy number is counted in (the Shift total, Width's last-step test): the step of the
    option leg with the nearest expiry (the first such leg), never a minimum across expiries."""
    return steps[min(steps, key=lambda i: (legs[i].leg.expiry, i))]


def shift_step(listing: Listing, underlying: str, legs: list[EditLeg]) -> Decimal:
    return reference_step(legs, leg_steps(listing, underlying, legs))


def shift(listing: Listing, underlying: str, legs: list[EditLeg], direction: int) -> Moved:
    """REQ-078 AC-3: every option leg by one strike step of its own expiry; futures legs stay where they are."""
    options = [i for i, x in enumerate(legs) if x.leg.instrument in OPTIONS]
    if not options:
        raise LegEditRefused("leg_edit_shift_needs_option_leg")
    steps = leg_steps(listing, underlying, legs)
    return _land(listing, underlying, legs, {i: legs[i].leg.strike + direction * steps[i] for i in options})


def width(listing: Listing, underlying: str, legs: list[EditLeg], direction: int,
          spot: Decimal | None = None) -> Moved:
    """REQ-078 AC-4 / ADR-186 (5): every call leg one step up and every put leg one step down (reversed for -1), so the
    width (the lowest call strike minus the highest put strike) changes by two steps and the hedge distances stay.
    The width never goes below 0: the change is cut to what is left (a width of 0 refuses -1). When half the cut change
    is less than one step, ONLY the side nearer the live index price moves, by the whole change; with no live price
    (``spot`` None) or equal distances the CALL side moves (a missing price counts as below both sides)."""
    puts = {i: x.leg.strike for i, x in enumerate(legs) if x.leg.instrument is Instrument.PE}
    calls = {i: x.leg.strike for i, x in enumerate(legs) if x.leg.instrument is Instrument.CE}
    if not puts or not calls:
        raise LegEditRefused("leg_edit_width_not_applicable")
    steps = leg_steps(listing, underlying, legs)
    ref = reference_step(legs, steps)
    now = min(calls.values()) - max(puts.values())
    change = min(2 * ref, now) if direction < 0 else 2 * ref  # how far the width may move (never below 0)
    if change <= 0:
        raise LegEditRefused("leg_edit_width_below_zero")
    if change / 2 >= ref:
        targets = {i: x.leg.strike + (direction * steps[i] if i in calls else -direction * steps[i])
                   for i, x in enumerate(legs) if x.leg.instrument in OPTIONS}
    else:
        put_nearer = spot is not None and abs(spot - max(puts.values())) < abs(spot - min(calls.values()))
        side = puts if put_nearer else calls
        targets = {i: strike - direction * change if put_nearer else strike + direction * change
                   for i, strike in side.items()}
    return _land(listing, underlying, legs, targets)


def _hedge_distances(legs: list[EditLeg], protective: frozenset[int]) -> dict[int, tuple[int, Decimal]]:
    """For each Hedge leg (by index): (the index of its short leg, its distance from it, outwards). A Hedge leg must be
    an option, be the only Hedge of its type, and sit beyond a non-Hedge leg of the same type; anything else is not a
    shape this control handles (fail closed)."""
    out: dict[int, tuple[int, Decimal]] = {}
    for i in sorted(protective):
        leg = legs[i].leg
        if leg.instrument not in OPTIONS or any(legs[j].leg.instrument is leg.instrument for j in out):
            raise LegEditRefused("leg_edit_hedge_not_applicable")
        sign = 1 if leg.instrument is Instrument.CE else -1  # a call hedge sits above its short, a put hedge below
        shorts = [j for j, x in enumerate(legs) if j not in protective and x.leg.instrument is leg.instrument
                  and sign * (leg.strike - x.leg.strike) > 0]
        if not shorts:
            raise LegEditRefused("leg_edit_hedge_not_applicable")
        near = min(shorts, key=lambda j: abs(leg.strike - legs[j].leg.strike))
        out[i] = (near, sign * (leg.strike - legs[near].leg.strike))
    return out


def hedge(listing: Listing, underlying: str, legs: list[EditLeg], protective: frozenset[int], direction: int) -> Moved:
    """REQ-078 AC-5 / ADR-186: only the legs marked Hedge move, away from (+1) or towards (-1) their short leg; the
    distance never goes below one step; an even number of legs, at most 4.

    Equal put-side and call-side distances: both move one step. Unequal (as in Sensibull): +1 moves ONLY the nearer
    hedge out until its distance equals the farther one; -1 moves ONLY the farther hedge in until its distance equals
    the nearer one. A vertical spread (one hedge) moves its one hedge one step."""
    if not protective or len(legs) % 2 or len(legs) > MAX_HEDGE_LEGS:
        raise LegEditRefused("leg_edit_hedge_not_applicable")
    steps = leg_steps(listing, underlying, legs)
    found = _hedge_distances(legs, protective)
    distances = {i: d for i, (_, d) in found.items()}
    if len(set(distances.values())) > 1:  # unequal: only the side that evens them out
        pick = min(distances.values()) if direction > 0 else max(distances.values())
        wanted = {i: max(distances.values()) if direction > 0 else min(distances.values())
                  for i, d in distances.items() if d == pick}
    else:
        wanted = {i: d + direction * steps[i] for i, d in distances.items()}
    targets: dict[int, Decimal] = {}
    for i, new_distance in wanted.items():
        short = legs[found[i][0]].leg.strike
        if new_distance < steps[i]:
            raise LegEditRefused("leg_edit_hedge_below_minimum", leg=leg_ref(underlying, legs, i))
        targets[i] = short + new_distance if legs[i].leg.instrument is Instrument.CE else short - new_distance
    return _land(listing, underlying, legs, targets)


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
    # bounded BEFORE quantize: 27+ whole digits make quantize raise InvalidOperation; above the charges module's
    # absurd-price cap is no option or future price, so it is the same one price refusal, never a crash
    if (value is None or value <= 0 or value > MAX_PRICE or value != value.quantize(PAISE)
            or round_to_tick(value, tick, Action.BUY) != value):
        raise LegEditRefused("leg_edit_price_not_tick", leg=leg_ref(underlying, legs, index), tick=tick)
    return [replace(x, leg=replace(x.leg, entry_price=value.quantize(PAISE)), typed=True) if i == index else x
            for i, x in enumerate(legs)]


def with_entries(legs: list[EditLeg], entries: Mapping[int, Decimal]) -> list[EditLeg]:
    """REQ-076 AC-2 / REQ-077 AC-5: the freshly captured planned entries replace the old ones (and any typed mark)."""
    return [replace(x, leg=replace(x.leg, entry_price=entries[i]), typed=False) if i in entries else x
            for i, x in enumerate(legs)]
