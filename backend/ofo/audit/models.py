"""Audit event model: structured payload, actor, time, correlation id, and a tamper-evident hash."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from ofo.audit.catalogue import EventType

#: Hash used as the "previous hash" of the first event in a chain (64 zero hex digits).
GENESIS_HASH = "0" * 64

#: Whole words that make a key a secret wherever they appear (REQ-064 fix round, class: a guard
#: written as substring matching both over-blocks required data — "session_expires_at" or
#: "instrument_token" contain "session"/"token" as substrings — and under-blocks real secrets
#: whose word doesn't happen to be a configured substring). Matched as a WHOLE WORD after
#: splitting the key (see ``_split_words``), never as a substring: "pin" no longer matches
#: "shipping", and "session" alone no longer matches "session_expires_at".
_SECRET_WORD_MARKERS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "credential",
        "credentials",
        "authorization",
        "cookie",
        "bearer",
        "jwt",
        "otp",
        "pin",
        "signature",
    }
)

#: A key ending in one of these words immediately followed by the word "token" is a secret
#: (access_token, refresh_token, request_token, session_token, auth_token, api_token,
#: bearer_token, id_token). "instrument_token" and "exchange_token" are NOT caught here because
#: "instrument"/"exchange" are not in this set — REQ-064 AC-1 requires auditing broker responses,
#: which carry exactly those two Kite-style field names.
_TOKEN_PAIR_PREFIX_MARKERS = frozenset(
    {"access", "refresh", "request", "session", "auth", "api", "bearer", "id"}
)

#: A key whose words, joined together, equal one of these exactly (api_key, apikey, private_key,
#: client_secret) is a secret regardless of separator style.
_EXACT_FORBIDDEN_JOINED_WORDS = frozenset({"apikey", "privatekey", "clientsecret"})

#: Prefix reserved for this module's own internal type tags (see ``_json_default``): a caller's
#: payload may never use a key starting with "$", at any depth, so a tagged internal value (e.g.
#: ``{"$decimal": "1365.00"}``) can never collide with — and hash identically to — a caller-
#: supplied dict that happens to look the same.
_RESERVED_KEY_PREFIX = "$"

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


class PayloadValidationError(ValueError):
    """Raised when an audit payload contains a forbidden key or is not JSON-serialisable."""


def _split_words(key: str) -> list[str]:
    """Split a key into lower-case words on '_', '-', '.', spaces and camelCase boundaries."""
    words: list[str] = []
    for part in re.split(r"[_\-.\s]+", key):
        if not part:
            continue
        words.extend(w.lower() for w in _CAMEL_BOUNDARY.split(part) if w)
    return words


def _is_secret_key(key: str) -> bool:
    """True if ``key`` names a secret, by word (not substring) matching. Only KEYS are scanned —
    this never inspects the values, e.g. a value that happens to look like a JWT under an
    innocuous key name is not detected; that is out of scope for a key-name guard."""
    words = _split_words(key)
    if not words:
        return False
    if any(word in _SECRET_WORD_MARKERS for word in words):
        return True
    if len(words) >= 2 and words[-1] == "token" and words[-2] in _TOKEN_PAIR_PREFIX_MARKERS:
        return True
    if "".join(words) in _EXACT_FORBIDDEN_JOINED_WORDS:
        return True
    return False


def _check_payload_safe(payload: Any, *, _path: str = "payload") -> None:
    """Recursively reject payload keys that look like a secret, or start with the reserved "$"
    prefix (nested dicts and lists too). Only mapping KEYS are checked; values are never scanned."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise PayloadValidationError(f"{_path}: non-string key {key!r} is not allowed")
            if key.startswith(_RESERVED_KEY_PREFIX):
                raise PayloadValidationError(
                    f"{_path}.{key}: keys starting with '{_RESERVED_KEY_PREFIX}' are reserved for "
                    "internal type tags and cannot appear in a caller's payload"
                )
            if _is_secret_key(key):
                raise PayloadValidationError(
                    f"{_path}.{key}: payload key looks like a secret and must never be logged"
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


def _canonical_json(data: Mapping[str, Any]) -> str:
    """Canonical JSON: sorted keys, no extra whitespace, deterministic regardless of key order."""
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)
    except TypeError as exc:
        raise PayloadValidationError(f"payload is not JSON-serialisable: {exc}") from exc


def _deep_freeze(value: Any) -> Any:
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
