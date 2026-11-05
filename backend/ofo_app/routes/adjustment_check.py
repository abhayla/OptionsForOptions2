"""GET /api/strategies/{id}/adjustment-check (GC-ADJ2 step 1C; REQ-158 AC-5, REQ-159 AC-2, REQ-160 AC-3, REQ-045 AC-1,
F-71): the tracked strategy's playbook evaluated now, through the adjustment-approaches route's own seams (tracked
strategy, market, REST spot, margin, charge rates); the logic is ``ofo_app.adjustment_check``.

Answer states: strategy not found / another user's -> the approaches route's not-found answer; legs unreadable
(TrackedUnreadable) -> its refusal; type None -> playbook source ``none`` and no results; not connected or no spot ->
every rule ``not_checked`` with its reason (never a 500, never a flag); the records' store unreadable -> a refusal
(503), never an empty list. ADR-237 (6): this check writes NOTHING (no record, no lapse, no rule memory: only the
background worker writes, through the alert gate); it shows the current condition and the stored records.
Suggest-only (ADR-003): nothing here places an order. Wording: a system playbook's flag is "Adjustment opportunity
detected", the user's own playbook or plan's "Your rule was triggered" (REQ-045 AC-1, Q252); a rule true at entry is
"Already true when tracking started" (F-71).
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.charges import ChargeRates
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.timeutil import IST
from sqlalchemy.exc import SQLAlchemyError

from ofo_app import adjustment_check as check
from ofo_app import playbook_store, scenario_mode
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.outcome_margin import PlannedOrderIn
from ofo_app.routes.adjustment import (
    ApproachMargin,
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_approach_margin,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
    margin_block,
)
from ofo_app.routes.adjustment_preferences import UserPreferences, UserValuesIn
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


class CheckPlaybookOut(ApiModel):
    source: Literal["plan", "active", "system", "none"]
    id: int | None
    status: Literal["approved", "draft"] | None
    draft: bool


class CheckStageOut(ApiModel):
    name: CatalogueText | None  # the stage name as the user typed it (spaces allowed)
    index: int | None


class CheckResultOut(ApiModel):
    kind: Literal["flag", "not_checked", "already_true"]
    rule_id: Identifier
    trigger_id: Identifier
    cmp: Literal["le", "ge", "lt"] | None
    value: Money | None  # None for a clock trigger (T-10b) and for a not-checked rule
    threshold: Money | None
    reason: CatalogueText | None
    wording: CatalogueText | None
    condition: CatalogueText | None = None  # the condition in words, from the body's label and unit
    suggestion_id: int | None = None  # a flag's open REQ-112 record (Dismiss / acted on name it)
    note: CatalogueText | None = None  # ADR-217: "You dismissed this" on a flag whose dismissed record still holds


class CheckPauseOut(ApiModel):
    until: Identifier  # HHMM IST, e.g. 1030 (an Identifier has no ':')
    text: CatalogueText


class AdjustmentCheckOut(ApiModel):
    strategy_id: int
    strategy_type: Identifier | None
    type_name: CatalogueText | None
    playbook: CheckPlaybookOut
    stage: CheckStageOut
    withheld: CatalogueText | None
    results: list[CheckResultOut]
    #: A-38 (GC-IC1 4a): the user's pause in force at the check's own time -> {until, text} and no evaluation (the
    #: worker skips it too); none, cleared or expired -> None
    paused: CheckPauseOut | None = None


async def pause_in_force(db: Any, user_ref: str, strategy_id: int, now: datetime.datetime) -> dict | None:
    """The check's pause block at ``now`` (the market reader's clock, the check's own time); None when not paused."""
    from ofo.adjustment import monitor_pause  # noqa: PLC0415 - A-38

    from ofo_app import strategy_pause_store  # noqa: PLC0415 - A-38
    until = await strategy_pause_store.pause_of(db, user_ref, strategy_id)
    if until is None or not monitor_pause.in_force(until, now):
        return None
    end = until.astimezone(IST).time().replace(second=0, microsecond=0)
    return {"until": f"{end:%H%M}", "text": render_explanation("monitor_pause_shown", time=end)}


