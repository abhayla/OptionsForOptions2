"""PostgreSQL store for the hash-chained audit log (W-052; REQ-064 AC-2, REQ-063 AC-5).

Copy from: none - algochanakya has no hash-chained audit log (legacy-reuse.md M9). The hashing, canonical JSON and
chain verification are ``ofo.audit`` (models.py, log.py); this module only stores and reloads them.

append(conn, ...) inside the caller's transaction (READ COMMITTED, the PostgreSQL default; anything else is refused):
1. ``pg_advisory_xact_lock(AUDIT_APPEND_LOCK_KEY)`` serialises appends until the caller commits or rolls back.
2. Reads the anchor (event_count, last_hash) from ``public.audit_anchor``.
3. Filters the payload through the event type's field allowlist (undeclared type: refused, nothing sent), refuses any
   value the store cannot round-trip exactly (float, non-finite Decimal, NUL or lone surrogate in a string, other
   types), and builds the ``ofo.audit.AuditEvent`` on the anchor's last hash.
4. Inserts seq = count + 1 with the canonical tagged payload and the canonical text the hash is the SHA-256 of.
   The database refuses a row whose time is outside the Q256 window (OF001), whose payload leaves the allowlist
   (OF004), whose hash is not sha256(canonical) or whose canonical text does not match its columns (OF005), or that
   does not extend the anchor (OF003); its SECURITY DEFINER trigger moves the anchor in the same transaction.

load_log(conn) reads the anchor FIRST, then the events (so events committed in between only extend the prefix the
anchor attests), rebuilds every event with ``ofo.audit``, requires each payload to equal its allowlist-filtered form,
the stored canonical text to equal the Python canonical form byte for byte, each stored hash to equal its
recomputation, and
verifies the chain against the anchor via ``AuditLog.from_events``. Any mismatch raises ``AuditChainError`` naming
the row's seq.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditChainError, AuditLog, HeadAnchor
from ofo.audit.models import GENESIS_HASH, AuditEvent, canonical_json
from ofo_app.audit_allowlist import filter_payload, is_declared

#: Fixed key for the append lock (any constant; only the audit store uses it).
AUDIT_APPEND_LOCK_KEY = 5_200_052_001

_DECIMAL_TAG = "$decimal"
_DATETIME_TAG = "$datetime"

_LOCK = text("SELECT pg_advisory_xact_lock(:k)")
_ISOLATION = text("SELECT current_setting('transaction_isolation')")
_ANCHOR = text("SELECT event_count, last_hash FROM public.audit_anchor WHERE id = 1")
_INSERT = text(
    'INSERT INTO public.audit_events (seq, event_type, actor, "timestamp", correlation_id, payload, previous_hash, '
    "hash, canonical) VALUES (:seq, :event_type, :actor, :ts, :correlation_id, CAST(:payload AS jsonb), "
    ":previous_hash, :hash, :canonical)"
)
_EVENTS = text(
    'SELECT seq, event_type, actor, "timestamp", correlation_id, payload::text AS payload, previous_hash, hash, '
    "canonical FROM public.audit_events ORDER BY seq"
)


def canonical_text(event: AuditEvent) -> str:
    """The exact text ``event.hash`` is the SHA-256 of (the input of ofo.audit.models._compute_hash).

    Stored in the ``canonical`` column so the database can check hash = sha256(canonical) at insert. append()
    refuses if this ever drifts from ofo.audit's own hash.
    """
    return canonical_json(
        {
            "event_type": event.event_type.value,
            "actor": event.actor,
            "timestamp": event.timestamp.astimezone(timezone.utc).isoformat(),
            "correlation_id": event.correlation_id,
            "payload": event.payload,
            "previous_hash": event.previous_hash,
        }
    )


class AuditStoreError(ValueError):
    """The store refused an append: a value it cannot round-trip exactly, or an unsafe transaction setting."""


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    event: AuditEvent


# ---- values the store can round-trip exactly ----


def _check_storable(value: Any, path: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        raise AuditStoreError(f"{path} is a float; money is never float (ADR-008) - use Decimal")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise AuditStoreError(f"{path} is a non-finite Decimal ({value}); it cannot be stored")
        return
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AuditStoreError(f"{path} is a naive datetime; use a timezone-aware value")
        return
    if isinstance(value, str):
        if "\x00" in value:
            raise AuditStoreError(f"{path} contains a NUL character, which PostgreSQL JSONB cannot store")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise AuditStoreError(f"{path} is not valid Unicode (lone surrogate): {exc}") from exc
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_storable(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _check_storable(key, f"{path} key")
            _check_storable(item, f"{path}.{key}")
        return
    raise AuditStoreError(f"{path} has type {type(value).__name__}, which the audit store cannot round-trip")


def _refuse_float(literal: str) -> Any:
    raise AuditStoreError(f"stored payload holds a non-integer JSON number {literal!r} (money is tagged Decimal)")


def _refuse_constant(literal: str) -> Any:
    raise AuditStoreError(f"stored payload holds the non-JSON constant {literal!r}")


def decode_payload(value: Any) -> Any:
    """Turn the stored tagged form back into Decimal / datetime. A "$" key outside an exact one-key tag fails."""
    if isinstance(value, dict):
        if any(isinstance(k, str) and k.startswith("$") for k in value):
            if len(value) != 1:
                raise AuditStoreError(f"stored payload has a '$' key outside a one-key tag: {sorted(value)}")
            (tag, raw), = value.items()
            if not isinstance(raw, str):
                raise AuditStoreError(f"stored tag {tag} holds a non-string value {raw!r}")
            if tag == _DECIMAL_TAG:
                number = Decimal(raw)
                if not number.is_finite() or str(number) != raw:
                    raise AuditStoreError(f"stored {tag} {raw!r} does not round-trip")
                return number
            if tag == _DATETIME_TAG:
                moment = datetime.fromisoformat(raw)
                if moment.tzinfo is None:
                    raise AuditStoreError(f"stored {tag} {raw!r} is naive")
                return moment
            raise AuditStoreError(f"stored payload has an unknown tag {tag!r}")
        return {key: decode_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_payload(item) for item in value]
    return value


def encode_payload(payload: Mapping[str, Any]) -> str:
    """The canonical tagged JSON text stored in the payload column; refused unless it decodes back identically."""
    _check_storable(payload, "payload")
    stored = canonical_json(payload)
    reloaded = decode_payload(json.loads(stored, parse_float=_refuse_float, parse_constant=_refuse_constant))
    if canonical_json(reloaded) != stored:
        raise AuditStoreError("payload does not round-trip through its stored form")
    return stored


# ---- append ----


async def _take_lock(conn: Any) -> None:
    await conn.execute(_LOCK, {"k": AUDIT_APPEND_LOCK_KEY})


async def read_anchor(conn: Any) -> HeadAnchor:
    row = (await conn.execute(_ANCHOR)).one_or_none()
    if row is None:
        raise AuditChainError("audit anchor row is missing")
    return HeadAnchor(count=int(row.event_count), last_hash=str(row.last_hash))


async def append(
    conn: Any,
    event_type: EventType,
    *,
    actor: str,
    timestamp: datetime,
    correlation_id: str,
    payload: Mapping[str, Any] | None = None,
) -> StoredEvent:
    """Append one event inside the caller's transaction and return it with its seq. The caller commits."""
    filtered = filter_payload(event_type, payload)  # refuses an undeclared type before any SQL
    encoded = encode_payload(filtered)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise AuditStoreError("timestamp must be timezone-aware")

    isolation = (await conn.execute(_ISOLATION)).scalar_one()
    if isolation != "read committed":
        raise AuditStoreError(f"audit appends need READ COMMITTED (the head is read after the lock), got {isolation}")
    await _take_lock(conn)
    head = await read_anchor(conn)
    event = AuditEvent(
        event_type=event_type,
        actor=actor,
        timestamp=timestamp,
        correlation_id=correlation_id,
        payload=filtered,
        previous_hash=head.last_hash,
    )
    seq = head.count + 1
    canonical = canonical_text(event)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != event.hash:
        raise AuditStoreError("canonical text drifted from ofo.audit's hash input; refusing to store")
    await conn.execute(
        _INSERT,
        {
            "seq": seq,
            "event_type": event_type.value,
            "actor": actor,
            "ts": timestamp,
            "correlation_id": correlation_id,
            "payload": encoded,
            "previous_hash": event.previous_hash,
            "hash": event.hash,
            "canonical": canonical,
        },
    )
    return StoredEvent(seq=seq, event=event)


