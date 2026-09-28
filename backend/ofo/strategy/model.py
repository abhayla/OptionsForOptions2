"""Parametric strategy templates and the resolver: template + params + spot + strike gap -> engine ``Strategy``.

Spec: spec/requirements/REQ-028.md AC-1, AC-3, AC-5; ADR-006 (Q8: the system builds the strategy from simple
answers, so a template is a SHAPE with parameters, not one fixed set of strikes); ADR-042 (strike gap per index).

A template is pure data: named integer parameters (in strike steps, with a default and bounds), constraints
between them, and legs whose strike is a linear expression of the parameters, measured in strike steps from
the at-the-money (ATM) strike. Nothing in this module knows any particular template (AC-5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence, Union

from ofo.engine.legs import Action, Instrument, Leg, require_decimal
from ofo.engine.strategy import Strategy
from ofo.strategy.linear import LinearExpr, rank_of

#: Named expiry slots, in time order. A template must use a prefix of this tuple ("near", or "near" and
#: "next"); a multi-expiry strategy's exact metrics raise ``MultiExpiryError`` by design.
EXPIRY_SLOTS: tuple[str, ...] = ("near", "next")

#: Hard cap on any parameter bound, default or strike-expression constant, in strike steps.
MAX_STEPS = 50

#: Sign of a leg's strike offset from ATM. ``positive`` = above ATM, ``negative`` = below ATM.
SIGNS: tuple[str, ...] = ("negative", "non_positive", "zero", "non_negative", "positive")


class TemplateError(ValueError):
    """A template file, a template definition, or a resolve/match call is invalid."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def sign_holds(sign: str, offset: int) -> bool:
    return {
        "negative": offset < 0,
        "non_positive": offset <= 0,
        "zero": offset == 0,
        "non_negative": offset >= 0,
        "positive": offset > 0,
    }[sign]


@dataclass(frozen=True)
class Param:
    """One template parameter: an integer count of strike steps."""

    name: str
    default: int
    min: int
    max: int
    must_be_positive: bool = False
    unit: str = "steps"

    def __post_init__(self) -> None:
        for label in ("default", "min", "max"):
            value = getattr(self, label)
            if not _is_int(value) or abs(value) > MAX_STEPS:
                raise TemplateError(f"param {self.name!r}: {label} must be an int within +/-{MAX_STEPS}, got {value!r}")
        if self.unit != "steps":
            raise TemplateError(f"param {self.name!r}: unit must be 'steps', got {self.unit!r}")
        if not self.min <= self.default <= self.max:
            raise TemplateError(f"param {self.name!r}: need min <= default <= max, got {self.min}/{self.default}/{self.max}")
        if self.must_be_positive and self.min < 1:
            raise TemplateError(f"param {self.name!r}: must_be_positive needs min >= 1, got {self.min}")

    def violation(self, value: int) -> str | None:
        if not _is_int(value):
            return f"param {self.name!r} must be an int, got {value!r}"
        if not self.min <= value <= self.max:
            return f"param {self.name!r}={value} outside its bounds [{self.min}, {self.max}]"
        if self.must_be_positive and value <= 0:
            return f"param {self.name!r}={value} must be positive"
        return None


@dataclass(frozen=True)
class TemplateLeg:
    """One template leg. ``strike`` is ``None`` for a futures leg, else steps from ATM as an expression."""

    name: str
    action: Action
    instrument: Instrument
    strike: LinearExpr | None
    expiry_slot: str
    quantity_multiplier: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise TemplateError(f"leg {self.name!r}: action must be an Action, got {self.action!r}")
        if not isinstance(self.instrument, Instrument):
            raise TemplateError(f"leg {self.name!r}: instrument must be an Instrument, got {self.instrument!r}")
        if (self.instrument is Instrument.FUT) != (self.strike is None):
            raise TemplateError(f"leg {self.name!r}: a futures leg has no strike and an option leg needs one")
        if self.strike is not None and abs(self.strike.const) > MAX_STEPS:
            raise TemplateError(f"leg {self.name!r}: strike constant {self.strike.const} beyond +/-{MAX_STEPS} steps")
        if self.expiry_slot not in EXPIRY_SLOTS:
            raise TemplateError(f"leg {self.name!r}: expiry_slot must be one of {EXPIRY_SLOTS}, got {self.expiry_slot!r}")
        if not _is_int(self.quantity_multiplier) or not 1 <= self.quantity_multiplier <= 10:
            raise TemplateError(f"leg {self.name!r}: quantity_multiplier must be an int 1..10, got {self.quantity_multiplier!r}")


