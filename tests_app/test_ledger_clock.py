"""W-051 core proof: the trusted database clock on ledger_entries (REQ-064 AC-2).

Spec basis: REQ-064 AC-2 "Audit and timeline records are append-only."; ADR-023 Q225 clarification ("recorded at" is
stamped by the ledger from its own clock; a caller can never supply it. Every new event's own date must lie within
the clock-skew window of that stamp, both ways); ADR-023 Q256 "the clock-skew window is 60 seconds, both ways.";
ADR-048 (the proof runs as the non-superuser application role on real PostgreSQL).

Every check below is a plain function over a connection, so the same check runs twice: once against the real guard
(must pass) and once in a mutation test where the owner role weakens the guard inside a rolled-back transaction and
then acts as the application role (the check must fail). Expected values come from the spec text: 60 s window,
2 minutes off refused, 30 s off accepted, a caller's 2020-01-01 never stored, SQLSTATE 42501 (insufficient
privilege) for UPDATE/DELETE/TRUNCATE/ALTER ... DISABLE TRIGGER.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from ofo_app import ledger

# From the spec, not from the code under test.
SKEW_WINDOW = timedelta(seconds=60)  # ADR-023 Q256
CALLER_RECORDED_AT = datetime(2020, 1, 1, tzinfo=UTC)  # W-051 proof (a)
INSUFFICIENT_PRIVILEGE = "42501"  # PostgreSQL SQLSTATE for "permission denied" / "must be owner"
LEDGER_CLOCK_SQLSTATE = "OF001"  # documented in the baseline migration
TRIGGER = "ledger_entries_trusted_clock"

INSERT_WITH_CALLER_STAMP = text(
    "INSERT INTO ledger_entries (kind, event_at, recorded_at, payload) "
    "VALUES (:kind, :event_at, :recorded_at, CAST(:payload AS jsonb)) RETURNING id, recorded_at"
)
INSERT = text(
    "INSERT INTO ledger_entries (kind, event_at, payload) "
    "VALUES (:kind, :event_at, CAST(:payload AS jsonb)) RETURNING id, recorded_at"
)


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


def _kind() -> str:
    return f"test-{uuid.uuid4().hex}"


async def _db_clock(conn: AsyncConnection) -> datetime:
    return (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def _insert(conn: AsyncConnection, kind: str, event_at: datetime | None, recorded_at: datetime | None = None):
    params = {"kind": kind, "event_at": event_at, "payload": json.dumps({"t": kind})}
    if recorded_at is None:
        return (await conn.execute(INSERT, params)).one()
    return (await conn.execute(INSERT_WITH_CALLER_STAMP, {**params, "recorded_at": recorded_at})).one()


async def _expect_refused(conn: AsyncConnection, sql: str, params: dict | None, expected: str) -> None:
    """Run `sql` inside a savepoint; it must fail with SQLSTATE `expected`."""
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql), params or {})
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == expected, f"refused with SQLSTATE {got}, expected {expected}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


async def _expect_insert_refused(conn: AsyncConnection, event_at: datetime | None) -> None:
    try:
        async with conn.begin_nested():
            await _insert(conn, _kind(), event_at)
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == LEDGER_CLOCK_SQLSTATE, f"refused with SQLSTATE {got}, expected {LEDGER_CLOCK_SQLSTATE}: {exc}"
        return
    raise AssertionError(f"insert with event_at={event_at!r} was accepted")


# ---- checks (each used by a real test and, where named, by a mutation test) ----


async def check_caller_recorded_at_is_ignored(conn: AsyncConnection) -> None:
    """(a) A caller-supplied recorded_at of 2020-01-01 is replaced by the server clock at insert."""
    before = await _db_clock(conn)
    row_id, _ = await _insert(conn, _kind(), before, CALLER_RECORDED_AT)
    after = await _db_clock(conn)
    stored = (await conn.execute(text("SELECT recorded_at FROM ledger_entries WHERE id = :i"), {"i": row_id})).scalar_one()
    assert stored != CALLER_RECORDED_AT, "the caller's recorded_at was stored"
    assert before <= stored <= after, f"stored {stored} is not the server clock between {before} and {after}"


async def check_two_minutes_off_refused(conn: AsyncConnection) -> None:
    """(b) event_at 2 minutes off the stamp is refused, both ways."""
    now = await _db_clock(conn)
    await _expect_insert_refused(conn, now + timedelta(minutes=2))
    await _expect_insert_refused(conn, now - timedelta(minutes=2))


async def check_update_refused(conn: AsyncConnection) -> None:
    row_id, _ = await _insert(conn, _kind(), await _db_clock(conn))
    await _expect_refused(
        conn, "UPDATE ledger_entries SET kind = 'tampered' WHERE id = :i", {"i": row_id}, INSUFFICIENT_PRIVILEGE
    )


async def check_delete_refused(conn: AsyncConnection) -> None:
    row_id, _ = await _insert(conn, _kind(), await _db_clock(conn))
    await _expect_refused(conn, "DELETE FROM ledger_entries WHERE id = :i", {"i": row_id}, INSUFFICIENT_PRIVILEGE)


async def check_disable_trigger_refused(conn: AsyncConnection) -> None:
    """(d) The application role cannot switch the guard off."""
    await _expect_refused(conn, f"ALTER TABLE ledger_entries DISABLE TRIGGER {TRIGGER}", None, INSUFFICIENT_PRIVILEGE)
    await _expect_refused(conn, "ALTER TABLE ledger_entries DISABLE TRIGGER ALL", None, INSUFFICIENT_PRIVILEGE)
    await _expect_refused(conn, f"DROP TRIGGER {TRIGGER} ON ledger_entries", None, INSUFFICIENT_PRIVILEGE)


# ---- the proof, as the application role ----


async def test_app_role_is_not_superuser_and_not_owner(app_engine: AsyncEngine) -> None:
    """Precondition: without it every privilege test below would prove nothing."""
    async with app_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT r.rolsuper, r.rolbypassrls, t.tableowner, current_user "
                    "FROM pg_roles r, pg_tables t "
                    "WHERE r.rolname = current_user AND t.tablename = 'ledger_entries'"
                )
            )
        ).one()
    rolsuper, bypassrls, owner, me = row
    assert rolsuper is False and bypassrls is False, f"{me} must be NOSUPERUSER (ADR-048)"
    assert owner != me, f"{me} owns ledger_entries; migrations must run as the owner role"


async def test_a_caller_recorded_at_2020_is_replaced_by_server_clock(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_caller_recorded_at_is_ignored(conn)


async def test_b_event_two_minutes_off_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_two_minutes_off_refused(conn)


async def test_b_refused_insert_rolls_back_the_transaction(app_engine: AsyncEngine) -> None:
    kind = _kind()
    async with app_engine.connect() as conn:
        with pytest.raises(DBAPIError) as info:
            async with conn.begin():
                now = await _db_clock(conn)
                await _insert(conn, kind, now)  # valid row in the same transaction
                await _insert(conn, kind, now + timedelta(minutes=2))
        assert _sqlstate(info.value) == LEDGER_CLOCK_SQLSTATE
    async with app_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM ledger_entries WHERE kind = :k"), {"k": kind})).scalar_one()
    assert count == 0, "the valid row in the refused transaction was kept"


async def test_event_thirty_seconds_off_is_accepted_both_ways(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        for offset in (timedelta(seconds=30), timedelta(seconds=-30)):
            row_id, recorded_at = await _insert(conn, _kind(), now + offset)
            assert row_id > 0
            assert abs((now + offset) - recorded_at) <= SKEW_WINDOW


async def test_null_event_at_is_refused_by_the_trigger(app_engine: AsyncEngine) -> None:
    """Fail closed: an undated event is refused by the clock guard itself, not left to chance."""
    async with app_engine.connect() as conn, conn.begin():
        await _expect_insert_refused(conn, None)


async def test_c_update_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_update_refused(conn)


async def test_c_delete_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_delete_refused(conn)


async def test_truncate_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await _expect_refused(conn, "TRUNCATE ledger_entries", None, INSUFFICIENT_PRIVILEGE)


async def test_d_disable_trigger_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_disable_trigger_refused(conn)


async def test_replica_mode_cannot_be_set_to_skip_triggers(app_engine: AsyncEngine) -> None:
    """session_replication_role = replica would skip ordinary triggers; only a superuser may set it."""
    async with app_engine.connect() as conn, conn.begin():
        await _expect_refused(conn, "SET LOCAL session_replication_role = replica", None, INSUFFICIENT_PRIVILEGE)


async def test_repository_append_returns_db_stamp_and_never_sends_recorded_at(app_engine: AsyncEngine) -> None:
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(app_engine.sync_engine, "before_cursor_execute", capture)
    try:
        async with AsyncSession(app_engine) as session, session.begin():
            before = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
            row_id, recorded_at = await ledger.append(session, _kind(), before, {"amount": "12.50"})
            after = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()
    finally:
        event.remove(app_engine.sync_engine, "before_cursor_execute", capture)

    assert isinstance(row_id, int) and row_id > 0
    assert before <= recorded_at <= after, "append did not return the database-stamped recorded_at"
    inserts = [s for s in statements if s.lstrip().upper().startswith("INSERT INTO LEDGER_ENTRIES")]
    assert len(inserts) == 1, statements
    columns = re.search(r"\(([^)]*)\)", inserts[0]).group(1)
    assert "recorded_at" not in [c.strip() for c in columns.split(",")], inserts[0]


async def test_repository_refuses_naive_event_at_without_touching_the_db() -> None:
    with pytest.raises(ValueError):
        await ledger.append(None, "k", datetime(2026, 10, 2, 9, 0), {})  # type: ignore[arg-type]


# ---- mutation tests: weaken the guard (rolled back) and show the checks turn red ----


async def _as_app_role_after(admin_engine: AsyncEngine, app_engine: AsyncEngine, mutation_sql: list[str], check) -> None:
    role = app_engine.url.username
    assert role and re.fullmatch(r"[a-z_][a-z0-9_]*", role), role
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in mutation_sql:
                await conn.execute(text(sql.format(role=role)))
            await conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            with pytest.raises(AssertionError):
                await check(conn)
        finally:
            await trans.rollback()


async def test_mutation_dropping_the_trigger_turns_a_and_b_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    drop = [f"DROP TRIGGER {TRIGGER} ON ledger_entries"]
    await _as_app_role_after(admin_engine, app_engine, drop, check_caller_recorded_at_is_ignored)
    await _as_app_role_after(admin_engine, app_engine, drop, check_two_minutes_off_refused)


async def test_mutation_granting_update_turns_c_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _as_app_role_after(
        admin_engine, app_engine, ['GRANT UPDATE ON ledger_entries TO "{role}"'], check_update_refused
    )
    await _as_app_role_after(
        admin_engine, app_engine, ['GRANT DELETE ON ledger_entries TO "{role}"'], check_delete_refused
    )


async def test_mutation_making_app_role_owner_turns_d_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _as_app_role_after(
        admin_engine, app_engine, ['ALTER TABLE ledger_entries OWNER TO "{role}"'], check_disable_trigger_refused
    )


async def test_guard_still_in_place_after_mutation_tests(app_engine: AsyncEngine) -> None:
    """The mutations were rolled back: the real guard still holds."""
    async with app_engine.connect() as conn, conn.begin():
        await check_caller_recorded_at_is_ignored(conn)
        await check_update_refused(conn)
