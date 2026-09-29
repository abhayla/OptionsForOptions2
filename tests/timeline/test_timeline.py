"""REQ-040 AC-1 (every entry type, append-only, chronological) and AC-2 (entries never edited or deleted).

The AC-1 list is read from spec/requirements/REQ-040.md on disk (never copied here), so an edit to the spec's list
fails this test until the EntryType enum matches.
"""
from __future__ import annotations

import dataclasses
import datetime
import time

import pytest

from ofo.audit import AuditChainError
from ofo.timeline import ENTRY_SPEC_PHRASES, EntryType, FollowUp, FollowUpKind, RuleTriggerRecord, Timeline
from ofo.timeline.log import MAX_DETAIL_CHARS, TimelineEntry

from timeline_fixtures import CHECKED_AT, IST, MAX_LOSS_RULE, ac_text, clock, executed_record, loss_evaluation

T = datetime.datetime(2026, 10, 20, 9, 15, tzinfo=IST)


def parse_ac1(text: str) -> list[str]:
    listed = text.split("recording:", 1)[1].strip().rstrip(".")
    return [" ".join(part.split()).lower() for part in listed.split(",") if part.strip()]


def at(minutes: int) -> datetime.datetime:
    return T + datetime.timedelta(minutes=minutes)


def timeline() -> Timeline:
    return Timeline("strat-ic-1", clock=clock)


# ---- AC-1 ----------------------------------------------------------------------------------------------------


def test_entry_types_match_the_ac1_list_on_disk():
    """AC-1: every entry type REQ-040 AC-1 names has exactly one EntryType member, and no member is extra."""
    phrases = parse_ac1(ac_text("AC-1"))
    assert len(phrases) == 16 and len(set(phrases)) == 16
    assert set(ENTRY_SPEC_PHRASES.values()) == set(phrases)
    assert set(ENTRY_SPEC_PHRASES) == set(EntryType)


def test_every_entry_type_is_recorded_in_chronological_order():
    """AC-1: one timeline holds every AC-1 entry type in time order; a rule trigger enters with its record."""
    tl = timeline()
    record = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(),
                                               strategy=executed_record())
    minute = 0
    for entry_type in EntryType:
        if entry_type is EntryType.RULE_TRIGGERED:
            continue
        tl.append(entry_type, at=at(minute), actor="user-1", detail={"note": entry_type.value})
        minute += 1
    trigger = tl.record_trigger(record)  # CHECKED_AT 10:00 is after the 15 entries from 09:15
    assert [e.seq for e in tl.entries] == list(range(16))
    assert {e.kind for e in tl.entries} == set(EntryType)
    assert trigger.kind is EntryType.RULE_TRIGGERED and trigger.at == CHECKED_AT
    assert [e.at for e in tl.entries] == sorted(e.at for e in tl.entries)
    assert tl.verify().ok