#: the shown scale of a check value and threshold (the scenario fixtures' "0.3416" / "0.5000"); the evaluator keeps
#: the exact values, only the answer is rounded (half-up, GC-ADJ2 step 5 item 1)
SHOWN_PLACES = Decimal("0.0001")


def _num(v: Decimal | str | None) -> Decimal | None:
    if not isinstance(v, Decimal):  # a clock value or UNLIMITED is not a number
        return None
    return v.quantize(SHOWN_PLACES, rounding=ROUND_HALF_UP)


def _condition(r: pe.Flag | pe.AlreadyTrue, body: Mapping | None,
               cheapest: tuple[str, Decimal, int] | None = None) -> Any:
    """The condition in words from the evaluated body's own label and unit; None without a comparison. T-19 also names
    the cheapest offered approach and its cost (``cheapest``, ADR-221)."""
    if r.cmp is None:
        return None
    value, threshold = _num(r.value), _num(r.threshold)
    label, unit = check.trigger_words(body, r.trigger_id)
    shown = str(r.value) if value is None else str(value)
    limit = str(r.threshold) if threshold is None else str(threshold)
    if r.trigger_id == "T-19" and cheapest is not None:
        return check.condition_line_t19(label, shown, limit, *cheapest)
    return check.condition_line(r.trigger_id, label, unit, shown, limit)


def result_out(r: pe.Result, flag_wording: Any, opened: dict[str, int] | None = None, *,  # noqa: PLR0913
               dismissed: frozenset[str] = frozenset(), body: Mapping | None = None,
               cheapest: tuple[str, Decimal, int] | None = None) -> dict:
    # dismissed and body are keyword-only: a positional body once landed in dismissed (TypeError on a None body)
    if isinstance(r, pe.Flag):
        return {"kind": "flag", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": r.cmp, "value": _num(r.value),
                "threshold": _num(r.threshold), "reason": None, "wording": flag_wording,
                "condition": _condition(r, body, cheapest), "suggestion_id": (opened or {}).get(r.rule_id),
                "note": render_explanation("suggestion_outcome_dismissed") if r.rule_id in dismissed else None}
    if isinstance(r, pe.AlreadyTrue):
        return {"kind": "already_true", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": r.cmp,
                "value": _num(r.value), "threshold": _num(r.threshold), "reason": None, "wording": render(r.code),
                "condition": _condition(r, body, cheapest)}
    return {"kind": "not_checked", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": None, "value": None,
            "threshold": None, "reason": render(r.code, **dict(r.slots)), "wording": None}


def t19_record(trigger_id: str, cheapest: tuple[str, Decimal, int] | None) -> dict:
    """ADR-221: a T-19 record keeps the approach, cost and unpriced count it was shown with (the list draws them)."""
    if trigger_id != "T-19" or cheapest is None:
        return {}
    return {"approach": cheapest[0], "approach_cost": cheapest[1], "unpriced": cheapest[2]}


def cheapest(state: pe.StrategyState) -> tuple[str, Decimal, int] | None:
    """The T-19 approach, cost and unpriced count the check used (ADR-221); None when it had none."""
    if state.adjustment_approach is None or state.adjustment_cost is None:
        return None
    return state.adjustment_approach, state.adjustment_cost, state.adjustment_unpriced


async def stored_records(db: Any, user_ref: str, strategy_id: int,
                         ev: pe.Evaluation) -> tuple[dict[str, int], frozenset[str]]:
    """ADR-237 (6): the screen READS the records; only the background worker opens and lapses them, through the one
    gate (``ofo.adjustment.alert_gate``, stored by ``background.DbGateStore``). Returns (rule id -> id of its open
    record, for each flagged rule that has one; the flagged rules whose latest record is dismissed and none is open,
    for the ADR-217 "You dismissed this" note). Writes nothing. A store read that fails raises
    ``StrategyRefused`` (never an empty answer that would read as "nothing is open")."""
    flagged = {r.rule_id for r in ev.results if isinstance(r, pe.Flag)}
    try:
        open_now = {rec.rule_id: rec.id for rec in await playbook_store.open_suggestions(db, user_ref, strategy_id)}
        held = await playbook_store.dismissed_holding(db, user_ref, strategy_id)
    except SQLAlchemyError as exc:
        log.warning("adjustment check: records of strategy %s unreadable: %s", strategy_id, type(exc).__name__)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.UPSTREAM_BUSY) from None
    opened = {rid: sid for rid, sid in open_now.items() if rid in flagged}
    return opened, frozenset(rid for rid in held if rid in flagged and rid not in opened)


