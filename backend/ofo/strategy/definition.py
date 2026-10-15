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
from ofo.errors.explanations import render_explanation, strike_text

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Union

from ofo.engine.legs import Action, Instrument, require_decimal, require_price
from ofo.engine.strategy import Strategy
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo.strategy import settings_value

MAX_LEGS = 20
MAX_UNITS = 1_000_000
MAX_NAMED_VALUES = 20
MAX_TEXT = 200
MAX_CHANGE_ITEMS = 100  # migration 0008's ofo_strategy_change_items_valid: a stored summary holds 1..100 items
#: A strike as the stored text writes it (str(Decimal)): plain digits, at most 18 integer digits, no leading zero, a
#: whole number of paise. The database validator (migration 0008 STRIKE_REGEX) is the same text rule; the domain
#: refuses first, with its own refusal, so a save never fails late with a bare check violation.
STRIKE_PATTERN = r"(0|[1-9][0-9]{0,17})([.][0-9]{1,2}0*)?"
_STRIKE_TEXT = re.compile(STRIKE_PATTERN)
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: A contract a position is held in: (underlying, instrument, strike, expiry). Strike is None for futures.
Contract = tuple[str, Instrument, Union[Decimal, None], datetime.date]


#: ADR-064: the only names a definition's maps may use (REQ-025 AC-1's inputs), compared exactly - no case folding,
#: no trimming. Any other name is refused on every path that builds or loads a definition; a new name needs a new
#: decision row. A closed list, not a list of forbidden live-market spellings (which missed LTP, Spot, last_price, ...).
RISK_LIMIT_NAMES = frozenset({"max_loss", "max_capital", "max_margin"})
PREFERENCE_NAMES = frozenset({"objective", "market_view", "risk_preference", "capital", "expected_range_low",
                              "expected_range_high"})


class DefinitionError(ValueError):
    """A strategy definition (or a change to one) is invalid."""

    def __init__(self, *args: object, detail: str | None = None) -> None:
        """``detail`` marks developer-only input-validation text: it is never shown to a user."""
        super().__init__(*args) if detail is None else super().__init__(detail)


class ValueRefusedError(DefinitionError):
    """A risk limit, preference or rules reference outside ADR-069's type (an identifier or a number). The text holds
    no part of the value, so no path can echo it."""


class UnknownNameError(DefinitionError):
    """A risk-limit or preference name outside ADR-064's closed list. ``map_name`` is 'risk_limits' or 'preferences'."""

    def __init__(self, map_name: str, names: list[str], text: str) -> None:
        """``text`` is developer detail (built where the error is raised, as a DefinitionError's is)."""
        self.map_name = map_name
        self.names = names
        super().__init__(text)


def check_names(map_name: str, names) -> None:
    """Refuses (UnknownNameError) any name not in ADR-064's list for ``map_name``; exact comparison."""
    allowed = {"risk_limits": RISK_LIMIT_NAMES, "preferences": PREFERENCE_NAMES}[map_name]
    unknown = [n for n in names if not isinstance(n, str) or n not in allowed]
    if unknown:
        raise UnknownNameError(
            map_name, unknown, f"{map_name}: unknown name(s) {unknown}; allowed {sorted(allowed)} (ADR-064)")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def contract_sort_key(contract: Contract) -> tuple:
    underlying, instrument, strike, expiry = contract
    return (underlying, instrument.value, strike if strike is not None else Decimal(0), expiry)


