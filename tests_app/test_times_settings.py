"""REQ-167 AC-4, AC-5: the contract-list publish time and the Kite session expiry are settings read at each run.

Spec basis (quoted): REQ-167 AC-5 "Exchange and broker facts (... Kite session expiry, ... contract-list publish
time), each with its source in the note"; AC-4 "Each wired calculation reads the value in force when it runs (no
restart)". Defaults never change: 08:30 and 06:00. Every case rolls back, so no setting row is left behind.
"""

from __future__ import annotations

import datetime
import os

import pytest
from ofo import settings
from ofo.settings import calc
from ofo.timeutil import IST
from ofo_app import broker_token_store as store
from ofo_app import catalogue_picker as picker
from ofo_app import settings_store
from ofo_app.broker_crypto import TokenCipher
from sqlalchemy import text


def _ist(day: int, hour: int, minute: int) -> datetime.datetime:
    return datetime.datetime(2026, 10, day, hour, minute, tzinfo=IST)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def test_the_defaults_are_exactly_0830_and_0600_with_a_source():
    values = settings.defaults()
    assert calc.contract_list_publish_time(values) == datetime.time(8, 30)
    assert calc.kite_session_expiry(values) == datetime.time(6, 0)
    for key in (calc.CONTRACT_LIST_PUBLISH_TIME, calc.KITE_SESSION_EXPIRY):
        entry = settings.setting(key)
        assert entry.group == "Exchange and broker facts" and entry.unit == "time" and "Kite" in entry.source


async def test_core_a_changed_publish_time_changes_what_the_picker_calls_published(db):
    """Core proof: with 0900 in force, at 08:45 today's list is not yet published (the session is yesterday's, so a
    load from yesterday 09:30 is still current); at the default 08:30 today's list is out and that load is stale."""
    load = _ist(21, 9, 30)  # the day before, 09:30
    judged = _ist(22, 8, 45)
    default = await picker.publish_time(db)
    assert default == datetime.time(8, 30)
    assert picker.session_start(judged, default) == _ist(22, 8, 30)
    assert picker.loaded_before(load, judged, default)
    await settings_store.add_setting(db, calc.CONTRACT_LIST_PUBLISH_TIME, "900", set_by="admin-test",
                                     correlation_id="t")
    moved = await picker.publish_time(db)  # read again, no restart
    assert moved == datetime.time(9, 0)
    assert picker.session_start(judged, moved) == _ist(21, 9, 0)
    assert not picker.loaded_before(load, judged, moved)


async def test_a_malformed_stored_publish_time_fails_closed(db):
    await db.execute(text("INSERT INTO public.app_settings (key, value, effective_from, set_by) "
                          "VALUES (:k, 875, clock_timestamp(), 'raw-test')"), {"k": calc.CONTRACT_LIST_PUBLISH_TIME})
    with pytest.raises(settings_store.SettingsError, match=r"facts.contract_list_publish_time"):
        await picker.publish_time(db)


def _hhmm(at: datetime.datetime) -> str:
    local = at.astimezone(IST)
    return str(local.hour * 100 + local.minute)


@pytest.mark.parametrize(("offset_minutes", "past"), [(-10, True), (10, False)])
async def test_a_changed_kite_expiry_moves_when_a_session_counts_as_expired(admin_engine, offset_minutes, past):
    """Session logged in 30 minutes ago; the setting says the login lapses 10 minutes ago (past) or in 10 minutes
    (not past). The default 06:00 would not decide either, so the setting is what moved the answer."""
    user = f"u-{os.urandom(4).hex()}"
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            await store.store_session(conn, user, "tok", TokenCipher(os.urandom(32)))
            now = await settings_store.database_now(conn)
            await conn.execute(text("ALTER TABLE public.broker_sessions DISABLE TRIGGER broker_sessions_guard"))
            await conn.execute(text("UPDATE public.broker_sessions SET started_at = clock_timestamp() - "
                                    "interval '30 minutes' WHERE user_ref = :u"), {"u": user})
            await conn.execute(text("ALTER TABLE public.broker_sessions ENABLE TRIGGER broker_sessions_guard"))
            await settings_store.add_setting(
                conn, calc.KITE_SESSION_EXPIRY, _hhmm(now + datetime.timedelta(minutes=offset_minutes)),
                set_by="admin-test", correlation_id="t")
            _started, is_past = await store.active_session_status(conn, user)
            assert is_past is past
        finally:
            await outer.rollback()
