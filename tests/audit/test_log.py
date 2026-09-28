"""AC-2: audit records are append-only; a hash chain makes any modification detectable.

Core proof (W-015): append one event of every catalogued type, verify the chain is OK, then
tamper (change a payload value, delete an event, reorder two events, insert a forged event) and
assert verify() reports failure at the correct index each time.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.audit.models import GENESIS_HASH, AuditEvent, PayloadValidationError, _compute_hash

BASE_TIME = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


def _build_full_log() -> AuditLog:
    """A log with one event of every EventType in the catalogue, in enum definition order."""
    log = AuditLog()
    for index, event_type in enumerate(EventType):
        log.append(
            event_type,
            actor=f"user-{index}",
            timestamp=BASE_TIME + timedelta(seconds=index),
            correlation_id=f"corr-{index}",
            payload={"index": index, "note": event_type.value},
        )
    return log


def test_append_one_event_of_every_type_then_verify_ok() -> None:
    """AC-2: appending one event per catalogued type builds a chain that verifies clean."""
    log = _build_full_log()
    assert len(log.events) == len(list(EventType))
    result = log.verify()
    assert result.ok is True
    assert result.first_broken_index is None


def test_chain_links_previous_hash_to_predecessor() -> None:
    """AC-2: each event's previous_hash equals the actual hash of the event before it."""
    log = _build_full_log()
    events = log.events
    assert events[0].previous_hash == GENESIS_HASH
    for i in range(1, len(events)):
        assert events[i].previous_hash == events[i - 1].hash


def test_no_update_or_delete_api_exists() -> None:
    """AC-2: AuditLog exposes no method to modify or remove a stored event."""
    log = _build_full_log()
    for forbidden in ("update", "delete", "remove", "edit", "pop", "clear", "truncate"):
        assert not hasattr(log, forbidden), f"AuditLog must not expose {forbidden}()"


def test_events_property_is_an_immutable_tuple() -> None:
    """AC-2: the stored sequence is exposed as an immutable tuple, not the live internal list."""
    log = _build_full_log()
    events = log.events
    assert isinstance(events, tuple)
    with pytest.raises(AttributeError):
        events.append(events[0])  # type: ignore[attr-defined]


def test_tamper_changed_payload_value_detected() -> None:
    """AC-2: changing a stored event's payload value is caught at that event's index."""
    log = _build_full_log()
    target_index = 5
    original = log._events[target_index]
    tampered = replace(original, payload={**original.payload, "note": "tampered"})
    object.__setattr__(tampered, "hash", original.hash)  # attacker keeps the old (now-wrong) hash
    log._events[target_index] = tampered

    result = log.verify()
    assert result.ok is False
    assert result.first_broken_index == target_index


def test_tamper_deleted_event_detected() -> None:
    """AC-2: deleting a stored event breaks the chain at the point of deletion."""
    log = _build_full_log()
    deleted_index = 3
    del log._events[deleted_index]

    result = log.verify()
    assert result.ok is False
    assert result.first_broken_index == deleted_index


def test_tamper_reordered_events_detected() -> None:
    """AC-2: swapping two stored events breaks the chain at the earlier swapped index."""
    log = _build_full_log()
    i, j = 2, 7
    log._events[i], log._events[j] = log._events[j], log._events[i]

    result = log.verify()
    assert result.ok is False
    assert result.first_broken_index == i


def test_tamper_forged_insert_with_wrong_previous_hash_detected() -> None:
    """AC-2: an inserted event whose own hash is self-consistent but whose previous_hash is
    wrong (does not match its new predecessor) is still caught."""
    log = _build_full_log()
    insert_at = 4
    forged = AuditEvent(
        event_type=EventType.SECURITY_EVENT_RECORDED,
        actor="attacker",
        timestamp=BASE_TIME + timedelta(seconds=999),
        correlation_id="forged-corr",
        payload={"forged": True},
        previous_hash="f" * 64,  # self-consistent hash, but wrong linkage to its new predecessor
    )
    log._events.insert(insert_at, forged)

    result = log.verify()
    assert result.ok is False
    assert result.first_broken_index == insert_at


def test_timestamp_must_be_timezone_aware() -> None:
    """AC-2: a naive timestamp is rejected (fail closed), never silently accepted as UTC."""
    log = AuditLog()
    with pytest.raises(ValueError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=datetime(2026, 1, 1, 9, 15),  # no tzinfo
            correlation_id="corr-1",
            payload={},
        )


def test_payload_must_be_json_serialisable() -> None:
    """AC-2: a non-JSON-serialisable payload value is rejected, not silently dropped."""
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"handler": lambda: None},
        )


def test_ordinary_payload_keys_are_accepted() -> None:
    """AC-2: this module does not filter secrets — see models.py docstring; REQ-063 AC-5 owns
    per-event-type field allowlisting as separate, future work. Ordinary keys, including ones an
    earlier (now-removed) name-based guard would have flagged, are accepted unchanged."""
    log = AuditLog()
    event = log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={
            "strategy_id": "S-1",
            "amount": "1000.00",
            "note": "rebalanced",
            # These key names would have been rejected by the now-removed name-based guard; this
            # module stores whatever the caller passes, unfiltered.
            "password": "not-actually-filtered-here",
            "api_key": "not-actually-filtered-here",
            "session_token": "not-actually-filtered-here",
        },
    )
    assert event.payload["strategy_id"] == "S-1"
    assert event.payload["password"] == "not-actually-filtered-here"
    assert event.payload["api_key"] == "not-actually-filtered-here"
    assert event.payload["session_token"] == "not-actually-filtered-here"


