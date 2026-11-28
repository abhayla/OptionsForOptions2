# ruff: noqa: F811 - the imported fixture is used as a test argument
"""Lane FD3 item 1 (I-158; ADR-330 (64), ADR-016 to ADR-019): a USER exit on a real or unknown position is refused at
the one write both save paths use, and by the tracking exit route; nothing is stored. Real PostgreSQL, rolled back."""
from __future__ import annotations

import datetime
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
