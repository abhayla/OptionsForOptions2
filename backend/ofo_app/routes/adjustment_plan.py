"""GET / POST / PUT /api/strategies/{id}/adjustment-plan (GC-ADJ2 step 4; REQ-161 AC-1..AC-4, REQ-158 AC-5).

The plan sheet's server side. A strategy's plan is a COPY of a playbook's body (``playbook_store.accept_plan``): the
sheet's overrides (target, stop, max adjustments, time exit) are written into the copy's ``guards`` only, never into the
playbook, and editing or deleting the playbook later never changes the plan.

- GET: the strategy's type (its plan's type, else the shape's type through the check route's own reader and
  ``adjustment_check.strategy_type``), that type's playbooks, the plan (or None), the prefill (from the plan, else from
  the active playbook; ``?playbook_id=`` refills every field from that playbook, REQ-161 AC-2) and the sheet's words.
- POST: accept ("Use playbook as is" sends only ``playbook_id``); PUT: edit the existing plan (404 when none). A PUT
  that keeps the plan's playbook starts from the plan's own body, so earlier changes survive; another playbook starts
  from that playbook's body.
- Type None (Custom or an unmapped shape): GET answers ``generic`` with the sheet's text; POST / PUT are refused with
  the same catalogue text (409) and nothing is written (REQ-161 AC-4).
- Every answer state: plan stated / absent; prefill from the plan / the user's active playbook / the system playbook;
  a value that is not valid -> ``playbook_body_invalid`` naming the sheet field (422); another user's or a missing
  strategy -> 404 before anything is read or written; a playbook of another type -> 422 naming ``playbook_id``.
- Suggest-only (ADR-003): nothing here places an order. Values are decimals as strings, the clock as hour and minute
  numbers; the browser computes nothing.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from ofo import market_calendar
from ofo.adjustment import playbook_stages as stages
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.playbook_text import name_shown
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.charges import ChargeRates
from ofo.checks import pnl_amount as rupee
from ofo.checks import rupee_figures as figs
from ofo.checks.time_of_day import CLOCK, DATE, ON_EXPIRY, day_of, time_exit_parts
from ofo.errors import render
from ofo.errors.explanations import LABEL_TABLES, render_explanation
from ofo.settings import layers
from ofo.timeutil import IST
from pydantic import BaseModel, ConfigDict

from ofo_app import adjustment_check as check
from ofo_app import playbook_store as store
from ofo_app import settings_in_force as in_force_mod
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.playbook_body_out import PlaybookBody
from ofo_app.routes import playbooks as pb_routes
from ofo_app.routes.adjustment import (
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
    release_connection,
)
from ofo_app.routes.adjustment_preferences import UserValuesIn
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import (
    MarketContext,
    get_market_context,
    load_charge_rates,
)
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_NOT_AVAILABLE = "user_input_request_not_available"
_GENERIC = "adjust_plan_no_playbook"
ID_MAX = 9_223_372_036_854_775_807  # the id column is BIGSERIAL
MAX_ADJUSTMENTS_LIMIT = 10
_PERCENT = re.compile(r"[0-9]{1,3}(\.[0-9]{1,4})?")
_COUNT = re.compile(r"[0-9]{1,3}")
_RUPEES = rupee.LEVEL_PATTERN  # whole-trade rupees, to the paisa: the one pattern (F8), shared with the stored guard
#: The sheet field -> the guard of the plan's copy that holds it (docs/design/playbook-body-v1.md "guards")
TARGET_KEY = "profit_target_pct_of_max_profit"
#: the sheet's stop is the % of max loss trigger's value (ADR-252: ``settings_in_force.set_max_loss_stop`` /
#: ``sheet_stop``), never a guard key
SOURCE_RUPEES = "rupees"  # which box is the saved level (the other figure is derived for display)
SOURCE_PERCENT = "percent"
EITHER_RULE ="whichever comes first"
MAX_KEY = "max_adjustments"
TIME_KEY = "time_exit"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TimeExitIn(_In):
    """ADR-330 (7): the plan's time exit, one time on one day; a blank ``on`` = expiry day (Q9)."""
    at: str
    on: str = ""


class PlanIn(_In):
    """Every sheet value arrives as the text typed (the browser forms no number, ADR-008): percents as decimal text,
    max adjustments as digits, the time exit as ``HH:MM``; each is checked here and names its field when not valid."""
    playbook_id: int
    target: str | None = None
    stop: str | None = None
    max_adjustments: str | None = None
    time_exit: str | TimeExitIn | None = None  # a plain "HH:MM" = on expiry day (the old shape)
    #: ADR-330 (5): the same two levels typed in rupees (whole trade, before charges, decimal text; "" = none). The
    #: sheet sends the box last edited; both given must be the same level, else refused naming the rupee field
    target_rupees: str | None = None
    stop_rupees: str | None = None
    #: ADR-245: this strategy's own setting overrides (the strategy layer), ``{key: "decimal text"}``. Given -> the
    #: plan's overrides become exactly this object (``{}`` removes every override, so each value follows the user's,
    #: else the default); left out -> kept as the body has them. Each key must be a three-layer setting and each value
    #: one the registry accepts, else refused naming ``settings.<key>`` (never dropped, never clamped)
    settings: dict[str, str] | None = None


class ClockOut(ApiModel):
    hour: int
    minute: int


class PlanPlaybookOut(ApiModel):
    id: int
    name: CatalogueText
    type: Identifier
    type_name: CatalogueText
    is_system: bool
    draft: bool
    active: bool


