"""Pytest fixtures for the table tests; the golden Iron Condor constants and helpers live in table_fixtures.py (a
uniquely named module, so no test imports the bare name `conftest`)."""
import pytest

from table_fixtures import GOLDEN_LEGS, nifty_input, nifty_leg
from ofo.scenario.config import ScenarioSettings
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import scenario_values

@pytest.fixture
def golden():
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
