"""GET /api/strategies/{id}/level-watch, PUT / DELETE /api/strategies/{id}/level-watch/{direction}: A-37, watch an
index level on one strategy (GC-IC1 step 4c, ADR-242).

Spec basis: ADR-242 (one active watch per strategy per direction, set / cleared by its owner, evaluated as a yes/no
rule through the alert gate); REQ-170 AC-5 (risk exits never read a watch); REQ-168 AC-3 (keyed by the user). Copy
from: ``routes/monitoring_pause.py`` (same key, same store shape, same refusals).

- GET: {strategy_id, above, below}: each the watched level as a plain number string, or null (none / cleared).
- PUT {level: "23800"}: the watch of that direction set, then the GET reply. Refused with its reason (422): the level
  is not a number above zero. A direction other than "above" / "below" -> 404 (no such route).
- DELETE: the watch of that direction cleared now, then the GET reply.
- Answer states: none / set / cleared; another user's or a missing strategy -> 404 (a watch set by another user is
  never shown or changed); the same instant twice -> 409. The worker picks a change up at its next rebuild.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import level_watch
from ofo.errors.explanations import render_explanation
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app import strategy_level_watch_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure, respond
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
Db = Annotated[AsyncSession, Depends(get_db)]
User = Annotated[str, Depends(current_user_ref)]
Direction = Literal["above", "below"]
_NOT_AVAILABLE = "user_input_request_not_available"
# Route paths are written as literals in the decorators: the app-test selector (scripts/orchestrator/
# select_app_tests.py) reads them from the source and fails closed on a computed path.


class WatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str


class WatchOut(ApiModel):
    strategy_id: int
    above: Identifier | None  # the level as a plain number, e.g. 23800 or 23800.5 (no colon, no space)
    below: Identifier | None


class RefusedOut(ApiModel):
    reason: CatalogueText


def compose(strategy_id: int, watches: tuple[level_watch.LevelWatch, ...]) -> WatchOut:
    by = {w.direction: format(w.level, "f") for w in watches}
    return WatchOut(strategy_id=strategy_id, above=by.get(level_watch.ABOVE), below=by.get(level_watch.BELOW))


async def _read(db: AsyncSession, user: str, strategy_id: int) -> tuple[level_watch.LevelWatch, ...]:
    try:
        return await store.watches_of(db, user, strategy_id)
    except store.WatchNotFound:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND) from None


@router.get("/api/strategies/{strategy_id}/level-watch", response_model=WatchOut)
async def read_watch(strategy_id: int, db: Db, user: User) -> Any:
    return compose(strategy_id, await _read(db, user, strategy_id))


@router.put("/api/strategies/{strategy_id}/level-watch/{direction}", response_model=WatchOut)
async def set_watch(strategy_id: int, direction: Direction, body: WatchIn, db: Db, user: User) -> Any:
    await _read(db, user, strategy_id)  # 404 before anything else
    try:
        await store.set_watch(db, user, strategy_id, direction, body.level)
        await db.commit()
    except level_watch.WatchRefused:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("level_watch_refused_not_a_number")), 422)
    except store.WatchSameTime:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("settings_refused_same_time")), 409)
    except Exception:
        await db.rollback()
        raise
    return compose(strategy_id, await _read(db, user, strategy_id))


@router.delete("/api/strategies/{strategy_id}/level-watch/{direction}", response_model=WatchOut)
async def clear_watch(strategy_id: int, direction: Direction, db: Db, user: User) -> Any:
    await _read(db, user, strategy_id)
    try:
        await store.clear_watch(db, user, strategy_id, direction)
        await db.commit()
    except store.WatchSameTime:
        await db.rollback()
        return respond(RefusedOut(reason=render_explanation("settings_refused_same_time")), 409)
    except Exception:
        await db.rollback()
        raise
    return compose(strategy_id, await _read(db, user, strategy_id))
