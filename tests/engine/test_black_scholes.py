"""Black-Scholes price, implied volatility and Greeks (REQ-032 AC-3; W-002 core proof).

Reference values: Hull, *Options, Futures and Other Derivatives*, the Black-Scholes-Merton worked example
(S=42, K=40, r=10 %, sigma=20 %, T=0.5: call 4.76, put 0.81) and the Greek-letters chapter's running example
(S=49, K=50, r=5 %, sigma=20 %, T=0.3846 = 20 weeks: delta 0.522, gamma 0.066, theta -4.31 per year, vega 12.1 per
unit of sigma). Chapter numbers differ between editions, so none is cited. Theta is stated on the forward (ADR-234), so
Hull's -4.31 (which carries the -r K e^(-rT) N(d2) term) reads -3.15 a year here.
"""
import datetime
import math
from decimal import Decimal as D

import pytest

from ofo.engine.black_scholes import (
    IST,
    Greeks,
    NoImpliedVolatilityError,
    _price,
    _solve_iv,
    bs_greeks,
    bs_greeks_unrounded,
    bs_price,
    forward_price,
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
    """AC-3: Greeks match Hull's running example (theta per calendar day, vega per 1 vol point), Decimal at 4 dp.

    Theta is stated on the forward (ADR-234): Hull's call theta -4.31 a year includes the carry term -r K e^(-rT) N(d2);
    on the forward it is -S n(d1) sigma / (2 sqrt T) = -3.147489 a year, -0.008623 a day (hand figure, math.erf,
    checked against a finite difference of the Black-76 undiscounted price at a fixed forward)."""
    args = (CE, D("49"), D("50"), D("0.3846"), D("0.05"), D("0.20"))
    g = bs_greeks(*args)
    assert g == Greeks(delta=D("0.5216"), gamma=D("0.0655"), theta=D("-0.0086"), vega=D("0.1211"))
    assert round(g.delta, 3) == D("0.522") and round(g.gamma, 3) == D("0.066")
    assert round(g.vega * 100, 1) == D("12.1")  # Hull quotes vega per 1.00 of sigma
    assert round(bs_greeks(*args, days_in_year=1).theta, 2) == D("-3.15")  # annual theta on the forward
    put = bs_greeks(PE, *args[1:])
    assert put.delta == D("-0.4784")  # call delta - 1
    assert (put.gamma, put.theta, put.vega) == (g.gamma, g.theta, g.vega)


# ---- ADR-234: theta stated on the forward, the same for a call and a put ---------------------------------------
def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _undiscounted_black76(f: float, k: float, t: float, v: float, call: bool) -> float:
    d1 = (math.log(f / k) + 0.5 * v * v * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    return f * _ncdf(d1) - k * _ncdf(d2) if call else k * _ncdf(-d2) - f * _ncdf(-d1)


def _theta_on_forward_fd(s: float, k: float, t: float, r: float, q: float, v: float, call: bool) -> float:  # noqa: PLR0913
    """Independent: -e^(-rT) dU/dT at a FIXED forward F = S e^((r-q)T), U the Black-76 undiscounted price; per day."""
    f, h = s * math.exp((r - q) * t), 1e-7
    du = (_undiscounted_black76(f, k, t + h, v, call) - _undiscounted_black76(f, k, t - h, v, call)) / (2 * h)
    return -math.exp(-r * t) * du / 365


# (spot, strike, years, rate, q, vol): ATM, deep ITM call / OTM put, OTM call, a large yield, q = 0, a 1-day expiry
THETA_CASES = [
    ("23292.25", "23300", "0.0195131596", "0.065", "0.0250901872", "0.1503"),  # real NIFTY 9 Nov, 2 Nov 12:33:52
    ("23292.25", "22500", "0.0195131596", "0.065", "0.0250901872", "0.18"),
    ("23292.25", "24000", "0.0195131596", "0.065", "0.0250901872", "0.13"),
    ("100", "100", "1", "0.065", "0.5", "0.2"),
    ("49", "50", "0.3846", "0.05", "0", "0.20"),
    ("23298.60", "23300", "0.0029", "0.065", "0.04", "0.1694"),
]


@pytest.mark.parametrize("s, k, t, r, q, v", THETA_CASES)
def test_call_theta_equals_put_theta_at_the_same_strike_expiry_and_vol(s, k, t, r, q, v):  # noqa: PLR0913
    """ADR-234 (2): one theta per strike; no carry term splits the call from the put (F-98: it drifted 2.57 -> 3.58)."""
    common = (D(s), D(k), D(t), D(r), D(v))
    call = bs_greeks_unrounded(CE, *common, dividend_yield=D(q))
    put = bs_greeks_unrounded(PE, *common, dividend_yield=D(q))
    assert call.theta == put.theta
    assert bs_greeks(CE, *common, dividend_yield=D(q)).theta == bs_greeks(PE, *common, dividend_yield=D(q)).theta


@pytest.mark.parametrize("s, k, t, r, q, v", THETA_CASES)
def test_theta_is_the_decay_on_the_forward(s, k, t, r, q, v):  # noqa: PLR0913
    """ADR-234 (2): theta = the time decay of the option on its forward (Black-76 form), against an independent
    finite difference with the forward held fixed; both kinds."""
    for kind, call in ((CE, True), (PE, False)):
        g = bs_greeks_unrounded(kind, D(s), D(k), D(t), D(r), D(v), dividend_yield=D(q))
        hand = _theta_on_forward_fd(float(s), float(k), float(t), float(r), float(q), float(v), call)
        assert abs(float(g.theta) - hand) <= 1e-6 * max(1.0, abs(hand)), (kind, g.theta, hand)


def test_theta_stays_per_calendar_day():
    """ADR-234 (3): the day count is unchanged: the per-day theta is the annual theta / 365."""
    args = (D("23292.25"), D("23300"), D("0.0195131596"), D("0.065"), D("0.1503"))
    year = bs_greeks_unrounded(CE, *args, days_in_year=1, dividend_yield=D("0.0250901872")).theta
    day = bs_greeks_unrounded(CE, *args, dividend_yield=D("0.0250901872")).theta
    assert abs(day * 365 - year) <= D("1e-9")


REAL_0911 = {"spot": D("23292.25"), "strike": D("23300"), "years": D("0.01951315956367326230339928970"),
             "rate": D("0.065")}
HAND_TOLERANCE = 0.00006  # 4 dp rounding of the engine figure
REAL_Q = D("0.0250901872")


def test_price_iv_delta_gamma_vega_unchanged_on_the_real_case():
    """ADR-234 (1): only theta moves. Real NIFTY 9 Nov 23300 CE, 2 Nov 12:33:52 IST (D:\\Abhay\\scratch\\gclive3
    ours-2026-11-09-r1.json, the engine's reply BEFORE ADR-234): mid 200.18 on bid 199.85 / ask 200.50, parity q
    0.0250901872, IV shown 15.03 %, delta 0.5124, gamma 0.0008, vega 12.9674; theta was -14.9512 (CE) / -12.3623 (PE).
    """
    iv = implied_volatility(CE, D("200.18"), **REAL_0911, dividend_yield=REAL_Q)
    assert round(iv * 100, 2) == D("15.03")
    assert bs_price(CE, vol=iv, **REAL_0911, dividend_yield=REAL_Q) == D("200.18")
    g = bs_greeks(CE, vol=iv, **REAL_0911, dividend_yield=REAL_Q)
    assert (g.delta, g.gamma, g.vega) == (D("0.5124"), D("0.0008"), D("12.9674"))
    # the new theta, independently: -S e^(-qT) n(d1) sigma / (2 sqrt T) / 365 at the engine's IV (an input here)
    s, k, t, r, q, v = 23292.25, 23300.0, float(REAL_0911["years"]), 0.065, float(REAL_Q), float(iv)
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    hand = -s * math.exp(-q * t) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * v / (2 * math.sqrt(t)) / 365
    assert abs(float(g.theta) - hand) <= HAND_TOLERANCE
    assert D("-14.9512") < g.theta < D("-12.3623")  # between the old split call and put figures


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


@pytest.mark.parametrize("field", ["spot", "strike", "years", "vol", "rate"])
def test_bs_price_refuses_nan_in_every_input(field):
    """AC-4 (issue #10 item 4): a NaN in any Black-Scholes input is refused, never propagated into a price."""
    args = dict(option=CE, vol=D("0.20"), **HULL) | {field: D("NaN")}
    with pytest.raises(ValueError):
        bs_price(**args)


@pytest.mark.parametrize("field", ["spot", "years", "rate"])
def test_forward_price_refuses_nan(field):
    """AC-4: forward_price refuses NaN spot, years and rate."""
    args = dict(spot=D("42"), years=D("0.5"), rate=D("0.10")) | {field: D("NaN")}
    with pytest.raises(ValueError):
        forward_price(**args)


@pytest.mark.parametrize("spot", [D(23047.3), 23047.3])
def test_forward_price_refuses_float_built_spot(spot):
    """AC-4: -322.50 must not become -322.4999999 - a Decimal built from a float (23047.3 is inexact in binary)
    and a raw float are both refused."""
    with pytest.raises(ValueError):
        forward_price(spot, D("0.5"), D("0.10"))


def test_forward_price_accepts_exact_decimal():
    """AC-4 positive control: S e^(rT) with S=42, r=10%, T=0.5 is 42 x 1.051271 = 44.15 (hand: e^0.05 = 1.0512711)."""
    assert forward_price(D("42"), D("0.5"), D("0.10")) == D("44.15")


def test_year_fraction_is_calendar_days_over_explicit_day_count():
    """AC-3: time to expiry = seconds to 15:30 IST on expiry / (days_in_year x 86400); both explicit."""
    valuation = datetime.datetime(2026, 10, 17, 15, 30, tzinfo=IST)
    assert year_fraction(valuation, datetime.date(2026, 10, 27)) == D(10) / D(365)
    assert year_fraction(valuation, datetime.date(2026, 10, 27), days_in_year=360) == D(10) / D(360)
    with pytest.raises(ValueError, match="after the"):
        year_fraction(datetime.datetime(2026, 10, 27, 15, 31, tzinfo=IST), datetime.date(2026, 10, 27))
    with pytest.raises(ValueError, match="timezone-aware"):
        year_fraction(datetime.datetime(2026, 10, 17), datetime.date(2026, 10, 27))
