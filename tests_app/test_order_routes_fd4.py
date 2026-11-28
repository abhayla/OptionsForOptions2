"""FD4 item 7 (FD2 review F7): "a stop the monitor fired first is not named": the order reply's ``cancelled_stops``
lists only stops THIS request cancelled; a leg stop the monitor already fired is no stop the user's move removed.
(The other half of F7, "an unknown outcome keeps the key", is Lane FD3's durable request key: a crash between claim and
commit stores neither, see test_order_request_key_durable_fd3.py.) Real PostgreSQL; the test rolls back."""
# ruff: noqa: F811 - the imported fixtures are used as test arguments
from __future__ import annotations

from http import HTTPStatus

from httpx import ASGITransport, AsyncClient
from test_paper_armed_exits import _order, _stop
from test_paper_routes import _new
from test_paper_triggers_routes import _open, db, notified  # noqa: F401 - fixtures


async def test_a_leg_stop_the_monitor_fired_first_is_not_named_as_cancelled(db, notified):
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1])
    await _stop(app, stored, ids[0])
    (row,) = [r for r in await triggers.list_for(db, stored.id) if r.trigger.contract_id == ids[0]]
    assert await triggers.claim_fire(db, row.trigger.id)  # the monitor claims the stop first
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders",
                             json={"orders": [_order(_new(ids[2], "SELL", 65, "82.75"))]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    assert reply.json()["cancelled_stops"] == []  # a fired stop is fired, not cancelled by this request


async def test_fd5_a_stop_swept_inside_place_is_named_by_its_id_and_the_monitors_fired_one_is_not(db, notified):
    """FD5 item 2a: ``place`` returns the ids its stale-stop sweep cancelled (``_STALE_CANCEL ... RETURNING id``), and
    the route names exactly those plus the ids ``paper_trigger_store.cancel`` returned: no read-back by state."""
    import datetime  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from ofo.marketdata.kite_provider import IST  # noqa: PLC0415
    from ofo_app import paper_store  # noqa: PLC0415
    from ofo_app import paper_trigger_store as triggers  # noqa: PLC0415
    app, stored, ids = await _open(db)  # short 22800 CE (ids[0]), long 23000 CE (ids[1])
    await _stop(app, stored, ids[0])
    await _stop(app, stored, ids[1], "below", "5.00")
    rows = {r.trigger.contract_id: r.trigger.id for r in await triggers.list_for(db, stored.id)}
    assert await triggers.claim_fire(db, rows[ids[1]])  # the monitor fired the long leg's stop first
    swept: list[int] = []
    close = paper_store.NewOrder(ids[0], "BUY", 65, Decimal("30"), "exit",
                                  datetime.datetime(2026, 10, 13, 11, 0, tzinfo=IST))
    await paper_store.place(db, stored.user_ref, stored.id, [close], swept=swept)
    assert swept == [rows[ids[0]]]  # the closed leg's stop, by id; the fired one is not named
