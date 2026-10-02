"""W-007 round 7: entitlement events on the trusted database clock (REQ-017 AC-3, AC-4; ADR-023 Q225, Q256).

Spec basis: ADR-023 Q225 ("a NEW entitlement event is checked against the current settings (caps, clock skew, no
backdating, no post-dating). STORED history is loaded with integrity checks only (order, ids, references) and is
never re-judged by today's settings"); its clarification ("recorded at" "is stamped by the ledger from its own clock;
a caller can never supply it."); Q256 ("the clock-skew window is 60 seconds, both ways."); REQ-017 AC-4 ("every change
is audited").

Two groups:
- unit tests of the row codec, the integrity-only loader and the audit mapping (no database; run everywhere);
- database tests as the application role ofo_app (TEST_DATABASE_URL; skipped locally with a reason, required in CI by
  OFO_REQUIRE_DB_TESTS=1). The ledger is append-only, so each test uses a fresh user id and reads only its own rows.

Expected values come from the spec: a 7-day trial (ADR-023 Q88), 30 referral days (ADR-038), periods laid end to end
(rule 2/5), so trial + 30 + 30 granted at t0 give Pro on [t0, t0 + 67 days); a 60 s window both ways (Q256).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.audit.catalogue import EventType
from ofo.entitlements import ledger as ledger_module
from ofo.entitlements.engine import access_at, referral_grant, trial_grant
from ofo.entitlements.events import (
    AccessLevel,
    Audit,
    AuditNote,
    EntitlementGrant,
    NewGrant,
    NewStatusChange,
    Source,
    Status,
)
from ofo_app import entitlement_store
from ofo_app.audit_allowlist import filter_payload
from ofo_app.entitlement_store import (
    DatabaseStamp,
    EntitlementStoreError,
    audit_record,
    decode_row,
    encode,
    ledger_from_rows,
)

PRO, LIMITED = AccessLevel.PRO, AccessLevel.LIMITED
TICK = timedelta(microseconds=1)
DAY = timedelta(days=1)
CLOCK_SQLSTATE = "OF001"
T0 = datetime(2026, 10, 2, 4, 30, tzinfo=timezone.utc)  # a realistic stamp for the unit tests


def note(reason: str = "test") -> AuditNote:
    return AuditNote("system", reason)


def _row(row_id: int, user_id: str, draft, recorded_at: datetime) -> SimpleNamespace:
    """A ledger row as PostgreSQL hands it back (payload through JSON, as JSONB stores it)."""
    kind, event_at, payload = encode(user_id, draft)
    return SimpleNamespace(id=row_id, kind=kind, event_at=event_at, recorded_at=recorded_at,
                           payload=json.loads(json.dumps(payload)))


def _seven_thirty_thirty(user_id: str, t0: datetime) -> list[SimpleNamespace]:
    return [
        _row(1, user_id, trial_grant("trial", t0, "registration", note()), t0),
        _row(2, user_id, referral_grant("ref-1", t0, "referral:a", note()), t0),
        _row(3, user_id, referral_grant("ref-2", t0, "referral:b", note()), t0),
    ]


# ================================================================ unit: codec, loader, audit mapping (no database)


def test_new_event_rows_never_carry_a_recorded_at():
    """Q225 clarification: the row the store sends has no recorded_at anywhere; the database stamps it."""
    for draft in (trial_grant("t", T0, "reg", note()), NewStatusChange("t", Status.ENDED, T0, note())):
        kind, event_at, payload = encode("u", draft)
        assert kind.startswith("entitlement.")
        assert event_at == T0
        assert "recorded_at" not in payload and "recorded_at" not in json.dumps(payload)


def test_rows_round_trip_to_the_recorded_events_with_the_database_stamp():
    """AC-3: source, grant time, duration, reference, status and audit survive the row; recorded_at is the row's."""
    stamp = T0 + timedelta(seconds=20)
    paid = NewGrant("p", Source.PAID_MONTHLY, T0, timedelta(days=30), "pay_1", note("bought"),
                    paid_at=T0 - timedelta(days=2))
    led = ledger_from_rows("u", [_row(7, "u", paid, stamp)], clock=DatabaseStamp())
    grant = led.grant("p")
    assert (grant.source, grant.granted_at, grant.duration, grant.reference) == (
        Source.PAID_MONTHLY, T0, timedelta(days=30), "pay_1")
    assert grant.paid_at == T0 - timedelta(days=2)
    assert grant.audit == Audit("system", stamp, "bought")


