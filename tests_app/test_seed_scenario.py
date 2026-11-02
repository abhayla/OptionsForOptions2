"""scripts/seed_scenario.py refusals (no DB needed) and the booked-P&L arithmetic (GC-ADJ1 1b)."""
import datetime
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


# ---- #628: batch shape and the adjustments_used check (pure, no DB) ----
def _position(scenario_id: str) -> dict:
    return json.loads((seed.FIXTURES / f"{scenario_id}.json").read_text(encoding="utf-8"))["position"]


def _clock(position: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(position["entry"]["clock"])


def _described(batch: list) -> set:
    return {(side, leg["type"], leg["strike"], kind) for side, leg, _price, kind in batch}


def test_adj13_batches_are_entry_four_legs_then_one_adjustment():
    position = _position("ADJ-13")
    batches = seed.placement_batches(position, _clock(position))
    assert len(batches) == len(("entry", "adjustment 1"))
    assert _described(batches[0][1]) == {
        ("BUY", "PE", "22400", "open"), ("SELL", "PE", "22600", "open"),
        ("SELL", "CE", "23450", "open"), ("BUY", "CE", "23650", "open")}
    assert _described(batches[1][1]) == {
        ("SELL", "PE", "22400", "exit"), ("BUY", "PE", "22600", "exit"),
        ("BUY", "PE", "22700", "open"), ("SELL", "PE", "22900", "open")}
    assert seed.adjustments_used(position, _clock(position)) == position["adjustments_used"] == 1


def test_every_scenario_with_a_history_has_entry_plus_one_batch_per_adjustment():
    checked = 0
    for path in sorted(seed.FIXTURES.glob("ADJ-*.json")):
        position = json.loads(path.read_text(encoding="utf-8"))["position"]
        if not position.get("history"):
            continue
        n = int(position["adjustments_used"])
        batches = seed.placement_batches(position, _clock(position))
        every = position["history"] + position["legs"]
        assert len(batches) == n + 1, path.name
        assert len(batches[0][1]) == len([x for x in every if "opened_by" not in x]), path.name
        assert {kind for *_rest, kind in batches[0][1]} == {"open"}, path.name
        for number in range(1, n + 1):
            exits = [leg for _s, leg, _p, kind in batches[number][1] if kind == "exit"]
            opens = [leg for _s, leg, _p, kind in batches[number][1] if kind == "open"]
            assert exits == [h for h in position["history"] if int(h["adjustment"]) == number], path.name
            assert opens == [x for x in every if x.get("opened_by") == number], path.name
        assert seed.adjustments_used(position, _clock(position)) == n, path.name
        checked += 1
    assert checked == len(("ADJ-12", "ADJ-13"))


def test_a_count_the_orders_cannot_show_is_refused():
    position = _position("ADJ-45")  # adjustments_used 2 with no history: its orders show 0
    with pytest.raises(seed.SeedRefused, match="adjustments_used"):
        seed.check_adjustments_used(position, _clock(position))


def test_a_matching_position_passes_the_check():
    position = _position("ADJ-12")
    seed.check_adjustments_used(position, _clock(position))
