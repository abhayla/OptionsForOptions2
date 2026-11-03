"""GC-ALERT1 wire-a: migration 0036 (the "worse" marker, held crossings) and the store's gate functions.

Spec basis: ADR-237 (5) "a held crossing ... is a row in a new insert-only table ... a record's 'worse' marker (none |
last | dismissed) is a new insert-only column of adjustment_suggestions; one migration, guarded like the suggestion
table (no update, no delete)"; REQ-170 AC-3/AC-4. Every test runs in a rolled-back transaction.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.adjustment import alert_gate as ag
from ofo_app import playbook_store as pb
from ofo_app import strategy_store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELD = "public.adjustment_held_crossings"
SUGG = "public.adjustment_suggestions"
D = Decimal


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0036_alert_gate_storage.py"
    found = importlib.util.spec_from_file_location("ofo_migration_0036_test", path)
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


@pytest.fixture
async def admin(admin_engine):
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(conn) -> tuple[str, int]:
    user = _user()
    _, stored = await _with_draft(conn, user)
    return user, stored.id


MIDDLE_T03 = D("0.35")


async def _open(conn, user, sid, rule="T-03", worse=None, threshold=MIDDLE_T03):  # noqa: PLR0913 - one record's fields
    return await pb.open_suggestion(conn, user, sid, rule, trigger_id=rule, stage="Middle", value=D("0.36"),
                                    threshold=threshold, worse=worse)


def _sqlstate(info) -> str | None:
    return getattr(info.value.orig, "sqlstate", None)


# ---- the worse marker -----------------------------------------------------------------------------------------------

async def test_open_with_worse_is_stored_and_existing_callers_store_none(db):
    user, sid = await _strategy(db)
    await _open(db, user, sid, "T-01")
    await _open(db, user, sid, "T-03", worse="dismissed")
    rows = dict((await db.execute(text(f"SELECT rule_id, worse FROM {SUGG} WHERE strategy_id = :s"),  # noqa: S608
                                  {"s": sid})).all())
    assert rows == {"T-01": None, "T-03": "dismissed"}


async def test_an_unknown_worse_marker_is_refused_by_the_store_and_the_table(db):
    user, sid = await _strategy(db)
    with pytest.raises(ValueError, match="worse"):
        await _open(db, user, sid, worse="much")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(f"INSERT INTO {SUGG} (strategy_id, rule_id, worse) VALUES (:s, 'T-03', 'much')"),  # noqa: S608
                             {"s": sid})


async def test_the_app_role_cannot_update_worse(db):
    user, sid = await _strategy(db)
    await _open(db, user, sid, worse="last")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(f"UPDATE {SUGG} SET worse = 'dismissed' WHERE strategy_id = :s"), {"s": sid})  # noqa: S608


async def test_the_guard_refuses_an_update_of_worse_even_for_the_owner(admin):
    user, sid = await _strategy(admin)
    await _open(admin, user, sid, worse=None)
    with pytest.raises(DBAPIError) as info:
        async with admin.begin_nested():
            await admin.execute(text(f"UPDATE {SUGG} SET worse = 'last' WHERE strategy_id = :s"), {"s": sid})  # noqa: S608
    assert _sqlstate(info) == "OF031"


async def test_mutation_old_guard_without_worse_lets_the_update_through_and_fails_the_allowlist(admin):
    """The discriminating proof: with 0031's guard (worse not in its list) the same UPDATE passes, so the test above
    fails on that guard; and the allow-list post check refuses the swapped body by its pin."""
    m = _migration()
    user, sid = await _strategy(admin)
    await _open(admin, user, sid, worse=None)
    await admin.execute(text(m._M31._suggestions_guard_sql()))
    await admin.execute(text(f"UPDATE {SUGG} SET worse = 'last' WHERE strategy_id = :s"), {"s": sid})  # noqa: S608
    with pytest.raises(DBAPIError):
        async with admin.begin_nested():
            await admin.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


# ---- held crossings -------------------------------------------------------------------------------------------------

async def test_record_held_stores_a_row_with_the_database_clock(db):
    user, sid = await _strategy(db)
    row = await pb.record_held(db, user, sid, "T-07", trigger_id="T-07", stage="Last day", value=D("81.5"),
                               threshold=D("80"), reason=ag.HELD_DAILY_LIMIT)
    assert (row.strategy_id, row.rule_id, row.value, row.threshold, row.reason) == \
        (sid, "T-07", D("81.5"), D("80"), "daily_limit")
    now = (await db.execute(text("SELECT clock_timestamp()"))).scalar_one()
    assert abs(now - row.held_at) < datetime.timedelta(seconds=5)
    yes_no = await pb.record_held(db, user, sid, "T-02", trigger_id="T-02", stage=None, value=None,
                                  threshold=None, reason=ag.HELD_QUIET_TIME)
    assert (yes_no.value, yes_no.reason) == (None, "quiet_time")


async def test_record_held_refuses_an_unknown_reason_a_bool_value_and_another_users_strategy(db):
    user, sid = await _strategy(db)
    with pytest.raises(ValueError, match="reason"):
        await pb.record_held(db, user, sid, "T-07", trigger_id=None, stage=None, value=None, threshold=None,
                             reason="tired")
    with pytest.raises(ValueError, match="bool"):
        await pb.record_held(db, user, sid, "T-02", trigger_id=None, stage=None, value=True, threshold=None,
                             reason="quiet_time")
    with pytest.raises(strategy_store.StrategyStoreError):
        await pb.record_held(db, _user(), sid, "T-07", trigger_id=None, stage=None, value=None, threshold=None,
                             reason="quiet_time")


async def test_a_back_dated_raw_held_at_is_overwritten_by_the_clock(admin):
    _, sid = await _strategy(admin)
    got = (await admin.execute(text(f"INSERT INTO {HELD} (strategy_id, rule_id, reason, held_at) "  # noqa: S608
                                    "VALUES (:s, 'T-07', 'daily_limit', '2020-01-01') RETURNING held_at"),
                               {"s": sid})).scalar_one()
    assert got.year >= 2026  # noqa: PLR2004


@pytest.mark.parametrize("sql", [f"UPDATE {HELD} SET reason = 'quiet_time'", f"DELETE FROM {HELD}",  # noqa: S608
                                 f"TRUNCATE {HELD}"])
async def test_the_app_role_cannot_update_delete_or_truncate_held(db, sql):
    user, sid = await _strategy(db)
    await pb.record_held(db, user, sid, "T-07", trigger_id=None, stage=None, value=None, threshold=None,
                         reason="daily_limit")
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql))


@pytest.mark.parametrize("sql", [f"UPDATE {HELD} SET reason = 'quiet_time'", f"DELETE FROM {HELD}",  # noqa: S608
                                 f"TRUNCATE {HELD}"])
async def test_the_held_guard_refuses_update_delete_truncate_even_for_the_owner(admin, sql):
    user, sid = await _strategy(admin)
    await pb.record_held(admin, user, sid, "T-07", trigger_id=None, stage=None, value=None, threshold=None,
                         reason="daily_limit")
    with pytest.raises(DBAPIError) as info:
        async with admin.begin_nested():
            await admin.execute(text(sql))
    assert _sqlstate(info) == "OF036"


# ---- allow-list -----------------------------------------------------------------------------------------------------

def test_the_constants_match_the_gate_and_the_store():
    m = _migration()
    assert m.REASONS == (ag.HELD_DAILY_LIMIT, ag.HELD_QUIET_TIME) == pb.HELD_REASONS
    assert (None, *m.WORSE) == pb.WORSE_MARKS
    assert "NEW.worse" in m.suggestions_guard_sql() and "OLD.worse" in m.suggestions_guard_sql()


def test_the_allowlist_chain_gains_block_28_and_repins_only_the_suggestion_part():
    m = _migration()
    previous, extended = m.previous_allowlist_sql(), m.extended_allowlist_sql()
    assert m.ALLOWLIST_BLOCK_MARKER not in previous and extended.count(m.ALLOWLIST_BLOCK_MARKER) == 1
    assert m.OLD_SUGGESTION_PIN not in extended and extended.count(m.SUGGESTION_PIN) == 1
    undone = extended.replace(m._block(), "", 1).replace(m._new_suggestion_block(), m._old_suggestion_block(), 1)
    assert undone == previous


async def test_the_post_allowlist_check_passes_on_the_migrated_database(admin):
    await admin.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


@pytest.mark.parametrize("mutation", [
    f'GRANT UPDATE ON {HELD} TO "ofo_app"',
    f'GRANT UPDATE (worse) ON {SUGG} TO "ofo_app"',
    f'GRANT DELETE ON {HELD} TO "ofo_app"',
    f'REVOKE INSERT (worse) ON {SUGG} FROM "ofo_app"',
    f"ALTER TABLE {HELD} DISABLE TRIGGER adjustment_held_crossings_no_truncate",
])
async def test_allowlist_drift_fails_the_post_check(admin, mutation):
    await admin.execute(text(mutation))
    with pytest.raises(DBAPIError):
        async with admin.begin_nested():
            await admin.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


# ---- review #3: the downgrade ---------------------------------------------------------------------------------------

def _recorded_downgrade() -> list[str]:
    recorded: list[str] = []
    m = _migration()
    m.op = SimpleNamespace(execute=lambda sql, *a, **k: recorded.append(str(sql)))
    m._BASE._app_role = lambda: "ofo_app"
    m.downgrade()
    return recorded


@pytest.mark.parametrize("kind", ["held", "worse"])
async def test_the_downgrade_refuses_while_held_rows_or_worse_marks_exist(admin, kind):
    user, sid = await _strategy(admin)
    if kind == "held":
        await pb.record_held(admin, user, sid, "T-03", trigger_id="T-03", stage="Middle", value=D("0.36"),
                             threshold=MIDDLE_T03, reason=ag.HELD_DAILY_LIMIT)
    else:
        await _open(admin, user, sid, worse="last")
    with pytest.raises(DBAPIError, match="refusing to downgrade 0036_alert_gate_storage") as info:
        async with admin.begin_nested():
            await admin.execute(text(_recorded_downgrade()[0]))
    assert _sqlstate(info) == _migration().SQLSTATE


async def test_the_downgrade_restores_the_0031_guard_and_the_0035_allowlist_chain(admin):
    """On a database with no held row and no worse mark the whole downgrade runs (rolled back after): the held table
    and the worse column are gone, the suggestion guard is 0031's again and the allowlist post check (0035's chain,
    the downgrade's own last statement) passes."""
    for sql in _recorded_downgrade():
        await admin.execute(text(sql))
    names = (await admin.execute(text("SELECT to_regclass(:t), (SELECT count(*) FROM information_schema.columns "
                                      "WHERE table_schema = 'public' AND table_name = 'adjustment_suggestions' "
                                      "AND column_name = 'worse')"), {"t": HELD})).one()
    assert tuple(names) == (None, 0)
    guard = (await admin.execute(text("SELECT pg_get_functiondef(p.oid) FROM pg_trigger t JOIN pg_proc p "
                                      "ON p.oid = t.tgfoid WHERE t.tgrelid = CAST(:s AS regclass) "
                                      "AND NOT t.tgisinternal AND p.proname LIKE '%guard%'"),
                                 {"s": SUGG})).scalars().all()
    assert guard and all("worse" not in g for g in guard), guard
    await admin.execute(text("SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post')"))


