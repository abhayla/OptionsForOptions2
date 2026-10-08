"""FastAPI application builder. No module-level app, no create_all: the schema comes only from Alembic.

Lifespan pattern referenced from abhayla/algochanakya@bf9faf7:backend/app/main.py (ADR-047, REFERENCE only). Unlike
its global handler (main.py:293-307), no handler here returns str(exc): every error body comes from
`ofo_app.errors` (W-024 round 9 part 6), only from a render() catalogue message.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ofo_app import errors
from ofo_app.broker_config import BrokerConfig, load_broker_config
from ofo_app.db import close_db
from ofo_app.routes import broker, health, outcome

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_db()


def create_app(broker_config: BrokerConfig | None = None) -> FastAPI:
    """Builds the app. The broker routes refuse to start without a valid broker configuration (W-058):
    ``load_broker_config`` raises BrokerConfigError, so the app is never built without its token key."""
    config = broker_config if broker_config is not None else load_broker_config()
    app = FastAPI(title="OptionsForOptions2 API", version="0.1.0", lifespan=_lifespan)
    errors.install(app)
    app.include_router(health.router)
    app.include_router(outcome.router)
    broker.mount(app, config)
    return app