class PrefillOut(ApiModel):
    playbook_id: int
    target: Money | None
    stop: Money | None
    target_words: CatalogueText | None = None
    stop_words: CatalogueText | None = None
    max_adjustments: int | None
    time_exit: ClockOut | None
    time_exit_on: datetime.date | None = None  # None = expiry day
    target_rupees: Money | None = None  # ADR-330 (5): the level in rupees (whole trade, before charges)
    target_per_lot: Money | None = None
    target_rupee_words: CatalogueText | None = None
    stop_rupees: Money | None = None
    stop_per_lot: Money | None = None
    stop_rupee_words: CatalogueText | None = None
    target_source: Identifier | None = None  # the saved level's own box: "rupees" or "percent" (the other is derived)
    stop_source: Identifier | None = None


class PlanOut(ApiModel):
    playbook_id: int | None
    playbook_name: CatalogueText | None
    target: Money | None
    stop: Money | None
    target_words: CatalogueText | None = None
    stop_words: CatalogueText | None = None
    max_adjustments: int | None
    time_exit: ClockOut | None
    time_exit_on: datetime.date | None = None  # None = expiry day
    target_rupees: Money | None = None  # ADR-330 (5): the level in rupees (whole trade, before charges)
    target_per_lot: Money | None = None
    target_rupee_words: CatalogueText | None = None
    stop_rupees: Money | None = None
    stop_per_lot: Money | None = None
    stop_rupee_words: CatalogueText | None = None
    target_source: Identifier | None = None  # the saved level's own box: "rupees" or "percent" (the other is derived)
    stop_source: Identifier | None = None
    accepted_at: datetime.datetime


class SettingInForceOut(ApiModel):
    """One covered setting in force for this strategy (ADR-245): its value and where it came from (``strategy`` /
    ``user`` / ``default``); a layer that exists but cannot be read -> value and source None, ``reason`` its code."""
    key: Identifier
    value: Money | None
    source: Identifier | None
    reason: Identifier | None


class TriggerInForceOut(ApiModel):
    """One trigger of the playbook in force, its per-stage values (Trigger 1 / 2 / 3: Early, Middle, Last) and the
    playbook's source; values None = the trigger has no threshold (a cross) or ``reason`` names why it is unread."""
    id: Identifier
    label: CatalogueText | None
    unit: Identifier | None
    on: bool | None
    weekly: list[Money | None] | None
    monthly: list[Money | None] | None
    source: Identifier | None
    reason: Identifier | None


class StopLineOut(ApiModel):
    """ADR-247: one stop line: ``figure`` the % or multiple in force, ``amount`` the loss in rupees at which it fires
    (engine, exact decimal text), or None with ``reason`` naming the missing input."""
    kind: Identifier
    active: bool
    figure: Money | None
    amount: Money | None
    source: Identifier | None
    reason: Identifier | None
    later: list[Money]  # the figures at the stages after this one (ADR-252: per stage)


class StopsOut(ApiModel):
    lines: list[StopLineOut]
    first: Identifier | None  # the kind that fires first (the smallest amount), None with ``reason``
    reason: Identifier | None


class AdjustmentPlanOut(ApiModel):
    strategy_id: int
    type: Identifier | None
    type_name: CatalogueText | None
    generic: bool
    generic_text: CatalogueText | None
    playbooks: list[PlanPlaybookOut]
    plan: PlanOut | None
    prefill: PrefillOut | None
    labels: dict[Identifier, CatalogueText]
    #: contract "Your adjustment settings" step 3: the ONE settings-in-force read (``settings_in_force.in_force``)
    settings: list[SettingInForceOut]
    triggers: list[TriggerInForceOut]
    triggers_reason: Identifier | None
    stops: StopsOut


def _bad(field: str) -> store.PlaybookStoreError:
    return store.PlaybookStoreError(store.BODY_INVALID, f"plan sheet field {field}", field=field)


def _refused(exc: store.PlaybookStoreError) -> StrategyRefused:
    status = Failure.NOT_FOUND if exc.code == store.NOT_FOUND else None
    return StrategyRefused(exc.code, status, message=render(exc.code, **exc.slots))


def _percent(raw: str, field: str) -> str:
    if not _PERCENT.fullmatch(raw):
        raise _bad(field)
    try:
        value = Decimal(raw)
    except InvalidOperation:  # pragma: no cover - the pattern admits only decimals
        raise _bad(field) from None
    if not 0 < value <= 100:  # noqa: PLR2004 - a percent of max profit / max loss
        raise _bad(field)
    return raw


def _read_percent(guards: dict, key: str) -> Decimal | None:
    raw = guards.get(key)
    return Decimal(raw) if isinstance(raw, str) and _PERCENT.fullmatch(raw) else None


def _read_clock(guards: dict) -> ClockOut | None:
    parts = time_exit_parts(guards.get(TIME_KEY))
    found = None if parts is None else CLOCK.fullmatch(parts[0])
    return None if found is None else ClockOut.model_validate({"hour": int(found[1]), "minute": int(found[2])})


def _read_clock_on(guards: dict) -> datetime.date | None:
    parts = time_exit_parts(guards.get(TIME_KEY))
    return None if parts is None or parts[1] == ON_EXPIRY else day_of(parts[1])


_STOP_WORD_IDS = {in_force_mod.STOP_MAX_LOSS: "plan_stop_words_loss",
                  in_force_mod.STOP_CREDIT: "plan_stop_words_credit",
                  in_force_mod.STOP_MARGIN: "plan_stop_words_margin"}
