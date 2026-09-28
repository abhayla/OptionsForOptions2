"""Tier A: tests that fail if verify() skipped the previous-hash check, or hashing used a
non-canonical (key-order-dependent) serialisation.

Each test below isolates exactly one of the two properties AuditLog.verify() depends on. Comment
out the previous-hash check in log.py, or drop ``sort_keys=True`` from _canonical_json in
models.py, and the corresponding test here fails — proving the real implementation needs both.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.audit.models import GENESIS_HASH, _compute_hash

BASE_TIME = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


def _own_hash_only_verify(log: AuditLog) -> tuple[bool, int | None]:
    """A deliberately weakened verify(): checks each event's own hash, but never checks that
    ``previous_hash`` actually links to its predecessor. This is the mutant described in this
    module's docstring, reproduced here (not in production code) to prove the real check matters."""
    for index, event in enumerate(log._events):
        if event.recompute_hash() != event.hash:
            return False, index
    return True, None


def test_previous_hash_check_is_necessary_to_detect_a_deleted_middle_event() -> None:
    """A deleted middle event leaves every REMAINING event internally self-consistent (each
    event's own hash still matches its own unchanged fields) — only the previous_hash linkage
    breaks. A verify() that skipped the previous-hash check would report this log as OK; the real
    AuditLog.verify() must not."""
    log = AuditLog()
    for index, event_type in enumerate(list(EventType)[:6]):
        log.append(
            event_type,
            actor=f"user-{index}",
            timestamp=BASE_TIME + timedelta(seconds=index),
            correlation_id=f"corr-{index}",
            payload={"index": index},
        )
    del log._events[3]

    weakened_ok, _ = _own_hash_only_verify(log)
    assert weakened_ok is True, "the weakened, own-hash-only check should miss this tamper"

    real_result = log.verify()
    assert real_result.ok is False
    assert real_result.first_broken_index == 3


def test_canonical_serialisation_is_key_order_independent() -> None:
    """The same logical payload, built with keys inserted in a different order, must hash
    identically. A serialiser that used dict insertion order instead of sorted keys would produce
    two different hashes here for the same logical event."""
    payload_a = {}
    payload_a["alpha"] = 1
    payload_a["beta"] = 2
    payload_a["gamma"] = 3

    payload_b = {}
    payload_b["gamma"] = 3
    payload_b["alpha"] = 1
    payload_b["beta"] = 2

    assert list(payload_a.keys()) != list(payload_b.keys())

    hash_a = _compute_hash(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload=payload_a,
        previous_hash=GENESIS_HASH,
    )
    hash_b = _compute_hash(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload=payload_b,
        previous_hash=GENESIS_HASH,
    )
    assert hash_a == hash_b


def test_canonical_serialisation_still_distinguishes_different_content() -> None:
    """Guard against a canonicaliser so aggressive it hides real differences: a genuinely
    different payload value must still change the hash."""
    hash_a = _compute_hash(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"amount": "1000.00"},
        previous_hash=GENESIS_HASH,
    )
    hash_b = _compute_hash(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"amount": "9999.99"},
        previous_hash=GENESIS_HASH,
    )
    assert hash_a != hash_b


def test_previous_hash_is_part_of_the_hashed_content() -> None:
    """Two events with identical type/actor/timestamp/correlation_id/payload but different
    previous_hash must hash differently — proving previous_hash is inside the hashed content, not
    just an unhashed sidecar field a forger could freely rewrite."""
    common = dict(
        event_type=EventType.STRATEGY_CHANGED,
        actor="user-1",
        timestamp=BASE_TIME,
        correlation_id="corr-1",
        payload={"amount": "1000.00"},
    )
    hash_a = _compute_hash(previous_hash=GENESIS_HASH, **common)
    hash_b = _compute_hash(previous_hash="a" * 64, **common)
    assert hash_a != hash_b
