"""I-02 (test plan 28 Nov 2026): a plan's rupee loss stop alert, once raised, is KEPT when the loss worsens (the same
open row is updated, ``escalated_at`` set, still one row) and when it recovers (the row stays open with "no longer true
since"; a loss past the line again clears that note and opens no second row). Nothing answers or exits by itself.

Real case: the S-21 base with a stop typed as Rs 400 (as ``test_plan_rupee_worker.py``): raised at 400.00, worse at
650.00, back under the line, past it again.
Spec basis: ADR-330 (3) (lapse note, one open row per rule), (5)(b), (47).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.adjustment import alert_gate
from ofo.adjustment import stop_lines as sl
from ofo_app import actionable_alerts, background
from sqlalchemy import text
from test_background_worker import (  # noqa: F401 - the fixture is used by name
    _db_now,
    _watched_and_fresh_t03,
    app_db_url,
)

_ROW = ("SELECT id, outcome, kind, value, no_longer_true_since, escalated_at, answer FROM public.adjustment_suggestions "
        "WHERE strategy_id = :s AND rule_id = :r AND id >= :first ORDER BY id")


async def _rows(engine, sid: int, first: int) -> list:
    async with engine.connect() as conn:
        return (await conn.execute(text(_ROW), {"s": sid, "r": sl.RUPEE_LOSS_RULE, "first": first})).all()


async def test_worse_then_recovered_loss_keeps_one_open_stop_alert(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    store = background.DbGateStore()
    t0 = await _db_now(app_db_url)
    minute = datetime.timedelta(minutes=1)
    opened = await store.apply(w, [alert_gate.Opened(sl.RUPEE_LOSS_RULE, t0, 0, D("400"), D("400.00"))])
    alert_id = opened[sl.RUPEE_LOSS_RULE]
    r = await _rows(app_db_url, w.strategy_id, alert_id)
    assert [(x.id, x.outcome, x.kind, x.value) for x in r] == [(alert_id, "open", "plan_rupee_loss", D("400.0000"))]
    assert r[0].escalated_at is None and r[0].no_longer_true_since is None

    # the loss worsens: the SAME row is updated (value 650), marked escalated, not a second alert
    again = await store.apply(w, [alert_gate.Escalated(sl.RUPEE_LOSS_RULE, t0 + minute, 1, D("400"), D("650.00"))])
    assert again[sl.RUPEE_LOSS_RULE] == alert_id
    r = await _rows(app_db_url, w.strategy_id, alert_id)
    assert len(r) == 1 and r[0].id == alert_id and r[0].outcome == "open", r
    assert r[0].value == D("650.0000"), r
    assert r[0].escalated_at is not None, r

    # the loss recovers under the line: the alert is KEPT (open) and notes "no longer true since"
    await store.apply(w, [alert_gate.Lapsed(sl.RUPEE_LOSS_RULE, t0 + 2 * minute, D("250.00"))])
    r = await _rows(app_db_url, w.strategy_id, alert_id)
    assert len(r) == 1 and r[0].outcome == "open" and r[0].answer is None, r
    assert r[0].no_longer_true_since is not None, r
    assert r[0].value == D("650.0000"), r  # the worst reading stays on the row, it is not rewritten by the recovery
    async with app_db_url.connect() as conn:
        assert [a.id for a in await actionable_alerts.unanswered(conn, "owner") if a.rule_id == sl.RUPEE_LOSS_RULE] \
            == [alert_id]  # still in Active, still counted by the bell

    # past the line again: the note clears, no second row
    await store.apply(w, [alert_gate.TrueAgain(sl.RUPEE_LOSS_RULE, t0 + 3 * minute, D("420.00"))])
    r = await _rows(app_db_url, w.strategy_id, alert_id)
    assert len(r) == 1 and r[0].outcome == "open" and r[0].no_longer_true_since is None, r
