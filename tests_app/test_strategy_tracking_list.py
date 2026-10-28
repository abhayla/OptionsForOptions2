"""GC-BP steps 4 + 5 over HTTP on the recorded replay: GET /tracking (every tracked strategy of the signed-in user,
booked / unbooked / total) and POST /strategies/{id}/tracking/exit (REQ-109 AC-4, AC-5; ADR-201 (2)).

The saved strategy is test_strategy_store's iron condor (65 units a leg): SELL 22800 CE, BUY 23000 CE, SELL 22400 PE,
BUY 22200 PE, entered at the recorded LTPs 39.15 / 12.95 / 82.75 / 35.80 (2026-10-08 09:20:09 IST). The feed then moves
to 45.15 / 14.95 / 70.75 / 30.80. By hand: (39.15 - 45.15) x 65 = -390.00; (14.95 - 12.95) x 65 = +130.00;
(82.75 - 70.75) x 65 = +780.00; (30.80 - 35.80) x 65 = -325.00 -> total +195.00.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import strategy_store as store
from ofo_app import tracking_store
from ofo_app.routes import tracking as tracking_routes
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _client, _saved_in
from test_strategy_tracking import (
    _RETIRE,
    IDS,
    _frame,
    _setup,
)

D = Decimal


@pytest.fixture
async def db(app_engine):
    """The rolled-back connection (as test_strategy_tracking): no test leaves a row in the insert-only tables."""
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()
MOVED = ["45.15", "14.95", "70.75", "30.80"]


def _move(provider, last, prices=MOVED):
    for iid, rupees in zip(IDS, prices, strict=True):
        provider.on_frame(_frame(provider, iid, rupees), last)


async def _tracked(db, count: int = 1):
    """``count`` tracked strategies of one user (all on the same condor), then the feed moved to MOVED."""
    app, stored, provider, clock, last = await _setup(db)
    ids = [stored.id]
    for _ in range(count - 1):
        ids.append(  # noqa: PERF401 - awaited one at a time
            (await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref,
                                                                               await _contract_ids(db)))).id)
    async with _client(app) as c:
        for sid in ids:
            started = await c.post(f"/strategies/{sid}/tracking", json={"revision": 1})
            assert started.status_code == HTTPStatus.CREATED, started.text
    _move(provider, last)
    return app, ids, provider, clock, last


async def _contract_ids(db):
    from test_strategy_store import _ids  # noqa: PLC0415

    return await _ids(db)


async def _exits(db, strategy_id: int) -> list[tuple[int, Decimal]]:
    rows = await db.execute(text("SELECT leg_index, exit_price FROM public.strategy_tracking_exits "
                                 "WHERE strategy_id = :i ORDER BY leg_index"), {"i": strategy_id})
    return [(int(r[0]), r[1]) for r in rows]


# --- step 4: GET /tracking -------------------------------------------------------------------------------------------

async def test_list_none_tracked_is_an_empty_list(db):
    app, *_ = await _setup(db)
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code == HTTPStatus.OK and listed.json()["strategies"] == []


async def test_list_all_live_gives_total_booked_unbooked_and_leg_fields(db):
    app, ids, *_ = await _tracked(db, 2)
    async with _client(app) as c:
        body = (await c.get("/tracking")).json()
    assert [s["strategy_id"] for s in body["strategies"]] == ids
    first = body["strategies"][0]
    assert (first["state"], first["total"], first["booked"], first["unbooked"], first["underlying"]) == (
        "LIVE", "195.00", "0.00", "195.00", "NIFTY")
    assert "detections" not in first and body["answered_at"]
    leg = first["legs"][0]
    assert {k: leg[k] for k in ("leg_index", "action", "instrument", "strike", "quantity", "entry_price",
                                "current_price", "price_state", "exit_price", "exited_at")} == {
        "leg_index": 0, "action": "SELL", "instrument": "CE", "strike": "22800.00", "quantity": 65,
        "entry_price": "39.15", "current_price": "45.15", "price_state": "live", "exit_price": None, "exited_at": None}


async def test_list_never_shows_another_users_tracking(db):
    _app, ids, *_ = await _tracked(db)
    other, *_ = await _setup(db)
    async with _client(other) as c:
        body = (await c.get("/tracking")).json()
    assert ids[0] not in [s["strategy_id"] for s in body["strategies"]]


async def test_list_paused_strategy_keeps_booked_and_drops_unbooked_and_total(db):
    app, ids, _provider, clock, last = await _tracked(db)
    async with _client(app) as c:
        exited = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
        assert exited.status_code == HTTPStatus.OK, exited.text
        clock.now = last + datetime.timedelta(minutes=10)
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["pause_reason"], row["booked"], row["unbooked"], row["total"]) == (
        "PAUSED", "prices_not_live", "-390.00", None, None)
    assert row["as_of"] is not None


async def test_list_not_connected_keeps_booked(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
        app.dependency_overrides[tracking_routes.get_market_context] = lambda: None
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["booked"], row["unbooked"], row["total"]) == ("NOT_CONNECTED", "-390.00", None, None)


async def test_list_expired_contract_pauses_with_its_reason_never_crashes(db):
    app, ids, *_ = await _tracked(db)
    await db.execute(text(_RETIRE), {"id": (await _leg_contracts(db, ids[0]))[0]})
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code == HTTPStatus.OK
    row = listed.json()["strategies"][0]
    assert (row["state"], row["pause_reason"], row["total"], row["legs"][0]["price_state"]) == (
        "PAUSED", "contract_retired", None, "contract_retired")


async def _leg_contracts(db, sid):
    return [int(r[0]) for r in await db.execute(text(
        "SELECT contract_id FROM public.strategy_tracking_legs WHERE strategy_id = :i ORDER BY leg_index"), {"i": sid})]


async def test_list_fully_exited_strategy_is_exited_with_total_equal_booked_and_no_market_read(db, monkeypatch):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit",
                             json={"legs": [0, 1, 2, 3]})).status_code == HTTPStatus.OK
        reads = []
        real = tracking_routes.read_snapshot
        monkeypatch.setattr(tracking_routes, "read_snapshot", lambda *a, **k: reads.append(a) or real(*a, **k))
        row = (await c.get("/tracking")).json()["strategies"][0]
    assert (row["state"], row["total"], row["booked"], row["unbooked"]) == ("EXITED", "195.00", "195.00", "0.00")
    assert reads == []


async def test_list_read_failure_is_refused_never_a_partial_list(db, monkeypatch):
    app, *_ = await _tracked(db)

    async def broken(*_a, **_k):
        raise RuntimeError("read failed")

    monkeypatch.setattr(tracking_store, "load_all", broken)
    async with _client(app) as c:
        listed = await c.get("/tracking")
    assert listed.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR and "strategies" not in listed.text


async def _list_cost(db, count: int, monkeypatch) -> tuple[int, int]:
    app, *_ = await _tracked(db, count)
    statements = []
    reads = []
    real = tracking_routes.read_snapshot
    monkeypatch.setattr(tracking_routes, "read_snapshot", lambda *a, **k: reads.append(a) or real(*a, **k))

    def counted(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    event.listen(db.sync_engine, "before_cursor_execute", counted)
    try:
        async with _client(app) as c:
            body = (await c.get("/tracking")).json()
    finally:
        event.remove(db.sync_engine, "before_cursor_execute", counted)
    assert len(body["strategies"]) == count
    return len(statements), len(reads)


async def test_list_cost_does_not_grow_from_2_to_6_tracked_strategies(db, monkeypatch):
    """Finding F-3: a fixed number of queries and ONE market read per underlying, whatever the count."""
    two = await _list_cost(db, 2, monkeypatch)
    six = await _list_cost(db, 6, monkeypatch)
    assert two == six and two[1] == 1, (two, six)


# --- step 5: POST /strategies/{id}/tracking/exit ---------------------------------------------------------------------

async def test_exit_books_the_leg_at_its_live_price_and_freezes_it(db):
    app, ids, provider, _clock, last = await _tracked(db)
    async with _client(app) as c:
        exited = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
        assert exited.status_code == HTTPStatus.OK, exited.text
        body = exited.json()
        assert (body["state"], body["booked"], body["unbooked"], body["paper_pnl"]) == (
            "LIVE", "-390.00", "585.00", "195.00")
        assert (body["legs"][0]["price_state"], body["legs"][0]["exit_price"]) == ("exited", "45.15")
        assert body["legs"][0]["exited_at"] is not None
        _move(provider, last, ["50.00", *MOVED[1:]])  # the exited leg moves: booked must not
        view = (await c.get(f"/strategies/{ids[0]}/tracking")).json()
    assert (view["booked"], view["unbooked"], view["paper_pnl"]) == ("-390.00", "585.00", "195.00")
    assert await _exits(db, ids[0]) == [(0, D("45.15"))]


async def test_exit_refused_when_a_named_leg_is_not_live_and_nothing_is_stored(db):
    app, ids, _provider, clock, last = await _tracked(db)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0, 1]})
    assert refused.status_code == HTTPStatus.CONFLICT
    assert "Prices are not live; try again when they update" in refused.text
    assert await _exits(db, ids[0]) == []


async def test_a_leg_exits_once(db):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [2]})).status_code == HTTPStatus.OK
        again = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [2, 3]})
    assert again.status_code == HTTPStatus.CONFLICT and "already been exited" in again.text
    assert await _exits(db, ids[0]) == [(2, D("70.75"))]


@pytest.mark.parametrize("body", [{"legs": [4]}, {"legs": []}, {"legs": [0, 0]}, {"legs": [0], "price": "1.00"},
                                  {"legs": [-1]}], ids=["unknown", "empty", "twice", "extra_key", "negative"])
async def test_exit_body_refused_422(db, body):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json=body)
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _exits(db, ids[0]) == []


async def test_exit_of_an_untracked_or_another_users_strategy_is_404_and_not_connected_409(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{stored.id}/tracking/exit",
                             json={"legs": [0]})).status_code == HTTPStatus.NOT_FOUND
    app, ids, *_ = await _tracked(db)
    other, *_ = await _setup(db)
    async with _client(other) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit",
                             json={"legs": [0]})).status_code == HTTPStatus.NOT_FOUND
    app.dependency_overrides[tracking_routes.get_market_context] = lambda: None
    async with _client(app) as c:
        refused = await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})
    assert refused.status_code == HTTPStatus.CONFLICT and "not connected" in refused.text
    assert await _exits(db, ids[0]) == []


@pytest.mark.parametrize("sql", ["UPDATE public.strategy_tracking_exits SET exit_price = 1 WHERE strategy_id = :i",
                                 "DELETE FROM public.strategy_tracking_exits WHERE strategy_id = :i"],
                         ids=["update", "delete"])
async def test_paper_exit_rows_are_append_only(db, sql):
    app, ids, *_ = await _tracked(db)
    async with _client(app) as c:
        assert (await c.post(f"/strategies/{ids[0]}/tracking/exit", json={"legs": [0]})).status_code == HTTPStatus.OK
    nested = await db.begin_nested()
    with pytest.raises(DBAPIError):
        await db.execute(text(sql), {"i": ids[0]})
    await nested.rollback()
    assert await _exits(db, ids[0]) == [(0, D("45.15"))]
