"""I-90 (test plan 28 Nov 2026), Lane D re-tests of issues 745 and 749: a DELETED trade's plan is hidden everywhere and
every link to it answers 404, as a missing one does; its open alerts leave Active and the bell; Undo brings all back.
Real case: the ADJ-02 iron condor with its own plan and an open alert, hidden (``deleted_at``) as the delete does.
Spec basis: ADR-293 (a deleted strategy is hidden from every read), REQ-070 AC-6, ADR-330 (11) (a plan is the
strategy's own).
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
import test_adjustment_check as check_test
from ofo_app import actionable_alerts as aa
from sqlalchemy import text
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call
from test_alert_routes import FIRED

app_db_url = check_test.app_db_url
OK, NOT_FOUND = 200, 404
HIDE = text("UPDATE public.strategies SET deleted_at = now() WHERE id = :i")
SHOW = text("UPDATE public.strategies SET deleted_at = NULL WHERE id = :i")
LINKS = ["/api/strategies/{s}/adjustment-plan", "/api/strategies/{s}/adjustment-plan/rules",
         "/api/strategies/{s}/adjustment-plan/levels", "/api/strategies/{s}/plan-watch",
         "/api/strategies/{s}/adjustment-check", "/api/strategies/{s}/adjustment-history"]


async def _hide(engine, sid: int, *, hidden: bool) -> None:
    async with engine.begin() as conn:
        await conn.execute(HIDE if hidden else SHOW, {"i": sid})


@pytest.mark.parametrize("link", LINKS)
async def test_every_link_to_a_deleted_trades_plan_is_404_and_undo_brings_it_back(app_db_url, monkeypatch, link):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")  # with its plan
    url = link.format(s=sid)
    assert (await _call("GET", url))[0] == OK, "control: the visible trade's own link answers"
    await _hide(app_db_url, sid, hidden=True)
    status, body = await _call("GET", url)
    assert status == NOT_FOUND, (url, status, body)
    assert (await _call("GET", link.format(s=sid + 100000)))[1] == body  # as a missing one says it
    await _hide(app_db_url, sid, hidden=False)
    assert (await _call("GET", url))[0] == OK  # Undo: back


async def test_a_deleted_trades_alerts_and_ideas_leave_active_the_bell_and_the_list(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    async with app_db_url.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=FIRED, value=D("15.5"),
                                          threshold=D("15.4"), trigger_id="T-06", stage=None)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK and alert.id in [a["id"] for a in active["alerts"]]
    await _hide(app_db_url, sid, hidden=True)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK and alert.id not in [a["id"] for a in active["alerts"]]
    assert active["count"] == len(active["alerts"])  # the bell is that list
    inbox = (await _call("GET", "/api/adjustment-opportunities"))[1]
    assert sid not in [g["strategy_id"] for g in inbox["groups"]]
    status, batch = await _call("GET", f"/api/plan-watch?strategy_ids={sid}")
    assert status == OK and (batch["items"][0]["state"], batch["items"][0]["status"]) == ("refused", NOT_FOUND)
    assert (await _call("POST", f"/api/alerts/{alert.id}/answer", {"answer": "continue"}))[0] == NOT_FOUND  # the link
