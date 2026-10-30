"""scripts/seed_scenario.py refusals (no DB needed) and the booked-P&L arithmetic (GC-ADJ1 1b)."""
import importlib.util
import json
import pathlib
from decimal import Decimal

import pytest

pytestmark = pytest.mark.repo_scan  # the history test walks the fixture folder

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def url(database: str) -> str:
    return f"postgresql+asyncpg://example@localhost:5432/{database}"


def test_dev_database_in_development_or_test_is_accepted():
    seed.check_environment({"APP_ENV": "development", "DATABASE_URL": url("ofo_dev")})
    seed.check_environment({"APP_ENV": "test", "DATABASE_URL": url("ofo_dev")})
    seed.check_environment({"DATABASE_URL": url("ofo_dev")})  # APP_ENV unset = the app's own default, development


@pytest.mark.parametrize("app_env", ["production", "staging", "Development", " test", ""])
def test_other_app_env_is_refused(app_env):
    with pytest.raises(seed.SeedRefused):
        seed.check_environment({"APP_ENV": app_env, "DATABASE_URL": url("ofo_dev")})


@pytest.mark.parametrize("name", ["ofo_test", "ofo_dev2", "xofo_dev", "ofo", ""])
def test_any_database_but_ofo_dev_is_refused(name):
    with pytest.raises(seed.SeedRefused):
        seed.check_environment({"APP_ENV": "development", "DATABASE_URL": url(name)})


def test_missing_or_unreadable_database_url_is_refused():
    for env in ({"APP_ENV": "development"}, {"APP_ENV": "development", "DATABASE_URL": "not a url"}):
        with pytest.raises(seed.SeedRefused):
            seed.check_environment(env)


@pytest.mark.parametrize("bad", ["ADJ-99", "../ADJ-02", "ADJ-02.json", "", "adj-02"])
def test_an_id_that_is_not_a_fixture_file_is_refused(bad):
    with pytest.raises(seed.SeedRefused):
        seed.scenario_path(bad)


def test_a_fixture_id_resolves_to_its_file():
    assert seed.scenario_path("ADJ-13").name == "ADJ-13.json"


def test_history_booked_equals_every_scenarios_booked_pnl():
    checked = 0
    for path in sorted(seed.FIXTURES.glob("ADJ-*.json")):
        position = json.loads(path.read_text(encoding="utf-8")).get("position")
        if position and position.get("history"):
            assert seed.booked(position["history"]) == Decimal(position["booked_pnl"]), path.name
            checked += 1
    assert checked >= 1