def test_backdated_future_naive_and_bypass_entries_are_refused():
    """AC-1 negative: an entry earlier than the last one, in the future, timezone-naive, a rule trigger without its
    record, or a non-EntryType is refused, and the timeline is unchanged."""
    tl = timeline()
    tl.append(EntryType.CREATED, at=at(5), actor="user-1")
    with pytest.raises(ValueError, match="chronological"):
        tl.append(EntryType.MODIFIED, at=at(4), actor="user-1")
    with pytest.raises(ValueError, match="future"):
        tl.append(EntryType.MODIFIED, at=clock() + datetime.timedelta(minutes=5), actor="user-1")
    with pytest.raises(ValueError, match="timezone-aware"):
        tl.append(EntryType.MODIFIED, at=datetime.datetime(2026, 10, 20, 9, 30), actor="user-1")
    with pytest.raises(ValueError, match="record_trigger"):
        tl.append(EntryType.RULE_TRIGGERED, at=at(6), actor="user-1", detail={"rule": "ml-3000"})
    with pytest.raises(ValueError, match="EntryType"):
        tl.append("created", at=at(6), actor="user-1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="actor"):
        tl.append(EntryType.MODIFIED, at=at(6), actor="")
    with pytest.raises(ValueError, match="reserved"):
        tl.append(EntryType.MODIFIED, at=at(6), actor="user-1", detail={"$decimal": "1"})
    with pytest.raises(ValueError, match="limit"):
        tl.append(EntryType.MODIFIED, at=at(6), actor="user-1", detail={"note": "x" * MAX_DETAIL_CHARS})
    with pytest.raises(ValueError, match="strategy_id"):
        Timeline("")
    assert len(tl.entries) == 1 and tl.verify().ok


def test_same_time_entries_are_allowed_and_1000_appends_stay_fast():
    """AC-1: two events in the same instant keep their append order; 1,000 one-by-one appends take well under 2 s
    (append never re-verifies the whole history)."""
    tl = timeline()
    started = time.perf_counter()
    for i in range(1000):
        tl.append(EntryType.MODIFIED, at=at(i // 10), actor="user-1", detail={"i": i})
    assert time.perf_counter() - started < 2.0
    assert [e.content["i"] for e in tl.entries] == list(range(1000))
    assert tl.verify().ok


# ---- AC-2 ----------------------------------------------------------------------------------------------------


def test_there_is_no_edit_or_delete_api():
    """AC-2: the timeline has no method that edits or removes an entry, and its attributes cannot be replaced."""
    public = {name for name in dir(Timeline) if not name.startswith("_")}
    assert public == {"append", "record_trigger", "record_follow_up", "entries", "strategy_id", "trigger",
                      "follow_ups", "why", "head", "verify", "from_entries"}
    tl = timeline()
    tl.append(EntryType.CREATED, at=at(0), actor="user-1")
    with pytest.raises(AttributeError):
        tl._entries = []  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del tl._entries
    with pytest.raises(TypeError):
        del tl.entries[0]  # type: ignore[attr-defined]
    assert len(tl.entries) == 1


def test_entries_and_their_content_are_immutable():
    """AC-2: an entry, its detail mapping and a stored trigger record cannot be changed through normal Python APIs;
    the caller's own dict is copied, so changing it afterwards changes nothing stored."""
    tl = timeline()
    detail = {"note": "first", "legs": [1, 2]}
    entry = tl.append(EntryType.CREATED, at=at(0), actor="user-1", detail=detail)
    detail["note"] = "changed"
    detail["legs"].append(3)
    assert entry.content["note"] == "first" and entry.content["legs"] == (1, 2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.actor = "someone-else"  # type: ignore[misc]
    with pytest.raises(TypeError):
        entry.content["note"] = "edited"  # type: ignore[index]
    record = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(),
                                               strategy=executed_record())
    stored = tl.record_trigger(record).content
    with pytest.raises(dataclasses.FrozenInstanceError):
        stored.source = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="from_evaluation"):
        dataclasses.replace(stored, source="other")
    assert tl.verify().ok


def test_edit_or_delete_by_reaching_into_storage_is_detected():
    """AC-2: a change forced past the frozen dataclass, a deleted middle entry, a reorder, and a truncated tail
    (with a head anchor kept elsewhere) each fail verification, and from_entries refuses to load them."""
    def build() -> Timeline:
        tl = timeline()
        for i, kind in enumerate((EntryType.CREATED, EntryType.VALIDATED, EntryType.ACTIVATED)):
            tl.append(kind, at=at(i), actor="user-1", detail={"i": i})
        record = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(),
                                                   strategy=executed_record())
        seq = tl.record_trigger(record).seq
        tl.record_follow_up(FollowUp(FollowUpKind.EXECUTED, seq, CHECKED_AT, False))
        return tl

    edited = build()
    object.__setattr__(edited.entries[1], "actor", "attacker")
    assert edited.verify().first_broken_index == 1

    edited_record = build()
    trigger = edited_record.entries[3].content
    object.__setattr__(trigger, "data_health", trigger.data_health.__class__.STALE)
    assert edited_record.verify().first_broken_index == 3

    original = build()
    anchor = original.head()
    entries = list(original.entries)
    with pytest.raises(AuditChainError):
        Timeline.from_entries("strat-ic-1", entries[:1] + entries[2:], clock=clock)  # middle deleted
    with pytest.raises(AuditChainError):
        Timeline.from_entries("strat-ic-1", [entries[1], entries[0]] + entries[2:], clock=clock)  # reordered
    with pytest.raises(AuditChainError):
        Timeline.from_entries("strat-ic-1", entries[:-1], expected_head=anchor, clock=clock)  # tail truncated
    with pytest.raises(AuditChainError):
        Timeline.from_entries("other-strategy", entries, clock=clock)  # another strategy's history
    loaded = Timeline.from_entries("strat-ic-1", entries, expected_head=anchor, clock=clock)
    assert loaded.follow_ups(3)[0].answer is False and loaded.trigger(3) == original.trigger(3)


def test_a_forged_entry_cannot_be_built_with_the_wrong_content():
    """AC-2 negative: a RULE_TRIGGERED entry with a plain dict, or a follow-up under another kind, is refused."""
    with pytest.raises(ValueError, match="plain detail"):
        TimelineEntry("strat-ic-1", 0, EntryType.RULE_TRIGGERED, at(0), "user-1", {"rule": "ml-3000"})
    follow_up = FollowUp(FollowUpKind.EXECUTED, 0, at(0), True)
    with pytest.raises(ValueError, match="its own follow-up kind"):
        TimelineEntry("strat-ic-1", 1, FollowUpKind.ALERT_GENERATED, at(0), "user-1", follow_up)
