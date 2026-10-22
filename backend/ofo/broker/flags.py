"""The broker's named capability flags (REQ-117, W-132; ADR-016 Zerodha is the authority).

A feature asks a flag by name; it never compares a broker's name or id. The set of flags is closed (``Capability``).
Each declared value carries on/off, the source it rests on and the date (``datetime.date``) it was checked.

Answer states (standing item d: the flags are our own declared data, no other system's answer is read here):
- name is one of the seven and the loaded set declares it on  -> supported;
- declared off                                                 -> not supported;
- name missing from the set, not one of the seven, not a str   -> not supported (never raises);
- the object asked is not a ``CapabilitySet`` (None, a dict)   -> not supported for every name;
- the declared data is malformed, has an unknown key, or an entry lacks a bool, a source or a date
                                                               -> ``CapabilityLoadError``; ``load_or_off`` gives an
                                                                  all-off set, never a half-loaded one.
Flags never loosen a safety gate (REQ-117 AC-5): the margin, reconciliation, market-hours, kill-switch and
freeze-limit checks do not import this module (``tests/execution/test_flags_never_loosen_gates.py``).
"""
from __future__ import annotations

import datetime
import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


class Capability(enum.StrEnum):
    """The closed set of flags (REQ-117 AC-1). Adding a flag is a deliberate edit of this enum and its test."""

    BASKET_PAGE_ORDERS = "basket_page_orders"
    BROKER_HELD_TRIGGERS = "broker_held_triggers"
    INTRADAY_PRODUCT = "intraday_product"
    ORDER_UPDATE_STREAM = "order_update_stream"
    FUNDS_READ = "funds_read"
    POSITIONS_READ = "positions_read"
    BASKET_MARGIN_QUOTE = "basket_margin_quote"


CAPABILITY_NAMES: Final = frozenset(c.value for c in Capability)
#: Shown where the margin line would be when ``basket_margin_quote`` is not on. Plain words; names no broker.
MARGIN_LINE_HIDDEN_REASON: Final = "Margin from the broker is not available for this account."


class CapabilityLoadError(ValueError):
    """The declared flag data cannot be trusted; the whole set is refused."""


@dataclass(frozen=True)
class CapabilityValue:
    supported: bool
    source: str
    as_of: datetime.date

    def __post_init__(self) -> None:
        if type(self.supported) is not bool:
            raise CapabilityLoadError("a flag is on or off (a bool)")
        if not isinstance(self.source, str) or not self.source.strip():
            raise CapabilityLoadError("a flag needs the source it rests on")
        if type(self.as_of) is not datetime.date:
            raise CapabilityLoadError("a flag needs the date (datetime.date) its source was checked")


@dataclass(frozen=True)
class CapabilitySet:
    """The flags a broker implementation declares. Missing flags are simply not in ``flags`` (and so are off)."""

    flags: Mapping[str, CapabilityValue]

    def __post_init__(self) -> None:
        if not isinstance(self.flags, Mapping):
            raise CapabilityLoadError("flags must be a mapping")
        checked = {}
        for name, value in self.flags.items():
            if name not in CAPABILITY_NAMES or not isinstance(value, CapabilityValue):
                raise CapabilityLoadError("flags hold only the seven named flags, each a CapabilityValue")
            checked[name] = value
        object.__setattr__(self, "flags", MappingProxyType(checked))

    def value(self, name: str) -> CapabilityValue | None:
        return self.flags.get(name) if isinstance(name, str) else None


def load_capabilities(raw: Mapping[str, tuple[bool, str, datetime.date]]) -> CapabilitySet:
    """Build a set from declared ``{name: (on, source, date)}``. An unknown or misspelled key, a wrong shape or an
    entry lacking its bool, source or date refuses the whole load (never ignored, never half-loaded)."""
    if not isinstance(raw, Mapping):
        raise CapabilityLoadError("the declared flags must be a mapping")
    built = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or name not in CAPABILITY_NAMES:
            raise CapabilityLoadError("an unknown flag name in the declared data")
        if type(entry) is not tuple or len(entry) != 3:
            raise CapabilityLoadError(f"flag {name}: expected (on, source, date)")
        built[name] = CapabilityValue(*entry)
    return CapabilitySet(built)


def load_or_off(loader: Callable[[], CapabilitySet]) -> CapabilitySet:
    """Run ``loader``; anything but a ``CapabilitySet`` back, or any exception, gives the empty set (every flag off)."""
    try:
        loaded = loader()
    except Exception:  # noqa: BLE001 - fail closed: whatever went wrong, no flag is on
        return CapabilitySet({})
    return loaded if type(loaded) is CapabilitySet else CapabilitySet({})


def is_supported(flags: object, name: object) -> bool:
    """True only when ``flags`` is a loaded ``CapabilitySet`` that declares ``name`` on. Never raises."""
    if type(flags) is not CapabilitySet or not isinstance(name, str):
        return False
    value = flags.value(str(name))
    return value is not None and value.supported is True


@dataclass(frozen=True)
class FeatureState:
    visible: bool
    reason: str | None


def feature_state(flags: object, needs: object, hidden_reason: str) -> FeatureState:
    """The state of a feature that needs the flag ``needs``: visible, or hidden with its plain ``hidden_reason``
    (a sentence that names no broker). A missing, unknown or unloadable flag hides it."""
    if is_supported(flags, needs):
        return FeatureState(True, None)
    return FeatureState(False, hidden_reason)


__all__ = ["CAPABILITY_NAMES", "MARGIN_LINE_HIDDEN_REASON", "Capability", "CapabilityLoadError", "CapabilitySet",
           "CapabilityValue", "FeatureState", "feature_state", "is_supported", "load_capabilities", "load_or_off"]
