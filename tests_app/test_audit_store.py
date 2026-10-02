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
from ofo.audit.models import GENESIS_HASH, AuditEvent, canonical_json
from ofo_app import audit_store
from ofo_app.audit_allowlist import (
    ALLOWLIST,
    PayloadShapeError,
    UndeclaredEventType,
    allowlist_spec,
    filter_payload,
)
from ofo_app.audit_store import (
    AuditStoreError,
    append,
    canonical_text,
    decode_payload,
    encode_payload,
    load_log,
    read_anchor,
)

INSUFFICIENT_PRIVILEGE = "42501"
CLOCK_SQLSTATE = "OF001"
LINK_SQLSTATE = "OF003"
PAYLOAD_SQLSTATE = "OF004"
HASH_SQLSTATE = "OF005"
ALLOWLIST_SQLSTATE = "OF002"
COLUMNS = 'seq, event_type, actor, "timestamp", correlation_id, payload, previous_hash, hash, canonical'
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


def _values(suffix: str = "") -> str:
    s = suffix
    return (
        f"(:seq{s}, :event_type{s}, :actor{s}, :ts{s}, :cid{s}, CAST(:payload{s} AS jsonb), :prev{s}, :hash{s}, "
        f":canonical{s})"
    )


RAW_INSERT = f"INSERT INTO public.audit_events ({COLUMNS}) VALUES {_values()}"


def _raw(event: AuditEvent, seq: int, suffix: str = "", **override) -> dict:
    """Parameters for a raw INSERT of `event` (bypassing the Python store), optionally with columns overridden."""
    params = {
        "seq": seq, "event_type": event.event_type.value, "actor": event.actor, "ts": event.timestamp,
        "cid": event.correlation_id, "payload": canonical_json(event.payload), "prev": event.previous_hash,
        "hash": event.hash, "canonical": canonical_text(event),
    }
    params.update(override)
    return {f"{key}{suffix}": value for key, value in params.items()}


async def _next_event(
    conn: AsyncConnection, event_type: EventType = EventType.SUBSCRIPTION_STARTED, payload: dict | None = None,
    previous_hash: str | None = None,
):
    head = await read_anchor(conn)
    event = AuditEvent(
        event_type=event_type, actor="admin-1", timestamp=await _db_clock(conn), correlation_id=_cid(),
        payload=payload if payload is not None else {"plan": "pro"},
        previous_hash=previous_hash or head.last_hash,
    )
    return head, event


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


