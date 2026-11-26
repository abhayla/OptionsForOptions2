"""ADR-330 (3), (4): GET /api/alerts/active, POST /api/alerts/{id}/answer, GET /api/alerts/answered (real DB).

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
               "no_longer_true_line", "escalated_at", "worse_line", "answers"}
HISTORY_KEYS = {"id", "strategy_id", "strategy_name", "kind", "text", "fired_at", "fired_line", "escalated_at",
                "worse_line", "answer", "answer_label", "answered_at", "closed_reason"}


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
    assert (mine["escalated_at"], mine["worse_line"]) == (None, None)  # never worse: null, not an empty line
    assert [a["code"] for a in mine["answers"]] == ["exit", "continue"] and set(mine["answers"][0]) == {"code", "label"}
    for body, code in (({"answer": ""}, REFUSED), ({"answer": "add_legs"}, REFUSED),  # empty, not for this kind
                       ({"answer": "continue", "unnamed": 1}, REFUSED)):  # a closed body: an extra field is refused
        assert (await _call("POST", f"/api/alerts/{alert_id}/answer", body))[0] == code
    other = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"}, user="someone-else")
    assert other[0] == NOT_FOUND
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"]  # nothing written by a refusal
    status, done = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"})
    assert status == OK and set(done) == {"id", "answer", "answer_label", "answered_at"}
    assert (await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "exit"}))[0] == CONFLICT
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"] - 1
    status, history = await _call("GET", "/api/alerts/answered")
    row = next(i for i in history["items"] if i["id"] == alert_id)
    assert status == OK and set(history) == {"items"} and set(row) == HISTORY_KEYS
    assert (row["answer"], row["answer_label"]) == ("continue", "Continue with the position")
    assert (row["fired_line"], row["answered_at"]) == ("Fired at 11:02", done["answered_at"])
    assert row["closed_reason"] is None
    assert mine["strategy_name"] == row["strategy_name"] == f'"Scenario ADJ-02" (#{mine["strategy_id"]}, 9 Nov)'  # W2-A pin changed: ADR-330 (19)(b) label (was the bare quoted name)


ESCALATED = datetime.datetime(2026, 11, 25, 11, 9, 0, tzinfo=IST)


async def test_a_worse_reading_shows_escalated_at_and_the_worse_line_in_active_and_history(app_db_url, monkeypatch):
    """P1 round 3 F3 (contract): the open alert carries when a WORSE value of the same rule last updated it, and the
    catalogue's line; a later answer keeps both in History; a second worse reading moves escalated_at."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=FIRED, value=D("15.5750"),
                                          threshold=D("15.4000"), trigger_id="T-06", stage=None, unit="%", cmp="ge")
        worse = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=ESCALATED,
                                          value=D("16.2000"), threshold=D("15.4000"), trigger_id="T-06", stage=None)
    assert worse.id == alert.id
    status, active = await _call("GET", "/api/alerts/active")
    mine = next(a for a in active["alerts"] if a["id"] == alert.id)
    assert status == OK and set(mine) == ACTIVE_KEYS
    assert mine["escalated_at"] == "2026-11-25T05:39:00Z"
    assert mine["worse_line"] == "Worse than when it fired: 16.2000 % (fired at 15.5750 %)"
    assert mine["fired_at"] == "2026-11-25T05:32:20Z"  # the first-shown time never moves
    assert (await _call("POST", f"/api/alerts/{alert.id}/answer", {"answer": "continue"}))[0] == OK
    row = next(i for i in (await _call("GET", "/api/alerts/answered"))[1]["items"] if i["id"] == alert.id)
    assert set(row) == HISTORY_KEYS and (row["escalated_at"], row["worse_line"]) == (
        mine["escalated_at"], mine["worse_line"])


async def test_a_noted_row_in_history_is_catalogue_worded_and_never_a_500(app_db_url, monkeypatch):
    """P1 round 3 F4: an informational note (answer 'noted') comes back from the catalogue id and values it was stored
    with; it is never a stored plain string returned as catalogue text (that was a 500 for the whole History)."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        note_id = await aa.inform(conn, "owner", sid, "stop_fired", "stop_fired_loss", {
            "loss": D("12000.00"), "loss_pct": D("61.5"), "stop": D("11700.00"), "stop_pct": D("60")}, at=FIRED)
    status, history = await _call("GET", "/api/alerts/answered")
    row = next(i for i in history["items"] if i["id"] == note_id)
    assert status == OK and set(row) == HISTORY_KEYS and (row["answer"], row["kind"]) == ("noted", "stop_fired")
    assert row["text"] == ("Stop reached: loss now ₹12,000.00 (61.5 % of max loss); "
                           "stop line ₹11,700.00 (60 % of max loss)")
    active = (await _call("GET", "/api/alerts/active"))[1]
    # never counted
    assert active["count"] == len(active["alerts"]) and note_id not in [a["id"] for a in active["alerts"]]
