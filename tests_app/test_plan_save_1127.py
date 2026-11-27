"""Hotfix plan-save-1127 (Lane R, 27 Nov 2026; ADR-330 (1), (5), (7); REQ-161 AC-2/AC-3): a plan save or reset waits for
its price read at most PLAN_SAVE_PRICE_BUDGET_S, is refused past it (nothing stored), and otherwise stores exactly what
it stored before: the market's expiry kind still decides which T-06 row a typed stop edits. Same harness as
test_adjustment_plan.py (fresh migrated DB, scenario ADJ-02)."""
# ruff: noqa: F811 - the sibling file's fixture is imported by name, as the other tests_app files do
from __future__ import annotations

import asyncio
import copy
import datetime
import json
from decimal import Decimal as D

from ofo_app import playbook_store
from ofo_app import adjustment_readers as readers
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




# --- no live session (market closed, LIVE_MARKET off): the REAL read_market(tracked, None), expiry_kind None ---


class _Scn:
    """A scenario that states the strategy's expiry kind (what ``expiry_kind_of`` reads first in scenario mode)."""

    def __init__(self, kind):
        self.data = {"expiry_kind": kind}


def _no_session(monkeypatch, scenario_kind):
    """The market read of a save with no Kite session: the real reader with no context. ``scenario_kind`` None: no
    stored source of the kind (no scenario, the catalogue holds no future); else the scenario states it."""
    async def real(tracked, market_reader, ctx):
        return await readers.read_market(tracked, None)
    monkeypatch.setattr(route, "_market", real)
    shim = type("S", (), {"current": staticmethod(lambda: None if scenario_kind is None else _Scn(scenario_kind))})
    monkeypatch.setattr(route, "scenario_mode", shim)
    monkeypatch.setattr(readers, "scenario_mode", shim)  # R3: the position's own kind is read by the same rule


ROWS_AFTER_50 = {"weekly": [D("50"), D("50"), D("40")], "monthly": [D("50"), D("50"), D("20")]}
ROWS_AS_IS = {"weekly": [D("50"), D("50"), D("40")], "monthly": [D("30"), D("30"), D("20")]}


async def _accepted(app_db_url, monkeypatch, name):
    """A MONTHLY strategy with an accepted plan on a playbook with two different T-06 rows (market read as monthly)."""
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-02")
    own = await _own_with_two_kinds(app_db_url, name)
    _monthly_market(monkeypatch)
    status, out = await _call("POST", _plan_path(sid), json={"playbook_id": own.id})
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == ROWS_AS_IS
    return sid, own


async def test_a_percent_stop_with_no_session_and_no_stored_kind_is_refused_and_writes_nothing(app_db_url, monkeypatch):
    """Blocker (round 2): real read_market(tracked, None) answers expiry_kind None; the weekly row (50) equals the typed
    50, so the save said 200 and wrote nothing. With the kind unknown it is refused instead (422, nothing stored)."""
    sid, own = await _accepted(app_db_url, monkeypatch, "No kind percent")
    before = await _plan_row(app_db_url, sid)
    _no_session(monkeypatch, None)
    for method in ("POST", "PUT"):
        status, out = await _call(method, _plan_path(sid), json={"playbook_id": own.id, "stop": "50"})
        assert status == UNPROCESSABLE, out
        assert out["what_happened"] == ("The stop could not be saved: whether this trade expires weekly or monthly "
                                        "could not be read.")  # the percent case's own sentence
        assert before == await _plan_row(app_db_url, sid)


async def test_a_percent_stop_with_no_session_uses_the_stored_kind_and_lands_in_monthly(app_db_url, monkeypatch):
    sid, own = await _accepted(app_db_url, monkeypatch, "Stored kind percent")
    _no_session(monkeypatch, "monthly")
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop": "50"})
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == ROWS_AFTER_50


async def test_a_rupee_stop_with_no_session_is_stored(app_db_url, monkeypatch):
    sid, own = await _accepted(app_db_url, monkeypatch, "No kind rupees")
    _no_session(monkeypatch, None)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop_rupees": "100"})
    assert status == OK, out
    row = await _plan_row(app_db_url, sid)
    assert json.loads(row.body)["guards"]["loss_stop_rupees"] == "100"
    assert _t06(row.body) == ROWS_AS_IS


async def test_a_target_only_save_with_no_session_is_stored(app_db_url, monkeypatch):
    sid, own = await _accepted(app_db_url, monkeypatch, "No kind target")
    _no_session(monkeypatch, None)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "target": "60"})
    assert status == OK, out
    row = await _plan_row(app_db_url, sid)
    assert json.loads(row.body)["guards"]["profit_target_pct_of_max_profit"] == "60"
    assert _t06(row.body) == ROWS_AS_IS


async def test_a_reset_with_no_session_works(app_db_url, monkeypatch):
    sid, _own = await _accepted(app_db_url, monkeypatch, "No kind reset")
    _no_session(monkeypatch, None)
    status, out = await _call("POST", _plan_path(sid) + "/reset")
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == ROWS_AS_IS


class _Entry:
    def __init__(self, expiry, future):
        self.currently_listed = True
        self.contract = type("C", (), {"name": "NIFTY", "expiry": expiry, "is_future": lambda s: future,
                                       "is_option": lambda s: not future})()


class _Cat:
    def __init__(self, entries):
        self._entries = entries

    def all_entries(self):
        return self._entries


async def test_the_stored_kind_is_the_one_rule_over_the_stored_catalogue(monkeypatch):
    """Monthly = the leg expiry is also a future expiry; a catalogue with no future cannot judge (None, no guess)."""
    from ofo_app import adjustment_readers as readers  # noqa: PLC0415
    monkeypatch.setattr(route, "scenario_mode", type("S", (), {"current": staticmethod(lambda: None)}))
    leg_day, other = datetime.date(2026, 12, 29), datetime.date(2026, 12, 3)
    tracked = type("T", (), {"position": type("P", (), {
        "underlying": "NIFTY", "legs": (type("L", (), {"expiry": leg_day})(),)})()})()

    def stored(entries):
        async def load(db):
            return _Cat(entries)
        monkeypatch.setattr(route, "load_catalogue", load)
    stored([_Entry(leg_day, True), _Entry(leg_day, False), _Entry(other, False)])
    assert await route._stored_kind(None, tracked) == "monthly"
    later = datetime.date(2027, 1, 26)
    stored([_Entry(other, True), _Entry(later, True), _Entry(leg_day, False)])  # a future on both sides: weekly
    assert await route._stored_kind(None, tracked) == "weekly"
    stored([_Entry(other, True), _Entry(leg_day, False)])  # far month: its own future is not listed -> cannot judge
    assert await route._stored_kind(None, tracked) is None
    stored([_Entry(leg_day, False), _Entry(other, False)])
    assert await route._stored_kind(None, tracked) is None
