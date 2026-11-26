"""S-02 (owner screen check 25 Nov 2026, ERR-6960F002 on a strategy delete): a database lock wait or statement timeout
on a store write is answered with the catalogue's `store_busy` refusal, never a raw 500 (ERR-xxxx).

Spec basis: ADR-330 (8) "Busy store" paragraph (new wording, ADR-NB-1 pending owner read, Lane R 26 Nov 2026);
RESULTS-lane-q2.md "S-02 candidate cause, measured" (delete_draft raised sqlstate 55P03 with a second connection
holding FOR UPDATE and lock_timeout 300 ms); ADR-016 to ADR-019 (nothing half-written).

Real PostgreSQL only (ADR-048). The rows are committed (a second connection must see them) and removed by the owner
role at the end; the lock holder is an owner-role connection.
"""

from __future__ import annotations

import os
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from ofo.errors import render
from ofo_app import errors as door
from ofo_app.catalogue_store import apply_update
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.requests import Request
from test_strategy_store import (
    _MAX_DELIST,
    AS_OF,
    SYMBOLS,
    _app,
    _body,
    _client,
    _digests,
    _fixture_rows,
    _ids,
    _remove_own_rows,
    _user,
)

BUSY_TEXT = "This strategy is busy with another action, so nothing was changed."
BUSY_NEXT = "Wait a moment, then try again."
BUSY_CODE = "STRATEGY_VALIDATION_522"
CONFLICT, INTERNAL = 409, 500
REVISION_ONE = 1
LOCK_NOT_AVAILABLE = "55P03"
QUERY_CANCELED = "57014"
DEADLOCK = "40P01"
HOLD_FOR = "SELECT id FROM public.strategies WHERE id = :id FOR UPDATE"
RAW = text("SELECT revision, deleted_at FROM public.strategies WHERE id = :id")


def _timed_engine(url: str, setting: str):
    """An application engine whose every connection waits at most 300 ms (the setting named)."""
    return create_async_engine(url, poolclass=NullPool,
                               connect_args={"server_settings": {"jit": "off", setting: "300"}})


async def _committed_draft(app_engine, user: str) -> tuple[dict[str, int], int]:
    async with app_engine.connect() as conn:
        async with conn.begin():
            await apply_update(conn, _fixture_rows(SYMBOLS), as_of=AS_OF, max_delist_percent=_MAX_DELIST)
        ids = await _ids(conn)
    maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    async with _client(_app(maker, user)) as ac:
        saved = await ac.post("/strategies", json=_body(ids))
    assert saved.status_code == HTTPStatus.CREATED, saved.text
    return ids, int(saved.json()["id"])


@pytest.mark.parametrize(("setting", "sqlstate"), [("lock_timeout", LOCK_NOT_AVAILABLE),
                                                   ("statement_timeout", QUERY_CANCELED)])
async def test_a_delete_that_waits_on_a_row_lock_answers_the_busy_refusal_and_changes_nothing(
        app_engine, admin_engine, monkeypatch, setting, sqlstate):
    user = _user()
    before = await _digests(admin_engine)
    ids: dict[str, int] = {}
    timed = _timed_engine(os.environ["TEST_DATABASE_URL"], setting)
    try:
        ids, strategy_id = await _committed_draft(app_engine, user)
        async with admin_engine.connect() as holder:
            trans = await holder.begin()
            await holder.execute(text(HOLD_FOR), {"id": strategy_id})  # the second connection holds the row
            try:
                maker = async_sessionmaker(timed, class_=AsyncSession, expire_on_commit=False)
                async with _client(_app(maker, user)) as ac:
                    # the failing delete reaches the route: the raw error is what the user saw as ERR-xxxx
                    answer = await ac.delete(f"/strategies/{strategy_id}", params={"expected_revision": 1})
            finally:
                await trans.rollback()
        body = answer.json()
        assert (answer.status_code, body["code"], body["what_happened"], body["next_action"]) == (
            CONFLICT, BUSY_CODE, BUSY_TEXT, BUSY_NEXT), answer.text
        assert "ERR-" not in answer.text
        async with admin_engine.connect() as conn:  # all-or-nothing: the row is untouched
            row = (await conn.execute(RAW, {"id": strategy_id})).one()
        assert (row.revision, row.deleted_at) == (REVISION_ONE, None)
        # and once the lock is gone the same delete works (the refusal was only "busy")
        maker = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
        async with _client(_app(maker, user)) as ac:
            again = await ac.delete(f"/strategies/{strategy_id}", params={"expected_revision": 1})
        assert again.status_code in (200, 204), again.text
    finally:
        await timed.dispose()
        if not ids:
            async with admin_engine.connect() as conn:
                ids = await _ids(conn)
        await _remove_own_rows(admin_engine, list(ids.values()), user)
    assert await _digests(admin_engine) == before, "the test left rows behind"


def _db_error(sqlstate: str) -> DBAPIError:
    return DBAPIError("DELETE ...", {}, SimpleNamespace(sqlstate=sqlstate))


@pytest.mark.parametrize("sqlstate", [LOCK_NOT_AVAILABLE, QUERY_CANCELED, DEADLOCK])
async def test_the_three_busy_states_are_answered_by_the_one_error_door(sqlstate):
    response = await door.handle_error(_request(), _db_error(sqlstate))
    expected = render("store_busy")
    assert response.status_code == CONFLICT
    assert (expected.what_happened, expected.code) == (BUSY_TEXT, BUSY_CODE)
    assert BUSY_TEXT.encode() in response.body


async def test_a_busy_error_wrapped_by_another_exception_is_still_busy():
    try:
        try:
            raise _db_error(LOCK_NOT_AVAILABLE)
        except DBAPIError as inner:
            raise RuntimeError("store call failed") from inner
    except RuntimeError as outer:
        response = await door.handle_error(_request(), outer)
    assert response.status_code == CONFLICT and BUSY_TEXT.encode() in response.body


@pytest.mark.parametrize("sqlstate", ["23505", "42501", "57P01", None])
async def test_any_other_database_error_is_unchanged_the_internal_answer(sqlstate):
    response = await door.handle_error(_request(), _db_error(sqlstate))
    assert response.status_code == INTERNAL
    assert BUSY_TEXT.encode() not in response.body


def _request():
    return Request({"type": "http", "method": "DELETE", "path": "/strategies/1", "headers": [], "query_string": b""})
