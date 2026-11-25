"""GC-TP step 7a (REQ-109 AC-8; ADR-207 (5)): trigger and alert routes, real PostgreSQL, every test rolled back.

Core: POST /paper/strategies/{id}/triggers stores an armed trigger and notifies the monitor; GET /paper/alerts returns
the alert rows the monitor wrote (written here with the store's own add_alert after a claim, as the monitor does).
"""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
import test_strategy_tracking as tst
from ofo.errors.explanations import render_explanation
from ofo.rules.inputs import DataHealth
from ofo.tracking.paper_alert import alert_body
from ofo_app import paper_monitor, paper_store, paper_trigger_store
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_paper_routes import _new
from test_strategy_store import _app, _client, _remove_own_rows
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
from ofo_app import market_read, paper_settlement  # noqa: E402
from ofo_app.routes import paper as paper_routes  # noqa: E402
from ofo_app.routes.outcome import get_answer_clock, get_market_context  # noqa: E402

# ADR-327 (25 Nov 2026, supersedes ADR-317 (2) in market hours): market open and the level cannot be checked against a
# live price -> 422 and nothing stored; market closed -> saved. The replay is 09:20 IST on a Thursday (market open).
UNREADABLE_SENTENCE = "the live price could not be read, so this level cannot be checked. Try again in a moment."
SATURDAY = datetime.datetime(2026, 10, 10, 6, 0, tzinfo=datetime.UTC)  # 11:30 IST


def _close_the_market(app) -> None:
    """The same replay context with a Saturday clock (the market calendar says closed); the answer clock too."""
    ctx = app.dependency_overrides[get_market_context]()
    closed = dataclasses.replace(ctx, clock=lambda: SATURDAY) if ctx is not None else None
    app.dependency_overrides[get_market_context] = lambda: closed
    app.dependency_overrides[get_answer_clock] = lambda: lambda: SATURDAY


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


async def test_f1_no_market_context_in_market_hours_is_refused_and_when_closed_it_saves(db, notified):
    app, stored, *_ = await _setup(db, ctx=None)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [_new(ids[0], "SELL", 65, "39.15")])
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
        assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text
        assert await _stored(db, stored.id) == [] and notified == []
        _close_the_market(app)  # ADR-327 (3): closed, unchanged: saved, arms at the next live tick
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert len(await _stored(db, stored.id)) == 1 and notified == [1]


