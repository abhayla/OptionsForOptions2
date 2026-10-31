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
from ofo.marketdata.spot_source import resolve_spot
from pydantic import BaseModel, ConfigDict

from ofo_app import adjustment_check as check
from ofo_app import playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
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
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_NOT_AVAILABLE = "user_input_request_not_available"
_GENERIC = "adjust_plan_no_playbook"
ID_MAX = 9_223_372_036_854_775_807  # the id column is BIGSERIAL
MAX_ADJUSTMENTS_LIMIT = 10
_PERCENT = re.compile(r"[0-9]{1,3}(\.[0-9]{1,4})?")
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
#: The sheet field -> the guard of the plan's copy that holds it (docs/design/playbook-body-v1.md "guards")
TARGET_KEY = "profit_target_pct_of_max_profit"
STOP_KEY = "stop_line_pct_of_max_loss"
MAX_KEY = "max_adjustments"
TIME_KEY = "time_exit"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClockIn(_In):
    hour: int
    minute: int


class PlanIn(_In):
    playbook_id: int
    target: str | None = None
    stop: str | None = None
    max_adjustments: int | None = None
    time_exit: ClockIn | None = None


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
    target: Decimal | None
    stop: Decimal | None
    max_adjustments: int | None
    time_exit: ClockOut | None


class PlanOut(ApiModel):
    playbook_id: int | None
    playbook_name: CatalogueText | None
    target: Decimal | None
    stop: Decimal | None
    max_adjustments: int | None
    time_exit: ClockOut | None
    accepted_at: datetime.datetime


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


def _values(body: dict) -> dict[str, Any]:
    guards = body.get("guards") if isinstance(body.get("guards"), dict) else {}
    mx = guards.get(MAX_KEY)
    return {"target": _read_percent(guards, TARGET_KEY), "stop": _read_percent(guards, STOP_KEY),
            "max_adjustments": mx if type(mx) is int else None, "time_exit": _read_clock(guards)}


def with_overrides(body: dict, data: PlanIn) -> dict:
    """A copy of ``body`` whose guards hold the sheet's values (a value left out stays as the body has it)."""
    out = copy.deepcopy(body)
    guards = out.setdefault("guards", {})
    if data.target is not None:
        guards[TARGET_KEY] = _percent(data.target, "target")
    if data.stop is not None:
        guards[STOP_KEY] = _percent(data.stop, "stop")
    if data.max_adjustments is not None:
        if not 0 <= data.max_adjustments <= MAX_ADJUSTMENTS_LIMIT:
            raise _bad(MAX_KEY)
        guards[MAX_KEY] = data.max_adjustments
    if data.time_exit is not None:
        if not (0 <= data.time_exit.hour <= 23 and 0 <= data.time_exit.minute <= 59):  # noqa: PLR2004 - a clock
            raise _bad(TIME_KEY)
        guards[TIME_KEY] = f"{data.time_exit.hour:02d}:{data.time_exit.minute:02d}"
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


async def _type_of(db: Any, user_ref: str, strategy_id: int, tracked: Any, market_reader: MarketReader,  # noqa: PLR0913
                   rest_reader: RestSpotReader, ctx: MarketContext | None) -> tuple[str | None, store.Plan | None]:
    """The plan's type when there is a plan (a plan keeps its type), else the shape's, read as the check route does."""
    plan = await store.plan_for(db, user_ref, strategy_id)
    if plan is not None:
        return plan.strategy_type, plan
    market = await market_reader(tracked, ctx)
    spot = resolve_spot(market.feed, await rest_reader(tracked.position.underlying), market.last_close, now=market.now)
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
            **_values(plan.body)}


async def _sheet(db: Any, user_ref: str, strategy_id: int, stype: str | None, plan: store.Plan | None,  # noqa: PLR0913
                 pick: int | None) -> AdjustmentPlanOut:
    reply: dict[str, Any] = {"strategy_id": strategy_id, "type": stype, "type_name": None, "generic": stype is None,
                             "generic_text": render(_GENERIC) if stype is None else None, "playbooks": [],
                             "plan": None, "prefill": None, "labels": _labels()}
    if stype is None:
        return AdjustmentPlanOut.model_validate(reply)
    active = await store.active_for(db, user_ref, stype)
    listed = await store.list_for_type(db, user_ref, stype)
    chosen = active
    if pick is not None:
        found = next((p for p in listed if p.id == pick), None)
        if found is None:  # not of this type, not visible to the user, or missing
            raise _bad("playbook_id")
        chosen = found
    if plan is not None and pick is None:
        values, source_id = _values(plan.body), plan.playbook_id if plan.playbook_id is not None else active.id
    else:
        values, source_id = _values(chosen.body), chosen.id
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
        playbook_id: Annotated[int | None, Query(ge=1, le=ID_MAX)] = None) -> AdjustmentPlanOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, market_reader, rest_reader, ctx)

    async def work() -> AdjustmentPlanOut:
        return await _sheet(db, user_ref, strategy_id, stype, plan, playbook_id)
    return await _run(db, work)


async def _write(strategy_id: int, data: PlanIn, edit: bool, db: Any, user_ref: str,  # noqa: PLR0913
                 tracked_reader: TrackedReader, market_reader: MarketReader, rest_reader: RestSpotReader,
                 ctx: MarketContext | None, rates: ChargeRates | None) -> AdjustmentPlanOut:
    rates = rates if isinstance(rates, ChargeRates) else None
    tracked = await _own_strategy(strategy_id, tracked_reader, rates)
    stype, plan = await _type_of(db, user_ref, strategy_id, tracked, market_reader, rest_reader, ctx)
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
        return await _sheet(db, user_ref, strategy_id, stype, saved, None)
    return await _run(db, work)


@router.post("/api/strategies/{strategy_id}/adjustment-plan", response_model=AdjustmentPlanOut)
async def accept_plan(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, data: PlanIn, db: Annotated[Any, Depends(get_db)],
        user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> AdjustmentPlanOut:
    """REQ-161 AC-2: accept the sheet (one click when only ``playbook_id`` is sent)."""
    return await _write(strategy_id, data, False, db, user_ref, tracked_reader, market_reader, rest_reader, ctx, rates)


@router.put("/api/strategies/{strategy_id}/adjustment-plan", response_model=AdjustmentPlanOut)
async def edit_plan(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, data: PlanIn, db: Annotated[Any, Depends(get_db)],
        user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> AdjustmentPlanOut:
    """REQ-161 AC-3: edit the strategy's plan later (REQ-158 AC-5); 404 when it has none."""
    return await _write(strategy_id, data, True, db, user_ref, tracked_reader, market_reader, rest_reader, ctx, rates)
