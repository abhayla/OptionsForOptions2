"""Black-Scholes price, implied volatility and Greeks (REQ-032 AC-3; W-002 core proof).

Reference values: Hull, *Options, Futures and Other Derivatives*, the Black-Scholes-Merton worked example
(S=42, K=40, r=10 %, sigma=20 %, T=0.5: call 4.76, put 0.81) and the Greek-letters chapter's running example
(S=49, K=50, r=5 %, sigma=20 %, T=0.3846 = 20 weeks: delta 0.522, gamma 0.066, theta -4.31 per year, vega 12.1 per
unit of sigma). Chapter numbers differ between editions, so none is cited.
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.black_scholes import (
    IST,
    Greeks,
    NoImpliedVolatilityError,
    _price,
    _solve_iv,
    bs_greeks,
    bs_price,
    implied_volatility,
    year_fraction,
)
from ofo.engine.legs import Instrument

CE, PE = Instrument.CE, Instrument.PE
HULL = dict(spot=D("42"), strike=D("40"), years=D("0.5"), rate=D("0.10"))


def test_core_hull_price_iv_price_round_trip():
    """AC-3: Hull 15.6 reproduced to the paisa, and IV recovered from the model price within 1e-6 (core proof)."""
    assert bs_price(CE, vol=D("0.20"), **HULL) == D("4.76")
    assert bs_price(PE, vol=D("0.20"), **HULL) == D("0.81")
    # The public API only accepts 2-decimal prices (AC-4), so the 1e-6 recovery of the unrounded model price is
    # proved on the solver it wraps.
    for kind in (CE, PE):
        exact = _price(kind, 42.0, 40.0, 0.5, 0.10, 0.20)
        assert abs(_solve_iv(kind, exact, 42.0, 40.0, 0.5, 0.10) - 0.20) <= 1e-6
    for kind, quoted in ((CE, D("4.76")), (PE, D("0.81"))):
        assert bs_price(kind, vol=implied_volatility(kind, quoted, **HULL), **HULL) == quoted
    # Round trip from the quoted two-decimal price: the IV re-prices to the same paisa.
    quoted_iv = implied_volatility(CE, D("4.76"), **HULL)
    assert quoted_iv == D("0.200066")
    assert bs_price(CE, vol=quoted_iv, **HULL) == D("4.76")


def test_put_call_parity():
    """AC-3: C - P = S - K e^(-rT) holds for the model prices (Hull: 4.7594 - 0.8086 = 42 - 38.0492 = 3.9508)."""
    import math

    for s, k, t, r, v in [(42.0, 40.0, 0.5, 0.10, 0.20), (23000.0, 23400.0, 0.05, 0.065, 0.14)]:
        lhs = _price(CE, s, k, t, r, v) - _price(PE, s, k, t, r, v)
        assert lhs == pytest.approx(s - k * math.exp(-r * t), abs=1e-9)


def test_greeks_match_hull_and_are_rounded_to_4dp():
    """AC-3: Greeks match Hull's running example (theta per calendar day, vega per 1 vol point), Decimal at 4 dp."""
    args = (CE, D("49"), D("50"), D("0.3846"), D("0.05"), D("0.20"))
    g = bs_greeks(*args)
    assert g == Greeks(delta=D("0.5216"), gamma=D("0.0655"), theta=D("-0.0118"), vega=D("0.1211"))
    assert round(g.delta, 3) == D("0.522") and round(g.gamma, 3) == D("0.066")
    assert round(g.vega * 100, 1) == D("12.1")  # Hull quotes vega per 1.00 of sigma
    assert round(bs_greeks(*args, days_in_year=1).theta, 2) == D("-4.31")  # annual theta, Hull's figure
    put = bs_greeks(PE, *args[1:])
    assert put.delta == D("-0.4784")  # call delta - 1
    assert (put.gamma, put.vega) == (g.gamma, g.vega)


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: implied_volatility(CE, D("1.50"), **HULL), "below"),  # under discounted intrinsic (3.95)
        (lambda: implied_volatility(CE, D("41.99"), **HULL), "above"),  # more than the spot: no vol reaches it
    ],
)
def test_iv_without_solution_raises(call, message):
    """AC-3: a price no volatility in [0.0001, 5.0] can produce raises a clear error, never a clipped bound."""
    with pytest.raises(NoImpliedVolatilityError, match=message):
        call()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (dict(vol=D("0")), "vol"),
        (dict(vol=0.2), "vol"),  # float refused at the boundary
        (dict(years=D("0")), "years"),
        (dict(spot=D("-1")), "spot"),
        (dict(rate=D("NaN")), "rate"),
        (dict(option=Instrument.FUT), "CE or PE"),
    ],
)
def test_invalid_model_input_is_rejected(kwargs, message):
    """AC-3: invalid model input fails closed with ValueError."""
    args = dict(option=CE, vol=D("0.20"), **HULL) | kwargs
    with pytest.raises(ValueError, match=message):
        bs_price(**args)


def test_year_fraction_is_calendar_days_over_explicit_day_count():
    """AC-3: time to expiry = seconds to 15:30 IST on expiry / (days_in_year x 86400); both explicit."""
    valuation = datetime.datetime(2026, 10, 17, 15, 30, tzinfo=IST)
    assert year_fraction(valuation, datetime.date(2026, 10, 27)) == D(10) / D(365)
    assert year_fraction(valuation, datetime.date(2026, 10, 27), days_in_year=360) == D(10) / D(360)
    with pytest.raises(ValueError, match="after the"):
        year_fraction(datetime.datetime(2026, 10, 27, 15, 31, tzinfo=IST), datetime.date(2026, 10, 27))
    with pytest.raises(ValueError, match="timezone-aware"):
        year_fraction(datetime.datetime(2026, 10, 17), datetime.date(2026, 10, 27))
