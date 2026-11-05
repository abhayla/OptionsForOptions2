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

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.stop_lines import (
    CREDIT_UNKNOWN,
    GUARDS_UNREADABLE,
    MARGIN_NOT_READ,
    MAX_LOSS_UNKNOWN,
    MAX_LOSS_UNLIMITED,
    NO_CREDIT,
    STAGE_UNKNOWN,
    STOP_CREDIT,
    STOP_MARGIN,
    STOP_MAX_LOSS,
    STOP_VALUE_UNREADABLE,
    StopInForce,
    StopsInForce,
)
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
FIRST_UNKNOWN: Final = "stop_first_unknown"
NO_ACTIVE_STOP: Final = "stop_none_active"

#: the plan copy's guards (docs/design/playbook-body-v1.md "guards")
STOP_PCT_KEY: Final = "stop_line_pct_of_max_loss"
STOP_CREDIT_KEY: Final = "stop_line_x_credit"
STOP_MARGIN_KEY: Final = "stop_line_pct_of_margin"
#: ADR-247: the "2x the credit received" stop is ALWAYS active; a body that does not state its multiple follows this
#: default (source "default"); a strategy or a user changes it by writing ``stop_line_x_credit`` into their copy
CREDIT_MULTIPLE_DEFAULT: Final = Decimal(2)
#: ADR-247: the "50 % of max loss" stop is ALWAYS active too; a body that does not state it follows this default
#: (source "default"), exactly like the credit multiple (fix round 1: it used to drop out, so strategy 82 showed its
#: first stop at the 2x-credit 17,836 instead of 11,948.52)
MAX_LOSS_PCT_DEFAULT: Final = Decimal(50)
#: a trigger's unit as the body holds it -> the closed code the reply carries (the screen renders the words); a unit
#: outside this set -> None (never free text in an Identifier field)
UNIT_CODES: Final = {"%": "pct", "pts": "pts", "x": "x", "Rs": "rs", "SD": "sd", "delta": "delta",
                     "delta/lot": "delta_per_lot", "time": "time"}



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
        unit = UNIT_CODES.get(unit) if isinstance(unit, str) else None
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
    (``price_after``; None = not priced, UNLIMITED = unlimited), ``credit`` the net credit collected so far (ADR-251,
    ``adjust_money.net_credit_so_far``: entry +/- every adjustment's net credit or debit, booked trades included;
    None = not read) and ``margin`` Zerodha's stated margin (None = not read here, #627)."""

    max_loss: Decimal | Any | None
    credit: Decimal | None
    margin: Decimal | None = None


@dataclasses.dataclass(frozen=True)
class StageAt:
    """Where the strategy is in its playbook's stages (a plan saved before ADR-247 holds a per-stage %)."""

    expiry_kind: str
    days_left: int | None


def net_credit(tracked: Any) -> Decimal | None:
    """ADR-251: the net credit collected so far for a tracked strategy (book unread -> None, never 0)."""
    position = tracked.position
    if tracked.booked is None:
        return None
    return adjust_money.net_credit_so_far(tracked.booked, ((x.side, x.entry, x.lots * position.lot)
                                                           for x in position.legs))


def money_inputs(tracked: Any, market: Any, rates: Any) -> MoneyInputs:
    """The ONE engine read of the stop inputs for a tracked strategy (no market -> max loss not priced)."""
    from ofo_app.routes.adjustment import price_after  # noqa: PLC0415 - it imports this package's routes

    position = tracked.position
    credit = net_credit(tracked)
    if market is None:
        return MoneyInputs(None, credit)
    before = price_after(position.legs, position, tracked.booked, tracked.paid_charges, (), rates, market)
    gross = None if before.after is None else before.after.gross
    return MoneyInputs(None if gross is None else gross.max_loss, credit)


def _guard(guards: Mapping, key: str) -> Decimal | None:
    raw = guards.get(key)
    return None if raw is None else _decimal_text(raw)


def _stage_value(body: Mapping, tid: str, at: StageAt | None) -> tuple[bool, Decimal | None, str | None]:
    """ADR-250: a pre-ADR-247 plan's own per-stage % from its trigger ``tid``: (active, figure, reason)."""
    trig = (body.get("triggers") or {}).get(tid) if isinstance(body.get("triggers"), Mapping) else None
    if not isinstance(trig, Mapping):
        return False, None, None
    if trig.get("on") is not True:
        return trig.get("on") is not False, None, None if trig.get("on") is False else STOP_VALUE_UNREADABLE
    if at is None or at.days_left is None:
        return True, None, STAGE_UNKNOWN
    try:
        stage = pe.stage_of(body, at.expiry_kind, at.days_left)  # type: ignore[arg-type]
        values = trig.get(at.expiry_kind)
        if stage is None:
            return True, None, STAGE_UNKNOWN
        return True, _decimal_text(values[stage]), None
    except (ValueError, TypeError, KeyError, IndexError):
        return True, None, STOP_VALUE_UNREADABLE


