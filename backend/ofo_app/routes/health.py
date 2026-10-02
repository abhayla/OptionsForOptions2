# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/api/routes/health.py (ADR-047)
# Database check only (no Redis). Changed: the error detail is logged, never returned to the client.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ofo_app.db import get_db

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "disconnected"})
    return JSONResponse(status_code=200, content={"status": "healthy", "database": "connected"})
