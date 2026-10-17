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
import dataclasses
import importlib.util
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditChainError
from ofo.audit.models import GENESIS_HASH, AuditEvent, canonical_json
from ofo.entitlements.engine import trial_grant
from ofo.entitlements.events import AuditNote
from ofo_app import audit_store, entitlement_store, order_audit
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
    # W-017: the two broker-reply types (declared from the real replies of 2026-10-16)
    EventType.BROKER_RESPONSE_RECORDED, EventType.EXECUTION_RECORDED,
    # W-103: the Execute route's stored plan (migration 0017)
    EventType.ORDER_PREPARED,
}
UNDECLARED = sorted(set(EventType) - DECLARED, key=lambda e: e.value)
#: Frozen: the types 0002 renders (every database at 0016). Never derived from the live allowlist.
PRE_0017_TYPES = {
    "entitlement_changed", "trial_started", "trial_expired", "direct_customer_eligibility_granted",
    "direct_customer_eligibility_revoked", "referral_reward_granted", "subscription_started", "subscription_expired",
    "broker_response_recorded", "execution_recorded", "admin_change_recorded",
}

ROOT = Path(__file__).resolve().parents[1]


def _migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0002_audit_store.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0002_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _order_prepared_migration():
    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0017_audit_order_prepared.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0017_test", path)
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


def test_exactly_the_nine_non_broker_two_broker_reply_and_order_prepared_types_are_declared() -> None:
    assert set(ALLOWLIST) == DECLARED
    assert len(DECLARED) == 12 and len(UNDECLARED) == 21 and len(EventType) == 33


