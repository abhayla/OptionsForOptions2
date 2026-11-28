"""REQ-049 AC-4: a statement that raises must not leave its start time for the next statement's db timer."""
from __future__ import annotations

import pytest
from ofo_app import step_timing
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


async def test_failed_statement_leaves_no_stale_start(app_engine) -> None:
    step_timing.install_db_events(app_engine.sync_engine)
    token = step_timing.start()
    try:
        async with app_engine.connect() as conn:
            await conn.execute(text("select 1"))
            with pytest.raises(DBAPIError):
                await conn.execute(text("select 1/0"))
            await conn.rollback()
            assert conn.sync_connection.info.get("ofo_t0") is None  # cleared by the error hook
            await conn.execute(text("select 2"))
            assert conn.sync_connection.info.get("ofo_t0") is None  # and by the after hook
        ms, n = step_timing.snapshot()["db"]
    finally:
        step_timing.stop(token)
    assert n == 2  # noqa: PLR2004 - select 1 and select 2 are timed; the raised statement is not
    assert ms >= 0.0
