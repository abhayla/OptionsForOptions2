"""PostgreSQL store for entitlement events on the trusted database clock (W-007 round 7; REQ-017; ADR-023 Q225, Q256).

Copy from: none - algochanakya has no entitlement code (legacy-reuse.md M9).

Spec basis:
- ADR-023 Q225: "a NEW entitlement event is checked against the current settings (caps, clock skew, no backdating,
  no post-dating). STORED history is loaded with integrity checks only (order, ids, references) and is never
  re-judged by today's settings".
- ADR-023 Q225 clarification: "recorded at" "is stamped by the ledger from its own clock; a caller can never supply
  it." Q256: "the clock-skew window is 60 seconds, both ways." The stamp is the database server clock at insert.
- REQ-017 AC-4: "every change is audited".

Each entitlement event is ONE row in the W-051 ledger (``public.ledger_entries``): kind ``entitlement.grant`` or
``entitlement.status_change``, ``event_at`` = the event's own date (a grant's ``granted_at``, a change's
``effective_at``), payload = the rest. ``recorded_at`` is never sent: the BEFORE INSERT trigger stamps it with
``clock_timestamp()`` and refuses an ``event_at`` outside stamp +/- 60 s (SQLSTATE OF001).

append(conn, user_id, draft) inside the caller's transaction, in a SAVEPOINT so a refusal leaves nothing behind:
1. takes the per-user advisory lock (two appends for one user never interleave), loads the user's stored history;
2. inserts the ledger row and reads back the database's ``recorded_at``;
3. feeds that stamp to the domain ledger's clock seam and runs the domain's NEW-event checks (integrity + the
   current policy: 60 s skew both ways, no post-dated status change, the free-day cap); a refusal rolls the row back;
4. writes the matching audit event (W-052 store) with the same stamp and ``correlation_id = "ledger:<row id>"``.
Ledger row and audit event commit or roll back together.

load(conn, user_id) reads the user's rows ordered by id and rebuilds the ledger with integrity checks only
(``EntitlementLedger.load``): today's caps and skew are never re-applied to stored rows. A row the loader cannot
decode, or one that breaks integrity, fails closed with ``EntitlementStoreError`` naming the row id.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from ofo.audit.catalogue import EventType
from ofo.entitlements.engine import resolve
from ofo.entitlements.events import (
    Audit,
    EntitlementEvent,
    EntitlementGrant,
    EntitlementStatusChange,
    NewGrant,
    NewStatusChange,
    Placement,
    Source,
    Status,
)
from ofo.entitlements.ledger import EntitlementLedger, _restore
from ofo_app import audit_store
from ofo_app import ledger as trusted_ledger

#: ADR-023 Q256 (owner, 2026-10-02): "the clock-skew window is 60 seconds, both ways." Same value as the trigger.
Q256_CLOCK_SKEW = timedelta(seconds=60)

KIND_PREFIX = "entitlement."
KIND_GRANT = "entitlement.grant"
KIND_CHANGE = "entitlement.status_change"

#: First key of the two-key advisory lock; the second is hashtext(user_id). Only this store uses it.
ENTITLEMENT_LOCK_CLASS = 52_007

GRANT_KEYS = frozenset({"user_id", "entitlement_id", "source", "duration_us", "reference", "placement", "paid_at",
                        "actor", "reason"})
CHANGE_KEYS = frozenset({"user_id", "entitlement_id", "status", "actor", "reason"})

_LOCK = text("SELECT pg_advisory_xact_lock(:cls, hashtext(:user_id))")
_ROWS = text(
    "SELECT id, kind, event_at, recorded_at, payload FROM public.ledger_entries "
    "WHERE kind LIKE 'entitlement.%' AND payload->>'user_id' = :user_id ORDER BY id"
)


class EntitlementStoreError(ValueError):
    """A stored row the loader cannot decode or that breaks integrity, or a refused append."""


# ---------------------------------------------------------------- encode (new event -> ledger row)


def _duration_us(duration: timedelta | None) -> int | None:
    if duration is None:
        return None
    return (duration.days * 86_400 + duration.seconds) * 1_000_000 + duration.microseconds


def encode(user_id: str, draft: NewGrant | NewStatusChange) -> tuple[str, datetime, dict[str, Any]]:
    """(kind, event_at, payload) for a new event. There is no recorded_at: the database stamps it."""
    if isinstance(draft, NewGrant):
        return KIND_GRANT, draft.granted_at, {
            "user_id": user_id,
            "entitlement_id": draft.entitlement_id,
            "source": draft.source.value,
            "duration_us": _duration_us(draft.duration),
            "reference": draft.reference,
            "placement": draft.placement.value,
            "paid_at": draft.paid_at.isoformat() if draft.paid_at is not None else None,
            "actor": draft.note.actor,
            "reason": draft.note.reason,
        }
    return KIND_CHANGE, draft.effective_at, {
        "user_id": user_id,
        "entitlement_id": draft.entitlement_id,
        "status": draft.status.value,
        "actor": draft.note.actor,
        "reason": draft.note.reason,
    }


# ---------------------------------------------------------------- decode (stored row -> recorded event), fail closed


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} is not a string: {value!r}")
    return value


def _aware(name: str, value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} is not a timezone-aware time: {value!r}")
    return value


def decode_row(row: Any, user_id: str) -> EntitlementEvent:
    """Rebuild one recorded event from a ledger row. Any shape it cannot vouch for raises EntitlementStoreError."""
    row_id = getattr(row, "id", None)
    try:
        payload = row.payload
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
        if payload.get("user_id") != user_id:
            raise ValueError(f"payload user_id {payload.get('user_id')!r} is not {user_id!r}")
        event_at = _aware("event_at", row.event_at)
        audit = Audit(_text(payload, "actor"), _aware("recorded_at", row.recorded_at), _text(payload, "reason"))
        if row.kind == KIND_GRANT:
            if set(payload) != GRANT_KEYS:
                raise ValueError(f"grant payload keys {sorted(payload)} are not {sorted(GRANT_KEYS)}")
            raw_us = payload["duration_us"]
            if raw_us is not None and (isinstance(raw_us, bool) or not isinstance(raw_us, int)):
                raise ValueError(f"duration_us is not a whole number: {raw_us!r}")
            raw_paid = payload["paid_at"]
            paid_at = None if raw_paid is None else _aware("paid_at", datetime.fromisoformat(_text(payload, "paid_at")))
            return EntitlementGrant(
                _text(payload, "entitlement_id"),
                Source(_text(payload, "source")),
                event_at,
                None if raw_us is None else timedelta(microseconds=raw_us),
                _text(payload, "reference"),
                audit,
                Placement(_text(payload, "placement")),
                paid_at,
            )
        if row.kind == KIND_CHANGE:
            if set(payload) != CHANGE_KEYS:
                raise ValueError(f"status change payload keys {sorted(payload)} are not {sorted(CHANGE_KEYS)}")
            return EntitlementStatusChange(
                _text(payload, "entitlement_id"), Status(_text(payload, "status")), event_at, audit
            )
        raise ValueError(f"unknown entitlement kind {row.kind!r}")
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError) as exc:
        raise EntitlementStoreError(f"ledger row id={row_id} cannot be loaded as an entitlement event: {exc}") from exc


def ledger_from_rows(
    user_id: str,
    rows: list[Any],
    *,
    clock: Callable[[], datetime],
    max_free_days: int | None = None,
) -> EntitlementLedger:
    """Integrity checks only (order, ids, references): today's caps and skew are never re-applied (Q225)."""
    events = tuple(decode_row(row, user_id) for row in rows)
    settings = {"clock_skew": Q256_CLOCK_SKEW, "clock": clock, "max_free_days": max_free_days}
    try:
        return EntitlementLedger.load(_restore(user_id, events), **settings)
    except ValueError as exc:
        # Name the first row that breaks integrity (the failure path only; the normal path is one pass).
        for end in range(1, len(events) + 1):
            try:
                EntitlementLedger.load(_restore(user_id, events[:end]), **settings)
            except ValueError:
                raise EntitlementStoreError(
                    f"ledger row id={getattr(rows[end - 1], 'id', None)} breaks entitlement integrity: {exc}"
                ) from exc
        raise EntitlementStoreError(f"stored entitlement history of {user_id!r} is refused: {exc}") from exc


