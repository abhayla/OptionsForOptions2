# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane FD3 item 1 (I-158; ADR-330 (64), ADR-016 to ADR-019): a USER exit on a real or unknown position is refused at
the one write both save paths use, and by the tracking exit route; nothing is stored. Real PostgreSQL, rolled back."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

from ofo.marketdata.kite_provider import IST
from ofo_app import held_entry_store
from test_paper_adjustment_limit import _book
from test_paper_save_paths_fx2 import _count, db  # noqa: F401 - fixture
from test_paper_triggers_routes import notified  # noqa: F401 - fixture
from test_strategy_store import _client

REAL_SENTENCE = "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."


async def _held_book(db):
    app, stored, ids = await _book(db, max_adjustments=2)
    await held_entry_store.record(db, stored.id, datetime.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    return app, stored, ids


async def test_i158_a_tracking_exit_on_a_held_strategy_is_refused_and_nothing_is_stored(db):
    app, stored, _ids = await _held_book(db)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [2]})
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text[:200]
    assert REAL_SENTENCE in reply.json()["what_happened"] + " " + reply.json()["impact"]
    assert await _count(db, stored.id) == before


async def test_i158_a_paper_strategy_still_exits_on_the_tracking_route(db):
    app, stored, _ids = await _book(db, max_adjustments=2)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [2]})
    assert reply.status_code == HTTPStatus.OK, reply.text[:200]
    assert await _count(db, stored.id) == before + 1


async def test_i158_an_unknown_kind_is_refused_at_the_tracking_exit(db, monkeypatch):
    app, stored, _ids = await _book(db, max_adjustments=2)

    async def unknown(_db, sids):
        return dict.fromkeys(sids, "unknown")

    monkeypatch.setattr("ofo_app.strategy_store.kinds_of", unknown)
    before = await _count(db, stored.id)
    async with _client(app) as c:
        reply = await c.post(f"/strategies/{stored.id}/tracking/exit", json={"legs": [2]})
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text[:200]
    assert await _count(db, stored.id) == before


async def test_i158_place_checked_refuses_a_user_exit_on_a_held_strategy_but_not_a_server_stop(db):
    """The write itself (not the route) refuses; a server-written kind is never refused."""
    import pytest  # noqa: PLC0415
    from ofo_app import paper_limit, paper_store  # noqa: PLC0415
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    _app, stored, _ids = await _held_book(db)
    rows = await paper_store.load(db, stored.id)
    cid = rows[0].order.contract_id
    new = paper_store.NewOrder(cid, "BUY", rows[0].order.quantity, rows[0].order.price, "exit",
                               datetime.datetime(2026, 11, 27, 11, 0, tzinfo=IST))
    with pytest.raises(StrategyRefused) as err:
        await paper_limit.place_checked(db, "u", stored.id, [new], entry=None, ctx=None, at=new.placed_at,
                                        reader=None, rates=None, settings={})
    assert str(err.value) == "real_position_exit_refused"
    stop = paper_store.NewOrder(cid, "BUY", rows[0].order.quantity, rows[0].order.price, "stop", new.placed_at)
    assert await paper_limit.refuse_real_exit(db, stored.id, [stop]) is None


async def test_item3_a_failing_kinds_read_propagates_and_is_never_no_kinds(db):
    """FD3 item 3: kinds_of used to swallow every error and answer "unknown" for each id."""
    import pytest  # noqa: PLC0415
    from ofo_app import strategy_store  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    class Broken:
        async def execute(self, *_a, **_k):
            raise SQLAlchemyError("boom")

    with pytest.raises(SQLAlchemyError):
        await strategy_store.kinds_of(Broken(), [1])
    assert await strategy_store.kinds_of(Broken(), []) == {}  # nothing asked, nothing read


async def test_r6_an_old_armed_stop_on_a_real_position_reads_not_applicable_never_live(db, notified):
    """Coordinator 09:12 / Opus review R6: the row stays stored (nothing is removed without the owner), but the list
    never offers it as a live stop: state ``not_applicable`` with the position-kind sentence; paper is unchanged."""
    from decimal import Decimal  # noqa: PLC0415

    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    from test_paper_triggers_routes import _open  # noqa: PLC0415
    app, stored, ids = await _open(db)
    tid = await triggers.add(db, stored.id, triggers.NewTrigger("leg_stop", "above", Decimal("120.00"),
                                                                contract_id=ids[0]))
    async with _client(app) as c:
        paper = (await c.get(f"/paper/strategies/{stored.id}/triggers")).json()["triggers"]
    assert [(t["id"], t["state"], t["not_applicable_text"]) for t in paper] == [(tid, "armed", None)]
    await held_entry_store.record(db, stored.id, datetime.datetime(2026, 11, 27, 10, 0, tzinfo=IST), "Zerodha")
    async with _client(app) as c:
        for path in (f"/paper/strategies/{stored.id}/triggers", f"/real/strategies/{stored.id}/triggers"):
            rows = (await c.get(path)).json()["triggers"]
            assert [(t["id"], t["state"]) for t in rows] == [(tid, "not_applicable")], path
            assert rows[0]["not_applicable_text"] == REAL_SENTENCE
    assert [r.cancelled_at for r in await triggers.list_for(db, stored.id)] == [None]  # kept, not cancelled


# --- FD5 / N1 (second Opus review of round 2; ADR-330 (64), (58)): NO paper order of any kind on a real position ----

_ADD_AT = datetime.datetime(2026, 11, 27, 11, 0, tzinfo=IST)


