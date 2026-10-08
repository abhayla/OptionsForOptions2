"""The engine's one input model (REQ-032 AC-2)."""
import datetime
from decimal import Decimal as D

import pytest
from conftest import EXPIRY, RATE, SPOT, VALUATION, leg_input

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.engine.black_scholes import Greeks
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement

BUY, SELL, CE, PE, FUT = Action.BUY, Action.SELL, Instrument.CE, Instrument.PE, Instrument.FUT


def test_inputs_carry_every_ac2_field_and_feed_the_engine(condor_inputs):
    """AC-2: underlying, expiry, contract, legs, quantity, premium, LTP, Greeks, IV, margin, charges and current
    market value are all engine inputs, and the engine computes from them (§6 live P&L +1,365.00)."""
    greeks = Greeks(delta=D("-0.1312"), gamma=D("0.0003"), theta=D("-3.1045"), vega=D("7.8211"))
    first = leg_input(BUY, PE, "22800", "42.50", "38.20", "0.117446", greeks=greeks)
    full = StrategyInput(
        underlying="NIFTY",
        spot=condor_inputs.spot,
        valuation_time=VALUATION,
        rate=RATE,
        legs=(first,) + condor_inputs.legs[1:],
        margin=MarginRequirement(total=D("41250.00"), source="broker basket margin"),
        charges=ChargesBreakdown(items=(("brokerage", D("80.00")), ("gst", D("14.40")))),
    )
    leg = full.legs[0]
    assert (leg.underlying, leg.contract, leg.expiry, leg.quantity) == ("NIFTY", "NIFTY26OCT22800PE", EXPIRY, 75)
    assert (leg.premium, leg.ltp, leg.iv, leg.greeks) == (D("42.50"), D("38.20"), D("0.117446"), greeks)
    assert (full.spot.level, full.margin.total, full.charges.total) == (D("23200"), D("41250.00"), D("94.40"))
    assert leg.leg == Leg(BUY, PE, D("22800"), EXPIRY, 75, D("42.50"), D("38.20"))
    assert isinstance(full.strategy, Strategy)
    assert full.strategy.live_pnl() == D("1365.00")
    assert full.strategy.expiry_pnl_at(D("22900")) == D("-675")


@pytest.mark.parametrize(
    "overrides, message",
    [
        (dict(underlying=""), "underlying"),
        (dict(contract="  "), "contract"),
        (dict(premium=D(42.3)), "entry_price"),  # float-built premium (42.3 is not exact in binary): Leg's paise check applies
        (dict(ltp=D("38.205")), "ltp"),
        (dict(quantity=0), "quantity"),
        (dict(iv=D("0")), "iv"),
        (dict(iv=D("5.5")), "iv"),
        (dict(iv=0.12), "iv"),
        (dict(iv=D("NaN")), "iv"),
        (dict(greeks=(D("0.5"),)), "greeks"),
    ],
)
def test_invalid_leg_input_fails_closed(overrides, message):
    """AC-2: every leg field is validated on construction; bad input raises ValueError, nothing defaults."""
    with pytest.raises(ValueError, match=message):
        leg_input(BUY, PE, "22800", "42.50", **({"ltp": "38.20", "iv": "0.117446"} | overrides))


def test_futures_leg_input_has_no_strike_or_iv():
    """AC-2: a futures leg is accepted without strike/IV and refused with an IV."""
    assert leg_input(BUY, FUT, None, "23250.00", contract="NIFTY26OCTFUT").leg.strike is None
    with pytest.raises(ValueError, match="no implied volatility"):
        leg_input(BUY, FUT, None, "23250.00", iv="0.12", contract="NIFTY26OCTFUT")


@pytest.mark.parametrize(
    "overrides, message",
    [
        (dict(spot=D("23200")), "SpotReading"),  # W-060 round 3: there is no bare level
        (dict(spot=None), "SpotReading"),
        (dict(valuation_time=datetime.datetime(2026, 10, 17, 15, 30)), "timezone-aware"),
        (dict(rate=0.065), "rate"),
        (dict(rate=D("Infinity")), "rate"),
        (dict(days_in_year=0), "days_in_year"),
        (dict(legs=()), "at least one leg"),
        (dict(underlying="SENSEX"), "strategy is on SENSEX"),
        (dict(margin=D("41250.00")), "MarginRequirement"),
        (dict(charges=D("94.40")), "ChargesBreakdown"),
    ],
)
def test_invalid_strategy_input_fails_closed(condor_inputs, overrides, message):
    """AC-2: strategy-level inputs are validated; a leg on another underlying is refused."""
    fields = dict(
        underlying="NIFTY", spot=condor_inputs.spot, valuation_time=VALUATION, rate=RATE, legs=condor_inputs.legs
    )
    fields.update(overrides)
    with pytest.raises(ValueError, match=message):
        StrategyInput(**fields)


def test_leg_input_is_the_only_leg_shape():
    """AC-2: LegInput builds the engine Leg (the Leg's own checks run), not a parallel copy of its rules."""
    with pytest.raises(ValueError, match="futures leg has no strike"):
        LegInput("NIFTY", "X", BUY, FUT, D("23000"), EXPIRY, 75, D("10.00"))