# ---------------------------------------------------------------- the database clock seam


class DatabaseStamp:
    """The domain ledger's clock: returns the ``recorded_at`` the database stamped on the row just inserted.

    Asked for a time before the database has stamped one, it refuses (fail closed): the domain never falls back
    to the application's clock.
    """

    def __init__(self) -> None:
        self.recorded_at: datetime | None = None

    def __call__(self) -> datetime:
        if self.recorded_at is None:
            raise EntitlementStoreError("no database stamp yet: recorded_at comes only from the database clock")
        return self.recorded_at


# ---------------------------------------------------------------- audit mapping (REQ-017 AC-4)


def audit_record(ledger: EntitlementLedger, event: EntitlementEvent) -> tuple[EventType, dict[str, Any]]:
    """The audit event type and payload for a newly recorded event (fields per ``ofo_app.audit_allowlist``)."""
    by_id = {r.grant.entitlement_id: r for r in resolve(ledger)}
    resolved = by_id[event.entitlement_id]
    grant = resolved.grant
    dates = {"starts_at": resolved.start, "ends_at": resolved.expiry, "reason": event.audit.reason}
    user = {"platform_user_id": ledger.user_id}
    if isinstance(event, EntitlementGrant):
        if grant.source is Source.TRIAL:
            return EventType.TRIAL_STARTED, {**user, **dates}
        if grant.source is Source.REFERRAL:
            return EventType.REFERRAL_REWARD_GRANTED, {**user, "reward_period": str(grant.duration), **dates}
        if grant.source is Source.DIRECT_ZERODHA_CUSTOMER:
            return EventType.DIRECT_CUSTOMER_ELIGIBILITY_GRANTED, {**user, "action": "granted",
                                                                   "reason": event.audit.reason}
        return EventType.SUBSCRIPTION_STARTED, {**user, "plan": grant.source.value, **dates}
    if grant.source is Source.TRIAL:
        return EventType.TRIAL_EXPIRED, {**user, **dates}
    if grant.source is Source.DIRECT_ZERODHA_CUSTOMER:
        return EventType.DIRECT_CUSTOMER_ELIGIBILITY_REVOKED, {**user, "action": "revoked",
                                                               "reason": event.audit.reason}
    if grant.source in (Source.PAID_MONTHLY, Source.PAID_ANNUAL):
        return EventType.SUBSCRIPTION_EXPIRED, {**user, "plan": grant.source.value, **dates}
    return EventType.ENTITLEMENT_CHANGED, {**user, "action": f"{grant.source.value.lower()}_{event.status.value}"}


