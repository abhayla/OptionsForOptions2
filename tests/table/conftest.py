"""Fixtures for the table tests: the §6 golden Iron Condor plus its scenario level set/values.

Legs and IVs match tests/scenario/scenario_fixtures.py (kept self-contained here: tests/table is its own pytest
rootless-import directory, so it does not share that module's sys.path entry).
"""
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine.black_scholes import IST
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.scenario.config import ScenarioSettings
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import scenario_values

NIFTY_EXPIRY = datetime.date(2026, 10, 27)
VALUATION = datetime.datetime(2026, 10, 17, 15, 30, tzinfo=IST)
GOLDEN_SPOT = D("23047")
RATE = D("0.065")

# (action, instrument, strike, entry, ltp, iv) — §6 legs; IVs as in tests/engine/conftest.py.
GOLDEN_LEGS = [
    (Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446"),
    (Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
    (Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
    (Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
]


def nifty_leg(action, instrument, strike, entry, ltp=None, iv=None, greeks=None, expiry=NIFTY_EXPIRY,
              quantity=75):
    return LegInput(
        underlying="NIFTY",
        contract=f"NIFTY26OCT{strike}{instrument.value}" if strike is not None else "NIFTY26OCTFUT",
        action=action,
        instrument=instrument,
        strike=None if strike is None else D(strike),
        expiry=expiry,
        quantity=quantity,
        premium=D(entry),
        ltp=None if ltp is None else D(ltp),
        iv=None if iv is None else D(iv),
        greeks=greeks,
    )


def nifty_input(legs, spot=GOLDEN_SPOT, valuation=VALUATION) -> StrategyInput:
    return StrategyInput(underlying="NIFTY", underlying_level=spot, valuation_time=valuation, rate=RATE,
                         legs=tuple(legs))


@pytest.fixture
def golden() -> StrategyInput:
    return nifty_input(nifty_leg(*row) for row in GOLDEN_LEGS)


@pytest.fixture
def settings() -> ScenarioSettings:
    return ScenarioSettings()


@pytest.fixture
def golden_scenario(golden, settings):
    config = settings.for_index("NIFTY")
    level_set = build_level_set(golden, config)
    values = scenario_values(level_set, golden)
    return level_set, values
