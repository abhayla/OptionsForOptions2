"""GC-TP step 6a core proof (REQ-084 AC-4, ADR-008): the one engine estimate valued at a what-if time.

A NIFTY 22,800 / 23,000 bull call spread (REQ-084 AC-4's own example) on the 3 Nov expiry, spot 22,976.85, fixed IVs
and rate, valued 29 Oct 10:00 IST: (a) at = now IS Estimated Now (one function, no second formula); (b) at = the expiry
close gives the At Expiry payoff to the paisa; (c) a long ATM call's estimate falls as the time moves later.
"""
import dataclasses
import datetime
from decimal import Decimal as D

import pytest
from ofo.engine.black_scholes import IST
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.engine.legs import Action, Instrument, expiry_pnl
from ofo.engine.model import estimate, leg_greeks_at_unrounded, leg_greeks_unrounded
from ofo.rules.inputs import DataHealth

from tests.scenario.scenario_fixtures import gated

EXPIRY = datetime.date(2026, 11, 3)
LATER_EXPIRY = datetime.date(2026, 11, 10)
NOW = datetime.datetime(2026, 10, 29, 10, 0, tzinfo=IST)
CLOSE = datetime.datetime(2026, 11, 3, 15, 30, tzinfo=IST)
SPOT = D("22976.85")
RATE = D("0.065")


def _leg(action, kind, strike, entry, iv):
    return LegInput(underlying="NIFTY", contract=f"NIFTY{strike}{kind.value}", action=action, instrument=kind,
                    strike=D(strike), expiry=EXPIRY, quantity=75, premium=D(entry), ltp=D(entry), iv=D(iv))


def later_leg(action, kind, strike, entry, iv):
    """The same leg on the later (10 Nov) expiry."""
    leg = _leg(action, kind, strike, entry, iv)
    return dataclasses.replace(leg, expiry=LATER_EXPIRY, contract=f"{leg.contract}-10NOV")


def _model(legs):
    return gated(StrategyInput(underlying="NIFTY", valuation_time=NOW, rate=RATE, legs=tuple(legs),
                               spot=SpotReading(level=SPOT, at=NOW, health=DataHealth.AVAILABLE)))


SPREAD = (_leg(Action.BUY, Instrument.CE, "22800", "220.00", "0.1210"),
          _leg(Action.SELL, Instrument.CE, "23000", "110.00", "0.1150"))


def test_at_now_is_estimated_now_same_function():
    m = _model(SPREAD)
    for level in (D("22800"), D("23000"), SPOT):
        assert estimate(m, level, NOW) == estimate(m, level)
        assert estimate(m, level, None) == estimate(m, level)


def test_at_expiry_close_is_the_at_expiry_payoff_to_the_paisa():
    m = _model(SPREAD)
    got = estimate(m, D("23000"), CLOSE)
    # BUY 22,800 CE: (200 - 220) x 75 = -1,500; SELL 23,000 CE: (110 - 0) x 75 = 8,250
    assert got.total == D("6750.00")
    assert got.total == sum((expiry_pnl(leg.leg, D("23000")) for leg in SPREAD), D(0))
    assert got.assumptions.years_to_expiry == (D(0), D(0))
    assert got.assumptions.valuation_time == CLOSE


def test_after_expiry_close_still_the_at_expiry_payoff():
    m = _model(SPREAD)
    # BUY 22,800 CE at 22,900: (100 - 220) x 75 = -9,000; SELL 23,000 CE: +8,250
    assert estimate(m, D("22900"), CLOSE + datetime.timedelta(hours=1)).total == D("-750.00")


def test_between_moves_the_estimate_toward_expiry():
    m = _model(SPREAD)
    mid = datetime.datetime(2026, 11, 1, 10, 0, tzinfo=IST)
    now, between, close = (estimate(m, D("23000"), t).total for t in (NOW, mid, CLOSE))
    assert now < between < close  # a bull call spread at its short strike gains as time passes


def test_long_atm_call_falls_as_target_moves_later():
    m = _model((_leg(Action.BUY, Instrument.CE, "23000", "150.00", "0.1200"),))
    times = (NOW, datetime.datetime(2026, 10, 31, 10, 0, tzinfo=IST), datetime.datetime(2026, 11, 2, 10, 0, tzinfo=IST))
    totals = [estimate(m, D("23000"), t).total for t in times]
    assert totals[0] > totals[1] > totals[2]


def test_before_now_and_naive_time_are_refused():
    m = _model(SPREAD)
    with pytest.raises(ValueError):
        estimate(m, D("23000"), NOW - datetime.timedelta(minutes=1))
    with pytest.raises(ValueError):
        estimate(m, D("23000"), NOW.replace(tzinfo=None))


def test_multi_expiry_values_each_leg_on_its_own_time():
    later = later_leg(Action.BUY, Instrument.CE, "23000", "190.00", "0.1180")
    m = _model((SPREAD[1], later))
    got = estimate(m, D("23000"), CLOSE)
    assert got.leg_pnls[0] == expiry_pnl(SPREAD[1].leg, D("23000"))  # first expiry: intrinsic
    assert got.assumptions.years_to_expiry[0] == D(0)
    assert got.assumptions.years_to_expiry[1] > 0  # the later leg keeps its own remaining time
    assert got.marks[1] > 0  # an ATM call with a week left holds time value


def test_greeks_at_now_match_todays_greeks_and_none_at_expiry():
    m = _model(SPREAD)
    for leg in SPREAD:
        assert leg_greeks_at_unrounded(m, leg, SPOT, NOW) == leg_greeks_unrounded(m, leg)
        assert leg_greeks_at_unrounded(m, leg, SPOT, CLOSE) is None
    later = leg_greeks_at_unrounded(m, SPREAD[0], D("23000"), datetime.datetime(2026, 11, 2, 10, 0, tzinfo=IST))
    assert later is not None and later.theta < 0