async def test_f1_a_failed_price_read_in_market_hours_is_refused(db, notified, monkeypatch):
    app, stored, _ids = await _open(db)

    def boom(*_a, **_k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(market_read, "read_snapshot", boom)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text
    assert await _stored(db, stored.id) == []


async def test_f1_a_closed_market_saves_as_before(db, notified):
    app, stored, _ids = await _open(db)
    _close_the_market(app)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert len(await _stored(db, stored.id)) == 1


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


# ---- D-05 / ADR-317 (3): the reply says when NOTHING new was stored; the armed set is read under the
# strategy lock ----

async def test_d05_an_identical_second_save_says_already_set_and_stores_one_row(db, notified):
    app, stored, _ = await _open(db)
    ce = {"kind": "conditional_exit", "above": "23100"}
    async with _client(app) as c:
        first = await c.post(_url(stored), json=ce)
        again = await c.post(_url(stored), json=ce)
    assert first.json()["already_set"] is False and again.json()["already_set"] is True
    assert first.json()["already_armed"] == [] and again.json()["already_armed"] == ["above"]
    assert len([r for r in again.json()["triggers"] if r["state"] == "armed"]) == 1
    assert len(await _stored(db, stored.id)) == 1


STORED_ROWS = 2  # rows stored before the refused save


async def test_d05_a_save_with_one_new_side_stores_it_and_is_not_already_set(db, notified):
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
        both = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
    assert both.json()["already_set"] is False
    assert both.json()["already_armed"] == ["above"]  # D-05 r3: the server names which submitted level was not stored
    assert len(await _stored(db, stored.id)) == STORED_ROWS


async def test_d05_r3_already_armed_names_every_duplicate_side_and_none_when_all_are_new(db, notified):
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        fresh = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        same = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100.00", "below": "22000"})
    assert fresh.json()["already_armed"] == [] and fresh.json()["already_set"] is False
    assert sorted(same.json()["already_armed"]) == ["above", "below"] and same.json()["already_set"] is True


async def test_d05_the_route_takes_the_strategy_row_lock_before_reading_the_armed_set(db, notified, monkeypatch):
    app, stored, _ = await _open(db)
    seen: list[str] = []
    real_lock, real_list = paper_routes.store.lock_strategy, paper_trigger_store.list_for

    async def lock(*a, **k):
        seen.append("lock")
        return await real_lock(*a, **k)

    async def listed(*a, **k):
        seen.append("list")
        return await real_list(*a, **k)

    monkeypatch.setattr(paper_routes.store, "lock_strategy", lock)
    monkeypatch.setattr(paper_trigger_store, "list_for", listed)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
    assert reply.status_code == HTTPStatus.CREATED and seen[0] == "lock" and "list" in seen


async def test_d05_a_cancelled_or_fired_identical_trigger_does_not_block_a_new_save(db, notified):
    app, stored, _ = await _open(db)
    ce = {"kind": "conditional_exit", "above": "23100"}
    async with _client(app) as c:
        first = (await c.post(_url(stored), json=ce)).json()["triggers"][0]["id"]
        assert (await c.delete(_url(stored, f"/{first}"))).status_code == HTTPStatus.OK
        again = await c.post(_url(stored), json=ce)
        assert again.json()["already_set"] is False
        second = next(r for r in again.json()["triggers"] if r["state"] == "armed")["id"]
        assert await paper_trigger_store.claim_fire(db, second)
        third = await c.post(_url(stored), json=ce)
    assert third.json()["already_set"] is False
    assert sorted(r["state"] for r in third.json()["triggers"]) == ["armed", "cancelled", "fired"]


async def test_d05_the_same_level_typed_two_ways_is_one_trigger(db, notified):
    app, stored, _ = await _open(db)
    async with _client(app) as c:
        first = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "25720"})
        again = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "25720.00"})
    assert first.json()["already_set"] is False and again.json()["already_set"] is True
    assert len(await _stored(db, stored.id)) == 1


async def _remove_committed(admin_engine, user: str, contract_ids: list[int]) -> None:
    """Deletes exactly this test's committed rows: every row that names its strategies, then the strategies,
    contracts."""
    async with admin_engine.connect() as conn, conn.begin():
        await conn.execute(text("SET LOCAL session_replication_role = replica"))
        tables = [r[0] for r in await conn.execute(text(
            "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables t "
            "ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
            "WHERE c.table_schema = 'public' AND c.column_name = 'strategy_id' ORDER BY 1"))]
        for table in tables:
            await conn.execute(text(f'DELETE FROM public."{table}" WHERE strategy_id IN '  # noqa: S608
                                    "(SELECT id FROM public.strategies WHERE user_ref = :u)"), {"u": user})
    await _remove_own_rows(admin_engine, contract_ids, user)


async def test_d05_two_identical_saves_at_one_instant_on_two_connections_store_one_row(app_engine, admin_engine,
                                                                                         notified, monkeypatch):
    """REAL concurrency: committed rows, two apps on two separate sessions/connections, both POSTs sent together.
    Without the strategy row lock both read an empty armed set and both insert (run once with the lock line removed)."""
    ids: list[int] = []
    user = ""
    real_user = tst._user

    def _remembered_user():  # the user is known before _setup commits, so a failing set-up is still cleaned up
        nonlocal user
        user = real_user()
        return user
    monkeypatch.setattr(tst, "_user", _remembered_user)
    try:
        async with app_engine.connect() as conn, conn.begin():
            app, stored, *_ = await _setup(conn)
            ids, user = list(stored.saved.contract_ids), stored.user_ref
            await paper_store.place(conn, user, stored.id, [_new(ids[0], "SELL", 65, "39.15"),
                                                            _new(ids[1], "BUY", 65, "12.95")])
        apps = []
        for _ in range(2):
            fresh = _app(async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False), user)
            fresh.dependency_overrides.update({k: v for k, v in app.dependency_overrides.items()
                                               if k not in fresh.dependency_overrides})
            apps.append(fresh)
        rounds = ["23100", "23200", "23300", "23400", "23500"]
        async with _client(apps[0]) as c1, _client(apps[1]) as c2:
            for level in rounds:
                body = {"kind": "conditional_exit", "above": level}
                r1, r2 = await asyncio.gather(c1.post(_url(stored), json=body), c2.post(_url(stored), json=body))
                assert (r1.status_code, r2.status_code) == (HTTPStatus.CREATED, HTTPStatus.CREATED)
                assert sorted([r1.json()["already_set"], r2.json()["already_set"]]) == [False, True], level
        async with app_engine.connect() as conn:
            count = (await conn.execute(text("SELECT count(*) FROM public.paper_triggers WHERE strategy_id = :i"),
                                        {"i": stored.id})).scalar_one()
        assert count == len(rounds)
    finally:
        if user:
            await _remove_committed(admin_engine, user, ids)


