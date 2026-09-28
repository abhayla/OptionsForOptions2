"""Money precision policy (REQ-032 AC-4; scenario-calculations.md §5; ADR-008)."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy, expiry_pnl
from ofo.engine.black_scholes import bs_greeks, bs_price, implied_volatility

EXP = datetime.date(2026, 10, 27)


def make_leg(**overrides):
    fields = dict(
        action=Action.BUY,
        instrument=Instrument.CE,
        strike=D("100"),
        expiry=EXP,
        quantity=3,
        entry_price=D("0.10"),
        ltp=None,
    )
    fields.update(overrides)
    return Leg(**fields)


def test_float_built_decimal_is_refused_w001_red_case():
    """AC-4: the W-001 verifier's case, Decimal(0.1) as entry price, is refused instead of leaking float error."""
    # With the string-built price the P&L is exact: (0 - 0.10) x 3 = -0.30, not -0.3000000000000000166533453693.
    assert expiry_pnl(make_leg(), D("0")) == D("-0.30")
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        make_leg(entry_price=D(0.1))


@pytest.mark.parametrize(
    "field, value",
    [
        ("entry_price", D(0.1)),
        ("entry_price", D("42.505")),  # a third decimal is not a whole number of paise
        ("entry_price", D("Infinity")),
        ("entry_price", D("NaN")),
        ("ltp", D(38.2)),
        ("ltp", D("-Infinity")),
        ("strike", D(22800.1)),
        ("strike", D("22800.001")),
    ],
)
def test_price_strike_ltp_must_be_finite_whole_paise(field, value):
    """AC-4: any price, strike or LTP that is not finite or has more than 2 decimal places raises ValueError."""
    with pytest.raises(ValueError):
        make_leg(**{field: value})


def test_equivalent_two_decimal_forms_are_accepted():
    """AC-4: trailing zeros and integer values are valid paise amounts (the guard is on value, not on notation)."""
    for value in (D("1.500"), D("1.5"), D("2"), D("0"), D("1E+1")):
        assert make_leg(entry_price=value).entry_price == value


def test_money_stays_exact_where_float_drifts():
    """AC-4: -322.50 stays -322.50 (float gives -322.4999999999998); sums of paise never drift."""
    assert (38.20 - 42.50) * 75 != -322.50  # the float failure the policy exists for (§5)
    leg1 = Leg(Action.BUY, Instrument.PE, D("22800"), EXP, 75, D("42.50"), D("38.20"))
    assert Strategy((leg1,)).live_pnl() == D("-322.50")
    tenths = Strategy(tuple(make_leg(entry_price=D("0.10"), ltp=D("0.20"), quantity=1) for _ in range(3)))
    assert tenths.live_pnl() == D("0.30")  # 0.1 + 0.1 + 0.1 exactly


def test_model_outputs_cross_the_boundary_as_rounded_decimals():
    """AC-4: the float-only Black-Scholes model hands back Decimals at the documented steps (0.01, 1e-6, 1e-4)."""
    args = (Instrument.CE, D("42"), D("40"), D("0.5"), D("0.10"))
    price = bs_price(*args, D("0.20"))
    assert isinstance(price, D) and price.as_tuple().exponent == -2
    iv = implied_volatility(Instrument.CE, D("4.76"), D("42"), D("40"), D("0.5"), D("0.10"))
    assert isinstance(iv, D) and iv.as_tuple().exponent == -6
    greeks = bs_greeks(*args, D("0.20"))
    for value in (greeks.delta, greeks.gamma, greeks.theta, greeks.vega):
        assert isinstance(value, D) and value.as_tuple().exponent == -4


@pytest.mark.parametrize(
    "call",
    [
        lambda: implied_volatility(Instrument.CE, D(4.76), D("42"), D("40"), D("0.5"), D("0.10")),
        lambda: implied_volatility(Instrument.CE, D("4.765"), D("42"), D("40"), D("0.5"), D("0.10")),
        lambda: implied_volatility(Instrument.CE, D("4.76"), D(42.1), D("40"), D("0.5"), D("0.10")),
        lambda: implied_volatility(Instrument.CE, D("4.76"), D("42"), D("40.001"), D("0.5"), D("0.10")),
        lambda: bs_price(Instrument.CE, D(42.1), D("40"), D("0.5"), D("0.10"), D("0.20")),
        lambda: bs_price(Instrument.CE, D("42"), D(40.1), D("0.5"), D("0.10"), D("0.20")),
        lambda: bs_greeks(Instrument.PE, D("42.005"), D("40"), D("0.5"), D("0.10"), D("0.20")),
    ],
)
def test_black_scholes_money_and_level_inputs_are_whole_paise(call):
    """AC-4: option price, spot and strike entering the model must be finite with at most 2 decimal places, so a
    float-built Decimal (Decimal(4.76)) or a sub-paisa value (4.765) is refused, same as a leg's prices."""
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        call()


@pytest.mark.parametrize("level", [D(23500.1), D("23500.005")])
def test_estimate_level_is_finite_two_decimal_points(condor_inputs, level):
    """AC-4: an Estimated Now level (index points) must be finite with at most 2 decimal places."""
    from ofo.engine.estimate import estimate_now

    with pytest.raises(ValueError, match="at most 2 decimal places"):
        estimate_now(condor_inputs, level)