_STOP_SLOTS = {in_force_mod.STOP_MAX_LOSS: "pct", in_force_mod.STOP_CREDIT: "multiple",
               in_force_mod.STOP_MARGIN: "margin"}
def _stop_words(body: dict, saved_before: bool, kind: str | None = None, rupee_part: Any = None) -> Any:
    """ADR-247/252: the ACTIVE stops from the ONE settings-in-force stops list (``settings_in_force.stops_of`` at the
    first stage: T-06 % of max loss, N x the credit received where it applies, T-16 % of margin only when on), joined
    "..., whichever comes first". Read for every plan, whatever guard keys its body holds."""
    lines = in_force_mod.stops_of(check.Resolved("plan", body, None, None, False, saved_before_adr247=saved_before),
                                  None, in_force_mod.first_stage_of(kind)).lines
    parts = [render_explanation(_STOP_WORD_IDS[x.kind], **{_STOP_SLOTS[x.kind]: format(x.figure, "f")})
             for x in lines if x.active and x.figure is not None]
    if rupee_part is not None:  # ADR-330 (5)/LP-2: the rupee stop leads; the lines still in force follow it
        parts.insert(0, rupee_part)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:  # noqa: PLR2004
        joined = render_explanation("plan_stop_words_or", a=parts[0], b=parts[1])
    else:
        joined = render_explanation("plan_stop_words_or3", a=parts[0], b=parts[1], c=parts[2])
    return render_explanation("plan_stop_words_first", words=joined)


def _words(body: dict, guards: dict, saved_before: bool, kind: str | None = None) -> tuple[Any, Any]:
    """GC-ADJ2 item 3: what the target and the stop numbers ARE, in words from the catalogue (the number stays the
    input). The stop words come from the stops in force (ADR-247), not from the guards the body happens to hold."""
    target = _read_percent(guards, TARGET_KEY)
    t_words = None if target is None else render_explanation("plan_target_words", pct=format(target, "f"))
    return t_words, _stop_words(body, saved_before, kind)


def _values(body: dict, saved_before: bool, kind: str | None = None) -> dict[str, Any]:
    found = body.get("guards")
    guards: dict = found if isinstance(found, dict) else {}
    mx = guards.get(MAX_KEY)
    t_words, s_words = _words(body, guards, saved_before, kind)
    return {"target": _read_percent(guards, TARGET_KEY), "stop": in_force_mod.sheet_stop(body, kind),
            "target_words": t_words, "stop_words": s_words,
            "max_adjustments": mx if type(mx) is int else None, "time_exit": _read_clock(guards),
            "time_exit_on": _read_clock_on(guards)}


@dataclasses.dataclass(frozen=True)
class Bases:
    """What a rupee level is shown against (ADR-330 (5)): max profit for a target, the stored stop base's max loss for
    a stop (both whole trade, before charges) and the lots of the largest leg for the per-lot figure. None = unknown."""
    max_profit: Decimal | None = None
    max_loss: Decimal | None = None
    lots: int | None = None


def bases_of(tracked: Any, market: Any, rates: Any) -> Bases:
    base = getattr(tracked, "stop_base", None)
    loss = getattr(base, "max_loss", None)
    profit = None
    if market is not None:
        try:
            profit = check.max_profit_of(tracked, market, rates)
        except Exception:  # noqa: BLE001 - an optional display figure: unknown, never a guess; logged
            log.warning("adjustment plan: max profit not worked out for the rupee figures", exc_info=True)
    legs = getattr(getattr(tracked, "position", None), "legs", None) or ()
    counts = {x.lots for x in legs}  # LP-3: the per-lot figure only when every leg has the same lot count
    return Bases(profit, loss if isinstance(loss, Decimal) and loss.is_finite() else None,
                 counts.pop() if len(counts) == 1 else None)


def _rupee_guard(guards: dict, key: str) -> Decimal | None:
    try:
        return rupee.level_of(guards.get(key) if isinstance(guards.get(key), str) else None)
    except ValueError:
        return None  # an unreadable stored level shows nothing (the evaluator says "not checked")


def _rupee_words(found: figs.Figures) -> Any:
    if found.rupees is None:
        return None
    if found.per_lot is None:
        return render_explanation("plan_level_rupees_whole", rupees=found.rupees)
    return render_explanation("plan_level_rupees", rupees=found.rupees, per_lot=found.per_lot)


def _rupee_stop_part(stop: figs.Figures) -> Any:
    if stop.rupees is None:
        return None
    if stop.percent is None:
        return render_explanation("plan_stop_words_rupees_plain", rupees=stop.rupees)
    return render_explanation("plan_stop_words_rupees", rupees=stop.rupees, pct=stop.percent)