def test_history_7_30_30_loads_from_rows_after_the_cap_drops_to_30():
    """Issue #12 defect 2 / Q225: legal under cap 90, it loads under cap 30 with Pro on [t0, t0 + 67 days)."""
    rows = _seven_thirty_thirty("u", T0)
    for cap in (90, 30):
        led = ledger_from_rows("u", rows, clock=DatabaseStamp(), max_free_days=cap)
        assert access_at(led, T0 + 67 * DAY - TICK).level is PRO
        assert access_at(led, T0 + 67 * DAY).level is LIMITED
        assert access_at(led, T0 + 7 * DAY).sources == (Source.REFERRAL,)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: setattr(r, "payload", "not an object"), "payload is not an object"),
        (lambda r: r.payload.update(extra="x"), "keys"),
        (lambda r: r.payload.update(duration_us=1.5), "duration_us"),
        (lambda r: r.payload.update(source="GOLD"), "GOLD"),
        (lambda r: r.payload.update(user_id="someone-else"), "user_id"),
        (lambda r: setattr(r, "kind", "entitlement.mystery"), "unknown entitlement kind"),
        (lambda r: setattr(r, "event_at", datetime(2026, 10, 2)), "event_at"),
    ],
)
def test_an_undecodable_row_fails_closed_naming_its_id(mutate, message):
    """B4 standing item: any stored row the loader cannot decode is refused, naming the row id."""
    rows = _seven_thirty_thirty("u", T0)
    mutate(rows[1])
    with pytest.raises(EntitlementStoreError, match=rf"ledger row id=2 .*{message}"):
        ledger_from_rows("u", rows, clock=DatabaseStamp())


def test_a_row_breaking_integrity_is_refused_naming_its_id():
    """Q225: integrity (ids, references, order) still holds on load; the offending row is named."""
    rows = _seven_thirty_thirty("u", T0)
    rows.append(_row(9, "u", referral_grant("ref-3", T0, "REFERRAL:A ", note()), T0))  # same reference, re-cased
    with pytest.raises(EntitlementStoreError, match="ledger row id=9 breaks entitlement integrity"):
        ledger_from_rows("u", rows, clock=DatabaseStamp())


def test_the_database_stamp_clock_refuses_before_the_database_has_stamped():
    """Fail closed: the domain never falls back to the application clock."""
    led = ledger_from_rows("u", [], clock=DatabaseStamp())
    with pytest.raises(EntitlementStoreError, match="only from the database clock"):
        led.append(trial_grant("t", T0, "reg", note()))


async def test_append_refuses_a_stamped_event_before_any_sql():
    """Q225 clarification: an EntitlementGrant carrying a caller's 2020 recorded_at is refused (conn is never used)."""
    stamped = EntitlementGrant("t", Source.TRIAL, T0, timedelta(days=7), "reg",
                               Audit("system", datetime(2020, 1, 1, tzinfo=timezone.utc), "backdated"))
    with pytest.raises(EntitlementStoreError, match="never supplied by the caller"):
        await entitlement_store.append(None, "u", stamped)  # type: ignore[arg-type]


