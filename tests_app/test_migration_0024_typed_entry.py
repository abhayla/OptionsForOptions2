"""REQ-077 AC-4 (part 21m): migration 0024 lets a saved leg carry the mark of a typed entry price.

Spec basis (quoted): REQ-077 AC-4 "A typed price is saved with the definition, marked as typed, with its time"; ADR-048
(the limited application role keeps its grants). The leg key set is an allow-list: 6 keys, 8 (with the 0011 pair
planned_entry + captured_at) or 9 (the pair plus entry_source 'typed' | 'captured'); everything else is refused.

Real PostgreSQL only; every test rolls back. Inserts run as ofo_app (app_engine); the downgrade round trip runs as the
owner (admin_engine) through the SQL the migrations themselves execute (tests_app/_migration_replay.py).
"""

from __future__ import annotations

import json

import pytest
from _migration_replay import round_trip_sql
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

MIGRATION = "0024_typed_entry_mark.py"
CHECK_VIOLATION = "23514"
INSERT = ("INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
          "VALUES (:u, 'NIFTY', CAST(:d AS JSONB), 1)")
INSERT_HISTORY = ("INSERT INTO public.strategy_history (strategy_id, change_summary, definition, "
                  "definition_schema_version) VALUES (:id, CAST(:s AS JSONB), CAST(:d AS JSONB), 1)")
REORDERED = json.dumps([{"kind": "legs_reordered"}])
TYPED_AT = "2026-10-24T09:20:05+05:30"
SIX_KEY_LEG = {"contract_id": 1001, "action": "SELL", "instrument": "CE", "strike": "23000", "expiry": "2026-10-29",
               "quantity": 75}
PAIR = {"planned_entry": "44.90", "captured_at": TYPED_AT}
LEG_8 = SIX_KEY_LEG | PAIR
LEG_9 = LEG_8 | {"entry_source": "typed"}
LEG_9_CAPTURED = LEG_8 | {"entry_source": "captured"}


def _definition(leg: dict) -> str:
    return json.dumps({"schema_version": 1, "underlying": "NIFTY", "legs": [leg], "rules_ref": None,
                       "risk_limits": {}, "preferences": {}})


async def _verdict(conn, sql: str, params: dict) -> tuple[str | None, str]:
    """(sqlstate, message) when PostgreSQL refuses the write, (None, '') when it accepts it. Always rolled back."""
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params)
        return None, ""
    except DBAPIError as err:
        return getattr(err.orig, "sqlstate", None), str(err.orig)
    finally:
        await savepoint.rollback()


async def _insert_verdict(conn, leg: dict) -> tuple[str | None, str]:
    return await _verdict(conn, INSERT, {"u": "test-0024", "d": _definition(leg)})


# --- invalid shapes: the allow-list (attack items 1 and 2) -------------------------------------------------------

BAD_LEGS = {
    "key alone": SIX_KEY_LEG | {"entry_source": "typed"},
    "key with planned_entry only": SIX_KEY_LEG | {"planned_entry": "44.90", "entry_source": "typed"},
    "key with captured_at only": SIX_KEY_LEG | {"captured_at": TYPED_AT, "entry_source": "typed"},
    "TYPED": LEG_8 | {"entry_source": "TYPED"},
    "manual": LEG_8 | {"entry_source": "manual"},
    "empty string": LEG_8 | {"entry_source": ""},
    "number 1": LEG_8 | {"entry_source": 1},
    "null": LEG_8 | {"entry_source": None},
    "true": LEG_8 | {"entry_source": True},
    "array": LEG_8 | {"entry_source": ["typed"]},
    "object": LEG_8 | {"entry_source": {"typed": 1}},
    "tenth key": LEG_9 | {"ltp": "1"},
    "9 keys, other name": LEG_8 | {"entry_origin": "typed"},
}


async def test_ac4_core_a_9_key_typed_leg_is_accepted_and_a_bad_value_refused(app_engine):
    """AC-4 core proof: after 0024 the database accepts the nine-key typed leg and refuses entry_source 'manual'."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _insert_verdict(conn, LEG_9) == (None, "")
            state, _ = await _insert_verdict(conn, LEG_8 | {"entry_source": "manual"})
            assert state == CHECK_VIOLATION, state
        finally:
            await trans.rollback()


@pytest.mark.parametrize("label", sorted(BAD_LEGS))
async def test_ac4_every_other_leg_shape_is_refused(app_engine, label):
    """AC-4: entry_source without the pair, with half the pair, with any value but 'typed'/'captured', of any other
    JSON type, or beside another extra key is refused by the validator (check_violation)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            state, _ = await _insert_verdict(conn, BAD_LEGS[label])
            assert state == CHECK_VIOLATION, f"{label}: {state}"
        finally:
            await trans.rollback()


