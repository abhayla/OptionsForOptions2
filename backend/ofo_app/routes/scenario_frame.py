"""DEV/TEST-ONLY: move a path scenario's shared frame index (IC e2e paper contract, design decision 2).

``POST /api/scenario/frame {frame}`` stores the frame in ``public.scenario_frames`` for the scenario the process runs
under; the API and the background worker read that row on every check (``scenario_mode.sync_frame``). Answer states:
scenario mode off -> 404 (the route does not exist for a live app); a frame outside 0..last -> 422
``scenario_frame_out_of_range`` (nothing stored); a one-snapshot ADJ scenario has only frame 0. No order, no Kite
call: the route is in ``scenario_mode.NON_ORDER_ROUTES``.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ofo_app import scenario_mode
from ofo_app.api_models import ApiModel, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.strategy_refused import StrategyRefused

router = APIRouter(route_class=ClosedRoute)
PATH = "/api/scenario/frame"


class FrameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame: int


class FrameOut(ApiModel):
    scenario_id: Identifier
    frame: int
    last: int


@router.post(PATH, response_model=FrameOut)
async def move_frame(body: FrameIn, db: Annotated[Any, Depends(get_db)]) -> FrameOut:
    sid = scenario_mode.current_id()
    if sid is None:
        raise StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
    last = scenario_mode.last_frame(sid)
    if isinstance(body.frame, bool) or not 0 <= body.frame <= last:
        raise StrategyRefused("scenario_frame_out_of_range")
    try:
        await scenario_mode.write_frame(db, sid, body.frame)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return FrameOut(scenario_id=sid, frame=body.frame, last=last)
