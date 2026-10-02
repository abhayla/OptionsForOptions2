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
    "INSERT INTO public.ledger_entries (kind, event_at, recorded_at, payload) "
    "VALUES (:kind, :event_at, :recorded_at, CAST(:payload AS jsonb)) RETURNING id, recorded_at"
)
INSERT = text(
    "INSERT INTO public.ledger_entries (kind, event_at, payload) "
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
    stored = (await conn.execute(text("SELECT recorded_at FROM public.ledger_entries WHERE id = :i"), {"i": row_id})).scalar_one()
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
        conn, "UPDATE public.ledger_entries SET kind = 'tampered' WHERE id = :i", {"i": row_id}, INSUFFICIENT_PRIVILEGE
    )


async def check_delete_refused(conn: AsyncConnection) -> None:
    row_id, _ = await _insert(conn, _kind(), await _db_clock(conn))
    await _expect_refused(conn, "DELETE FROM public.ledger_entries WHERE id = :i", {"i": row_id}, INSUFFICIENT_PRIVILEGE)


async def check_disable_trigger_refused(conn: AsyncConnection) -> None:
    """(d) The application role cannot switch the guard off."""
    await _expect_refused(conn, f"ALTER TABLE public.ledger_entries DISABLE TRIGGER {TRIGGER}", None, INSUFFICIENT_PRIVILEGE)
    await _expect_refused(conn, "ALTER TABLE public.ledger_entries DISABLE TRIGGER ALL", None, INSUFFICIENT_PRIVILEGE)
    await _expect_refused(conn, f"DROP TRIGGER {TRIGGER} ON public.ledger_entries", None, INSUFFICIENT_PRIVILEGE)


# ---- the proof, as the application role ----


APP_ROLE_VIEW = text(
    """
    WITH me AS (SELECT * FROM pg_roles WHERE rolname = current_user)
    SELECT
        me.rolsuper, me.rolcreatedb, me.rolcreaterole, me.rolreplication, me.rolbypassrls, me.rolcanlogin,
        EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = me.oid) AS member_of_any,
        EXISTS (SELECT 1 FROM pg_database d WHERE d.datname = current_database() AND d.datdba = me.oid) AS owns_db,
        EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner = me.oid) AS owns_schema,
        EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = me.oid) AS owns_relation,
        EXISTS (SELECT 1 FROM pg_proc p WHERE p.proowner = me.oid) AS owns_function,
        EXISTS (SELECT 1 FROM pg_type t WHERE t.typowner = me.oid) AS owns_type,
        has_database_privilege(me.oid, current_database(), 'CREATE') AS db_create,
        has_database_privilege(me.oid, current_database(), 'TEMPORARY') AS db_temp,
        has_schema_privilege(me.oid, 'public', 'CREATE') AS public_create,
        has_table_privilege(me.oid, 'public.ledger_entries', 'SELECT') AS t_select,
        has_table_privilege(me.oid, 'public.ledger_entries', 'INSERT') AS t_insert_all,
        has_table_privilege(me.oid, 'public.ledger_entries', 'UPDATE') AS t_update,
        has_table_privilege(me.oid, 'public.ledger_entries', 'DELETE') AS t_delete,
        has_table_privilege(me.oid, 'public.ledger_entries', 'TRUNCATE') AS t_truncate,
        has_table_privilege(me.oid, 'public.ledger_entries', 'REFERENCES') AS t_references,
        has_table_privilege(me.oid, 'public.ledger_entries', 'TRIGGER') AS t_trigger,
        has_column_privilege(me.oid, 'public.ledger_entries', 'id', 'INSERT') AS c_id_insert,
        has_column_privilege(me.oid, 'public.ledger_entries', 'kind', 'INSERT')
          AND has_column_privilege(me.oid, 'public.ledger_entries', 'event_at', 'INSERT')
          AND has_column_privilege(me.oid, 'public.ledger_entries', 'recorded_at', 'INSERT')
          AND has_column_privilege(me.oid, 'public.ledger_entries', 'payload', 'INSERT') AS c_allowed_insert,
        has_sequence_privilege(me.oid, 'public.ledger_entries_id_seq', 'USAGE') AS s_usage,
        has_sequence_privilege(me.oid, 'public.ledger_entries_id_seq', 'UPDATE') AS s_update,
        (SELECT setting FROM pg_settings WHERE name = 'statement_timeout') AS statement_timeout_ms,
        (SELECT setting FROM pg_settings WHERE name = 'idle_in_transaction_session_timeout') AS idle_timeout_ms
    FROM me
    """
)


