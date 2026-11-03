"""A-37 (GC-IC1 step 4a): the level watch IS a REQ-041 rule (alert only, underlying level), evaluated by the one rule
evaluator; refused with its reason when the level is not a number or there is no underlying price."""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment import level_watch as lw
from ofo.rules.conditions import Compare, Op
from ofo.rules.inputs import DataHealth, InputName, Snapshot
from ofo.rules.model import Outcome, Rule, RuleAction, RuleKind, evaluate
from ofo.timeutil import IST

AT = datetime.datetime(2026, 11, 3, 10, 10, tzinfo=IST)


def _snap(level: str | None, health: DataHealth = DataHealth.AVAILABLE) -> Snapshot:
    values = {} if level is None else {InputName.UNDERLYING_LEVEL: D(level)}
    return Snapshot(values, AT, health)


def test_a_level_above_the_spot_is_an_alert_only_rule_at_or_above():
    rule = lw.watch("w-1", "23600", D("23420"))
    assert isinstance(rule, Rule)
    assert (rule.kind, rule.action) == (RuleKind.ADJUSTMENT, RuleAction.ALERT_ONLY)
    assert rule.condition == Compare(InputName.UNDERLYING_LEVEL, Op.GTE, D("23600"))
    assert evaluate(rule, _snap("23599.95")).outcome is Outcome.NOT_TRIGGERED
    assert evaluate(rule, _snap("23600")).outcome is Outcome.TRIGGERED


def test_a_level_below_the_spot_is_watched_at_or_below():
    rule = lw.watch("w-2", " 23000.5 ", D("23420"))
    assert rule.condition == Compare(InputName.UNDERLYING_LEVEL, Op.LTE, D("23000.5"))
    assert evaluate(rule, _snap("23000")).outcome is Outcome.TRIGGERED


def test_a_stale_level_cannot_be_evaluated_never_a_guess():
    rule = lw.watch("w-3", "23600", D("23420"))
    assert evaluate(rule, _snap("23700", DataHealth.STALE)).outcome is Outcome.CANNOT_EVALUATE
    assert evaluate(rule, _snap(None)).outcome is Outcome.CANNOT_EVALUATE


@pytest.mark.parametrize(("text", "spot", "reason"), [
    ("abc", D("23420"), lw.Refusal.NOT_A_NUMBER),
    ("", D("23420"), lw.Refusal.NOT_A_NUMBER),
    ("NaN", D("23420"), lw.Refusal.NOT_A_NUMBER),
    ("-5", D("23420"), lw.Refusal.NOT_A_NUMBER),
    ("23600", None, lw.Refusal.NO_SPOT),
    ("23420", D("23420"), lw.Refusal.AT_SPOT),
])
def test_a_refused_watch_names_its_reason(text, spot, reason):
    with pytest.raises(lw.WatchRefused) as refused:
        lw.watch("w-x", text, spot)
    assert refused.value.reason is reason