def describe_contract(contract: Contract) -> str:
    underlying, instrument, strike, expiry = contract
    return render_explanation("contract_description", underlying=underlying, strike=strike_text(strike),
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
            # Refuses Decimal("2.28E+4") (= 22800) on purpose: str() gives an exponent, the stored text refuses it too,
            # and no source produces one (the catalogue and the API hand over plain-digit text) - issue #184 item 4.
            if _STRIKE_TEXT.fullmatch(str(self.strike)) is None:  # the stored text rule: size and plain digits
                raise DefinitionError("strike is outside the stored form: at most 18 integer digits, no exponent")
        if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
            raise DefinitionError(f"expiry must be a datetime.date, got {self.expiry!r}")
        if not _is_int(self.quantity) or not 0 < self.quantity <= MAX_UNITS:
            raise DefinitionError(f"quantity must be an int in 1..{MAX_UNITS} units, got {self.quantity!r}")

    def signed_quantity(self) -> int:
        return self.quantity if self.action is Action.BUY else -self.quantity

    def describe(self) -> str:
        return render_explanation("leg_description", action=self.action.value, strike=strike_text(self.strike),
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
        check_names(label, [name])  # ADR-064 closed list first: an unknown name gets its own error
        if not isinstance(name, str) or not _NAME.match(name):
            raise DefinitionError(detail=f"{label}: name must match {_NAME.pattern}, got {name!r}")
        if name in seen:
            raise DefinitionError(detail=f"{label}: duplicate name {name!r}")
        seen.add(name)
        out.append((name, check(name, value)))
    return tuple(sorted(out))


def _limit_value(name: str, value: object) -> Decimal:
    try:
        return settings_value.limit(value, f"risk_limit.{name}")
    except settings_value.SettingsValueError as exc:
        raise ValueRefusedError(detail=f"{exc.kind} is not an identifier or number (ADR-069), got a {exc.got}") from None


def _preference_value(name: str, value: object) -> str:
    try:
        return settings_value.identifier(value, f"preference.{name}")
    except settings_value.SettingsValueError as exc:
        raise ValueRefusedError(detail=f"{exc.kind} is not an identifier or number (ADR-069), got a {exc.got}") from None


def _rules_ref(value: object) -> str | None:
    if value is None:
        return None
    try:
        return settings_value.identifier(value, "rules_ref")
    except settings_value.SettingsValueError as exc:
        raise ValueRefusedError(detail=f"{exc.kind} is not an identifier or number (ADR-069), got a {exc.got}") from None


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
        object.__setattr__(self, "rules_ref", _rules_ref(self.rules_ref))
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
        return _render_items(self.change_items(old))

    def change_items(self, old: "StrategyDefinition") -> tuple[dict, ...]:
        """The same differences as DATA (a closed shape, see ``render_change_items``): what an activity-history entry
        stores, so the text a user reads is always rendered from the catalogue, never kept as text."""
        if not isinstance(old, StrategyDefinition):
            raise DefinitionError(f"changes_from needs a StrategyDefinition, got {old!r}")
        items: list[dict] = []
        if old.underlying != self.underlying:
            items.append({"kind": "underlying", "old": old.underlying, "new": self.underlying})
        old_legs = {old._leg_key(leg): leg for leg in old.legs}
        new_legs = {self._leg_key(leg): leg for leg in self.legs}
        for key in sorted(old_legs.keys() - new_legs.keys(), key=_leg_sort_key):
            items.append({"kind": "leg_removed", "leg": _leg_data(old_legs[key])})
        for key in sorted(new_legs.keys() - old_legs.keys(), key=_leg_sort_key):
            items.append({"kind": "leg_added", "leg": _leg_data(new_legs[key])})
        for key in sorted(old_legs.keys() & new_legs.keys(), key=_leg_sort_key):
            before, after = old_legs[key].quantity, new_legs[key].quantity
            if before != after:
                items.append({"kind": "quantity", "leg": _leg_data(new_legs[key]), "before": before})
        if old.rules_ref != self.rules_ref:
            items.append({"kind": "field", "map": "rules_ref", "name": "rules_ref", "old": old.rules_ref,
                          "new": self.rules_ref})
        for label in ("risk_limits", "preferences"):
            before, after = dict(getattr(old, label)), dict(getattr(self, label))
            for name in sorted(before.keys() | after.keys()):
                if before.get(name) != after.get(name):
                    items.append({"kind": "field", "map": label, "name": name,
                                  "old": None if name not in before else str(before[name]),
                                  "new": None if name not in after else str(after[name])})
        return tuple(items)

    @staticmethod
    def _leg_key(leg: DefinitionLeg) -> tuple:
        return (leg.action, leg.instrument, leg.strike, leg.expiry)


def _leg_data(leg: DefinitionLeg) -> dict:
    return {"action": leg.action.value, "instrument": leg.instrument.value,
            "strike": None if leg.strike is None else str(leg.strike), "expiry": leg.expiry.isoformat(),
            "quantity": leg.quantity}


_LEG_KEYS = frozenset({"action", "instrument", "strike", "expiry", "quantity"})
#: kind -> its exact keys. A closed shape: anything else is refused, never rendered.
_ITEM_KEYS = {"underlying": {"kind", "old", "new"}, "leg_removed": {"kind", "leg"}, "leg_added": {"kind", "leg"},
              "quantity": {"kind", "leg", "before"}, "field": {"kind", "map", "name", "old", "new"},
              "legs_reordered": {"kind"}, "replaced_unreadable": {"kind"}, "restored": {"kind", "seq"}}
#: A field change item: ``map`` -> the closed list of ``name`` (ADR-064); ``old``/``new`` are None (absent) or ADR-069's
#: value type (a plain-digit number for a risk limit, an identifier otherwise). One item per changed name; never repr.
_FIELD_NAMES = {"rules_ref": frozenset({"rules_ref"}), "risk_limits": RISK_LIMIT_NAMES, "preferences": PREFERENCE_NAMES}


def _field_value(map_name: str, value: object):
    if value is None:
        return render_explanation("change_value_unset")
    if map_name == "risk_limits":
        if type(value) is not str or re.fullmatch(settings_value.LIMIT_PATTERN, value) is None:
            raise DefinitionError(detail="a change item's risk limit is not a plain number")
        return value
    return settings_value.identifier(value, "change_item")


def _field_text(item: dict):
    map_name, name = item["map"], item["name"]
    if (not isinstance(map_name, str) or map_name not in _FIELD_NAMES or not isinstance(name, str)
            or name not in _FIELD_NAMES[map_name]):
        raise DefinitionError(detail="a change item names an unknown field")
    old, new = _field_value(map_name, item["old"]), _field_value(map_name, item["new"])
    if map_name == "rules_ref":
        return render_explanation("change_rules_ref", old=old, new=new)
    return render_explanation("change_field", map=map_name, name=name, old=old, new=new)


#: The database's own predicates for a leg slot (migration 0008's ofo_strategy_leg_valid): the domain refuses exactly
#: what the database refuses, so a summary that renders here is one the database stores.
_DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MAX_SEQ = 2**31 - 1  # strategy_history.seq (INTEGER)


def _closed_member(enum: type, value: object):
    """The enum member for ``value`` when it is a string spelled exactly like a member; else DefinitionError."""
    if type(value) is not str or value not in {m.value for m in enum}:
        raise DefinitionError(detail="a change item slot is not one of its allowed values")
    return enum(value)


def _positive_units(value: object) -> int:
    if not _is_int(value) or not 0 < value <= MAX_UNITS:
        raise DefinitionError(detail="a change item's quantity is not a whole number of units")
    return value  # type: ignore[return-value]


def _leg_text(leg: object):
    if not isinstance(leg, dict) or set(leg) != _LEG_KEYS:
        raise DefinitionError(detail="a change item's leg is not in the closed shape")
    action = _closed_member(Action, leg["action"])
    instrument = _closed_member(Instrument, leg["instrument"])
    strike = leg["strike"]
    if instrument is Instrument.FUT:
        if strike is not None:
            raise DefinitionError(detail="a change item's futures leg has a strike")
        strike_value = None
    else:
        if type(strike) is not str or _STRIKE_TEXT.fullmatch(strike) is None or Decimal(strike) <= 0:
            raise DefinitionError(detail="a change item's strike is not a plain positive decimal")
        strike_value = Decimal(strike)
    expiry = leg["expiry"]
    if type(expiry) is not str or _DATE_TEXT.fullmatch(expiry) is None or datetime.date.fromisoformat(expiry).isoformat() != expiry:
        raise DefinitionError(detail="a change item's expiry is not an ISO date")
    return render_explanation(
        "leg_description", action=action.value, strike=strike_text(strike_value), instrument=instrument.value,
        expiry=expiry, quantity=_positive_units(leg["quantity"]))


def _underlying_slot(value: object) -> str:
    if type(value) is not str or value not in SUPPORTED_UNDERLYINGS:
        raise DefinitionError(detail="a change item's underlying is not a supported underlying")
    return value


def render_change_items(items: object) -> tuple:
    """Catalogue text (``render_explanation`` results) for STORED change items; DefinitionError on any shape or value
    that does not validate (an unknown kind, an extra key, a slot of the wrong type) and on a count outside the stored
    1..MAX_CHANGE_ITEMS (the database's rule). Used on write and on read."""
    if not isinstance(items, (list, tuple)):
        raise DefinitionError(detail="change items must be a list")
    if not 1 <= len(items) <= MAX_CHANGE_ITEMS:
        raise DefinitionError(detail=f"a summary holds 1..{MAX_CHANGE_ITEMS} change items")
    return _render_items(items)


def _render_items(items: object) -> tuple:
    """The rendering without the stored count bound: ``changes_from`` has no items when nothing meaningful changed."""
    if not isinstance(items, (list, tuple)):
        raise DefinitionError(detail="change items must be a list")
    out = []
    try:
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in _ITEM_KEYS or set(item) != _ITEM_KEYS[item["kind"]]:
                raise DefinitionError(detail="a change item is not in the closed shape")
            kind = item["kind"]
            if kind == "underlying":
                out.append(render_explanation("change_underlying", old=_underlying_slot(item["old"]),
                                              new=_underlying_slot(item["new"])))
            elif kind == "leg_removed":
                out.append(render_explanation("change_leg_removed", leg=_leg_text(item["leg"])))
            elif kind == "leg_added":
                out.append(render_explanation("change_leg_added", leg=_leg_text(item["leg"])))
            elif kind == "quantity":
                out.append(render_explanation("change_quantity", leg=_leg_text(item["leg"]),
                                              before=_positive_units(item["before"])))
            elif kind == "field":
                out.append(_field_text(item))
            elif kind == "restored":
                seq = item["seq"]
                if not _is_int(seq) or not 0 < seq <= MAX_SEQ:
                    raise DefinitionError(detail="a change item's seq is not a history sequence number")
                out.append(render_explanation("change_restored", seq=seq))
            elif kind == "legs_reordered":
                out.append(render_explanation("change_legs_reordered"))
            else:
                out.append(render_explanation("change_replaced_unreadable"))
    except DefinitionError:
        raise
    except (TypeError, ValueError, KeyError, ArithmeticError) as exc:  # a slot that does not validate
        raise DefinitionError(detail=f"a change item does not validate: {type(exc).__name__}") from None
    return tuple(out)


def _leg_sort_key(key: tuple) -> tuple:
    action, instrument, strike, expiry = key
    return (action.value, instrument.value, strike if strike is not None else Decimal(0), expiry)