async def test_app_role_privileges_equal_the_allowlist(app_engine: AsyncEngine) -> None:
    """Precondition, as ofo_app sees itself: without it every privilege test below would prove nothing."""
    async with app_engine.connect() as conn:
        v = (await conn.execute(APP_ROLE_VIEW)).mappings().one()
    # 1. attributes
    assert (v["rolsuper"], v["rolcreatedb"], v["rolcreaterole"], v["rolreplication"], v["rolbypassrls"]) == (
        False, False, False, False, False,
    ), dict(v)
    assert v["rolcanlogin"] is True
    # 2. membership: none at all
    assert v["member_of_any"] is False
    # 3. ownership: nothing
    assert not any(v[k] for k in ("owns_db", "owns_schema", "owns_relation", "owns_function", "owns_type")), dict(v)
    # 4-5. database and schema privileges
    assert (v["db_create"], v["db_temp"], v["public_create"]) == (False, False, False), dict(v)
    # 6. exactly SELECT + column INSERT(kind, event_at, recorded_at, payload); sequence USAGE only
    assert v["t_select"] is True and v["c_allowed_insert"] is True
    assert not any(
        v[k] for k in ("t_insert_all", "t_update", "t_delete", "t_truncate", "t_references", "t_trigger", "c_id_insert")
    ), dict(v)
    assert v["s_usage"] is True and v["s_update"] is False
    # 7. ADR-048 timeouts (pg_settings reports milliseconds): 30 s statement, 60 s idle in transaction
    assert v["statement_timeout_ms"] == "30000"
    assert v["idle_timeout_ms"] == "60000"


# ---- the migration's allowlist function, called directly ----

ALLOWLIST_SQLSTATE = "OF002"


async def check_allowlist(conn: AsyncConnection, role: str) -> None:
    """Run public.ofo_assert_app_role_allowlist(role, 'post'); its refusal becomes an AssertionError with its text."""
    try:
        async with conn.begin_nested():
            await conn.execute(text("SELECT public.ofo_assert_app_role_allowlist(:r, 'post')"), {"r": role})
    except DBAPIError as exc:
        assert _sqlstate(exc) == ALLOWLIST_SQLSTATE, f"unexpected error {_sqlstate(exc)}: {exc}"
        raise AssertionError(str(exc.orig)) from None


async def _allowlist_after(admin_engine: AsyncEngine, app_engine: AsyncEngine, mutation_sql: list[str], match: str) -> None:
    role = app_engine.url.username
    assert role and re.fullmatch(r"[a-z_][a-z0-9_]*", role), role
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            db = (await conn.execute(text("SELECT current_database()"))).scalar_one()
            owner = (
                await conn.execute(
                    text("SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'ledger_entries'")
                )
            ).scalar_one()
            assert re.fullmatch(r"[a-z_][a-z0-9_]*", db) and re.fullmatch(r"[a-z_][a-z0-9_]*", owner), (db, owner)
            await check_allowlist(conn, role)  # holds before the mutation
            for sql in mutation_sql:
                await conn.execute(text(sql.format(role=role, db=db, owner=owner)))
            with pytest.raises(AssertionError, match=match):
                await check_allowlist(conn, role)
        finally:
            await trans.rollback()