def with_rupee_figures(values: dict[str, Any], body: dict, bases: Bases, *, kind: str | None = None,
                       saved_before: bool = False) -> dict[str, Any]:
    """ADR-330 (5): the plan shows BOTH figures of each level, worked out here (the browser computes nothing). A stored
    rupee target is the source: its percent is derived from max profit; otherwise the rupees come from the percent."""
    found = body.get("guards")
    guards: dict = found if isinstance(found, dict) else {}
    out = dict(values)
    level = _rupee_guard(guards, sl.RUPEE_PROFIT_KEY)
    out["target_source"] = SOURCE_PERCENT if level is None else SOURCE_RUPEES
    if level is not None:
        target = figs.from_rupees(level, bases.max_profit, bases.lots)
        out["target"] = target.percent
        out["target_words"] = None if target.percent is None else render_explanation(
            "plan_target_words", pct=format(target.percent, "f"))
    elif values.get("target") is None:
        target = figs.NONE
    else:
        target = figs.from_percent(values["target"], bases.max_profit, bases.lots)
    level = _rupee_guard(guards, sl.RUPEE_LOSS_KEY)
    out["stop_source"] = SOURCE_PERCENT if level is None else SOURCE_RUPEES
    if level is not None:
        stop = figs.from_rupees(level, bases.max_loss, bases.lots)
        # the rupee level IS the stop; its percent is the derived display figure only (None when not computable: never
        # the stale T-06 value, review F3), and the words say every stop in force (LP-2: the 2x-credit line too)
        out["stop"] = stop.percent
        out["stop_words"] = _stop_words(body, saved_before, kind, _rupee_stop_part(stop))
    elif values.get("stop") is None:
        stop = figs.NONE
    else:
        stop = figs.from_percent(values["stop"], bases.max_loss, bases.lots)
    out |= {"target_rupees": target.rupees, "target_per_lot": target.per_lot,
            "target_rupee_words": _rupee_words(target), "stop_rupees": stop.rupees, "stop_per_lot": stop.per_lot,
            "stop_rupee_words": _rupee_words(stop)}
    return out


def _rupee_in(raw: str, field: str) -> Decimal | None:
    """The typed rupee text -> a positive Decimal; "" -> None (no rupee level); else refused naming the field."""
    if raw == "":
        return None
    try:
        if not _RUPEES.fullmatch(raw):
            raise ValueError(field)
        return rupee.level_of(raw)
    except ValueError:
        raise _bad(field) from None


def _apply_rupee(out: dict, key: str, typed: str | None, percent: str | None,  # noqa: PLR0913
                 base: Decimal | None, lots: int | None, field: str) -> bool:
    """One level's rupee box. Returns True when the rupee level is the SOURCE (typed, no percent beside it): the caller
    then switches the percent target off. Both typed -> they must be the same level (else refused naming the rupee
    field; a base that cannot judge refuses too) and the rupee level is the one stored. A percent typed alone drops the
    rupee level (the last edited box is the source of truth)."""
    guards = out.setdefault("guards", {})
    if typed is None:
        if percent is not None:
            guards.pop(key, None)
        return False
    level = _rupee_in(typed, field)
    if level is None:
        if key == sl.RUPEE_LOSS_KEY and not percent and key in guards:
            raise _bad(field)  # a plan always has a stop: clearing it with no percent would restore a stale T-06
        guards.pop(key, None)
        return False
    if percent and not figs.agree(Decimal(percent), level, base, lots):
        raise _bad(field)
    guards[key] = format(level, "f")  # agreeing boxes store the RUPEE level: the rounded percent would move it (F4)
    return True


def _stored_loss(stored: Any, bases: Bases) -> Decimal | None:
    """The max loss of the base now stored (ADR-330 (1)), else the one read before the save."""
    found = getattr(getattr(stored, "stop_base", None), "max_loss", None)
    return found if isinstance(found, Decimal) and found.is_finite() else bases.max_loss


def _set_stop(out: dict, raw: str, kind: str | None = None) -> None:
    """ADR-252: the sheet's stop edit IS the T-06 value the live check reads (``settings_in_force``), every stage."""
    try:
        in_force_mod.set_max_loss_stop(out, _percent(raw, "stop"), kind)
    except ValueError:
        raise _bad("stop") from None


def _time_exit_guard(raw: str | TimeExitIn) -> str | dict[str, str]:
    """The guard to store: a plain "HH:MM" stays as typed (on expiry day); {at, on} keeps its day, a blank day stored
    as "expiry". An unreadable time or date -> refused naming the field."""
    if isinstance(raw, str):
        if not CLOCK.fullmatch(raw):
            raise _bad(TIME_KEY)
        return raw
    on = raw.on.strip() or ON_EXPIRY
    if not CLOCK.fullmatch(raw.at) or (on != ON_EXPIRY and (not DATE.fullmatch(on) or day_of(on) is None)):
        raise _bad(TIME_KEY)
    return {"at": raw.at, "on": on}


def check_time_exit_day(guard: object, today: datetime.date | None, last_expiry: datetime.date | None) -> None:
    """ADR-330 (7), at save: a dated time exit must be a trading day (not a weekend or holiday), not before today and
    not after the last expiry of the legs; otherwise refused naming ``time_exit``. A day that cannot be judged
    (today or the legs unknown) is refused too, never passed. On expiry (blank) there is nothing to judge."""
    parts = time_exit_parts(guard)
    if parts is None or parts[1] == ON_EXPIRY:
        return
    day = day_of(parts[1])
    if day is None or today is None or last_expiry is None or day < today or day > last_expiry \
            or not market_calendar.is_trading_day(day):
        raise _bad(TIME_KEY)


