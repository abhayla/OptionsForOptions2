"""The ONE read of a strategy's adjustment settings in force (goal contract "Your adjustment settings" step 3, ADR-245).

Spec basis: ADR-245 "The value in force is the strategy's, else the user's, else the admin default, and every flag,
alert line and Compare cell names the value it used"; ADR-247 (the iron condor default stop: 50 % of max loss or 2x the
credit received, whichever comes first; % of margin OFF by default); ADR-008 (one engine owns every rupee figure).

``in_force`` is the single place a route reads, for one strategy:
- ``settings``: every covered key (``covered_keys``: the user's preference keys, i.e. ``adjustments.*``, the
  user-changeable ``alerts.<style>.*``, the three-layer ``other.*`` keys and ``orders.*``) with its value and source
  through ``ofo.settings.layers.resolve`` (the strategy layer is the PLAN copy only, ``Resolved.strategy_layer``);
- ``triggers``: the playbook in force's trigger values with the source of that playbook (plan -> strategy, the user's
  own active copy -> user, the system playbook -> default);
- ``stops``: the ADR-247 stop lines with their amounts from the engine (``adjust_money.stop_at_pct`` /
  ``stop_at_multiple`` over ``price_after``'s gross max loss and the open legs' entry credit) and which fires first.

A repo-scan test (``tests_app/test_settings_in_force_scan.py``) fails when a route reads a covered value any other way.

Answer states (each with its reply; never a default when a layer exists but cannot be read):
- a layer present with the key -> that value and its source; absent / no key -> the next layer;
- a layer that exists but is unreadable (or a refused stored value) -> value None, source None, ``reason`` the
  layer's code (``layers.STRATEGY_UNREADABLE`` / ``USER_UNREADABLE`` / ``DEFAULT_UNREADABLE``);
- no playbook (Custom or an unmapped shape) -> no triggers, ``triggers_reason`` ``NO_PLAYBOOK``; stops with
  ``NO_PLAYBOOK``;
- a playbook whose ``triggers`` is not an object -> no triggers, ``TRIGGERS_UNREADABLE``; one trigger whose values
  are not decimal strings -> that trigger's values None and ``TRIGGER_UNREADABLE`` (the others still shown);
- a stop input missing (booked P&L unread, several expiries, max loss unlimited, no credit received, the margin not
  read here) -> that stop's amount None with its named reason; ``first`` None with ``FIRST_UNKNOWN`` when any active
  stop has no amount (which fires first cannot be told).
Codes only: the words are rendered by the screen / the catalogue.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from ofo.engine import adjust_money
from ofo.engine.metrics import UNLIMITED
from ofo.settings import layers

from ofo_app import adjustment_check as check
from ofo_app import user_preferences_store as store

#: playbook source (``Resolved.source``) -> the resolver's source code
PLAYBOOK_SOURCE: Final = {"plan": layers.SOURCE_STRATEGY, "active": layers.SOURCE_USER,
                          "system": layers.SOURCE_DEFAULT}

NO_PLAYBOOK: Final = "settings_no_playbook"
TRIGGERS_UNREADABLE: Final = "settings_triggers_unreadable"
TRIGGER_UNREADABLE: Final = "settings_trigger_unreadable"
GUARDS_UNREADABLE: Final = "stop_guards_unreadable"
STOP_VALUE_UNREADABLE: Final = "stop_value_unreadable"
MAX_LOSS_UNKNOWN: Final = "stop_max_loss_unknown"
MAX_LOSS_UNLIMITED: Final = "stop_max_loss_unlimited"
NO_CREDIT: Final = "stop_no_credit_received"
CREDIT_UNKNOWN: Final = "stop_credit_unknown"
MARGIN_NOT_READ: Final = "stop_margin_not_read"
FIRST_UNKNOWN: Final = "stop_first_unknown"
NO_ACTIVE_STOP: Final = "stop_none_active"

#: the plan copy's guards (docs/design/playbook-body-v1.md "guards")
STOP_PCT_KEY: Final = "stop_line_pct_of_max_loss"
STOP_CREDIT_KEY: Final = "stop_line_x_credit"
STOP_MARGIN_KEY: Final = "stop_line_pct_of_margin"
#: ADR-247: the "2x the credit received" stop is ALWAYS active; a body that does not state its multiple follows this
#: default (source "default"); a strategy or a user changes it by writing ``stop_line_x_credit`` into their copy
CREDIT_MULTIPLE_DEFAULT: Final = Decimal(2)

STOP_MAX_LOSS: Final = "max_loss_pct"
STOP_CREDIT: Final = "credit_multiple"
STOP_MARGIN: Final = "margin_pct"


@dataclasses.dataclass(frozen=True)
class SettingInForce:
    key: str
    value: Decimal | None
    source: str | None
    reason: str | None


@dataclasses.dataclass(frozen=True)
class TriggerInForce:
    id: str
    label: str | None
    unit: str | None
    on: bool | None
    weekly: tuple[Decimal | None, ...] | None
    monthly: tuple[Decimal | None, ...] | None
    source: str | None
    reason: str | None


@dataclasses.dataclass(frozen=True)
class StopInForce:
    kind: str  # STOP_MAX_LOSS / STOP_CREDIT / STOP_MARGIN
    active: bool
    figure: Decimal | None  # the % or the multiple in force
    amount: Decimal | None  # the loss in rupees at which it fires (engine)
    source: str | None
    reason: str | None


@dataclasses.dataclass(frozen=True)
class StopsInForce:
    lines: tuple[StopInForce, ...]
    first: str | None
    reason: str | None


@dataclasses.dataclass(frozen=True)
class InForce:
    settings: tuple[SettingInForce, ...]
    triggers: tuple[TriggerInForce, ...]
    triggers_reason: str | None
    stops: StopsInForce


def covered_keys() -> tuple[str, ...]:
    """Every key a user (and, for ``layers.THREE_LAYER_KEYS``, a strategy) can change: the preference keys."""
    return tuple(k for k in store.preference_keys() if layers.is_layered(k))


def setting_of(key: str, user_values: Mapping[str, Decimal] | None, strategy: layers.Layer) -> SettingInForce:
    admin = check.admin_of(user_values, key)
    admin_layer: layers.Layer = layers.Unreadable("not read") if admin is None else {key: admin}
    try:
        got = layers.resolve(key, admin_layer, check.user_layer(user_values), strategy)
    except layers.LayerUnreadable as exc:
        return SettingInForce(key, None, None, exc.code)
    return SettingInForce(key, got.value, got.source, None)


def settings_of(user_values: Mapping[str, Decimal] | None, strategy: layers.Layer,
                keys: Sequence[str] | None = None) -> tuple[SettingInForce, ...]:
    return tuple(setting_of(k, user_values, strategy) for k in (covered_keys() if keys is None else keys))


def _decimal_text(raw: object) -> Decimal:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"not a decimal string: {raw!r}")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"not a decimal: {raw!r}") from None
    if not value.is_finite():
        raise ValueError(f"not finite: {raw!r}")
    return value


def _values(raw: object) -> tuple[Decimal | None, ...] | None:
    """A trigger's per-stage values: null (a trigger without a threshold, e.g. a breakeven cross) -> None."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("values not a list")
    return tuple(_decimal_text(x) for x in raw)


