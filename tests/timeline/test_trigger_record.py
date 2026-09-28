"""REQ-040 AC-3 (a trigger records rule, exact inputs, threshold, timestamp, source, data health, active version) and
AC-4 (it records what followed, linked to the trigger).

The AC-4 list is read from spec/requirements/REQ-040.md on disk, so FollowUpKind cannot drift from the spec.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from ofo.rules import (
    AnyOf,
    Compare,
    DataHealth,
    InputName,
    Observation,
    Op,
    Outcome,
    Rule,
    RuleAction,
    RuleKind,
    Snapshot,
    evaluate,
)
from ofo.timeline import FOLLOW_UP_SPEC_PHRASES, EntryType, FollowUp, FollowUpKind, RuleTriggerRecord, Timeline

from timeline_fixtures import (
    ac_text,
    CHECKED_AT,
    EXPECTED_LOSS_PNL,
    EXPECTED_THRESHOLD,
    GOLDEN,
    MAX_LOSS_RULE,
    SOURCE,
    STRESSED,
    clock,
    executed_record,
    loss_evaluation,
    snapshot,
)


def active():
    return executed_record().active_version


def record() -> RuleTriggerRecord:
    return RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(), active_version=active())


# ---- AC-3 ----------------------------------------------------------------------------------------------------


def test_trigger_record_holds_every_ac3_field_from_the_evaluation():
    """AC-3: which rule (id and text), the exact live P&L -3450.00 against threshold -3000 (hand computation), the
    timestamp, market-data source, data health and active version 1 (from a real executed StrategyRecord)."""
    r = record()
    assert (r.rule_id, r.rule_text, r.rule_kind, r.action) == (
        "ml-3000", "Max loss 3000", RuleKind.EXIT, RuleAction.ALERT_AND_PREPARE_ORDERS)
    assert r.observations == (Observation(InputName.LIVE_PNL, Op.LTE, EXPECTED_THRESHOLD, EXPECTED_LOSS_PNL, True),)
    assert str(r.observations[0].value) == "-3450.00"  # exact scale kept, not re-rounded
    assert r.missing == ()
    assert r.timestamp == CHECKED_AT and r.source == SOURCE and r.data_health is DataHealth.AVAILABLE
    assert r.active_version == 1


def test_or_rule_records_the_deciding_values_and_the_unavailable_inputs():
    """AC-3: an OR rule triggered by one proven branch records that branch's exact value and names the input it could
    not read (IV missing), so the record shows what was not known."""
    rule = Rule("or-1", RuleKind.EXIT, AnyOf((Compare(InputName.LIVE_PNL, Op.LTE, D("-3000")),
                                              Compare(InputName.IV, Op.GTE, D("25")))),
                RuleAction.ALERT_ONLY, "Loss 3000 or IV 25")
    evaluation = evaluate(rule, snapshot(STRESSED))
    assert evaluation.outcome is Outcome.TRIGGERED
    r = RuleTriggerRecord.from_evaluation(rule, evaluation, active_version=active())
    assert r.observations == (Observation(InputName.LIVE_PNL, Op.LTE, D("-3000"), D("-3450.00"), True),)
    assert r.missing == (InputName.IV,)


def test_only_a_real_triggered_evaluation_becomes_a_record():
    """AC-3 negative: the golden LTPs (+1365.00, spec §6) do not trigger a max loss of 3000, so no record; a record
    cannot be constructed directly or copied with changed values; source 'unspecified', a mismatched rule, an exit
    rule without an active version, and a forged observation are all refused."""
    not_triggered = evaluate(MAX_LOSS_RULE, snapshot(GOLDEN))
    assert not_triggered.outcome is Outcome.NOT_TRIGGERED
    with pytest.raises(ValueError, match="only a triggered evaluation"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, not_triggered, active_version=active())
    stale = loss_evaluation(health=DataHealth.STALE)
    assert stale.outcome is Outcome.CANNOT_EVALUATE
    with pytest.raises(ValueError, match="only a triggered evaluation"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, stale, active_version=active())

    with pytest.raises(ValueError, match="from_evaluation"):
        RuleTriggerRecord("ml-3000", "Max loss 3000", RuleKind.EXIT, RuleAction.ALERT_ONLY, (), (), CHECKED_AT,
                          SOURCE, DataHealth.AVAILABLE, 1)
    with pytest.raises(ValueError, match="from_evaluation"):
        dataclasses.replace(record(), active_version=2)
    with pytest.raises(ValueError, match="unspecified"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(source="unspecified"), active_version=active())
    other = Rule("ml-3000", RuleKind.EXIT, Compare(InputName.LIVE_PNL, Op.LTE, D("-3000")), RuleAction.ALERT_ONLY,
                 "Max loss 3000")
    with pytest.raises(ValueError, match="does not belong"):
        RuleTriggerRecord.from_evaluation(other, loss_evaluation(), active_version=active())
    with pytest.raises(ValueError, match="active strategy version"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(), active_version=None)
    with pytest.raises(ValueError, match="Version or None"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, loss_evaluation(), active_version=1)  # type: ignore[arg-type]
    undescribed = Rule("u-1", RuleKind.EXIT, Compare(InputName.LIVE_PNL, Op.LTE, D("-3000")), RuleAction.ALERT_ONLY)
    with pytest.raises(ValueError, match="rule text"):
        RuleTriggerRecord.from_evaluation(undescribed, evaluate(undescribed, snapshot(STRESSED)),
                                          active_version=active())
    forged_value = dataclasses.replace(loss_evaluation(), observations=(
        Observation(InputName.LIVE_PNL, Op.LTE, D("-3000"), D("-2000"), True),))  # -2000 is not <= -3000
    with pytest.raises(ValueError, match="does not hold"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, forged_value, active_version=active())
    forged_threshold = dataclasses.replace(loss_evaluation(), observations=(
        Observation(InputName.LIVE_PNL, Op.LTE, D("-1000"), D("-3450.00"), True),))
    with pytest.raises(ValueError, match="not a comparison of this rule"):
        RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, forged_threshold, active_version=active())


def test_the_same_trigger_cannot_be_recorded_twice():
    """AC-3 negative: recording an identical trigger record a second time is refused (one trigger, one record)."""
    tl = Timeline("strat-ic-1", clock=clock)
    tl.record_trigger(record())
    with pytest.raises(ValueError, match="already recorded"):
        tl.record_trigger(record())
    later = RuleTriggerRecord.from_evaluation(
        MAX_LOSS_RULE, loss_evaluation(at=CHECKED_AT + datetime.timedelta(minutes=1)), active_version=active())
    assert tl.record_trigger(later).seq == 1  # a new evaluation a minute later is a new trigger


# ---- AC-4 ----------------------------------------------------------------------------------------------------


def parse_ac4(text: str) -> list[str]:
    listed = text.split("followed:", 1)[1].strip().rstrip(".")
    phrases = []
    for part in listed.split(","):
        part = part.strip().removeprefix("and ").rstrip("?").strip()
        if part:
            phrases.append(" ".join(part.split()).lower())
    return phrases


def test_follow_up_kinds_match_the_ac4_list_on_disk():
    """AC-4: every follow-up REQ-040 AC-4 names has exactly one FollowUpKind member, and none is extra."""
    phrases = parse_ac4(ac_text("AC-4"))
    assert len(phrases) == 6
    assert set(FOLLOW_UP_SPEC_PHRASES.values()) == set(phrases)
    assert set(FOLLOW_UP_SPEC_PHRASES) == set(FollowUpKind)


def test_follow_ups_are_linked_to_their_trigger_on_the_timeline():
    """AC-4: alert, order prepared, confirmation, executed, broker report and reconciliation result are recorded
    against trigger 0, in order, as timeline entries that verify; another trigger's follow-ups stay separate."""
    tl = Timeline("strat-ic-1", clock=clock)
    first = tl.record_trigger(record()).seq
    later = RuleTriggerRecord.from_evaluation(
        MAX_LOSS_RULE, loss_evaluation(at=CHECKED_AT + datetime.timedelta(minutes=10)), active_version=active())
    minute = CHECKED_AT + datetime.timedelta(minutes=1)
    answers = [(FollowUpKind.ALERT_GENERATED, True), (FollowUpKind.ORDER_PREPARED, True),
               (FollowUpKind.CONFIRMATION_REQUIRED, True), (FollowUpKind.EXECUTED, True),
               (FollowUpKind.BROKER_REPORTED, "COMPLETE: 4 of 4 exit orders filled"),
               (FollowUpKind.RECONCILIATION_SUCCEEDED, True)]
    for kind, answer in answers:
        entry = tl.record_follow_up(FollowUp(kind, first, minute, answer))
        assert entry.kind is kind and entry.content.trigger_seq == first
    second = tl.record_trigger(later).seq
    assert [(f.kind, f.answer) for f in tl.follow_ups(first)] == answers
    assert tl.follow_ups(second) == ()
    assert tl.entries[second].kind is EntryType.RULE_TRIGGERED
    assert tl.verify().ok


