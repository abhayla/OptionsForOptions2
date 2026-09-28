"""Match a concrete leg set to the parametric template it fits, with the parameters, or say it is Custom.

Spec: spec/requirements/REQ-028.md AC-4 ("any combination not matching a template is valid as a Custom
Strategy", Q52); ADR-006 Q52 ("resembles" wording is optional, so near misses are returned, not required).

Each leg's strike is measured in steps from the ATM strike of the given spot. For a template, legs are
paired by (action, instrument, expiry rank); the strike expressions are solved exactly for the template's
parameters, and the solution must satisfy every bound and constraint (sign constraints carry any ITM/ATM/OTM
requirement). A shape that fits more than one template is a catalogue defect and raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import permutations, product
from typing import Iterable, Mapping, Sequence

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.strategy.linear import solve_integer
from ofo.strategy.model import EXPIRY_SLOTS, Template, TemplateError, atm_strike

CUSTOM_STRATEGY = "Custom Strategy"

#: (action, instrument, strike offset from ATM in steps or None for futures, expiry rank) -> units.
Shape = Mapping[tuple[Action, Instrument, "int | None", int], int]


@dataclass(frozen=True)
class MatchResult:
    """The leg set is ``template`` at ``params``; each leg's units = ``base_quantity`` x its multiplier."""

    template: Template
    params: Mapping[str, int]
    base_quantity: int

    @property
    def label(self) -> str:
        return self.template.name


@dataclass(frozen=True)
class NearMiss:
    """A template with the same leg types that the leg set does not fit, and the first reason why."""

    template: Template
    reason: str


@dataclass(frozen=True)
class Custom:
    """No template fits: a valid Custom Strategy (Q52). ``nearest`` lists same-leg-type templates."""

    nearest: tuple[NearMiss, ...]

    @property
    def label(self) -> str:
        return CUSTOM_STRATEGY


def shape_of(legs: Sequence[Leg], *, spot: Decimal, strike_gap: Decimal) -> dict | None:
    """Merge legs into a :data:`Shape`; ``None`` when a strike is off the grid or expiries exceed the slots."""
    atm = atm_strike(spot, strike_gap)
    ranks = {expiry: i for i, expiry in enumerate(sorted({leg.expiry for leg in legs}))}
    if len(ranks) > len(EXPIRY_SLOTS):
        return None
    shape: dict = {}
    for leg in legs:
        offset = None
        if leg.instrument is not Instrument.FUT:
            steps = (leg.strike - atm) / strike_gap
            if steps != steps.to_integral_value():
                return None
            offset = int(steps)
        key = (leg.action, leg.instrument, offset, ranks[leg.expiry])
        shape[key] = shape.get(key, 0) + leg.quantity
    return shape


def template_shape(template: Template, values: Mapping[str, int], base_quantity: int = 1) -> dict:
    """The :data:`Shape` a template resolves to at ``values`` (used for uniqueness and round-trip checks)."""
    offsets = template.offsets(values)
    shape: dict = {}
    for leg in template.legs:
        key = (leg.action, leg.instrument, offsets[leg.name], EXPIRY_SLOTS.index(leg.expiry_slot))
        shape[key] = shape.get(key, 0) + base_quantity * leg.quantity_multiplier
    return shape


def _fit(template: Template, shape: Shape) -> tuple[dict[str, int], int] | str | None:
    """(params, base_quantity) if ``shape`` is this template; a reason string if it has the template's leg
    types but does not fit; ``None`` if its leg types differ."""
    if len(template.legs) != len(shape):
        return None
    observed: dict[tuple, list[tuple[int | None, int]]] = {}
    for (action, instrument, offset, rank), quantity in shape.items():
        observed.setdefault((action, instrument, rank), []).append((offset, quantity))
    expected: dict[tuple, list] = {}
    for leg in template.legs:
        expected.setdefault((leg.action, leg.instrument, EXPIRY_SLOTS.index(leg.expiry_slot)), []).append(leg)
    if {k: len(v) for k, v in observed.items()} != {k: len(v) for k, v in expected.items()}:
        return None

    groups = list(expected)
    reason = "strikes do not fit the template's shape"
    for choice in product(*(permutations(observed[g]) for g in groups)):
        pairs = [(leg, seen) for g, arrangement in zip(groups, choice) for leg, seen in zip(expected[g], arrangement)]
        bases = {quantity // leg.quantity_multiplier for leg, (_, quantity) in pairs}
        if len(bases) != 1 or any(quantity % leg.quantity_multiplier for leg, (_, quantity) in pairs):
            reason = "quantity ratio between legs differs from the template"
            continue
        equations = [(leg.strike, offset) for leg, (offset, _) in pairs if leg.strike is not None]
        values = solve_integer(equations, [p.name for p in template.params])
        if values is None:
            continue
        problems = template.violations(values)
        if problems:
            reason = problems[0]
            continue
        return values, bases.pop()
    return reason


def match_shape(shape: Shape, templates: Iterable[Template]) -> MatchResult | Custom:
    """Match a merged :data:`Shape` against ``templates``; exactly one fit, or Custom with near misses."""
    fits: list[MatchResult] = []
    near: list[NearMiss] = []
    for template in templates:
        outcome = _fit(template, shape)
        if isinstance(outcome, tuple):
            fits.append(MatchResult(template=template, params=outcome[0], base_quantity=outcome[1]))
        elif isinstance(outcome, str):
            near.append(NearMiss(template=template, reason=outcome))
    if len(fits) > 1:
        raise TemplateError(f"ambiguous catalogue: one leg set fits {[f.template.id for f in fits]}")
    return fits[0] if fits else Custom(nearest=tuple(near))


def match(
    legs: Strategy | Sequence[Leg],
    *,
    spot: Decimal,
    strike_gap: Decimal,
    templates: Iterable[Template],
) -> MatchResult | Custom:
    """Which template (and parameters) ``legs`` are, measured from the ATM strike of ``spot``; else Custom."""
    leg_list = tuple(legs.legs if isinstance(legs, Strategy) else legs)
    if not leg_list or not all(isinstance(leg, Leg) for leg in leg_list):
        raise TemplateError("match needs a non-empty sequence of Leg")
    shape = shape_of(leg_list, spot=spot, strike_gap=strike_gap)
    if shape is None:
        return Custom(nearest=())
    return match_shape(shape, templates)
