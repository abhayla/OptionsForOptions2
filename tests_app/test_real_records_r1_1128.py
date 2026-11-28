# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane R1 stage 2 (28 Nov 2026; ADR-330 (73), ADR-281, ADR-016 to ADR-019): a REAL position's open, add, exit and stop
go through the same routes and checks as paper and are stored in ``real_action_records``, never in ``paper_orders``;
nothing is sent. Spec basis: ADR-330 (73), (58). Real PostgreSQL on the recorded replay, rolled back.
Answer states: stored, repeated press (same request key), market closed, kind unreadable, held position, paper."""
from __future__ import annotations

import datetime
import uuid
from http import HTTPStatus

import pytest
from ofo_app import strategy_store
from ofo_app.routes.outcome import get_answer_clock
from sqlalchemy import text
from test_exit_door_real_fd3 import _sent_basket
from test_order_request_key_r2_fd2 import _use, keys  # noqa: F401 - fixtures
from test_paper_armed_exits import _order
from test_paper_routes import _new
from test_paper_save_paths_fx2 import _count, db  # noqa: F401 - fixture
from test_paper_triggers_routes import notified  # noqa: F401 - fixture
from test_strategy_store import _client

_RECORDS = text("SELECT action, trigger_id, request_key FROM public.real_action_records "
                "WHERE strategy_id = :s ORDER BY id")


async def _records(db, sid: int):
    return [tuple(r) for r in (await db.execute(_RECORDS, {"s": sid})).all()]


async def _post(app, sid: int, orders, **extra):
    async with _client(app) as c:
        return await c.post(f"/paper/strategies/{sid}/orders", json={"orders": [_order(o) for o in orders], **extra})


async def test_an_exit_on_a_real_position_is_stored_as_a_record_and_nothing_else(db, notified):
    app, stored, ids = await _sent_basket(db)
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    body = reply.json()
    print("ANSWER", {k: body.get(k) for k in ("position_kind", "stored_not_sent", "record", "status_word")})
    assert body["position_kind"] == "real" and body["stored_not_sent"] is True
    assert body["record"]["action"] == "exit" and body["record"]["price"]
    assert body["status_word"] == "Running"  # the row stays open until the broker shows it closed
    assert [r[0] for r in await _records(db, stored.id)] == ["exit"]
    assert await _count(db, stored.id) == 0  # no paper order
    assert (await strategy_store.kinds_of(db, [stored.id]))[stored.id] == "real"  # the tag never flipped


async def test_open_and_add_on_a_real_position_are_records_too(db, notified):
    app, stored, ids = await _sent_basket(db)
    for kind in ("add", "open"):
        reply = await _post(app, stored.id, [_new(ids[0], "SELL", 65, "39.15", kind)])
        assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
        assert reply.json()["record"]["action"] == kind
    assert [r[0] for r in await _records(db, stored.id)] == ["add", "open"]
    assert await _count(db, stored.id) == 0


async def test_a_repeated_press_with_the_same_request_key_stores_one_record(db, notified, keys):
    app, stored, ids = await _sent_basket(db)
    _use(app, keys)
    key = str(uuid.uuid4())
    first = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")], client_request_id=key)
    again = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")], client_request_id=key)
    assert first.status_code == again.status_code == HTTPStatus.CREATED, (first.text[:200], again.text[:200])
    assert again.json()["record"] == first.json()["record"]
    assert [r[0] for r in await _records(db, stored.id)] == ["exit"]


async def test_a_real_exit_with_the_market_closed_is_refused_and_nothing_is_stored(db, notified):
    app, stored, ids = await _sent_basket(db)
    saturday = datetime.datetime(2026, 11, 28, 5, 30, tzinfo=datetime.UTC)
    app.dependency_overrides[get_answer_clock] = lambda: lambda: saturday
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code >= HTTPStatus.BAD_REQUEST, reply.text[:300]
    assert await _records(db, stored.id) == [] and await _count(db, stored.id) == 0


async def test_an_unreadable_kind_refuses_every_order_and_stores_nothing(db, notified, monkeypatch):
    app, stored, ids = await _sent_basket(db)

    async def unknown(_db, sids):
        return dict.fromkeys(sids, "unknown")
    monkeypatch.setattr("ofo_app.strategy_store.kinds_of", unknown)
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.SERVICE_UNAVAILABLE, reply.text[:300]
    assert await _records(db, stored.id) == [] and await _count(db, stored.id) == 0


async def test_a_held_position_stores_its_exit_as_a_record_and_its_add_stays_a_paper_order(db, notified):
    import datetime as _dt  # noqa: PLC0415

    from ofo.marketdata.kite_provider import IST  # noqa: PLC0415
    from ofo_app import held_entry_store  # noqa: PLC0415
    from test_paper_adjustment_limit import _book  # noqa: PLC0415
    app, stored, ids = await _book(db, max_adjustments=None)  # no plan maximum: the add below is not the limit's test
    await held_entry_store.record(db, stored.id, _dt.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    before = await _count(db, stored.id)
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert [r[0] for r in await _records(db, stored.id)] == ["exit"] and await _count(db, stored.id) == before
    reply = await _post(app, stored.id, [_new(ids[2], "SELL", 65, "82.75", "add")])  # Q3 interim: as before
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert await _count(db, stored.id) == before + 1 and len(await _records(db, stored.id)) == 1


async def test_a_paper_strategy_is_unchanged_it_stores_orders_and_carries_no_record(db, notified):
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)
    before = await _count(db, stored.id)
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    body = reply.json()
    assert body["position_kind"] == "paper" and body["stored_not_sent"] is None and body["record"] is None
    assert await _count(db, stored.id) == before + 1 and await _records(db, stored.id) == []


async def test_a_stop_on_a_real_position_is_armed_stored_as_a_record_and_listed_as_armed(db, notified):
    app, stored, ids = await _sent_basket(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/triggers",
                             json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above", "level": "120.00"})
        assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
        body = reply.json()
        (row,) = body["triggers"]
        assert row["state"] == "armed" and row["not_applicable_text"] is None  # real reads armed, not "not applicable"
        assert body["position_kind"] == "real" and body["stored_not_sent"] is True
        assert row["record"]["action"] == "stop" and row["stored_not_sent"] is True
        listed = (await c.get(f"/real/strategies/{stored.id}/triggers")).json()["triggers"]
    assert [(t["id"], t["state"]) for t in listed] == [(row["id"], "armed")]
    assert [r[0] for r in await _records(db, stored.id)] == ["stop"] and await _count(db, stored.id) == 0


async def test_a_stop_on_a_leg_the_plan_does_not_have_is_refused_by_name(db, notified):
    app, stored, _ids = await _sent_basket(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/triggers",
                             json={"kind": "leg_stop", "contract_id": 999999999, "direction": "above", "level": "9.00"})
    assert reply.status_code >= HTTPStatus.BAD_REQUEST
    assert await _records(db, stored.id) == []


@pytest.mark.parametrize("sql", ["UPDATE public.real_action_records SET reason = 'x'",
                                 "DELETE FROM public.real_action_records"])
async def test_a_record_is_append_only_even_through_a_route_made_row(db, notified, sql):
    from sqlalchemy.exc import DBAPIError  # noqa: PLC0415
    app, stored, ids = await _sent_basket(db)
    await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql + " WHERE strategy_id = :s"), {"s": stored.id})


# ---- Opus review F1 (Lane R1, Q2 interim): a stored exit cancels the stops it covers ---------------------------------

async def _arm(db, stored, ids):
    from decimal import Decimal  # noqa: PLC0415

    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    leg0 = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", Decimal("120.00"),
                                                                 contract_id=ids[0]))
    leg1 = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", Decimal("40.00"),
                                                                 contract_id=ids[1]))
    index = await triggers.add(db, stored.id, triggers.NewTrigger("conditional_exit", "above", Decimal("23100"),
                                                                  underlying="NIFTY"))
    return leg0, leg1, index


async def _armed_ids(db, sid: int) -> set[int]:
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    return {r.trigger.id for r in await triggers.list_for(db, sid) if r.cancelled_at is None and r.fired_at is None}


async def test_a_partial_exit_cancels_only_the_leg_stop_of_the_exited_leg(db, notified):
    app, stored, ids = await _sent_basket(db)
    leg0, leg1, index = await _arm(db, stored, ids)
    assert await _armed_ids(db, stored.id) == {leg0, leg1, index}
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert [c["contract"] for c in reply.json()["cancelled_stops"]] == [ids[0]]
    assert await _armed_ids(db, stored.id) == {leg1, index}


async def test_an_exit_of_every_leg_cancels_every_armed_stop_so_no_alert_follows_a_closed_position(db, notified):
    app, stored, ids = await _sent_basket(db)
    leg0, leg1, index = await _arm(db, stored, ids)
    assert await _armed_ids(db, stored.id) == {leg0, leg1, index}
    legs = stored.saved.definition.legs
    orders = [_new(c, "BUY" if leg.action.value == "SELL" else "SELL", leg.quantity, "30", "exit")
              for c, leg in zip(ids, legs, strict=True)]
    reply = await _post(app, stored.id, orders)
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert await _armed_ids(db, stored.id) == set()


async def test_an_add_cancels_no_stop(db, notified):
    app, stored, ids = await _sent_basket(db)
    leg0, leg1, index = await _arm(db, stored, ids)
    reply = await _post(app, stored.id, [_new(ids[0], "SELL", 65, "39.15", "add")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    assert await _armed_ids(db, stored.id) == {leg0, leg1, index}


@pytest.mark.parametrize(("quantity", "side"), [(0, "BUY"), (-65, "BUY"), (65, "HOLD"), (65, ""), (True, "BUY")])
async def test_the_record_store_refuses_a_leg_with_a_bad_quantity_or_side(db, quantity, side):
    import datetime as _dt  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from ofo_app import real_action_store  # noqa: PLC0415
    _app, stored, ids = await _sent_basket(db)
    with pytest.raises(ValueError, match="quantity"):
        await real_action_store.record(
            db, user_ref=stored.user_ref, strategy_id=stored.id, action="exit",
            legs=[real_action_store.Leg(ids[0], side, quantity, Decimal("30"))],
            stored_at=_dt.datetime(2026, 11, 27, 10, 0, tzinfo=_dt.UTC))
    assert await _records(db, stored.id) == []


# ---- Lane R2's need: every row of GET /paper/strategies carries position_kind (never missing) ---------------

async def _paper_list(app) -> dict:
    async with _client(app) as c:
        reply = await c.get("/paper/strategies")
    assert reply.status_code == HTTPStatus.OK, reply.text[:300]
    return {row["strategy_id"]: row for row in reply.json()["strategies"]}


async def test_the_paper_list_names_the_kind_of_a_paper_row(db, notified):
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, _ids = await _open(db)
    row = (await _paper_list(app))[stored.id]
    assert (row["position_kind"], row["stored_not_sent"], row["record"]) == ("paper", None, None)


async def test_the_paper_list_names_a_real_row_with_its_newest_record(db, notified):
    import datetime as _dt  # noqa: PLC0415

    from ofo.marketdata.kite_provider import IST  # noqa: PLC0415
    from ofo_app import held_entry_store  # noqa: PLC0415
    from test_paper_adjustment_limit import _book  # noqa: PLC0415
    app, stored, ids = await _book(db, max_adjustments=None)
    await held_entry_store.record(db, stored.id, _dt.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    first = (await _paper_list(app))[stored.id]
    assert (first["position_kind"], first["stored_not_sent"], first["record"]) == ("real", True, None)
    reply = await _post(app, stored.id, [_new(ids[0], "BUY", 65, "30", "exit")])
    assert reply.status_code == HTTPStatus.CREATED, reply.text[:300]
    row = (await _paper_list(app))[stored.id]
    assert row["position_kind"] == "real" and row["stored_not_sent"] is True
    assert row["record"]["action"] == "exit" and row["record"]["text"]  # the page reads the stored exit from the row


async def test_the_paper_list_reads_unknown_for_every_row_when_the_kinds_cannot_be_read(db, notified, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, _ids = await _open(db)

    async def failing(_db, _sids):
        raise SQLAlchemyError("kind read failed")
    monkeypatch.setattr(strategy_store, "kinds_of", failing)
    row = (await _paper_list(app))[stored.id]
    assert row["position_kind"] == "unknown" and row["stored_not_sent"] is None  # never missing, never a 5xx


async def test_the_paper_list_reads_unknown_for_a_row_whose_kind_is_unknown(db, notified, monkeypatch):
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, _ids = await _open(db)

    async def unknown(_db, sids):
        return dict.fromkeys(sids, "unknown")
    monkeypatch.setattr(strategy_store, "kinds_of", unknown)
    row = (await _paper_list(app))[stored.id]
    assert row["position_kind"] == "unknown" and row["position_kind_text"]