def test_every_audit_payload_stays_inside_its_allowlist():
    """AC-4: each mapped audit event is a declared type and nothing it carries is dropped by the allowlist."""
    stamp = DatabaseStamp()
    led = ledger_from_rows("u", [], clock=stamp)
    drafts = [
        trial_grant("t", T0, "reg", note()),
        referral_grant("r", T0, "referral:x", note()),
        NewGrant("p", Source.PAID_ANNUAL, T0, timedelta(days=365), "pay_1", note()),
        NewGrant("d", Source.DIRECT_ZERODHA_CUSTOMER, T0, None, "eligibility:1", note()),
        NewStatusChange("t", Status.ENDED, T0, note("used account")),
        NewStatusChange("p", Status.REVOKED, T0, note("refund")),
        NewStatusChange("d", Status.REVOKED, T0, note("deactivated")),
        NewStatusChange("r", Status.REVOKED, T0, note("fraud")),
    ]
    seen = []
    for draft in drafts:
        stamp.recorded_at = T0
        led = led.append(draft)
        event_type, payload = audit_record(led, led.events[-1])
        assert filter_payload(event_type, payload) == payload
        seen.append(event_type)
    assert seen == [
        EventType.TRIAL_STARTED, EventType.REFERRAL_REWARD_GRANTED, EventType.SUBSCRIPTION_STARTED,
        EventType.DIRECT_CUSTOMER_ELIGIBILITY_GRANTED, EventType.TRIAL_EXPIRED, EventType.SUBSCRIPTION_EXPIRED,
        EventType.DIRECT_CUSTOMER_ELIGIBILITY_REVOKED, EventType.ENTITLEMENT_CHANGED,
    ]


# ================================================================ database (real PostgreSQL as ofo_app)


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


def _user() -> str:
    return f"test-ent-{uuid.uuid4().hex}"


