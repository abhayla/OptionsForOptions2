"""REQ-167 AC-1..AC-3: the app settings store (migration 0032, ``ofo_app.settings_store``).

Spec basis: REQ-167 AC-1 "the value in force at a time is the newest row not after that time, else the default";
AC-2 "a value outside the allowed range or of the wrong unit is refused with the reason (e.g. 6.5 typed for a rate
whose unit is a fraction: 'Enter 0.065 for 6.5%')", "Reset to default is a new row, never a delete"; AC-3 every change
is written to the audit log; ADR-222 (1); ADR-023 (the database clock); ADR-048 (the limited application role).

Every test runs inside a transaction that is rolled back: app_settings rows can never be deleted, so a committed test
row would stay in the shared test database for ever.
"""

from __future__ import annotations

import datetime
import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from ofo.settings import SettingRefused
from ofo_app import settings_store
from ofo_app.settings_store import SettingsError, add_setting, history, settings_in_force
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

D = Decimal
KEY = "pricing.risk_free_rate"
DEFAULT = D("0.065")
VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
_RAW = text("INSERT INTO public.app_settings (key, value, effective_from, set_by) VALUES (:k, :v, :at, 'raw-test')")


class _Tx:
    """A connection in a transaction that is always rolled back."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def __aenter__(self):
        self.conn = await self.engine.connect()
        self.trans = await self.conn.begin()
        return self.conn

    async def __aexit__(self, *exc):
        await self.trans.rollback()
        await self.conn.close()


async def _now(conn) -> datetime.datetime:
    return await settings_store.database_now(conn)


async def _add(conn, value: str, **kw):
    kw.setdefault("set_by", "admin-test")
    kw.setdefault("correlation_id", "settings-test")
    return await add_setting(conn, KEY, value, **kw)


async def test_no_row_is_the_registry_default(app_engine):
    async with _Tx(app_engine) as conn:
        assert (await conn.execute(text("SELECT count(*) FROM public.app_settings"))).scalar_one() == 0
        assert (await settings_in_force(conn))[KEY] == DEFAULT


async def test_a_row_in_force_is_its_value_and_a_reset_is_a_new_row(app_engine):
    async with _Tx(app_engine) as conn:
        stored = await _add(conn, "0.07")
        assert stored.value == D("0.07") and isinstance(stored.value, Decimal)
        assert (await settings_in_force(conn))[KEY] == D("0.07")
        await _add(conn, "0.065", note="reset to default")  # AC-2: reset is a new row
        assert (await settings_in_force(conn))[KEY] == DEFAULT
        assert [r.value for r in (await history(conn))[KEY]] == [DEFAULT, D("0.07")]


async def test_a_future_dated_row_is_not_in_force_until_its_time(app_engine):
    async with _Tx(app_engine) as conn:
        now = await _now(conn)
        await _add(conn, "0.07", effective_from=now + datetime.timedelta(days=1))
        assert (await settings_in_force(conn))[KEY] == DEFAULT
        assert (await settings_in_force(conn, now + datetime.timedelta(days=2)))[KEY] == D("0.07")


async def test_a_key_the_registry_does_not_hold_is_ignored(app_engine):
    async with _Tx(app_engine) as conn:
        now = await _now(conn)
        await conn.execute(_RAW, {"k": "retired.old_rate", "v": D("5"), "at": now})
        values = await settings_in_force(conn)
        assert "retired.old_rate" not in values and values[KEY] == DEFAULT
        assert "retired.old_rate" not in await history(conn)


@pytest.mark.parametrize(("raw", "code", "words"), [
    ("51", "setting_out_of_range", "between 0 and 0.5"),
    ("-0.01", "setting_out_of_range", "between 0 and 0.5"),
    ("6.5", "setting_fraction_unit", "enter 0.065 for 6.5%"),
    ("abc", "setting_not_a_number", "must be a number"),
])
async def test_a_refused_value_writes_nothing(app_engine, raw, code, words):
    async with _Tx(app_engine) as conn:
        with pytest.raises(SettingRefused) as info:
            await _add(conn, raw)
        assert info.value.code == code and words in info.value.reason
        assert (await conn.execute(text("SELECT count(*) FROM public.app_settings"))).scalar_one() == 0


async def test_an_unknown_key_is_refused(app_engine):
    async with _Tx(app_engine) as conn:
        with pytest.raises(SettingRefused) as info:
            await add_setting(conn, "pricing.no_such", "1", set_by="admin-test", correlation_id="c")
        assert info.value.code == "setting_unknown"


async def test_a_back_dated_write_is_refused(app_engine):
    async with _Tx(app_engine) as conn:
        now = await _now(conn)
        with pytest.raises(SettingRefused) as info:
            await _add(conn, "0.07", effective_from=now - datetime.timedelta(minutes=1))
        assert info.value.code == "setting_back_dated"
        assert (await conn.execute(text("SELECT count(*) FROM public.app_settings"))).scalar_one() == 0


async def test_a_naive_time_is_refused(app_engine):
    async with _Tx(app_engine) as conn:
        with pytest.raises(SettingRefused) as info:
            await _add(conn, "0.07", effective_from=datetime.datetime(2030, 1, 1))  # noqa: DTZ001 - the case
        assert info.value.code == "setting_time_invalid"


async def test_two_values_at_one_instant_are_refused_and_the_transaction_stays_usable(app_engine):
    async with _Tx(app_engine) as conn:
        at = await _now(conn) + datetime.timedelta(hours=1)
        await _add(conn, "0.07", effective_from=at)
        with pytest.raises(SettingRefused) as info:
            await _add(conn, "0.06", effective_from=at)
        assert info.value.code == "setting_same_time"
        assert (await settings_in_force(conn, at))[KEY] == D("0.07")  # the caller's transaction still answers


async def test_a_stored_value_the_registry_now_refuses_fails_closed(app_engine):
    """A row written before the registry range was narrowed: the read raises, never falls back to the default."""
    async with _Tx(app_engine) as conn:
        await conn.execute(_RAW, {"k": KEY, "v": D("0.9"), "at": await _now(conn)})
        with pytest.raises(SettingsError, match="refused by the registry"):
            await settings_in_force(conn)


async def test_history_is_newest_first(app_engine):
    async with _Tx(app_engine) as conn:
        now = await _now(conn)
        await _add(conn, "0.07")
        await _add(conn, "0.06", effective_from=now + datetime.timedelta(hours=2))
        await _add(conn, "0.05", effective_from=now + datetime.timedelta(hours=1))
        rows = (await history(conn))[KEY]
        assert [r.value for r in rows] == [D("0.06"), D("0.05"), D("0.07")]
        assert all(r.set_by == "admin-test" and r.created_at is not None for r in rows)


async def test_every_change_writes_an_audit_event(app_engine):
    async with _Tx(app_engine) as conn:
        await _add(conn, "0.07", note="RBI repo change", correlation_id="settings-audit-1")
        rows = (await conn.execute(text(
            "SELECT event_type, actor, payload->>'action' AS action, payload->>'reason' AS reason "
            "FROM public.audit_events WHERE correlation_id = 'settings-audit-1'"))).all()
        assert len(rows) == 1
        r = rows[0]
        assert (r.event_type, r.actor, r.action) == ("admin_change_recorded", "admin-test", "app_setting_set")
        assert r.reason.startswith(f"{KEY} (Risk-free interest rate) = 0.07 from ") and "RBI repo change" in r.reason


async def test_a_refused_write_writes_no_audit_event(app_engine):
    async with _Tx(app_engine) as conn:
        with pytest.raises(SettingRefused):
            await _add(conn, "0.9", correlation_id="settings-audit-refused")
        n = (await conn.execute(text(
            "SELECT count(*) FROM public.audit_events WHERE correlation_id = 'settings-audit-refused'"))).scalar_one()
        assert n == 0


async def test_the_application_role_cannot_update_or_delete(app_engine):
    for sql in ("UPDATE public.app_settings SET value = 0 WHERE key = 'pricing.risk_free_rate'",
                "DELETE FROM public.app_settings"):
        async with _Tx(app_engine) as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(sql))


async def test_the_guard_refuses_update_and_delete_even_for_the_owner(admin_engine):
    """Killing test for the trigger: with a row present, the owner's UPDATE and DELETE raise OF032."""
    for sql in ("UPDATE public.app_settings SET value = 0 WHERE key = 'pricing.risk_free_rate'",
                "DELETE FROM public.app_settings WHERE key = 'pricing.risk_free_rate'"):
        async with _Tx(admin_engine) as conn:
            await conn.execute(_RAW, {"k": KEY, "v": D("0.07"), "at": await _now(conn)})
            with pytest.raises(DBAPIError, match="insert-only") as info:
                await conn.execute(text(sql))
            assert getattr(info.value.orig, "sqlstate", None) == "OF032"


