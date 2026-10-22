"""W-127 core proof (REQ-084 AC-4, REQ-083 AC-4): the engine's Estimated figures at a what-if level, date and IV change
equal an INDEPENDENT Black-Scholes written in this file (math.erf, no engine import for the pricing).

Hand computation (the ADR-151 example): NIFTY BUY 22,800 CE (IV 13.0 %, entry 330.00) and SELL 23,000 CE (IV 12.0 %,
entry 190.00), 75 units each, rate 6.5 %, q = 0 (spot-fallback forward). Target level 23,000, target date
2026-10-25 15:30 IST (two days before the 2026-10-27 expiry), IV +2.0 points => 15.0 % and 14.0 %; T = 2/365.
"""
import datetime
import math
from decimal import ROUND_HALF_EVEN
from decimal import Decimal as D

import pytest
from ofo.engine.black_scholes import IST
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import WhatIfRefused, estimate
from ofo.scenario.levels import ExpectedMove
from scenario_fixtures import NIFTY_EXPIRY, VALUATION, nifty_input, nifty_leg

RATE = 0.065
TARGET = datetime.datetime(2026, 10, 25, 15, 30, tzinfo=IST)


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_call(s: float, k: float, t: float, iv: float) -> D:
    """Independent Black-Scholes call (q = 0), rounded half-even to the paisa like a quoted price."""
    d1 = (math.log(s / k) + (RATE + iv * iv / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    return D(repr(s * _cdf(d1) - k * math.exp(-RATE * t) * _cdf(d2))).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)


def spread():
    return nifty_input([
        nifty_leg(Action.BUY, Instrument.CE, "22800", "330.00", iv="0.13"),
        nifty_leg(Action.SELL, Instrument.CE, "23000", "190.00", iv="0.12")], spot=D("23000"))


def expected_pnl(level: float, t_days: int, iv_points: float) -> D:
    t = t_days / 365
    long_c = bs_call(level, 22800, t, 0.13 + iv_points / 100)
    short_c = bs_call(level, 23000, t, 0.12 + iv_points / 100)
    return (long_c - D("330.00")) * 75 + (D("190.00") - short_c) * 75


def test_ac4_pnl_at_target_matches_independent_black_scholes() -> None:
    """AC-4: the P&L at level 23,000, two days before expiry, IV +2 equals the independent hand computation."""
    got = estimate(spread(), D("23000"), valuation_time=TARGET, iv_offset=D("2.0"))
    assert got.total == expected_pnl(23000, 2, 2.0)
    assert got.assumptions.ivs == (D("0.15"), D("0.14"))
    assert got.assumptions.valuation_time == TARGET


def test_ac4_default_inputs_are_the_live_estimate() -> None:
    """AC-4 (negative): no what-if input gives the unchanged Estimated Now (10 days to expiry, own IVs)."""
    got = estimate(spread(), D("23000"))
    assert got.total == expected_pnl(23000, 10, 0.0)
    assert got.assumptions.valuation_time == VALUATION


def test_ac3_iv_offset_to_zero_or_below_is_refused_with_the_reason() -> None:
    """AC-3: a resulting IV at or below 0 is refused (12.0 % - 12.0 points = 0)."""
    with pytest.raises(WhatIfRefused) as err:
        estimate(spread(), D("23000"), iv_offset=D("-12.0"))
    assert "zero or below" in str(err.value.reason)
    with pytest.raises(WhatIfRefused):
        estimate(spread(), D("23000"), iv_offset=D("-20.0"))


def test_ac2_target_at_expiry_close_is_the_expiry_value() -> None:
    """AC-2: a target exactly at the 15:30 IST expiry close is the exact expiry P&L (22,800 long worth 200, 23,000 short
    worth 0 at level 23,000): (200 - 330) x 75 + (190 - 0) x 75."""
    close = datetime.datetime.combine(NIFTY_EXPIRY, datetime.time(15, 30), tzinfo=IST)
    assert estimate(spread(), D("23000"), valuation_time=close).total == D("4500")


def test_req083_ac4_expected_move_bands() -> None:
    """REQ-083 AC-4: NIFTY 23,047, ATM IV 12 %, 7 days: 23047 x 0.12 x sqrt(7/365) = 383.0 => 1 SD 383, 2 SD 766 points."""
    one = ExpectedMove(D("0.12"), 7).points(D("23047"))
    assert one == D("383")
    assert 2 * one == D("766")
