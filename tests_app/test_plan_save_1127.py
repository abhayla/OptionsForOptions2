"""Hotfix plan-save-1127 (Lane R, 27 Nov 2026; ADR-330 (1), (5), (7); REQ-161 AC-2/AC-3): a plan save or reset waits for
its price read at most PLAN_SAVE_PRICE_BUDGET_S, is refused past it (nothing stored), and otherwise stores exactly what
it stored before: the market's expiry kind still decides which T-06 row a typed stop edits. Same harness as
test_adjustment_plan.py (fresh migrated DB, scenario ADJ-02)."""
# ruff: noqa: F811 - the sibling file's fixture is imported by name, as the other tests_app files do
from __future__ import annotations

import asyncio
import copy
import json
from decimal import Decimal as D

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
    _t06,
    app_db_url,
)

SLOW_S = 9.0


def _slow(monkeypatch, name: str, seconds: float):
    original = getattr(route, name)

    async def wrapped(*a, **k):
        await asyncio.sleep(seconds)
        return await original(*a, **k)
    monkeypatch.setattr(route, name, wrapped)


class _Monthly:
    """The scenario's market, read as a MONTHLY expiry (the market's expiry kind is what the stored stop follows)."""

    def __init__(self, inner):
        self._inner = inner
        self.expiry_kind = "monthly"

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _monthly_market(monkeypatch):
    original = route._market

    async def wrapped(*a, **k):
        market = await original(*a, **k)
        return None if market is None else _Monthly(market)
    monkeypatch.setattr(route, "_market", wrapped)


async def _own_with_two_kinds(engine, name: str):
    system = await _system_ic(engine)
    body = copy.deepcopy(system.body)
    body["triggers"]["T-06"]["weekly"] = ["50", "50", "40"]
    body["triggers"]["T-06"]["monthly"] = ["30", "30", "20"]
    async with engine.begin() as conn:
        return await playbook_store.create(conn, "owner", "ic", name, body)


async def test_a_percent_stop_on_a_monthly_strategy_is_stored_in_the_monthly_row(app_db_url, monkeypatch):
    """The reviewer's case: the market's expiry kind (monthly) decides which T-06 row the typed stop edits."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    own = await _own_with_two_kinds(app_db_url, "Two kinds percent")
    _monthly_market(monkeypatch)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id, "stop": "50"})
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == {
        "weekly": [D("50"), D("50"), D("40")], "monthly": [D("50"), D("50"), D("20")]}


async def test_a_rupee_stop_on_a_monthly_strategy_leaves_both_rows_and_stores_the_level(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    own = await _own_with_two_kinds(app_db_url, "Two kinds rupees")
    _monthly_market(monkeypatch)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id, "stop_rupees": "100"})
    assert status == OK, out
    row = await _plan_row(app_db_url, sid)
    assert _t06(row.body) == {"weekly": [D("50"), D("50"), D("40")], "monthly": [D("30"), D("30"), D("20")]}
    assert json.loads(row.body)["guards"]["loss_stop_rupees"] == "100"


async def test_a_slow_price_read_on_a_save_is_refused_in_time_and_stores_nothing(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    system = await _system_ic(app_db_url)
    before = await _plan_row(app_db_url, sid)  # ADJ-02 is shared by this file's tests: compare, not "none"
    _slow(monkeypatch, "_market", SLOW_S)
    status, out = await asyncio.wait_for(
        _call("POST", _plan_path(sid), json={"playbook_id": system.id, "stop_rupees": "100"}),
        route.PLAN_SAVE_PRICE_BUDGET_S + 1.0)  # the bound plus 1 s, against a 9 s read
    assert status == UNPROCESSABLE, out
    assert "price" in out["what_happened"].lower()
    assert before == await _plan_row(app_db_url, sid)


async def test_a_slow_price_read_on_a_reset_is_refused_in_time(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    _slow(monkeypatch, "_market", SLOW_S)
    status, out = await asyncio.wait_for(_call("POST", _plan_path(sid) + "/reset"),
                                         route.PLAN_SAVE_PRICE_BUDGET_S + 1.0)
    assert status == UNPROCESSABLE, out
    assert "price" in out["what_happened"].lower()