async def test_allowlist_holds_on_the_real_setup(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn, conn.begin():
        await check_allowlist(conn, app_engine.url.username)


async def test_allowlist_refuses_role_owning_the_database(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _allowlist_after(admin_engine, app_engine, ['ALTER DATABASE "{db}" OWNER TO "{role}"'], "owns the database")


async def test_allowlist_refuses_create_on_public(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _allowlist_after(
        admin_engine, app_engine, ['GRANT CREATE ON SCHEMA public TO "{role}"'], "has CREATE on schema public"
    )


async def test_allowlist_refuses_temporary(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _allowlist_after(
        admin_engine, app_engine, ['GRANT TEMPORARY ON DATABASE "{db}" TO "{role}"'], "has TEMPORARY on the database"
    )


async def test_allowlist_refuses_membership_of_the_table_owner(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _allowlist_after(
        admin_engine, app_engine, ['GRANT "{owner}" TO "{role}"'], "is a member of another role"
    )


async def test_temp_table_cannot_be_created_to_shadow_the_ledger(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await _expect_refused(conn, "CREATE TEMP TABLE ledger_entries (id BIGINT)", None, INSUFFICIENT_PRIVILEGE)


async def test_insert_naming_id_is_refused(app_engine: AsyncEngine) -> None:
    """INSERT is granted per column without id: the caller can never choose an id."""
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        await _expect_refused(
            conn,
            "INSERT INTO public.ledger_entries (id, kind, event_at, payload) "
            "VALUES (999999999, :k, :e, CAST('{}' AS jsonb))",
            {"k": _kind(), "e": now},
            INSUFFICIENT_PRIVILEGE,
        )


@pytest.mark.parametrize("seconds", [55, -55])
async def test_boundary_event_within_window_is_accepted(app_engine: AsyncEngine, seconds: int) -> None:
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        row_id, _ = await _insert(conn, _kind(), now + timedelta(seconds=seconds))
        assert row_id > 0


@pytest.mark.parametrize("seconds", [65, -65])
async def test_boundary_event_outside_window_is_refused(app_engine: AsyncEngine, seconds: int) -> None:
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        await _expect_insert_refused(conn, now + timedelta(seconds=seconds))


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
        count = (await conn.execute(text("SELECT count(*) FROM public.ledger_entries WHERE kind = :k"), {"k": kind})).scalar_one()
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
        await _expect_refused(conn, "TRUNCATE public.ledger_entries", None, INSUFFICIENT_PRIVILEGE)


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
    inserts = [s for s in statements if re.match(r"\s*INSERT INTO (public\.)?ledger_entries\b", s, re.IGNORECASE)]
    assert len(inserts) == 1, statements
    columns = re.search(r"\(([^)]*)\)", inserts[0]).group(1)
    sent = [c.strip() for c in columns.split(",")]
    assert "recorded_at" not in sent and "id" not in sent, inserts[0]


async def test_repository_refuses_naive_event_at_without_touching_the_db() -> None:
    with pytest.raises(ValueError):
        await ledger.append(None, "k", datetime(2026, 10, 2, 9, 0), {})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [{"amount": 12.5}, {"legs": [{"premium": "1.00"}, {"premium": 0.05}]}, {"nested": {"deep": (1, 2.0)}}],
)
async def test_repository_refuses_float_anywhere_in_payload_without_touching_the_db(payload: dict) -> None:
    """Money is never float (ADR-008): a float at any depth is refused before any SQL is sent."""
    aware = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    with pytest.raises(TypeError, match="float"):
        await ledger.append(None, "k", aware, payload)  # type: ignore[arg-type]


async def test_repository_float_check_accepts_decimal_strings_and_tagged_form() -> None:
    ledger._reject_floats({"amount": "12.50", "fee": {"$decimal": "0.05"}, "qty": 75, "ok": True, "none": None})


# ---- mutation tests: weaken the guard (rolled back) and show the checks turn red ----


async def _as_app_role_after(
    admin_engine: AsyncEngine, app_engine: AsyncEngine, mutation_sql: list[str], check, match: str
) -> None:
    """Weaken the guard, act as the app role, and require `check` to fail for the intended reason (`match`)."""
    role = app_engine.url.username
    assert role and re.fullmatch(r"[a-z_][a-z0-9_]*", role), role
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in mutation_sql:
                await conn.execute(text(sql.format(role=role)))
            await conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            with pytest.raises(AssertionError, match=match):
                await check(conn)
        finally:
            await trans.rollback()


async def test_mutation_dropping_the_trigger_turns_a_and_b_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    drop = [f"DROP TRIGGER {TRIGGER} ON public.ledger_entries"]
    await _as_app_role_after(
        admin_engine, app_engine, drop, check_caller_recorded_at_is_ignored, match="the caller's recorded_at was stored"
    )
    await _as_app_role_after(
        admin_engine, app_engine, drop, check_two_minutes_off_refused, match=r"insert with event_at=.* was accepted"
    )


async def test_mutation_granting_update_turns_c_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _as_app_role_after(
        admin_engine, app_engine, ['GRANT UPDATE ON public.ledger_entries TO "{role}"'],
        check_update_refused,
        match=r"not refused: UPDATE public\.ledger_entries",
    )
    await _as_app_role_after(
        admin_engine, app_engine, ['GRANT DELETE ON public.ledger_entries TO "{role}"'],
        check_delete_refused,
        match=r"not refused: DELETE FROM public\.ledger_entries",
    )


async def test_mutation_making_app_role_owner_turns_d_red(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await _as_app_role_after(
        admin_engine, app_engine, ['ALTER TABLE public.ledger_entries OWNER TO "{role}"'],
        check_disable_trigger_refused,
        match=r"not refused: ALTER TABLE public\.ledger_entries DISABLE TRIGGER ledger_entries_trusted_clock",
    )


async def test_guard_still_in_place_after_mutation_tests(app_engine: AsyncEngine) -> None:
    """The mutations were rolled back: the real guard still holds."""
    async with app_engine.connect() as conn, conn.begin():
        await check_caller_recorded_at_is_ignored(conn)
        await check_update_refused(conn)
