"""ADR-330 (31): migration 0057 lets strategy_history hold the items ``deleted`` and ``undeleted``.

Spec basis (quoted): ADR-330 (31) "A delete and its Undo are recorded in the strategy's history as "Deleted" and
"Restored" entries with their times"; ADR-048 (the limited application role keeps what it had).

Core proof (first test): the limited role inserts [{"kind":"deleted"}] and [{"kind":"undeleted"}]; an item with an extra
key or an unknown kind is still refused with SQLSTATE 23514. The downgrade refuses (never deletes history) while a
delete or restore entry exists, and round-trips without one. Real PostgreSQL only; every test rolls back.
"""

from __future__ import annotations

import importlib.util
import json

import pytest
from _migration_replay import VERSIONS, own_step_sql, round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_migration_0025_strategy_name import DEFINITION, INSERT_HISTORY, _new_strategy, _verdict

MIGRATION = "0057_history_delete_entries.py"
CHECK_VIOLATION = "23514"


@pytest.mark.parametrize("summary,ok", [
    ([{"kind": "deleted"}], True),
    ([{"kind": "undeleted"}], True),
    ([{"kind": "deleted"}, {"kind": "legs_reordered"}], True),
    ([{"kind": "deleted", "x": 1}], False),
    ([{"kind": "undeleted", "seq": 1}], False),
    ([{"kind": "nonsense"}], False),
    ([{"kind": "Deleted"}], False),
    ([{"kind": "delete"}], False),
    ([{"kind": 5}], False),
    ([{}], False),
    ([], False),
    ({"kind": "deleted"}, False),
])
async def test_core_the_two_kinds_are_accepted_and_every_other_shape_is_still_refused(app_engine, summary, ok):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = await _new_strategy(conn, "test-0057-items")
            state, message = await _verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": json.dumps(summary),
                                                                   "d": DEFINITION})
            assert state == (None if ok else CHECK_VIOLATION), (summary, state, message)
        finally:
            await trans.rollback()


async def test_the_downgrade_refuses_while_a_delete_or_restore_entry_exists_and_never_removes_it(admin_engine):
    own_down, _ = own_step_sql(MIGRATION)
    for kind in ("deleted", "undeleted"):
        async with admin_engine.connect() as conn:
            trans = await conn.begin()
            try:
                strategy_id = await _new_strategy(conn, "test-0057-down")
                await conn.execute(text(INSERT_HISTORY), {"id": strategy_id, "d": DEFINITION,
                                                          "s": json.dumps([{"kind": kind}])})
                with pytest.raises(DBAPIError, match=r"refusing to downgrade 0057_history_delete_entries"):
                    async with conn.begin_nested():
                        for sql in own_down:
                            await conn.execute(text(sql))
                assert (await conn.execute(text("SELECT count(*) FROM public.strategy_history "
                                                "WHERE strategy_id = :i"), {"i": strategy_id})).scalar_one() == 1
            finally:
                await trans.rollback()


async def test_the_downgrade_round_trips_without_such_an_entry(admin_engine):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            strategy_id = await _new_strategy(conn, "test-0057-round")
            state, _ = await _verdict(conn, INSERT_HISTORY, {"id": strategy_id, "d": DEFINITION,
                                                             "s": json.dumps([{"kind": "deleted"}])})
            assert state == CHECK_VIOLATION  # at 0056 the kind is unknown again
            for sql in up:
                await conn.execute(text(sql))
            state, _ = await _verdict(conn, INSERT_HISTORY, {"id": strategy_id, "d": DEFINITION,
                                                             "s": json.dumps([{"kind": "deleted"}])})
            assert state is None
        finally:
            await trans.rollback()


def test_the_validator_pin_moves_with_the_body():
    found = importlib.util.spec_from_file_location("ofo_migration_0057_under_test", VERSIONS / MIGRATION)
    migration = importlib.util.module_from_spec(found)
    found.loader.exec_module(migration)
    assert migration.NEW_ITEMS_PIN != migration.OLD_ITEMS_PIN
    assert f"'{migration.NEW_ITEMS_PIN}'" in migration.extended_allowlist_sql()
    assert f"'{migration.OLD_ITEMS_PIN}'" not in migration.extended_allowlist_sql()
    assert f"'{migration.OLD_ITEMS_PIN}'" in migration.previous_allowlist_sql()
