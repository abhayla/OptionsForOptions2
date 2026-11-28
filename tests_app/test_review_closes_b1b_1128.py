# ruff: noqa: F811
"""Lane B1b: the closes of the Opus review findings F1 and F2 against Lane RA2's 1f8e0018c, and a backstop.

F1 (a stop the user believes armed must be committed): the answer is built AFTER the commit (RA2); a REAL PostgreSQL
error (``SELECT 1/0`` aborts the transaction) in a read after the commit must still answer 201 armed with the row
stored; a real error BEFORE the commit stores nothing, answers an error and does not notify the monitor; a
swallowed error inside ``_adjustment_marks`` (it aborts the transaction) never undoes a committed stop.
F2 (a foreign exception's text never reaches the log): a ValueError of any other module whose message merely STARTS like
one of ours must not be logged with its text.
Backstop (d): no session at 09:15:00 IST on a trading day, with a stored close in the book: NOT_CONNECTED, no figure."""
from __future__ import annotations

import datetime
import logging
from http import HTTPStatus

from ofo.marketdata.kite_provider import IST
from ofo_app import paper_monitor, paper_trigger_store, regime_inputs, tracked_contracts
from ofo_app.regime_inputs import Clients
from ofo_app.routes import paper as paper_routes
from ofo_app.routes.outcome import MarketContext, get_market_context
from sqlalchemy import text
from test_paper_routes import _client as _book_client
from test_paper_triggers_routes import _client, _open, _stored, _url, db, notified  # noqa: F401
from test_stored_close_paper_pnl_ra2_1128 import _no_session_book

BODY = {"kind": "conditional_exit", "below": "22000"}


def _real_error_after_the_commit(monkeypatch, which):
    state = {"committed": False, "hits": 0}
    owner, name = which
    real = getattr(owner, name)

    async def broken(conn, *args, **kwargs):
        if state["committed"] and state["hits"] == 0:
            state["hits"] += 1
            await conn.execute(text("SELECT 1/0"))  # a server-side error: the transaction is aborted
        return await real(conn, *args, **kwargs)
    monkeypatch.setattr(owner, name, broken)
    monkeypatch.setattr(paper_monitor, "notify", lambda: state.update(committed=True))
    return state


async def test_f1_a_real_database_error_in_the_read_after_the_commit_still_answers_armed_and_stored(db, monkeypatch):
    state = _real_error_after_the_commit(monkeypatch, (paper_trigger_store, "list_for"))
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=BODY)
    assert state["hits"] == 1
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert [r["state"] for r in reply.json()["triggers"]] == ["armed"]
    assert len(await _stored(db, stored.id)) == 1


async def test_f1_a_real_error_before_the_commit_stores_nothing_and_never_says_armed(db, notified, monkeypatch):
    app, stored, _ = await _open(db)
    real_add = paper_trigger_store.add

    async def add_then_break(conn, *args, **kwargs):
        got = await real_add(conn, *args, **kwargs)
        await conn.execute(text("SELECT 1/0"))  # the transaction is aborted before the commit
        return got
    monkeypatch.setattr(paper_trigger_store, "add", add_then_break)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=BODY)
    assert reply.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    assert "armed" not in reply.text
    assert await _stored(db, stored.id) == [] and notified == []


async def test_f1_a_swallowed_error_in_the_marks_read_never_undoes_a_committed_stop(db, monkeypatch):
    app, stored, _ = await _open(db)
    state = {"committed": False}
    monkeypatch.setattr(paper_monitor, "notify", lambda: state.update(committed=True))
    real_marks, real_resolve = paper_routes._adjustment_marks, tracked_contracts.resolve
    inside = {"on": False}

    async def marks(*args, **kwargs):
        inside["on"] = True
        try:
            return await real_marks(*args, **kwargs)
        finally:
            inside["on"] = False

    async def resolve(conn, ids):
        if inside["on"]:
            await conn.execute(text("SELECT 1/0"))
        return await real_resolve(conn, ids)
    monkeypatch.setattr(paper_routes, "_adjustment_marks", marks)
    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=BODY)
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert len(await _stored(db, stored.id)) == 1 and state["committed"]


def test_f2_a_foreign_value_error_that_starts_like_ours_never_reaches_the_log_with_its_text(caplog):
    class _Leaky:
        def last(self, _token):
            raise ValueError("needs the header token key:SECRET-ACCESS-TOKEN")  # foreign text, our opening words
    regime_inputs._TOLD.clear()
    with caplog.at_level(logging.WARNING):
        got = regime_inputs.read_with(Clients(history=object()), "NIFTY", _Leaky())
    assert got.adx is None
    assert "SECRET" not in caplog.text, caplog.text


async def test_d_no_session_at_09_15_00_reads_not_connected_with_no_figure(db):
    app, stored = await _no_session_book(db)
    at = datetime.datetime(2026, 10, 9, 9, 15, 0, tzinfo=IST)  # Friday, the bell: open
    provider = app.dependency_overrides[get_market_context]().provider
    context = MarketContext(provider, lambda: at, regime_inputs.Decimal("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    async with _book_client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
        whole = (await c.get("/paper/strategies")).json()
    listed = next(s for s in whole["strategies"] if s["strategy_id"] == stored.id)
    for one in (body, listed):
        assert (one["state"], one["unbooked"], one["total"], one["as_of"]) == ("NOT_CONNECTED", None, None, None)