def test_database_event_type_check_equals_the_python_allowlist() -> None:
    """0002 renders the 0016 state (every type but those a later revision declares); 0017 renders the full list."""
    assert set(_migration().DECLARED_EVENT_TYPES) == PRE_0017_TYPES
    assert set(_order_prepared_migration().AFTER) == {e.value for e in ALLOWLIST}


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
            None, event_type, actor="a", correlation_id="c", payload={}
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
                conn, EventType.SUBSCRIPTION_STARTED, actor="admin-1", correlation_id=_cid(),
                payload={"platform_user_id": "u-1", "plan": "pro", "price": PRICE, "starts_at": now},
            ),
            await append(
                conn, EventType.TRIAL_STARTED, actor="system", correlation_id=_cid(),
                payload={"platform_user_id": "u-2", "starts_at": now, "ends_at": now + timedelta(days=7)},
            ),
            await append(
                conn, EventType.ENTITLEMENT_CHANGED, actor="admin-1", correlation_id=_cid(),
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
            await append(conn, EventType.ORDER_SUBMITTED, actor="a", correlation_id=_cid(), payload={"order_id": "1"})
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
    """A raw row 2 minutes off the database clock (correct hash, canonical text and link) is refused (OF001), both
    ways. append() can no longer be given a time, so the database check is driven by a raw INSERT."""
    for minutes in (2, -2):
        head, event = await _next_event(conn, EventType.TRIAL_EXPIRED, {"platform_user_id": "u-1"})
        off = dataclasses.replace(event, timestamp=event.timestamp + timedelta(minutes=minutes))
        try:
            async with conn.begin_nested():
                await conn.execute(text(RAW_INSERT), _raw(off, head.count + 1))
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


# ---------------------------------------------------------------------------------------------------------------
# W-103: order_prepared (REQ-063 AC-5) and migration 0017
# ---------------------------------------------------------------------------------------------------------------

PREPARED = {"strategy_id": 1, "plan_number": 1, "action": "ENTRY", "tags": "OFS1V1L0"}


async def _prepared(conn: AsyncConnection, payload: dict) -> audit_store.StoredEvent:
    return await append(conn, EventType.ORDER_PREPARED, actor="u-1", correlation_id=_cid(), payload=payload)


async def _stored_payload(conn: AsyncConnection, seq: int) -> dict:
    raw = (await conn.execute(text("SELECT payload::text FROM public.audit_events WHERE seq = :s"), {"s": seq}))
    return json.loads(raw.scalar_one())


async def test_ac5_order_prepared_keeps_its_four_fields_drops_an_extra_and_refuses_bad_payloads(
    app_engine: AsyncEngine,
) -> None:
    """AC-5: {strategy_id, plan_number, action, tags, x} is stored WITHOUT x; {x} alone is refused
    (PayloadShapeError); plan_number 1.0 is refused by the store's float rule; neither refusal writes a row."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            stored = await _prepared(conn, {**PREPARED, "x": 1})
            assert stored.event.payload == PREPARED and await _stored_payload(conn, stored.seq) == PREPARED
            anchor = await audit_store.read_anchor(conn)
            with pytest.raises(PayloadShapeError, match="none is declared"):
                await _prepared(conn, {"x": 1})
            with pytest.raises(AuditStoreError, match="float"):
                await _prepared(conn, {**PREPARED, "plan_number": 1.0})
            assert await audit_store.read_anchor(conn) == anchor
            log, head = await load_log(conn)
            assert log.verify(head).ok
        finally:
            await trans.rollback()


async def test_ac5_live_event_type_check_names_exactly_the_declared_types(admin_engine: AsyncEngine) -> None:
    """AC-5: the database's event-type CHECK and the code's allowlist agree at head (both copies, not only one)."""
    async with admin_engine.connect() as conn:
        definition = (await conn.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'audit_events_event_type_check'"
        ))).scalar_one()
    assert set(re.findall(r"'([a-z_]+)'::text", definition)) == {e.value for e in ALLOWLIST}


async def _db_allowlist(conn: AsyncConnection) -> dict:
    return json.loads((await conn.execute(text("SELECT public.ofo_audit_payload_allowlist()::text"))).scalar_one())


async def test_ac5_0017_downgrade_removes_order_prepared_and_upgrade_restores_it(admin_engine: AsyncEngine) -> None:
    """AC-5: 0017 down -> the database allowlist and CHECK are 0016's (no order_prepared; an order_prepared append is
    refused by the database), the allowlist function's 'post' check passes; up -> equal to the code again and the
    append stores. Rolled back."""
    from _migration_replay import round_trip_sql  # noqa: PLC0415

    own_down, own_up, down, up = round_trip_sql("0017_audit_order_prepared.py")
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    migration = _order_prepared_migration()
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _db_allowlist(conn) == allowlist_spec()
            for sql in down:
                await conn.execute(text(sql))
            assert await _db_allowlist(conn) == migration.BEFORE
            assert "order_prepared" not in migration.BEFORE
            with pytest.raises(DBAPIError):
                async with conn.begin_nested():
                    await _prepared(conn, PREPARED)
            for sql in up:
                await conn.execute(text(sql))
            assert await _db_allowlist(conn) == allowlist_spec()
            assert (await _prepared(conn, PREPARED)).event.payload == PREPARED
        finally:
            await trans.rollback()


async def test_ac5_0017_downgrade_is_refused_while_an_order_prepared_event_is_stored(admin_engine: AsyncEngine) -> None:
    """AC-5: the audit store is append-only, so the downgrade refuses (nothing changes) once a row of the type
    exists."""
    from _migration_replay import recorded  # noqa: PLC0415

    own_down = recorded("0017_audit_order_prepared.py", "downgrade")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _prepared(conn, PREPARED)
            with pytest.raises(DBAPIError, match="order_prepared events"):
                async with conn.begin_nested():
                    await conn.execute(text(own_down[0]))
            assert await _db_allowlist(conn) == allowlist_spec()
        finally:
            await trans.rollback()


def test_ac5_the_0016_render_is_frozen_and_a_new_type_without_a_revision_is_refused() -> None:
    """AC-5: 0002 renders exactly the 11 pre-0017 types (a frozen literal, not "all minus order_prepared"); a type
    added to the allowlist without a DECLARED_IN_REVISION entry is refused at import (fail closed), as is a base type
    given a revision or a revision at or below 16."""
    from ofo_app import audit_allowlist as al  # noqa: PLC0415

    assert set(allowlist_spec(through_revision=16)) == PRE_0017_TYPES == al.BASE_TYPES
    fake = {**ALLOWLIST, EventType.ORDER_SUBMITTED: {"order_id": "scalar"}}
    with pytest.raises(ValueError, match="order_submitted"):
        al.check_revisions(fake, al.DECLARED_IN_REVISION)
    al.check_revisions(fake, {**al.DECLARED_IN_REVISION, EventType.ORDER_SUBMITTED: 18})
    for bad in ({**al.DECLARED_IN_REVISION, EventType.TRIAL_STARTED: 18}, {EventType.ORDER_PREPARED: 16}):
        with pytest.raises(ValueError, match="DECLARED_IN_REVISION"):
            al.check_revisions(ALLOWLIST, bad)


def test_ac5_0017_pin_swap_fails_closed_and_through_revision_is_checked() -> None:
    """AC-5: the chain text must pin the 0016 allowlist body exactly once, else the migration refuses to render;
    ``allowlist_spec(through_revision=...)`` refuses a revision before the base and a non-int."""
    migration = _order_prepared_migration()
    good = migration.previous_allowlist_sql()
    assert migration.extended_allowlist_sql() != good
    old_pin = migration._M4._md5_body(migration.allowed_function_sql(migration.BEFORE))
    for broken in (good.replace(f"'{old_pin}'", "'0'"), good + f"'{old_pin}'"):
        migration.previous_allowlist_sql = lambda text=broken: text
        with pytest.raises(RuntimeError, match="exactly once"):
            migration.extended_allowlist_sql()
    for bad in (15, True, "17", 16.0):
        with pytest.raises(ValueError, match="through_revision"):
            allowlist_spec(through_revision=bad)
    assert "order_prepared" not in allowlist_spec(through_revision=16)
    assert allowlist_spec(through_revision=17) == allowlist_spec()


# ---------------------------------------------------------------------------------------------------------------
# Finding request-clock-for-database-stamped-fact: the store stamps its own time from the database clock
# ---------------------------------------------------------------------------------------------------------------

#: A pinned request clock far from the database clock (the GC-2c failure: a route's frozen "now").
REQUEST_CLOCK = datetime(2026, 10, 16, 15, 7, tzinfo=timezone(timedelta(hours=5, minutes=30)))
#: The brief's bound: the stored time is within 5 s of clock_timestamp() read in the same transaction.
DB_CLOCK_BOUND = timedelta(seconds=5)


def test_append_refuses_a_caller_supplied_timestamp_with_type_error() -> None:
    """append has no timestamp parameter: passing one is a TypeError at the call, before any SQL (conn=None)."""
    with pytest.raises(TypeError, match="timestamp"):
        append(None, EventType.SUBSCRIPTION_STARTED, actor="a", timestamp=REQUEST_CLOCK,  # type: ignore[call-arg]
               correlation_id="c", payload={})


def _within_db_clock(stamp: datetime, before: datetime, after: datetime) -> bool:
    return before <= stamp <= after and after - stamp <= DB_CLOCK_BOUND


async def test_append_under_a_far_request_clock_stores_the_database_time(app_engine: AsyncEngine) -> None:
    """Core proof: the session's time zone is set far from IST (UTC+14) and the request clock is pinned to
    2026-10-16 15:07 IST; the stored time is the database clock read in the same transaction, not the request clock,
    and the row, the event and the hash all carry it."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
            before = await _db_clock(conn)
            stored = await append(conn, EventType.TRIAL_STARTED, actor="system", correlation_id=_cid(),
                                  payload={"platform_user_id": "u-far"})
            after = await _db_clock(conn)
            row_ts = (await conn.execute(text('SELECT "timestamp" FROM public.audit_events WHERE seq = :s'),
                                         {"s": stored.seq})).scalar_one()
            assert _within_db_clock(stored.event.timestamp, before, after), (before, stored.event.timestamp, after)
            assert row_ts == stored.event.timestamp
            assert abs(stored.event.timestamp - REQUEST_CLOCK) > DB_CLOCK_BOUND
            log, anchor = await load_log(conn)
            assert log.events[stored.seq - 1].hash == stored.event.hash and log.verify(anchor).ok
        finally:
            await trans.rollback()