# ---- D-01 (ADR-317 (1), (2)): the crossed-level refusal wording and every answer state -----------------------------
CE_SENTENCE = ("the live price is already at or beyond this level, so this exit would close the trade straight away. "
               "To close now, use Exit.")
LEG_SENTENCE = ("the live price is already at or beyond this level, so this stop would close the leg straight away. "
                "To close now, use Exit.")


@pytest.mark.parametrize("body, stored_rows", [
    ({"kind": "conditional_exit", "above": "22533.25"}, 0),  # at the level: refused
    ({"kind": "conditional_exit", "below": "22533.25"}, 0),
    ({"kind": "conditional_exit", "above": "22533.30"}, 1),  # one tick on the safe side: stored
    ({"kind": "conditional_exit", "below": "22533.20"}, 1),
    ({"kind": "conditional_exit", "above": "22533.20"}, 0),  # price above the level: refused
    ({"kind": "conditional_exit", "below": "22533.30"}, 0),  # price below the level: refused
])
async def test_d01_at_the_level_refuses_one_tick_safe_stores(db, notified, body, stored_rows):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=body)
    assert reply.status_code == (HTTPStatus.CREATED if stored_rows else HTTPStatus.UNPROCESSABLE_ENTITY), reply.text
    assert len(await _stored(db, stored.id)) == stored_rows


async def test_d01_the_reply_says_the_approved_sentence_for_an_exit_and_for_a_leg_stop(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        ce = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
        ls = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above",
                                              "level": "35.00"})
    assert CE_SENTENCE in ce.text
    assert LEG_SENTENCE in ls.text and CE_SENTENCE not in ls.text
    assert await _stored(db, stored.id) == [] and notified == []


async def test_d01_a_crossed_side_with_a_safe_side_refuses_the_whole_request(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500", "below": "22000"})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and CE_SENTENCE in reply.text
    assert await _stored(db, stored.id) == [] and notified == []  # the safe "below" half is not stored


async def test_d01_a_price_that_is_not_live_is_never_used_to_refuse_and_in_market_hours_refuses_the_save(
        db, notified, monkeypatch):
    app, stored, _ids = await _open(db)
    real = market_read.read_snapshot
    body = {"kind": "conditional_exit", "above": "22500"}
    async with _client(app) as c:  # control: the live index price refuses this level, so the check really runs
        control = await c.post(_url(stored), json=body)
    assert control.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and await _stored(db, stored.id) == []

    def stale(*a, **k):
        snap = real(*a, **k)
        return dataclasses.replace(snap, spot=dataclasses.replace(snap.spot, health=DataHealth.STALE))

    monkeypatch.setattr(market_read, "read_snapshot", stale)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=body)
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text  # ADR-327
    assert await _stored(db, stored.id) == []


@pytest.mark.parametrize("direction, level", [("above", "35.00"), ("below", "35.00")])
async def test_d01_a_leg_with_no_feed_key_is_never_judged_on_the_index_and_is_refused_in_market_hours(
        db, notified, monkeypatch, direction, level):
    app, stored, ids = await _open(db)
    real = paper_routes.tracked_contracts.resolve

    async def no_key(d, cids):
        return [dataclasses.replace(c, state="contract_retired") for c in await real(d, cids)]

    monkeypatch.setattr(paper_routes.tracked_contracts, "resolve", no_key)
    body = {"kind": "leg_stop", "contract_id": ids[0], "direction": direction, "level": level}
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=body)
        assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text  # ADR-327
        assert await _stored(db, stored.id) == []
        _close_the_market(app)  # closed: ADR-327 (3), saved as before
        reply = await c.post(_url(stored), json=body)
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert [r[:4] for r in await _stored(db, stored.id)] == [("leg_stop", direction, D(level), ids[0])]