def test_canonical_text_is_exactly_what_ofo_audit_hashes() -> None:
    import hashlib

    event = AuditEvent(
        event_type=EventType.SUBSCRIPTION_STARTED, actor="admin-1",
        timestamp=datetime(2026, 10, 2, 9, 0, 0, 5, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        correlation_id="c-1", payload={"price": PRICE, "plan": "proé"},
    )
    assert hashlib.sha256(canonical_text(event).encode("utf-8")).hexdigest() == event.hash


def test_allowlist_block_shape_guard_fails_closed() -> None:
    migration = _migration()
    previous = migration.previous_allowlist_sql()
    extended = migration.extend_allowlist(previous)
    assert migration.ALLOWLIST_BLOCK_MARKER in extended and extended.count("CREATE OR REPLACE FUNCTION") == 1
    with pytest.raises(RuntimeError, match="changed shape"):
        migration.extend_allowlist(previous.replace("    IF cardinality(problems) > 0 THEN\n", "", 1))
    with pytest.raises(RuntimeError, match="changed shape"):
        migration.extend_allowlist(extended)  # already holds this block: never added twice
    with pytest.raises(RuntimeError, match="changed shape"):
        migration.extend_allowlist(previous + previous)  # two function headers


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


@pytest.mark.parametrize(
    "event_type, payload",
    [
        (EventType.SUBSCRIPTION_STARTED, {"plan": "pro", "unlisted_field": "x"}),
        (EventType.ENTITLEMENT_CHANGED, {"before": {"client_id": "AB1234", "unlisted_inner": "x"}}),
        (EventType.SUBSCRIPTION_STARTED, {"plan": {"anything": "x"}}),
        (EventType.SUBSCRIPTION_STARTED, '{"price": {"$decimal": "1", "extra": "x"}}'),
        (EventType.ADMIN_CHANGE_RECORDED, {"dropped_tradingsymbols": [{"x": 1}]}),
        (EventType.SUBSCRIPTION_STARTED, {"price": 1365.5}),
        (EventType.ORDER_SUBMITTED, {}),
    ],
    ids=["extra-top-level", "extra-nested", "object-in-scalar", "fake-tag", "object-in-list", "float", "undeclared"],
)
async def test_raw_insert_outside_the_allowlist_is_refused(
    app_engine: AsyncEngine, event_type: EventType, payload: dict | str
) -> None:
    """Storage-level allowlist: a raw INSERT with a correct hash, canonical text and link is still refused. A str
    payload is raw JSON that ofo.audit itself would refuse to build (a "$" key), sent as the payload column (the
    allowlist check runs before the hash check, so OF004 is expected either way)."""
    async with app_engine.connect() as conn, conn.begin():
        if isinstance(payload, str):
            head, event = await _next_event(conn, event_type, {})
            params = _raw(event, head.count + 1, payload=payload)
        else:
            head, event = await _next_event(conn, event_type, payload)
            params = _raw(event, head.count + 1)
        await _expect_refused(conn, RAW_INSERT, params, PAYLOAD_SQLSTATE)


async def check_clock_refused(conn: AsyncConnection) -> None:
    """An event 2 minutes off the database clock is refused (OF001), both ways."""
    for minutes in (2, -2):
        now = await _db_clock(conn)
        try:
            async with conn.begin_nested():
                await append(conn, EventType.TRIAL_EXPIRED, actor="system", timestamp=now + timedelta(minutes=minutes),
                             correlation_id=_cid(), payload={"platform_user_id": "u-1"})
        except DBAPIError as exc:
            assert _sqlstate(exc) == CLOCK_SQLSTATE, f"refused with {_sqlstate(exc)}, expected {CLOCK_SQLSTATE}: {exc}"
            continue
        raise AssertionError(f"not refused: event {minutes} minutes off the database clock")


async def check_bogus_hash_refused(conn: AsyncConnection) -> None:
    """A correct row whose hash is 'e'*64 (not sha256(canonical)) is refused (OF005)."""
    head, event = await _next_event(conn)
    await _expect_refused(conn, RAW_INSERT, _raw(event, head.count + 1, hash="e" * 64), HASH_SQLSTATE)


async def test_event_time_two_minutes_off_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_clock_refused(conn)


async def test_raw_insert_with_a_bogus_hash_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        await check_bogus_hash_refused(conn)


@pytest.mark.parametrize("column", ["actor", "cid", "prev_in_canonical", "payload", "timestamp", "not-json"])
async def test_raw_insert_whose_canonical_text_does_not_match_the_row_is_refused(
    app_engine: AsyncEngine, column: str
) -> None:
    """hash = sha256(canonical) holds, but canonical describes a different row: refused (OF005)."""
    import hashlib

    async with app_engine.connect() as conn, conn.begin():
        head, event = await _next_event(conn)
        doc = json.loads(canonical_text(event))
        if column == "actor":
            doc["actor"] = "someone-else"
        elif column == "cid":
            doc["correlation_id"] = "other"
        elif column == "prev_in_canonical":
            doc["previous_hash"] = "d" * 64
        elif column == "payload":
            doc["payload"] = {"plan": "basic"}
        elif column == "timestamp":
            doc["timestamp"] = "2020-01-01T00:00:00+00:00"
        canonical = "not json" if column == "not-json" else json.dumps(doc, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        await _expect_refused(
            conn, RAW_INSERT, _raw(event, head.count + 1, hash=digest, canonical=canonical), HASH_SQLSTATE
        )


async def test_self_consistent_non_canonical_text_is_stored_but_load_log_names_the_row(app_engine: AsyncEngine) -> None:
    """Pinned behaviour: the database cannot check canonical FORM. Text with spaces and its true SHA-256 is accepted
    at insert; load_log then refuses the log naming that seq. Rolled back, so the shared chain stays clean."""
    import hashlib

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head, event = await _next_event(conn)
            spaced = json.dumps(json.loads(canonical_text(event)), sort_keys=True)  # ", " and ": " separators
            assert spaced != canonical_text(event)
            digest = hashlib.sha256(spaced.encode("utf-8")).hexdigest()
            await conn.execute(text(RAW_INSERT), _raw(event, head.count + 1, hash=digest, canonical=spaced))
            with pytest.raises(AuditChainError, match=rf"seq={head.count + 1}: stored canonical text is not the canonical form"):
                await load_log(conn)
        finally:
            await trans.rollback()


async def test_load_log_refuses_a_stored_payload_outside_the_allowlist(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    """Second layer on read: with the insert guard switched off by the owner (rolled back), a row carrying an
    undeclared field is named by load_log."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_link_and_clock"))
            head, event = await _next_event(conn, payload={"plan": "pro", "unlisted_field": "x"})
            await conn.execute(text(RAW_INSERT), _raw(event, head.count + 1))
            with pytest.raises(AuditChainError, match=rf"seq={head.count + 1}: stored payload holds fields outside"):
                await load_log(conn)
        finally:
            await trans.rollback()


async def test_row_not_extending_the_anchor_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn, conn.begin():
        head, event = await _next_event(conn)
        await _expect_refused(conn, RAW_INSERT, _raw(event, head.count + 2), LINK_SQLSTATE)
        _, stray = await _next_event(conn, previous_hash="d" * 64)
        await _expect_refused(conn, RAW_INSERT, _raw(stray, head.count + 1), LINK_SQLSTATE)


async def test_multi_row_insert_is_refused_at_its_second_row(app_engine: AsyncEngine) -> None:
    """Two correctly chained rows in one INSERT: AFTER ROW triggers run at the end of the statement, so the anchor
    has not moved when the second row is checked - refused (OF003), and nothing is stored."""
    async with app_engine.connect() as conn, conn.begin():
        head, first = await _next_event(conn)
        _, second = await _next_event(conn, previous_hash=first.hash)
        sql = f"INSERT INTO public.audit_events ({COLUMNS}) VALUES {_values('_1')}, {_values('_2')}"
        params = {**_raw(first, head.count + 1, "_1"), **_raw(second, head.count + 2, "_2")}
        await _expect_refused(conn, sql, params, LINK_SQLSTATE)
        assert await read_anchor(conn) == head


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


async def test_head_allowlist_function_holds_every_block(app_engine: AsyncEngine) -> None:
    """The live function (after every migration) still carries 0001's blocks and the audit store block."""
    async with app_engine.connect() as conn:
        body = (
            await conn.execute(text("SELECT pg_get_functiondef('public.ofo_assert_app_role_allowlist'::regproc)"))
        ).scalar_one()
    markers = ["-- 1. attributes", "-- 2. membership", "-- 3. ownership", "-- 4. database privileges",
               "-- 5. schema public", "-- 6. exactly SELECT", _migration().ALLOWLIST_BLOCK_MARKER]
    missing = [m for m in markers if m not in body]
    assert not missing, missing


async def test_database_payload_allowlist_equals_the_python_allowlist(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        stored = (await conn.execute(text("SELECT public.ofo_audit_payload_allowlist()::text"))).scalar_one()
    assert json.loads(stored) == allowlist_spec()


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
        ('REVOKE INSERT (canonical) ON public.audit_events FROM "{role}"',
         "lacks INSERT on audit_events column canonical"),
        ("GRANT EXECUTE ON FUNCTION public.ofo_assert_within_clock_window(timestamptz, timestamptz) TO \"{role}\"",
         "has EXECUTE on public.ofo_assert_within_clock_window"),
        ("GRANT EXECUTE ON FUNCTION public.audit_events_link_and_clock() TO \"{role}\"",
         "has EXECUTE on public.audit_events_link_and_clock"),
        ("GRANT EXECUTE ON FUNCTION public.ofo_audit_payload_conforms(jsonb, jsonb) TO \"{role}\"",
         "has EXECUTE on public.ofo_audit_payload_conforms"),
        ("ALTER FUNCTION public.audit_events_advance_anchor() SECURITY INVOKER",
         "function public.audit_events_advance_anchor is not SECURITY DEFINER"),
        ("ALTER FUNCTION public.audit_events_link_and_clock() RESET search_path",
         "function public.audit_events_link_and_clock does not pin search_path"),
        ("CREATE OR REPLACE TRIGGER audit_events_link_and_clock BEFORE INSERT ON public.audit_events "
         "FOR EACH ROW EXECUTE FUNCTION public.audit_events_advance_anchor()",
         "trigger audit_events_link_and_clock does not call public.audit_events_link_and_clock"),
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


async def test_mutation_disabling_the_before_trigger_turns_clock_and_hash_red(
    admin_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """Without the BEFORE trigger the app role can store an event 2 minutes off and a bogus hash. (Linkage itself
    stays guarded by the AFTER trigger's conditional anchor UPDATE, so a link check would not go red here.)"""
    role = _role(app_engine)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_link_and_clock"))
            with pytest.raises(AssertionError, match="trigger audit_events_link_and_clock is missing or not enabled"):
                await check_allowlist(conn, role)
            await conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            with pytest.raises(AssertionError, match="not refused: event 2 minutes off the database clock"):
                await check_clock_refused(conn)
            with pytest.raises(AssertionError, match=r"not refused: INSERT INTO public\.audit_events"):
                await check_bogus_hash_refused(conn)
        finally:
            await trans.rollback()


async def test_real_log_still_verifies_after_all_mutations(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        log, anchor = await load_log(conn)
    assert log.verify(anchor).ok and anchor.count == len(log.events)
