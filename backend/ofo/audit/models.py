"""Audit event model: structured payload, actor, time, correlation id, and a tamper-evident hash.

This module does NOT filter secrets out of payloads (REQ-064 round 3, orchestrator + independent
reviewer decision under ADR-045: secret filtering is not one of REQ-064's acceptance criteria — it
was added by an earlier build brief, is a separate concern, and is removed here). Callers are
responsible for passing only the fields their event type needs. Per-event-type field allowlisting
belongs to REQ-063 AC-5 (a separate, future work item, blocked until real Kite response fixtures
are available to prove the allowlist against).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from ofo.audit.catalogue import EventType

#: Hash used as the "previous hash" of the first event in a chain (64 zero hex digits).
GENESIS_HASH = "0" * 64

#: Prefix reserved for this module's own internal type tags (see ``_json_default``): a caller's
#: payload may never use a key starting with "$", at any depth, so a tagged internal value (e.g.
#: ``{"$decimal": "1365.00"}``) can never collide with — and hash identically to — a caller-
#: supplied dict that happens to look the same.
_RESERVED_KEY_PREFIX = "$"


class PayloadValidationError(ValueError):
    """Raised when an audit payload contains a reserved key or is not JSON-serialisable."""


def check_payload_safe(payload: Any, *, _path: str = "payload") -> None:
    """Recursively reject non-string keys and keys starting with the reserved "$" prefix (nested
    dicts and lists too).

    This module does NOT filter secrets out of payloads. Callers are responsible for passing only
    the fields their event type needs (see the module docstring); per-event-type field
    allowlisting is REQ-063 AC-5, a separate, future work item.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise PayloadValidationError(f"{_path}: non-string key {key!r} is not allowed")
            if key.startswith(_RESERVED_KEY_PREFIX):
                raise PayloadValidationError(
                    f"{_path}.{key}: keys starting with '{_RESERVED_KEY_PREFIX}' are reserved for "
                    "internal type tags and cannot appear in a caller's payload"
                )
            _check_payload_safe(value, _path=f"{_path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            _check_payload_safe(item, _path=f"{_path}[{index}]")


def _reject_naive_datetime(value: datetime) -> None:
    if value.tzinfo is None:
        raise PayloadValidationError(
            "naive datetime is not allowed anywhere in an audit payload; use a timezone-aware value"
        )


def _json_default(value: Any) -> Any:
    """Canonical representation for values json.dumps cannot natively serialise.

    Decimal (ADR-008: money is exact Decimal, never float) is tagged as {"$decimal": "<str(value)>"}.
    str(Decimal(...)) preserves the exact scale as constructed, so Decimal('1365.00') and
    Decimal('1365.0') hash DIFFERENTLY (documented choice: the hash reflects exactly what the
    caller constructed, including trailing-zero precision, rather than silently normalising two
    Decimals that are numerically equal but carry different stated precision).

    An aware datetime is tagged as {"$datetime": "<UTC ISO-8601 string>"} for the same reason: a
    bare ISO string is how ``str(Decimal(...))``-style values are represented too, so an
    UNTAGGED datetime would hash identically to a caller-supplied plain string that happens to
    read the same ISO text (REQ-064 fix round: "an aware datetime and its ISO string hash the
    same" was a type ambiguity). A naive datetime raises. Both tags use the reserved "$" key
    prefix (see ``_RESERVED_KEY_PREFIX``), which a caller's own payload can never contain, so a
    caller cannot forge a lookalike {"$decimal": ...} / {"$datetime": ...} dict to collide with a
    real one. MappingProxyType (produced by ``_deep_freeze``) is unwrapped back to a plain dict so
    json.dumps can walk it.
    """
    if isinstance(value, datetime):
        _reject_naive_datetime(value)
        return {"$datetime": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, MappingProxyType):
        return dict(value)
    raise TypeError(f"not JSON-serialisable: {value!r}")


def canonical_json(data: Mapping[str, Any]) -> str:
    """Canonical JSON: sorted keys, no extra whitespace, deterministic regardless of key order."""
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)
    except TypeError as exc:
        raise PayloadValidationError(f"payload is not JSON-serialisable: {exc}") from exc


def deep_freeze(value: Any) -> Any:
    """Recursively freeze a payload into immutable structures.

    Dicts become a read-only ``MappingProxyType`` over a freshly built dict (never the caller's
    dict); lists/tuples become tuples. Scalars (str, int, float, bool, None, Decimal, datetime)
    are already immutable and are kept as-is. Because every container is rebuilt from scratch,
    neither the caller's original nested objects nor the stored event's payload can be mutated
    to change what was appended.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _compute_hash(
    *,
    event_type: EventType,
    actor: str,
    timestamp: datetime,
    correlation_id: str,
    payload: Mapping[str, Any],
    previous_hash: str,
) -> str:
    """SHA-256 over the canonical JSON of the event's fields, including the previous hash."""
    canonical = _canonical_json(
        {
            "event_type": event_type.value,
            "actor": actor,
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "correlation_id": correlation_id,
            "payload": payload,
            "previous_hash": previous_hash,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Private aliases kept so existing callers of the underscore names keep working (W-020 made these public for reuse
# by ofo.timeline, which hashes and freezes its entries with the same mechanism).
_check_payload_safe = check_payload_safe
_canonical_json = canonical_json
_deep_freeze = deep_freeze


@dataclass(frozen=True)
class AuditEvent:
    """One immutable audit record, linked into the chain by ``previous_hash``.

    ``payload`` is deep-frozen on construction (see ``_deep_freeze``): the stored value is
    independent of whatever mutable dict/list the caller passed in, and cannot itself be mutated
    afterwards through the normal Python container APIs.
    """

    event_type: EventType
    actor: str
    timestamp: datetime
    correlation_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    previous_hash: str = GENESIS_HASH
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("AuditEvent.timestamp must be timezone-aware")
        if not self.actor:
            raise ValueError("AuditEvent.actor must not be empty")
        if not self.correlation_id:
            raise ValueError("AuditEvent.correlation_id must not be empty")
        _check_payload_safe(self.payload)
        # Validate JSON-serialisability (incl. naive-datetime rejection) up front.
        _canonical_json({"payload": self.payload})
        own_hash = _compute_hash(
            event_type=self.event_type,
            actor=self.actor,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            payload=self.payload,
            previous_hash=self.previous_hash,
        )
        # Freeze AFTER hashing (content is identical either way; canonical JSON does not depend
        # on container type), so the stored payload can never be reached and mutated via any
        # reference the caller kept.
        object.__setattr__(self, "payload", _deep_freeze(self.payload))
        object.__setattr__(self, "hash", own_hash)

    def recompute_hash(self) -> str:
        """Recompute this event's own hash from its current field values (for verification)."""
        return _compute_hash(
            event_type=self.event_type,
            actor=self.actor,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            payload=self.payload,
            previous_hash=self.previous_hash,
        )
