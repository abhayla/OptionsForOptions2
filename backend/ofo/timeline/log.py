"""A strategy's append-only, chronological, hash-chained activity timeline (REQ-040 AC-1, AC-2; REQ-064 AC-2).

This reuses the audit log's mechanism (``ofo.audit``) rather than a second one: the same canonical JSON (Decimal and
datetime tagged, reserved ``$`` keys refused), the same deep-freeze of stored content, the same genesis hash,
``HeadAnchor`` checkpoint and ``verify`` semantics. The audit log's ``AuditEvent`` itself is not reused because its
event type is the REQ-064 catalogue, and a timeline entry is a REQ-040 entry type, a trigger record or a follow-up.

There is no edit or delete method (AC-2). Entries are frozen; any change made by reaching into storage is found by
:meth:`Timeline.verify`, and a truncated tail by ``verify(expected_head=...)`` with an anchor kept elsewhere (see the
``ofo.audit.log`` module docstring for why the anchor must live outside the store it protects).

A trigger enters only through :meth:`Timeline.record_trigger` and a follow-up only through
:meth:`Timeline.record_follow_up`; :meth:`Timeline.append` refuses ``RULE_TRIGGERED`` so a trigger entry can never
exist without its full record.
"""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Union

from ofo.audit import GENESIS_HASH, AuditChainError, HeadAnchor, VerificationResult
from ofo.audit.models import _canonical_json, _check_payload_safe, _deep_freeze
from ofo.timeline.catalogue import EntryType, FollowUpKind
from ofo.timeline.records import FollowUp, RuleTriggerRecord
from ofo.timeline.why import why_did_this_trigger

MAX_ENTRIES = 100_000
MAX_DETAIL_CHARS = 16_384
MAX_ID_CHARS = 200
MAX_FUTURE_SKEW = datetime.timedelta(seconds=60)

Content = Union[Mapping[str, Any], RuleTriggerRecord, FollowUp]
Kind = Union[EntryType, FollowUpKind]


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_ID_CHARS:
        raise ValueError(f"{label} must be a non-empty string of at most {MAX_ID_CHARS} characters, got {value!r}")
    return value


def _content_payload(content: Content) -> Any:
    if isinstance(content, (RuleTriggerRecord, FollowUp)):
        return content.as_payload()
    return content


def _entry_hash(entry: "TimelineEntry") -> str:
    canonical = _canonical_json({
        "strategy_id": entry.strategy_id,
        "seq": entry.seq,
        "kind": f"{type(entry.kind).__name__}.{entry.kind.value}",
        "at": entry.at,
        "actor": entry.actor,
        "content": _content_payload(entry.content),
        "previous_hash": entry.previous_hash,
    })
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TimelineEntry:
    """One immutable timeline entry, linked into the strategy's chain by ``previous_hash``."""

    strategy_id: str
    seq: int
    kind: Kind
    at: datetime.datetime
    actor: str
    content: Content
    previous_hash: str = GENESIS_HASH
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        _require_id(self.strategy_id, "strategy_id")
        _require_id(self.actor, "actor")
        if isinstance(self.seq, bool) or not isinstance(self.seq, int) or self.seq < 0:
            raise ValueError(f"seq must be a non-negative integer, got {self.seq!r}")
        if not isinstance(self.kind, (EntryType, FollowUpKind)):
            raise ValueError(f"kind must be an EntryType or FollowUpKind, got {self.kind!r}")
        if not isinstance(self.at, datetime.datetime) or self.at.tzinfo is None:
            raise ValueError(f"entry time must be a timezone-aware datetime, got {self.at!r}")
        if isinstance(self.content, RuleTriggerRecord):
            if self.kind is not EntryType.RULE_TRIGGERED:
                raise ValueError("a trigger record is stored only as a RULE_TRIGGERED entry")
        elif isinstance(self.content, FollowUp):
            if self.kind is not self.content.kind:
                raise ValueError("a follow-up is stored only under its own follow-up kind")
        elif isinstance(self.content, Mapping):
            if not isinstance(self.kind, EntryType) or self.kind is EntryType.RULE_TRIGGERED:
                raise ValueError(f"{self.kind!r} cannot carry a plain detail mapping")
            _check_payload_safe(self.content)
            size = len(_canonical_json({"detail": self.content}))
            if size > MAX_DETAIL_CHARS:
                raise ValueError(f"entry detail is {size} characters; the limit is {MAX_DETAIL_CHARS}")
            object.__setattr__(self, "content", _deep_freeze(self.content))
        else:
            raise ValueError(f"unsupported entry content {self.content!r}")
        object.__setattr__(self, "hash", _entry_hash(self))

    def recompute_hash(self) -> str:
        return _entry_hash(self)


