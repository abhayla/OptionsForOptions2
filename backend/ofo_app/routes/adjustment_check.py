"""GET /api/strategies/{id}/adjustment-check (GC-ADJ2 step 1C; REQ-158 AC-5, REQ-159 AC-2, REQ-160 AC-3, REQ-045 AC-1,
F-71): the tracked strategy's playbook evaluated now, through the adjustment-approaches route's own seams (tracked
strategy, market, REST spot, margin, charge rates); the logic is ``ofo_app.adjustment_check``.

Answer states: strategy not found / another user's -> the approaches route's not-found answer; legs unreadable
(TrackedUnreadable) -> its refusal; type None -> playbook source ``none`` and no results; not connected or no spot ->
every rule ``not_checked`` with its reason (never a 500, never a flag). Suggest-only (ADR-003): nothing here places an
order. Wording: a system playbook's flag is "Adjustment opportunity detected", the user's own playbook or plan's "Your
rule was triggered" (REQ-045 AC-1, Q252); a rule true at entry is "Already true when tracking started" (F-71).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.charges import ChargeRates
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.marketdata.spot_source import resolve_spot

from ofo_app import adjustment_check as check
from ofo_app import scenario_mode
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
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
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
    name: Identifier | None
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


class AdjustmentCheckOut(ApiModel):
    strategy_id: int
    strategy_type: Identifier | None
    type_name: CatalogueText | None
    playbook: CheckPlaybookOut
    stage: CheckStageOut
    withheld: CatalogueText | None
    results: list[CheckResultOut]


def _num(v: Decimal | str | None) -> Decimal | None:
    return v if isinstance(v, Decimal) else None  # a clock value or UNLIMITED is not a number


def result_out(r: pe.Result, flag_wording: Any) -> dict:
    if isinstance(r, pe.Flag):
        return {"kind": "flag", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": r.cmp, "value": _num(r.value),
                "threshold": _num(r.threshold), "reason": None, "wording": flag_wording}
    if isinstance(r, pe.AlreadyTrue):
        return {"kind": "already_true", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": None,
                "value": _num(r.value), "threshold": _num(r.threshold), "reason": None, "wording": render(r.code)}
    return {"kind": "not_checked", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": None, "value": None,
            "threshold": None, "reason": render(r.code, **dict(r.slots)), "wording": None}


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
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> AdjustmentCheckOut:
    from ofo_app.adjustment_readers import TrackedUnreadable  # noqa: PLC0415 - it imports routes.adjustment
    rates = rates if isinstance(rates, ChargeRates) else None
    try:
        tracked = await tracked_reader(strategy_id, rates)
    except TrackedUnreadable as exc:
        log.warning("adjustment check: strategy %s unreadable: %s", strategy_id, exc)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    if tracked is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    market = await market_reader(tracked, ctx)
    spot = resolve_spot(market.feed, await rest_reader(tracked.position.underlying), market.last_close, now=market.now)
    listed = None if ctx is None else ctx.provider.instrument_master()
    stype = check.strategy_type(tracked.position, spot.value if spot.available else None, listed)
    resolved = await check.resolve(db, user_ref, strategy_id, stype)
    reply: dict[str, Any] = {
        "strategy_id": strategy_id, "strategy_type": stype,
        "type_name": None if stype is None else render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]),
        "playbook": {"source": resolved.source, "id": resolved.playbook_id, "status": resolved.status,
                     "draft": resolved.status == "draft"},
        "stage": {"name": None, "index": None}, "withheld": None, "results": []}
    if resolved.body is None:
        return AdjustmentCheckOut.model_validate(reply)
    margin = await current_margin(margin_of, tracked, market)
    state = check.state_of(tracked, market, spot, margin, rates, check.prices_fresh(ctx), resolved.body)
    ev = await check.evaluate_and_remember(db, user_ref, strategy_id, resolved.body, state, scenario_mode.current(),
                                           tracked.position)
    await db.commit()
    wording = render_explanation("adjust_check_flag_system" if resolved.is_system else "adjust_check_flag_user")
    reply |= {"stage": {"name": ev.stage_name, "index": ev.stage_index},
              "withheld": None if ev.withheld is None else render(ev.withheld),
              "results": [result_out(r, wording) for r in ev.results]}
    return AdjustmentCheckOut.model_validate(reply)
