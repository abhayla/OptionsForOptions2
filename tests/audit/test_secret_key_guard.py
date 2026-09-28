"""AC-2 fix round: word-based secret-key matching, and the $-tag type-disambiguation fix.

Class: a guard written as substring matching over free-form names, which both over-blocks
required data (a broker response payload with instrument_token/exchange_token was rejected
because it contained the substring "token") and under-blocks real secrets (whose word doesn't
happen to be one of the configured substrings). Proof below: a raw Kite-style broker response is
accepted whole; a list of real secret field names is rejected individually, at any depth.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.audit.models import GENESIS_HASH, PayloadValidationError, _compute_hash

BASE_TIME = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)

# A representative raw Kite (Zerodha) broker order-response payload (REQ-064 AC-1 requires
# auditing "broker responses"). Field names taken from Kite Connect's documented order/quote
# response shape.
KITE_STYLE_BROKER_RESPONSE = {
    "order_id": "231020000000001",
    "exchange_order_id": "1100000000001",
    "tradingsymbol": "NIFTY24JAN25000CE",
    "exchange": "NFO",
    "instrument_token": 256265,
    "exchange_token": 1001,
    "transaction_type": "BUY",
    "order_type": "LIMIT",
    "quantity": 50,
    "status": "COMPLETE",
    "session_expires_at": "2026-01-01T15:30:00+05:30",
    "meta": {"order_id": "231020000000001", "instrument_token": 256265},
}

# Real secret field names that must be rejected, individually, at any nesting depth.
REAL_SECRET_KEYS = (
    "authorization",
    "cookie",
    "bearer",
    "jwt",
    "access_token",
    "refresh_token",
    "request_token",
    "api_key",
    "api_secret",
    "password",
    "private_key",
)


def test_kite_style_broker_response_payload_is_accepted() -> None:
    """AC-1 requires auditing broker responses; a raw Kite-style payload must not be rejected."""
    log = AuditLog()
    event = log.append(
        EventType.BROKER_RESPONSE_RECORDED,
        actor="system",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload=KITE_STYLE_BROKER_RESPONSE,
    )
    assert event.payload["instrument_token"] == 256265
    assert event.payload["exchange_token"] == 1001
    assert event.payload["order_id"] == "231020000000001"
    assert event.payload["tradingsymbol"] == "NIFTY24JAN25000CE"
    assert event.payload["session_expires_at"] == "2026-01-01T15:30:00+05:30"


@pytest.mark.parametrize("secret_key", REAL_SECRET_KEYS)
def test_real_secret_keys_are_rejected_top_level(secret_key: str) -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={secret_key: "value"},
        )


@pytest.mark.parametrize("secret_key", REAL_SECRET_KEYS)
def test_real_secret_keys_are_rejected_nested(secret_key: str) -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"headers": {"nested": {secret_key: "value"}}},
        )


def test_session_token_is_rejected_but_session_expires_at_is_accepted() -> None:
    """The exact discriminating pair the fix round named."""
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"session_token": "abc"},
        )
    event = log.append(
        EventType.SECURITY_EVENT_RECORDED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-2",
        payload={"session_expires_at": "2026-01-01T15:30:00+05:30"},
    )
    assert event.payload["session_expires_at"] == "2026-01-01T15:30:00+05:30"


def test_id_token_pair_is_rejected_but_order_id_is_accepted() -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"id_token": "abc"},
        )
    event = log.append(
        EventType.SECURITY_EVENT_RECORDED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-2",
        payload={"order_id": "231020000000001"},
    )
    assert event.payload["order_id"] == "231020000000001"


def test_client_secret_and_apikey_camel_case_variants_rejected() -> None:
    log = AuditLog()
    for bad_key in ("client_secret", "apiKey", "ApiKey", "privateKey"):
        with pytest.raises(PayloadValidationError):
            log.append(
                EventType.SECURITY_EVENT_RECORDED,
                actor="user-1",
                timestamp=BASE_TIME,
                correlation_id="corr-1",
                payload={bad_key: "value"},
            )


def test_values_are_not_scanned_only_keys() -> None:
    """Documented scope: a value that looks like a secret under an innocuous key is not caught —
    only mapping keys are scanned, never values."""
    log = AuditLog()
    event = log.append(
        EventType.SECURITY_EVENT_RECORDED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"note": "password=hunter2"},
    )
    assert event.payload["note"] == "password=hunter2"


# --- Type-ambiguity fix: reserved "$" keys, and tagged Decimal/datetime -----------------------


def test_dollar_prefixed_key_is_rejected_top_level() -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.ORDER_PREPARED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"$decimal": "1365.00"},
        )


def test_dollar_prefixed_key_is_rejected_nested() -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.ORDER_PREPARED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"details": {"$datetime": "2026-01-01T00:00:00+00:00"}},
        )


def test_decimal_value_and_lookalike_dict_hash_differently() -> None:
    """Before the fix: Decimal('1365.00') and {"$decimal": "1365.00"} hashed the same (both
    serialised to the identical JSON fragment). After the fix, the lookalike dict can never even
    be constructed as a caller payload (its key is reserved), so no collision is possible; this
    test proves the two payloads now behave differently: one is accepted, one is rejected."""
    hash_decimal = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.00")},
        previous_hash=GENESIS_HASH,
    )
    log = AuditLog()
    event = log.append(
        EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.00")},
    )
    assert event.hash == hash_decimal

    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.ORDER_PREPARED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-2",
            payload={"premium": {"$decimal": "1365.00"}},
        )


def test_aware_datetime_value_and_its_iso_string_hash_differently() -> None:
    """Before the fix: an aware datetime and its own ISO string hashed the same (the datetime
    serialised to a bare ISO string, indistinguishable from a caller-supplied string). After the
    fix, the datetime is tagged {"$datetime": "..."}, a caller cannot construct a lookalike
    (reserved key), and the two hashes differ."""
    aware = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    iso_string = aware.isoformat()

    hash_with_datetime_object = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"submitted_at": aware},
        previous_hash=GENESIS_HASH,
    )
    hash_with_plain_string = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"submitted_at": iso_string},
        previous_hash=GENESIS_HASH,
    )
    assert hash_with_datetime_object != hash_with_plain_string
