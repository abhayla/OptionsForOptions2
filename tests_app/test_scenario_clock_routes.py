"""GC-ICGUIDE g26f / #681: in scenario mode the strategy save and the builder's expiry picker use the scenario's answer
clock; live mode keeps the real clock, and the picker's list-currency check keeps the real database date.

Real case (measured 2026-11-09): OFO_SCENARIO=PATH-60, clock 2026-11-17 09:20 IST, real date 2026-11-09: Save Draft with
captured_at = the scenario time answered 422 USER_INPUT_002. Here the clock is a fixed far-future instant so the test
never depends on the wall clock.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

from ofo_app import scenario_mode
from ofo_app.routes import catalogue
from ofo_app.routes.outcome import get_answer_clock
from test_catalogue_picker_api import _picker_client
from test_strategy_planned_entry import _body, _catalogue, _client, _user

IST = timezone(timedelta(hours=5, minutes=30))
FUTURE = datetime(2099, 11, 17, 9, 20, tzinfo=IST)
FUTURE_STAMP = "2099-11-17T09:20:00+05:30"
CREATED = 201


async def _save(app_engine, scenario_clock) -> tuple[int, str]:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids = await _catalogue(conn)
            async with _client(conn, _user()) as ac:
                if scenario_clock:
                    ac._transport.app.dependency_overrides[get_answer_clock] = lambda: (lambda: FUTURE)
                resp = await ac.post("/strategies", json=_body(ids, captured=FUTURE_STAMP))
            return resp.status_code, resp.text
        finally:
            await trans.rollback()


async def test_scenario_clock_after_the_real_date_saves_a_draft_captured_at_the_scenario_time(app_engine):
    status, text = await _save(app_engine, scenario_clock=True)
    assert status == CREATED, text


async def test_live_mode_still_refuses_a_capture_time_ahead_of_the_real_clock(app_engine):
    status, text = await _save(app_engine, scenario_clock=False)
    assert (status, "USER_INPUT_002" in text) == (422, True), text


async def _expiries(monkeypatch, real_today: date, shown_now: datetime | None, listed: list[date]):
    async def pickable(_db, _u, today):
        assert today == real_today, "list currency must stay on the real database date"
        return listed

    async def instant(_db, _today):
        return datetime(real_today.year, real_today.month, real_today.day, 11, 0, tzinfo=IST)

    monkeypatch.setattr(catalogue.picker, "pickable_expiries", pickable)
    monkeypatch.setattr(catalogue.picker, "judging_instant", instant)
    async with await _picker_client(None, real_today) as ac:
        if shown_now is not None:  # the same shape scenario_mode.overrides installs
            async def reader(_db, _today):
                return shown_now
            ac._transport.app.dependency_overrides[catalogue.get_shown_now] = lambda: reader
        return (await ac.get("/api/catalogue/NIFTY/expiries")).json()


async def test_expiry_days_and_default_follow_the_scenario_clock_while_the_list_stays_on_the_real_date(monkeypatch):
    """Real date 9 Nov, scenario 17 Nov 09:20: 17 Nov reads 0 days (not 8) and is the default; 24 Nov reads 7."""
    listed = [date(2026, 11, 17), date(2026, 11, 24)]
    body = await _expiries(monkeypatch, date(2026, 11, 9), datetime(2026, 11, 17, 9, 20, tzinfo=IST), listed)
    assert body["expiries"] == ["2026-11-17", "2026-11-24"]  # the real-date list check did not empty the builder
    assert [d["days"] for d in body["expiry_days"]] == [0, 7] and body["default_expiry"] == "2026-11-17"


async def test_expiry_days_in_live_mode_count_from_the_database_date(monkeypatch):
    body = await _expiries(monkeypatch, date(2026, 11, 9), None, [date(2026, 11, 17), date(2026, 11, 24)])
    assert [d["days"] for d in body["expiry_days"]] == [8, 15] and body["default_expiry"] == "2026-11-17"


def test_scenario_overrides_install_the_shown_now_seam():
    assert "catalogue.get_shown_now" in inspect.getsource(scenario_mode.overrides)