@dataclass(frozen=True)
class EqualConstraint:
    """Two parameters must take the same value."""

    params: tuple[str, str]


@dataclass(frozen=True)
class SignConstraint:
    """A leg's strike offset from ATM must have this sign (how ITM/ATM/OTM is expressed)."""

    leg: str
    sign: str


@dataclass(frozen=True)
class OrderConstraint:
    """``lower`` leg's strike is strictly below ``higher`` leg's strike."""

    lower: str
    higher: str


Constraint = Union[EqualConstraint, SignConstraint, OrderConstraint]


@dataclass(frozen=True)
class Template:
    """A named, parametric strategy template: pure data (AC-3, AC-5)."""

    id: str
    name: str
    description: str
    params: tuple[Param, ...]
    constraints: tuple[Constraint, ...]
    legs: tuple[TemplateLeg, ...]
    _params_by_name: dict = field(init=False, repr=False, compare=False)
    _legs_by_name: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for label in ("id", "name", "description"):
            if not isinstance(getattr(self, label), str) or not getattr(self, label):
                raise TemplateError(f"template needs a non-empty string {label}")
        params, legs, constraints = tuple(self.params), tuple(self.legs), tuple(self.constraints)
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "legs", legs)
        object.__setattr__(self, "constraints", constraints)
        if not legs:
            raise TemplateError(f"template {self.id!r} needs at least one leg")
        by_param = {p.name: p for p in params}
        by_leg = {leg.name: leg for leg in legs}
        if len(by_param) != len(params):
            raise TemplateError(f"template {self.id!r}: duplicate param name")
        if len(by_leg) != len(legs):
            raise TemplateError(f"template {self.id!r}: duplicate leg name")
        object.__setattr__(self, "_params_by_name", by_param)
        object.__setattr__(self, "_legs_by_name", by_leg)
        self._check_legs()
        self._check_constraints()
        violations = self.violations(self.defaults())
        if violations:
            raise TemplateError(f"template {self.id!r}: defaults break its own rules: {violations}")

    def _check_legs(self) -> None:
        slots = {leg.expiry_slot for leg in self.legs}
        if slots != set(EXPIRY_SLOTS[: len(slots)]):
            raise TemplateError(f"template {self.id!r}: expiry slots {sorted(slots)} must be a prefix of {EXPIRY_SLOTS}")
        keys = [(leg.action, leg.instrument, leg.strike, leg.expiry_slot) for leg in self.legs]
        if len(set(keys)) != len(keys):
            raise TemplateError(f"template {self.id!r}: two identical legs; use quantity_multiplier instead")
        expressions = [leg.strike for leg in self.legs if leg.strike is not None]
        for leg_expr in expressions:
            unknown = leg_expr.params - self._params_by_name.keys()
            if unknown:
                raise TemplateError(f"template {self.id!r}: strike uses unknown param(s) {sorted(unknown)}")
        used = set().union(*(e.params for e in expressions)) if expressions else set()
        unused = self._params_by_name.keys() - used
        if unused:
            raise TemplateError(f"template {self.id!r}: param(s) {sorted(unused)} appear in no leg strike")
        names = [p.name for p in self.params]
        if rank_of(expressions, names) != len(names):
            raise TemplateError(f"template {self.id!r}: params cannot be recovered from strikes (not independent)")

    def _check_constraints(self) -> None:
        for constraint in self.constraints:
            if isinstance(constraint, EqualConstraint):
                a, b = constraint.params
                if a == b or a not in self._params_by_name or b not in self._params_by_name:
                    raise TemplateError(f"template {self.id!r}: equal constraint needs two known params, got {constraint.params}")
            elif isinstance(constraint, SignConstraint):
                leg = self._legs_by_name.get(constraint.leg)
                if leg is None or leg.strike is None:
                    raise TemplateError(f"template {self.id!r}: sign constraint needs an option leg, got {constraint.leg!r}")
                if constraint.sign not in SIGNS:
                    raise TemplateError(f"template {self.id!r}: sign must be one of {SIGNS}, got {constraint.sign!r}")
            elif isinstance(constraint, OrderConstraint):
                for name in (constraint.lower, constraint.higher):
                    leg = self._legs_by_name.get(name)
                    if leg is None or leg.strike is None:
                        raise TemplateError(f"template {self.id!r}: order constraint needs option legs, got {name!r}")
                if constraint.lower == constraint.higher:
                    raise TemplateError(f"template {self.id!r}: order constraint needs two different legs")
            else:
                raise TemplateError(f"template {self.id!r}: unknown constraint {constraint!r}")

    def leg(self, name: str) -> TemplateLeg:
        return self._legs_by_name[name]

    def defaults(self) -> dict[str, int]:
        return {p.name: p.default for p in self.params}

    def offsets(self, values: Mapping[str, int]) -> dict[str, int | None]:
        """Each leg's strike offset from ATM, in steps (``None`` for a futures leg)."""
        return {leg.name: None if leg.strike is None else leg.strike.evaluate(values) for leg in self.legs}

    def violations(self, values: Mapping[str, int]) -> list[str]:
        """Every bound or constraint ``values`` breaks; empty when the parameter set is allowed."""
        problems: list[str] = []
        if set(values) != self._params_by_name.keys():
            return [f"params must be exactly {sorted(self._params_by_name)}, got {sorted(values)}"]
        for param in self.params:
            problem = param.violation(values[param.name])
            if problem:
                problems.append(problem)
        if problems:
            return problems
        offsets = self.offsets(values)
        for constraint in self.constraints:
            if isinstance(constraint, EqualConstraint):
                a, b = constraint.params
                if values[a] != values[b]:
                    problems.append(f"equal constraint {a}={values[a]} vs {b}={values[b]}")
            elif isinstance(constraint, SignConstraint):
                if not sign_holds(constraint.sign, offsets[constraint.leg]):
                    problems.append(f"sign constraint: leg {constraint.leg!r} offset {offsets[constraint.leg]} is not {constraint.sign}")
            else:
                if not offsets[constraint.lower] < offsets[constraint.higher]:
                    problems.append(f"order constraint: leg {constraint.lower!r} must sit below leg {constraint.higher!r}")
        return problems


