"""AC-2: audit records are append-only; a hash chain makes any modification detectable.

Core proof (W-015): append one event of every catalogued type, verify the chain is OK, then
tamper (change a payload value, delete an event, reorder two events, insert a forged event) and
assert verify() reports failure at the correct index each time.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

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


def test_secret_looking_payload_keys_are_rejected() -> None:
    """AC-2: payload keys that look like secrets are rejected, never logged."""
    log = AuditLog()
    for bad_key in ("password", "Password", "api_key", "API-KEY", "secret_token", "user_token"):
        with pytest.raises(PayloadValidationError):
            log.append(
                EventType.SECURITY_EVENT_RECORDED,
                actor="user-1",
                timestamp=BASE_TIME,
                correlation_id="corr-1",
                payload={bad_key: "value"},
            )


def test_secret_looking_key_nested_in_payload_is_rejected() -> None:
    """AC-2: the secret-key guard checks nested dicts and lists, not only the top level."""
    log = AuditLog()
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"details": {"nested": {"api_key": "sk-123"}}},
        )
    with pytest.raises(PayloadValidationError):
        log.append(
            EventType.SECURITY_EVENT_RECORDED,
            actor="user-1",
            timestamp=BASE_TIME,
            correlation_id="corr-1",
            payload={"items": [{"access_token": "abc"}]},
        )


def test_ordinary_payload_keys_are_accepted() -> None:
    """AC-2: payload keys that merely contain safe substrings are not falsely rejected."""
    log = AuditLog()
    event = log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"strategy_id": "S-1", "amount": "1000.00", "note": "rebalanced"},
    )
    assert event.payload["strategy_id"] == "S-1"


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
