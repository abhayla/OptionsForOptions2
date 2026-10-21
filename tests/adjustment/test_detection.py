"""W-122: Q253 condition 1 (REQ-045 AC-1, AC-2; REQ-046 AC-1). Every expected number is a hand calculation in the
docstring: distance points = |index - level|; distance percent = points / index x 100, rounded half-up to 0.01."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ofo.adjustment import detection as d
from ofo.engine.legs import Action, Instrument

D = Decimal


def _leg(action: Action, instrument: Instrument, strike: str | None):
    return SimpleNamespace(action=action, instrument=instrument, strike=None if strike is None else D(strike),
                           expiry=datetime.date(2026, 10, 27), quantity=65)


def test_ac2_short_strike_24400_at_index_24350_fires_at_half_a_percent_and_not_at_0_2():
    """AC-2: detection needs no user rule. 24,400 CE short, index 24,350: 50 points; 50 / 24,350 x 100 = 0.2053... ->
    0.21%. 0.2053 <= 0.5 fires; 0.2053 > 0.2 does not."""
    fired = d.detect_near_levels(short_strike_levels=[D("24400")], breakevens=[], index_level=D("24350"),
                                 threshold_percent=d.NEAR_LEVEL_THRESHOLD_PERCENT)
    assert fired == (d.Detection("near_short_strike", D("24400"), D("24350"), D("50"), D("0.21"), D("0.5")),)
    assert d.detect_near_levels(short_strike_levels=[D("24400")], breakevens=[], index_level=D("24350"),
                                threshold_percent=D("0.2")) == ()


def test_ac1_the_label_and_the_default_threshold_are_the_spec_values():
    """AC-1: platform detections read 'Adjustment opportunity detected'; Q253's default threshold is 0.5%."""
    assert d.PLATFORM_DETECTION_LABEL == "Adjustment opportunity detected"
    assert d.NEAR_LEVEL_THRESHOLD_PERCENT == D("0.5")


def test_ac2_a_distance_exactly_at_the_threshold_fires_and_one_paisa_beyond_does_not():
    """AC-2 boundary ("within" is inclusive): index 20,000, strike 20,100 = 100 points = exactly 0.50% -> fires.
    Strike 20,100.10 = 100.10 points = 0.5005% -> shown 0.50 but above 0.5, so it does NOT fire (exact comparison)."""
    at = d.detect_near_levels(short_strike_levels=[D("20100")], breakevens=[], index_level=D("20000"),
                              threshold_percent=D("0.5"))
    assert [(x.distance_points, x.distance_percent) for x in at] == [(D("100"), D("0.50"))]
    assert d.detect_near_levels(short_strike_levels=[D("20100.10")], breakevens=[], index_level=D("20000"),
                                threshold_percent=D("0.5")) == ()


def test_ac2_breakeven_condition_names_the_breakeven_and_short_strikes_come_first():
    """AC-2: index 22,533.25; breakeven 22,500.00 -> 33.25 points, 33.25 / 22,533.25 x 100 = 0.1475... -> 0.15%;
    short strike 22,400 -> 133.25 points, 0.5913... -> 0.59% (fires at 0.6). Order: strike, then breakeven."""
    fired = d.detect_near_levels(short_strike_levels=[D("22400"), D("22800")], breakevens=[D("22500.00")],
                                 index_level=D("22533.25"), threshold_percent=D("0.6"))
    assert [(x.condition, x.level, x.distance_points, x.distance_percent) for x in fired] == [
        ("near_short_strike", D("22400"), D("133.25"), D("0.59")),
        ("near_breakeven", D("22500.00"), D("33.25"), D("0.15"))]


def test_short_strikes_are_the_sold_option_strikes_only():
    """Bought options and a sold future carry no short strike."""
    legs = [_leg(Action.SELL, Instrument.CE, "24400"), _leg(Action.BUY, Instrument.CE, "24600"),
            _leg(Action.SELL, Instrument.PE, "24000"), _leg(Action.SELL, Instrument.FUT, None)]
    assert d.short_strikes(legs) == (D("24000"), D("24400"))


def test_no_breakevens_gives_no_breakeven_condition():
    """Engine answer 'breakevens empty': only the short-strike condition can fire."""
    assert d.detect_near_levels(short_strike_levels=[], breakevens=[], index_level=D("24350"),
                                threshold_percent=D("0.5")) == ()


@pytest.mark.parametrize("threshold", [D("0"), D("-0.5"), D("100.01"), 0.5, "0.5", None, D("NaN")])
def test_a_threshold_outside_0_to_100_or_not_a_decimal_is_refused(threshold):
    with pytest.raises(ValueError):
        d.detect_near_levels(short_strike_levels=[D("24400")], breakevens=[], index_level=D("24350"),
                             threshold_percent=threshold)


@pytest.mark.parametrize("index", [D("0"), D("-1"), 24350.0, None])
def test_an_index_level_that_is_not_a_positive_decimal_is_refused(index):
    with pytest.raises(ValueError):
        d.detect_near_levels(short_strike_levels=[D("24400")], breakevens=[], index_level=index,
                             threshold_percent=D("0.5"))
