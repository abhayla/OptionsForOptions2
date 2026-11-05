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
from ofo.timeutil import IST

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

#: the plan copy's 2x-credit multiple (docs/design/playbook-body-v1.md "guards"); ADR-252: no guard key is the source
#: of a % stop line (the body's % of max loss / % of margin guard keys are never read)
STOP_CREDIT_KEY: Final = "stop_line_x_credit"
#: ADR-247: the "2x the credit received" stop is ALWAYS active; a body that does not state its multiple follows this
#: default (source "default"); a strategy or a user changes it by writing ``stop_line_x_credit`` into their copy
CREDIT_MULTIPLE_DEFAULT: Final = Decimal(2)
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
    #: the strategy's stage (ADR-252: the % lines are per stage); None -> the % lines name ``STAGE_UNKNOWN``
    at: StageAt | None = None


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
    expiry = min(x.expiry for x in position.legs)  # the live check's stage read (``adjustment_check.state_of``)
    at = StageAt(market.expiry_kind or position.expiry_kind or "weekly",
                 (expiry - market.now.astimezone(IST).date()).days)
    return MoneyInputs(None if gross is None else gross.max_loss, credit, at=at)


#: ADR-247 is "Default stop for the iron condor playbook": only this family gets the 2x-credit line
CREDIT_FAMILY: Final = "ic"
#: a stated credit multiple above this is refused (a typo such as 1e400 would overflow the rupee amount)
CREDIT_MULTIPLE_MAX: Final = Decimal(100)
#: a % of max loss / of margin stop is in (0, 100]
PCT_MAX: Final = Decimal(100)
#: the plan sheet and the plan words read the FIRST stage (the sheet edits every stage at once, ``set_max_loss_stop``)
FIRST_STAGE: Final = "first"
#: the per-stage trigger behind each % line (ADR-252: T-06 for % of max loss, T-16 for % of margin)
TRIGGER_OF_LINE: Final = {STOP_MAX_LOSS: sl.TRIGGER_MAX_LOSS, STOP_MARGIN: sl.TRIGGER_MARGIN}
_KINDS: Final = ("weekly", "monthly")


def _pct(raw: object) -> Decimal:
    value = _decimal_text(raw)
    if not 0 < value <= PCT_MAX:
        raise ValueError(f"stop % out of (0, 100]: {raw!r}")
    return value


def _multiple(raw: object) -> Decimal:
    value = _decimal_text(raw)
    if not 0 < value <= CREDIT_MULTIPLE_MAX:
        raise ValueError(f"credit multiple out of (0, {CREDIT_MULTIPLE_MAX}]: {raw!r}")
    return value


def _trigger(body: Mapping, tid: str) -> tuple[Mapping | None, bool]:
    """(the trigger, readable): a body whose ``triggers`` is not an object is unreadable (fail closed)."""
    found = body.get("triggers")
    if not isinstance(found, Mapping):
        return None, False
    trig = found.get(tid)
    return (trig, True) if trig is None or isinstance(trig, Mapping) else (None, False)


def _stage_index(body: Mapping, at: StageAt | str | None) -> tuple[str, int] | None:
    if at == FIRST_STAGE:
        return "weekly", 0
    if not isinstance(at, StageAt) or at.days_left is None:
        return None
    try:
        stage = pe.stage_of(body, at.expiry_kind, at.days_left)  # type: ignore[arg-type]
    except (ValueError, TypeError, KeyError):
        return None
    return None if stage is None else (at.expiry_kind, stage)


def _figures(trig: Mapping, expiry_kind: str, stage: int) -> tuple[Decimal, tuple[Decimal, ...]]:
    values = trig.get(expiry_kind)
    figure = _pct(values[stage])  # type: ignore[index]
    later = []
    for raw in values[stage + 1:]:  # type: ignore[index]
        try:
            later.append(_pct(raw))
        except ValueError:
            continue  # a stage without a value is skipped
    return figure, tuple(later)


