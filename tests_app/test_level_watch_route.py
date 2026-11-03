"""A-37 route (GC-IC1 step 4c): GET /api/strategies/{id}/level-watch, PUT / DELETE .../level-watch/{direction} on a
saved strategy. Answer states: none / set / cleared / another user's (404) / level not a number (422) / not a
direction (404 or 422 by FastAPI's path check, never stored)."""
from __future__ import annotations

import pytest
from test_adjustment_plan import _seeded
from test_strategy_alert_style import _call, app_db_url  # noqa: F401 - the shared fixture

OK, NOT_FOUND, UNPROCESSABLE = 200, 404, 422
NOT_A_NUMBER = "Enter the level as a number above zero, like 23800."


def _path(sid: int, direction: str | None = None) -> str:
    return f"/api/strategies/{sid}/level-watch" + ("" if direction is None else f"/{direction}")


async def test_set_read_and_clear_a_watch_per_direction(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, body = await _call("GET", _path(sid), "owner")
    assert (status, body) == (OK, {"strategy_id": sid, "above": None, "below": None}), body
    status, body = await _call("PUT", _path(sid, "above"), "owner", json={"level": "23800"})
    assert (status, body) == (OK, {"strategy_id": sid, "above": "23800", "below": None}), body
    status, body = await _call("PUT", _path(sid, "below"), "owner", json={"level": " 23000.5 "})
    assert (status, body) == (OK, {"strategy_id": sid, "above": "23800", "below": "23000.5"}), body
    status, body = await _call("PUT", _path(sid, "above"), "owner", json={"level": "23900"})  # replaces, one active
    assert body["above"] == "23900", body
    status, body = await _call("DELETE", _path(sid, "above"), "owner")
    assert (status, body) == (OK, {"strategy_id": sid, "above": None, "below": "23000.5"}), body
    status, body = await _call("DELETE", _path(sid, "below"), "owner")
    assert (status, body) == (OK, {"strategy_id": sid, "above": None, "below": None}), body


@pytest.mark.parametrize("level", ["abc", "", "NaN", "0", "-5", "Infinity"])
async def test_a_level_that_is_not_a_number_above_zero_is_refused_and_not_stored(app_db_url, monkeypatch, level):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, body = await _call("PUT", _path(sid, "above"), "owner", json={"level": level})
    assert (status, body) == (UNPROCESSABLE, {"reason": NOT_A_NUMBER}), body
    status, body = await _call("GET", _path(sid), "owner")
    assert body["above"] is None, body


async def test_another_users_strategy_is_not_found_for_every_method(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    for method, path, kw in (("GET", _path(sid), {}), ("PUT", _path(sid, "above"), {"json": {"level": "23800"}}),
                             ("DELETE", _path(sid, "above"), {})):
        status, _body = await _call(method, path, "someone-else", **kw)
        assert status == NOT_FOUND, (method, status)
    status, body = await _call("GET", _path(sid), "owner")
    assert body["above"] is None, body  # the other user's PUT stored nothing


async def test_a_direction_other_than_above_or_below_is_refused(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    status, _body = await _call("PUT", _path(sid, "sideways"), "owner", json={"level": "23800"})
    assert status in (NOT_FOUND, UNPROCESSABLE), status
    status, body = await _call("GET", _path(sid), "owner")
    assert body == {"strategy_id": sid, "above": None, "below": None}, body
