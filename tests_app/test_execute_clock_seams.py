"""INSTR-FRESH round 3 (independent redesign): the instrument-list freshness rule is judged on a clock the caller
controls, never on the wall-clock hour a test or the CI replay happens to run at.

RCA: the list-load stamp is written by the database trigger (``clock_timestamp()``) and was judged on the database
clock, while every route test and the CI replay pinned only the REQUEST clock (``get_execute_clock`` -> ``AT``). With
the 08:30 IST publish rule, any run between 00:00 and 08:30 IST saw its own seed as a pre-publish load: STALE.
Class: every path that seeds a list load and then executes; the stamp and its judging clock now come from ONE seam,
``execute.get_list_stamp``. Production answers it from the database (both sides); the test-only replay answers the
recorded day's pair (``execute_replay.replay_list_stamp``), installed together with the request clock
(``replay_clocks``). The rule itself (``execute._list_health``) is unchanged and shared.

No database: the stamp reads are monkeypatched; the real route and replay functions run.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from ofo.execution.context import DataHealth, DataInput
from ofo.timeutil import IST
from ofo_app import eligibility_from_zerodha as elig
from ofo_app import execute_replay as er
from ofo_app.routes import execute as route

#: a CI run before the publish time: the seed stamped the list at 07:00 IST and Execute runs at 07:00:05 IST
SEEDED_07_00 = datetime.datetime(2026, 10, 20, 7, 0, tzinfo=IST)
NOW_07_00 = SEEDED_07_00 + datetime.timedelta(seconds=5)


def _database(monkeypatch, loaded, now) -> None:
    async def _loaded_at(conn):
        return loaded

    async def _now(conn):
        return now

    monkeypatch.setattr(elig, "list_loaded_at", _loaded_at)
    monkeypatch.setattr(elig, "database_now", _now)


async def _listing(stamp) -> DataHealth:
    req = SimpleNamespace(db=None, now=er.AT, clock=lambda: er.AT, list_stamp=stamp,
                          quotes=SimpleNamespace(underlying_price=lambda u: None))
    return (await route._data_health(req, SimpleNamespace(quote_times=()), "NIFTY"))[DataInput.INSTRUMENT_LIST]


async def test_core_a_seed_at_07_00_ist_is_healthy_under_the_replay_and_stale_in_production(monkeypatch):
    _database(monkeypatch, SEEDED_07_00, NOW_07_00)
    assert await _listing(route.database_list_stamp) is DataHealth.STALE  # production keeps the 08:30 rule
    replay = er.overrides()[route.get_list_stamp]()  # exactly what create_app installs under EXECUTE_REPLAY
    assert await _listing(replay) is DataHealth.HEALTHY


@pytest.mark.parametrize("hour", [0, 3, 7, 8, 9, 12, 15, 18, 23])
async def test_the_replay_answer_does_not_depend_on_the_database_hour(monkeypatch, hour):
    at = datetime.datetime(2026, 10, 20, hour, 0, tzinfo=IST)
    _database(monkeypatch, at, at + datetime.timedelta(seconds=1))
    assert await er.replay_list_stamp(None) == (er.LIST_LOADED_AT, er.AT)
    assert await _listing(er.replay_list_stamp) is DataHealth.HEALTHY


async def test_the_replay_still_reads_whether_a_list_was_ever_loaded(monkeypatch):
    _database(monkeypatch, None, NOW_07_00)
    assert await _listing(er.replay_list_stamp) is DataHealth.UNAVAILABLE


def test_the_recorded_pair_obeys_the_rule_it_is_judged_by():
    """The replay's pair is a real case of the rule (a load after 08:30 on the session's own day), not a bypass."""
    assert er.LIST_LOADED_AT.date() == er.AT.date() and er.LIST_LOADED_AT <= er.AT
    assert route._list_health(er.LIST_LOADED_AT, er.AT) is DataHealth.HEALTHY
    assert route._list_health(er.LIST_LOADED_AT.replace(hour=8, minute=29), er.AT) is DataHealth.STALE


def test_production_answers_the_list_stamp_from_the_database():
    assert route.get_list_stamp() is route.database_list_stamp
    assert route._Request.__dataclass_fields__["list_stamp"].default is route.database_list_stamp


async def test_production_reads_both_sides_from_the_database(monkeypatch):
    _database(monkeypatch, SEEDED_07_00, NOW_07_00)
    assert await route.database_list_stamp(None) == (SEEDED_07_00, NOW_07_00)


def test_replay_clocks_pin_the_request_clock_and_the_list_stamp_together():
    clocks = er.replay_clocks()
    assert set(clocks) == {route.get_execute_clock, route.get_list_stamp}
    assert clocks[route.get_execute_clock]()() == er.AT
    assert clocks[route.get_list_stamp]() is er.replay_list_stamp
    assert set(clocks) <= set(er.overrides())