def _migration():
    spec = importlib.util.spec_from_file_location("ofo_0032_for_test", VERSIONS / "0032_app_settings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def test_the_downgrade_refuses_while_rows_exist(admin_engine):
    recorded: list[str] = []
    m = _migration()
    m.op = SimpleNamespace(execute=lambda sql, *a, **k: recorded.append(str(sql)))
    m._BASE._app_role = lambda: "ofo_app"
    m.downgrade()
    async with _Tx(admin_engine) as conn:
        await conn.execute(_RAW, {"k": KEY, "v": D("0.07"), "at": await _now(conn)})
        with pytest.raises(DBAPIError, match="refusing to downgrade 0032_app_settings") as info:
            async with conn.begin_nested():
                await conn.execute(text(recorded[0]))
        assert getattr(info.value.orig, "sqlstate", None) == "OF032"


async def test_a_failed_audit_append_leaves_no_setting_row(app_engine):
    """Finding 3: under REPEATABLE READ the audit append refuses (AuditStoreError); the setting row must not survive
    it (one savepoint holds both)."""
    from ofo_app.audit_store import AuditStoreError  # noqa: PLC0415

    conn = await app_engine.connect()
    try:
        await conn.execution_options(isolation_level="REPEATABLE READ")
        trans = await conn.begin()
        try:
            with pytest.raises(AuditStoreError, match="READ COMMITTED"):
                await _add(conn, "0.07", correlation_id="settings-audit-rr")
            n = (await conn.execute(text("SELECT count(*) FROM public.app_settings"))).scalar_one()
            assert n == 0, "the setting row survived a failed audit append"
        finally:
            await trans.rollback()
    finally:
        await conn.close()


async def test_a_raw_back_dated_insert_is_refused_for_the_application_role(app_engine):
    """Finding 2: the guard refuses an effective_from in the past (beyond the 5 s grace) even without the store."""
    async with _Tx(app_engine) as conn:
        back = await _now(conn) - datetime.timedelta(minutes=1)
        with pytest.raises(DBAPIError, match="back-dated") as info:
            await conn.execute(_RAW, {"k": KEY, "v": D("0.07"), "at": back})
        assert getattr(info.value.orig, "sqlstate", None) == "OF032"


async def test_the_guard_allows_now_and_a_few_seconds_of_clock_gap_but_not_ten(app_engine):
    """Finding 2, both sides of the boundary: the store reads 'now' one statement before it inserts, so a time 1 s old
    passes; 10 s old is back-dated."""
    async with _Tx(app_engine) as conn:
        now = await _now(conn)
        await conn.execute(_RAW, {"k": KEY, "v": D("0.07"), "at": now})
        await conn.execute(_RAW, {"k": KEY, "v": D("0.071"), "at": now - datetime.timedelta(seconds=1)})
        with pytest.raises(DBAPIError, match="back-dated"):
            async with conn.begin_nested():
                await conn.execute(_RAW, {"k": KEY, "v": D("0.072"), "at": now - datetime.timedelta(seconds=10)})


async def test_the_owner_cannot_truncate_the_settings_table(admin_engine):
    """Finding 4: a statement-level BEFORE TRUNCATE trigger raises OF032, even for the table owner."""
    async with _Tx(admin_engine) as conn:
        await conn.execute(_RAW, {"k": KEY, "v": D("0.07"), "at": await _now(conn)})
        with pytest.raises(DBAPIError, match="insert-only") as info:
            await conn.execute(text("TRUNCATE public.app_settings"))
        assert getattr(info.value.orig, "sqlstate", None) == "OF032"
