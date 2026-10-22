"""The broker's named flags (REQ-117 "broker capability flags", W-132; ADR-016 Zerodha is the authority).

A feature asks a flag by name; it never compares a broker's name or id. The set of flags is closed (``BrokerFlag``).
Each declared value carries on/off, the source it rests on and the date (``datetime.date``) it was checked.

Named ``flags`` and not "capabilities" on purpose: ``tests/execution/test_strategy_only.py`` refuses any public name
in ``ofo`` that says "capabilit" (a different idea there: a capability that mints a sealed object).

Answer states (standing item d: the flags are our own declared data, no other system's answer is read here):
- name is one of the seven and the loaded set declares it on  -> supported;
- declared off                                                 -> not supported;
- name missing from the set, not one of the seven, not a str   -> not supported (never raises);
- the object asked is not a ``FlagSet`` (None, a dict)         -> not supported for every name;
- the declared data is malformed, has an unknown key, or an entry lacks a bool, a source or a date
                                                               -> ``FlagLoadError``; ``flags_or_off`` gives an
                                                                  all-off set, never a half-loaded one.
Flags never loosen a safety gate (REQ-117 AC-5): the margin, reconciliation, market-hours, kill-switch and
freeze-limit checks do not import this module (``tests/execution/test_gates_import_no_flags.py``).
The text a user sees when a feature is hidden is not here: it is the frontend's reviewed text for a hidden feature.
"""
from __future__ import annotations

import datetime
import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


class BrokerFlag(enum.StrEnum):
    """The closed set of flags (REQ-117 AC-1). Adding a flag is a deliberate edit of this enum and its test."""

    BASKET_PAGE_ORDERS = "basket_page_orders"
    BROKER_HELD_TRIGGERS = "broker_held_triggers"
    INTRADAY_PRODUCT = "intraday_product"
    ORDER_UPDATE_STREAM = "order_update_stream"
    FUNDS_READ = "funds_read"
    POSITIONS_READ = "positions_read"
    BASKET_MARGIN_QUOTE = "basket_margin_quote"


FLAG_NAMES: Final = frozenset(f.value for f in BrokerFlag)


class FlagLoadError(ValueError):
    """The declared flag data cannot be trusted; the whole set is refused."""


@dataclass(frozen=True)
class FlagValue:
    supported: bool
    source: str
    as_of: datetime.date

    def __post_init__(self) -> None:
        if type(self.supported) is not bool:
            raise FlagLoadError("a flag is on or off (a bool)")
        if not isinstance(self.source, str) or not self.source.strip():
            raise FlagLoadError("a flag needs the source it rests on")
        if type(self.as_of) is not datetime.date:
            raise FlagLoadError("a flag needs the date (datetime.date) its source was checked")


@dataclass(frozen=True)
class FlagSet:
    """The flags a broker implementation declares. Missing flags are simply not in ``flags`` (and so are off)."""

    flags: Mapping[str, FlagValue]

    def __post_init__(self) -> None:
        if not isinstance(self.flags, Mapping):
            raise FlagLoadError("flags must be a mapping")
        checked = {}
        for name, value in self.flags.items():
            if name not in FLAG_NAMES or not isinstance(value, FlagValue):
                raise FlagLoadError("flags hold only the seven named flags, each a FlagValue")
            checked[name] = value
        object.__setattr__(self, "flags", MappingProxyType(checked))

    def value(self, name: str) -> FlagValue | None:
        return self.flags.get(name) if isinstance(name, str) else None


def load_flags(raw: Mapping[str, tuple[bool, str, datetime.date]]) -> FlagSet:
    """Build a set from declared ``{name: (on, source, date)}``. An unknown or misspelled key, a wrong shape or an
    entry lacking its bool, source or date refuses the whole load (never ignored, never half-loaded)."""
    if not isinstance(raw, Mapping):
        raise FlagLoadError("the declared flags must be a mapping")
    built = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or name not in FLAG_NAMES:
            raise FlagLoadError("an unknown flag name in the declared data")
        if type(entry) is not tuple or len(entry) != 3:
            raise FlagLoadError(f"flag {name}: expected (on, source, date)")
        built[name] = FlagValue(*entry)
    return FlagSet(built)


def flags_or_off(loader: Callable[[], FlagSet]) -> FlagSet:
    """Run ``loader``; anything but a ``FlagSet`` back, or any exception, gives the empty set (every flag off)."""
    try:
        loaded = loader()
    except Exception:  # noqa: BLE001 - fail closed: whatever went wrong, no flag is on
        return FlagSet({})
    return loaded if type(loaded) is FlagSet else FlagSet({})


def is_supported(flags: object, name: object) -> bool:
    """True only when ``flags`` is a loaded ``FlagSet`` that declares ``name`` on. Never raises."""
    if type(flags) is not FlagSet or not isinstance(name, str):
        return False
    value = flags.value(str(name))
    return value is not None and value.supported is True


__all__ = ["FLAG_NAMES", "BrokerFlag", "FlagLoadError", "FlagSet", "FlagValue", "flags_or_off", "is_supported",
           "load_flags"]
