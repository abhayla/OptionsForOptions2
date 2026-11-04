"""Goal contract "Your adjustment settings" step 1 CORE proof (ADR-245): the carry gap in force for a strategy is its
plan's value, else the user's, else the admin default, and the carry check's figures name where it came from.

Spec basis: ADR-245 "The value in force is the strategy's, else the user's, else the admin default, and every flag,
alert line and Compare cell names the value it used." Contract step 1 proof: iron condor plan; carry gap admin 2, user
3, strategy 1.5 -> the figures use 1.5, "strategy"; strategy value removed -> 3, "user"; user value
removed -> 2, "default". Real PostgreSQL (db_run_fresh); every test rolls back.

The path under test is the one the worker and the screen both take: ``playbook_store.plan_for`` (via
``adjustment_check.resolve``) and ``user_preferences_store.values_for`` -> ``adjustment_check.carry_gap_in_force``
-> ``ofo.adjustment.carry.carry_figures`` on a real engine model (the GC-IC1 golden legs).
"""
from __future__ import annotations

import copy
import dataclasses
import datetime
import pathlib
import sys
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "scenario"))
sys.path.insert(0, str(ROOT / "tests_app"))

from ofo.adjustment import carry  # noqa: E402
from ofo.engine.inputs import SpotReading, StrategyInput  # noqa: E402
from ofo.rules.inputs import DataHealth  # noqa: E402
from ofo.settings import layers  # noqa: E402
from ofo.timeutil import IST  # noqa: E402
from ofo_app import adjustment_check as check  # noqa: E402
from ofo_app import playbook_store as pb  # noqa: E402
from ofo_app import settings_store  # noqa: E402
from ofo_app import user_preferences_store as prefs_store  # noqa: E402
from scenario_fixtures import GOLDEN_LEGS, RATE, gated, nifty_leg  # noqa: E402
from test_strategy_store import _user, _with_draft  # noqa: E402

KEY = "other.carry_gap_percent"
FRI_1500 = datetime.datetime(2026, 10, 23, 15, 0, tzinfo=IST)
SPOT = D("23047")
BOOKED = D("-1250.50")
TABLE = {2026: frozenset({datetime.date(2026, 10, 20)})}


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _model():
    legs = [nifty_leg(a, i, k, e, ltp, iv) for a, i, k, e, ltp, iv in GOLDEN_LEGS]
    return gated(StrategyInput(underlying="NIFTY", valuation_time=FRI_1500, rate=RATE, legs=tuple(legs),
                               spot=SpotReading(level=SPOT, at=FRI_1500, health=DataHealth.AVAILABLE)))


async def _in_force(db, user: str, strategy_id: int, admin: D):
    """What the worker and the screen do: the admin value in the market read, then the per-strategy resolution."""
    resolved = await check.resolve(db, user, strategy_id, "ic")
    gap = check.carry_gap_of(admin, await prefs_store.values_for(db, user), resolved.strategy_layer)
    got = SimpleNamespace(carry_gap_pct=gap.value, carry_gap_source=gap.source, carry_gap_reason=gap.reason)
    return got, carry.carry_figures(_model(), BOOKED, D("98765.40"), FRI_1500, TABLE, gap_pct=got.carry_gap_pct,
                                    gap_source=got.carry_gap_source, gap_setting_reason=got.carry_gap_reason)


async def test_core_strategy_then_user_then_default(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    await settings_store.add_setting(db, KEY, "2", set_by="test-admin", correlation_id="cfg-step1")
    admin = (await settings_store.settings_in_force(db, await settings_store.database_now(db)))[KEY]
    assert admin == D("2")
    await prefs_store.set_preference(db, user, KEY, "3")
    system = await pb.active_for(db, user, "ic")  # the iron condor system playbook
    body = copy.deepcopy(system.body) | {"settings": {KEY: "1.5"}}
    await pb.accept_plan(db, user, stored.id, system.id, body)

    market, figs = await _in_force(db, user, stored.id, admin)
    assert (market.carry_gap_pct, market.carry_gap_source) == (D("1.5"), "strategy")
    assert (figs.gap_pct, figs.gap_source, figs.gap_reason) == (D("1.5"), "strategy", None)
    assert carry.gap_levels(SPOT, figs.gap_pct) == (D("23392.70"), D("22701.30"))
    expected = carry.carry_figures(_model(), BOOKED, D("98765.40"), FRI_1500, TABLE, gap_pct=D("1.5"))
    assert (figs.up, figs.down) == (expected.up, expected.down) and figs.up is not None

    # remove the strategy value (the plan sheet accepted again without it) -> the user's 3
    await pb.accept_plan(db, user, stored.id, system.id, copy.deepcopy(system.body))
    market, figs = await _in_force(db, user, stored.id, admin)
    assert (figs.gap_pct, figs.gap_source) == (D("3"), "user")
    assert carry.gap_levels(SPOT, figs.gap_pct) == (D("23738.41"), D("22355.59"))

    # remove the user value (reset: follow the default) -> the admin's 2
    await prefs_store.reset_preference(db, user, KEY)
    market, figs = await _in_force(db, user, stored.id, admin)
    assert (figs.gap_pct, figs.gap_source) == (D("2"), "default")
    assert carry.gap_levels(SPOT, figs.gap_pct) == (D("23507.94"), D("22586.06"))


async def test_a_plan_settings_value_the_registry_refuses_is_refused_at_write(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    system = await pb.active_for(db, user, "ic")
    for bad in ({KEY: "999"}, {KEY: ""}, {KEY: "abc"}, {"speeds.open_strategy_seconds": "5"}, ["1.5"]):
        with pytest.raises(pb.PlaybookStoreError):
            await pb.accept_plan(db, user, stored.id, system.id, copy.deepcopy(system.body) | {"settings": bad})


async def test_an_unreadable_stored_plan_value_fails_closed_never_the_default(db):
    """A plan row written around the store's check (a later narrowed range, a raw edit) holds a value the registry
    refuses: no figures, the named reason, never the user's or the admin's value."""
    user = _user()
    _, stored = await _with_draft(db, user)
    await prefs_store.set_preference(db, user, KEY, "3")
    system = await pb.active_for(db, user, "ic")
    await pb.accept_plan(db, user, stored.id, system.id, copy.deepcopy(system.body))
    from sqlalchemy import text  # noqa: PLC0415
    await db.execute(text("UPDATE public.strategy_adjustment_plans SET body = jsonb_set(body, '{settings}', "
                          "'{\"other.carry_gap_percent\": \"999\"}') WHERE strategy_id = :s"), {"s": stored.id})
    market, figs = await _in_force(db, user, stored.id, D("2"))
    assert market.carry_gap_pct is None and market.carry_gap_reason == layers.STRATEGY_UNREADABLE
    assert (figs.up, figs.down, figs.gap_reason, figs.gap_setting_reason) == (
        None, None, carry.CARRY_GAP_UNKNOWN, layers.STRATEGY_UNREADABLE)
    assert dataclasses.is_dataclass(figs)
