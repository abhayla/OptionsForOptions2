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
from ofo.timeline.why import ACTION_WORDS, FOLLOW_UP_LABELS, INPUT_LABELS, OP_WORDS, advice_words_in

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

def _recorded_trigger():
    evaluation = loss_evaluation()
    assert evaluation.outcome is Outcome.TRIGGERED
    record = RuleTriggerRecord.from_evaluation(MAX_LOSS_RULE, evaluation,
                                               strategy=executed_record())
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
    assert f'Market data: source "{SOURCE}", health available.' in lines
    assert "Active strategy version: 1." in lines
    assert "The rule's chosen action: alert and prepare orders for your review." in lines
    # No follow-up recorded yet: said so, never assumed.
    assert "Alert generated: not recorded." in lines and "Executed: not recorded." in lines


def _record_numbers(record: RuleTriggerRecord) -> set[str]:
    numbers = {str(o.value) for o in record.observations} | {str(o.threshold) for o in record.observations}
    numbers |= {str(v) for v in (record.active_version, record.planned_version) if v is not None}
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
    """AC-5 with ADR-003: the answer uses 'Your rule was triggered' and the shared wording checker
    (ofo.strategy.wording, via advice_words_in) finds no advice phrase in it or in any fixed wording the answer uses."""
    timeline, seq, _ = _recorded_trigger()
    for kind, answer in ((FollowUpKind.ALERT_GENERATED, True), (FollowUpKind.ORDER_PREPARED, True),
                         (FollowUpKind.CONFIRMATION_REQUIRED, True), (FollowUpKind.EXECUTED, False),
                         (FollowUpKind.BROKER_REPORTED, "no order placed"),
                         (FollowUpKind.RECONCILIATION_SUCCEEDED, True)):
        timeline.record_follow_up(FollowUp(kind, seq, CHECKED_AT, answer))
    text = timeline.why(seq)
    assert text.startswith("Your rule was triggered")
    assert advice_words_in(text) == []
    fixed = [*INPUT_LABELS.values(), *OP_WORDS.values(), *ACTION_WORDS.values(), *FOLLOW_UP_LABELS.values()]
    assert [phrase for phrase in fixed if advice_words_in(phrase)] == []
    # checker is live: shared ofo.wording label families changed shape on purpose (W-024) to
    # generalise past exact substrings ("should" catches every "should"/"shouldn't" phrasing; "best
    # <trade/strategy/option/choice/adjustment/strike/entry/time/pick/level>" replaced a bare "best"
    # that false-positived on ordinary words like "best way" — see tests/strategy/test_templates.py).
    # This assertion is updated to the real current labels rather than the stale ones it hardcoded.
    assert advice_words_in("You should exit now, it is the best trade") == [
        "should",
        "best <trade/strategy/option/choice/adjustment/strike/entry/time/pick/level>",
    ]
    assert "Alert generated: yes." in text and "Executed: no." in text
    assert 'Broker reported: "no order placed".' in text and "Reconciliation succeeded: yes." in text


def test_answer_reports_missing_inputs_and_unhealthy_data_honestly():
    """AC-5: an unconditional entry trigger says it has no market condition; the data health printed is the recorded
    one (stale), never upgraded."""
    rule = entry_immediate("enter-now", action=RuleAction.ALERT_ONLY)
    from ofo.rules import evaluate
    from timeline_fixtures import GOLDEN, snapshot

    evaluation = evaluate(rule, snapshot(GOLDEN, health=DataHealth.STALE))
    assert evaluation.outcome is Outcome.TRIGGERED
    record = RuleTriggerRecord.from_evaluation(rule, evaluation, strategy=executed_record())
    text = why_did_this_trigger(record)
    assert 'Market data: source "zerodha-kite-quote", health stale.' in text
    assert "Active strategy version: 1." in text
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


def test_platform_wording_is_checked_at_runtime_but_recorded_text_is_quoted_not_rewritten(monkeypatch):
    """AC-5 with ADR-003: if the platform's own answer wording contains an advice phrase, building the answer raises;
    a user's rule text or a broker report that contains one is printed as recorded, in quotes, and does not raise."""
    timeline, seq, record = _recorded_trigger()
    monkeypatch.setitem(OP_WORDS, record.observations[0].op, "at or below, you should exit at")
    with pytest.raises(ValueError, match="advice phrases"):
        timeline.why(seq)
    monkeypatch.undo()
    timeline.record_follow_up(FollowUp(FollowUpKind.BROKER_REPORTED, seq, CHECKED_AT, "best price filled"))
    text = timeline.why(seq)
    assert 'Broker reported: "best price filled".' in text
    assert text.splitlines()[0] == 'Your rule was triggered: "Max loss 3000" (exit rule ml-3000).'
