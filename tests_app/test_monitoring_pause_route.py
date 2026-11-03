"""A-38 route (GC-IC1 step 4a): GET / PUT / DELETE /api/strategies/{id}/monitoring-pause on a saved strategy, the
route's clock pinned (``pause_now``) so the time of day is known. Answer states: none / set / expired / cleared /
another user's (404) / in the past, after the close, not a time (422 with the reason)."""
from __future__ import annotations

import datetime

from ofo.timeutil import IST
from ofo_app.routes import monitoring_pause as route
from test_adjustment_plan import _seeded
from test_strategy_alert_style import _call, app_db_url  # noqa: F401 - the shared fixture
from test_strategy_store import _user

DAY = datetime.date(2026, 11, 3)
OK, NOT_FOUND, UNPROCESSABLE = 200, 404, 422


def _at(h: int, m: int) -> datetime.datetime:
    return datetime.datetime.combine(DAY, datetime.time(h, m), IST)


def _clock(h: int, m: int) -> dict:
    return {route.pause_now: lambda: _at(h, m)}


async def _saved(engine, monkeypatch) -> tuple[str, int]:
    """Scenario ADJ-02's strategy of the V1 owner (seeded once per scenario; each test leaves its pause cleared)."""
    return "owner", await _seeded(engine, monkeypatch, "ADJ-02")


def _path(sid: int) -> str:
    return f"/api/strategies/{sid}/monitoring-pause"


def _shape(body: dict) -> tuple:
    return body["paused"], body["until"], body["state_text"]


async def test_set_read_expire_and_clear_a_pause(app_db_url, monkeypatch):  # noqa: F811
    user, sid = await _saved(app_db_url, monkeypatch)
    status, body = await _call("GET", _path(sid), user, _clock(10, 10))
    assert status == OK, body
    assert body["label"] == "Pause adjustment checks"
    assert _shape(body) == (False, None, "Adjustment checks are running. Stop-losses and exits always run.")
    status, body = await _call("PUT", _path(sid), user, _clock(10, 10), json={"until": "10:30"})
    assert status == OK, body
    assert _shape(body) == (True, "1030", "Adjustment checks paused until 10:30. Stop-losses and exits still run.")
    status, body = await _call("GET", _path(sid), user, _clock(10, 31))  # ends by itself
    assert _shape(body) == (False, "1030", "The pause ended at 10:30. Adjustment checks are running again.")
    await _call("PUT", _path(sid), user, _clock(10, 40), json={"until": "11:00"})
    status, body = await _call("DELETE", _path(sid), user, _clock(10, 41))
    assert status == OK, body
    assert _shape(body)[:2] == (False, None)
    status, body = await _call("GET", _path(sid), user, _clock(10, 42))
    assert _shape(body)[:2] == (False, None)


async def test_a_pause_on_another_users_strategy_is_not_found(app_db_url, monkeypatch):  # noqa: F811
    _owner, sid = await _saved(app_db_url, monkeypatch)
    for method, kw in (("GET", {}), ("PUT", {"json": {"until": "10:30"}}), ("DELETE", {})):
        status, _ = await _call(method, _path(sid), _user(), _clock(10, 10), **kw)
        assert status == NOT_FOUND, method


async def test_a_refused_end_names_its_reason_and_writes_nothing(app_db_url, monkeypatch):  # noqa: F811
    user, sid = await _saved(app_db_url, monkeypatch)
    cases = [((15, 20), "15:40", "Pick a time at or before the market close, 15:30."),  # attack 3
             ((10, 10), "10:00", "Pick a time later today than now."),
             ((10, 10), "ten", "Enter the end of the pause as a time, like 10:30.")]
    for (h, m), until, reason in cases:
        status, body = await _call("PUT", _path(sid), user, _clock(h, m), json={"until": until})
        assert (status, body["reason"]) == (UNPROCESSABLE, reason), until
    _status, body = await _call("GET", _path(sid), user, _clock(10, 10))
    assert _shape(body)[:2] == (False, None)