def triggers_of(resolved: check.Resolved) -> tuple[tuple[TriggerInForce, ...], str | None]:
    body = resolved.body
    if resolved.source == "none" or body is None:
        return (), NO_PLAYBOOK
    found = body.get("triggers") if isinstance(body, Mapping) else None
    if not isinstance(found, Mapping):
        return (), TRIGGERS_UNREADABLE
    source = PLAYBOOK_SOURCE.get(resolved.source)
    out = []
    for tid, trig in found.items():
        if not isinstance(trig, Mapping):
            out.append(TriggerInForce(str(tid), None, None, None, None, None, None, TRIGGER_UNREADABLE))
            continue
        label, unit, on = trig.get("label"), trig.get("unit"), trig.get("on")
        label = label if isinstance(label, str) else None
        unit = unit if isinstance(unit, str) and unit else None
        on = on if isinstance(on, bool) else None
        try:
            weekly, monthly = _values(trig.get("weekly")), _values(trig.get("monthly"))
        except ValueError:
            out.append(TriggerInForce(str(tid), label, unit, on, None, None, None, TRIGGER_UNREADABLE))
            continue
        out.append(TriggerInForce(str(tid), label, unit, on, weekly, monthly, source, None))
    return tuple(out), None


@dataclasses.dataclass(frozen=True)
class MoneyInputs:
    """What the stop amounts are computed from: ``max_loss`` the Before's gross whole-trade max loss
    (``price_after``, as the playbook check's T-06 reads it; None = not priced, UNLIMITED = unlimited) and
    ``credit`` the open legs' entry credit (``adjust_money.trade_credit``; None = not read)."""

    max_loss: Decimal | Any | None
    credit: Decimal | None