async def current_margin(margin_of: ApproachMargin, tracked: Any, market: Any) -> dict | None:
    try:
        legs = [PlannedOrderIn(market.instrument_ids[x.tradingsymbol], x.side, x.lots, x.entry)
                for x in tracked.position.legs]
        return margin_block(await margin_of(legs))
    except Exception:  # noqa: BLE001 - a margin read failing is "margin not stated" (T-16 not checked), never a 500
        log.warning("adjustment check: margin read failed")
        return None


@router.get("/api/strategies/{strategy_id}/adjustment-check", response_model=AdjustmentCheckOut)
async def adjustment_check(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int,
        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        prefs: UserPreferences, user_values: UserValuesIn) -> AdjustmentCheckOut:
    from ofo_app.adjustment_readers import (  # noqa: PLC0415 - imports routes.adjustment
        TrackedExited,
        TrackedUnreadable,
        entry_facts_in,
    )
    rates = rates if isinstance(rates, ChargeRates) else None
    try:
        tracked = await tracked_reader(strategy_id, rates)
    except TrackedExited:  # every leg exited: the worker lapses its open records (REQ-112 AC-2; ADR-237 (6))
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    except TrackedUnreadable as exc:
        log.warning("adjustment check: strategy %s unreadable: %s", strategy_id, exc)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    if tracked is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    market = await market_reader(tracked, ctx)
    spot = judge_spot(market, await rest_reader(tracked.position.underlying), ctx)
    listed = check.listed_of(ctx)
    stype = check.strategy_type(tracked.position, spot.value if spot.available else None, listed)
    resolved = await check.resolve(db, user_ref, strategy_id, stype)
    reply: dict[str, Any] = {
        "strategy_id": strategy_id, "strategy_type": stype,
        "type_name": None if stype is None else render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]),
        "playbook": {"source": resolved.source, "id": resolved.playbook_id, "status": resolved.status,
                     "draft": resolved.draft},
        "stage": {"name": None, "index": None}, "withheld": None, "results": []}
    reply["paused"] = await pause_in_force(db, user_ref, strategy_id, market.now)
    if resolved.body is None or reply["paused"] is not None:  # A-38: paused -> shown with its end, not evaluated
        return AdjustmentCheckOut.model_validate(reply)
    margin = await current_margin(margin_of, tracked, market)
    # ADR-245: the carry gap in force (plan, else the user's own, else the admin default) is resolved inside state_of
    # ADR-243: the roll basis in force is resolved inside state_of too, from the same layers and the stored entry facts
    state = check.state_of(tracked, market, spot, margin, rates, check.prices_fresh(ctx), resolved.body,
                           config=prefs.approach, user_values=user_values, strategy_layer=resolved.strategy_layer,
                           entry_facts=await entry_facts_in(db, strategy_id), resolved=resolved)
    # read-only (review round 2, finding 3): evaluated against the stored rule memory, NOTHING written; the background
    # worker is the one writer of rule memory and records (ADR-237 (6)), so the two never disagree about a dip
    ev, _memory = await check.evaluate_stored(db, user_ref, strategy_id, resolved.body, state, scenario_mode.current(),
                                              tracked.position, gap_until=prefs.gap_until)
    opened, dismissed = await stored_records(db, user_ref, strategy_id, ev)
    wording = render_explanation("adjust_check_flag_system" if resolved.is_system else "adjust_check_flag_user")
    reply |= {"stage": check.stage_out(ev.stage_name, ev.stage_index),
              "withheld": None if ev.withheld is None else render(ev.withheld),
              "results": [result_out(r, wording, opened, dismissed=dismissed, body=resolved.body,
                                    cheapest=cheapest(state)) for r in ev.results]}
    return AdjustmentCheckOut.model_validate(reply)
