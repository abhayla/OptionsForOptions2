"""Strategy definition: what the user told the platform. Never holds market data.

Spec: REQ-038 AC-1; ADR-019 Q189 ("Market movement can change what the platform tells the user, but it cannot
change what the user told the platform"); spec/data/domain-model.md §2. The live market side is
``ofo.strategy.live_state.LiveState``, a separate object.

A definition leg has no entry price and no LTP: prices are market facts (live state) or execution facts (the
broker's fills), not user decisions. Risk limits and preferences are named values because the spec defines no
fixed field list for either; names are validated so a misspelling is not silently a new limit.

Meaningful change (REQ-070 AC-2, T2 #84): adding/removing a leg, changing a strike, quantity or expiry, and
changing rules, risk limits or preferences (they change risk). Leg ORDER and the textual form of an equal number
(``23000`` vs ``23000.00``) are not meaningful. Counting a preference change as meaningful is a builder default
under ADR-045 (T2 #84 does not list preferences); it records more, never less.
"""
from __future__ import annotations
from ofo.errors.explanations import render_explanation

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Union

from ofo.engine.legs import Action, Instrument, require_decimal, require_price
from ofo.engine.strategy import Strategy
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

MAX_LEGS = 20
MAX_UNITS = 1_000_000
MAX_NAMED_VALUES = 20
MAX_TEXT = 200
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: A contract a position is held in: (underlying, instrument, strike, expiry). Strike is None for futures.
Contract = tuple[str, Instrument, Union[Decimal, None], datetime.date]


class DefinitionError(ValueError):
    """A strategy definition (or a change to one) is invalid."""

    def __init__(self, *args: object, detail: str | None = None) -> None:
        """``detail`` marks developer-only input-validation text: it is never shown to a user."""
        super().__init__(*args) if detail is None else super().__init__(detail)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def contract_sort_key(contract: Contract) -> tuple:
    underlying, instrument, strike, expiry = contract
    return (underlying, instrument.value, strike if strike is not None else Decimal(0), expiry)


def describe_contract(contract: Contract) -> str:
    underlying, instrument, strike, expiry = contract
    strike_text = "" if strike is None else f" {strike.normalize():f}"
    return render_explanation("contract_description", underlying=underlying, strike=strike_text,
                              instrument=instrument.value, expiry=expiry.isoformat())


@dataclass(frozen=True)
class DefinitionLeg:
    """One leg the user chose: side, instrument, strike, expiry and quantity in units (lots x lot size)."""

    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.action, Action):
            raise DefinitionError(f"action must be an Action, got {self.action!r}")
        if not isinstance(self.instrument, Instrument):
            raise DefinitionError(f"instrument must be an Instrument, got {self.instrument!r}")
        if self.instrument is Instrument.FUT:
            if self.strike is not None:
                raise DefinitionError("a futures leg has no strike")
        else:
            try:
                require_price(self.strike, "strike", allow_zero=False)
            except ValueError as exc:
                raise DefinitionError(str(exc)) from exc
        if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
            raise DefinitionError(f"expiry must be a datetime.date, got {self.expiry!r}")
        if not _is_int(self.quantity) or not 0 < self.quantity <= MAX_UNITS:
            raise DefinitionError(f"quantity must be an int in 1..{MAX_UNITS} units, got {self.quantity!r}")

    def signed_quantity(self) -> int:
        return self.quantity if self.action is Action.BUY else -self.quantity

    def describe(self) -> str:
        strike = "" if self.strike is None else f" {self.strike.normalize():f}"
        return render_explanation("leg_description", action=self.action.value, strike=strike,
                                  instrument=self.instrument.value, expiry=self.expiry.isoformat(),
                                  quantity=self.quantity)


def _named(values: object, label: str, check) -> tuple:
    if isinstance(values, Mapping):
        items = list(values.items())
    elif isinstance(values, tuple):
        items = list(values)
    else:
        raise DefinitionError(detail=f"{label} must be a mapping or a tuple of (name, value) pairs, got {values!r}")
    if len(items) > MAX_NAMED_VALUES:
        raise DefinitionError(detail=f"{label}: at most {MAX_NAMED_VALUES} entries, got {len(items)}")
    seen: set[str] = set()
    out = []
    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise DefinitionError(detail=f"{label}: each entry must be a (name, value) pair, got {item!r}")
        name, value = item
        if not isinstance(name, str) or not _NAME.match(name):
            raise DefinitionError(detail=f"{label}: name must match {_NAME.pattern}, got {name!r}")
        if name in seen:
            raise DefinitionError(detail=f"{label}: duplicate name {name!r}")
        seen.add(name)
        out.append((name, check(name, value)))
    return tuple(sorted(out))


def _limit_value(name: str, value: object) -> Decimal:
    try:
        return require_decimal(value, f"risk limit {name!r}")
    except ValueError as exc:
        raise DefinitionError(str(exc)) from exc


