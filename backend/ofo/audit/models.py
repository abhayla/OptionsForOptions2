"""Audit event model: structured payload, actor, time, correlation id, and a tamper-evident hash."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from ofo.audit.catalogue import EventType

#: Hash used as the "previous hash" of the first event in a chain (64 zero hex digits).
GENESIS_HASH = "0" * 64

#: Payload keys matching this (case-insensitive) must never be logged.
_FORBIDDEN_KEY_PATTERN = re.compile(r"(password|secret|token|api[_-]?key)", re.IGNORECASE)


class PayloadValidationError(ValueError):
    """Raised when an audit payload contains a forbidden key or is not JSON-serialisable."""


def _check_payload_safe(payload: Any, *, _path: str = "payload") -> None:
    """Recursively reject payload keys that look like a secret (password/secret/token/api_key)."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise PayloadValidationError(f"{_path}: non-string key {key!r} is not allowed")
            if _FORBIDDEN_KEY_PATTERN.search(key):
                raise PayloadValidationError(
                    f"{_path}.{key}: payload key looks like a secret and must never be logged"
                )
            _check_payload_safe(value, _path=f"{_path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            _check_payload_safe(item, _path=f"{_path}[{index}]")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"not JSON-serialisable: {value!r}")


def _canonical_json(data: Mapping[str, Any]) -> str:
    """Canonical JSON: sorted keys, no extra whitespace, deterministic regardless of key order."""
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)
    except TypeError as exc:
        raise PayloadValidationError(f"payload is not JSON-serialisable: {exc}") from exc


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


@dataclass(frozen=True)
class AuditEvent:
    """One immutable audit record, linked into the chain by ``previous_hash``."""

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
        # Validate JSON-serialisability up front (also exercised by _compute_hash below).
        _canonical_json({"payload": self.payload})
        own_hash = _compute_hash(
            event_type=self.event_type,
            actor=self.actor,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            payload=self.payload,
            previous_hash=self.previous_hash,
        )
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