def _trigger_line(body: Mapping, kind: str, base: Decimal | Any | None,  # noqa: PLR0911 - one return per answer state
                  at: StageAt | str | None, source: str | None) -> StopInForce | None:
    """ADR-252: the line of ``kind`` = its trigger's value at the current stage; on/off = that trigger's switch only.
    Trigger absent -> no line; off -> inactive; on with an unreadable / out-of-range value -> active, not checked."""
    trig, readable = _trigger(body, TRIGGER_OF_LINE[kind])
    if not readable:
        return StopInForce(kind, True, None, None, None, STOP_VALUE_UNREADABLE)
    if trig is None:
        return None
    if trig.get("on") is False:
        return StopInForce(kind, False, None, None, source, None)
    if trig.get("on") is not True:
        return StopInForce(kind, True, None, None, source, STOP_VALUE_UNREADABLE)
    where = _stage_index(body, at)
    if where is None:
        return StopInForce(kind, True, None, None, source, STAGE_UNKNOWN)
    try:
        figure, later = _figures(trig, *where)
    except (ValueError, TypeError, KeyError, IndexError):
        return StopInForce(kind, True, None, None, source, STOP_VALUE_UNREADABLE)
    if kind == STOP_MAX_LOSS and base is UNLIMITED:
        return StopInForce(kind, True, figure, None, source, MAX_LOSS_UNLIMITED, later)
    if not isinstance(base, Decimal):
        missing = MAX_LOSS_UNKNOWN if kind == STOP_MAX_LOSS else MARGIN_NOT_READ
        return StopInForce(kind, True, figure, None, source, missing, later)
    return StopInForce(kind, True, figure, adjust_money.stop_at_pct(base, figure), source, None, later)


def _credit_line(body: Mapping, credit: Decimal | None, source: str | None) -> StopInForce:
    """ADR-247/251: N x the net credit so far; N = the copy's stated multiple, else 2 (source "default")."""
    guards = body.get("guards", {})
    stated = guards.get(STOP_CREDIT_KEY) if isinstance(guards, Mapping) else STOP_VALUE_UNREADABLE
    try:
        multiple, msource = (CREDIT_MULTIPLE_DEFAULT, layers.SOURCE_DEFAULT) if stated is None \
            else (_multiple(stated), source)
    except ValueError:
        return StopInForce(STOP_CREDIT, True, None, None, source, STOP_VALUE_UNREADABLE)
    if credit is None:
        return StopInForce(STOP_CREDIT, True, multiple, None, msource, CREDIT_UNKNOWN)
    if credit <= 0:
        return StopInForce(STOP_CREDIT, True, multiple, None, msource, NO_CREDIT)
    try:
        amount = adjust_money.stop_at_multiple(credit, multiple)
    except ArithmeticError:  # decimal.InvalidOperation included: never raise inside the check
        return StopInForce(STOP_CREDIT, True, multiple, None, msource, STOP_VALUE_UNREADABLE)
    return StopInForce(STOP_CREDIT, True, multiple, amount, msource, None)


def credit_line_applies(resolved: check.Resolved) -> bool:
    """ADR-247 (iron condor only) and ADR-250 (a plan saved before ADR-247 gains no 2x-credit line)."""
    body = resolved.body
    if not isinstance(body, Mapping) or body.get("strategy_type") != CREDIT_FAMILY:
        return False
    return not (resolved.source == "plan" and resolved.saved_before_adr247)


def _first(lines: list[StopInForce]) -> StopsInForce:
    active = [x for x in lines if x.active]
    if not active:
        return StopsInForce(tuple(lines), None, NO_ACTIVE_STOP)
    if any(x.amount is None for x in active):
        return StopsInForce(tuple(lines), None, FIRST_UNKNOWN)
    first = min(active, key=lambda x: x.amount)  # the smallest loss is reached first; ties keep the listed order
    return StopsInForce(tuple(lines), first.kind, None)


