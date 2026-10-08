"""Shared scenario fixtures.

- The §6 golden Iron Condor (scenario-calculations.md §6) as engine inputs at spot 23,047 (the §4 example's CURRENT).
- A SENSEX Iron Condor whose strikes, expiry and lot size come from the real instrument fixture
  (tests/fixtures/instruments/instruments_slice.csv, captured 2026-09-29): gap 100, lot 20. Its entry prices and
  spot are illustrative (the public list carries no prices).
"""
import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from ofo.engine.black_scholes import IST
from ofo.engine.inputs import LegInput, SpotReading, StrategyInput
from ofo.rules.inputs import DataHealth
from ofo.engine.legs import Action, Instrument
from ofo.instruments.catalogue import Catalogue, ContractKind
from ofo.instruments.parser import parse_instruments_csv
from ofo.scenario.config import ScenarioSettings

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"

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

SENSEX_EXPIRY = datetime.date(2026, 10, 1)
SENSEX_VALUATION = datetime.datetime(2026, 9, 29, 15, 30, tzinfo=IST)
SENSEX_SPOT = D("75530.45")
# Strikes listed in the real fixture for SENSEX 2026-10-01 (asserted in the test that uses them).
SENSEX_LEGS = [
    (Action.BUY, Instrument.PE, "74700", "60.00", "0.140"),
    (Action.SELL, Instrument.PE, "75300", "180.00", "0.130"),
    (Action.SELL, Instrument.CE, "75900", "170.00", "0.120"),
    (Action.BUY, Instrument.CE, "76500", "55.00", "0.125"),
]


def nifty_leg(action, instrument, strike, entry, ltp=None, iv=None, expiry=NIFTY_EXPIRY):
    return LegInput(
        underlying="NIFTY",
        contract=f"NIFTY26OCT{strike}{instrument.value}",
        action=action,
        instrument=instrument,
        strike=None if strike is None else D(strike),
        expiry=expiry,
        quantity=75,
        premium=D(entry),
        ltp=None if ltp is None else D(ltp),
        iv=None if iv is None else D(iv),
    )


def nifty_input(legs, spot=GOLDEN_SPOT):
    return gated(StrategyInput(underlying="NIFTY", valuation_time=VALUATION, rate=RATE, legs=tuple(legs),
                               spot=SpotReading(level=spot, at=VALUATION, health=DataHealth.AVAILABLE)))


def gated(si: StrategyInput):
    """The ModelInputs every product entry takes: the strategy input plus a spot-fallback forward (q = 0) per expiry,
    so the q = 0 expected values of these fixtures stay exactly as they were (W-060 round 3)."""
    from ofo.engine.model import model_inputs
    from ofo.marketdata.forward import spot_fallback_forward
    return model_inputs(si, {e: spot_fallback_forward(e, si.spot.level, si.spot.at, si.valuation_time, si.rate,
                                                      days_in_year=si.days_in_year, spot_health=si.spot.health)
                             for e in {leg.expiry for leg in si.legs}})


@pytest.fixture
def golden():
    return nifty_input(nifty_leg(*row) for row in GOLDEN_LEGS)


@pytest.fixture
def settings() -> ScenarioSettings:
    return ScenarioSettings()


@pytest.fixture(scope="session")
def catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load(parse_instruments_csv(FIXTURE))
    return cat


@pytest.fixture
def sensex(catalogue) -> StrategyInput:
    lot = catalogue.lot_size("SENSEX", SENSEX_EXPIRY, ContractKind.OPTION)
    listed = {c.strike for c in catalogue.contracts_for("SENSEX", SENSEX_EXPIRY, frozenset({"CE", "PE"}))}
    legs = []
    for action, instrument, strike, entry, iv in SENSEX_LEGS:
        assert D(strike) in listed, f"SENSEX {strike} is not listed for {SENSEX_EXPIRY}"
        legs.append(LegInput(
            underlying="SENSEX",
            contract=f"SENSEX26O01{strike}{instrument.value}",
            action=action,
            instrument=instrument,
            strike=D(strike),
            expiry=SENSEX_EXPIRY,
            quantity=lot,
            premium=D(entry),
            iv=D(iv),
        ))
    return gated(StrategyInput(underlying="SENSEX", valuation_time=SENSEX_VALUATION, rate=RATE, legs=tuple(legs),
                               spot=SpotReading(level=SENSEX_SPOT, at=SENSEX_VALUATION, health=DataHealth.AVAILABLE)))
