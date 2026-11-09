"""C12 / GC-ICGUIDE g13 (REQ-148): a whole trade whose legs span two expiries is valued at the NEARER expiry close.

Expected values come from an independent Black-Scholes written here with ``math`` (finding
test-asserts-implementation-output), never from the code under test."""
from __future__ import annotations

import datetime
import math
from decimal import Decimal

import pytest
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import FarLegNoIV, near_expiry_after, near_pnl_at

NEAR, FAR = datetime.date(2026, 11, 10), datetime.date(2026, 11, 17)  # 7 calendar days apart, both 15:30 IST
QTY = 65 * 2  # NIFTY lot 65, 2 lots
RATE, IV = Decimal("0.065"), Decimal("0.12")


def _bs_call(s: float, k: float, t: float, r: float, v: float) -> float:
    n = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))  # noqa: E731
    d1 = (math.log(s / k) + (r + v * v / 2) * t) / (v * math.sqrt(t))
    return s * n(d1) - k * math.exp(-r * t) * n(d1 - v * math.sqrt(t))


def _after(ivs=(None, IV)):
    legs = (Leg(Action.SELL, Instrument.PE, Decimal(24500), NEAR, QTY, Decimal("50.00")),
            Leg(Action.SELL, Instrument.CE, Decimal(25300), FAR, QTY, Decimal("80.00")))
    return near_expiry_after(Strategy(legs), booked_pnl=Decimal("100.00"), paid_charges=Decimal("10.00"),
                             adjustment_charges=Decimal("20.00"), open_exit_charges=Decimal("30.00"), rate=RATE,
                             ivs=ivs)


def test_core_two_expiries_valued_at_the_nearer_close():
    # near short PE expires worthless at 25000: +50 x 130 = 6500; far short CE marked at BS with 7 days left
    mark = round(_bs_call(25000, 25300, 7 / 365, 0.065, 0.12), 2)
    expected = Decimal("6500") + (Decimal("80.00") - Decimal(str(mark))) * QTY + Decimal(100) - Decimal(60)
    assert near_pnl_at(_after(), Decimal(25000)) == expected


def test_near_leg_in_the_money_uses_its_expiry_value():
    # at 24300 the near short 24500 PE pays 200: (50 - 200) x 130 = -19500
    mark = round(_bs_call(24300, 25300, 7 / 365, 0.065, 0.12), 2)
    expected = Decimal(-19500) + (Decimal(80) - Decimal(str(mark))) * QTY + Decimal(40)
    assert near_pnl_at(_after(), Decimal(24300)) == expected


def test_far_leg_without_iv_is_named():
    with pytest.raises(FarLegNoIV) as e:
        _after(ivs=(None, None))
    assert e.value.index == 1


def test_single_expiry_is_refused():
    leg = Leg(Action.SELL, Instrument.PE, Decimal(24500), NEAR, QTY, Decimal("50.00"))
    with pytest.raises(ValueError, match="single-expiry"):
        near_expiry_after(Strategy((leg,)), booked_pnl=Decimal(0), paid_charges=Decimal(0),
                          adjustment_charges=Decimal(0), open_exit_charges=Decimal(0), rate=RATE, ivs=(None,))


def test_result_is_whole_paise_decimal():
    v = near_pnl_at(_after(), Decimal("25012.35"))
    assert isinstance(v, Decimal) and v == v.quantize(Decimal("0.01"))
