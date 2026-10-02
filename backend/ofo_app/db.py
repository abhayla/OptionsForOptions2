# Copied/adapted from abhayla/algochanakya@bf9faf7:backend/app/database.py (ADR-047)
# Kept: async engine (jit off), async_sessionmaker(expire_on_commit=False), Base, get_db.
# Dropped: convert_decimals_to_float (float money, ADR-008), init_db/create_all (schema comes only from Alembic),
# the Redis pool, and the print of the database host.
# Changed: the engine is created lazily, so importing this module (or calling create_app) has no side effects.
from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ofo_app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().DATABASE_URL,
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
