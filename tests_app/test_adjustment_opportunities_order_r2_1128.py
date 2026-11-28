"""I-82 (test plan 28 Nov 2026), the order of what the user is shown. Decided here (B2, owner asleep) from the code's
own sort rules, each pinned on a real database: Active and the Adjustment ideas list are NEWEST FIRST by the time the
alert was raised; a LAPSED idea leaves Active and stays in the ideas list at the place of its own raise time (it
does not
jump to the top because it closed later); History is by the time each row ended (answered or closed, else raised), so
a stop-out note and a lapsed idea sort by their own end times, newest first.
Real case (25 Nov 2026, the ADJ-02 condor): plan loss stop raised 11:00 (closed by the system 11:30), rule T-01 11:05,
rupee stop 11:10, stop-out note 11:20, a second stop-out note 11:25.
Spec basis: ADR-330 (3) (Active, History), (4) (the bell is the Active list), (3b) (informational rows, History only).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import test_adjustment_check as check_test
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from ofo_app import playbook_store as pbs
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean

app_db_url = check_test.app_db_url
OK = 200
NOTE = {"loss": D("12000.00"), "loss_pct": D("61.5"), "stop": D("11700.00"), "stop_pct": D("60")}


def _at(hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 11, 25, hour, minute, tzinfo=IST)


async def test_active_ideas_and_history_orders_with_a_lapsed_idea_and_stop_out_notes(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        loss = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=_at(11, 0), value=D("15.5"),
                                         threshold=D("15.4"), trigger_id="T-06", stage=None)
        rule = await aa.raise_actionable(conn, "owner", sid, "T-01", "adjustment_rule", at=_at(11, 5), value=D("1"),
                                         threshold=D("2"), trigger_id="T-01", stage=None)
        rupee = await aa.raise_actionable(conn, "owner", sid, "plan.rupee_loss", "plan_rupee_loss", at=_at(11, 10),
                                          value=D("400"), threshold=D("400"), trigger_id="plan.rupee_loss", stage=None)
        note1 = await aa.inform(conn, "owner", sid, "stop_fired", "stop_fired_loss", NOTE, at=_at(11, 20))
        note2 = await aa.inform(conn, "owner", sid, "stop_fired", "stop_fired_loss", NOTE, at=_at(11, 25))
        await aa.close_by_system(conn, "owner", sid, pbs.LAPSE_STRATEGY_CLOSED, at=_at(11, 30), ids=[loss.id])
    ids = {loss.id, rule.id, rupee.id, note1, note2}

    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK
    assert [a["id"] for a in active["alerts"] if a["id"] in ids] == [rupee.id, rule.id]  # newest first
    assert active["count"] == len(active["alerts"])

    status, history = await _call("GET", "/api/alerts/answered")
    assert status == OK
    assert [h["id"] for h in history["items"] if h["id"] in ids] == [loss.id, note2, note1]  # by end time, newest first
    assert {h["id"]: h["kind"] for h in history["items"] if h["id"] in ids}[loss.id] == "plan_loss_stop"

    status, inbox = await _call("GET", "/api/adjustment-opportunities")
    assert status == OK
    flat = [(r["id"], r["outcome"]) for g in inbox["groups"] if g["strategy_id"] == sid for r in g["records"]
            if r["id"] in ids]
    assert flat == [(rupee.id, "open"), (rule.id, "open"), (loss.id, "lapsed")]  # lapsed stays at its own raise time