def with_overrides(body: dict, data: PlanIn, kind: str | None = None, bases: Bases | None = None) -> dict:
    """A copy of ``body`` whose guards hold the sheet's values (a value left out stays as the body has it)."""
    out = copy.deepcopy(body)
    guards = out.setdefault("guards", {})
    if data.target is not None:
        guards[TARGET_KEY] = _percent(data.target, "target") if data.target != "" else ""  # ADR-305: "" = no Target
    if data.stop is not None:
        _set_stop(out, data.stop, kind)
    bases = bases or Bases()
    if _apply_rupee(out, sl.RUPEE_PROFIT_KEY, data.target_rupees, data.target, bases.max_profit, bases.lots,
                    "target_rupees"):
        guards[TARGET_KEY] = ""  # the rupee target is the source: the percent target is off (one target level)
    _apply_rupee(out, sl.RUPEE_LOSS_KEY, data.stop_rupees, data.stop, bases.max_loss, bases.lots, "stop_rupees")
    if data.max_adjustments is not None:
        if not _COUNT.fullmatch(data.max_adjustments) or int(data.max_adjustments) > MAX_ADJUSTMENTS_LIMIT:
            raise _bad(MAX_KEY)
        guards[MAX_KEY] = int(data.max_adjustments)
    if data.time_exit is not None:
        guards[TIME_KEY] = _time_exit_guard(data.time_exit)
    if data.settings is not None:
        for key, raw in data.settings.items():
            try:
                layers.check_plan_settings({key: raw})
            except ValueError:
                raise _bad(f"{layers.PLAN_SETTINGS}.{key}") from None
        out[layers.PLAN_SETTINGS] = dict(data.settings)
    return out


def _labels() -> dict[str, Any]:
    return {key: render_explanation(f"plan_sheet_{key}") for key in LABEL_TABLES["plan_sheet"]}


def _playbook_row(pb: store.Playbook, active_id: int) -> dict[str, Any]:
    return {"id": pb.id, "name": name_shown(pb.name), "type": pb.strategy_type,
            "type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[pb.strategy_type]),
            "is_system": pb.is_system, "draft": pb.is_system and pb.status == "draft", "active": pb.id == active_id}


async def _own_strategy(strategy_id: int, tracked_reader: TrackedReader, rates: ChargeRates | None) -> Any:
    from ofo_app.adjustment_readers import TrackedUnreadable  # noqa: PLC0415 - it imports routes.adjustment
    try:
        tracked = await tracked_reader(strategy_id, rates)
    except TrackedUnreadable as exc:
        log.warning("adjustment plan: strategy %s unreadable: %s", strategy_id, exc)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    if tracked is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    return tracked


async def _market(tracked: Any, market_reader: MarketReader, ctx: MarketContext | None) -> Any:
    """The market read the stop amounts are priced from; a failed read -> None (each stop amount then names
    ``stop_max_loss_unknown``), never a guessed figure."""
    try:
        return await market_reader(tracked, ctx)
    except Exception:  # noqa: BLE001 - any failed read means "not priced", logged
        log.warning("adjustment plan: market not read for the stop amounts", exc_info=True)
        return None


async def _type_of(db: Any, user_ref: str, strategy_id: int, tracked: Any,
                   ctx: MarketContext | None) -> tuple[str | None, store.Plan | None]:
    """The plan's type when there is a plan (a plan keeps its type), else the shape's, read as the check route does.
    D-38: the entry type takes no market and no spot (D-04, owner decision 25 Nov 2026, ADR-322 point 5), so this reads
    none; it used to ask the market reader a second time for a figure it then threw away."""
    plan = await store.plan_for(db, user_ref, strategy_id)
    if plan is not None:
        return plan.strategy_type, plan
    return check.entry_type(tracked, check.listed_of(ctx)), None  # D-04
def _kind_of(tracked: Any, money: in_force_mod.MoneyInputs | None) -> str:
    """The strategy's own expiry kind (the live check's read): the market's, else the position's, else weekly."""
    at = None if money is None else money.at
    return (None if at is None else at.expiry_kind) or getattr(tracked.position, "expiry_kind", None) or "weekly"


async def _plan_out(db: Any, user_ref: str, plan: store.Plan, kind: str | None = None,
                    bases: Bases | None = None) -> dict[str, Any]:
    name = None
    if plan.playbook_id is not None:  # a deleted playbook leaves the plan's playbook_id NULL
        try:
            name = name_shown((await store.get(db, user_ref, plan.playbook_id)).name)
        except store.PlaybookStoreError:
            name = None
    saved_before = await check.plan_saved_before_adr247(db, plan)
    return {"playbook_id": plan.playbook_id, "playbook_name": name, "accepted_at": plan.accepted_at,
            **with_rupee_figures(_values(plan.body, saved_before, kind), plan.body, bases or Bases(),
                                 kind=kind, saved_before=saved_before)}


def _in_force_reply(found: in_force_mod.InForce) -> dict[str, Any]:
    """The reply fields of the ONE settings-in-force read; every field is copied, nothing is recomputed here."""
    def trig_label(label: str | None) -> Any:
        # the label is the PLAYBOOK body's own text (the user may edit it), never settings-registry text: it goes
        # through the playbook-trigger-label slot; a label that slot refuses (empty, a quote, too long) -> None and
        # the trigger ``id`` names it (fail visible, never a 500)
        if label is None:
            return None
        try:
            return render_explanation("adjust_condition_line_id", label=label)
        except (TypeError, ValueError):
            return None
    return {
        "settings": [dataclasses.asdict(x) for x in found.settings],
        "triggers": [{**dataclasses.asdict(t), "label": trig_label(t.label),
                      "weekly": None if t.weekly is None else list(t.weekly),
                      "monthly": None if t.monthly is None else list(t.monthly)} for t in found.triggers],
        "triggers_reason": found.triggers_reason,
        "stops": {"lines": [dataclasses.asdict(x) for x in found.stops.lines], "first": found.stops.first,
                  "reason": found.stops.reason}}


