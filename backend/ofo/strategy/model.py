"""Template data shapes and the resolver: template + spot + strike gap + expiries -> engine ``Strategy``.

Spec: spec/requirements/REQ-028.md AC-1, AC-3, AC-5; ADR-042 (strike gap is per index, configurable);
ADR-001/Q8 (six leg types = the two ``Action`` values x the three ``Instrument`` values, already exact in
``ofo.engine.legs``). A template is pure data (id, name, description, legs); the resolver is the only code
that turns a template into a concrete ``Strategy``, so a new template file needs zero code changes (AC-3).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence

from ofo.engine.legs import Action, Instrument, Leg, require_decimal
from ofo.engine.strategy import Strategy

#: Fixed order in which named expiry slots are resolved. "near" is the nearest expiry a leg can sit on;
#: "next" is the one after it. A template that only uses "near" is single-expiry (AC-1); one that also
#: uses "next" (e.g. a calendar spread) is multi-expiry and the engine's exact metrics then raise
#: ``MultiExpiryError`` by design (scenario-calculations.md, "Multi-expiry strategies ... raise").
EXPIRY_SLOTS: tuple[str, ...] = ("near", "next")


class TemplateError(ValueError):
    """A template file, a template definition, or a resolve/match call is invalid."""


@dataclass(frozen=True)
class TemplateLeg:
    """One leg of a template, expressed relative to the strategy's own at-the-money strike."""

    action: Action
    instrument: Instrument
    offset_steps: int
    expiry_slot: str
    quantity_multiplier: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise TemplateError(f"action must be an Action, got {self.action!r}")
        if not isinstance(self.instrument, Instrument):
            raise TemplateError(f"instrument must be an Instrument, got {self.instrument!r}")
        if self.instrument is Instrument.FUT and self.offset_steps != 0:
            raise TemplateError("a futures leg has no strike, so its offset_steps must be 0")
        if isinstance(self.offset_steps, bool) or not isinstance(self.offset_steps, int):
            raise TemplateError(f"offset_steps must be an int, got {self.offset_steps!r}")
        if self.expiry_slot not in EXPIRY_SLOTS:
            raise TemplateError(f"expiry_slot must be one of {EXPIRY_SLOTS}, got {self.expiry_slot!r}")
        if (
            isinstance(self.quantity_multiplier, bool)
            or not isinstance(self.quantity_multiplier, int)
            or self.quantity_multiplier <= 0
        ):
            raise TemplateError(
                f"quantity_multiplier must be a positive int, got {self.quantity_multiplier!r}"
            )


@dataclass(frozen=True)
class Template:
    """A named strategy template: pure data, no formulas (AC-3, AC-5)."""

    id: str
    name: str
    description: str
    legs: tuple[TemplateLeg, ...]

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise TemplateError("a template needs a non-empty id")
        if not self.name or not isinstance(self.name, str):
            raise TemplateError(f"template {self.id!r} needs a non-empty name")
        if not self.description or not isinstance(self.description, str):
            raise TemplateError(f"template {self.id!r} needs a non-empty description")
        legs = tuple(self.legs)
        if not legs:
            raise TemplateError(f"template {self.id!r} needs at least one leg")
        for leg in legs:
            if not isinstance(leg, TemplateLeg):
                raise TemplateError(f"template {self.id!r}: every leg must be a TemplateLeg, got {leg!r}")
        object.__setattr__(self, "legs", legs)

    @property
    def is_single_expiry(self) -> bool:
        return len({leg.expiry_slot for leg in self.legs}) == 1


def atm_strike(spot: Decimal, strike_gap: Decimal) -> Decimal:
    """Round ``spot`` to the nearest multiple of ``strike_gap``; a tie rounds up (half-up), per REQ-028."""
    require_decimal(spot, "spot", allow_zero=False)
    require_decimal(strike_gap, "strike_gap", allow_zero=False)
    steps = (spot / strike_gap).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return steps * strike_gap


def resolve_template(
    template: Template,
    *,
    spot: Decimal,
    strike_gap: Decimal,
    expiries: Mapping[str, object],
    prices: Sequence[Decimal],
    base_quantity: int = 1,
) -> Strategy:
    """Resolve a template into a concrete engine ``Strategy`` (AC-1, AC-3).

    ``expiries`` maps each expiry slot the template uses (a subset of ``EXPIRY_SLOTS``) to a
    ``datetime.date``. ``prices`` supplies one entry price per template leg, in the template's leg
    order -- the caller's real or sample quote, never invented here. ``base_quantity`` is the number of
    units (lots x lot size) the *first* multiplier step represents; each leg's final quantity is
    ``base_quantity * leg.quantity_multiplier``.
    """
    if not isinstance(template, Template):
        raise TemplateError(f"resolve_template needs a Template, got {template!r}")
    if len(prices) != len(template.legs):
        raise TemplateError(
            f"template {template.id!r} has {len(template.legs)} legs but {len(prices)} prices were given"
        )
    if isinstance(base_quantity, bool) or not isinstance(base_quantity, int) or base_quantity <= 0:
        raise TemplateError(f"base_quantity must be a positive int, got {base_quantity!r}")
    atm = atm_strike(spot, strike_gap)

    legs: list[Leg] = []
    for template_leg, price in zip(template.legs, prices):
        if template_leg.expiry_slot not in expiries:
            raise TemplateError(
                f"template {template.id!r} needs expiry slot {template_leg.expiry_slot!r}, "
                f"which is missing from expiries={dict(expiries)!r}"
            )
        strike = (
            None
            if template_leg.instrument is Instrument.FUT
            else atm + Decimal(template_leg.offset_steps) * strike_gap
        )
        legs.append(
            Leg(
                action=template_leg.action,
                instrument=template_leg.instrument,
                strike=strike,
                expiry=expiries[template_leg.expiry_slot],
                quantity=base_quantity * template_leg.quantity_multiplier,
                entry_price=price,
            )
        )
    return Strategy(legs=tuple(legs))