async def _db_now(conn: AsyncConnection) -> datetime:
    return (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def _row_count(conn: AsyncConnection, user_id: str) -> int:
    return (await conn.execute(
        text("SELECT count(*) FROM public.ledger_entries WHERE kind LIKE 'entitlement.%' "
             "AND payload->>'user_id' = :u"), {"u": user_id})).scalar_one()


async def _audit_count(conn: AsyncConnection, row_id: int) -> int:
    return (await conn.execute(text("SELECT count(*) FROM public.audit_events WHERE correlation_id = :c"),
                               {"c": f"ledger:{row_id}"})).scalar_one()


async def test_proof_b_a_caller_time_from_2020_is_replaced_by_the_database_time(app_engine: AsyncEngine) -> None:
    """Proof (b): a raw insert naming recorded_at 2020 is stamped with the database time; the store reloads it with
    that stamp and access is unchanged: Pro on [t0, t0 + 7 days)."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        before = await _db_now(conn)
        kind, event_at, payload = encode(user, trial_grant("trial", before, "registration", note()))
        row = (await conn.execute(
            text("INSERT INTO public.ledger_entries (kind, event_at, recorded_at, payload) "
                 "VALUES (:k, :e, :r, CAST(:p AS jsonb)) RETURNING id, recorded_at"),
            {"k": kind, "e": event_at, "r": datetime(2020, 1, 1, tzinfo=timezone.utc), "p": json.dumps(payload)},
        )).one()
        after = await _db_now(conn)
        assert before <= row.recorded_at <= after, f"recorded_at {row.recorded_at} is not the database time"
        assert row.recorded_at.year != 2020
        print(f"PROOF caller recorded_at 2020-01-01 -> stored recorded_at {row.recorded_at.isoformat()}")
        led = await entitlement_store.load(conn, user)
        assert led.grant("trial").audit.recorded_at == row.recorded_at
        assert access_at(led, before + 7 * DAY - TICK).level is PRO
        assert access_at(led, before + 7 * DAY).level is LIMITED


async def test_store_append_stamps_the_database_time_and_writes_the_audit_event(app_engine: AsyncEngine) -> None:
    """AC-3/AC-4: the store's grant carries the database stamp; its audit event (same stamp, ledger:<id>) exists."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        t0 = await _db_now(conn)
        led, row_id = await entitlement_store.append(conn, user, trial_grant("trial", t0, "registration", note()))
        stored = (await conn.execute(text("SELECT recorded_at FROM public.ledger_entries WHERE id = :i"),
                                     {"i": row_id})).scalar_one()
        assert led.grant("trial").audit.recorded_at == stored
        audit = (await conn.execute(
            text('SELECT event_type, "timestamp" FROM public.audit_events WHERE correlation_id = :c'),
            {"c": f"ledger:{row_id}"})).one()
        assert (audit.event_type, audit.timestamp) == (EventType.TRIAL_STARTED.value, stored)


async def test_store_refuses_a_grant_dated_2020_with_nothing_written(app_engine: AsyncEngine) -> None:
    """Q256: an event dated outside the database stamp +/- 60 s is refused by the database (OF001)."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        with pytest.raises(DBAPIError) as caught:
            await entitlement_store.append(
                conn, user, trial_grant("trial", datetime(2020, 1, 1, tzinfo=timezone.utc), "registration", note()))
        assert _sqlstate(caught.value) == CLOCK_SQLSTATE
        assert await _row_count(conn, user) == 0


async def test_post_dated_revoke_is_refused_and_a_real_revoke_still_lands(app_engine: AsyncEngine) -> None:
    """Issue #12 defect 1: a revoke effective 2106 (or 61 s ahead) is refused; the real revoke now is recorded."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        t0 = await _db_now(conn)
        await entitlement_store.append(conn, user, NewGrant("p", Source.PAID_MONTHLY, t0, 30 * DAY, "pay_1", note()))
        for effective in (datetime(2106, 1, 1, tzinfo=timezone.utc), (await _db_now(conn)) + timedelta(seconds=61)):
            with pytest.raises(DBAPIError) as caught:
                await entitlement_store.append(conn, user, NewStatusChange("p", Status.REVOKED, effective, note()))
            assert _sqlstate(caught.value) == CLOCK_SQLSTATE
        now = await _db_now(conn)
        led, _ = await entitlement_store.append(conn, user, NewStatusChange("p", Status.REVOKED, now, note("fraud")))
        assert led.status_change("p").effective_at == now
        assert access_at(led, now).level is LIMITED


async def _build_7_30_30(conn: AsyncConnection, user: str) -> datetime:
    t0 = await _db_now(conn)
    await entitlement_store.append(conn, user, trial_grant("trial", t0, "registration", note()), max_free_days=90)
    await entitlement_store.append(conn, user, referral_grant("ref-1", await _db_now(conn), "referral:a", note()),
                                   max_free_days=90)
    await entitlement_store.append(conn, user, referral_grant("ref-2", await _db_now(conn), "referral:b", note()),
                                   max_free_days=90)
    return t0


async def _history_survives_the_cap_drop(conn: AsyncConnection, user: str, t0: datetime) -> None:
    try:
        led = await entitlement_store.load(conn, user, max_free_days=30)
    except EntitlementStoreError as exc:
        raise AssertionError(f"stored history refused on load: {exc}") from exc
    assert access_at(led, t0 + 67 * DAY - TICK).level is PRO
    assert access_at(led, t0 + 67 * DAY).level is LIMITED


async def _over_cap_grant_is_refused(conn: AsyncConnection, user: str) -> None:
    rows_before = await _row_count(conn, user)
    try:
        await entitlement_store.append(conn, user, referral_grant("ref-3", await _db_now(conn), "referral:c", note()),
                                       max_free_days=30)
    except EntitlementStoreError as exc:
        assert "maximum accumulated free days is 30" in str(exc)
        assert await _row_count(conn, user) == rows_before, "a refused grant left its ledger row behind"
        return
    raise AssertionError("over-cap grant was accepted")


async def test_proof_b_7_30_30_history_loads_after_the_cap_drops_to_30(app_engine: AsyncEngine) -> None:
    """Proof (b) / issue #12 defect 2: built under cap 90 through the store, it loads under cap 30 with access
    unchanged; a NEW free grant then meets the cap 30 (Q225)."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        t0 = await _build_7_30_30(conn, user)
        await _history_survives_the_cap_drop(conn, user, t0)
        print(f"PROOF 7+30+30 history of {user} loads under max_free_days=30 (3 rows)")
        await _over_cap_grant_is_refused(conn, user)


async def test_the_audit_event_rolls_back_with_the_ledger_row(app_engine: AsyncEngine) -> None:
    """AC-4: ledger row and audit event share the transaction: a rollback removes both."""
    user = _user()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        t0 = await _db_now(conn)
        _, row_id = await entitlement_store.append(conn, user, trial_grant("trial", t0, "registration", note()))
        assert await _row_count(conn, user) == 1 and await _audit_count(conn, row_id) == 1
        await trans.rollback()
    async with app_engine.connect() as fresh:
        assert await _row_count(fresh, user) == 0
        assert await _audit_count(fresh, row_id) == 0


async def test_an_audit_failure_rolls_back_the_ledger_row(app_engine: AsyncEngine, monkeypatch) -> None:
    """AC-4: if the audit event cannot be written, the entitlement event is not recorded either."""
    user = _user()

    async def failing_audit(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(entitlement_store.audit_store, "append", failing_audit)
    async with app_engine.connect() as conn, conn.begin():
        t0 = await _db_now(conn)
        with pytest.raises(RuntimeError, match="audit store down"):
            await entitlement_store.append(conn, user, trial_grant("trial", t0, "registration", note()))
        assert await _row_count(conn, user) == 0


async def test_a_domain_refusal_leaves_no_ledger_row(app_engine: AsyncEngine) -> None:
    """Integrity on a new event: a second trial is refused by the domain after the insert; the row is rolled back."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        await entitlement_store.append(conn, user, trial_grant("trial", await _db_now(conn), "registration", note()))
        with pytest.raises(EntitlementStoreError, match="already has a trial"):
            await entitlement_store.append(conn, user, trial_grant("trial-2", await _db_now(conn), "again", note()))
        assert await _row_count(conn, user) == 1


# ---------------------------------------------------------------- mutation tests (each turns its test red)


async def test_mutant_loader_re_applying_todays_cap_is_caught(app_engine: AsyncEngine, monkeypatch) -> None:
    """If load re-judged stored history by today's cap, the 7 + 30 + 30 history would fail under cap 30."""
    real = entitlement_store.ledger_from_rows

    def re_applying(user_id, rows, *, clock, max_free_days=None):
        led = real(user_id, rows, clock=clock, max_free_days=max_free_days)
        free = sum((g.duration for g in led.grants() if g.source in ledger_module.FREE_SOURCES), timedelta(0))
        if max_free_days is not None and free > timedelta(days=max_free_days):
            raise EntitlementStoreError(f"maximum accumulated free days is {max_free_days} (re-applied on load)")
        return led

    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        t0 = await _build_7_30_30(conn, user)
        await _history_survives_the_cap_drop(conn, user, t0)  # baseline: green
        monkeypatch.setattr(entitlement_store, "ledger_from_rows", re_applying)
        with pytest.raises(AssertionError, match="stored history refused on load"):
            await _history_survives_the_cap_drop(conn, user, t0)


async def test_mutant_store_skipping_the_new_event_policy_is_caught(app_engine: AsyncEngine, monkeypatch) -> None:
    """If the store's append skipped the domain's new-event policy, an over-cap grant would be accepted."""
    user = _user()
    async with app_engine.connect() as conn, conn.begin():
        await _build_7_30_30(conn, user)
        await _over_cap_grant_is_refused(conn, user)  # baseline: green
        monkeypatch.setattr(ledger_module, "_check_policy", lambda ledger, event: None)
        with pytest.raises(AssertionError, match="over-cap grant was accepted"):
            await _over_cap_grant_is_refused(conn, user)
