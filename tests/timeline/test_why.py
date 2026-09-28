"""REQ-040 AC-5: 'Why did this trigger?' answered from the records only (W-020 core proof).

Core: a max-loss rule (W-013 template) on the golden Iron Condor, valued by the engine, triggers; the recorded trigger's
answer quotes the rule, the exact live P&L, the threshold, the data health and the version, and nothing else.
Expected numbers come from the hand computation in timeline_fixtures.py, never from running the code.
"""
from __future__ import annotations

import re

import pytest

from ofo.rules import DataHealth, InputName, Outcome, RuleAction
from ofo.rules import entry_immediate
from ofo.timeline import FollowUp, FollowUpKind, RuleTriggerRecord, Timeline, why_did_this_trigger
from ofo.timeline.why import INPUT_LABELS

from timeline_fixtures import (
    CHECKED_AT,
    EXPECTED_LOSS_PNL,
    EXPECTED_THRESHOLD,
    MAX_LOSS_RULE,
    SOURCE,
    clock,
    executed_record,
    loss_evaluation,
)

#: ADR-003 forbidden list, plus advice verbs the platform never uses.
FORBIDDEN = ("you should", "best trade", "best adjustment", "recommended", "recommend", "guaranteed", "risk-free",
             "certain profit", "must exit", "should exit", "what should i do")


def _recorded_trigger():
    evaluation = loss_evaluation()
    assert evaluation.outcome is Outcome.TRIGGERED
    record = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, evaluation,
                                               active_version=executed_record().active_version)
    timeline = Timeline("strat-ic-1", clock=clock)
    entry = timeline.record_trigger(record)
    return timeline, entry.seq, record


def test_core_max_loss_trigger_answer_quotes_the_recorded_values():
    """AC-5: the answer names the rule, live P&L -3450.00 against threshold -3000, the health, source, time and
    version 1, exactly as recorded (values from the hand computation, not from the code)."""
    timeline, seq, record = _recorded_trigger()
    answer = timeline.why(seq)
    assert record.observations[0].value == EXPECTED_LOSS_PNL
    assert record.observations[0].threshold == EXPECTED_THRESHOLD
    lines = answer.splitlines()
    assert lines[0] == 'Your rule was triggered: "Max loss 3000" (exit rule ml-3000).'
    assert lines[1] == "Condition met: live P&L (Rs) was -3450.00, at or below the threshold -3000."
    assert f"Checked at: {CHECKED_AT.isoformat()}." in lines
    assert f"Market data: source {SOURCE}, health available." in lines
    assert "Active strategy version: 1." in lines
    assert "The rule's chosen action: alert and prepare orders for your review." in lines
    # No follow-up recorded yet: said so, never assumed.
    assert "Alert generated: not recorded." in lines and "Executed: not recorded." in lines


def _record_numbers(record: RuleTriggerRecord) -> set[str]:
    numbers = {str(o.value) for o in record.observations} | {str(o.threshold) for o in record.observations}
    if record.active_version is not None:
        numbers.add(str(record.active_version))
    return numbers


def test_every_number_in_the_answer_is_a_recorded_field():
    """AC-5: after removing the quoted rule text, id and the recorded timestamp, every number left in the answer is a
    recorded value, threshold or version: nothing invented or recomputed."""
    timeline, seq, record = _recorded_trigger()
    timeline.record_follow_up(FollowUp(FollowUpKind.BROKER_REPORTED, seq, CHECKED_AT, "COMPLETE 4 of 4 legs"))
    answer = timeline.why(seq)
    stripped = answer
    for quoted in (record.rule_text, record.rule_id, record.timestamp.isoformat(), "COMPLETE 4 of 4 legs"):
        assert quoted in stripped
        stripped = stripped.replace(quoted, "")
    numbers = re.findall(r"-?\d+(?:\.\d+)?", stripped)
    assert numbers, "the answer must quote the deciding values"
    assert set(numbers) <= _record_numbers(record), f"numbers not in the record: {set(numbers) - _record_numbers(record)}"
    assert {"-3450.00", "-3000", "1"} <= set(numbers)


def test_answer_has_no_advice_words():
    """AC-5 with ADR-003: the answer uses 'Your rule was triggered' and none of the forbidden advice wording."""
    timeline, seq, _ = _recorded_trigger()
    for kind, answer in ((FollowUpKind.ALERT_GENERATED, True), (FollowUpKind.ORDER_PREPARED, True),
                         (FollowUpKind.CONFIRMATION_REQUIRED, True), (FollowUpKind.EXECUTED, False),
                         (FollowUpKind.BROKER_REPORTED, "no order placed"),
                         (FollowUpKind.RECONCILIATION_SUCCEEDED, True)):
        timeline.record_follow_up(FollowUp(kind, seq, CHECKED_AT, answer))
    text = timeline.why(seq)
    assert text.startswith("Your rule was triggered")
    lowered = text.lower()
    assert [word for word in FORBIDDEN if word in lowered] == []
    assert "Alert generated: yes." in text and "Executed: no." in text
    assert 'Broker reported: "no order placed".' in text and "Reconciliation succeeded: yes." in text


def test_answer_reports_missing_inputs_and_unhealthy_data_honestly():
    """AC-5: an entry trigger with no version yet says so; the data health printed is the recorded one (stale)."""
    rule = entry_immediate("enter-now", action=RuleAction.ALERT_ONLY)
    from ofo.rules import evaluate
    from timeline_fixtures import GOLDEN, snapshot

    evaluation = evaluate(rule, snapshot(GOLDEN, health=DataHealth.STALE))
    assert evaluation.outcome is Outcome.TRIGGERED
    record = RuleTriggerRecord.from_evaluation(rule, evaluation, active_version=None)
    text = why_did_this_trigger(record)
    assert "Market data: source zerodha-kite-quote, health stale." in text
    assert "Active strategy version: none (nothing had executed yet)." in text
    assert "Condition met: this rule has no market condition; it applies as soon as it is checked." in text


def test_every_input_has_a_label():
    """AC-5: every rule input can be named in plain language (no KeyError on a rarer input)."""
    assert set(INPUT_LABELS) == set(InputName)


def test_why_refuses_non_records_and_duplicate_follow_ups():
    """AC-5 negative: only a real trigger record is explained; a follow-up kind given twice is refused."""
    _, seq, record = _recorded_trigger()
    with pytest.raises(ValueError, match="RuleTriggerRecord"):
        why_did_this_trigger({"rule_id": "ml-3000"})  # type: ignore[arg-type]
    twice = [FollowUp(FollowUpKind.EXECUTED, seq, CHECKED_AT, True)] * 2
    with pytest.raises(ValueError, match="given twice"):
        why_did_this_trigger(record, twice)
