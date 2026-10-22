"""W-124 (REQ-087 AC-3): the per-user setting store on the real database, as the limited ``ofo_app`` role
(migration 0022).

Core: a user who never chose reads the default 10; a write of 20 reads back 20 for that user only; a second write
changes the one row in place. Every test runs inside an outer transaction that is rolled back, so the shared ofo_test
is left with 0 rows (finding branch-migration-tests-move-shared-db). This file runs its own tests because it is a
migration / DB store.

Guards, each with the test that kills it: no DELETE for the app role; no UPDATE of user_ref / key; a key off the closed
pattern refused by the database; an unknown key and a value off the list refused by the store before any SQL; a bool is
not an int choice (True == 1 never passes); updated_at is stamped by the database trigger, not by the caller.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ofo_app import user_setting_store as store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

KEY = store.CHAIN_STRIKES_EACH_SIDE
MIGRATION = (Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
             / "0022_user_settings.py")
OWNER, OTHER = "u-owner", "u-other"
DEFAULT, TWENTY = 10, 20
FIRST_YEAR = 2026


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_core_default_then_write_then_read_back_for_that_user_only(db):
    assert await store.read(db, OWNER, KEY) == (DEFAULT, True)
    await store.write(db, OWNER, KEY, TWENTY)
    assert await store.read(db, OWNER, KEY) == (TWENTY, False)
    assert await store.read(db, OTHER, KEY) == (DEFAULT, True)  # another user is untouched


async def test_a_second_write_updates_the_one_row_in_place(db):
    await store.write(db, OWNER, KEY, TWENTY)
    await store.write(db, OWNER, KEY, 40)
    rows = (await db.execute(text("SELECT value::text FROM public.user_settings WHERE user_ref = :u"),
                             {"u": OWNER})).all()
    assert [r[0] for r in rows] == ["40"]


@pytest.mark.parametrize("bad", [0, 5, 15, 41, "20", True, 20.0, None, [10]])
async def test_a_value_off_the_list_is_refused_before_any_sql(db, bad):
    with pytest.raises(store.SettingError) as caught:
        await store.write(db, OWNER, KEY, bad)
    assert caught.value.code == store.BAD_VALUE
    assert await store.read(db, OWNER, KEY) == (DEFAULT, True)


async def test_an_unknown_key_and_an_empty_user_are_refused(db):
    with pytest.raises(store.SettingError) as unknown:
        await store.read(db, OWNER, "chain.something_else")
    assert unknown.value.code == store.UNKNOWN_KEY
    with pytest.raises(store.SettingError):
        await store.write(db, "", KEY, TWENTY)


async def test_a_stored_value_no_longer_allowed_reads_as_the_default_not_an_error(db):
    """The allowed list can change later; an old stored 15 must not break the screen."""
    await db.execute(text("INSERT INTO public.user_settings (user_ref, key, value) "
                          "VALUES (:u, :k, CAST('15' AS JSONB))"),
                     {"u": OWNER, "k": KEY})
    assert await store.read(db, OWNER, KEY) == (DEFAULT, True)


async def test_the_app_role_cannot_delete_or_move_a_row(db):
    await store.write(db, OWNER, KEY, TWENTY)
    for sql in ("DELETE FROM public.user_settings WHERE user_ref = :u",
                "UPDATE public.user_settings SET key = 'other.key' WHERE user_ref = :u",
                "UPDATE public.user_settings SET user_ref = 'x' WHERE user_ref = :u"):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text(sql), {"u": OWNER})
    assert await store.read(db, OWNER, KEY) == (TWENTY, False)


async def test_the_database_refuses_a_key_off_the_closed_pattern(db):
    for key in ("Chain.Strikes", "1chain", "has space", ""):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text("INSERT INTO public.user_settings (user_ref, key, value) "
                                      "VALUES (:u, :k, CAST('1' AS JSONB))"), {"u": OWNER, "k": key})


async def test_updated_at_is_stamped_by_the_trigger_not_the_caller(db):
    with pytest.raises(DBAPIError):  # the app role has no INSERT/UPDATE grant on updated_at
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.user_settings (user_ref, key, value, updated_at) "
                                  "VALUES (:u, :k, CAST('10' AS JSONB), '2001-01-01')"), {"u": OWNER, "k": KEY})
    await store.write(db, OWNER, KEY, TWENTY)
    year = (await db.execute(text("SELECT EXTRACT(YEAR FROM updated_at) FROM public.user_settings "
                                  "WHERE user_ref = :u"), {"u": OWNER})).scalar_one()
    assert int(year) >= FIRST_YEAR


async def test_the_downgrade_guard_refuses_while_a_row_exists_and_passes_when_empty(admin_engine):
    """REQ-087 AC-3 / ADR-093: a stored preference is the user's record. The migration's own refuse-SQL, run as the
    owner
    inside a transaction that is rolled back: it raises with a row present and is silent on an empty table."""
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("ofo_mig_0022_guard_test", MIGRATION)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            assert (await conn.execute(text("SELECT count(*) FROM public.user_settings"))).scalar_one() == 0
            await conn.execute(text(mig.refuse_downgrade_sql()))  # empty: no error
            await conn.execute(text("INSERT INTO public.user_settings (user_ref, key, value) "
                                    "VALUES ('u-guard', 'chain.strikes_each_side', CAST('20' AS JSONB))"))
            with pytest.raises(DBAPIError, match="refusing downgrade"):
                async with conn.begin_nested():
                    await conn.execute(text(mig.refuse_downgrade_sql()))
        finally:
            await outer.rollback()
