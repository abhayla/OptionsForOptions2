"""I-03 (test plan 28 Nov 2026): answering Continue on a STOP alert clears it from Active and lowers the bell count by
exactly one; the row goes to History with answer ``continue`` and nothing exits. Covers both stop kinds: the percent
stop (``plan_loss_stop``) and the plan's rupee stop (``plan_rupee_loss``), raised as the worker raises them.
Spec basis: ADR-330 (3), (4) (bell = the unanswered actionable alerts), (5)(b).
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
import test_adjustment_check as check_test
from ofo.adjustment import stop_lines as sl
from ofo_app import actionable_alerts as aa
from sqlalchemy import text
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean
from test_alert_routes import FIRED

app_db_url = check_test.app_db_url
OK = 200


async def _orders(engine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.paper_orders"))).scalar_one()


@pytest.mark.parametrize(("rule", "kind", "value", "threshold"), [
    ("T-06", "plan_loss_stop", D("15.5750"), D("15.4000")),
    (sl.RUPEE_LOSS_RULE, "plan_rupee_loss", D("400.00"), D("400.00")),
])
async def test_continue_on_a_stop_alert_clears_it_and_lowers_the_bell_by_one(app_db_url, monkeypatch, rule, kind,  # noqa: F811
                                                                           value, threshold):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, rule, kind, at=FIRED, value=value, threshold=threshold,
                                          trigger_id=rule, stage=None)
    async with app_db_url.connect() as conn:
        bell_before = await aa.unanswered_count(conn, "owner")
    orders = await _orders(app_db_url)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK and active["count"] == bell_before and alert.id in [a["id"] for a in active["alerts"]]
    mine = next(a for a in active["alerts"] if a["id"] == alert.id)
    assert "continue" in [a["code"] for a in mine["answers"]], mine["answers"]

    status, done = await _call("POST", f"/api/alerts/{alert.id}/answer", {"answer": "continue"})
    assert status == OK and done["answer"] == "continue", done

    status, after = await _call("GET", "/api/alerts/active")
    assert status == OK and alert.id not in [a["id"] for a in after["alerts"]]
    assert after["count"] == bell_before - 1 == len(after["alerts"])  # the bell is the one list, minus exactly one
    async with app_db_url.connect() as conn:
        assert await aa.unanswered_count(conn, "owner") == bell_before - 1
    hist = (await _call("GET", "/api/alerts/answered"))[1]["items"]
    assert [h["answer"] for h in hist if h["id"] == alert.id] == ["continue"]
    assert await _orders(app_db_url) == orders  # Continue exits nothing