def _preference_value(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise DefinitionError(f"preference {name!r} must be a non-empty string of at most {MAX_TEXT} chars")
    return value


@dataclass(frozen=True)
class StrategyDefinition:
    """The versioned, stable half of a strategy (Q189). Immutable; a change is a NEW definition."""

    underlying: str
    legs: tuple[DefinitionLeg, ...]
    rules_ref: str | None = None
    risk_limits: tuple[tuple[str, Decimal], ...] = ()
    preferences: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.underlying not in SUPPORTED_UNDERLYINGS:
            raise DefinitionError(f"underlying must be one of {sorted(SUPPORTED_UNDERLYINGS)}, got {self.underlying!r}")
        if not isinstance(self.legs, (tuple, list)):
            raise DefinitionError(f"legs must be a tuple of DefinitionLeg, got {self.legs!r}")
        legs = tuple(self.legs)
        if not 1 <= len(legs) <= MAX_LEGS:
            raise DefinitionError(f"a definition needs 1..{MAX_LEGS} legs, got {len(legs)}")
        contracts: set[Contract] = set()
        for leg in legs:
            if not isinstance(leg, DefinitionLeg):
                raise DefinitionError(f"every leg must be a DefinitionLeg, got {leg!r}")
            contract = self._contract_of(leg)
            if contract in contracts:
                raise DefinitionError(
                    f"two legs on the same contract {describe_contract(contract)}; use one leg with the total quantity"
                )
            contracts.add(contract)
        if self.rules_ref is not None and (
            not isinstance(self.rules_ref, str) or not self.rules_ref.strip() or len(self.rules_ref) > MAX_TEXT
        ):
            raise DefinitionError(f"rules_ref must be None or a non-empty string, got {self.rules_ref!r}")
        object.__setattr__(self, "legs", legs)
        object.__setattr__(self, "risk_limits", _named(self.risk_limits, "risk_limits", _limit_value))
        object.__setattr__(self, "preferences", _named(self.preferences, "preferences", _preference_value))

    def _contract_of(self, leg: DefinitionLeg) -> Contract:
        return (self.underlying, leg.instrument, leg.strike, leg.expiry)

    @classmethod
    def from_engine(cls, underlying: str, strategy: Strategy, **fields: object) -> "StrategyDefinition":
        """Take the user's decisions from an engine ``Strategy``; its entry prices and LTPs are dropped."""
        if not isinstance(strategy, Strategy):
            raise DefinitionError(f"from_engine needs an engine Strategy, got {strategy!r}")
        legs = tuple(
            DefinitionLeg(leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity) for leg in strategy.legs
        )
        return cls(underlying, legs, **fields)

    @property
    def expiries(self) -> tuple[datetime.date, ...]:
        return tuple(sorted({leg.expiry for leg in self.legs}))

    def intended_position(self) -> dict[Contract, int]:
        """Net signed units per contract this definition asks for (BUY positive, SELL negative)."""
        return {self._contract_of(leg): leg.signed_quantity() for leg in self.legs}

    def changes_from(self, old: "StrategyDefinition") -> tuple[str, ...]:
        """Every meaningful difference from ``old``, described; empty when nothing meaningful changed."""
        if not isinstance(old, StrategyDefinition):
            raise DefinitionError(f"changes_from needs a StrategyDefinition, got {old!r}")
        changes: list[str] = []
        if old.underlying != self.underlying:
            changes.append(render_explanation("change_underlying", old=old.underlying, new=self.underlying))
        old_legs = {old._leg_key(leg): leg for leg in old.legs}
        new_legs = {self._leg_key(leg): leg for leg in self.legs}
        for key in sorted(old_legs.keys() - new_legs.keys(), key=_leg_sort_key):
            changes.append(render_explanation("change_leg_removed", leg=old_legs[key].describe()))
        for key in sorted(new_legs.keys() - old_legs.keys(), key=_leg_sort_key):
            changes.append(render_explanation("change_leg_added", leg=new_legs[key].describe()))
        for key in sorted(old_legs.keys() & new_legs.keys(), key=_leg_sort_key):
            before, after = old_legs[key].quantity, new_legs[key].quantity
            if before != after:
                changes.append(render_explanation("change_quantity", leg=new_legs[key].describe(), before=before))
        for label in ("rules_ref", "risk_limits", "preferences"):
            if getattr(old, label) != getattr(self, label):
                changes.append(render_explanation("change_field", label=label, old=repr(getattr(old, label)),
                                                  new=repr(getattr(self, label))))
        return tuple(changes)

    @staticmethod
    def _leg_key(leg: DefinitionLeg) -> tuple:
        return (leg.action, leg.instrument, leg.strike, leg.expiry)


def _leg_sort_key(key: tuple) -> tuple:
    action, instrument, strike, expiry = key
    return (action.value, instrument.value, strike if strike is not None else Decimal(0), expiry)