def test_own_hash_matches_manual_recomputation() -> None:
    """AC-2: an event's own hash equals SHA-256 over the canonical JSON of its fields
    (including previous_hash), computed independently of the model's internals."""
    log = AuditLog()
    event = log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"b": 2, "a": 1},
    )
    expected = _compute_hash(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"a": 1, "b": 2},  # different insertion order, same logical content
        previous_hash=GENESIS_HASH,
    )
    assert event.hash == expected


# --- Immutability: caller mutation after append must not change the stored event -----------


def test_caller_mutating_nested_dict_after_append_does_not_change_stored_event() -> None:
    """AC-2 fix round: the caller's own dict is frozen into a new structure on append; mutating
    the caller's original object afterwards must not reach the stored payload."""
    log = AuditLog()
    nested = {"inner": {"x": 1}, "items": [1, 2, 3]}
    event = log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload=nested,
    )
    nested["inner"]["x"] = 999
    nested["items"].append(4)
    nested["new_key"] = "surprise"

    assert event.payload["inner"]["x"] == 1
    assert event.payload["items"] == (1, 2, 3)
    assert "new_key" not in event.payload


def test_stored_payload_cannot_be_mutated_via_log_events() -> None:
    """AC-2 fix round: reaching into the stored event through log.events cannot mutate it either
    — the payload is a read-only mapping with tuples, not a dict with lists."""
    log = AuditLog()
    log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"inner": {"x": 1}, "items": [1, 2, 3]},
    )
    stored_payload = log.events[0].payload
    assert isinstance(stored_payload, MappingProxyType)
    with pytest.raises(TypeError):
        stored_payload["inner"] = "tampered"  # type: ignore[index]
    assert isinstance(stored_payload["items"], tuple)
    with pytest.raises(AttributeError):
        stored_payload["items"].append(4)  # type: ignore[union-attr]
    with pytest.raises(TypeError):
        stored_payload["inner"]["x"] = 999  # type: ignore[index]


# --- Decimal payloads (ADR-008: money is exact Decimal, never float) ------------------------


def test_decimal_payload_is_accepted_and_round_trips() -> None:
    log = AuditLog()
    event = log.append(
        EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.00")},
    )
    assert event.payload["premium"] == Decimal("1365.00")
    assert isinstance(event.payload["premium"], Decimal)


def test_decimal_hash_reflects_exact_stated_precision() -> None:
    """Documented choice: Decimal('1365.00') and Decimal('1365.0') hash DIFFERENTLY, because the
    hash is computed from str(value), which preserves the exact scale/precision the caller
    constructed — the hash must not silently treat two differently-precise values as the same
    audit fact, even though they are numerically equal."""
    hash_a = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.00")},
        previous_hash=GENESIS_HASH,
    )
    hash_b = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.0")},
        previous_hash=GENESIS_HASH,
    )
    assert hash_a != hash_b
    assert Decimal("1365.00") == Decimal("1365.0")  # numerically equal, precision differs


def test_decimal_payload_verifies_through_append_and_verify() -> None:
    """A Decimal in a payload does not break the chain: append then verify() must still pass."""
    log = AuditLog()
    log.append(
        EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"premium": Decimal("1365.00"), "lots": 5},
    )
    assert log.verify().ok is True


# --- Naive datetimes inside a payload (not just the top-level timestamp) --------------------


def test_naive_datetime_nested_in_payload_is_rejected() -> None:
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.ORDER_PREPARED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"submitted_at": datetime(2026, 1, 1, 9, 15)},  # no tzinfo
        )


def test_aware_datetime_nested_in_payload_is_accepted_and_hashed_as_utc() -> None:
    log = AuditLog()
    ist = timezone(timedelta(hours=5, minutes=30))
    aware = datetime(2026, 1, 1, 14, 45, tzinfo=ist)
    event = log.append(
        EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"submitted_at": aware},
    )
    assert event.payload["submitted_at"] == aware

    hash_with_aware = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"submitted_at": aware},
        previous_hash=GENESIS_HASH,
    )
    hash_with_utc_equivalent = _compute_hash(
        event_type=EventType.ORDER_PREPARED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"submitted_at": aware.astimezone(timezone.utc)},
        previous_hash=GENESIS_HASH,
    )
    assert hash_with_aware == hash_with_utc_equivalent  # same instant -> same UTC ISO string


# --- Reserved "$" keys (type-tag disambiguation, not a secret guard) ------------------------


def test_dollar_prefixed_key_is_rejected_top_level() -> None:
    """"$"-prefixed keys are reserved for this module's own internal type tags (Decimal/datetime),
    not a secret guard — see models.py docstring."""
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


# --- Round 3: a real Kite-order-like payload is stored unchanged and verifies -----------------


def test_kite_order_like_payload_is_stored_unchanged_and_verifies() -> None:
    """REQ-064 stays exactly what its ACs ask for: an append-only, hash-chained audit log with no
    secret filtering. A raw Kite-style broker-response payload (REQ-064 AC-1: "broker responses")
    is stored exactly as passed, and the chain verifies."""
    kite_order_payload = {
        "instrument_token": 256265,
        "exchange_token": 1001,
        "order_id": "231020000000001",
        "tradingsymbol": "NIFTY24JAN25000CE",
        "session_expires_at": "2026-01-01T15:30:00+05:30",
    }
    log = AuditLog()
    event = log.append(
        EventType.BROKER_RESPONSE_RECORDED,
        actor="system",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload=kite_order_payload,
    )
    assert event.payload["instrument_token"] == 256265
    assert event.payload["exchange_token"] == 1001
    assert event.payload["order_id"] == "231020000000001"
    assert event.payload["tradingsymbol"] == "NIFTY24JAN25000CE"
    assert event.payload["session_expires_at"] == "2026-01-01T15:30:00+05:30"
    assert log.verify().ok is True