def stops_of(resolved: check.Resolved, money: MoneyInputs | None,
             at: StageAt | str | None = None) -> StopsInForce:
    """THE stop lines in force (the live check's only stop source, ``adjustment_check.state_of``). ADR-252: the % of
    max loss line is T-06 at the strategy's stage ``at``, the % of margin line T-16, each on/off by its own switch;
    the 2x-credit line only where ``credit_line_applies``. No guard key is the source of a % line. ``at`` None -> the
    % lines name ``STAGE_UNKNOWN``; ``FIRST_STAGE`` -> the first stage (the plan sheet and its words)."""
    body = resolved.body
    if resolved.source == "none" or not isinstance(body, Mapping):
        return StopsInForce((), None, NO_PLAYBOOK)
    source = PLAYBOOK_SOURCE.get(resolved.source)
    max_loss = None if money is None else money.max_loss
    margin = None if money is None else money.margin
    lines = [x for x in (_trigger_line(body, STOP_MAX_LOSS, max_loss, at, source),) if x is not None]
    if credit_line_applies(resolved):
        lines.append(_credit_line(body, None if money is None else money.credit, source))
    lines.extend(x for x in (_trigger_line(body, STOP_MARGIN, margin, at, source),) if x is not None)
    return _first(lines)


def set_max_loss_stop(body: dict, raw: str) -> None:
    """The plan sheet's stop edit (ADR-252): ``raw`` becomes T-06's value at every stage of both expiry kinds (a stage
    without a value stays without one) and T-06 is switched on; no guard key is written."""
    _pct(raw)
    trig = body.setdefault("triggers", {}).get(sl.TRIGGER_MAX_LOSS)
    if not isinstance(trig, dict):
        raise ValueError("the body has no % of max loss trigger")
    for kind in _KINDS:
        if isinstance(trig.get(kind), list):
            trig[kind] = [raw if x not in (None, "") else x for x in trig[kind]]
    trig["on"] = True


def sheet_stop(body: Mapping) -> Decimal | None:
    """The plan sheet's stop: T-06's first-stage value when T-06 is on (None otherwise)."""
    line = _trigger_line(body, STOP_MAX_LOSS, None, FIRST_STAGE, None)
    return None if line is None or not line.active else line.figure


def check_stop_values(body: Mapping) -> str | None:
    """Save-time range check (the check itself never raises on these): the field out of range, or None."""
    guards = body.get("guards")
    if isinstance(guards, Mapping) and guards.get(STOP_CREDIT_KEY) is not None:
        try:
            _multiple(guards[STOP_CREDIT_KEY])
        except ValueError:
            return f"guards.{STOP_CREDIT_KEY}"
    for tid in TRIGGER_OF_LINE.values():
        trig, readable = _trigger(body, tid)
        if not readable:
            return f"triggers.{tid}"
        for kind in _KINDS:
            for raw in (trig or {}).get(kind) or ():
                if raw in (None, ""):
                    continue
                try:
                    _pct(raw)
                except ValueError:
                    return f"triggers.{tid}.{kind}"
    return None


def margin_line_on(resolved: check.Resolved) -> bool:
    """The strategy's stops in force include an ACTIVE % of margin line (the background worker reads the margin only
    then; ADR-247: off by default)."""
    return any(x.kind == STOP_MARGIN and x.active for x in stops_of(resolved, None).lines)


def in_force(user_values: Mapping[str, Decimal] | None, resolved: check.Resolved,
             money: MoneyInputs | None) -> InForce:
    """THE settings in force for one strategy (ADR-245): every reply field about a covered setting reads this."""
    triggers, reason = triggers_of(resolved)
    return InForce(settings_of(user_values, resolved.strategy_layer), triggers, reason,
                   stops_of(resolved, money, None if money is None else money.at))


__all__ = [
    "CREDIT_FAMILY",
    "CREDIT_MULTIPLE_DEFAULT",
    "FIRST_STAGE",
    "CREDIT_UNKNOWN",
    "FIRST_UNKNOWN",
    "GUARDS_UNREADABLE",
    "MARGIN_NOT_READ",
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
    "check_stop_values",
    "covered_keys",
    "credit_line_applies",
    "in_force",
    "margin_line_on",
    "money_inputs",
    "net_credit",
    "setting_of",
    "set_max_loss_stop",
    "settings_of",
    "sheet_stop",
    "stops_of",
    "triggers_of",
]