def money_inputs(tracked: Any, market: Any, rates: Any) -> MoneyInputs:
    """The ONE engine read of the stop inputs for a tracked strategy (no market -> max loss not priced)."""
    from ofo_app.routes.adjustment import price_after  # noqa: PLC0415 - it imports this package's routes

    position = tracked.position
    credit = adjust_money.trade_credit((x.side, x.entry, x.lots * position.lot) for x in position.legs) \
        if position.legs else None
    if market is None:
        return MoneyInputs(None, credit)
    before = price_after(position.legs, position, tracked.booked, tracked.paid_charges, (), rates, market)
    gross = None if before.after is None else before.after.gross
    return MoneyInputs(None if gross is None else gross.max_loss, credit)


def _guard(guards: Mapping, key: str) -> Decimal | None:
    raw = guards.get(key)
    return None if raw is None else _decimal_text(raw)


def stops_of(resolved: check.Resolved, money: MoneyInputs | None) -> StopsInForce:  # noqa: C901, PLR0912 - one row per answer state
    body = resolved.body
    if resolved.source == "none" or body is None:
        return StopsInForce((), None, NO_PLAYBOOK)
    guards = body.get("guards", {}) if isinstance(body, Mapping) else None
    if not isinstance(guards, Mapping):
        return StopsInForce((), None, GUARDS_UNREADABLE)
    source = PLAYBOOK_SOURCE.get(resolved.source)
    lines: list[StopInForce] = []
    max_loss = None if money is None else money.max_loss
    credit = None if money is None else money.credit
    # 50 % of max loss (ADR-247: always active)
    try:
        pct = _guard(guards, STOP_PCT_KEY)
    except ValueError:
        lines.append(StopInForce(STOP_MAX_LOSS, True, None, None, None, STOP_VALUE_UNREADABLE))
    else:
        if pct is None:
            lines.append(StopInForce(STOP_MAX_LOSS, False, None, None, None, None))
        elif max_loss is UNLIMITED:
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, None, source, MAX_LOSS_UNLIMITED))
        elif not isinstance(max_loss, Decimal):
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, None, source, MAX_LOSS_UNKNOWN))
        else:
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, adjust_money.stop_at_pct(max_loss, pct), source, None))
    # 2x the credit received (ADR-247: always active)
    try:
        stated = _guard(guards, STOP_CREDIT_KEY)
    except ValueError:
        lines.append(StopInForce(STOP_CREDIT, True, None, None, None, STOP_VALUE_UNREADABLE))
    else:
        multiple, msource = (CREDIT_MULTIPLE_DEFAULT, layers.SOURCE_DEFAULT) if stated is None else (stated, source)
        if credit is None:
            lines.append(StopInForce(STOP_CREDIT, True, multiple, None, msource, CREDIT_UNKNOWN))
        elif credit <= 0:
            lines.append(StopInForce(STOP_CREDIT, True, multiple, None, msource, NO_CREDIT))
        else:
            lines.append(StopInForce(STOP_CREDIT, True, multiple, adjust_money.stop_at_multiple(credit, multiple),
                                     msource, None))
    # % of margin (ADR-247: OFF unless the copy states it; the margin is Zerodha's figure, not read here, #627)
    try:
        margin_pct = _guard(guards, STOP_MARGIN_KEY)
    except ValueError:
        lines.append(StopInForce(STOP_MARGIN, True, None, None, None, STOP_VALUE_UNREADABLE))
    else:
        if margin_pct is None:
            lines.append(StopInForce(STOP_MARGIN, False, None, None, layers.SOURCE_DEFAULT, None))
        else:
            lines.append(StopInForce(STOP_MARGIN, True, margin_pct, None, source, MARGIN_NOT_READ))
    active = [x for x in lines if x.active]
    if not active:
        return StopsInForce(tuple(lines), None, NO_ACTIVE_STOP)
    if any(x.amount is None for x in active):
        return StopsInForce(tuple(lines), None, FIRST_UNKNOWN)
    first = min(active, key=lambda x: x.amount)  # the smallest loss is reached first; ties keep the listed order
    return StopsInForce(tuple(lines), first.kind, None)


def in_force(user_values: Mapping[str, Decimal] | None, resolved: check.Resolved,
             money: MoneyInputs | None) -> InForce:
    """THE settings in force for one strategy (ADR-245): every reply field about a covered setting reads this."""
    triggers, reason = triggers_of(resolved)
    return InForce(settings_of(user_values, resolved.strategy_layer), triggers, reason, stops_of(resolved, money))


__all__ = ["CREDIT_MULTIPLE_DEFAULT", "FIRST_UNKNOWN", "NO_PLAYBOOK", "PLAYBOOK_SOURCE", "InForce", "MoneyInputs",
           "SettingInForce", "StopInForce", "StopsInForce", "TriggerInForce", "covered_keys", "in_force",
           "money_inputs", "setting_of", "settings_of", "stops_of", "triggers_of"]
