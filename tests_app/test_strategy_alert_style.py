"""REQ-170 Q-AD-2: a user's alert-style pin per strategy (migration 0035, ``ofo_app.strategy_alert_style_store``).

Spec basis: REQ-170 Q-AD-2 "the style is taken from the strategy and changes by itself as expiry nears ... the user
may pin a style per strategy"; REQ-168 AC-3 "every read and write is keyed by the user".

Real input: a saved strategy from the recorded instrument fixture (``test_strategy_store._with_draft``). Every store
test runs in a rolled-back transaction: the pin table is insert-only, a committed row would stay for ever.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from ofo.adjustment import alert_presets
from ofo_app import strategy_alert_style_store as store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = "public.strategy_alert_style"


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0035_strategy_alert_style.py"
    found = importlib.util.spec_from_file_location("ofo_migration_0035_test", path)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(db) -> tuple[str, int]:
    user = _user()
    _, stored = await _with_draft(db, user)
    return user, stored.id


# ---- the core proof ---------------------------------------------------------------------------------------------

async def test_core_proof_pin_monthly_then_back_to_automatic(db):
    user, sid = await _strategy(db)
    assert await store.pin_of(db, user, sid) == store.StoredPin(None, None)  # absent: automatic
    pinned = await store.set_pin(db, user, sid, "monthly")
    assert pinned.style == "monthly"
    got = await store.pin_of(db, user, sid)
    assert (got.style, got.effective_from) == ("monthly", pinned.effective_from)
    auto = await store.set_pin(db, user, sid, None)
    got = await store.pin_of(db, user, sid)
    assert (got.style, got.effective_from) == (None, auto.effective_from)
    rows = (await db.execute(text(f"SELECT style FROM {TABLE} WHERE user_ref = :u ORDER BY effective_from"),  # noqa: S608
                             {"u": user})).scalars().all()
    assert rows == ["monthly", None]  # history kept: the return to automatic is a row, never a delete


@pytest.mark.parametrize("sql", [
    f"UPDATE {TABLE} SET style = 'weekly'",  # noqa: S608 - constant table name
    f"DELETE FROM {TABLE}",  # noqa: S608 - constant table name
    f"TRUNCATE {TABLE}",
])
async def test_the_application_role_cannot_update_delete_or_truncate(db, sql):
    user, sid = await _strategy(db)
    await store.set_pin(db, user, sid, "weekly")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql))


@pytest.mark.parametrize("sql", [
    f"UPDATE {TABLE} SET style = 'weekly'",  # noqa: S608 - constant table name
    f"DELETE FROM {TABLE}",  # noqa: S608 - constant table name
    f"TRUNCATE {TABLE}",
])
async def test_the_guard_refuses_update_delete_truncate_even_for_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            user, sid = await _strategy(conn)
            await store.set_pin(conn, user, sid, "monthly")
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text(sql))
            assert getattr(info.value.orig, "sqlstate", None) == "OF035"
        finally:
            await trans.rollback()


async def test_a_back_dated_raw_insert_is_refused(db):
    user, sid = await _strategy(db)
    with pytest.raises(DBAPIError) as info:
        async with db.begin_nested():
            await db.execute(text(f"INSERT INTO {TABLE} (user_ref, strategy_id, style, effective_from) "  # noqa: S608
                                  "VALUES (:u, :s, 'weekly', clock_timestamp() - interval '1 minute')"),
                             {"u": user, "s": sid})
    assert getattr(info.value.orig, "sqlstate", None) == "OF035"


async def test_a_style_outside_the_list_is_refused_by_the_store_and_the_table(db):
    user, sid = await _strategy(db)
    with pytest.raises(store.AlertStyleError):
        await store.set_pin(db, user, sid, "yearly")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(f"INSERT INTO {TABLE} (user_ref, strategy_id, style, effective_from) "  # noqa: S608
                                  "VALUES (:u, :s, 'yearly', clock_timestamp())"), {"u": user, "s": sid})
    assert (await store.pin_of(db, user, sid)).style is None


async def test_another_users_strategy_is_not_found_on_read_and_write(db):
    owner, sid = await _strategy(db)
    await store.set_pin(db, owner, sid, "intraday")
    other = _user()
    with pytest.raises(store.StyleNotFound):
        await store.pin_of(db, other, sid)
    with pytest.raises(store.StyleNotFound):
        await store.set_pin(db, other, sid, "weekly")
    with pytest.raises(store.StyleNotFound):
        await store.pin_of(db, owner, 987654321)
    assert (await store.pin_of(db, owner, sid)).style == "intraday"


async def test_a_read_without_a_user_fails_closed(db):
    _, sid = await _strategy(db)
    with pytest.raises(store.AlertStyleError):
        await store.pin_of(db, "  ", sid)


def test_the_table_styles_equal_the_resolver_styles():
    assert _migration().STYLES == alert_presets.STYLES


def test_the_allowlist_chain_gains_exactly_block_27():
    m = _migration()
    previous = m.previous_allowlist_sql()
    extended = m.extended_allowlist_sql()
    assert m.ALLOWLIST_BLOCK_MARKER not in previous and extended.count(m.ALLOWLIST_BLOCK_MARKER) == 1
    assert extended.replace(m._block(), "", 1) == previous


async def test_the_post_allowlist_check_passes_on_the_migrated_database(admin_engine):
    async with admin_engine.connect() as conn:
        await conn.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))
