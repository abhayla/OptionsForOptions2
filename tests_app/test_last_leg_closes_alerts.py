"""Lane J2 item 2 (T1-09 of 27 Nov): closing the LAST leg of a trade closes the trade's open alerts at once, each with a
closed-by-system History row carrying the exit's own time. The PC's words (27 Nov 15:41, build ff0448b3): "No closing
sentence exists in History; open alerts only left Active later by themselves" (the worker lapsed them later).
Spec basis: ADR-330 (3) (an alert stays until the trader answers or the position it is about is gone; the system's close
is a History entry with its time), REQ-112 AC-2. Real database, as the limited ofo_app role (fixtures of
test_background_worker.py). The one exit door is ``paper_exit.exit_strategy`` (the user's Exit and the stop monitor).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.tracking.orderbook import net_positions
from ofo_app import paper_exit, paper_store
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the fixture is used by name
    _db_now,
    _watched_and_fresh_t03,
    app_db_url,
)

PRICE = D("100.00")


async def _rows(engine, sid: int, rule_id: str) -> list[tuple]:
    async with engine.connect() as conn:
        return [tuple(r) for r in (await conn.execute(text(
            "SELECT outcome, answer, answered_at FROM public.adjustment_suggestions "
            "WHERE strategy_id = :s AND rule_id = :r ORDER BY id"), {"s": sid, "r": rule_id})).all()]


async def _exit(engine, w, at, only):
    async with engine.begin() as conn:
        book = await paper_store.load(conn, w.strategy_id)
        net = {int(p.instrument_id): p.net_quantity
               for p in net_positions([o.order.as_paper() for o in book], {}).positions if p.net_quantity}
        chosen = None if only is None else [sorted(net)[0]]
        out = await paper_exit.exit_strategy(
            conn, user_ref=w.user_ref, strategy_id=w.strategy_id, kind="exit", prices=dict.fromkeys(net, PRICE),
            placed_at=at, only=chosen,
            write=lambda orders: paper_store.place(conn, w.user_ref, w.strategy_id, orders, entry=None))
        assert isinstance(out, paper_exit.Exited), out
    return len(net)


async def test_exiting_the_last_leg_closes_each_open_alert_at_once_with_the_exits_time(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    assert [r[0] for r in await _rows(app_db_url, w.strategy_id, "T-03")] == ["open"]
    at = await _db_now(app_db_url) - datetime.timedelta(seconds=5)
    await _exit(app_db_url, w, at, only=None)  # every leg: the last one closes the trade
    rows = await _rows(app_db_url, w.strategy_id, "T-03")
    assert [(r[0], r[1], r[2]) for r in rows] == [("lapsed", "closed_by_system", at)], rows


async def test_exiting_one_leg_of_several_leaves_the_alerts_open(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    at = await _db_now(app_db_url) - datetime.timedelta(seconds=5)
    legs = await _exit(app_db_url, w, at, only=[0])
    assert legs > 1
    assert [r[0] for r in await _rows(app_db_url, w.strategy_id, "T-03")] == ["open"]