async def test_database_clock_that_is_not_an_aware_time_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The store fails closed if the clock read returns anything but a timezone-aware datetime."""

    class _Conn:
        def __init__(self, value: object) -> None:
            self.value = value

        async def execute(self, *_args: object) -> object:
            value = self.value
            return type("R", (), {"scalar_one": lambda _self: value})()

    naive = datetime(2026, 10, 17, 10, 0)  # noqa: DTZ001 - the naive value under test
    for bad in (None, "2026-10-17T10:00:00+05:30", naive):
        with pytest.raises(AuditStoreError, match="database clock"):
            await audit_store._database_now(_Conn(bad))


async def test_chain_verifies_after_appends_from_the_order_routes_and_the_entitlement_store(
    app_engine: AsyncEngine,
) -> None:
    """The Execute route's order_prepared, the return route's broker response, the entitlement store and a direct
    append share one chain; each event's time is the database clock of its own transaction. (The catalogue store's
    forced update is proven on the real write in test_catalogue_store.py with a fixed as_of far from now.)"""
    plan = SimpleNamespace(strategy_id=1, plan_number=1, action="ENTRY", orders=(SimpleNamespace(tag="OFS1V1L0"),))
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            head = await read_anchor(conn)
            before = await _db_clock(conn)
            await order_audit.record_prepared(conn, plan, actor="u-1")
            order_row = {"order_id": f"ord-{uuid.uuid4().hex}", "status": "COMPLETE"}
            assert await order_audit.record_once(conn, EventType.BROKER_RESPONSE_RECORDED,
                                                 order_audit.order_correlation(order_row), order_row)
            user = f"test-clock-{uuid.uuid4().hex}"
            await entitlement_store.append(conn, user, trial_grant("trial", before, "registration",
                                                                   AuditNote("system", "test")))
            await _subscription(conn)
            after = await _db_clock(conn)
            log, anchor = await load_log(conn)
            assert anchor.count == head.count + 4 and log.verify(anchor).ok
            new = log.events[head.count:]
            assert [e.event_type for e in new] == [EventType.ORDER_PREPARED, EventType.BROKER_RESPONSE_RECORDED,
                                                   EventType.TRIAL_STARTED, EventType.SUBSCRIPTION_STARTED]
            assert all(_within_db_clock(e.timestamp, before, after) for e in new), [e.timestamp for e in new]
            assert [e.timestamp for e in new] == sorted(e.timestamp for e in new)
        finally:
            await trans.rollback()


class _RecordingConn:
    """A fake connection: answers the store's statements, records their order and the INSERT's parameters."""

    def __init__(self, clock: datetime) -> None:
        self.clock = clock
        self.order: list[str] = []
        self.inserted: dict = {}

    async def execute(self, stmt: object, params: object = None) -> SimpleNamespace:
        sql = str(stmt)
        if "transaction_isolation" in sql:
            self.order.append("isolation")
            return SimpleNamespace(scalar_one=lambda: "read committed")
        if "pg_advisory_xact_lock" in sql:
            self.order.append("lock")
            return SimpleNamespace()
        if "clock_timestamp" in sql:
            self.order.append("clock")
            return SimpleNamespace(scalar_one=lambda: self.clock)
        if "audit_anchor" in sql:
            self.order.append("anchor")
            row = SimpleNamespace(event_count=0, last_hash=GENESIS_HASH)
            return SimpleNamespace(one_or_none=lambda: row)
        if "INSERT INTO public.audit_events" in sql:
            self.order.append("insert")
            self.inserted = dict(params)  # type: ignore[call-overload]
            return SimpleNamespace()
        raise AssertionError(f"unexpected statement: {sql}")


async def test_event_time_is_the_clock_read_after_the_lock_and_before_the_anchor() -> None:
    """The stored time is exactly what SELECT clock_timestamp() returned (a sentinel no Python clock can produce),
    it reaches the hash input, and the clock is read after the lock and before the anchor (a time read before the
    lock can be stale by the lock wait and trip the trigger's 60 s window, OF001)."""
    sentinel = datetime(2001, 1, 1, tzinfo=timezone(timedelta(0)))
    conn = _RecordingConn(sentinel)
    stored = await append(conn, EventType.TRIAL_STARTED, actor="system", correlation_id="c-1",
                          payload={"platform_user_id": "u-1"})
    assert stored.event.timestamp == sentinel and conn.inserted["ts"] == sentinel
    assert "2001-01-01T00:00:00+00:00" in conn.inserted["canonical"]
    assert conn.order == ["isolation", "lock", "clock", "anchor", "insert"]
