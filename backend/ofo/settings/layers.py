"""The three-layer settings resolver: the value in force for a strategy and where it came from (ADR-245).

Spec basis: ADR-245 "The value in force is the strategy's, else the user's, else the admin default, and every flag,
alert line and Compare cell names the value it used." ADR-243 is the first case (roll basis); GC "Your adjustment
settings" step 1 wires the carry gap (``other.carry_gap_percent``) through here; step 3 moves the rest.

Layers, read in this order:
- strategy: the strategy's plan copy (REQ-161), its ``settings`` container ``{key: "decimal string"}``;
- user: the user's OWN values (``user_preferences_store`` rows whose source is "yours", never a merged mapping);
- admin: the settings in force (``settings_store.settings_in_force`` / the registry default).

Answer states of each layer read (one test each in ``tests/settings/test_layers.py``):
- ``None``: the layer does not exist (no plan, no user value read path) -> the next layer;
- a mapping WITHOUT the key, or the strategy's ``settings`` container absent / empty -> the next layer;
- a mapping WITH the key and a value the registry accepts -> that value, with its source;
- a value the registry refuses (out of range, wrong type, "", a float, a bool) -> :class:`LayerUnreadable`;
- :class:`Unreadable` (the layer exists but could not be read: a failed read, a ``settings`` that is not an object)
  -> :class:`LayerUnreadable`.
A layer that exists but cannot be read is NEVER skipped to the next one: the caller shows no figure and the named
reason (fail closed). Admin-only keys (speeds, detection.feed_*, facts, data, limits, billing, pricing, scenarios) are
not three-layer keys and are refused here. Standard library and Decimal only.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from ofo.settings import SettingRefused, check_value, setting

SOURCE_STRATEGY: Final = "strategy"  # a code; the words are rendered by the screen (render())
SOURCE_USER: Final = "user"
SOURCE_DEFAULT: Final = "default"

#: reason codes of a layer that exists but cannot be read (fail closed)
STRATEGY_UNREADABLE: Final = "setting_strategy_unreadable"
USER_UNREADABLE: Final = "setting_user_unreadable"
DEFAULT_UNREADABLE: Final = "setting_default_unreadable"

#: the plan body's container of strategy overrides (``docs/design/playbook-body-v1.md`` "settings")
PLAN_SETTINGS: Final = "settings"

CARRY_GAP_PERCENT: Final = "other.carry_gap_percent"
#: the keys resolved through three layers so far (GC step 1: the carry gap; step 3 adds the rest of ADR-245's list)
ROLL_BASIS: Final = "adjustments.roll_basis"  # ADR-243: 1 target delta / 2 entry distance from spot
THREE_LAYER_KEYS: Final = (CARRY_GAP_PERCENT, ROLL_BASIS)
#: Step 3 (ADR-245): the registry groups whose keys the resolver reads (admin default -> user -> strategy). A plan may
#: WRITE only ``THREE_LAYER_KEYS`` (``check_plan_settings``); the rest resolve from the user's and the admin's layers.
#: ``orders.*`` are two-layer (admin default -> user): a plan never writes them. Every other prefix (speeds,
#: detection, facts, data, limits, billing, pricing, scenarios, other.undo_*) is admin-only and refused here.
LAYERED_PREFIXES: Final = ("adjustments.", "alerts.", "orders.")
TWO_LAYER_PREFIXES: Final = ("orders.",)
LAYERED_OTHER: Final = (CARRY_GAP_PERCENT, "other.situation_net_delta_per_lot", "other.situation_big_win_percent")


def is_layered(key: object) -> bool:
    """True for a key the resolver answers (a registry key in ADR-245's list); False for an admin-only key."""
    if not isinstance(key, str):
        return False
    from ofo.settings import registry  # noqa: PLC0415 - the checked-in registry, loaded once

    if key not in registry():
        return False
    return key in THREE_LAYER_KEYS or key in LAYERED_OTHER or key.startswith(LAYERED_PREFIXES)


@dataclass(frozen=True)
class Unreadable:
    """A layer that exists but could not be read; ``detail`` says why (logs only, never shown as a value)."""

    detail: str  # a log code, never shown


Layer = Mapping[str, object] | Unreadable | None


@dataclass(frozen=True)
class InForce:
    key: str
    value: Decimal
    source: str  # SOURCE_STRATEGY / SOURCE_USER / SOURCE_DEFAULT (codes, never shown as typed)


class LayerUnreadable(ValueError):
    """A layer exists for the key but cannot be read; ``code`` names the layer (fail closed, never a default)."""

    def __init__(self, key: str, code: str, detail: str) -> None:
        super().__init__(key, code, detail)  # log args, never shown text
        self.key = key
        self.code = code
        self.detail = detail


def _parse(key: str, raw: object) -> Decimal:
    """A stored layer value as the registry accepts it: a Decimal, or a decimal STRING (the plan body's JSON form).
    A float, bool, int, "" or anything else is refused (SettingRefused / ValueError)."""
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            value = Decimal(raw.strip())
        except InvalidOperation:
            raise ValueError(f"not a decimal: {raw!r}") from None
    else:
        raise ValueError(f"not a decimal string: {raw!r}")
    return check_value(setting(key), value)


def _read(key: str, layer: Layer, code: str) -> Decimal | None:
    if layer is None:
        return None
    if isinstance(layer, Unreadable):
        raise LayerUnreadable(key, code, layer.detail)
    if not isinstance(layer, Mapping):
        raise LayerUnreadable(key, code, f"layer is not a mapping: {type(layer).__name__}")
    if key not in layer:
        return None
    try:
        return _parse(key, layer[key])
    except (SettingRefused, ValueError) as exc:
        raise LayerUnreadable(key, code, str(exc)) from None


def resolve(key: str, admin: Layer, user: Layer, strategy: Layer) -> InForce:
    """The value in force for ``key``: the strategy's, else the user's, else the admin default (ADR-245). A missing
    admin value is a defect (the admin layer always holds every registry key): LayerUnreadable, never a typed one."""
    if not is_layered(key):
        raise KeyError(f"{key} is not a three-layer setting")
    # two-layer keys (orders.*): the strategy layer is never read, whatever a plan body holds
    found = None if key.startswith(TWO_LAYER_PREFIXES) else _read(key, strategy, STRATEGY_UNREADABLE)
    if found is not None:
        return InForce(key, found, SOURCE_STRATEGY)
    found = _read(key, user, USER_UNREADABLE)
    if found is not None:
        return InForce(key, found, SOURCE_USER)
    found = _read(key, admin, DEFAULT_UNREADABLE)
    if found is None:
        raise LayerUnreadable(key, DEFAULT_UNREADABLE, "the admin default was not read")
    return InForce(key, found, SOURCE_DEFAULT)


def strategy_layer(plan_body: object) -> Layer:
    """The strategy layer of a plan copy's body: its ``settings`` object (absent -> empty: every key follows the
    user); a ``settings`` that is not an object -> Unreadable. ``None`` (the strategy has no plan) -> None."""
    if plan_body is None:
        return None
    if not isinstance(plan_body, Mapping):
        return Unreadable("plan_body_not_object")
    found = plan_body.get(PLAN_SETTINGS, {})
    if not isinstance(found, Mapping):
        return Unreadable("plan_settings_not_object")
    return found


def check_plan_settings(found: object) -> dict[str, str]:
    """The write check of a plan body's ``settings``: an object of known three-layer keys, each a decimal string the
    registry accepts (ValueError naming the key otherwise). Returns it unchanged."""
    if not isinstance(found, Mapping):
        raise ValueError(f"{PLAN_SETTINGS} must be an object")
    for key, raw in found.items():
        if key not in THREE_LAYER_KEYS:
            raise ValueError(f"{PLAN_SETTINGS}.{key} is not a setting a strategy can change")
        if not isinstance(raw, str):
            raise ValueError(f"{PLAN_SETTINGS}.{key} must be a decimal string")
        try:
            _parse(key, raw)
        except (SettingRefused, ValueError):
            raise ValueError(f"{PLAN_SETTINGS}.{key} is refused by the registry: {raw!r}") from None
    return dict(found)


__all__ = ["CARRY_GAP_PERCENT", "DEFAULT_UNREADABLE", "LAYERED_OTHER", "LAYERED_PREFIXES", "PLAN_SETTINGS",
           "ROLL_BASIS", "is_layered",
           "SOURCE_DEFAULT", "SOURCE_STRATEGY",
           "SOURCE_USER", "STRATEGY_UNREADABLE", "THREE_LAYER_KEYS", "USER_UNREADABLE", "InForce", "Layer",
           "LayerUnreadable", "Unreadable", "check_plan_settings", "resolve", "strategy_layer"]