async def _sheet(db: Any, user_ref: str, strategy_id: int, stype: str | None, plan: store.Plan | None,  # noqa: PLR0913
                 pick: int | None, user_values: Any = None,
                 money: in_force_mod.MoneyInputs | None = None, kind: str | None = None,
                 bases: Bases | None = None) -> AdjustmentPlanOut:
    reply: dict[str, Any] = {"strategy_id": strategy_id, "type": stype, "type_name": None, "generic": stype is None,
                             "generic_text": render(_GENERIC) if stype is None else None, "playbooks": [],
                             "plan": None, "prefill": None, "labels": _labels()}
    if stype is None:
        none = check.Resolved("none", None, None, None, False, saved_before_adr247=False)
        found = in_force_mod.in_force(user_values, none, money)
        return AdjustmentPlanOut.model_validate(reply | _in_force_reply(found))
    active = await store.active_for(db, user_ref, stype)
    # the sheet shows the playbook that accepting would copy (``adjustment_check.resolve`` answers only the
    # strategy's own plan or "none"): the plan copy, else the user's active / the system one
    resolved = check.Resolved("plan", check.with_plan_target(plan.body), plan.playbook_id, None, False,
                              saved_before_adr247=await check.plan_saved_before_adr247(db,
                                                                                       plan)) if plan is not None else \
        check.Resolved("system" if active.is_system else "active", active.body, active.id,
                       active.status if active.is_system else None, active.is_system, saved_before_adr247=False)
    reply |= _in_force_reply(in_force_mod.in_force(user_values, resolved, money))
    listed = await store.list_for_type(db, user_ref, stype)
    chosen = active
    if pick is not None:
        found = next((p for p in listed if p.id == pick), None)
        if found is None:  # not of this type, not visible to the user, or missing
            raise _bad("playbook_id")
        chosen = found
    if plan is not None and pick is None:
        saved_before = await check.plan_saved_before_adr247(db, plan)
        values = with_rupee_figures(_values(plan.body, saved_before, kind), plan.body, bases or Bases(), kind=kind,
                                    saved_before=saved_before)
        source_id = plan.playbook_id if plan.playbook_id is not None else active.id
    else:
        values = with_rupee_figures(_values(chosen.body, False, kind), chosen.body, bases or Bases(), kind=kind)
        source_id = chosen.id  # a playbook, not a saved plan
        if (_t07_of(chosen.body) or {}).get("on") is False:  # ADR-305: the profit rule is off -> the box opens empty
            values |= {"target": None, "target_words": None}
    reply |= {"type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]),
              "playbooks": [_playbook_row(p, active.id) for p in listed],
              "plan": None if plan is None else await _plan_out(db, user_ref, plan, kind, bases),
              "prefill": {"playbook_id": source_id, **values}}
    return AdjustmentPlanOut.model_validate(reply)


