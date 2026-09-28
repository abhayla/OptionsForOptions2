"""Append-only audit log: hash-chained events, no update or delete API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from ofo.audit.catalogue import EventType
from ofo.audit.models import GENESIS_HASH, AuditEvent


@dataclass(frozen=True)
class VerificationResult:
    """Result of :meth:`AuditLog.verify`."""

    ok: bool
    first_broken_index: Optional[int]


class AuditLog:
    """An append-only, hash-chained sequence of :class:`AuditEvent`.

    There is no update or delete method. The stored sequence is only readable as an immutable
    tuple via :attr:`events`. Any modification, deletion or reordering of a stored event (which
    can only happen by reaching directly into storage, never through this class's API) is
    detected by :meth:`verify`.
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(
        self,
        event_type: EventType,
        *,
        actor: str,
        timestamp: datetime,
        correlation_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Append and return a new event, linked to the current chain head."""
        previous_hash = self._events[-1].hash if self._events else GENESIS_HASH
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            timestamp=timestamp,
            correlation_id=correlation_id,
            payload=dict(payload) if payload is not None else {},
            previous_hash=previous_hash,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """The stored sequence, immutable to callers."""
        return tuple(self._events)

    def verify(self) -> VerificationResult:
        """Recompute the hash chain and report the first index where it breaks, if any.

        For each event, in order, this checks (a) that its ``previous_hash`` equals the actual
        hash of the previous event (or the genesis hash for the first event) and (b) that its
        own ``hash`` matches a fresh recomputation from its current field values. Either check
        failing means the stored record no longer matches what was appended.
        """
        expected_previous_hash = GENESIS_HASH
        for index, event in enumerate(self._events):
            if event.previous_hash != expected_previous_hash:
                return VerificationResult(ok=False, first_broken_index=index)
            if event.recompute_hash() != event.hash:
                return VerificationResult(ok=False, first_broken_index=index)
            expected_previous_hash = event.hash
        return VerificationResult(ok=True, first_broken_index=None)
