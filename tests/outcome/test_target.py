"""REQ-084 AC-1/AC-2/AC-4/AC-7 (GC-TP step 6a): the what-if target module's rules, one test per rule, on the engine."""
import dataclasses
import datetime
from decimal import Decimal as D

from ofo.engine.legs import Action, Instrument
from ofo.engine.model import estimate
from ofo.outcome.target import TargetAsk, clamp_at, first_close, live_target, target_limits
from ofo.scenario.config import ScenarioSettings
from ofo.scenario.levels import build_level_set

from tests.engine.test_estimate_at import CLOSE, NOW, SPOT, SPREAD, _model, later_leg

STEP = D(50)


def _levels(m):
    return build_level_set(m, ScenarioSettings().for_index("NIFTY"))


def test_limits_are_spot_ten_percent_snapped_inward_to_the_step():
    lim = target_limits(SPOT, STEP)  # 22,976.85: 20,679.165 .. 25,274.535
    assert (lim.min, lim.max, lim.step) == (D(20700), D(25250), STEP)


def test_clamp_at_now_between_before_and_after():
    assert clamp_at(None, NOW, CLOSE) == (NOW, None)
    mid = NOW + datetime.timedelta(days=2)
    assert clamp_at(mid, NOW, CLOSE) == (mid, None)
    assert clamp_at(CLOSE, NOW, CLOSE) == (CLOSE, None)
    assert clamp_at(NOW - datetime.timedelta(seconds=1), NOW, CLOSE) == (NOW, "before_now")
    assert clamp_at(CLOSE + datetime.timedelta(seconds=1), NOW, CLOSE) == (CLOSE, "after_first_expiry")


def test_first_close_is_the_earliest_expiry_at_1530_ist():
    later = later_leg(Action.BUY, Instrument.CE, "23000", "190.00", "0.1180")
    assert first_close(_model((later, SPREAD[1]))) == CLOSE


def test_no_iv_gives_at_expiry_pnl_and_refuses_the_time():
    no_iv = dataclasses.replace(SPREAD[0], iv=None)
    m = _model((no_iv, SPREAD[1]))
    t = live_target(TargetAsk(D(23000), NOW + datetime.timedelta(days=1)), m, _levels(m), STEP)
    assert t.kind == "exact" and t.at is None and t.at_refused_reason is not None
    assert t.pnl == D("6750.00")  # (200 - 220) x 75 + (110 - 0) x 75, the At Expiry payoff
    assert t.curve is None and t.greeks is None and t.breakevens is None


def test_breakevens_at_target_are_zero_crossings_of_the_engine_estimate():
    m = _model(SPREAD)
    at = NOW + datetime.timedelta(days=2)
    t = live_target(TargetAsk(D(23000), at), m, _levels(m), STEP)
    assert len(t.breakevens) == 1
    be = t.breakevens[0]
    # marks are whole paise, so the estimate is flat in tiny steps: it is at its nearest to zero at the breakeven and
    # changes sign within one point either side
    here = abs(estimate(m, be, at).total)
    assert here <= abs(estimate(m, be - D("0.01"), at).total) and here <= abs(estimate(m, be + D("0.01"), at).total)
    assert estimate(m, be - 1, at).total < 0 < estimate(m, be + 1, at).total
    assert t.pnl == estimate(m, D(23000), at).total


def test_level_outside_limits_is_clamped_and_inside_is_kept():
    m = _model(SPREAD)
    assert live_target(TargetAsk(D(30000)), m, _levels(m), STEP).level == D(25250)
    inside = live_target(TargetAsk(D(23100)), m, _levels(m), STEP)
    assert inside.level == D(23100) and inside.level_clamped is False


# --- REQ-084 AC-2 / AC-5 (owner 2026-10-29): the three what-if sentences, each from its pinned template -------------

ESTIMATE_LABEL = "Estimate from the pricing model at your target, not a forecast."
NO_GREEKS = "No Greeks at expiry: the options have no time left."


def test_every_target_figure_carries_the_estimate_label_not_estimated_now():
    m = _model(SPREAD)
    t = live_target(TargetAsk(D(23000), NOW + datetime.timedelta(days=1)), m, _levels(m), STEP)
    assert t.output_label == ESTIMATE_LABEL
    assert t.curve is not None and t.curve.output_label == ESTIMATE_LABEL


def test_a_clamped_level_or_date_says_the_nearest_allowed_value():
    m = _model(SPREAD)
    high = live_target(TargetAsk(D(30000)), m, _levels(m), STEP)
    assert high.level_clamp_text == "Target moved to the nearest allowed value: 25,250.00."
    late = live_target(TargetAsk(at=CLOSE + datetime.timedelta(days=2)), m, _levels(m), STEP)
    assert late.clamp == "after_first_expiry"
    assert late.at_clamp_text == "Target moved to the nearest allowed value: 3 Nov, 15:30 IST."
    inside = live_target(TargetAsk(D(23100), NOW + datetime.timedelta(hours=1)), m, _levels(m), STEP)
    assert inside.level_clamp_text is None and inside.at_clamp_text is None


def test_no_time_left_greeks_carry_the_sentence_and_live_greeks_do_not():
    m = _model(SPREAD)
    at_close = live_target(TargetAsk(D(23000), CLOSE), m, _levels(m), STEP)
    assert at_close.greeks is not None and at_close.greeks.unavailable == "no_time_left"
    assert at_close.greeks.unavailable_text == NO_GREEKS
    now = live_target(TargetAsk(D(23000)), m, _levels(m), STEP)
    assert now.greeks is not None and now.greeks.unavailable_text is None