async def test_d01_a_stale_leg_price_with_a_live_index_is_refused_as_unreadable_and_a_live_one_as_crossed(
        db, notified, monkeypatch):
    app, stored, ids = await _open(db)
    body = {"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "35.00"}
    async with _client(app) as c:  # control: live leg price 39.15 is above 35 -> refused
        control = await c.post(_url(stored), json=body)
    assert control.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and await _stored(db, stored.id) == []
    real = market_read.read_snapshot

    def stale_legs(*a, **k):
        snap = real(*a, **k)
        legs = {k2: dataclasses.replace(m, quote=dataclasses.replace(m.quote, health=DataHealth.STALE))
                for k2, m in snap.legs.items()}
        return dataclasses.replace(snap, legs=legs)

    monkeypatch.setattr(market_read, "read_snapshot", stale_legs)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json=body)
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text  # ADR-327
    assert await _stored(db, stored.id) == []


async def test_d01_a_failed_price_read_is_refused_and_is_logged(db, notified, monkeypatch, caplog):
    app, stored, _ids = await _open(db)

    def boom(*_a, **_k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(market_read, "read_snapshot", boom)
    async with _client(app) as c:
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "above": "22500"})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and UNREADABLE_SENTENCE in reply.text
    assert await _stored(db, stored.id) == []
    assert any("paper trigger price read failed" in r.getMessage() for r in caplog.records)


# ---- D-03 (ADR-317 (7)): an index exit set before an adjustment stays armed, is marked, and is never moved ----
_LATER = datetime.timedelta(hours=1)


def _later(n: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC) + n * _LATER


def _at(order: paper_store.NewOrder, n: int) -> paper_store.NewOrder:
    return paper_store.NewOrder(order.contract_id, order.side, order.quantity, order.price, order.kind, _later(n))


async def _adjust(db, stored, orders, n):
    await paper_store.place(db, stored.user_ref, stored.id, [_at(o, n) for o in orders])


async def _armed_exits(c, stored):
    rows = (await c.get(_url(stored))).json()["triggers"]
    return {(r["direction"], r["state"]): r for r in rows}


async def test_d03_an_exit_set_before_an_adjustment_is_marked_with_the_new_short_strike(db, notified):
    app, stored, ids = await _open(db)  # entry: short call 22800, long call 23000
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        rows = await _armed_exits(c, stored)
        # no adjustment
        assert [(r["set_before_adjustment"], r["adjustment_note"]) for r in rows.values()] == [(False, None)] * 2
        await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
        rows = await _armed_exits(c, stored)
    above, below = rows[("above", "armed")], rows[("below", "armed")]
    assert above["set_before_adjustment"] is True and below["set_before_adjustment"] is True
    assert above["adjustment_note"] == (
        "Exit above 23,100.00 was set before this change; your new short call is 22,800. Check this level.")
    assert below["adjustment_note"] == (
        "Exit below 22,000.00 was set before this change; your new short put is 22,400. Check this level.")


async def test_d03_an_exit_set_after_the_adjustment_is_not_marked(db, notified):
    app, stored, ids = await _open(db)
    await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
        row = (await _armed_exits(c, stored))[("above", "armed")]
    assert (row["set_before_adjustment"], row["adjustment_note"]) == (False, None)


