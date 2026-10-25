"""Pytest fixtures for the engine tests; the shared constants and helpers live in engine_fixtures.py (a uniquely
named module, so no test imports the bare name `conftest`)."""
import pytest

from engine_fixtures import IRON_CONDOR, RATE, SPOT, VALUATION, leg_input
from ofo.engine.inputs import SpotReading, StrategyInput
from ofo.rules.inputs import DataHealth

@pytest.fixture
def condor_inputs() -> StrategyInput:
    return StrategyInput(
        underlying="NIFTY",
        spot=SpotReading(level=SPOT, at=VALUATION, health=DataHealth.AVAILABLE),
        valuation_time=VALUATION,
        rate=RATE,
        legs=tuple(leg_input(*row) for row in IRON_CONDOR),
    )