def test_follow_up_input_is_validated():
    """AC-4 negative: a follow-up for an unknown trigger or a non-trigger entry, the same kind twice, a yes/no kind
    with text, an empty broker report, a naive time, or a time before the trigger is refused."""
    tl = Timeline("strat-ic-1", clock=clock)
    created = tl.append(EntryType.CREATED, at=CHECKED_AT - datetime.timedelta(hours=1), actor="user-1").seq
    seq = tl.record_trigger(record()).seq
    with pytest.raises(ValueError, match="not a rule trigger"):
        tl.record_follow_up(FollowUp(FollowUpKind.EXECUTED, 99, CHECKED_AT, True))
    with pytest.raises(ValueError, match="not a rule trigger"):
        tl.record_follow_up(FollowUp(FollowUpKind.EXECUTED, created, CHECKED_AT, True))
    tl.record_follow_up(FollowUp(FollowUpKind.EXECUTED, seq, CHECKED_AT, False))
    with pytest.raises(ValueError, match="already recorded"):
        tl.record_follow_up(FollowUp(FollowUpKind.EXECUTED, seq, CHECKED_AT, True))
    with pytest.raises(ValueError, match="yes/no"):
        FollowUp(FollowUpKind.ALERT_GENERATED, seq, CHECKED_AT, "yes")
    with pytest.raises(ValueError, match="yes/no"):
        FollowUp(FollowUpKind.EXECUTED, seq, CHECKED_AT, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="broker report"):
        FollowUp(FollowUpKind.BROKER_REPORTED, seq, CHECKED_AT, "  ")
    with pytest.raises(ValueError, match="broker report"):
        FollowUp(FollowUpKind.BROKER_REPORTED, seq, CHECKED_AT, True)
    with pytest.raises(ValueError, match="timezone-aware"):
        FollowUp(FollowUpKind.EXECUTED, seq, datetime.datetime(2026, 10, 20, 10, 5), True)
    with pytest.raises(ValueError, match="trigger_seq"):
        FollowUp(FollowUpKind.EXECUTED, True, CHECKED_AT, True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="chronological"):
        tl.record_follow_up(FollowUp(FollowUpKind.ALERT_GENERATED, seq, CHECKED_AT - datetime.timedelta(minutes=1),
                                     True))
    assert len(tl.entries) == 3 and tl.verify().ok


def test_snapshot_health_override_is_what_the_record_shows():
    """AC-3: the record's data health is the evaluation's snapshot health as recorded (no upgrade): a snapshot whose
    overall health is 'delayed' but whose live P&L input is marked available still records 'delayed'."""
    snap = Snapshot({InputName.LIVE_PNL: D("-3450.00")}, CHECKED_AT, DataHealth.DELAYED, SOURCE,
                    {InputName.LIVE_PNL: DataHealth.AVAILABLE})
    evaluation = evaluate(MAX_LOSS_RULE, snap)
    assert evaluation.outcome is Outcome.TRIGGERED
    r = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, evaluation, active_version=active())
    assert r.data_health is DataHealth.DELAYED
