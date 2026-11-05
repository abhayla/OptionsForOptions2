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
from ofo.adjustment.playbook_text import name_shown
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.charges import ChargeRates
from ofo.errors import render
from ofo.errors.explanations import LABEL_TABLES, render_explanation
from ofo.settings import layers
from pydantic import BaseModel, ConfigDict

from ofo_app import adjustment_check as check
from ofo_app import playbook_store as store
from ofo_app import settings_in_force as in_force_mod
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.adjustment import (
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
)
from ofo_app.routes.adjustment_preferences import UserValuesIn
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import (
    MarketContext,
    get_market_context,
    judge_spot,
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
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
_COUNT = re.compile(r"[0-9]{1,3}")
#: The sheet field -> the guard of the plan's copy that holds it (docs/design/playbook-body-v1.md "guards")
TARGET_KEY = "profit_target_pct_of_max_profit"
#: the sheet's stop is the % of max loss trigger's value (ADR-252: ``settings_in_force.set_max_loss_stop`` /
#: ``sheet_stop``), never a guard key
EITHER_RULE = "whichever comes first"
MAX_KEY = "max_adjustments"
TIME_KEY = "time_exit"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PlanIn(_In):
    """Every sheet value arrives as the text typed (the browser forms no number, ADR-008): percents as decimal text,
    max adjustments as digits, the time exit as ``HH:MM``; each is checked here and names its field when not valid."""
    playbook_id: int
    target: str | None = None
    stop: str | None = None
    max_adjustments: str | None = None
    time_exit: str | None = None
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


class PlanOut(ApiModel):
    playbook_id: int | None
    playbook_name: CatalogueText | None
    target: Money | None
    stop: Money | None
    target_words: CatalogueText | None = None
    stop_words: CatalogueText | None = None
    max_adjustments: int | None
    time_exit: ClockOut | None
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
    found = _CLOCK.fullmatch(guards.get(TIME_KEY) or "")
    return None if found is None else ClockOut.model_validate({"hour": int(found[1]), "minute": int(found[2])})


_STOP_WORD_IDS = {in_force_mod.STOP_MAX_LOSS: "plan_stop_words_loss",
                  in_force_mod.STOP_CREDIT: "plan_stop_words_credit",
                  in_force_mod.STOP_MARGIN: "plan_stop_words_margin"}
_STOP_SLOTS = {in_force_mod.STOP_MAX_LOSS: "pct", in_force_mod.STOP_CREDIT: "multiple",
               in_force_mod.STOP_MARGIN: "margin"}
def _stop_words(body: dict, saved_before: bool) -> Any:
    """ADR-247/252: the ACTIVE stops from the ONE settings-in-force stops list (``settings_in_force.stops_of`` at the
    first stage: T-06 % of max loss, N x the credit received where it applies, T-16 % of margin only when on), joined
    "..., whichever comes first". Read for every plan, whatever guard keys its body holds."""
    lines = in_force_mod.stops_of(check.Resolved("plan", body, None, None, False, saved_before_adr247=saved_before),
                                  None, in_force_mod.FIRST_STAGE).lines
    parts = [render_explanation(_STOP_WORD_IDS[x.kind], **{_STOP_SLOTS[x.kind]: format(x.figure, "f")})
             for x in lines if x.active and x.figure is not None]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:  # noqa: PLR2004
        joined = render_explanation("plan_stop_words_or", a=parts[0], b=parts[1])
    else:
        joined = render_explanation("plan_stop_words_or3", a=parts[0], b=parts[1], c=parts[2])
    return render_explanation("plan_stop_words_first", words=joined)


def _words(body: dict, guards: dict, saved_before: bool) -> tuple[Any, Any]:
    """GC-ADJ2 item 3: what the target and the stop numbers ARE, in words from the catalogue (the number stays the
    input). The stop words come from the stops in force (ADR-247), not from the guards the body happens to hold."""
    target = _read_percent(guards, TARGET_KEY)
    t_words = None if target is None else render_explanation("plan_target_words", pct=format(target, "f"))
    return t_words, _stop_words(body, saved_before)


def _values(body: dict, saved_before: bool) -> dict[str, Any]:
    found = body.get("guards")
    guards: dict = found if isinstance(found, dict) else {}
    mx = guards.get(MAX_KEY)
    t_words, s_words = _words(body, guards, saved_before)
    return {"target": _read_percent(guards, TARGET_KEY), "stop": in_force_mod.sheet_stop(body),
            "target_words": t_words, "stop_words": s_words,
            "max_adjustments": mx if type(mx) is int else None, "time_exit": _read_clock(guards)}


def _set_stop(out: dict, raw: str) -> None:
    """ADR-252: the sheet's stop edit IS the T-06 value the live check reads (``settings_in_force``), every stage."""
    try:
        in_force_mod.set_max_loss_stop(out, _percent(raw, "stop"))
    except ValueError:
        raise _bad("stop") from None


def with_overrides(body: dict, data: PlanIn) -> dict:
    """A copy of ``body`` whose guards hold the sheet's values (a value left out stays as the body has it)."""
    out = copy.deepcopy(body)
    guards = out.setdefault("guards", {})
    if data.target is not None:
        guards[TARGET_KEY] = _percent(data.target, "target")
    if data.stop is not None:
        _set_stop(out, data.stop)
    if data.max_adjustments is not None:
        if not _COUNT.fullmatch(data.max_adjustments) or int(data.max_adjustments) > MAX_ADJUSTMENTS_LIMIT:
            raise _bad(MAX_KEY)
        guards[MAX_KEY] = int(data.max_adjustments)
    if data.time_exit is not None:
        if not _CLOCK.fullmatch(data.time_exit):
            raise _bad(TIME_KEY)
        guards[TIME_KEY] = data.time_exit
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


async def _type_of(db: Any, user_ref: str, strategy_id: int, tracked: Any, market_reader: MarketReader,  # noqa: PLR0913
                   rest_reader: RestSpotReader, ctx: MarketContext | None,
                   market: Any = None) -> tuple[str | None, store.Plan | None]:
    """The plan's type when there is a plan (a plan keeps its type), else the shape's, read as the check route does."""
    plan = await store.plan_for(db, user_ref, strategy_id)
    if plan is not None:
        return plan.strategy_type, plan
    if market is None:
        market = await market_reader(tracked, ctx)
    spot = judge_spot(market, await rest_reader(tracked.position.underlying), ctx)
    listed = None if ctx is None else ctx.provider.instrument_master()
    return check.strategy_type(tracked.position, spot.value if spot.available else None, listed), None


async def _plan_out(db: Any, user_ref: str, plan: store.Plan) -> dict[str, Any]:
    name = None
    if plan.playbook_id is not None:  # a deleted playbook leaves the plan's playbook_id NULL
        try:
            name = name_shown((await store.get(db, user_ref, plan.playbook_id)).name)
        except store.PlaybookStoreError:
            name = None
    return {"playbook_id": plan.playbook_id, "playbook_name": name, "accepted_at": plan.accepted_at,
            **_values(plan.body, await check.plan_saved_before_adr247(db, plan))}


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
                 money: in_force_mod.MoneyInputs | None = None) -> AdjustmentPlanOut:
    reply: dict[str, Any] = {"strategy_id": strategy_id, "type": stype, "type_name": None, "generic": stype is None,
                             "generic_text": render(_GENERIC) if stype is None else None, "playbooks": [],
                             "plan": None, "prefill": None, "labels": _labels()}
    if stype is None:
        none = check.Resolved("none", None, None, None, False, saved_before_adr247=False)
        found = in_force_mod.in_force(user_values, none, money)
        return AdjustmentPlanOut.model_validate(reply | _in_force_reply(found))
    active = await store.active_for(db, user_ref, stype)
    # the playbook in force (as ``adjustment_check.resolve``): the plan copy, else the user's active / the system one
    resolved = check.Resolved("plan", plan.body, plan.playbook_id, None, False,
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
        values = _values(plan.body, saved_before)
        source_id = plan.playbook_id if plan.playbook_id is not None else active.id
    else:
        values, source_id = _values(chosen.body, False), chosen.id  # a playbook, not a saved plan
    reply |= {"type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]),
              "playbooks": [_playbook_row(p, active.id) for p in listed],
              "plan": None if plan is None else await _plan_out(db, user_ref, plan),
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
    market = await _market(tracked, market_reader, ctx)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, market_reader, rest_reader, ctx, market)
    money = in_force_mod.money_inputs(tracked, market, rates)

    async def work() -> AdjustmentPlanOut:
        return await _sheet(db, user_ref, strategy_id, stype, plan, playbook_id, user_values, money)
    return await _run(db, work)


async def _write(strategy_id: int, data: PlanIn, edit: bool, db: Any, user_ref: str,  # noqa: PLR0913
                 tracked_reader: TrackedReader, market_reader: MarketReader, rest_reader: RestSpotReader,
                 ctx: MarketContext | None, rates: ChargeRates | None, user_values: Any = None) -> AdjustmentPlanOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    market = await _market(tracked, market_reader, ctx)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, market_reader, rest_reader, ctx, market)
    money = in_force_mod.money_inputs(tracked, market, rates)
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
        body = with_overrides(plan.body if keep and plan is not None else source.body, data)
        saved = await store.accept_plan(db, user_ref, strategy_id, source.id, body)
        return await _sheet(db, user_ref, strategy_id, stype, saved, None, user_values, money)
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