async def test_d03_no_short_left_on_that_side_says_so(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
        await _adjust(db, stored, [_new(ids[0], "BUY", 65, "30", "exit"), _new(ids[1], "SELL", 65, "10", "exit"),
                                   _new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
        row = (await _armed_exits(c, stored))[("above", "armed")]
    assert row["adjustment_note"] == (
        "Exit above 23,100.00 was set before this change; you no longer hold a short call. Check this level.")


async def test_d03_the_mark_is_relative_to_the_latest_adjustment_and_a_kept_exit_is_marked_again(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        first = (await c.post(_url(stored),
                              json={"kind": "conditional_exit", "above": "23100"})).json()["triggers"][0]["id"]
        await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
        kept = await c.post(_url(stored, f"/{first}/keep"))
        assert kept.status_code == HTTPStatus.OK, kept.text
        rows = {r["id"]: r for r in kept.json()["triggers"]}
        # one transaction: the old row goes, a new armed row with the same level
        assert rows[first]["state"] == "cancelled"
        [new] = [r for r in rows.values() if r["state"] == "armed"]
        assert (new["id"] != first, new["level"], new["direction"],
                new["set_before_adjustment"]) == (True, "23100.00", "above", False)
        assert notified[-1] == 1
        await _adjust(db, stored, [_new(ids[3], "SELL", 65, "30", "exit")], 2)  # a second adjustment
        again = (await _armed_exits(c, stored))[("above", "armed")]
        assert again["id"] == new["id"] and again["set_before_adjustment"] is True
        # keeping a cancelled exit is 409 and changes nothing; a missing one is 404
        assert (await c.post(_url(stored, f"/{first}/keep"))).status_code == HTTPStatus.CONFLICT
        assert (await c.post(_url(stored, "/999999999/keep"))).status_code == HTTPStatus.NOT_FOUND


async def test_d03_cancelled_fired_and_leg_stops_are_never_marked_and_a_full_exit_cancels_the_exits(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        await c.post(_url(stored),
                     json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "60"})
        rows = (await c.get(_url(stored))).json()["triggers"]
        down = next(r["id"] for r in rows if r["direction"] == "below" and r["kind"] == "conditional_exit")
        fired = next(r["id"] for r in rows if r["direction"] == "above" and r["kind"] == "conditional_exit")
        await c.delete(_url(stored, f"/{down}"))
        assert await paper_trigger_store.claim_fire(db, fired)
        await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
        rows = (await c.get(_url(stored))).json()["triggers"]
        assert [r["set_before_adjustment"]
                for r in rows if r["state"] != "armed" or r["kind"] == "leg_stop"] == [False] * 3
        await _adjust(db, stored, [_new(ids[i], s, 65, "20", "exit")
                                    for i, s in ((0, "BUY"), (1, "SELL"), (2, "BUY"), (3, "SELL"))], 2)
        assert [r["state"] for r in (await c.get(_url(stored))).json()["triggers"]
                if r["kind"] == "conditional_exit"] == ["cancelled", "fired"]


# ---- D-03 review round 2: any change to the open legs marks an armed exit, whatever changed them ----
_NO_CALL = "Exit above 23,100.00 was set before this change; you no longer hold a short call. Check this level."


async def test_d03r2_a_fired_leg_stop_that_closes_the_short_call_marks_the_armed_exit(db, notified):
    app, stored, ids = await _open(db)  # short call 22800 (ids[0]), long call 23000 (ids[1])
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
        # the leg stop fires: the short call closes
        await _adjust(db, stored, [_new(ids[0], "BUY", 65, "60", "stop")], 1)
        row = (await _armed_exits(c, stored))[("above", "armed")]
    assert (row["set_before_adjustment"], row["adjustment_note"]) == (True, _NO_CALL)


async def test_d03r2_one_expiry_settling_in_a_two_expiry_trade_marks_the_remaining_exits(db, notified):
    app, stored, ids = await _open(db)
    # puts: second expiry
    await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        await _adjust(db, stored,
                      [_new(ids[0], "BUY", 65, "0.05", "settle"), _new(ids[1], "SELL", 65, "0.05", "settle")], 2)
        rows = await _armed_exits(c, stored)
    assert rows[("above", "armed")]["adjustment_note"] == _NO_CALL
    assert rows[("below", "armed")]["adjustment_note"] == (
        "Exit below 22,000.00 was set before this change; your new short put is 22,400. Check this level.")


async def test_d03r2_a_manual_partial_exit_marks_the_armed_exit(db, notified):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100"})
        await _adjust(db, stored, [_new(ids[0], "BUY", 32, "30", "exit")], 1)  # half of the short call closed by hand
        row = (await _armed_exits(c, stored))[("above", "armed")]
    assert row["adjustment_note"] == (
        "Exit above 23,100.00 was set before this change; your new short call is 22,800. Check this level.")


async def test_d03r2_a_mark_that_cannot_be_worked_out_marks_every_armed_exit_with_the_generic_line(
        db, notified, monkeypatch, caplog):
    app, stored, _ids = await _open(db)

    def boom(*_a, **_k):
        raise RuntimeError("history unreadable")

    async with _client(app) as c:
        await c.post(_url(stored), json={"kind": "conditional_exit", "above": "23100", "below": "22000"})
        monkeypatch.setattr(paper_routes.ah, "adjustment_history", boom)
        rows = (await c.get(_url(stored))).json()["triggers"]
    assert [(r["set_before_adjustment"], r["adjustment_note"]) for r in rows] == [
        (True, "This exit could not be checked against your current legs. Check this level.")] * 2
    assert any("trigger marks could not be read" in r.getMessage() for r in caplog.records)


async def test_d03r2_keep_on_an_exit_that_is_not_marked_answers_normally_and_stores_nothing(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        first = (await c.post(_url(stored),
                              json={"kind": "conditional_exit", "above": "23100"})).json()["triggers"][0]["id"]
        kept = await c.post(_url(stored, f"/{first}/keep"))
        rows = (await c.get(_url(stored))).json()["triggers"]
    assert kept.status_code == HTTPStatus.OK, kept.text
    assert [(r["id"], r["state"]) for r in rows] == [(first, "armed")]


async def test_d03r2_keep_on_a_cancelled_exit_is_409(db, notified):
    app, stored, _ids = await _open(db)
    async with _client(app) as c:
        first = (await c.post(_url(stored),
                              json={"kind": "conditional_exit", "above": "23100"})).json()["triggers"][0]["id"]
        await c.delete(_url(stored, f"/{first}"))
        assert (await c.post(_url(stored, f"/{first}/keep"))).status_code == HTTPStatus.CONFLICT


async def test_d03r2_keep_while_the_monitor_fires_the_old_row_stores_no_new_row(db, notified, monkeypatch):
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        first = (await c.post(_url(stored),
                              json={"kind": "conditional_exit", "above": "23100"})).json()["triggers"][0]["id"]
        await _adjust(db, stored, [_new(ids[2], "SELL", 65, "82.75"), _new(ids[3], "BUY", 65, "35.80")], 1)
        real = paper_trigger_store.cancel

        async def fired_first(conn, strategy_id, trigger_id=None):  # the monitor wins the claim between read and cancel
            assert await paper_trigger_store.claim_fire(conn, trigger_id)
            return await real(conn, strategy_id, trigger_id)

        monkeypatch.setattr(paper_trigger_store, "cancel", fired_first)
        assert (await c.post(_url(stored, f"/{first}/keep"))).status_code == HTTPStatus.CONFLICT
        monkeypatch.setattr(paper_trigger_store, "cancel", real)
        rows = (await c.get(_url(stored))).json()["triggers"]
    # no stray armed row on the book (the claim itself is rolled back with this test's shared transaction, so the old
    # row's state is not asserted)
    assert [r["id"] for r in rows] == [first]


# D-22 / D-71 (owner decision 2026-11-24, REQ-109 AC-7, AC-8): a fired stop and an expiry settlement each leave a record
# in Alerts > History: time, what happened, the index value at that moment, the prices.
async def test_history_lists_a_fired_stop_and_an_expiry_settlement_with_time_index_value_and_prices(db, notified):
    from ofo_app import paper_settlement  # noqa: PLC0415
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        assert (await c.get("/paper/alerts/records")).json() == {"records": []}
        reply = await c.post(_url(stored), json={"kind": "conditional_exit", "below": "22000"})
        tid = reply.json()["triggers"][0]["id"]
        assert await paper_trigger_store.claim_fire(db, tid)
        dash = render_explanation("cell_dash")
        what = render_explanation("paper_stop_reason_index_at", what=render_explanation(
            "paper_stop_reason_index", underlying="NIFTY", direction="below", level=D("22000")),
            underlying="NIFTY", level=D("21999.90"))
        await paper_trigger_store.add_alert(
            db, stored.id, tid, str(render_explanation("paper_alert_title", name=dash)),
            str(alert_body(what, [(dash, D("41.00"))], names_contract=False)))
        at = datetime.datetime(2026, 11, 24, 10, 0, tzinfo=datetime.UTC)  # 15:30 IST, the exchange close
        why = str(paper_settlement.settle_reason("NIFTY", D("25641.35")))
        await paper_store.place(db, stored.user_ref, stored.id, [
            paper_store.NewOrder(ids[0], "BUY", 65, D("0.00"), "settle", at, why),
            paper_store.NewOrder(ids[1], "SELL", 65, D("246.03"), "settle", at, why)], entry=None)
        records = (await c.get("/paper/alerts/records")).json()["records"]
    assert sorted(r["kind"] for r in records) == ["settled", "stop"]
    settled = next(r for r in records if r["kind"] == "settled")
    assert settled["at"].startswith("2026-11-24T10:00:00")
    assert "Paper - settled at expiry: NIFTY closed at 25,641.35" in settled["body"]
    assert "0.00" in settled["body"] and "246.03" in settled["body"]
    assert "no order was sent to Zerodha" in settled["body"]
    stop = next(r for r in records if r["kind"] == "stop")
    assert "NIFTY was at 21,999.90 at that moment" in stop["body"]
    assert stop["strategy_id"] == settled["strategy_id"] == stored.id


# D-29 (ADR-260): the alert list and the bell's unread count read this process's own strategies only. Real case: 17 old
# "Scenario PATH-xx" alerts buried the 3 real stops of 23 Nov and inflated the bell (21-24 against 20 rows).
async def test_a_scenario_strategys_alert_is_neither_listed_nor_counted_nor_marked_read(db, notified):
    from ofo_app import strategy_store as store  # noqa: PLC0415
    from test_strategy_store import _ids, _saved_in  # noqa: PLC0415
    app, stored, ids = await _open(db)
    scenario = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, await _ids(db)),
                                      scenario_id="PATH-01")
    await paper_store.place(db, stored.user_ref, scenario.id, [_new(ids[0], "SELL", 65, "39.15"),
                                                               _new(ids[1], "BUY", 65, "12.95")])
    dash = render_explanation("cell_dash")
    what = render_explanation("paper_stop_reason_index", underlying="NIFTY", direction="below", level=D("22000"))
    body = str(alert_body(what, [(dash, D("41.00"))], names_contract=False))
    title = str(render_explanation("paper_alert_title", name=dash))
    for strategy in (stored, scenario):
        tid = await paper_trigger_store.add(db, strategy.id, paper_trigger_store.NewTrigger(
            "conditional_exit", "below", D("22000"), underlying="NIFTY"))
        assert await paper_trigger_store.claim_fire(db, tid)
        await paper_trigger_store.add_alert(db, strategy.id, tid, title, body)
    async with _client(app) as c:
        listed = (await c.get("/paper/alerts")).json()
        assert [a["strategy_id"] for a in listed["alerts"]] == [stored.id] and listed["unread"] == 1
        await c.post("/paper/alerts/read")
    sql = "SELECT count(*) FROM public.paper_alerts WHERE strategy_id = :s AND read_at IS NULL"
    unread = (await db.execute(text(sql), {"s": scenario.id})).scalar_one()
    assert unread == 1  # a live process never touches a scenario strategy's alerts


# D-22 / D-71 round 2: the closed row carries the reason; a scenario settlement is never listed.
async def test_the_closed_row_carries_the_settlement_reason_and_a_scenario_settlement_is_not_listed(db, notified):
    from ofo_app import paper_settlement  # noqa: PLC0415
    from ofo_app import strategy_store as store  # noqa: PLC0415
    from test_strategy_store import _ids, _saved_in  # noqa: PLC0415
    app, stored, ids = await _open(db)
    at = datetime.datetime(2026, 11, 24, 10, 0, tzinfo=datetime.UTC)
    why = str(paper_settlement.settle_reason("NIFTY", D("25641.35")))
    legs = [paper_store.NewOrder(ids[0], "BUY", 65, D("0.00"), "settle", at, why),
            paper_store.NewOrder(ids[1], "SELL", 65, D("246.03"), "settle", at, why)]
    await paper_store.place(db, stored.user_ref, stored.id, legs, entry=None)
    scenario = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, await _ids(db)),
                                      scenario_id="PATH-01")
    await paper_store.place(db, stored.user_ref, scenario.id, [_new(ids[0], "SELL", 65, "39.15"),
                                                               _new(ids[1], "BUY", 65, "12.95")])
    await paper_store.place(db, stored.user_ref, scenario.id, legs, entry=None)
    async with _client(app) as c:
        closed = (await c.get(f"/paper/strategies/{stored.id}")).json()["closed"]
        records = (await c.get("/paper/alerts/records")).json()["records"]
    assert sorted(r["reason_text"] for r in closed) == [why, why]
    assert [r["strategy_id"] for r in records] == [stored.id]
