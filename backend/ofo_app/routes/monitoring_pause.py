"""GET / PUT / DELETE /api/strategies/{id}/monitoring-pause: A-38, pause adjustment checks of one strategy until a time
today (GC-IC1 step 4a).

Spec basis: REQ-170 AC-5 (risk exits are never paused: the paper exit path never reads this pause); REQ-168 AC-3
(keyed by the user). Copy from: ``routes/alert_style.py`` (same key, same store shape, same refusals).

- GET: {strategy_id, label, paused, until (HHMM IST or null), state_text}.
- PUT {until: "HH:MM"}: a pause until that time today (IST), then the GET reply. Refused with its reason (422): not a
  time, at or before now, after the session close. The time "now" is the database clock (ADR-023).
- DELETE: the pause cleared now, then the GET reply.
- Answer states of the reply: none (never paused, or cleared) -> paused false, ``monitor_pause_none``; set and in force
  -> paused true with its end, ``monitor_pause_until``; set and expired -> paused false, ``monitor_pause_ended`` with
  the end; another user's or a missing strategy -> 404 (a pause set by another user is never shown or changed); the
  same instant twice -> 409.
"""
from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from ofo.adjustment import monitor_pause
from ofo.errors.explanations import render_explanation
from ofo.timeutil import IST
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app import settings_store
from ofo_app import strategy_pause_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure, respond
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
Db = Annotated[AsyncSession, Depends(get_db)]
_NOT_AVAILABLE = "user_input_request_not_available"
PATH = "/api/strategies/{strategy_id}/monitoring-pause"
REFUSAL_TEXT = {
    monitor_pause.Refusal.NO_ZONE: "monitor_pause_refused_not_a_time",
    monitor_pause.Refusal.IN_PAST: "monitor_pause_refused_in_past",
    monitor_pause.Refusal.NOT_TODAY: "monitor_pause_refused_in_past",
    monitor_pause.Refusal.AFTER_CLOSE: "monitor_pause_refused_after_close",
}


class PauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    until: str


class PauseOut(ApiModel):
    strategy_id: int
    label: CatalogueText
    paused: bool
    until: Identifier | None  # HHMM IST, e.g. 1030 (an Identifier has no colon)
    state_text: CatalogueText


class RefusedOut(ApiModel):
    reason: CatalogueText


def _hhmm(at: datetime.datetime) -> str:
    return f"{at.astimezone(IST):%H%M}"


def compose(strategy_id: int, until: datetime.datetime | None, now: datetime.datetime) -> PauseOut:
    """The reply's answer state from the stored end and ``now`` (pure; module docstring)."""
    label = render_explanation("monitor_pause_label")
    if until is None:
        return PauseOut(strategy_id=strategy_id, label=label, paused=False, until=None,
                        state_text=render_explanation("monitor_pause_none"))
    held = monitor_pause.in_force(until, now)
    end = until.astimezone(IST).time().replace(second=0, microsecond=0)
    text = render_explanation("monitor_pause_until" if held else "monitor_pause_ended", time=end)
    return PauseOut(strategy_id=strategy_id, label=label, paused=held, until=_hhmm(until), state_text=text)


def parse_until(value: str, now: datetime.datetime) -> datetime.datetime:
    """``HH:MM`` today (IST, the day of ``now``); PauseRefused(NO_ZONE) when it is not a time."""
    try:
        if len(value) != 5 or value[2] != ":":  # noqa: PLR2004 - the HH:MM shape
            raise ValueError(value)
        clock = datetime.time.fromisoformat(value)
    except ValueError:
        raise monitor_pause.PauseRefused(monitor_pause.Refusal.NO_ZONE) from None
    return datetime.datetime.combine(now.astimezone(IST).date(), clock, IST)


async def _read(db: AsyncSession, user: str, strategy_id: int) -> datetime.datetime | None:
    try:
        return await store.pause_of(db, user, strategy_id)
    except store.PauseNotFound:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND) from None


async def pause_now(db: Db) -> datetime.datetime:
    """The route's "now": the database clock (ADR-023); a seam so a test pins the time of day."""
    return await settings_store.database_now(db)


Now = Annotated[datetime.datetime, Depends(pause_now)]
User = Annotated[str, Depends(current_user_ref)]


def _refusal(reason: monitor_pause.Refusal) -> Any:
    """The 422 answer for a refused pause: the catalogue sentence for the refusal code, never the exception text."""
    return respond(RefusedOut(reason=render_explanation(REFUSAL_TEXT[reason])), 422)


@router.get(PATH, response_model=PauseOut)
async def read_pause(strategy_id: int, db: Db, user: User, now: Now) -> Any:
    return compose(strategy_id, await _read(db, user, strategy_id), now)


@router.put(PATH, response_model=PauseOut)
async def set_pause(strategy_id: int, body: PauseIn, db: Db, user: User, now: Now) -> Any:
    await _read(db, user, strategy_id)  # 404 before anything else
    code = None
    try:
        until = await store.set_pause(db, user, strategy_id, parse_until(body.until, now), now)
        await db.commit()
    except monitor_pause.PauseRefused as refused:
        await db.rollback()
        code = refused.reason  # the refusal code only; the answer is built below, from the catalogue
    except store.PauseSameTime:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("settings_refused_same_time")), 409)
    except Exception:
        await db.rollback()
        raise
    if code is not None:
        return _refusal(code)
    return compose(strategy_id, until, now)


@router.delete(PATH, response_model=PauseOut)
async def clear_pause(strategy_id: int, db: Db, user: User, now: Now) -> Any:
    await _read(db, user, strategy_id)
    try:
        await store.clear_pause(db, user, strategy_id)
        await db.commit()
    except store.PauseSameTime:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("settings_refused_same_time")), 409)
    except Exception:
        await db.rollback()
        raise
    return compose(strategy_id, None, now)
