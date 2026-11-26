"""ADR-330 (3), (4): GET /api/alerts/active, POST /api/alerts/{id}/answer, GET /api/alerts/history (real DB).

Asserts the EXACT key set of each reply: the frontend contract (frontend/src/lib/paperAlerts.js, mocked in
frontend/tests/alerts-actionable.test.js) reads exactly these names.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import test_adjustment_check as check_test
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean

app_db_url = check_test.app_db_url
OK, NOT_FOUND, CONFLICT, REFUSED = 200, 404, 409, 422
FIRED = datetime.datetime(2026, 11, 25, 11, 2, 20, tzinfo=IST)
STOPPED = datetime.datetime(2026, 11, 25, 11, 5, 1, tzinfo=IST)
ACTIVE_KEYS = {"id", "strategy_id", "strategy_name", "kind", "text", "fired_at", "fired_line", "no_longer_true_since",
               "no_longer_true_line", "answers"}
HISTORY_KEYS = {"id", "strategy_id", "strategy_name", "kind", "text", "fired_at", "fired_line", "answer",
                "answer_label", "answered_at", "closed_reason"}


async def _raise(engine, sid: int) -> int:
    async with engine.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=FIRED, value=D("15.5750"),
                                          threshold=D("15.4000"), trigger_id="T-06", stage=None)
        await aa.note_condition(conn, "owner", alert.id, still_true=False, at=STOPPED)
    return alert.id


async def test_active_answer_history_replies_and_errors(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    alert_id = await _raise(app_db_url, sid)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK and set(active) == {"count", "alerts"} and active["count"] == len(active["alerts"])
    mine = next(a for a in active["alerts"] if a["id"] == alert_id)
    assert set(mine) == ACTIVE_KEYS and mine["kind"] == "plan_loss_stop"
    assert (mine["fired_line"], mine["no_longer_true_line"]) == ("Fired at 11:02", "no longer true since 11:05")
    assert (mine["fired_at"], mine["no_longer_true_since"]) == ("2026-11-25T05:32:20Z", "2026-11-25T05:35:01Z")
    assert [a["code"] for a in mine["answers"]] == ["exit", "continue"] and set(mine["answers"][0]) == {"code", "label"}
    for body, code in (({"answer": ""}, REFUSED), ({"answer": "add_legs"}, REFUSED)):  # empty, not for this kind
        assert (await _call("POST", f"/api/alerts/{alert_id}/answer", body))[0] == code
    other = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"}, user="someone-else")
    assert other[0] == NOT_FOUND
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"]  # nothing written by a refusal
    status, done = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"})
    assert status == OK and set(done) == {"id", "answer", "answer_label", "answered_at"}
    assert (await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "exit"}))[0] == CONFLICT
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"] - 1
    status, history = await _call("GET", "/api/alerts/history")
    row = next(i for i in history["items"] if i["id"] == alert_id)
    assert status == OK and set(history) == {"items"} and set(row) == HISTORY_KEYS
    assert (row["answer"], row["answer_label"]) == ("continue", "Continue with the position")
    assert (row["fired_line"], row["answered_at"]) == ("Fired at 11:02", done["answered_at"])
    assert row["closed_reason"] is None
    assert mine["strategy_name"] == row["strategy_name"] == '"Scenario ADJ-02"'  # the user's name in the quoted slot
