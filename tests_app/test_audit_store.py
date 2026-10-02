"""W-052: the hash-chained audit log stored in PostgreSQL (REQ-064 AC-2, REQ-063 AC-5).

Spec basis: REQ-064 AC-2 "Audit and timeline records are append-only."; REQ-063 AC-5 (per-event-type field
ALLOWLIST: "each event type declares the fields it may carry; anything else is dropped before storage"); ADR-023
Q256 ("the clock-skew window is 60 seconds, both ways."); ADR-048 (non-superuser application role, real PostgreSQL).

Database tests run as the application role (TEST_DATABASE_URL); tampering and mutations run as the owner
(TEST_ADMIN_DATABASE_URL) inside a transaction that is always rolled back. The audit chain is one shared log, so
committed appends from earlier tests stay; every check reads the chain as it is and compares only its own rows.
Expected values come from the spec, not the code: 9 declared types of 33, 60 s window, SQLSTATE 42501 (insufficient
privilege), Decimal('1365.00') keeps its two decimal places.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditChainError
from ofo.audit.models import GENESIS_HASH
from ofo_app import audit_store
from ofo_app.audit_allowlist import ALLOWLIST, PayloadShapeError, UndeclaredEventType, filter_payload
from ofo_app.audit_store import AuditStoreError, append, decode_payload, encode_payload, load_log

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
CLOCK_SQLSTATE = "OF001"
LINK_SQLSTATE = "OF003"
ALLOWLIST_SQLSTATE = "OF002"
PRICE = Decimal("1365.00")

DECLARED = {
    EventType.ENTITLEMENT_CHANGED, EventType.TRIAL_STARTED, EventType.TRIAL_EXPIRED,
    EventType.DIRECT_CUSTOMER_ELIGIBILITY_GRANTED, EventType.DIRECT_CUSTOMER_ELIGIBILITY_REVOKED,
    EventType.REFERRAL_REWARD_GRANTED, EventType.SUBSCRIPTION_STARTED, EventType.SUBSCRIPTION_EXPIRED,
    EventType.ADMIN_CHANGE_RECORDED,
}
UNDECLARED = sorted(set(EventType) - DECLARED, key=lambda e: e.value)

ROOT = Path(__file__).resolve().parents[1]


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0002_audit_store.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0002_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


def _cid() -> str:
    return f"test-{uuid.uuid4().hex}"


async def _db_clock(conn: AsyncConnection) -> datetime:
    return (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def _expect_refused(conn: AsyncConnection, sql: str, params: dict | None, expected: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql), params or {})
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == expected, f"refused with SQLSTATE {got}, expected {expected}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


async def _subscription(conn: AsyncConnection, **extra) -> audit_store.StoredEvent:
    now = await _db_clock(conn)
    return await append(
        conn,
        EventType.SUBSCRIPTION_STARTED,
        actor="admin-1",
        timestamp=now,
        correlation_id=_cid(),
        payload={"platform_user_id": "u-1", "plan": "pro", "price": PRICE, "starts_at": now, **extra},
    )


# ---------------------------------------------------------------------------------------------------------------
# Pure checks (no database): allowlist, fail-closed encoding, exact Decimal
# ---------------------------------------------------------------------------------------------------------------


def test_exactly_the_nine_non_broker_types_are_declared() -> None:
    assert set(ALLOWLIST) == DECLARED
    assert len(DECLARED) == 9 and len(UNDECLARED) == 24 and len(EventType) == 33


def test_database_event_type_check_equals_the_python_allowlist() -> None:
    assert set(_migration().DECLARED_EVENT_TYPES) == {e.value for e in ALLOWLIST}


def test_migration_genesis_equals_ofo_audit_genesis() -> None:
    assert _migration().GENESIS_HASH == GENESIS_HASH


@pytest.mark.parametrize("event_type", UNDECLARED, ids=lambda e: e.value)
async def test_undeclared_type_refused_before_any_sql(event_type: EventType) -> None:
    """conn=None: a refusal that sent SQL would raise AttributeError, not UndeclaredEventType."""
    with pytest.raises(UndeclaredEventType, match=event_type.value):
        await append(
            None, event_type, actor="a", timestamp=datetime.now(UTC), correlation_id="c", payload={}
        )


def test_extra_fields_dropped_at_every_depth() -> None:
    kept = filter_payload(
        EventType.ENTITLEMENT_CHANGED,
        {
            "action": "entitlement_status",
            "client_id": "AB1234",
            "unlisted_field": "dropped",
            "before": {"client_id": "AB1234", "entitlement_status": "limited", "unlisted_inner": "dropped"},
            "after": None,
        },
    )
    assert kept == {
        "action": "entitlement_status",
        "client_id": "AB1234",
        "before": {"client_id": "AB1234", "entitlement_status": "limited"},
        "after": None,
    }


def test_mapping_in_a_scalar_field_is_refused() -> None:
    with pytest.raises(PayloadShapeError, match="payload.plan"):
        filter_payload(EventType.SUBSCRIPTION_STARTED, {"plan": {"anything": "x"}})
    with pytest.raises(PayloadShapeError, match=r"payload.dropped_tradingsymbols\[0\]"):
        filter_payload(EventType.ADMIN_CHANGE_RECORDED, {"dropped_tradingsymbols": [{"x": 1}]})


@pytest.mark.parametrize(
    "value, match",
    [
        (1365.0, "float"),
        (Decimal("NaN"), "non-finite"),
        (Decimal("Infinity"), "non-finite"),
        ("a\x00b", "NUL"),
        ("\ud800", "surrogate"),
        (datetime(2026, 10, 2, 9, 0), "naive"),
        ({1, 2}, "set"),
        (b"bytes", "bytes"),
    ],
)
def test_values_that_cannot_round_trip_are_refused(value, match: str) -> None:
    with pytest.raises(AuditStoreError, match=match):
        encode_payload({"plan": value})


def test_decimal_scale_and_datetime_survive_the_stored_form() -> None:
    moment = datetime(2026, 10, 2, 9, 0, 0, 123456, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    stored = encode_payload({"price": PRICE, "starts_at": moment, "n": 75, "flags": [True, None]})
    assert '{"$decimal":"1365.00"}' in stored
    back = decode_payload(json.loads(stored))
    assert str(back["price"]) == "1365.00"
    assert back["starts_at"] == moment and back["starts_at"].tzinfo is not None
    assert back["n"] == 75 and back["flags"] == [True, None]


@pytest.mark.parametrize(
    "stored, match",
    [
        ({"x": {"$decimal": "1", "y": 2}}, "one-key tag"),
        ({"x": {"$money": "1"}}, "unknown tag"),
        ({"x": {"$decimal": 1}}, "non-string"),
        ({"x": {"$decimal": "1e1"}}, "round-trip"),
        ({"x": {"$datetime": "2026-10-02T09:00:00"}}, "naive"),
    ],
)
def test_decoding_fails_closed_on_unexpected_tags(stored: dict, match: str) -> None:
    with pytest.raises(AuditStoreError, match=match):
        decode_payload(stored)


# ---------------------------------------------------------------------------------------------------------------
# Checks over a connection (each used by a real test and, where named, by a mutation test)
# ---------------------------------------------------------------------------------------------------------------


async def check_anchor_update_refused(conn: AsyncConnection) -> None:
    await _expect_refused(conn, "UPDATE public.audit_anchor SET event_count = 0 WHERE id = 1", None, INSUFFICIENT_PRIVILEGE)


async def check_concurrent_appends_are_one_linear_chain(app_engine: AsyncEngine) -> None:
    """Two appends overlap: A holds its transaction open while B starts; both must land, B linked to A."""
    async with app_engine.connect() as conn_a, app_engine.connect() as conn_b:
        trans_a = await conn_a.begin()
        a = await _subscription(conn_a)

        async def run_b() -> audit_store.StoredEvent:
            async with conn_b.begin():
                return await _subscription(conn_b)

        task_b = asyncio.create_task(run_b())
        await asyncio.sleep(0.5)  # B is now waiting (on the lock, or on the anchor row without it)
        assert not task_b.done(), "B finished while A still held its transaction open"
        await trans_a.commit()
        try:
            b = await task_b
        except DBAPIError as exc:
            raise AssertionError(f"concurrent append failed: SQLSTATE {_sqlstate(exc)}: {exc}") from None
    assert b.seq == a.seq + 1, (a.seq, b.seq)
    assert b.event.previous_hash == a.event.hash
    async with app_engine.connect() as conn:
        log, anchor = await load_log(conn)
    assert log.events[a.seq - 1].hash == a.event.hash and log.events[b.seq - 1].hash == b.event.hash
    assert log.verify(anchor).ok


# ---------------------------------------------------------------------------------------------------------------
# Core proof, as the application role
# ---------------------------------------------------------------------------------------------------------------


async def test_core_three_events_reload_on_a_new_connection_and_verify(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        stored = [
            await append(
                conn, EventType.SUBSCRIPTION_STARTED, actor="admin-1", timestamp=now, correlation_id=_cid(),
                payload={"platform_user_id": "u-1", "plan": "pro", "price": PRICE, "starts_at": now},
            ),
            await append(
                conn, EventType.TRIAL_STARTED, actor="system", timestamp=now, correlation_id=_cid(),
                payload={"platform_user_id": "u-2", "starts_at": now, "ends_at": now + timedelta(days=7)},
            ),
            await append(
                conn, EventType.ENTITLEMENT_CHANGED, actor="admin-1", timestamp=now, correlation_id=_cid(),
                payload={"action": "entitlement_status", "client_id": "AB1234",
                         "before": {"entitlement_status": "limited"}, "after": {"entitlement_status": "pro"}},
            ),
        ]
    # the in-memory chain links
    assert [s.seq for s in stored] == [stored[0].seq, stored[0].seq + 1, stored[0].seq + 2]
    assert stored[1].event.previous_hash == stored[0].event.hash
    assert stored[2].event.previous_hash == stored[1].event.hash

    async with app_engine.connect() as fresh:  # NullPool: a new server connection
        log, anchor = await load_log(fresh)
    assert log.verify(anchor).ok
    assert anchor.count >= stored[-1].seq
    for s in stored:
        reloaded = log.events[s.seq - 1]
        assert reloaded.hash == s.event.hash
        assert reloaded == s.event
    price = log.events[stored[0].seq - 1].payload["price"]
    assert isinstance(price, Decimal) and str(price) == "1365.00"
    assert log.events[stored[0].seq - 1].payload["starts_at"] == now


@pytest.mark.parametrize(
    "column, sql",
    [
        ("payload", "UPDATE public.audit_events SET payload = jsonb_set(payload, '{plan}', '\"prp\"') WHERE seq = :s"),
        ("actor", "UPDATE public.audit_events SET actor = 'admin-2' WHERE seq = :s"),
        ("timestamp", 'UPDATE public.audit_events SET "timestamp" = "timestamp" + interval \'1 microsecond\' WHERE seq = :s'),
        ("hash", "UPDATE public.audit_events SET hash = overlay(hash placing (CASE WHEN substr(hash, 1, 1) = 'a' "
                 "THEN 'b' ELSE 'a' END) from 1 for 1) WHERE seq = :s"),
        ("previous_hash", "UPDATE public.audit_events SET previous_hash = overlay(previous_hash placing "
                          "(CASE WHEN substr(previous_hash, 1, 1) = 'a' THEN 'b' ELSE 'a' END) from 1 for 1) WHERE seq = :s"),
    ],
)
async def test_owner_changing_one_value_fails_verification_naming_the_row(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, column: str, sql: str
) -> None:
    async with app_engine.connect() as conn, conn.begin():
        target = await _subscription(conn)
        await _subscription(conn)  # a row after it, so the target is not the tail
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            changed = (await conn.execute(text(sql), {"s": target.seq})).rowcount
            assert changed == 1, column
            with pytest.raises(AuditChainError, match=rf"seq={target.seq}\b"):
                await load_log(conn)
        finally:
            await trans.rollback()


async def test_owner_deleting_the_last_row_fails_against_the_anchor(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    async with app_engine.connect() as conn, conn.begin():
        last = await _subscription(conn)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("DELETE FROM public.audit_events WHERE seq = (SELECT max(seq) FROM public.audit_events)"))
            with pytest.raises(AuditChainError, match=rf"seq={last.seq}\b"):
                await load_log(conn)
        finally:
            await trans.rollback()


async def test_two_concurrent_appends_produce_one_linear_chain(app_engine: AsyncEngine) -> None:
    await check_concurrent_appends_are_one_linear_chain(app_engine)


# ---- allowlist through the database ----


async def test_extra_field_dropped_before_storage_and_hash_covers_the_stored_form(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            s = await _subscription(conn, unlisted_field="dropped")
            assert "unlisted_field" not in s.event.payload
            raw = (await conn.execute(text("SELECT payload::text FROM public.audit_events WHERE seq = :s"), {"s": s.seq})).scalar_one()
            assert "unlisted_field" not in json.loads(raw)
            log, anchor = await load_log(conn)
            assert log.events[s.seq - 1].hash == s.event.hash and log.verify(anchor).ok
        finally:
            await trans.rollback()


async def test_undeclared_type_refused_with_no_row_written(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        before = (await conn.execute(text("SELECT count(*) FROM public.audit_events"))).scalar_one()
        anchor_before = await audit_store.read_anchor(conn)
        with pytest.raises(UndeclaredEventType):
            await append(conn, EventType.ORDER_SUBMITTED, actor="a", timestamp=await _db_clock(conn),
                         correlation_id=_cid(), payload={"order_id": "1"})
        after = (await conn.execute(text("SELECT count(*) FROM public.audit_events"))).scalar_one()
        assert after == before and await audit_store.read_anchor(conn) == anchor_before


async def test_database_refuses_an_undeclared_type_inserted_directly(app_engine: AsyncEngine) -> None:
    """Second layer: a raw INSERT bypassing the Python store still cannot store a broker/order event."""
    async with app_engine.connect() as conn, conn.begin():
        head = await audit_store.read_anchor(conn)
        await _expect_refused(
            conn,
            'INSERT INTO public.audit_events (seq, event_type, actor, "timestamp", correlation_id, payload, previous_hash, hash) '
            "VALUES (:seq, 'order_submitted', 'a', clock_timestamp(), 'c', '{}'::jsonb, :prev, :h)",
            {"seq": head.count + 1, "prev": head.last_hash, "h": "f" * 64},
            CHECK_VIOLATION,
        )


# ---- database guards: clock, linkage, privileges ----


@pytest.mark.parametrize("minutes", [2, -2])
async def test_event_time_two_minutes_off_is_refused(app_engine: AsyncEngine, minutes: int) -> None:
    async with app_engine.connect() as conn, conn.begin():
        now = await _db_clock(conn)
        with pytest.raises(DBAPIError) as info:
            async with conn.begin_nested():
                await append(conn, EventType.TRIAL_EXPIRED, actor="system", timestamp=now + timedelta(minutes=minutes),
                             correlation_id=_cid(), payload={"platform_user_id": "u-1"})
        assert _sqlstate(info.value) == CLOCK_SQLSTATE


async def test_recorded_at_is_the_database_clock(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            before = await _db_clock(conn)
            s = await _subscription(conn)
            after = await _db_clock(conn)
            stamp = (await conn.execute(text("SELECT recorded_at FROM public.audit_events WHERE seq = :s"), {"s": s.seq})).scalar_one()
            assert before <= stamp <= after
        finally:
            await trans.rollback()


async def test_row_not_extending_the_anchor_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        head = await audit_store.read_anchor(conn)
        insert = (
            'INSERT INTO public.audit_events (seq, event_type, actor, "timestamp", correlation_id, payload, previous_hash, hash) '
            "VALUES (:seq, 'trial_started', 'a', clock_timestamp(), 'c', '{}'::jsonb, :prev, :h)"
        )
        await _expect_refused(conn, insert, {"seq": head.count + 2, "prev": head.last_hash, "h": "e" * 64}, LINK_SQLSTATE)
        await _expect_refused(conn, insert, {"seq": head.count + 1, "prev": "d" * 64, "h": "e" * 64}, LINK_SQLSTATE)


async def test_app_role_cannot_update_or_delete_events_or_move_the_anchor(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_anchor_update_refused(conn)
        await _expect_refused(conn, "UPDATE public.audit_events SET actor = 'x'", None, INSUFFICIENT_PRIVILEGE)
        await _expect_refused(conn, "DELETE FROM public.audit_events", None, INSUFFICIENT_PRIVILEGE)
        await _expect_refused(conn, "DELETE FROM public.audit_anchor", None, INSUFFICIENT_PRIVILEGE)
        await _expect_refused(conn, "INSERT INTO public.audit_anchor (id, event_count, last_hash) VALUES (2, 0, :h)",
                              {"h": "0" * 64}, INSUFFICIENT_PRIVILEGE)
        await _expect_refused(conn, "ALTER TABLE public.audit_events DISABLE TRIGGER ALL", None, INSUFFICIENT_PRIVILEGE)


async def test_repeatable_read_append_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        await conn.execution_options(isolation_level="REPEATABLE READ")
        async with conn.begin():
            with pytest.raises(AuditStoreError, match="READ COMMITTED"):
                await _subscription(conn)


async def test_allowlist_holds_with_the_audit_tables(admin_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn, conn.begin():
        await check_allowlist(conn, app_engine.url.username)


# ---------------------------------------------------------------------------------------------------------------
# Mutation tests: weaken one guard (rolled back) and show the matching check turns red
# ---------------------------------------------------------------------------------------------------------------


async def check_allowlist(conn: AsyncConnection, role: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text("SELECT public.ofo_assert_app_role_allowlist(:r, 'post')"), {"r": role})
    except DBAPIError as exc:
        assert _sqlstate(exc) == ALLOWLIST_SQLSTATE, f"unexpected error {_sqlstate(exc)}: {exc}"
        raise AssertionError(str(exc.orig)) from None


def _role(app_engine: AsyncEngine) -> str:
    role = app_engine.url.username
    assert role and re.fullmatch(r"[a-z_][a-z0-9_]*", role), role
    return role


async def test_mutation_removing_the_advisory_lock_turns_concurrency_red(
    app_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_lock(conn) -> None:
        return None

    monkeypatch.setattr(audit_store, "_take_lock", no_lock)
    with pytest.raises(AssertionError, match=rf"concurrent append failed: SQLSTATE {LINK_SQLSTATE}"):
        await check_concurrent_appends_are_one_linear_chain(app_engine)


async def test_mutation_granting_update_on_the_anchor_turns_anchor_check_red(
    admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    role = _role(app_engine)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f'GRANT UPDATE ON public.audit_anchor TO "{role}"'))
            with pytest.raises(AssertionError, match="has UPDATE on audit_anchor"):
                await check_allowlist(conn, role)
            await conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            with pytest.raises(AssertionError, match=r"not refused: UPDATE public\.audit_anchor"):
                await check_anchor_update_refused(conn)
        finally:
            await trans.rollback()


@pytest.mark.parametrize(
    "grant, match",
    [
        ('GRANT INSERT ON public.audit_events TO "{role}"', "has table-wide INSERT on audit_events"),
        ('GRANT INSERT (recorded_at) ON public.audit_events TO "{role}"', "has INSERT on audit_events column recorded_at"),
        ('GRANT DELETE ON public.audit_events TO "{role}"', "has DELETE on audit_events"),
        ('GRANT UPDATE (actor) ON public.audit_events TO "{role}"', "has column UPDATE on audit_events"),
        ('REVOKE INSERT (hash) ON public.audit_events FROM "{role}"', "lacks INSERT on audit_events column hash"),
        ("GRANT EXECUTE ON FUNCTION public.audit_events_advance_anchor() TO \"{role}\"",
         "has EXECUTE on public.audit_events_advance_anchor"),
        ("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_advance_anchor",
         "trigger audit_events_advance_anchor is missing or not enabled"),
    ],
)
async def test_mutation_widening_audit_privileges_is_refused_by_the_allowlist(
    admin_engine: AsyncEngine, app_engine: AsyncEngine, grant: str, match: str
) -> None:
    role = _role(app_engine)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await check_allowlist(conn, role)
            await conn.execute(text(grant.format(role=role)))
            with pytest.raises(AssertionError, match=match):
                await check_allowlist(conn, role)
        finally:
            await trans.rollback()


async def test_real_log_still_verifies_after_all_mutations(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        log, anchor = await load_log(conn)
    assert log.verify(anchor).ok and anchor.count == len(log.events)
