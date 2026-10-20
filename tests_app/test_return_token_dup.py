"""GC-6 TOKEN-RETURN (and DUP-TAG, below): the return path against a partial or duplicated broker answer.

Real inputs: the owner's 2026-10-16 replies (tests/fixtures/kite_replies/, through ``test_execution_return._data``).
Spec basis: ADR-016..019 (Zerodha is the authority; an unresolved mismatch blocks); ADR-117 (2)(g).
Each guard's mutation: removing it makes the named test fail (see each docstring).
"""
from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from ofo_app import execution_return as er
from ofo_app.kite_reads import TOKEN_CODE, KiteReadError
from ofo_app.routes.execute import read_refusal
from test_execution_return import (
    ENTRY_DONE,
    ENTRY_OPEN,
    TODAY,
    _app_for,
    _book,
    _data,
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


# ---- GC-6 DUP-TAG: one basket tag on more broker orders than the plan holds (a basket posted twice) -----------------

def _twice(rows_orders: list, rows_trades: list, *, second_status: str | None = None, second_filled: int | None = None):
    """The real 12:21:04 order and trade, plus a copy with a new order id / trade id and the SAME tag."""
    orders = [*rows_orders, {**rows_orders[0], "order_id": "261016170576999"}]
    trades = [*rows_trades, {**rows_trades[0], "order_id": "261016170576999", "trade_id": "4484195"}]
    if second_status is not None:
        orders[1]["status"] = second_status
    if second_filled is not None:
        orders[1]["filled_quantity"] = second_filled
        trades = trades[:1]
    return orders, trades


@pytest.mark.parametrize("shape", ["both_filled", "second_cancelled_unfilled", "second_still_working"])
def test_dup_tag_one_tag_on_two_orders_is_reconciliation_required_never_merged(shape):
    """The real order twice under Q0001010 -> the plan stays open with reason duplicate_tag, whatever the second
    row says (a second COMPLETE would be 130 of 65; a second CANCELLED with 0 filled would otherwise close the plan
    as a clean fill of the first; a second still working would otherwise read as waiting). Dies if the
    ``len(found) > 1`` guard in ``classify`` is removed."""
    orders, trades = _data("orders-122104"), _data("trades-122104")
    if shape == "second_cancelled_unfilled":
        orders, trades = _twice(orders, trades, second_status="CANCELLED", second_filled=0)
    elif shape == "second_still_working":
        orders, trades = _twice(orders, trades, second_status="OPEN", second_filled=0)
    else:
        orders, trades = _twice(orders, trades)
    book = _book(orders, trades, (ENTRY_OPEN,))
    assert [r.order_id for r in book.ours["Q0001010"]] == ["261016170576173", "261016170576999"]
    assert er.classify(ENTRY_OPEN, book, TODAY) == er.PlanAnswer(er.RECONCILE, {}, er.DUPLICATE_TAG)


def test_dup_tag_a_single_row_per_tag_still_closes_the_plan():
    """Discrimination: the real single-row book is unchanged (plan 1 filled 65 of 65, no reason)."""
    book = _book(_data("orders-122104"), _data("trades-122104"), (ENTRY_OPEN,))
    assert er.classify(ENTRY_OPEN, book, TODAY) == er.PlanAnswer(er.FILLED, {"Q0001010": 65})


def test_dup_tag_a_closed_plan_whose_tag_later_shows_two_orders_has_drifted():
    """A plan closed filled 65 against one row, then the book shows the same tag twice with a second 0-fill row
    (the sum still equals the stored 65): drift, which blocks the next Execute. Dies if ``len(found) > 1`` is removed
    from ``drifted``."""
    orders, trades = _twice(_data("orders-122104"), _data("trades-122104"), second_status="CANCELLED",
                            second_filled=0)
    assert er.drifted((ENTRY_DONE,), _book(orders, trades, (ENTRY_DONE,))) == (1,)
    single = _book(_data("orders-122104"), _data("trades-122104"), (ENTRY_DONE,))
    assert er.drifted((ENTRY_DONE,), single) == ()


@pytest.mark.usefixtures("app_engine")
async def test_dup_tag_route_blocks_with_the_reason_and_closes_nothing(app_engine, admin_engine, monkeypatch):
    """Core (2) on the database: plan 1 open, the real order posted twice -> 200 with plan state
    reconciliation_required, reason duplicate_tag, blocked true; the plan row is still open and no fill is stored;
    both orders are in the audit log (each order id once), and a replay adds nothing."""
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415
    from test_execute_route import _strategy_one, audit_head, audit_since  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("TEST_CATALOGUE_DATE", "2026-10-16")
    orders, trades = _twice(_data("orders-122104"), _data("trades-122104"))
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user = _user()
            sid = await _strategy_one(conn, user, app_engine.url.username)
            await _store_plan(conn, user, sid, ("ENTRY", "BUY", "5.45"))
            app = _app_for(conn, user, _Reads("122104", orders=orders, trades=trades))
            head = await audit_head(conn)
            resp = await _post(app, sid)
            assert resp.status_code == HTTPStatus.OK, resp.text
            body = resp.json()
            assert body["plans"] == [{"plan_number": 1, "action": "ENTRY", "state": "reconciliation_required",
                                      "choices": [], "reason": "duplicate_tag"}]
            assert body["blocked"] is True
            (stored,) = await plans.plans_for(conn, user, sid)
            assert (stored.status, stored.close_reason, stored.orders[0].filled_quantity) == ("open", None, None)
            events = await audit_since(conn, head)
            recorded = sorted(c for t, c, _ in events if t == "broker_response_recorded")
            assert recorded == ["order:261016170576173:COMPLETE:65", "order:261016170576999:COMPLETE:65"]
            head = await audit_head(conn)
            again = await _post(app, sid)
            assert again.json()["plans"] == body["plans"]
            assert await audit_since(conn, head) == []
        finally:
            await trans.rollback()