class Timeline:
    """One strategy's activity timeline. Append-only: there is no method that edits or removes an entry."""

    __slots__ = ("_strategy_id", "_clock", "_entries", "_follow_ups", "_recorded")

    def __init__(self, strategy_id: str, *, clock: Callable[[], datetime.datetime] = _utc_now) -> None:
        object.__setattr__(self, "_strategy_id", _require_id(strategy_id, "strategy_id"))
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_entries", [])
        object.__setattr__(self, "_follow_ups", {})  # trigger seq -> {FollowUpKind: FollowUp}
        object.__setattr__(self, "_recorded", {})  # RuleTriggerRecord -> its seq (duplicate check, O(1))

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"Timeline is append-only; cannot set {name!r}")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"Timeline is append-only; cannot delete {name!r}")

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def entries(self) -> tuple[TimelineEntry, ...]:
        """The chronological sequence, immutable to callers."""
        return tuple(self._entries)

    # ---- appending ----------------------------------------------------------------------------------------

    def append(
        self, entry_type: EntryType, *, at: datetime.datetime, actor: str, detail: Mapping[str, Any] | None = None
    ) -> TimelineEntry:
        """Append one AC-1 entry. A rule trigger must go through :meth:`record_trigger` instead."""
        if not isinstance(entry_type, EntryType):
            raise ValueError(f"entry_type must be an EntryType, got {entry_type!r}")
        if entry_type is EntryType.RULE_TRIGGERED:
            raise ValueError("a rule trigger is recorded with record_trigger(), which stores its full record")
        if detail is not None and not isinstance(detail, Mapping):
            raise ValueError(f"detail must be a mapping, got {detail!r}")
        return self._add(entry_type, at, actor, dict(detail or {}))

    def record_trigger(self, record: RuleTriggerRecord, *, actor: str = "rule-engine") -> TimelineEntry:
        """Append a RULE_TRIGGERED entry holding ``record``; its sequence number is the trigger's id."""
        if not isinstance(record, RuleTriggerRecord):
            raise ValueError(f"expected a RuleTriggerRecord, got {record!r}")
        if record in self._recorded:
            raise ValueError(f"this trigger is already recorded as entry {self._recorded[record]}")
        entry = self._add(EntryType.RULE_TRIGGERED, record.timestamp, actor, record)
        self._follow_ups[entry.seq] = {}
        self._recorded[record] = entry.seq
        return entry

    def record_follow_up(self, follow_up: FollowUp, *, actor: str = "system") -> TimelineEntry:
        """Append what followed a recorded trigger; each follow-up kind is recorded at most once per trigger."""
        if not isinstance(follow_up, FollowUp):
            raise ValueError(f"expected a FollowUp, got {follow_up!r}")
        known = self._follow_ups.get(follow_up.trigger_seq)
        if known is None:
            raise ValueError(f"entry {follow_up.trigger_seq} is not a rule trigger on this timeline")
        if follow_up.kind in known:
            raise ValueError(f"{follow_up.kind.value} is already recorded for trigger {follow_up.trigger_seq}")
        entry = self._add(follow_up.kind, follow_up.at, actor, follow_up)
        known[follow_up.kind] = follow_up
        return entry

    def _add(self, kind: Kind, at: object, actor: str, content: Content) -> TimelineEntry:
        if len(self._entries) >= MAX_ENTRIES:
            raise ValueError(f"a timeline holds at most {MAX_ENTRIES} entries")
        if not isinstance(at, datetime.datetime) or at.tzinfo is None:
            raise ValueError(f"entry time must be a timezone-aware datetime, got {at!r}")
        if at > self._clock() + MAX_FUTURE_SKEW:
            raise ValueError(f"entry time {at.isoformat()} is in the future")
        if self._entries and at < self._entries[-1].at:
            raise ValueError(f"entry time {at.isoformat()} is before the last entry "
                             f"({self._entries[-1].at.isoformat()}); the timeline is chronological")
        previous_hash = self._entries[-1].hash if self._entries else GENESIS_HASH
        entry = TimelineEntry(self._strategy_id, len(self._entries), kind, at, actor, content, previous_hash)
        self._entries.append(entry)
        return entry

    # ---- reading ------------------------------------------------------------------------------------------

    def trigger(self, seq: int) -> RuleTriggerRecord:
        if seq not in self._follow_ups:
            raise ValueError(f"entry {seq!r} is not a rule trigger on this timeline")
        return self._entries[seq].content  # type: ignore[return-value]

    def follow_ups(self, seq: int) -> tuple[FollowUp, ...]:
        """What followed trigger ``seq``, in the AC-4 order, only the kinds actually recorded."""
        self.trigger(seq)
        recorded = self._follow_ups[seq]
        return tuple(recorded[kind] for kind in FollowUpKind if kind in recorded)

    def why(self, seq: int) -> str:
        """'Why did this trigger?' for trigger ``seq``, answered only from its record and follow-ups (AC-5)."""
        return why_did_this_trigger(self.trigger(seq), self.follow_ups(seq))

    # ---- verification -------------------------------------------------------------------------------------

    def head(self) -> HeadAnchor:
        if not self._entries:
            return HeadAnchor(count=0, last_hash=GENESIS_HASH)
        return HeadAnchor(count=len(self._entries), last_hash=self._entries[-1].hash)

    def verify(self, expected_head: HeadAnchor | None = None) -> VerificationResult:
        """Recheck order, links and every entry's own hash; with an anchor, also detect a truncated tail."""
        expected_previous = GENESIS_HASH
        last_at: datetime.datetime | None = None
        triggers: set[int] = set()
        for index, entry in enumerate(self._entries):
            broken = (
                entry.seq != index
                or entry.strategy_id != self._strategy_id
                or entry.previous_hash != expected_previous
                or entry.recompute_hash() != entry.hash
                or (last_at is not None and entry.at < last_at)
                or (isinstance(entry.content, FollowUp) and entry.content.trigger_seq not in triggers)
            )
            if broken:
                return VerificationResult(ok=False, first_broken_index=index)
            if entry.kind is EntryType.RULE_TRIGGERED:
                triggers.add(index)
            expected_previous, last_at = entry.hash, entry.at
        if expected_head is not None:
            if len(self._entries) < expected_head.count:
                return VerificationResult(ok=False, first_broken_index=len(self._entries))
            checkpoint = GENESIS_HASH if expected_head.count == 0 else self._entries[expected_head.count - 1].hash
            if checkpoint != expected_head.last_hash:
                return VerificationResult(ok=False, first_broken_index=max(expected_head.count - 1, 0))
        return VerificationResult(ok=True, first_broken_index=None)

    @classmethod
    def from_entries(
        cls,
        strategy_id: str,
        entries: Iterable[TimelineEntry],
        *,
        expected_head: HeadAnchor | None = None,
        clock: Callable[[], datetime.datetime] = _utc_now,
    ) -> "Timeline":
        """Load a stored timeline, refusing one that fails verification (never work on a tampered history)."""
        timeline = cls(strategy_id, clock=clock)
        loaded = list(entries)
        if len(loaded) > MAX_ENTRIES:
            raise ValueError(f"a timeline holds at most {MAX_ENTRIES} entries")
        for entry in loaded:
            if not isinstance(entry, TimelineEntry):
                raise ValueError(f"expected TimelineEntry items, got {entry!r}")
        timeline._entries.extend(loaded)
        result = timeline.verify(expected_head)
        if not result.ok:
            raise AuditChainError(f"loaded timeline fails verification at entry {result.first_broken_index}")
        for entry in loaded:
            if entry.kind is EntryType.RULE_TRIGGERED:
                if entry.content in timeline._recorded:
                    raise AuditChainError(f"entry {entry.seq} repeats trigger {timeline._recorded[entry.content]}")
                timeline._follow_ups[entry.seq] = {}
                timeline._recorded[entry.content] = entry.seq
            elif isinstance(entry.content, FollowUp):
                recorded = timeline._follow_ups[entry.content.trigger_seq]
                if entry.content.kind in recorded:
                    raise AuditChainError(f"entry {entry.seq} repeats {entry.content.kind.value} for its trigger")
                recorded[entry.content.kind] = entry.content
        return timeline