# ---------------------------------------------------------------- public API


async def load(conn: Any, user_id: str, *, max_free_days: int | None = None) -> EntitlementLedger:
    """The user's stored entitlement history as a ledger (integrity checks only). New events appended to the
    returned ledger outside this store would have no database stamp and are refused."""
    rows = (await conn.execute(_ROWS, {"user_id": user_id})).all()
    return ledger_from_rows(user_id, list(rows), clock=DatabaseStamp(), max_free_days=max_free_days)


async def append(
    conn: Any,
    user_id: str,
    draft: NewGrant | NewStatusChange,
    *,
    max_free_days: int | None = None,
) -> tuple[EntitlementLedger, int]:
    """Record one new entitlement event and its audit event; return (the ledger after it, the ledger row id).

    Runs in a SAVEPOINT of the caller's transaction; the caller commits. Raises EntitlementStoreError (domain
    refusal) or the database error (e.g. SQLSTATE OF001, a date outside stamp +/- 60 s) with nothing written.
    """
    if not isinstance(draft, (NewGrant, NewStatusChange)):
        raise EntitlementStoreError(
            "append takes a NewGrant or NewStatusChange: recorded_at is stamped by the database clock, "
            f"never supplied by the caller (got {type(draft).__name__})"
        )
    if not isinstance(user_id, str) or not user_id.strip():
        raise EntitlementStoreError("user_id must be a non-empty string")
    kind, event_at, payload = encode(user_id, draft)
    async with conn.begin_nested():
        await conn.execute(_LOCK, {"cls": ENTITLEMENT_LOCK_CLASS, "user_id": user_id})
        rows = (await conn.execute(_ROWS, {"user_id": user_id})).all()
        stamp = DatabaseStamp()
        before = ledger_from_rows(user_id, list(rows), clock=stamp, max_free_days=max_free_days)
        row_id, recorded_at = await trusted_ledger.append(conn, kind, event_at, payload)
        stamp.recorded_at = recorded_at
        try:
            after = before.append(draft)
        except ValueError as exc:
            raise EntitlementStoreError(f"entitlement event refused: {exc}") from exc
        event = after.events[-1]
        if event.audit.recorded_at != recorded_at:
            raise EntitlementStoreError("the recorded event does not carry the database stamp; refusing")
        event_type, audit_payload = audit_record(after, event)
        await audit_store.append(
            conn,
            event_type,
            actor=event.audit.actor,
            timestamp=recorded_at,
            correlation_id=f"ledger:{row_id}",
            payload=audit_payload,
        )
    return after, row_id


__all__ = [
    "CHANGE_KEYS",
    "DatabaseStamp",
    "ENTITLEMENT_LOCK_CLASS",
    "EntitlementStoreError",
    "GRANT_KEYS",
    "KIND_CHANGE",
    "KIND_GRANT",
    "Q256_CLOCK_SKEW",
    "append",
    "audit_record",
    "decode_row",
    "encode",
    "ledger_from_rows",
    "load",
]
