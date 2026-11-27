"""Migration 0056 (P8; ADR-330 (9)): several standard playbooks per strategy type.

Real PostgreSQL. The one-system-per-type index is gone and a unique (type, slug) index stands for standard ones; the
12 seeded rows carry '<type>-default'; a user's own playbook has no slug; the app-role allow-list passes; the allow-list
text fails closed; the downgrade refuses while a type holds a second standard playbook; old code's one-row-per-type
query still returns one row with only the seeded rows.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from ofo.adjustment.playbook_types import TYPE_KEYS
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

VERSIONS = pathlib.Path(__file__).resolve().parent.parent / "backend/ofo_app/alembic/versions"
PATH = VERSIONS / "0056_several_standard_playbooks.py"
TABLE = "public.adjustment_playbooks"
# e01f747's _SELECT_SYSTEM
OLD_SELECT_SYSTEM = f"SELECT id FROM {TABLE} WHERE strategy_type = :type AND is_system"  # noqa: S608 - constant name


def _m56():
    found = importlib.util.spec_from_file_location("ofo_migration_0056_test", PATH)
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


async def test_the_twelve_seeded_rows_carry_their_default_slug_and_the_old_query_still_finds_one_each(admin_engine):
    async with admin_engine.connect() as c:
        slugs = dict((await c.execute(text(f"SELECT strategy_type, slug FROM {TABLE} WHERE is_system"))).all())  # noqa: S608 - constant table name
        counts = [len((await c.execute(text(OLD_SELECT_SYSTEM), {"type": t})).all()) for t in TYPE_KEYS]
    assert slugs == {t: f"{t}-default" for t in TYPE_KEYS}
    assert counts == [1] * len(TYPE_KEYS)


async def test_the_one_system_index_is_gone_and_the_slug_index_stands(admin_engine):
    async with admin_engine.connect() as c:
        names = {r[0] for r in (await c.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'adjustment_playbooks'"
        ))).all()}
    assert "adjustment_playbooks_one_system" not in names
    assert "adjustment_playbooks_standard_slug" in names


async def test_a_slug_is_for_a_standard_playbook_only_and_in_shape(admin_engine):
    body = "(SELECT body FROM public.adjustment_playbooks WHERE is_system AND strategy_type = 'ic')"
    async with admin_engine.connect() as c:
        outer = await c.begin()
        try:
            for user_ref, system, slug in (("someone", "false", "mine"), (None, "true", "Bad Slug")):
                with pytest.raises(DBAPIError, match="adjustment_playbooks_slug_shape"):
                    async with c.begin_nested():
                        await c.execute(text(
                            "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, is_system, body, "
                            f"slug) SELECT :u, 'ic', 'X', {system}, {body}, :s"), {"u": user_ref, "s": slug})
        finally:
            await outer.rollback()


async def test_the_allowlist_post_check_passes(admin_engine):
    async with admin_engine.connect() as c:
        await c.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


def test_the_allowlist_text_holds_block_36_once_and_fails_closed():
    m = _m56()
    sql = m.extended_allowlist_sql()
    assert sql.count(m.ALLOWLIST_BLOCK_MARKER) == 1
    assert sql != m.previous_allowlist_sql()
    m.previous_allowlist_sql = lambda: sql  # block 36 already in
    with pytest.raises(RuntimeError, match="changed shape"):
        m.extended_allowlist_sql()


async def test_downgrade_is_refused_while_a_type_holds_a_second_standard_playbook(admin_engine):
    from _migration_replay import recorded  # noqa: PLC0415

    async with admin_engine.connect() as c:
        outer = await c.begin()
        try:
            await c.execute(text(
                "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, is_system, body, slug) "
                "SELECT NULL, 'ic', 'ic: second', true, body, 'ic-second' FROM public.adjustment_playbooks "
                "WHERE is_system AND strategy_type = 'ic'"))
            sql = recorded("0056_several_standard_playbooks.py", "downgrade")
            with pytest.raises(DBAPIError, match=r"refusing to downgrade 0056_several_standard_playbooks: 1 strategy"):
                async with c.begin_nested():
                    for statement in sql:
                        await c.execute(text(statement))
        finally:
            await outer.rollback()


async def test_downgrade_with_only_the_seeded_rows_restores_the_one_system_index(admin_engine):
    from _migration_replay import round_trip_sql  # noqa: PLC0415

    async with admin_engine.connect() as c:
        outer = await c.begin()
        try:
            # every later migration's downgrade first (0057 and on), then 0056's: the database is at head
            for statement in round_trip_sql("0056_several_standard_playbooks.py")[2]:
                await c.execute(text(statement))
            names = {r[0] for r in (await c.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'adjustment_playbooks'"))).all()}
            assert "adjustment_playbooks_one_system" in names
            assert "adjustment_playbooks_standard_slug" not in names
        finally:
            await outer.rollback()
