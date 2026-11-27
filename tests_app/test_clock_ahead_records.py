"""Lane J2 (27 Nov), deferred issue "a fired stop never executes while the monitor clock is ahead of the database
clock": migration 0054's guard refuses a suggestion row whose ``shown_at`` is after the database clock, so every fire
rolled back and no stop ran. The record time is a stamp, not a decision: a time after the database's clock is stored as
the database's clock. Real database, as the limited ofo_app role (same fixtures as test_plan_rupee_worker.py).
Spec basis: ADR-330 (3)(b), (47); ADR-016 (submitted is not executed)."""
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

AHEAD = datetime.timedelta(hours=1)


async def _times(engine, sid: int, rule_id: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT shown_at, shown_at <= clock_timestamp() FROM public.adjustment_suggestions "
            "WHERE strategy_id = :s AND rule_id = :r"), {"s": sid, "r": rule_id})).all()


async def test_a_fired_stop_note_is_stored_when_the_monitor_clock_is_ahead(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    ahead = await _db_now(app_db_url) + AHEAD
    async with app_db_url.connect() as conn, conn.begin():
        await actionable_alerts.inform(
            conn, w.user_ref, w.strategy_id, "stop_fired", "alert_fired_at", {"time": ahead}, at=ahead,
            rule_id="info:clock-ahead")
    rows = await _times(app_db_url, w.strategy_id, "info:clock-ahead")
    assert len(rows) == 1 and rows[0][1] is True, rows  # stored, and not after the database clock


async def test_a_plan_stop_alert_is_stored_when_the_worker_clock_is_ahead(app_db_url, monkeypatch):  # noqa: F811
    w, _ = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    ahead = await _db_now(app_db_url) + AHEAD
    opened = await background.DbGateStore().apply(
        w, [alert_gate.Opened(sl.RUPEE_LOSS_RULE, ahead, 0, D("400"), D("400.00"))])
    assert sl.RUPEE_LOSS_RULE in opened
    rows = await _times(app_db_url, w.strategy_id, sl.RUPEE_LOSS_RULE)
    assert len(rows) == 1 and rows[0][1] is True, rows