async def test_ac4_six_eight_and_nine_key_legs_are_accepted_and_the_stored_leg_reads_back(app_engine):
    """AC-4 (attack item 3): the 6-key and 8-key legs stay valid; 9-key legs with 'typed' and 'captured' are valid;
    the typed leg reads back with the mark and its time exactly as written."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for leg in (SIX_KEY_LEG, LEG_8, LEG_9, LEG_9_CAPTURED):
                assert await _insert_verdict(conn, leg) == (None, ""), leg
            await conn.execute(text(INSERT), {"u": "test-0024-read", "d": _definition(LEG_9)})
            stored = (await conn.execute(text("SELECT definition -> 'legs' -> 0 FROM public.strategies "
                                              "WHERE user_ref = 'test-0024-read'"))).scalar_one()
            assert (stored["entry_source"], stored["captured_at"], stored["planned_entry"]) == (
                "typed", TYPED_AT, "44.90")
        finally:
            await trans.rollback()


async def test_ac4_a_change_item_leg_without_contract_id_cannot_carry_the_mark(app_engine):
    """AC-4: the five-key leg of a change item stays exactly five keys: the mark (even with the pair) is refused."""
    leg = {k: v for k, v in LEG_9.items() if k != "contract_id"}
    summary = json.dumps([{"kind": "legs_added", "legs": [leg]}])
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            strategy_id = (await conn.execute(text(INSERT + " RETURNING id"),
                                              {"u": "test-0024-ci", "d": _definition(SIX_KEY_LEG)})).scalar_one()
            state, _ = await _verdict(conn, INSERT_HISTORY, {"id": strategy_id, "s": summary,
                                                             "d": _definition(SIX_KEY_LEG)})
            assert state == CHECK_VIOLATION, state
        finally:
            await trans.rollback()


# --- downgrade and grants (attack items 4 and 5) -----------------------------------------------------------------


async def _grants(conn) -> list:
    rows = await conn.execute(text(
        "SELECT 'table', table_name, privilege_type, column_name FROM information_schema.column_privileges "
        "WHERE grantee = 'ofo_app' AND table_name IN ('strategies', 'strategy_history') "
        "UNION ALL SELECT 'function', p.proname, 'EXECUTE', has_function_privilege('ofo_app', p.oid, 'EXECUTE')::text "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname LIKE 'ofo_strategy_%' ORDER BY 1, 2, 3, 4"))
    return [tuple(r) for r in rows]


async def test_ac4_downgrade_is_refused_naming_the_table_while_a_typed_leg_is_stored(admin_engine):
    """AC-4 (attack item 4): with a typed leg in strategies, 0024's own downgrade raises naming the tables; the same
    for a typed leg only in strategy_history (append-only)."""
    own_down, _, _, _ = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for where in ("strategies", "history"):
                inner = await conn.begin_nested()
                strategy_id = (await conn.execute(text(INSERT + " RETURNING id"),
                                                  {"u": f"test-0024-{where}", "d": _definition(LEG_9)})).scalar_one()
                if where == "history":  # a history entry holds the current definition at its write; then it moves on
                    await conn.execute(text(INSERT_HISTORY), {"id": strategy_id, "s": REORDERED,
                                                              "d": _definition(LEG_9)})
                    await conn.execute(text("UPDATE public.strategies SET definition = CAST(:d AS JSONB) "
                                            "WHERE id = :id"), {"d": _definition(SIX_KEY_LEG), "id": strategy_id})
                with pytest.raises(DBAPIError, match="holds an entry source mark"):
                    async with conn.begin_nested():
                        await conn.execute(text(own_down[0]))
                await inner.rollback()
        finally:
            await trans.rollback()


async def test_ac4_downgrade_without_a_typed_leg_restores_0011s_validator_and_upgrade_restores_0024(admin_engine):
    """AC-4 (attack items 4 and 5): with no mark stored the downgrade succeeds and the 0011 validator is back (8-key leg
    accepted, 9-key leg refused); the upgrade brings 0024 back; the application role's grants are identical in the
    three states (ADR-048) and the allow-list 'post' check inside each step passes."""
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            before = await _grants(conn)
            assert before
            for sql in down:
                await conn.execute(text(sql))
            assert await _grants(conn) == before
            assert await _insert_verdict(conn, LEG_8) == (None, "")
            state, _ = await _insert_verdict(conn, LEG_9)
            assert state == CHECK_VIOLATION, state
            for sql in up:
                await conn.execute(text(sql))
            assert await _grants(conn) == before
            assert await _insert_verdict(conn, LEG_9) == (None, "")
        finally:
            await trans.rollback()
