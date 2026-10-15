"""TEST-ONLY: seed CI's throwaway database with the recorded instrument fixture (issue #237).

    APP_ENV=test TEST_CATALOGUE_DATE=2026-10-08 python -m ofo_app.seed_test_catalogue

Goes through the normal guarded loader (``catalogue_load.run`` -> ``apply_update``), with ``as_of`` = the pinned date, so
the fixture's contracts are not stale rows on that day. No guard is loosened and nothing is deleted. Refused unless
APP_ENV=test AND TEST_CATALOGUE_DATE is set, and refused when the catalogue already holds rows (a throwaway database
only; never the shared test database after other runs).
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import sys
from typing import Any

from sqlalchemy import text

from ofo_app import pinned_clock
from ofo_app.catalogue_load import run

FIXTURE = (pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "kite_ws"
           / "instruments-2026-10-08-subscribed.csv")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class SeedRefused(RuntimeError):
    """The seed was asked for outside its test-only conditions."""


def seed_as_of(app_env: str) -> datetime.datetime:
    """The load instant (10:00 IST on the pinned date); refuses outside APP_ENV=test or without a pin."""
    pinned_clock.require_test_env(app_env)
    pinned = pinned_clock.pinned_today()
    if pinned is None:
        raise SeedRefused(f"{pinned_clock.ENV_NAME} must be set to seed the test catalogue")
    return datetime.datetime.combine(pinned, datetime.time(10, 0), tzinfo=IST)


async def seed(conn: Any, settings: Any, app_env: str) -> int:
    """Load the fixture on ``conn`` (never commits); returns the loader's exit code."""
    as_of = seed_as_of(app_env)
    held = (await conn.execute(text("SELECT count(*) FROM public.catalogue_contracts"))).scalar_one()
    if held:
        raise SeedRefused(f"the catalogue already holds {held} contracts; seed only a fresh throwaway database")
    return await run(conn, FIXTURE.read_text(encoding="utf-8"), settings, as_of=as_of)


async def main() -> int:
    from ofo_app.config import app_env, get_settings
    from ofo_app.db import close_db, get_engine

    settings = get_settings()
    try:
        async with get_engine().connect() as conn:
            trans = await conn.begin()
            code = await seed(conn, settings, app_env() or "")
            if code == 0:
                await trans.commit()
            else:
                await trans.rollback()
            return code
    finally:
        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
