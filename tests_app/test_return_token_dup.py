"""GC-6 TOKEN-RETURN (and DUP-TAG, below): the return path against a partial or duplicated broker answer.

Real inputs: the owner's 2026-10-16 replies (tests/fixtures/kite_replies/, through ``test_execution_return._data``).
Spec basis: ADR-016..019 (Zerodha is the authority; an unresolved mismatch blocks); ADR-117 (2)(g).
Each guard's mutation: removing it makes the named test fail (see each docstring).
"""
from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from ofo_app.kite_reads import TOKEN_CODE, KiteReadError
from ofo_app.routes.execute import read_refusal
from test_execution_return import (
    _app_for,
    _post,
    _Reads,
    _store_plan,
)

EXPIRED_TEXT = "Your Zerodha session has expired. Reconnect to continue."
NOT_CONFIRMED_TEXT = "We could not confirm your Zerodha connection. Reconnect to continue."


class _TokenExpired(_Reads):
    """Kite answers the orders read with the real expired-token reply (403, ``error_type`` TokenException)."""

    def __call__(self, method, url, headers, body):
        if url.endswith("/orders"):
            self.calls.append((method, url))
            return 403, json.dumps({"status": "error", "message": "Incorrect `api_key` or `access_token`.",
                                    "data": None, "error_type": "TokenException"})
        return super().__call__(method, url, headers, body)


@pytest.mark.parametrize(("code", "text"), [(TOKEN_CODE, EXPIRED_TEXT), ("kite_read_busy", NOT_CONFIRMED_TEXT),
                                            ("kite_read_unavailable", NOT_CONFIRMED_TEXT)])
def test_token_return_only_an_expired_token_reads_session_expired(code, text):
    """Both routes that read the order book refuse through ``read_refusal``: the token code -> the existing
    session-expired message, every other read failure -> the existing "not confirmed" message. Dies if the mapping
    is removed (the token case then reads "could not confirm")."""
    refused = read_refusal(KiteReadError(code))
    assert refused.message.what_happened == text


async def _rows_snapshot(conn) -> dict[str, list]:
    """Every row the return could write (plans, their orders, the audit chain)."""
    from sqlalchemy import text  # noqa: PLC0415

    out = {}
    for table in ("execution_plans", "execution_plan_orders", "audit_events"):
        rows = await conn.execute(text(f"SELECT * FROM public.{table} ORDER BY 1, 2"))  # noqa: S608 constant table name
        out[table] = [tuple(r) for r in rows]
    return out


@pytest.mark.usefixtures("app_engine")
async def test_token_return_expired_token_changes_nothing_and_a_retry_after_reconnect_closes_the_plan(
        app_engine, admin_engine, monkeypatch):
    """Core (1): plan 1 open, the orders read answers 403 TokenException -> 409 with the session-expired message and
    every plan / order / audit row identical before and after (no sticky state); after reconnect the same return on
    the real 12:21:04 replies closes plan 1 filled. Dies if the route writes before its reads or loses the mapping."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execute_route import _strategy_one  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45"))
            before = await _rows_snapshot(conn)
            resp = await _post(_app_for(conn, user, _TokenExpired("122104")), sid)
            assert resp.status_code == HTTPStatus.CONFLICT, resp.text
            assert EXPIRED_TEXT in resp.text, resp.text
            assert await _rows_snapshot(conn) == before
            assert [p.status for p in await plans.plans_for(conn, user, sid)] == ["open"]
            retry = await _post(_app_for(conn, user, _Reads("122104")), sid)
            assert retry.status_code == HTTPStatus.OK, retry.text
            assert retry.json()["plans"][0]["state"] == "filled"
        finally:
            await trans.rollback()
