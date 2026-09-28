"""Append-only audit log: hash-chained events, no update or delete API.

This module does NOT filter secrets out of event payloads — see the ``models`` module docstring.
Callers must pass only the fields their event type needs; per-event-type field allowlisting is
REQ-063 AC-5, a separate, future work item, blocked until real Kite response fixtures are
available to prove the allowlist against.

Out of scope for W-015: the domain-model "timeline" records referenced alongside audit records in
REQ-064 AC-2 ("Audit and timeline records are append-only") are REQ-040, a separate, user-facing
feature (e.g. a strategy's activity timeline), and are not built here. This module only provides
the audit log itself.

On truncation (REQ-064 fix round, class: "tamper evidence that lives only inside the data it
protects"): a hash chain proves that every event PRESENT still links correctly to the one before
it, but it cannot prove anything about events that are no longer present — deleting the tail (or
all events) still leaves the remaining prefix perfectly self-consistent. Detecting that REQUIRES an
external anchor (:class:`HeadAnchor`: event count + hash of the last event) stored SEPARATELY from
the event store itself — e.g. a separate database table, an append-only file, or a checkpoint
signed with a key the application does not hold — because an anchor stored alongside the events it
protects can be truncated along with them, and would no longer detect anything. This module does
not implement that separate store; it only provides the anchor value to persist
(:meth:`AuditLog.head`) and the check against it (:meth:`AuditLog.verify` with ``expected_head``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from ofo.audit.catalogue import EventType
from ofo.audit.models import GENESIS_HASH, AuditEvent


@dataclass(frozen=True)
class VerificationResult:
    """Result of :meth:`AuditLog.verify`."""

    ok: bool
    first_broken_index: Optional[int]


@dataclass(frozen=True)
class HeadAnchor:
    """An external checkpoint on the chain: how many events existed, and the last one's hash.

    Must be persisted separately from the event store itself (a separate table/file, or a signed
    checkpoint) — an anchor stored alongside the events it protects can be truncated along with
    them, and would no longer detect anything.
    """

    count: int
    last_hash: str


class AuditChainError(ValueError):
    """Raised when a loaded event sequence fails chain or anchor verification."""


class AuditLog:
    """An append-only, hash-chained sequence of :class:`AuditEvent`.

    There is no update or delete method. The stored sequence is only readable as an immutable
    tuple via :attr:`events`. Any modification, deletion or reordering of a stored event (which
    can only happen by reaching directly into storage, never through this class's API) is
    detected by :meth:`verify` — deletion of a *tail* of events additionally requires an
    :class:`HeadAnchor` checkpoint (see the module docstring) since a shortened-but-internally-
    consistent chain has nothing wrong with the links it still has.
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
            payload=payload if payload is not None else {},
            previous_hash=previous_hash,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """The stored sequence, immutable to callers."""
        return tuple(self._events)

    def head(self) -> HeadAnchor:
        """The current checkpoint (event count + hash of the last event) to persist externally."""
        if not self._events:
            return HeadAnchor(count=0, last_hash=GENESIS_HASH)
        return HeadAnchor(count=len(self._events), last_hash=self._events[-1].hash)

    def verify(self, expected_head: HeadAnchor | None = None) -> VerificationResult:
        """Recompute the hash chain and report the first index where it breaks, if any.

        For each event, in order, this checks (a) that its ``previous_hash`` equals the actual
        hash of the previous event (or the genesis hash for the first event) and (b) that its
        own ``hash`` matches a fresh recomputation from its current field values. Either check
        failing means the stored record no longer matches what was appended.

        This alone CANNOT detect a truncated tail (see module docstring): pass ``expected_head``
        (a :class:`HeadAnchor` captured earlier and persisted separately) to additionally check
        that the log is at least as long as the anchor attests, and that the event at the
        anchor's checkpoint still has the anchored hash (a prefix check — events appended after
        the anchor was taken do not invalidate it).
        """
        expected_previous_hash = GENESIS_HASH
        for index, event in enumerate(self._events):
            if event.previous_hash != expected_previous_hash:
                return VerificationResult(ok=False, first_broken_index=index)
            if event.recompute_hash() != event.hash:
                return VerificationResult(ok=False, first_broken_index=index)
            expected_previous_hash = event.hash

        if expected_head is not None:
            current_count = len(self._events)
            if current_count < expected_head.count:
                # The chain is shorter than attested: the first missing event is at this index.
                return VerificationResult(ok=False, first_broken_index=current_count)
            checkpoint_hash = (
                GENESIS_HASH if expected_head.count == 0 else self._events[expected_head.count - 1].hash
            )
            if checkpoint_hash != expected_head.last_hash:
                return VerificationResult(
                    ok=False, first_broken_index=max(expected_head.count - 1, 0)
                )

        return VerificationResult(ok=True, first_broken_index=None)

    @classmethod
    def from_events(
        cls, events: Iterable[AuditEvent], expected_head: HeadAnchor | None = None
    ) -> "AuditLog":
        """Load a previously stored sequence, verifying it (optionally against an anchor) first.

        Raises :class:`AuditChainError` if the loaded sequence fails verification, so a caller
        can never silently start working against a tampered or truncated log.
        """
        log = cls()
        log._events = list(events)
        result = log.verify(expected_head)
        if not result.ok:
            raise AuditChainError(
                f"loaded audit events fail verification at index {result.first_broken_index}"
            )
        return log
