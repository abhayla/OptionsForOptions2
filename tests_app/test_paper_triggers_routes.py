"""GC-TP step 7a (REQ-109 AC-8; ADR-207 (5)): trigger and alert routes, real PostgreSQL, every test rolled back.

Core: POST /paper/strategies/{id}/triggers stores an armed trigger and notifies the monitor; GET /paper/alerts returns
the alert rows the monitor wrote (written here with the store's own add_alert after a claim, as the monitor does).
"""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.errors.explanations import render_explanation
from ofo_app import paper_monitor, paper_store, paper_trigger_store
from sqlalchemy import text
from test_paper_routes import _new
from test_strategy_store import _client
from test_strategy_tracking import _setup

D = Decimal


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


@pytest.fixture
def notified(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(paper_monitor, "notify", lambda: calls.append(1))
    return calls


async def _open(db):
    app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "SELL", 65, "39.15"),
                                                             _new(ids[1], "BUY", 65, "12.95")])
    return app, stored, ids


def _url(stored, tail: str = "") -> str:
    return f"/paper/strategies/{stored.id}/triggers{tail}"


async def test_core_a_posted_stop_is_stored_armed_notifies_the_monitor_and_its_alert_is_read_back(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22850"})
        assert reply.status_code == HTTPStatus.CREATED, reply.text
        rows = reply.json()["triggers"]
        assert sorted((r["direction"], r["level_text"], r["state"]) for r in rows) == [
            ("above", "23,100.00", "armed"), ("below", "22,850.00", "armed")]
        assert notified == [1]
        tid = next(r["id"] for r in rows if r["direction"] == "below")
        assert await paper_trigger_store.claim_fire(db, tid)
        dash = render_explanation("cell_dash")
        title = str(render_explanation("paper_alert_title", name=dash))
        what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below",
                                  level=Decimal("22850"))
        leg = render_explanation("paper_alert_leg", contract=dash, price=dash)
        body = str(render_explanation("paper_alert_body", what=what, count=1, prices=leg))
        await paper_trigger_store.add_alert(db, stored.id, tid, title, body)
        alerts = (await c.get("/paper/alerts")).json()
        assert alerts["unread"] == 1 and [a["trigger_id"] for a in alerts["alerts"]] == [tid]
        assert (await c.get(_url(stored))).json()["triggers"][0]["id"] > 0
        read = (await c.post("/paper/alerts/read")).json()
        assert read["unread"] == 0 and read["alerts"][0]["read"] is True


async def test_a_leg_stop_names_an_open_contract_and_one_direction(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above",
                                                 "level": "120.00"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    [row] = reply.json()["triggers"]
    assert (row["kind"], row["contract_id"], row["level_text"]) == ("leg_stop", ids[0], "120.00")
    assert row["contract_text"]


@pytest.mark.parametrize("level", ["0", "-5", "22850.03", "100.123"])
async def test_a_bad_level_is_422_with_the_reason_and_nothing_is_stored(db, notified, level):
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "below": level})
        assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "a multiple of 0.05" in reply.text
        assert (await c.get(_url(stored))).json()["triggers"] == []
    assert notified == []


async def test_a_leg_stop_on_a_closed_contract_is_422(db, notified):
    app, stored, ids = await _open(db)
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "BUY", 65, "30.00", "exit")])
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above",
                                                 "level": "50"})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "not open" in reply.text


async def test_a_strategy_with_nothing_open_refuses_a_new_trigger(db, notified):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "below": "22850"})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and "nothing open" in reply.text and notified == []


async def test_missing_and_another_users_strategy_are_404_on_every_trigger_route(db, notified):
    app, stored, _ = await _open(db)
    other, *_ = await _setup(db)
    body = {"kind": "conditional_exit", "below": "22850"}
    async with _client(app) as c:
        assert (await c.post("/paper/strategies/999999999/triggers", json=body)).status_code == HTTPStatus.NOT_FOUND
        assert (await c.get("/paper/strategies/999999999/triggers")).status_code == HTTPStatus.NOT_FOUND
    async with _client(other) as c:
        assert (await c.post(_url(stored), json=body)).status_code == HTTPStatus.NOT_FOUND
        assert (await c.get(_url(stored))).status_code == HTTPStatus.NOT_FOUND
        assert (await c.delete(_url(stored, "/1"))).status_code == HTTPStatus.NOT_FOUND
        assert (await c.get("/paper/alerts")).json() == {"alerts": [], "unread": 0}


async def test_cancel_an_armed_trigger_then_a_fired_one_is_409_and_a_missing_one_404(db, notified):
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        rows = (await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22850"})
                ).json()["triggers"]
        armed, fired = rows[0]["id"], rows[1]["id"]
        gone = await c.delete(_url(stored, f"/{armed}"))
        assert gone.status_code == HTTPStatus.OK and {r["id"]: r["state"] for r in gone.json()["triggers"]}[armed] \
            == "cancelled"
        assert notified == [1, 1]
        assert await paper_trigger_store.claim_fire(db, fired)
        late = await c.delete(_url(stored, f"/{fired}"))
        assert late.status_code == HTTPStatus.CONFLICT and "already fired" in late.text
        assert (await c.delete(_url(stored, "/999999999"))).status_code == HTTPStatus.NOT_FOUND
    state = (await db.execute(text("SELECT cancelled_at IS NULL FROM public.paper_triggers WHERE id = :i"),
                              {"i": fired})).scalar_one()
    assert state is True
