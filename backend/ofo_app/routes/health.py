# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/api/routes/health.py (ADR-047)
# Database check only (no Redis). Changed: the error detail is logged, never returned to the client; the body is a
# typed ApiModel (W-024 round 9 part 6 fix round: no route builds a Response itself).
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app.api_models import ApiModel
from ofo_app.db import get_db
from ofo_app.errors import typed_response

router = APIRouter()
log = logging.getLogger(__name__)


class HealthOut(ApiModel):
    status: Literal["healthy", "unhealthy"]
    database: Literal["connected", "disconnected"]


@router.get("/health", response_model=HealthOut)
async def health_check(session: AsyncSession = Depends(get_db)) -> object:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check: database unreachable")
        return typed_response(HealthOut(status="unhealthy", database="disconnected"), 503)
    return HealthOut(status="healthy", database="connected")
