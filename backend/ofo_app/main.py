"""FastAPI application builder. No module-level app, no create_all: the schema comes only from Alembic.

Lifespan pattern referenced from abhayla/algochanakya@bf9faf7:backend/app/main.py (ADR-047, REFERENCE only). Unlike
its global handler (main.py:293-307), the generic handler here never returns str(exc) to the client.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ofo_app.db import close_db
from ofo_app.routes import health

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db()


async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "internal_error"})


def create_app() -> FastAPI:
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan)
    app.add_exception_handler(Exception, _internal_error)
    app.include_router(health.router)
    return app
