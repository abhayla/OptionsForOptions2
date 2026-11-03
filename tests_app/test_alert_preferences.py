# ruff: noqa: PLR2004 - exact expected values from the REQ-170 table are the assertion (tests rule: assert exact values)
"""REQ-170 AC-6 / AC-7: the user-changeable alert-discipline values on the Preferences closed list (GC-ALERT1).

Spec basis: REQ-170 AC-6 "the re-arm margin and the daily cap are admin settings (the user may lower the cap, never
raise it); confirmation candle, cool-down and quiet time have admin defaults the user may change on the Preferences
tab"; AC-7 "an admin or user change applies to the next check"; ADR-222 (7) follow the admin default until changed.
Every test runs in a rolled-back transaction (the preference and settings tables are insert-only).
"""
from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

import pytest
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from ofo.adjustment import alert_gate, alert_presets  # noqa: E402
from ofo.settings import SettingRefused  # noqa: E402
from ofo_app import settings_store  # noqa: E402
from ofo_app import user_preferences_store as store  # noqa: E402
from test_strategy_store import _client  # noqa: E402
from test_user_preferences import PREFS, _untyped, _users  # noqa: E402

D = Decimal
pytestmark = pytest.mark.real_preferences
CAP = "alerts.intraday.daily_cap"
LIMIT_REASON = ("Intraday (0-1 day to expiry): daily limit per strategy can be at most 6, the limit your "
                "administrator set. Enter 6 or less.")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _preset(db, user: str, style: str) -> alert_gate.Preset:
    now = await settings_store.database_now(db)
    return alert_presets.preset_for(style, await store.values_for(db, user, now),
                                    await settings_store.settings_in_force(db, now))


async def test_core_no_user_values_gives_the_three_gate_presets(db):
    for style, expected in (("intraday", alert_gate.INTRADAY), ("weekly", alert_gate.WEEKLY),
                            ("monthly", alert_gate.MONTHLY)):
        assert await _preset(db, "user-alert", style) == expected


async def test_the_closed_list_holds_the_twelve_user_values_and_no_admin_only_key():
    keys = store.preference_keys()
    assert set(alert_presets.USER_KEYS) <= set(keys)
    assert not [k for k in keys if "rearm" in k or k.startswith("speeds.")]


async def test_a_cap_above_the_admin_cap_is_refused_with_the_limit_and_writes_nothing(db):
    app, _stored, _body = await _untyped(db)
    async with _client(app) as c:
        r = await c.post(f"{PREFS}/{CAP}", json={"value": "8"})
    assert (r.status_code, r.json()["reason"]) == (422, LIMIT_REASON)
    assert (await store.history(db, next(iter(_users(app)))))[CAP] == []


async def test_a_lower_cap_is_accepted_and_used_by_the_preset(db):
    app, _stored, _body = await _untyped(db)
    async with _client(app) as c:
        r = await c.post(f"{PREFS}/{CAP}", json={"value": "3"})
    assert r.status_code == 200
    row = next(p for p in r.json()["preferences"] if p["key"] == CAP)
    assert (row["value"], row["source"], row["admin_default"]) == ("3", "yours", "6")
    assert (await _preset(db, next(iter(_users(app))), "intraday")).daily_cap == 3


async def test_an_admin_lowering_the_ceiling_below_a_saved_cap_fences_it(db):
    await store.set_preference(db, "user-alert", CAP, "5")
    await db.execute(text("INSERT INTO public.app_settings (key, value, effective_from, set_by) "
                          "VALUES (:k, 2, clock_timestamp(), 'raw-test')"), {"k": CAP})
    assert (await _preset(db, "user-alert", "intraday")).daily_cap == 2
    with pytest.raises(SettingRefused) as info:
        await store.set_preference(db, "user-alert", CAP, "3")
    assert info.value.code == store.CAP_ABOVE_ADMIN


@pytest.mark.parametrize("raw", ["900", "1545", "2000"])
async def test_a_quiet_time_outside_the_market_day_is_refused(db, raw):
    with pytest.raises(SettingRefused) as info:
        await store.set_preference(db, "user-alert", "alerts.weekly.quiet_until", raw)
    assert info.value.code == "setting_out_of_range"


async def test_user_candle_cooldown_quiet_are_used_and_reset_follows_the_default(db):
    await store.set_preference(db, "user-alert", "alerts.monthly.cooldown_minutes", "60")
    await store.set_preference(db, "user-alert", "alerts.monthly.quiet_until", "1000")
    await store.set_preference(db, "user-alert", "alerts.monthly.confirm_candle_minutes", "30")
    p = await _preset(db, "user-alert", "monthly")
    assert (p.cooldown.total_seconds(), p.quiet_until.isoformat(), p.candle.total_seconds()) == (3600, "10:00:00", 1800)
    assert p.rearm_fraction == D("0.25")  # admin only, unchanged
    await store.reset_preference(db, "user-alert", "alerts.monthly.cooldown_minutes")
    assert (await _preset(db, "user-alert", "monthly")).cooldown.total_seconds() == 7200


async def test_the_rearm_margin_is_not_a_user_preference(db):
    with pytest.raises(SettingRefused) as info:
        await store.set_preference(db, "user-alert", "alerts.intraday.rearm_percent", "5")
    assert info.value.code == "setting_unknown"