# ---- reload ----


def _row_event(row: Any) -> AuditEvent:
    seq = int(row.seq)
    try:
        event_type = EventType(row.event_type)
        if not is_declared(event_type):
            raise AuditStoreError(f"event type {row.event_type!r} has no allowlist entry")
        raw = json.loads(row.payload, parse_float=_refuse_float, parse_constant=_refuse_constant)
        if not isinstance(raw, dict):
            raise AuditStoreError("stored payload is not an object")
        decoded = decode_payload(raw)
        allowed = filter_payload(event_type, decoded)
        event = AuditEvent(
            event_type=event_type,
            actor=row.actor,
            timestamp=row.timestamp,
            correlation_id=row.correlation_id,
            payload=decoded,
            previous_hash=row.previous_hash,
        )
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise AuditChainError(f"audit row seq={seq} cannot be rebuilt: {exc}") from exc
    if allowed != decoded:
        raise AuditChainError(f"audit row seq={seq}: stored payload holds fields outside its allowlist")
    if canonical_text(event) != row.canonical:
        raise AuditChainError(f"audit row seq={seq}: stored canonical text is not the canonical form of the row")
    if event.hash != row.hash:
        raise AuditChainError(f"audit row seq={seq}: stored hash does not match its recomputed hash")
    return event


async def load_log(conn: Any) -> tuple[AuditLog, HeadAnchor]:
    """Reload and verify the whole log against the stored anchor. Raises AuditChainError naming the failing seq."""
    anchor = await read_anchor(conn)  # first: later commits only extend what it attests
    rows = (await conn.execute(_EVENTS)).all()
    events: list[AuditEvent] = []
    for expected_seq, row in enumerate(rows, start=1):
        if int(row.seq) != expected_seq:
            raise AuditChainError(f"audit row seq={expected_seq} is missing (found seq={row.seq} instead)")
        events.append(_row_event(row))
    try:
        log = AuditLog.from_events(events, anchor)
    except AuditChainError as exc:
        # from_events reports a 0-based index; seq is gap-free from 1 (checked above), so seq = index + 1.
        match = re.search(r"at index (\d+)", str(exc))
        if match is None:
            raise AuditChainError(f"audit log fails verification against the anchor: {exc}") from exc
        seq = int(match.group(1)) + 1
        raise AuditChainError(
            f"audit row seq={seq} fails chain verification against the anchor "
            f"(anchor count {anchor.count}, rows {len(events)})"
        ) from exc
    return log, anchor


__all__ = [
    "AUDIT_APPEND_LOCK_KEY",
    "GENESIS_HASH",
    "AuditChainError",
    "AuditStoreError",
    "StoredEvent",
    "append",
    "canonical_text",
    "decode_payload",
    "encode_payload",
    "load_log",
    "read_anchor",
]