# ---- gate rows (restore input) --------------------------------------------------------------------------------------

async def test_gate_rows_none_rows_and_restore(db):
    user, sid = await _strategy(db)
    today = (await db.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date"))).scalar_one()
    assert await pb.gate_rows(db, user, sid, today) == ag.GateRows((), 0)  # none
    first = await _open(db, user, sid, "T-03", threshold=D("0.35"))
    await pb.lapse(db, user, first.id)
    second = await _open(db, user, sid, "T-03", threshold=D("0.40"), worse="last")
    await pb.dismiss(db, user, second.id)
    await _open(db, user, sid, "T-01", threshold=D("0.5"))
    got = await pb.gate_rows(db, user, sid, today)
    assert got.opened_today == 3  # noqa: PLR2004 - every record today counts for the cap
    last = {r.rule_id: r for r in got.last}
    assert (last["T-03"].threshold, last["T-03"].dismissed, last["T-03"].open) == (D("0.40"), True, False)
    assert (last["T-01"].threshold, last["T-01"].dismissed, last["T-01"].open) == (D("0.5"), False, True)
    assert last["T-03"].id == second.id  # #639 item 2: the worker's dismiss matches this record id
    assert (await pb.gate_rows(db, user, sid, today + datetime.timedelta(days=1))).opened_today == 0
    spec = ag.RuleSpec("T-03", "ge", (D("0.35"), D("0.40")))
    state = ag.restore(got, today, {"T-03": spec})
    assert state.opened_today == 3 and state.rule("T-03").record.level == 1  # noqa: PLR2004


async def test_gate_rows_another_users_or_a_missing_strategy_is_not_found(db):
    user, sid = await _strategy(db)
    today = datetime.date(2026, 11, 2)
    with pytest.raises(strategy_store.StrategyStoreError):
        await pb.gate_rows(db, _user(), sid, today)
    with pytest.raises(strategy_store.StrategyStoreError):
        await pb.gate_rows(db, user, 987654321, today)
