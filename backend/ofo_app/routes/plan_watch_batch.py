"""GET /api/plan-watch?strategy_ids=1,2,3: the Plan watch of a whole Positions list in ONE request (Lane H, 27 Nov 2026;
REQ-049 AC-4; ADR-330 (13)). The page asked once per row; each ask was its own HTTP request, auth, market context and
connection, and the checks piled up on the API's event loop (10 at once: median 525 ms, 20: 1006 ms).

Per row the answer is the single route's: ``watch_of`` (the same ``run_check``, never a second evaluation), or
that route's refusal for that row (its message and status, from ``row_answer``). One bad row never fails the others
(fail closed per row). The caller's own strategies only: a row not theirs is the same 404 the single route gives.
Rows run one after another with a yield between them, so the loop stays free for stops, alerts and other requests.
Writes nothing. Suggest-only (ADR-003).
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from ofo.charges import ChargeRates

from ofo_app.api_models import ApiModel, CatalogueText
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, refuse_request, row_answer
from ofo_app.routes.adjustment import (
    ApproachMargin,
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_approach_margin,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
)
from ofo_app.routes.adjustment_preferences import UserPreferences, UserValuesIn
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from ofo_app.routes.plan_watch import PlanWatchOut, watch_of

router = APIRouter(route_class=ClosedRoute)
MAX_ROWS = 20


class PlanWatchItemOut(ApiModel):
    """One row: ``watch`` when ``state`` is "ok"; else ``refusal`` (the message the single route shows) and its HTTP
    ``status`` (404 not found, 409 ..., 500)."""

    strategy_id: int
    state: Literal["ok", "refused"]
    watch: PlanWatchOut | None = None
    refusal: CatalogueText | None = None
    status: int | None = None


class PlanWatchBatchOut(ApiModel):
    as_of: datetime.datetime | None  # the newest row's as-of; None when no row was answered
    items: list[PlanWatchItemOut]


def _ids_of(raw: str) -> list[int]:
    """The asked ids, in order, each once; anything not 1 to MAX_ROWS whole positive numbers is the 422 of a request
    the API cannot read."""
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        refuse_request(("query", "strategy_ids"), "int_parsing", raw)
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_ROWS or any(i < 1 for i in ids):
        refuse_request(("query", "strategy_ids"), "value_error", raw)
    return ids


@router.get("/api/plan-watch", response_model=PlanWatchBatchOut)
async def plan_watch_batch(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_ids: Annotated[str, Query(max_length=200)], *,
        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        prefs: UserPreferences, user_values: UserValuesIn) -> PlanWatchBatchOut:
    items: list[dict] = []
    for sid in _ids_of(strategy_ids):
        try:
            watch = await watch_of(sid, db=db, user_ref=user_ref, tracked_reader=tracked_reader,
                                   market_reader=market_reader, rest_reader=rest_reader, margin_of=margin_of, ctx=ctx,
                                   rates=rates, prefs=prefs, user_values=user_values)
            items.append({"strategy_id": sid, "state": "ok", "watch": watch})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one row's failure is that row's refusal, never the whole reply
            message, status = row_answer(exc, f"GET /api/plan-watch row {sid}")
            items.append({"strategy_id": sid, "state": "refused", "refusal": message, "status": status})
            rollback = getattr(db, "rollback", None)
            if rollback is not None:  # a failed statement leaves the shared session unusable for the next row
                await rollback()
        await asyncio.sleep(0)  # let the loop serve a stop, an alert or another request between two checks
    as_of = max((i["watch"].as_of for i in items if i["state"] == "ok"), default=None)
    return PlanWatchBatchOut.model_validate({"as_of": as_of, "items": items})