async def _sent_basket(db):
    """A REAL position that is not held: a basket was sent (an execution plan) and no paper order exists."""
    from sqlalchemy import text  # noqa: PLC0415
    from test_strategy_tracking import _setup  # noqa: PLC0415
    app, stored, *_ = await _setup(db)
    await db.execute(text("INSERT INTO public.execution_plans (strategy_id, plan_number, action) "
                          "VALUES (:s, 1, 'ENTRY')"), {"s": stored.id})
    return app, stored, stored.saved.contract_ids


async def _kind(db, stored) -> str:
    from ofo_app import strategy_store  # noqa: PLC0415
    return (await strategy_store.kinds_of(db, [stored.id]))[stored.id]


async def test_n1_a_held_entry_records_an_add_and_an_open_but_refuses_an_exit_and_keeps_its_kind(db):
    """ADR-292 (4): the user records a broker change on a held position with the paper forms; ADR-330 (64): no exit
    (I-158, above). The kind stays real: the held row, not the order, makes it real."""
    import pytest  # noqa: PLC0415
    from ofo_app import paper_limit, paper_store  # noqa: PLC0415
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    _app, stored, _ids = await _held_book(db)
    first = (await paper_store.load(db, stored.id))[0].order
    before = await _count(db, stored.id)
    exit_ = paper_store.NewOrder(first.contract_id, "BUY", first.quantity, first.price, "exit", _ADD_AT)
    with pytest.raises(StrategyRefused):
        await paper_store.place(db, stored.user_ref, stored.id, [exit_])
    assert await _count(db, stored.id) == before
    add = paper_store.NewOrder(first.contract_id, first.side, first.quantity, first.price, "add", _ADD_AT)
    await paper_store.place(db, stored.user_ref, stored.id, [add])
    assert await _count(db, stored.id) == before + 1
    assert await _kind(db, stored) == "real"
    assert await paper_limit.refuse_real_position(db, stored.id, [add]) is None  # the door's own check agrees


async def test_n1_the_store_itself_refuses_an_open_on_a_real_position_and_the_kind_stays_real(db):
    """The structural guarantee: ``paper_store.place`` is the one door every paper order passes; a sent basket (a real
    position with no paper order) must not become a paper position by an order."""
    import pytest  # noqa: PLC0415
    from ofo_app import paper_store  # noqa: PLC0415
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    _app, stored, ids = await _sent_basket(db)
    assert await _kind(db, stored) == "real"
    new = paper_store.NewOrder(ids[0], "SELL", 65, Decimal("39.15"), "open", _ADD_AT)
    with pytest.raises(StrategyRefused) as err:
        await paper_store.place(db, stored.user_ref, stored.id, [new])
    assert str(err.value) == "real_position_exit_refused"
    assert await _count(db, stored.id) == 0
    assert await _kind(db, stored) == "real"  # never flipped to paper


async def test_n1_an_order_post_on_a_sent_basket_is_a_409_with_the_real_sentence_and_nothing_stored(db):
    from test_paper_armed_exits import _order  # noqa: PLC0415
    from test_paper_routes import _new  # noqa: PLC0415
    app, stored, ids = await _sent_basket(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_order(_new(ids[0], "SELL", 65, "39.15"))]})
    assert reply.status_code == HTTPStatus.CONFLICT, reply.text[:200]
    assert REAL_SENTENCE in reply.json()["what_happened"] + " " + reply.json()["impact"]
    assert await _count(db, stored.id) == 0
    assert await _kind(db, stored) == "real"


async def test_n1_an_unreadable_kind_refuses_every_order_kind_fail_closed(db, monkeypatch):
    import pytest  # noqa: PLC0415
    from ofo_app import paper_store  # noqa: PLC0415
    from ofo_app.strategy_refused import StrategyRefused  # noqa: PLC0415
    _app, stored, ids = await _book(db, max_adjustments=2)

    async def unknown(_db, sids):
        return dict.fromkeys(sids, "unknown")

    monkeypatch.setattr("ofo_app.strategy_store.kinds_of", unknown)
    before = await _count(db, stored.id)
    new = paper_store.NewOrder(ids[0], "SELL", 65, Decimal("39.15"), "add", _ADD_AT)
    with pytest.raises(StrategyRefused):
        await paper_store.place(db, stored.user_ref, stored.id, [new])
    assert await _count(db, stored.id) == before


async def test_n1_a_paper_strategy_and_a_held_entrys_own_first_basket_still_place(db):
    """No regression: kind ``none`` (an empty book: the held entry's first basket) and ``paper`` are allowed; the
    server's settle kind is never refused (ADR-292 settles a held position)."""
    from ofo_app import paper_store  # noqa: PLC0415
    from test_strategy_tracking import _setup  # noqa: PLC0415
    _app, stored, *_ = await _setup(db)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [paper_store.NewOrder(
        ids[0], "SELL", 65, Decimal("39.15"), "open", _ADD_AT)])  # kind none -> placed
    await paper_store.place(db, stored.user_ref, stored.id, [paper_store.NewOrder(
        ids[1], "BUY", 65, Decimal("12.95"), "add", _ADD_AT)])  # kind paper -> placed
    await held_entry_store.record(db, stored.id, _ADD_AT, "Zerodha")  # now real
    await paper_store.place(db, stored.user_ref, stored.id, [paper_store.NewOrder(
        ids[0], "BUY", 65, Decimal("0.00"), "settle", _ADD_AT)])  # a settle is the server's, never refused
    assert await _count(db, stored.id) == 3  # noqa: PLR2004 - open, add, settle