def _saved_plan_lines(body: Mapping, money: MoneyInputs | None, at: StageAt | None) -> list[StopInForce]:
    """ADR-250: a plan saved before ADR-247 keeps its own stops exactly as saved: its per-stage % of max loss (T-06)
    and its % of margin (T-16) if on; NO 2x-credit line."""
    source = layers.SOURCE_STRATEGY
    max_loss = None if money is None else money.max_loss
    margin = None if money is None else money.margin
    lines = []
    active, pct, reason = _stage_value(body, sl.TRIGGER_MAX_LOSS, at)
    if active and pct is not None:
        if max_loss is UNLIMITED:
            reason = MAX_LOSS_UNLIMITED
        elif not isinstance(max_loss, Decimal):
            reason = MAX_LOSS_UNKNOWN
    amount = adjust_money.stop_at_pct(max_loss, pct) if active and reason is None and pct is not None else None
    lines.append(StopInForce(STOP_MAX_LOSS, active, pct, amount, source, reason,
                             _later(body, sl.TRIGGER_MAX_LOSS, at) if amount is not None or pct is not None else ()))
    active, pct, reason = _stage_value(body, sl.TRIGGER_MARGIN, at)
    if active and pct is not None and margin is None:
        reason = MARGIN_NOT_READ
    amount = adjust_money.stop_at_pct(margin, pct) if active and reason is None and pct is not None else None
    lines.append(StopInForce(STOP_MARGIN, active, pct, amount, source, reason,
                             _later(body, sl.TRIGGER_MARGIN, at) if pct is not None else ()))
    return lines


def _later(body: Mapping, tid: str, at: StageAt | None) -> tuple[Decimal, ...]:
    """The plan's own figures of ``tid`` at the stages after the current one (a stage without a value skipped)."""
    if at is None or at.days_left is None:
        return ()
    stage = pe.stage_of(body, at.expiry_kind, at.days_left)  # type: ignore[arg-type]
    values = body["triggers"][tid].get(at.expiry_kind) or []
    out = []
    for raw in values[stage + 1:] if stage is not None else ():
        try:
            out.append(_decimal_text(raw))
        except ValueError:
            continue
    return tuple(out)


def _first(lines: list[StopInForce]) -> StopsInForce:
    active = [x for x in lines if x.active]
    if not active:
        return StopsInForce(tuple(lines), None, NO_ACTIVE_STOP)
    if any(x.amount is None for x in active):
        return StopsInForce(tuple(lines), None, FIRST_UNKNOWN)
    first = min(active, key=lambda x: x.amount)  # the smallest loss is reached first; ties keep the listed order
    return StopsInForce(tuple(lines), first.kind, None)


def stops_of(resolved: check.Resolved, money: MoneyInputs | None,  # noqa: C901, PLR0912 - one row per answer state
             at: StageAt | None = None) -> StopsInForce:
    """THE stop lines in force (the live check's only stop source, ``adjustment_check.state_of``). ``at``: the
    strategy's stage (needed only by a plan saved before ADR-247, whose stops are per stage)."""
    body = resolved.body
    if resolved.source == "none" or body is None:
        return StopsInForce((), None, NO_PLAYBOOK)
    guards = body.get("guards", {}) if isinstance(body, Mapping) else None
    if not isinstance(guards, Mapping):
        return StopsInForce((), None, GUARDS_UNREADABLE)
    if resolved.source == "plan" and resolved.saved_before_adr247:
        return _first(_saved_plan_lines(body, money, at))
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
        pct, psource = (MAX_LOSS_PCT_DEFAULT, layers.SOURCE_DEFAULT) if pct is None else (pct, source)
        if max_loss is UNLIMITED:
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, None, psource, MAX_LOSS_UNLIMITED))
        elif not isinstance(max_loss, Decimal):
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, None, psource, MAX_LOSS_UNKNOWN))
        else:
            lines.append(StopInForce(STOP_MAX_LOSS, True, pct, adjust_money.stop_at_pct(max_loss, pct), psource,
                                     None))
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
        margin = None if money is None else money.margin
        if margin_pct is None:
            lines.append(StopInForce(STOP_MARGIN, False, None, None, layers.SOURCE_DEFAULT, None))
        elif margin is None:
            lines.append(StopInForce(STOP_MARGIN, True, margin_pct, None, source, MARGIN_NOT_READ))
        else:
            lines.append(StopInForce(STOP_MARGIN, True, margin_pct, adjust_money.stop_at_pct(margin, margin_pct),
                                     source, None))
    return _first(lines)


def margin_line_on(resolved: check.Resolved) -> bool:
    """The strategy's stops in force include an ACTIVE % of margin line (the background worker reads the margin only
    then; ADR-247: off by default)."""
    return any(x.kind == STOP_MARGIN and x.active for x in stops_of(resolved, None).lines)


def in_force(user_values: Mapping[str, Decimal] | None, resolved: check.Resolved,
             money: MoneyInputs | None) -> InForce:
    """THE settings in force for one strategy (ADR-245): every reply field about a covered setting reads this."""
    triggers, reason = triggers_of(resolved)
    return InForce(settings_of(user_values, resolved.strategy_layer), triggers, reason, stops_of(resolved, money))


__all__ = [
    "CREDIT_MULTIPLE_DEFAULT",
    "CREDIT_UNKNOWN",
    "FIRST_UNKNOWN",
    "GUARDS_UNREADABLE",
    "MARGIN_NOT_READ",
    "MAX_LOSS_PCT_DEFAULT",
    "MAX_LOSS_UNKNOWN",
    "MAX_LOSS_UNLIMITED",
    "NO_CREDIT",
    "NO_PLAYBOOK",
    "PLAYBOOK_SOURCE",
    "STAGE_UNKNOWN",
    "STOP_CREDIT",
    "STOP_MARGIN",
    "STOP_MAX_LOSS",
    "STOP_VALUE_UNREADABLE",
    "UNIT_CODES",
    "InForce",
    "MoneyInputs",
    "SettingInForce",
    "StageAt",
    "StopInForce",
    "StopsInForce",
    "TriggerInForce",
    "covered_keys",
    "in_force",
    "margin_line_on",
    "money_inputs",
    "net_credit",
    "setting_of",
    "settings_of",
    "stops_of",
    "triggers_of",
]
