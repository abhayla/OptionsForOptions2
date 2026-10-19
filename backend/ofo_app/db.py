# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/database.py (ADR-047)
# Kept: async engine (jit off), async_sessionmaker(expire_on_commit=False), Base, get_db.
# Dropped: convert_decimals_to_float (float money, ADR-008), init_db/create_all (schema comes only from Alembic),
# the Redis pool, and the print of the database host.
# Changed: the engine is created lazily, so importing this module (or calling create_app) has no side effects.
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ofo_app.config import get_settings

log = logging.getLogger(__name__)

#: How long the start-up read of the role's connection limit may take; a slower database is a read failure (fail-open).
ROLE_LIMIT_READ_TIMEOUT_SECONDS = 5.0
_ROLE_LIMIT = text("SELECT rolconnlimit FROM pg_roles WHERE rolname = current_user")


class PoolBudgetError(RuntimeError):
    """The pool can open more connections than the database role allows (GC-6 POOL-BUDGET, ADR-048)."""


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={"server_settings": {"jit": "off"}},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


def pool_maximum() -> int:
    """The most connections ONE API process can open: pool_size + max_overflow, from the settings."""
    settings = get_settings()
    return settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW


def check_pool_against_role_limit(pool_max: int, role_limit: int) -> None:
    """Refuses a pool larger than the role's connection limit; -1 means the role is unlimited."""
    if role_limit != -1 and pool_max > role_limit:
        raise PoolBudgetError(
            f"DB_POOL_SIZE + DB_MAX_OVERFLOW = {pool_max} is above the database role's connection limit of "
            f"{role_limit}: lower DB_POOL_SIZE / DB_MAX_OVERFLOW (and divide the limit by the number of API processes)")


async def verify_pool_budget(engine: AsyncEngine | None = None) -> None:
    """Start-up check (GC-6): read the role's ``rolconnlimit`` once and refuse to start when the pool can exceed it.
    Fail-open ONLY when the read itself fails (logged as a warning); a known excess is never let through."""
    try:
        async with asyncio.timeout(ROLE_LIMIT_READ_TIMEOUT_SECONDS):
            async with (engine or get_engine()).connect() as conn:
                role_limit = int((await conn.execute(_ROLE_LIMIT)).scalar_one())
    except Exception as exc:  # noqa: BLE001 - an unreadable limit does not stop the app; the reason class is logged
        log.warning("database role connection limit not read (%s); pool budget not checked", type(exc).__name__)
        return
    check_pool_against_role_limit(pool_maximum(), role_limit)