def atm_strike(spot: Decimal, strike_gap: Decimal) -> Decimal:
    """Round ``spot`` to the nearest multiple of ``strike_gap``; a tie rounds up.

    The half-up tie rule is an ADR-045 overnight default, not a REQ-028 requirement.
    """
    require_decimal(spot, "spot", allow_zero=False)
    require_decimal(strike_gap, "strike_gap", allow_zero=False)
    steps = (spot / strike_gap).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return steps * strike_gap


def resolve_params(template: Template, overrides: Mapping[str, int] | None = None) -> dict[str, int]:
    """Defaults, replaced by ``overrides``; unknown names, bounds and constraints fail closed."""
    values = template.defaults()
    for name, value in (overrides or {}).items():
        if name not in values:
            raise TemplateError(f"template {template.id!r} has no param {name!r} (has {sorted(values)})")
        values[name] = value
    problems = template.violations(values)
    if problems:
        raise TemplateError(f"template {template.id!r}: {problems}")
    return values


def resolve_template(
    template: Template,
    *,
    spot: Decimal,
    strike_gap: Decimal,
    expiries: Mapping[str, object],
    prices: Sequence[Decimal],
    base_quantity: int = 1,
    overrides: Mapping[str, int] | None = None,
) -> Strategy:
    """Resolve a template into a concrete engine ``Strategy`` (AC-1, AC-3).

    ``expiries`` maps each slot the template uses to a ``datetime.date``. ``prices`` gives one entry price
    per template leg, in leg order (the caller's quote, never invented here). Each leg's quantity is
    ``base_quantity * quantity_multiplier`` units.
    """
    if not isinstance(template, Template):
        raise TemplateError(f"resolve_template needs a Template, got {template!r}")
    if len(prices) != len(template.legs):
        raise TemplateError(f"template {template.id!r} has {len(template.legs)} legs but {len(prices)} prices were given")
    if not _is_int(base_quantity) or base_quantity <= 0:
        raise TemplateError(f"base_quantity must be a positive int, got {base_quantity!r}")
    values = resolve_params(template, overrides)
    offsets = template.offsets(values)
    atm = atm_strike(spot, strike_gap)
    legs: list[Leg] = []
    for template_leg, price in zip(template.legs, prices):
        if template_leg.expiry_slot not in expiries:
            raise TemplateError(f"template {template.id!r} needs expiry slot {template_leg.expiry_slot!r}")
        offset = offsets[template_leg.name]
        strike = None if offset is None else atm + Decimal(offset) * strike_gap
        if strike is not None and strike <= 0:
            raise TemplateError(f"template {template.id!r}: leg {template_leg.name!r} resolves to strike {strike}")
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
