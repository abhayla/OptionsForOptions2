# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/api/routes/health.py (ADR-047)
# Database check only (no Redis). Changed: the error detail is logged, never returned to the client; the body is a
# typed ApiModel (W-024 round 9 part 6 fix round: no route builds a Response itself).
from __future__ import annotations

import datetime
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app.api_models import ApiModel
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, respond

router = APIRouter(route_class=ClosedRoute)
log = logging.getLogger(__name__)


class HealthOut(ApiModel):
    status: Literal["healthy", "unhealthy"]
    database: Literal["connected", "disconnected"]
    #: ADR-330 (61): which instrument list is in use: today's, an earlier day's (its date in ``instrument_list_day``) or
    #: none; "unknown" when it could not be read (the check never fails the probe)
    instrument_list: Literal["today", "earlier", "none", "unknown"] = "unknown"
    instrument_list_day: datetime.date | None = None


@router.get("/health", response_model=HealthOut)
async def health_check(session: AsyncSession = Depends(get_db)) -> object:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check: database unreachable")
        return respond(HealthOut(status="unhealthy", database="disconnected"), 503)
    return HealthOut(status="healthy", database="connected", **await _list_in_use(session))


async def _list_in_use(session: AsyncSession) -> dict:
    """Which instrument list is in use (the picker's own answer, one source); a failed read says "unknown"."""
    from ofo_app import catalogue_picker  # noqa: PLC0415 - late: the picker imports the settings store
    try:
        status = await catalogue_picker.list_status(session, await catalogue_picker.database_today(session))
    except Exception:  # never fails the probe
        log.exception("health check: the instrument list in use could not be read")
        return {"instrument_list": "unknown", "instrument_list_day": None}
    if status.list_day is None:
        return {"instrument_list": "none", "instrument_list_day": None}
    return {"instrument_list": "today" if status.current else "earlier", "instrument_list_day": status.list_day}
