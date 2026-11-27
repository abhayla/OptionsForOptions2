"""Hotfix plan-save-1127 (Lane R, 27 Nov 2026; ADR-330 (1), (5), (7); REQ-161 AC-2/AC-3): the plan save never waits on
a slow price read it does not need, never hangs on one it does, and answers from the stored plan. Same harness as
test_adjustment_plan.py (fresh migrated DB, scenario ADJ-02)."""
# ruff: noqa: F811 - the sibling file's fixture is imported by name, as the other tests_app files do
from __future__ import annotations

import asyncio
import time

from ofo_app import playbook_store
from ofo_app.routes import adjustment_plan as route
from test_adjustment_plan import (  # noqa: F401 - fixtures and helpers of the sibling file
    OK,
    UNPROCESSABLE,
    _call,
    _plan_path,
    _plan_row,
    _seeded,
    _system_ic,
    app_db_url,
)

SLOW_S = 9.0
NOT_WAITING_S = 4.0  # app start and the write take about 1 s; the stubbed read takes SLOW_S


def _slow(monkeypatch, name: str, seconds: float):
    original = getattr(route, name)

    async def wrapped(*a, **k):
        await asyncio.sleep(seconds)
        return await original(*a, **k)
    monkeypatch.setattr(route, name, wrapped)


def _timed(monkeypatch, owner, names: list[str], log: dict):
    for name in names:
        original = getattr(owner, name)

        async def wrapped(*a, _o=original, _n=name, **k):
            t0 = time.perf_counter()
            try:
                return await _o(*a, **k)
            finally:
                log[_n] = log.get(_n, 0) + time.perf_counter() - t0
        monkeypatch.setattr(owner, name, wrapped)


async def test_step_timings_with_an_instant_market(app_db_url, monkeypatch, capsys):
    """Diagnostic for the RCA: the time of each step of the save with the price read instant."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    log: dict = {}
    _timed(monkeypatch, route, ["_own_strategy", "_market", "_type_of", "_picked", "_sheet"], log)
    _timed(monkeypatch, playbook_store, ["accept_plan"], log)
    t0 = time.perf_counter()
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": system.id, "stop_rupees": "100"})
    log["TOTAL"] = time.perf_counter() - t0
    assert status == OK, out
    with capsys.disabled():
        print("STEP TIMINGS (s):", {k: round(v, 3) for k, v in log.items()})


async def test_a_stop_in_rupees_saves_without_waiting_for_a_slow_price_read(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    _slow(monkeypatch, "_market", SLOW_S)
    # the stub holds a read for SLOW_S: an answer inside the NOT_WAITING_S limit proves the save did not wait for it
    status, out = await asyncio.wait_for(
        _call("POST", _plan_path(sid), json={"playbook_id": system.id, "stop_rupees": "100"}), NOT_WAITING_S)
    assert status == OK, out
    assert '"loss_stop_rupees": "100"' in (await _plan_row(app_db_url, sid)).body.replace('":"', '": "')
    assert out["plan"]["stop_rupees"] == "100.00"


async def test_a_save_that_needs_the_price_is_refused_in_time_and_stores_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    before = await _plan_row(app_db_url, sid)  # ADJ-02 is shared by this file's tests: compare, not "none"
    _slow(monkeypatch, "_market", SLOW_S)
    status, out = await asyncio.wait_for(
        _call("POST", _plan_path(sid), json={"playbook_id": system.id, "target": "50", "target_rupees": "1000"}),
        route.PLAN_SAVE_PRICE_BUDGET_S + 1.0)  # the bound plus 1 s, against a 9 s read
    assert status == UNPROCESSABLE, out
    assert "price" in out["what_happened"].lower()
    assert tuple(await _plan_row(app_db_url, sid)) == tuple(before)


async def test_a_slow_read_after_the_write_does_not_hold_the_answer(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    _slow(monkeypatch, "_sheet", SLOW_S)
    # the stub holds a read for SLOW_S: an answer inside the NOT_WAITING_S limit proves the save did not wait for it
    status, out = await asyncio.wait_for(
        _call("POST", _plan_path(sid), json={"playbook_id": system.id, "stop_rupees": "100"}), NOT_WAITING_S)
    assert status == OK, out
    assert out["plan"]["stop_rupees"] == "100.00"
    assert (await _plan_row(app_db_url, sid)) is not None