async def _run(db: Any, work: Any) -> Any:
    """One unit: commit on success; a refusal or a failure rolls back (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except store.PlaybookStoreError as exc:
        await db.rollback()
        raise _refused(exc) from None
    except Exception:
        await db.rollback()
        raise
    return result


class LevelOut(ApiModel):
    percent: Money | None
    rupees: Money | None
    per_lot: Money | None
    words: CatalogueText | None  # the typed level in words (the percent), as the plan sheet shows it
    rupee_words: CatalogueText | None  # "Rs X for the whole trade (Rs Y per lot), before charges"


class LevelsOut(ApiModel):
    target: LevelOut | None
    stop: LevelOut | None


def preview_stop_words(body: dict | None, saved_before: bool, kind: str | None, bases: Bases,
                       typed_in: PlanIn) -> Any:
    """The stop sentence of the levels preview: the SAME builder the saved plan uses (``with_overrides`` then
    ``with_rupee_figures`` -> ``_stop_words``, which keeps the lines still in force), on a copy of the body with the typed
    level put in. Nothing is stored. None when there is no body to read the lines from."""
    if body is None:
        return None
    typed = with_overrides(body, typed_in, kind, bases)
    return with_rupee_figures(_values(typed, saved_before, kind), typed, bases, kind=kind,
                              saved_before=saved_before)["stop_words"]


def _level_out(percent_raw: str | None, rupees_raw: str | None, base: Decimal | None, lots: int | None,  # noqa: PLR0913
               field: str, words_id: str) -> dict[str, Any] | None:
    """One level from what was typed: percent and/or rupees (ADR-330 (5)); both must agree, else refused naming the
    rupee field. Nothing typed -> None. The server works both figures out; the browser prints them."""
    pct = None if percent_raw in (None, "") else Decimal(_percent(percent_raw, field.removesuffix("_rupees")))
    level = None if rupees_raw in (None, "") else _rupee_in(rupees_raw, field)
    if pct is not None and level is not None and not figs.agree(pct, level, base, lots):
        raise _bad(field)
    if level is not None and pct is None:
        found = figs.from_rupees(level, base, lots)
    elif pct is not None:
        found = figs.from_percent(pct, base, lots)
    else:
        return None
    words = None if found.percent is None else render_explanation(words_id, pct=format(found.percent, "f"))
    return {"percent": found.percent, "rupees": found.rupees, "per_lot": found.per_lot, "words": words,
            "rupee_words": _rupee_words(found)}


@router.get("/api/strategies/{strategy_id}/adjustment-plan/levels", response_model=LevelsOut)
async def read_levels(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        target: Annotated[str | None, Query(max_length=12)] = None,
        target_rupees: Annotated[str | None, Query(max_length=16)] = None,
        stop: Annotated[str | None, Query(max_length=12)] = None,
        stop_rupees: Annotated[str | None, Query(max_length=16)] = None) -> LevelsOut:
    """ADR-330 (5) / S-12: both figures of the typed level(s), worked out on the server, the per-lot figure beside the
    rupees. The last edited box is sent alone; both boxes with different values -> refused naming the rupee field."""
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    await release_connection(db)
    market = await _market(tracked, market_reader, ctx)
    bases = bases_of(tracked, market, rates)
    try:
        reply = {"target": _level_out(target, target_rupees, bases.max_profit, bases.lots, "target_rupees",
                                      "plan_target_words"),
                 "stop": _level_out(stop, stop_rupees, bases.max_loss, bases.lots, "stop_rupees",
                                    "plan_stop_words_loss")}
        if reply["stop"] is not None:  # the one stop sentence of the saved plan, for the level typed (ADR-330 (5)/LP-2)
            stype, plan = await _type_of(db, user_ref, strategy_id, tracked, ctx)
            body = None
            if plan is not None:
                body = plan.body
            elif stype is not None:
                body = (await store.active_for(db, user_ref, stype)).body
            kind = _kind_of(tracked, in_force_mod.money_inputs(tracked, market, rates))
            saved_before = plan is not None and await check.plan_saved_before_adr247(db, plan)
            words = preview_stop_words(body, saved_before, kind, bases,
                                       PlanIn(playbook_id=0, stop=stop or None, stop_rupees=stop_rupees or None))
            reply["stop"]["words"] = words if words is not None else reply["stop"]["words"]
    except store.PlaybookStoreError as exc:
        raise _refused(exc) from None
    return LevelsOut.model_validate(reply)


@router.get("/api/strategies/{strategy_id}/adjustment-plan", response_model=AdjustmentPlanOut)
async def read_plan(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        user_values: UserValuesIn,
        playbook_id: Annotated[int | None, Query(ge=1, le=ID_MAX)] = None) -> AdjustmentPlanOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    await release_connection(db)  # D-38: the market read waits on the broker; a held connection starves other pages
    market = await _market(tracked, market_reader, ctx)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, ctx)
    money = in_force_mod.money_inputs(tracked, market, rates)
    bases = bases_of(tracked, market, rates)

    async def work() -> AdjustmentPlanOut:
        return await _sheet(db, user_ref, strategy_id, stype, plan, playbook_id, user_values, money,
                            _kind_of(tracked, money), bases)
    return await _run(db, work)


async def _write(strategy_id: int, data: PlanIn, edit: bool, db: Any, user_ref: str,  # noqa: PLR0913
                 tracked_reader: TrackedReader, market_reader: MarketReader, rest_reader: RestSpotReader,
                 ctx: MarketContext | None, rates: ChargeRates | None, user_values: Any = None) -> AdjustmentPlanOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    await release_connection(db)  # D-38: the market read waits on the broker; a held connection starves other pages
    market = await _market(tracked, market_reader, ctx)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, ctx)
    money = in_force_mod.money_inputs(tracked, market, rates)
    bases = bases_of(tracked, market, rates)
    if stype is None:
        raise StrategyRefused(_GENERIC, Failure.CONFLICT)
    if edit and plan is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)

    async def work() -> AdjustmentPlanOut:
        if not 1 <= data.playbook_id <= ID_MAX:
            raise _bad("playbook_id")
        source = await store.get(db, user_ref, data.playbook_id)
        if source.strategy_type != stype:
            raise _bad("playbook_id")
        keep = edit and plan is not None and plan.playbook_id == source.id  # editing the plan keeps its own body
        body = with_overrides(plan.body if keep and plan is not None else source.body, data, _kind_of(tracked, money),
                              bases)
        if data.time_exit is not None:  # ADR-330 (7): the day is judged against today and the legs, never trusted
            legs = tracked.position.legs
            check_time_exit_day(body["guards"].get(TIME_KEY),
                                None if market is None else market.now.astimezone(IST).date(),
                                max((x.expiry for x in legs), default=None))
        saved = await store.accept_plan(db, user_ref, strategy_id, source.id, body, _base_json(tracked))
        # ADR-330 (1): the reply shows the base now STORED (the one the checks read), not the one read before the save
        stored = dataclasses.replace(tracked, stop_base=in_force_mod.stop_base_from_json(saved.stop_base))
        return await _sheet(db, user_ref, strategy_id, stype, saved, None, user_values,
                            in_force_mod.money_inputs(stored, market, rates), _kind_of(tracked, money),
                            dataclasses.replace(bases, max_loss=_stored_loss(stored, bases)))
    return await _run(db, work)


class RulesIn(_In):
    body: dict[str, Any]


def _rules_out(stype: str, body: dict, at: datetime.datetime) -> Any:
    """The trade's own rules in the editor's shape. ``id`` is 0 on purpose: this is no playbook row, so nothing
    can address a shared playbook through it (issue 7)."""
    return pb_routes.PlaybookFullOut.model_validate({
        "id": 0, "name": render_explanation("plan_rules_name", type=SHOWN_NAMES[stype]), "type": stype,
        "type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]), "is_system": False,
        "status": None, "draft": False, "active": False, "version": 1, "updated_at": at,
        "body": PlaybookBody.of(body), "situation_kinds": pb_routes.situation_kinds(body)})


def _t07_of(body: Any) -> Any:
    triggers = body.get("triggers") if isinstance(body, dict) else None
    return triggers.get("T-07") if isinstance(triggers, dict) else None


def _rules_to_save(base: dict, submitted: dict, is_plan: bool) -> dict:
    """ADR-304, "the last save wins": the editor showed ``with_plan_target(base)`` (a plan's Target overrides T-07's
    early
    and middle stages). T-07 as shown, unchanged -> the base's own T-07 and Target are kept (the Target keeps acting).
    T-07 changed (values or on/off) -> the user's T-07 is saved and the Target guard is left out (the form
    ``with_plan_target`` and ``_values`` already read as "no Target typed"), so the saved T-07 is what the check acts on
    and a T-07 switched off stays off. A Target typed later in the plan sheet wins again (``with_overrides``)."""
    shown = check.with_plan_target(base) if is_plan else base
    out = copy.deepcopy(submitted)
    if _t07_of(out) == _t07_of(shown):
        if _t07_of(base) is not None and isinstance(out.get("triggers"), dict):
            out["triggers"]["T-07"] = copy.deepcopy(_t07_of(base))
    elif isinstance(out.get("guards"), dict):
        out["guards"].pop(TARGET_KEY, None)
    return out


def _base_json(tracked: Any) -> dict | None:
    """ADR-330 (1): a plan save or edit stores the stop base worked out from the entry orders NOW (None: not worked
    out; the first check then works it out once, source "backfill")."""
    base = getattr(tracked, "entry_stop_base", None)
    return None if base is None else base.to_json()


async def _rules_scope(strategy_id: int, db: Any, user_ref: str, tracked_reader: TrackedReader,  # noqa: PLR0913
                       market_reader: MarketReader, rest_reader: RestSpotReader, ctx: MarketContext | None,
                       rates: ChargeRates | None) -> tuple[str, store.Plan | None, Any]:
    tracked = await _own_strategy(strategy_id, tracked_reader, rates if isinstance(rates, ChargeRates) else None)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, ctx)
    if stype is None:
        raise StrategyRefused(_GENERIC, Failure.CONFLICT)
    return stype, plan, tracked


@router.get("/api/strategies/{strategy_id}/adjustment-plan/rules", response_model=pb_routes.PlaybookFullOut)
async def read_rules(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> Any:
    """Issue 7 (REQ-158 AC-6): "Customise triggers" from a trade opens THIS trade's rules: its plan copy, else a copy of
    the type's active playbook that is written only when the user saves. Never a playbook row."""
    stype, plan, _ = await _rules_scope(strategy_id, db, user_ref, tracked_reader, market_reader, rest_reader, ctx,
                                        rates)

    async def work() -> Any:
        if plan is not None:  # the applied view: what the rule check reads (ADR-304), via the one function
            return _rules_out(stype, dict(check.with_plan_target(plan.body)), plan.accepted_at)
        active = await store.active_for(db, user_ref, stype)
        return _rules_out(stype, active.body, active.updated_at)
    return await _run(db, work)


