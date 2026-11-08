"""A-37 (GC-IC1 step 4c, ADR-242): a level watch is a yes/no rule ``watch.level.<direction>`` answered by the
evaluator and read by ``gate_readings`` as a bool (the alert gate opens one record per episode). No spot or a
withheld check -> no reading (never False). The rule id is Identifier-safe (no colon)."""
from __future__ import annotations

import re
from decimal import Decimal as D

import pytest
from ofo.adjustment import alert_gate, gate_readings
from ofo.adjustment import level_watch as lw
from ofo.adjustment import playbook_eval as pe
from ofo.strategy.settings_value import IDENTIFIER_PATTERN

ABOVE = lw.LevelWatch("above", D("23800"))
BELOW = lw.LevelWatch("below", D("23000"))


def test_every_watch_rule_id_matches_the_identifier_pattern():
    for direction in lw.DIRECTIONS:
        rid = lw.rule_id(direction)
        assert re.fullmatch(IDENTIFIER_PATTERN, rid), rid
        assert lw.is_rule_id(rid) and lw.direction_of(rid) == direction
    assert lw.rule_id("above") == "watch.level.above"


@pytest.mark.parametrize(("watch", "spot", "want"), [
    (ABOVE, "23790", False), (ABOVE, "23800", True), (ABOVE, "23805", True),
    (BELOW, "23010", False), (BELOW, "23000", True), (BELOW, "22990", True),
])
def test_the_answer_is_inclusive_and_follows_the_direction(watch, spot, want):
    assert lw.answer(watch, D(spot)) is want


def test_no_spot_is_no_answer_never_false():
    assert lw.answer(ABOVE, None) is None


@pytest.mark.parametrize("text", ["abc", "", "NaN", "Infinity", "0", "-5", None, 1.5, True])
def test_a_level_that_is_not_a_number_above_zero_is_refused(text):
    with pytest.raises(lw.WatchRefused) as refused:
        lw.parse_level(text)
    assert refused.value.reason is lw.Refusal.NOT_A_NUMBER


def test_a_direction_other_than_above_or_below_is_refused():
    with pytest.raises(lw.WatchRefused) as refused:
        lw.parse_direction("sideways")
    assert refused.value.reason is lw.Refusal.NOT_A_DIRECTION


def _state(spot: str | None, fresh: bool | None = True, watches=(ABOVE,)) -> pe.StrategyState:
    return pe.StrategyState("weekly", stops=None, days_left=3, hhmm="10:10", spot=None if spot is None else D(spot),
                            prices_fresh=fresh, watches=watches)


def _body() -> dict:
    from test_day_rules import _ic  # noqa: PLC0415 - the iron condor playbook body the day-rule tests use
    return _ic()


def _readings(state: pe.StrategyState):
    return gate_readings.readings(pe.evaluate(_body(), state, gap_until="09:30"))


def test_a_watch_reaches_the_gate_as_a_yes_no_reading():
    rid = "watch.level.above"
    assert _readings(_state("23790"))[rid] == (alert_gate.RuleSpec(rid, "bool", ()), False)
    assert _readings(_state("23805"))[rid] == (alert_gate.RuleSpec(rid, "bool", ()), True)
    assert _readings(_state("23800"))[rid][1] is True  # at the level: reached


def test_a_watch_below_reads_its_own_direction():
    got = _readings(_state("22990", watches=(BELOW,)))
    assert got["watch.level.below"][1] is True and "watch.level.above" not in got


def test_a_withheld_check_or_no_spot_gives_no_reading_never_false():
    assert _readings(_state("23805", fresh=False))["watch.level.above"][1] is None
    assert _readings(_state("23805", fresh=None))["watch.level.above"][1] is None


def test_no_watch_set_adds_no_rule():
    assert not any(lw.is_rule_id(r) for r in _readings(_state("23805", watches=())))
