"""ADR-330 (7): the plan's time exit on any trading day, saved as {at, on}; blank date = expiry day (Q9).

Save refusals name the field time_exit: a weekend or holiday, a date before today, a date after the last expiry of
the legs. An old plain "HH:MM" plan still reads as expiry day. ADJ-02 is read on Fri 2026-11-06, legs expire Mon
2026-11-09. Spec basis: ADR-330 (7) and its Q9 answer.
"""
# ruff: noqa: E501, F811
from __future__ import annotations

import datetime
import json

import pytest
from ofo_app.routes import adjustment_plan as route
from ofo_app.routes.adjustment_plan import PlanIn, TimeExitIn
from sqlalchemy import text
from test_adjustment_plan import (
    OK,
    UNPROCESSABLE,
    _call,
    _plan_path,
    _plan_row,
    _seeded,
    app_db_url,  # noqa: F401 - a fixture, found by name
)

NOT_VALID = "The playbook value time_exit is not valid."


async def _system_ic_id(engine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT id FROM public.adjustment_playbooks WHERE is_system AND "
                                        "strategy_type = 'ic'"))).scalar_one()


@pytest.mark.parametrize("day", ["2026-11-07", "2026-11-05", "2026-11-10", "2026-11-31", "x", "2026-1-9"])
async def test_save_refuses_weekend_past_after_expiry_and_unreadable_dates_naming_the_field(
        app_db_url, monkeypatch, day):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    pid = await _system_ic_id(app_db_url)
    before = await _plan_row(app_db_url, sid)  # the test database may keep a plan from an earlier case
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": pid, "time_exit": {"at": "15:15", "on": day}})
    assert (status, out["what_happened"]) == (UNPROCESSABLE, NOT_VALID), day
    assert await _plan_row(app_db_url, sid) == before  # nothing written


async def test_a_trading_day_up_to_the_last_expiry_saves_and_reads_back(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    pid = await _system_ic_id(app_db_url)
    status, out = await _call("POST", _plan_path(sid),
                              json={"playbook_id": pid, "time_exit": {"at": "15:15", "on": "2026-11-06"}})
    assert status == OK, out
    assert (out["plan"]["time_exit"], out["plan"]["time_exit_on"]) == ({"hour": 15, "minute": 15}, "2026-11-06")
    assert json.loads((await _plan_row(app_db_url, sid)).body)["guards"]["time_exit"] == {"at": "15:15",
                                                                                         "on": "2026-11-06"}
    status, out = await _call("PUT", _plan_path(sid),
                              json={"playbook_id": pid, "time_exit": {"at": "14:00", "on": "2026-11-09"}})
    assert status == OK and out["plan"]["time_exit_on"] == "2026-11-09"  # the expiry day itself is allowed


async def test_a_blank_date_is_expiry_day_and_an_old_plain_hhmm_reads_as_expiry(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    pid = await _system_ic_id(app_db_url)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": pid, "time_exit": {"at": "14:45", "on": ""}})
    assert status == OK and (out["plan"]["time_exit"], out["plan"]["time_exit_on"]) == (
        {"hour": 14, "minute": 45}, None)
    assert json.loads((await _plan_row(app_db_url, sid)).body)["guards"]["time_exit"] == {"at": "14:45", "on": "expiry"}
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": pid, "time_exit": "14:30"})  # the old shape
    assert status == OK and (out["plan"]["time_exit"], out["plan"]["time_exit_on"]) == ({"hour": 14, "minute": 30}, None)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and out["plan"]["time_exit_on"] is None


def test_a_holiday_on_a_weekday_is_refused_and_every_answer_state_is_named():
    today, last = datetime.date(2026, 11, 6), datetime.date(2026, 11, 30)
    holiday = {"at": "15:15", "on": "2026-11-10"}  # Diwali-Balipratipada, a Tuesday
    with pytest.raises(Exception, match="time_exit"):
        route.check_time_exit_day(holiday, today, last)
    route.check_time_exit_day({"at": "15:15", "on": "2026-11-11"}, today, last)  # stated, a trading day: passes
    route.check_time_exit_day({"at": "15:15", "on": "expiry"}, today, last)  # blank = expiry: nothing to judge
    route.check_time_exit_day(None, today, last)  # absent
    for known_today, known_last in ((None, last), (today, None)):  # not found: today or the legs unknown -> refused
        with pytest.raises(Exception, match="time_exit"):
            route.check_time_exit_day({"at": "15:15", "on": "2026-11-11"}, known_today, known_last)
    with pytest.raises(Exception, match="time_exit"):  # empty / ambiguous date text
        route.with_overrides({"guards": {}}, PlanIn(playbook_id=1, time_exit=TimeExitIn(at="15:15", on=" 2026-11-1")))