@router.put("/api/strategies/{strategy_id}/adjustment-plan/rules", response_model=pb_routes.PlaybookFullOut)
async def save_rules(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, data: RulesIn, db: Annotated[Any, Depends(get_db)],
        user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> Any:
    """Save this trade's rules: the strategy's plan body only (``accept_plan`` writes the plan row; no playbook row)."""
    stype, plan, tracked = await _rules_scope(strategy_id, db, user_ref, tracked_reader, market_reader, rest_reader,
                                              ctx, rates)

    async def work() -> Any:
        try:
            pb_routes.precheck(stype, data.body)  # the editor's own check: body shape, keys, stage coverage
        except stages.StageProblem as exc:
            raise pb_routes.refused(exc) from None
        keep = plan is not None and plan.playbook_id is not None
        source_id = plan.playbook_id if keep and plan is not None else (await store.active_for(db, user_ref, stype)).id
        base = plan.body if plan is not None else (await store.active_for(db, user_ref, stype)).body
        saved = await store.accept_plan(
            db, user_ref, strategy_id, source_id, _rules_to_save(base, data.body, plan is not None),
            _base_json(tracked))
        return _rules_out(stype, dict(check.with_plan_target(saved.body)), saved.accepted_at)
    return await _run(db, work)


@router.post("/api/strategies/{strategy_id}/adjustment-plan", response_model=AdjustmentPlanOut)
async def accept_plan(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, data: PlanIn, db: Annotated[Any, Depends(get_db)],
        user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        user_values: UserValuesIn) -> AdjustmentPlanOut:
    """REQ-161 AC-2: accept the sheet (one click when only ``playbook_id`` is sent)."""
    return await _write(strategy_id, data, False, db, user_ref, tracked_reader, market_reader, rest_reader, ctx, rates,
                        user_values)


@router.put("/api/strategies/{strategy_id}/adjustment-plan", response_model=AdjustmentPlanOut)
async def edit_plan(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, data: PlanIn, db: Annotated[Any, Depends(get_db)],
        user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        user_values: UserValuesIn) -> AdjustmentPlanOut:
    """REQ-161 AC-3: edit the strategy's plan later (REQ-158 AC-5); 404 when it has none."""
    return await _write(strategy_id, data, True, db, user_ref, tracked_reader, market_reader, rest_reader, ctx, rates,
                        user_values)
