"""The settings registry: every business number a calculation uses, with its default (REQ-167 AC-1, ADR-222).

Spec basis: ADR-222 (1) "No rupee amount, rate, percentage or threshold that changes a figure a user sees is typed in
code. Each is a setting with a default value, the date it was set and who set it."; REQ-167 AC-1 (key, group, label,
unit, type, allowed range, default, "what it changes"); AC-2 ("a value outside the allowed range or of the wrong unit
is refused with the reason (e.g. 6.5 typed for a rate whose unit is a fraction: 'Enter 0.065 for 6.5%')").

The registry is DATA (``registry.json``), the one closed list of keys: the store refuses any key not in it, and a
stored row for a key it no longer holds is ignored. Defaults and bounds are decimal STRINGS; a JSON float anywhere in
the file is refused at load. Standard library and Decimal only; no clock is read here.

``value_of(values, key)`` is the one way a calculation reads a setting from a mapping the app layer built with
``settings_in_force``; a missing key is a programming error (KeyError), never a silent default.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Final

DATA_FILE: Final = Path(__file__).with_name("registry.json")
UNITS: Final = ("fraction", "percent", "rupees", "points", "seconds", "count", "time", "days")
TYPES: Final = ("decimal", "integer")
MAX_TEXT: Final = 40  # the longest value text accepted from a form (a Decimal string)

#: App-wide admin settings only (owner 2026-10-31): per-user adjustment preferences (near-level distance, cost per
#: leg) are a separate per-user build on the Adjustments screen, never in this registry.
RISK_FREE_RATE: Final = "pricing.risk_free_rate"


class RegistryError(ValueError):
    """The registry file is malformed (load refuses it whole)."""


class SettingRefused(ValueError):
    """A value or key the registry refuses; ``reason`` is the readable text the Settings page shows."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class Setting:
    key: str
    group: str
    label: str
    unit: str
    type: str
    min: Decimal
    max: Decimal
    default: Decimal
    what_it_changes: str
    source: str


def _no_float(text: str) -> Decimal:
    raise RegistryError(f"registry.json holds a float ({text}); settings values are decimal strings")


def _dec(raw: object, where: str) -> Decimal:
    if not isinstance(raw, str):
        raise RegistryError(f"{where} must be a decimal string, got {raw!r}")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise RegistryError(f"{where} is not a decimal: {raw!r}") from None
    if not value.is_finite():
        raise RegistryError(f"{where} must be finite, got {raw!r}")
    return value


ENTRY_FIELDS = frozenset(("key", "group", "label", "unit", "type", "min", "max", "default", "what_it_changes",
                          "source"))
FILE_FIELDS = frozenset(("schema", "settings"))


def _no_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """json's object_pairs_hook: a repeated field name in one object is refused (the stdlib keeps the last one)."""
    seen: dict[str, object] = {}
    for name, value in pairs:
        if name in seen:
            raise RegistryError(f"registry.json repeats the field {name!r} in one object (the last would win)")
        seen[name] = value
    return seen


def _no_unknown_fields(obj: dict, allowed: frozenset[str], where: str) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise RegistryError(f"{where} has unknown field(s) {extra} (a misspelt field would be silently ignored)")


def parse_registry(text: str) -> dict[str, Setting]:
    """Parse and check the whole file; any defect refuses it (no partial registry), including a repeated field name
    and a field this loader does not read."""
    data = json.loads(text, parse_float=_no_float, parse_constant=_no_float, object_pairs_hook=_no_duplicate_fields)
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("settings"), list):
        raise RegistryError("registry.json must be {\"schema\": 1, \"settings\": [...]}")
    _no_unknown_fields(data, FILE_FIELDS, "registry.json")
    out: dict[str, Setting] = {}
    for row in data["settings"]:
        if not isinstance(row, dict):
            raise RegistryError("every registry entry is an object")
        _no_unknown_fields(row, ENTRY_FIELDS, f"registry entry {row.get('key')!r}")
        key = row.get("key")
        if not isinstance(key, str) or not key or key in out:
            raise RegistryError(f"registry key missing or duplicated: {key!r}")
        texts = {f: row.get(f) for f in ("group", "label", "unit", "type", "what_it_changes", "source")}
        if not all(isinstance(v, str) and v.strip() for v in texts.values()):
            raise RegistryError(f"{key}: group, label, unit, type, what_it_changes and source are required text")
        if texts["unit"] not in UNITS or texts["type"] not in TYPES:
            raise RegistryError(f"{key}: unknown unit {texts['unit']!r} or type {texts['type']!r}")
        low, high, default = (_dec(row.get(f), f"{key}.{f}") for f in ("min", "max", "default"))
        setting = Setting(key, texts["group"], texts["label"], texts["unit"], texts["type"], low, high, default,
                          texts["what_it_changes"], texts["source"])
        try:
            if low > high or check_value(setting, default) != default:
                raise SettingRefused("setting_out_of_range", "bounds reversed")
        except SettingRefused:
            raise RegistryError(f"{key}: the default {default} is outside [{low}, {high}] or not of its type") from None
        out[key] = setting
    return out


@lru_cache(maxsize=1)
def registry() -> Mapping[str, Setting]:
    """The checked-in registry, loaded once (the file is code-reviewed data, not an admin input)."""
    return parse_registry(DATA_FILE.read_text(encoding="utf-8"))


def setting(key: object) -> Setting:
    if not isinstance(key, str) or key not in registry():
        raise SettingRefused("setting_unknown", f"There is no setting named {key!r}.")
    return registry()[key]


def defaults() -> dict[str, Decimal]:
    return {k: s.default for k, s in registry().items()}


def plain(value: Decimal) -> str:
    """A Decimal as plain text, no exponent and no trailing zeros (0.0650 -> 0.065)."""
    return format(value.normalize(), "f")


def check_value(s: Setting, value: Decimal) -> Decimal:
    """Range and type check of an already-parsed Decimal; returns the value or raises SettingRefused."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise SettingRefused("setting_not_a_number", f"{s.label} must be a number.")
    if s.type == "integer" and value != value.to_integral_value():
        raise SettingRefused("setting_not_whole", f"{s.label} must be a whole number.")
    if value < s.min or value > s.max:
        as_fraction = value.scaleb(-2)  # exact percent -> fraction (no division: not money arithmetic)
        if s.unit == "fraction" and s.min <= as_fraction <= s.max:
            raise SettingRefused("setting_fraction_unit",
                                 f"{s.label} is a fraction: enter {plain(as_fraction)} for {plain(value)}%.")
        raise SettingRefused("setting_out_of_range",
                             f"{s.label} must be between {plain(s.min)} and {plain(s.max)} ({s.unit}).")
    return value


def validate(key: object, raw: object) -> Decimal:
    """The admin write's check: a known key and a decimal STRING in range (a JSON number, a bool, NaN, Infinity or
    an empty text is refused, never coerced)."""
    s = setting(key)
    if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_TEXT:
        raise SettingRefused("setting_not_a_number", f"{s.label} must be a number written as text, e.g. "
                                                     f"{plain(s.default)}.")
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        raise SettingRefused("setting_not_a_number", f"{s.label} must be a number, e.g. {plain(s.default)}.") from None
    return check_value(s, value)


def value_of(values: Mapping[str, Decimal], key: str) -> Decimal:
    """The one read of a setting by a calculation (AC-6's guard test looks for these reads per key)."""
    if key not in registry():
        raise KeyError(f"not a registry key: {key}")
    value = values[key]
    if not isinstance(value, Decimal):
        raise TypeError(f"setting {key} is not a Decimal: {value!r}")
    return value
