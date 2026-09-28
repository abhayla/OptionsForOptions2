"""AC-2 fix round: a hash chain alone cannot see its own tail removed; an external anchor can.

Class: tamper evidence that lives only inside the data it protects. Removing the last N events
(or all of them) leaves the remaining prefix perfectly self-consistent — internal per-link
verification has nothing to detect. Proof below: with no anchor, verify() reports ok=True after
truncating; with a HeadAnchor captured before the truncation and checked via
verify(expected_head=...), it correctly fails, at the index of the first missing event.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditChainError, AuditLog, HeadAnchor

BASE_TIME = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)


def _build_log(n: int) -> AuditLog:
    log = AuditLog()
    for index in range(n):
        log.append(
            EventType.STRATEGY_CHANGED,
            actor=f"user-{index}",
            timestamp=BASE_TIME + timedelta(seconds=index),
            correlation_id=f"corr-{index}",
            payload={"index": index},
        )
    return log


def test_internal_only_verify_does_not_see_truncation() -> None:
    """Documents the defect this fix addresses: verify() with no anchor is blind to a
    truncated tail, because the remaining prefix is still perfectly self-consistent."""
    log = _build_log(5)
    del log._events[-3:]
    assert log.verify().ok is True  # by design: this is exactly why an anchor is needed


def test_truncate_last_one_detected_by_anchor() -> None:
    log = _build_log(5)
    anchor = log.head()
    assert anchor.count == 5
    del log._events[-1:]
    result = log.verify(expected_head=anchor)
    assert result.ok is False
    assert result.first_broken_index == 4


def test_truncate_last_three_detected_by_anchor() -> None:
    log = _build_log(5)
    anchor = log.head()
    del log._events[-3:]
    result = log.verify(expected_head=anchor)
    assert result.ok is False
    assert result.first_broken_index == 2


def test_truncate_all_detected_by_anchor() -> None:
    log = _build_log(5)
    anchor = log.head()
    del log._events[:]
    result = log.verify(expected_head=anchor)
    assert result.ok is False
    assert result.first_broken_index == 0


def test_head_on_empty_log() -> None:
    log = AuditLog()
    anchor = log.head()
    assert anchor.count == 0


def test_legitimate_append_after_anchor_still_verifies_against_older_anchor() -> None:
    """An anchor taken mid-way through still passes: appending more events afterwards is legal,
    not tampering, and a prefix check must not reject it."""
    log = _build_log(5)
    older_anchor = log.head()
    log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-5",
        timestamp=BASE_TIME + timedelta(seconds=5),
        correlation_id="corr-5",
        payload={"index": 5},
    )
    result = log.verify(expected_head=older_anchor)
    assert result.ok is True


def test_legitimate_append_after_anchor_verifies_against_new_head() -> None:
    log = _build_log(5)
    log.append(
        EventType.STRATEGY_CHANGED,
        actor="user-5",
        timestamp=BASE_TIME + timedelta(seconds=5),
        correlation_id="corr-5",
        payload={"index": 5},
    )
    new_anchor = log.head()
    assert new_anchor.count == 6
    result = log.verify(expected_head=new_anchor)
    assert result.ok is True


def test_anchor_hash_mismatch_at_same_count_detected() -> None:
    """A forged log with the right event COUNT but the wrong content at the checkpoint (e.g. a
    replayed/rebuilt chain) is still caught: the anchor pins the hash, not just the length."""
    log = _build_log(5)
    real_anchor = log.head()
    forged_anchor = HeadAnchor(count=real_anchor.count, last_hash="f" * 64)
    result = log.verify(expected_head=forged_anchor)
    assert result.ok is False
    assert result.first_broken_index == real_anchor.count - 1


def test_from_events_loads_a_valid_chain() -> None:
    log = _build_log(5)
    anchor = log.head()
    reloaded = AuditLog.from_events(log.events, expected_head=anchor)
    assert len(reloaded.events) == 5
    assert reloaded.verify(expected_head=anchor).ok is True


def test_from_events_rejects_a_truncated_chain() -> None:
    log = _build_log(5)
    anchor = log.head()
    truncated_events = log.events[:2]
    with pytest.raises(AuditChainError):
        AuditLog.from_events(truncated_events, expected_head=anchor)


def test_from_events_rejects_a_broken_internal_chain_even_without_an_anchor() -> None:
    log = _build_log(5)
    events = list(log.events)
    events[2], events[3] = events[3], events[2]
    with pytest.raises(AuditChainError):
        AuditLog.from_events(events)
