# ruff: noqa: F811 - the imported fixtures are used as test arguments
"""Lane B2 (ADR-330 (58)): the real Execute door passes the same unknown-outcome block as the paper doors (its own file:
the real-door fixture loads a catalogue that the paper tests' catalogue would clash with in one database)."""
from __future__ import annotations

import uuid
from http import HTTPStatus

import pytest
from sqlalchemy import text
from test_order_request_key_r2_fd2 import keys  # noqa: F401 - fixture

UNKNOWN = "no known result yet"


@pytest.mark.usefixtures("order_path_on")
async def test_the_real_door_is_blocked_too_and_a_started_execute_blocks_a_paper_order(app_engine, admin_engine,
                                                                                       monkeypatch, keys):
    """ADR-330 (58): paper and real alike. An unknown real attempt refuses Execute; the table is per strategy."""
    from test_order_request_key_r2_fd2 import _execute, _real_app  # noqa: PLC0415
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            app, sid, user = await _real_app(conn, app_engine, monkeypatch, keys)
            await conn.execute(text("INSERT INTO public.order_attempts (user_ref, strategy_id, door, state) "
                                    "VALUES (:u, :s, 'paper', 'open')"), {"u": user, "s": sid})
            blocked = await _execute(app, sid, uuid.uuid4())
            assert blocked.status_code == HTTPStatus.CONFLICT and UNKNOWN in blocked.text, blocked.text[:300]
            await conn.execute(text("UPDATE public.order_attempts SET state = 'stored', resolved_at = now() "
                                    "WHERE strategy_id = :s"), {"s": sid})
            ok = await _execute(app, sid, uuid.uuid4())
            assert ok.status_code == HTTPStatus.OK, ok.text[:300]
        finally:
            await trans.rollback()
