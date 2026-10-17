"""TEST-ONLY: seed CI's throwaway database for the Execute/return replay API (W-101).

    (CI only) PYTHONPATH=backend APP_ENV=test DATABASE_URL=<owner role URL> python -m ofo_app.seed_execute_replay

Stores strategy id 1 for the v1 owner exactly as the route tests store it (``execute_replay.store_strategy_one``: the
real contract through the guarded catalogue loader, the strategy through the store, id 1 set as the owner role, then the
application role) and a Pro grant through ``entitlement_store.append`` stamped by the DATABASE clock (never a request
clock). Refused unless APP_ENV is exactly ``test`` (the replay's own guard), and for any database but the test one.
Idempotent: when strategy 1 already belongs to the owner, nothing is written; when it belongs to anyone else, refused.
Do NOT run this locally.
"""
from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from ofo_app import execute_replay
from ofo_app.routes.broker import V1_OWNER_REF

#: the limited application role the route runs as (ADR-048); CI creates it with this name
APP_ROLE = os.environ.get("OFO_APP_ROLE", "ofo_app")


class SeedRefused(RuntimeError):
    """The seed was asked for outside its test-only conditions."""


def check_database(database_url: str) -> None:
    """Allow-list: only the test database (``config.TEST_DATABASE_NAME``); any other name, or none, is refused."""
    from ofo_app.config import TEST_DATABASE_NAME, database_name  # noqa: PLC0415

    name = database_name(database_url)
    if name != TEST_DATABASE_NAME:
        raise SeedRefused(f"refused: the replay seed writes only to {TEST_DATABASE_NAME}, not {name!r}")


def planned_entry() -> Any:
    """W-104: the leg's ADR-075 planned entry, as a strategy saved from the Strategy Builder carries it: the recorded
    LIMIT price 3.35 captured at the recorded market instant. Without it the Execute screen cannot follow the strategy
    on the live socket (the outcome request needs each leg's planned entry) and never offers Execute."""
    from ofo.strategy.stored_form import LegEntry  # noqa: PLC0415

    return LegEntry(Decimal("3.35"), execute_replay.AT)


async def seed(conn: Any, app_env: str, user: str = V1_OWNER_REF) -> bool:
    """Seeds on ``conn`` (never commits); True when it wrote, False when strategy 1 is already the owner's."""
    execute_replay.require_test_env(app_env)
    held = (await conn.execute(text("SELECT user_ref FROM public.strategies WHERE id = 1"))).first()
    if held is not None:
        if held[0] != user:
            raise SeedRefused(f"strategy id 1 already belongs to {held[0]!r}; the replay needs it for {user!r}")
        return False
    await execute_replay.store_strategy_one(conn, user, APP_ROLE, entry=planned_entry())
    return True


async def main() -> int:
    from ofo_app.config import app_env, get_settings  # noqa: PLC0415
    from ofo_app.db import close_db, get_engine  # noqa: PLC0415

    execute_replay.require_test_env(app_env() or "")  # refused before any connection is opened
    check_database(get_settings().DATABASE_URL)
    try:
        async with get_engine().connect() as conn:
            trans = await conn.begin()
            if await seed(conn, app_env() or ""):
                await trans.commit()
            else:
                await trans.rollback()
            return 0
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
