"""ADR-330 (5)(b): a plan's rupee loss stop, once hit, is raised by the worker through ``actionable_alerts`` as ONE
alert of kind ``plan_rupee_loss`` (open, no answer yet) and nothing exits by itself: ``paper_orders`` is unchanged.

Real case: the S-21 base (max loss 2,600), a stop typed as Rs 400, the loss reaching Rs 400.00 (a repeat of the same
reading adds no second row). Same gate-store path as ``test_background_worker.py`` (the worker's one writer).
Spec basis: ADR-330 (5) and its Q3 answer (whole trade, before charges).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.adjustment import alert_gate
from ofo.adjustment import stop_lines as sl
from ofo_app import background
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the fixture is used by name
    _db_now,
    _watched_and_fresh_t03,
    app_db_url,
)


async def _orders(engine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.paper_orders"))).scalar_one()


async def test_rupee_loss_hit_raises_one_actionable_alert_and_places_no_order(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    before = await _orders(app_db_url)
    at = await _db_now(app_db_url)
    store = background.DbGateStore()
    opened = await store.apply(w, [alert_gate.Opened(sl.RUPEE_LOSS_RULE, at, 0, D("400"), D("400.00"))])
    again = await store.apply(w, [alert_gate.Opened(sl.RUPEE_LOSS_RULE, at + datetime.timedelta(minutes=9), 0,
                                                    D("400"), D("400.00"))])
    async with app_db_url.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, outcome, kind, value, threshold, answer FROM public.adjustment_suggestions "
            "WHERE strategy_id = :s AND rule_id = :r"), {"s": w.strategy_id, "r": sl.RUPEE_LOSS_RULE})).all()
        stops = (await conn.execute(text(
            "SELECT count(*) FROM public.adjustment_suggestions WHERE strategy_id = :s AND outcome = 'open' "
            "AND kind = 'plan_loss_stop'"), {"s": w.strategy_id})).scalar_one()
    assert [tuple(r) for r in rows] == [(opened[sl.RUPEE_LOSS_RULE], "open", "plan_rupee_loss", D("400.0000"),
                                         D("400.0000"), None)], rows
    assert again == opened  # the same alert, not a second one
    assert stops == 0  # no T-06 percent alert beside it
    assert await _orders(app_db_url) == before  # nothing exits by itself (ADR-003)
