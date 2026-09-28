"""Shared engine fixture: the §6 Iron Condor as full engine inputs, valued 10 days before expiry."""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.black_scholes import IST
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument

EXPIRY = datetime.date(2026, 10, 27)
VALUATION = datetime.datetime(2026, 10, 17, 15, 30, tzinfo=IST)  # exactly 10 calendar days to the 15:30 close
SPOT = D("23200")
RATE = D("0.065")

# §6 legs (entry, LTP) with each leg's IV implied from its LTP at SPOT, VALUATION and RATE (implied_volatility()).
IRON_CONDOR = [
    (Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446"),
    (Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
    (Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
    (Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
]


def leg_input(action, instrument, strike, entry, ltp=None, iv=None, **overrides):
    fields = dict(
        underlying="NIFTY",
        contract=f"NIFTY26OCT{strike}{instrument.value}",
        action=action,
        instrument=instrument,
        strike=None if strike is None else D(strike),
        expiry=EXPIRY,
        quantity=75,
        premium=D(entry),
        ltp=D(ltp) if isinstance(ltp, str) else ltp,
        iv=D(iv) if isinstance(iv, str) else iv,
    )
    fields.update(overrides)
    return LegInput(**fields)


@pytest.fixture
def condor_inputs() -> StrategyInput:
    return StrategyInput(
        underlying="NIFTY",
        underlying_level=SPOT,
        valuation_time=VALUATION,
        rate=RATE,
        legs=tuple(leg_input(*row) for row in IRON_CONDOR),
    )
