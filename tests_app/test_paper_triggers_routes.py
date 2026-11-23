"""GC-TP step 7a (REQ-109 AC-8; ADR-207 (5)): trigger and alert routes, real PostgreSQL, every test rolled back.

Core: POST /paper/strategies/{id}/triggers stores an armed trigger and notifies the monitor; GET /paper/alerts returns
the alert rows the monitor wrote (written here with the store's own add_alert after a claim, as the monitor does).
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.errors.explanations import render_explanation
from ofo.tracking.paper_alert import alert_body
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
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        assert reply.status_code == HTTPStatus.CREATED, reply.text
        rows = reply.json()["triggers"]
        assert sorted((r["direction"], r["level_text"], r["state"]) for r in rows) == [
            ("above", "23,100.00", "armed"), ("below", "22,000.00", "armed")]
        assert notified == [1]
        tid = next(r["id"] for r in rows if r["direction"] == "below")
        assert await paper_trigger_store.claim_fire(db, tid)
        dash = render_explanation("cell_dash")
        title = str(render_explanation("paper_alert_title", name=dash))
        what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below",
                                  level=Decimal("22000"))
        leg = render_explanation("paper_alert_leg", contract=dash, price=dash)
        body = str(render_explanation("paper_alert_body", what=what, count=1, prices=leg))
        await paper_trigger_store.add_alert(db, stored.id, tid, title, body)
        alerts = (await c.get("/paper/alerts")).json()
        assert alerts["unread"] == 1 and [a["trigger_id"] for a in alerts["alerts"]] == [tid]
        assert (await c.get(_url(stored))).json()["triggers"][0]["id"] > 0
        read = (await c.post("/paper/alerts/read")).json()
        assert read["unread"] == 0 and read["alerts"][0]["read"] is True


_FOUR_TRIGGERS = ("any", "stop", "stop", "stop")  # a conditional exit (2 levels) + two leg stops


async def _alerts_after_storing(db, bodies_of):
    """Open a paper book with four armed triggers, store ``bodies_of(what, dash)`` as alerts, return the GET reply."""
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        for payload in ({"kind": "conditional_exit", "above": "23100", "below": "22000"},
                        {"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "120.00"},
                        {"kind": "leg_stop", "contract_id": ids[1], "direction": "below", "level": "5.00"}):
            reply = await c.post(_url(stored), json=payload)
            assert reply.status_code == HTTPStatus.CREATED, reply.text
        tids = [row["id"] for row in (await c.get(_url(stored))).json()["triggers"]]
        assert len(tids) == len(set(tids)) == len(_FOUR_TRIGGERS)
        dash = render_explanation("cell_dash")
        title = str(render_explanation("paper_alert_title", name=dash))
        what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below",
                                  level=D("22000"))
        bodies = bodies_of(what, dash)
        for tid, body in zip(tids, bodies, strict=False):
            assert await paper_trigger_store.claim_fire(db, tid)
            await paper_trigger_store.add_alert(db, stored.id, tid, title, body)
        return await c.get("/paper/alerts"), bodies


def _good_bodies(what, dash):
    safety = "A paper exit only: no order was sent to Zerodha."
    return [
        f"{what}; exited 1 legs at {dash} at {dash}. {safety}",  # written before 7babdba9
        str(alert_body(what, [(dash, D("41.00"))], names_contract=True)),
        str(alert_body(what, [(dash, D("41.00"))], names_contract=False)),
        str(alert_body(what, [(dash, D("41.00")), (dash, D("12.50"))], names_contract=False)),
    ]


async def test_alerts_list_reads_every_stored_form(db, notified):
    """Regression 7babdba9: the new one-leg wording made GET /paper/alerts answer 500 for the whole list."""
    reply, bodies = await _alerts_after_storing(db, _good_bodies)
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert sorted(a["body"] for a in reply.json()["alerts"]) == sorted(bodies)


async def test_alerts_list_leaves_out_one_unreadable_row_not_the_whole_list(db, notified):
    reply, bodies = await _alerts_after_storing(
        db, lambda what, dash: [_good_bodies(what, dash)[1], "hand written, no template"])
    assert reply.status_code == HTTPStatus.OK, reply.text
    assert [a["body"] for a in reply.json()["alerts"]] == [bodies[0]]


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
        rows = (await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
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


# ---- IC live test 23 Nov 2026 (REQ-109 AC-8; ADR-314-next): save-time checks and reconcile -------------------------
# The saved condor's market is the replay at 22,533.25 NIFTY; the legs' last prices are 39.15 (ids[0]), 12.95 (ids[1]).

import dataclasses  # noqa: E402

from ofo.engine.legs import Instrument  # noqa: E402
from ofo_app import paper_settlement  # noqa: E402
from ofo_app.routes import paper as paper_routes  # noqa: E402


async def _stored(db, strategy_id: int) -> list[tuple]:
    rows = await db.execute(text("SELECT kind, direction, level, contract_id, "
                                 "fired_at IS NULL AND cancelled_at IS NULL "
                                 "FROM public.paper_triggers WHERE strategy_id = :i ORDER BY id"), {"i": strategy_id})
    return [tuple(r) for r in rows.all()]


async def _orders(db, strategy_id: int) -> int:
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": strategy_id})).scalar_one()


@pytest.mark.parametrize("body", [
    {"kind": "conditional_exit", "above": "22500"},  # spot 22,533.25 is already above
    {"kind": "conditional_exit", "below": "22600"},  # already below
    {"kind": "conditional_exit", "above": "22533.25"},  # equal to the spot counts as crossed (stops.crossed: >=)
    {"kind": "conditional_exit", "above": "23100", "below": "22600"},  # one crossed side refuses both: nothing stored
    {"kind": "leg_stop", "direction": "above", "level": "35.00"},  # 39.15 already above 35
    {"kind": "leg_stop", "direction": "below", "level": "45.00"},
])
async def test_f1_a_level_already_crossed_is_refused_and_nothing_is_stored(db, notified, body):
    app, stored, ids = await _open(db)
    if body["kind"] == "leg_stop":
        body = body | {"contract_id": ids[0]}
    before = await _orders(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=body)
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "straight away" in reply.text and "Exit" in reply.text
    assert await _stored(db, stored.id) == [] and notified == []
    assert await _orders(db, stored.id) == before  # a refused save places no paper order


async def test_f1_a_level_not_yet_crossed_is_saved(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        ok = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22550", "below": "22400"})
    assert ok.status_code == HTTPStatus.CREATED, ok.text
    assert [r[:3] for r in await _stored(db, stored.id)] == [("conditional_exit", "above", D("22550.00")),
                                                              ("conditional_exit", "below", D("22400.00"))]


async def test_f1_no_market_context_saves_as_before_it_arms_at_the_next_live_tick(db, notified):
    app, stored, *_ = await _setup(db, ctx=None)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "SELL", 65, "39.15")])
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert len(await _stored(db, stored.id)) == 1 and notified == [1]


async def test_f1_a_failed_price_read_saves_as_before(db, notified, monkeypatch):
    app, stored, _ids = await _open(db)

    def boom(*_a, **_k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(paper_routes, "read_snapshot", boom)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_f1_a_closed_market_saves_as_before(db, notified, monkeypatch):
    app, stored, _ids = await _open(db)
    real = paper_routes.read_snapshot
    monkeypatch.setattr(paper_routes, "read_snapshot",
                        lambda *a, **k: dataclasses.replace(real(*a, **k), market_closed=True))
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_f2_the_same_armed_trigger_is_not_stored_twice(db, notified):
    app, stored, ids = await _open(db)
    ce = {"kind": "conditional_exit", "above": "23100"}
    ls = {"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "120.00"}
    async with _client(app) as c:
        first = await c.post(_url(stored), json=ce)
        again = await c.post(_url(stored), json=ce)
        await c.post(_url(stored), json=ls)
        await c.post(_url(stored), json=ls)
        await c.post(_url(stored), json={"kind": "conditional_exit", "below": "22000"})  # another side: a new trigger
        assert again.status_code == HTTPStatus.CREATED and len(first.json()["triggers"]) == 1
        assert [r["id"] for r in again.json()["triggers"]] == [r["id"] for r in first.json()["triggers"]]
        await c.delete(_url(stored, f"/{first.json()['triggers'][0]['id']}"))
        await c.post(_url(stored), json=ce)  # a cancelled one never blocks a new save
    assert [(r[0], r[1], r[4]) for r in await _stored(db, stored.id)] == [
        ("conditional_exit", "above", False), ("leg_stop", "above", True), ("conditional_exit", "below", True),
        ("conditional_exit", "above", True)]


async def _armed_set(db):
    app, stored, cids = await _open(db)
    async with _client(app) as c:
        for body in ({"kind": "conditional_exit", "above": "23100", "below": "22000"},
                     {"kind": "leg_stop", "contract_id": cids[0], "direction": "above", "level": "120.00"},
                     {"kind": "leg_stop", "contract_id": cids[1], "direction": "below", "level": "5.00"}):
            assert (await c.post(_url(stored), json=body)).status_code == HTTPStatus.CREATED
    return stored, cids


async def test_f3_a_leg_stop_goes_when_its_contract_is_flat_the_index_exits_stay(db, notified):
    stored, ids = await _armed_set(db)
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "BUY", 65, "30.00", "exit")])
    assert [(r[0], r[3], r[4]) for r in await _stored(db, stored.id)] == [
        ("conditional_exit", None, True), ("conditional_exit", None, True), ("leg_stop", ids[0], False),
        ("leg_stop", ids[1], True)]


async def test_f3_every_trigger_goes_when_no_leg_is_open(db, notified):
    stored, ids = await _armed_set(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(ids[0], "BUY", 65, "30.00", "stop"), _new(ids[1], "SELL", 65, "10.00", "exit")])
    assert {r[4] for r in await _stored(db, stored.id)} == {False}


async def test_f3_the_sibling_is_cancelled_when_a_fire_closes_the_trade(db, notified):
    stored, ids = await _armed_set(db)
    fired = (await db.execute(text("SELECT id FROM public.paper_triggers WHERE strategy_id = :i AND direction = "
                                   "'below' AND kind = 'conditional_exit'"), {"i": stored.id})).scalar_one()
    assert await paper_trigger_store.claim_fire(db, fired)
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(ids[0], "BUY", 65, "30.00", "stop"), _new(ids[1], "SELL", 65, "10.00", "stop")])
    rows = await db.execute(text("SELECT fired_at IS NOT NULL, cancelled_at IS NOT NULL FROM public.paper_triggers "
                                 "WHERE strategy_id = :i ORDER BY id"), {"i": stored.id})
    assert [tuple(r) for r in rows.all()] == [(False, True), (True, False), (False, True), (False, True)]


async def test_f3_a_new_open_order_leaves_every_trigger_armed(db, notified):
    stored, ids = await _armed_set(db)
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "SELL", 65, "39.15", "add")])
    assert all(r[4] for r in await _stored(db, stored.id))


async def test_f3_dry_run_names_what_it_would_cancel_and_writes_nothing(db, notified):
    stored, ids = await _armed_set(db)
    book = [o.order.as_paper() for o in await paper_store.load(db, stored.id)]
    assert await paper_store.reconcile_triggers(db, stored.id, book, dry_run=True) == []
    flat = [*book, _new(ids[0], "BUY", 65, "30.00", "exit").as_paper()]
    would = await paper_store.reconcile_triggers(db, stored.id, flat, dry_run=True)
    assert len(would) == 1 and all(r[4] for r in await _stored(db, stored.id))


async def test_f4_settling_the_expiring_legs_leaves_the_index_exits_of_the_open_legs_armed(db, notified):
    """IC live 23 Nov: calls expired, the puts stay open (a later expiry): the index exits must still be armed."""
    stored, ids = await _armed_set(db)
    expiry = datetime.date(2026, 10, 13)
    due = [paper_settlement.DueContract(stored.id, stored.user_ref, ids[0], "NIFTY", Instrument.CE, D("22800"), expiry),
           paper_settlement.DueContract(stored.id, stored.user_ref, ids[1], "NIFTY", Instrument.CE, D("23000"), expiry)]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(stored.saved.contract_ids[2], "SELL", 65, "82.75")])
    await paper_settlement._settle_strategy(db, due, {("NIFTY", expiry): D("22533.25")})
    assert [(r[0], r[3], r[4]) for r in await _stored(db, stored.id)] == [
        ("conditional_exit", None, True), ("conditional_exit", None, True), ("leg_stop", ids[0], False),
        ("leg_stop", ids[1], False)]
