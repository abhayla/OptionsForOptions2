"""#636 round 4: the background check path makes ZERO database calls in steady state.

The settings come from ``settings_cache.SettingsCache`` (every stored row in memory, resolved against the worker clock,
refreshed by a ``count(*)`` poll on its own task); record writes leave the check path through one coalescing writer
queue; the rebuild, the writer and the poll share ONE database gate (one connection at a time). The worker is the REAL
``background.Worker`` with scenario ADJ-02's fed provider (``test_background_cycle.Prov``); the database is a counting
fake connection that answers the two statements the cache sends (``count(*)`` and the store's own history read).
No wall clock: every clock is injected.
"""
from __future__ import annotations

import asyncio
import copy
import datetime
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.settings import defaults as registry_defaults
from ofo_app import adjustment_readers, background, calc_speeds, db, scenario_mode, settings_cache, strategy_store
from ofo_app.settings_store import SettingsError

from tests_app.test_background_cycle import (
    NO_RULES,
    Calls,
    FakeGate,
    Prov,
    _flag,
    _prefs,
    _tracked,
    _watched,
)

ONE_S = datetime.timedelta(seconds=1)
WARM_CYCLES = 50
STRATEGIES = 3
FUTURE = datetime.timedelta(minutes=2)
#: the per-style check intervals (ADR-235 (1)); a test sets every style to one value so the scenario's style
#: does not matter, and asserts on the first
SPEED_KEYS = tuple(calc_speeds.BACKGROUND_KEYS.values())
KEY = SPEED_KEYS[0]


@pytest.fixture(scope="module")
def scn():
    return scenario_mode.load("ADJ-02")


class FakeDb:
    """The app_settings table behind a counting fake connection: ``executes`` counts every statement; ``open_now`` /
    ``open_max`` the connections open at once; ``fail`` makes the next statements raise."""

    def __init__(self, rows=()) -> None:
        self.rows = list(rows)
        self.executes = 0
        self.open_now = self.open_max = 0
        self.fail: Exception | None = None

    def add(self, key: str, value: str, effective_from: datetime.datetime) -> None:
        self.rows.append(SimpleNamespace(key=key, value=Decimal(value), effective_from=effective_from,
                                         set_by="admin", note="", created_at=effective_from))

    def add_speed(self, value: str, effective_from: datetime.datetime) -> None:
        """One stored check interval for every style (ADR-235 (1))."""
        for key in SPEED_KEYS:
            self.add(key, value, effective_from)

    def connect(self):
        fake = self

        class _Conn:
            async def __aenter__(self):
                fake.open_now += 1
                fake.open_max = max(fake.open_max, fake.open_now)
                await asyncio.sleep(0)  # yield while open, so a second opener would overlap
                return self

            async def __aexit__(self, *_a):
                fake.open_now -= 1
                return False

            async def execute(self, stmt, *_a, **_k):
                fake.executes += 1
                if fake.fail is not None:
                    raise fake.fail
                if "count(*)" in str(stmt):
                    return SimpleNamespace(scalar_one=lambda: len(fake.rows))
                return SimpleNamespace(all=lambda: list(fake.rows))
        return _Conn()


def _cycle_rig(scn, fakedb: FakeDb, n: int = STRATEGIES, recorder=None, **kw):
    prov, now, calls = Prov(scn), [scn.clock_at], Calls()
    cache = settings_cache.SettingsCache(fakedb.connect)
    watched = _watched(scn, n)

    async def lister():
        return watched
    w = background.Worker(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0], settings=cache.at,
                          preferences=_prefs, recorder=recorder or calls, observe=calls.seen, db_gate=cache.gate,
                          **{"gate_store": FakeGate(), **kw})
    return prov, now, calls, cache, w


def _tick(prov, now) -> None:
    now[0] += ONE_S
    prov.move_spot(prov.spot.ltp + 1, now[0])


class _CountingSessions:
    """Any session opened through ``db.get_sessionmaker`` on the check path is counted (a hidden read)."""

    def __init__(self) -> None:
        self.opened = 0

    def __call__(self):
        outer = self

        class _S:
            async def __aenter__(self):
                outer.opened += 1
                return self

            async def __aexit__(self, *_a):
                return False
        return _S()


# ---- 1. the core: zero DB calls per check in steady state ------------------------------------------------------
async def test_core_zero_db_calls_on_the_check_path_in_steady_state(scn, monkeypatch):
    """50 cycles of 3 strategies after warm-up, the price moving every second: every strategy is checked every
    cycle, and the connection, the session factory and the recorder see ZERO calls. (Before #636 r4: 100 statements
    in 50 cycles, the settings read at background.py:756.)"""
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))  # a stored value in force: 1 s checks
    prov, now, calls, cache, w = _cycle_rig(scn, fakedb)
    assert await cache.refresh() is True
    await w.cycle()  # warm-up: the first list, the first check, the first write of each strategy
    await w.drain_writes()
    sessions = _CountingSessions()
    monkeypatch.setattr(db, "get_sessionmaker", lambda: sessions)
    fakedb.executes, checks, writes = 0, len(calls.states), len(calls.writes)
    for _ in range(WARM_CYCLES):
        _tick(prov, now)
        await w.cycle()
    assert len(calls.states) - checks == WARM_CYCLES * STRATEGIES  # every strategy checked every cycle
    assert (fakedb.executes, sessions.opened, len(calls.writes) - writes, len(w._pending)) == (0, 0, 0, 0)
    assert set(w.background_seconds().values()) == {Decimal(1)}  # the stored value, served from memory


# ---- 2. a future-dated setting takes effect on the worker clock, with no read -------------------------------------
async def test_a_future_dated_setting_takes_effect_when_the_clock_passes_it_with_no_db_call(scn):
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    fakedb.add_speed("3", scn.clock_at + FUTURE)
    _prov, now, _calls, cache, w = _cycle_rig(scn, fakedb, n=1)
    await cache.refresh()
    await w.cycle()
    assert set(w.background_seconds().values()) == {Decimal(1)}
    fakedb.executes = 0
    now[0] = scn.clock_at + FUTURE - ONE_S
    await w.cycle()
    assert set(w.background_seconds().values()) == {Decimal(1)}  # one second before: still the old value
    now[0] = scn.clock_at + FUTURE
    await w.cycle()
    assert set(w.background_seconds().values()) == {Decimal(3)}  # effective_from <= now: in force (REQ-167 AC-1)
    assert fakedb.executes == 0 and cache.loads == 1


# ---- 3. the count poll -------------------------------------------------------------------------------------------
def test_the_poll_period_is_named_and_the_lag_is_one_poll_plus_one_cycle():
    assert 2 <= settings_cache.POLL_SECONDS <= 5  # noqa: PLR2004 - the #636 design range
    assert settings_cache.LAG_SECONDS == settings_cache.POLL_SECONDS + background.WAKE_SECONDS


async def test_a_new_row_is_loaded_at_the_next_poll_and_an_unchanged_count_reads_no_rows(scn):
    fakedb = FakeDb()
    cache = settings_cache.SettingsCache(fakedb.connect)
    assert await cache.refresh() is True  # empty table: a valid load, every key at its registry default
    assert cache.at(scn.clock_at) == registry_defaults()
    fakedb.executes = 0
    assert await cache.refresh() is False and fakedb.executes == 1  # count unchanged: only the count(*) statement
    fakedb.add_speed("7", scn.clock_at - ONE_S)
    assert await cache.refresh() is True
    assert cache.at(scn.clock_at)[KEY] == Decimal(7) and cache.loads == 2  # noqa: PLR2004


async def test_the_poll_loop_sleeps_the_named_period_then_refreshes(scn):
    fakedb, slept = FakeDb(), []

    async def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 3:  # noqa: PLR2004
            raise asyncio.CancelledError
    cache = settings_cache.SettingsCache(fakedb.connect, sleep=sleep)
    with pytest.raises(asyncio.CancelledError):
        await cache.poll_loop()
    assert slept == [settings_cache.POLL_SECONDS] * 3 and cache.loads == 1


async def test_a_failed_poll_or_reload_keeps_the_last_good_cache_and_logs_once(scn, caplog):
    fakedb = FakeDb()
    fakedb.add_speed("4", scn.clock_at - ONE_S)
    cache = settings_cache.SettingsCache(fakedb.connect)
    await cache.refresh()
    fakedb.add_speed("9", scn.clock_at - ONE_S / 2)
    fakedb.fail = ConnectionError("database blip")
    caplog.set_level(logging.ERROR, logger="ofo_app.settings_cache")
    assert await cache.refresh() is False
    assert await cache.refresh() is False
    assert cache.at(scn.clock_at)[KEY] == Decimal(4) and cache.failures == 2  # noqa: PLR2004 - last good kept
    assert len([r for r in caplog.records if "refresh failed" in r.message]) == 1  # one line per failure streak
    fakedb.fail = None
    assert await cache.refresh() is True and cache.at(scn.clock_at)[KEY] == Decimal(9)


async def test_no_good_load_yet_refuses_to_check_and_logs_never_a_silent_default(scn, caplog):
    fakedb = FakeDb()
    fakedb.fail = ConnectionError("database down at start")
    _prov, now, calls, cache, w = _cycle_rig(scn, fakedb, n=1)
    assert await cache.refresh() is False
    with pytest.raises(SettingsError):
        cache.at(now[0])
    caplog.set_level(logging.ERROR, logger="ofo_app.background")
    await w.cycle()
    assert calls.states == [] and any("no background speed" in r.message for r in caplog.records)


# ---- 7. the registry check runs on load ---------------------------------------------------------------------------
async def test_a_stored_value_the_registry_refuses_fails_the_load_closed_and_keeps_the_last_good(scn):
    fakedb = FakeDb()
    cache = settings_cache.SettingsCache(fakedb.connect)
    fakedb.add_speed("9999", scn.clock_at - ONE_S)  # above the registry's max of 600: refused
    assert await cache.refresh() is False and cache.loaded is None
    with pytest.raises(SettingsError):
        cache.at(scn.clock_at)  # nothing good yet: the worker refuses to check
    fakedb.rows.clear()
    fakedb.add_speed("5", scn.clock_at - ONE_S)
    assert await cache.refresh() is True
    fakedb.add_speed("9999", scn.clock_at + FUTURE)  # a refused row, even future-dated, fails the reload
    assert await cache.refresh() is False and cache.at(scn.clock_at + FUTURE)[KEY] == Decimal(5)


async def test_a_row_for_a_key_the_registry_does_not_hold_is_ignored_as_today(scn):
    fakedb = FakeDb()
    fakedb.add("retired.key_no_longer_in_registry", "1", scn.clock_at - ONE_S)
    cache = settings_cache.SettingsCache(fakedb.connect)
    assert await cache.refresh() is True
    assert "retired.key_no_longer_in_registry" not in cache.at(scn.clock_at)


# ---- 4. a plan change is rechecked with no price tick --------------------------------------------------------------
async def test_a_plan_body_change_found_by_the_rebuild_is_rechecked_with_no_price_tick(scn):
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    _prov, now, calls, cache, w = _cycle_rig(scn, fakedb, n=1)
    await cache.refresh()
    await w.cycle()
    assert len(calls.states) == 1
    now[0] += ONE_S
    await w._rebuild_safely()  # same body: no reset
    await w.cycle()
    assert len(calls.states) == 1  # no tick, no change: not checked
    changed = copy.deepcopy(NO_RULES)
    changed["stages"]["weekly"][0]["name"] = "renamed"
    new = [background.Watched("owner", w.monitors[0].strategy_id, w.monitors[0].tracked, changed, True, "owner")]

    async def lister():
        return new
    w._lister = lister
    now[0] += ONE_S
    await w._rebuild_safely()
    assert w.monitors[0].strategy_id not in w._signature and w.monitors[0].strategy_id not in w._tick
    await w.cycle()
    assert len(calls.states) == 2  # noqa: PLR2004 - rechecked with no price tick


# ---- 5. the writer queue ------------------------------------------------------------------------------------------
async def test_two_flags_inside_one_write_slot_coalesce_into_one_write_of_the_latest_state(scn, monkeypatch):
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: _flag("R-1"))
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    prov, now, calls, cache, w = _cycle_rig(scn, fakedb, n=1)
    await cache.refresh()
    await w.cycle()
    _tick(prov, now)
    await w.cycle()  # the writer has not run: the second check replaces the first queued state
    assert len(calls.states) == 2 and calls.writes == []  # noqa: PLR2004
    await w.drain_writes()
    assert len(calls.writes) == 1 and calls.writes[0][1] is calls.states[-1][1]  # one write, the LATEST state
    assert w._memory.get(w.monitors[0].strategy_id) is not None


async def test_a_raising_write_leaves_rule_memory_unset_and_the_next_check_writes_again(scn, monkeypatch):
    monkeypatch.setattr(background.pe, "evaluate", lambda *_a, **_k: _flag("R-1"))
    boom, written = [True], []

    async def recorder(wd, state, _prefs=None):
        if boom[0]:
            boom[0] = False
            raise RuntimeError("db down")
        written.append(wd.strategy_id)
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    _prov, now, _calls, cache, w = _cycle_rig(scn, fakedb, n=1, recorder=recorder)
    await cache.refresh()
    await w.cycle()
    sid = w.monitors[0].strategy_id
    await w.drain_writes()
    assert sid not in w._memory and sid not in w._written and w.writes_failed == 1  # fail closed
    now[0] += ONE_S  # no price tick: the failed write forgot the signature, so the next cycle checks and queues
    await w.cycle()
    await w.drain_writes()
    assert written == [sid] and w._memory.get(sid) is not None


async def test_a_slow_writer_does_not_delay_other_strategies_checks(scn):
    """B4 (a): one strategy's write hangs (a 2 s write, never finishing inside the test) while the run loop goes on:
    every strategy is still checked every cycle, and the writer holds only its own task."""
    release, started = asyncio.Event(), []

    async def slow(wd, _state, _prefs=None):
        started.append(wd.strategy_id)
        await release.wait()  # the 2 s write: still running for the whole of the cycles below
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    never = asyncio.Event()

    async def rebuild_sleep(_s):
        await never.wait()
    cycles = [0]

    async def sleep(_s):
        cycles[0] += 1
        _tick(prov, now)
        if cycles[0] == 5:  # noqa: PLR2004
            seen[:] = list(calls.states)
            busy[:] = list(started)
            release.set()
            w.stop()
        await asyncio.sleep(0)
    seen, busy = [], []
    prov, now, calls, cache, w = _cycle_rig(scn, fakedb, recorder=slow, sleep=sleep, rebuild_sleep=rebuild_sleep)
    await cache.refresh()
    await w.run()
    assert busy == [w.monitors[0].strategy_id]  # the writer was stuck in the first write all along
    per = {sid: sum(1 for s, _ in seen if s == sid) for sid in (m.strategy_id for m in w.monitors)}
    assert all(n == 5 for n in per.values()), per  # noqa: PLR2004 - checked every cycle regardless


# ---- 6. connection budget: one connection at a time ---------------------------------------------------------------
async def test_poll_rebuild_and_writer_share_one_gate_so_at_most_one_connection_is_open(scn):
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))

    async def on_db():
        async with fakedb.connect() as conn:
            await conn.execute("SELECT 1")

    async def lister():
        await on_db()
        return _watched(scn, 2)

    async def preferences(user):
        await on_db()
        return await _prefs(user)

    async def recorder(_wd, _state, _prefs=None):
        await on_db()
    _prov, _now, _calls, cache, w = _cycle_rig(scn, fakedb, recorder=recorder)
    w._lister, w._preferences = lister, preferences
    await cache.refresh()
    await w.cycle()  # queues the first writes of both strategies
    assert len(w._pending) == 2  # noqa: PLR2004
    fakedb.rows.append(fakedb.rows[0])  # a count change, so the poll reloads too
    fakedb.open_max = 0
    await asyncio.gather(w._rebuild_safely(), cache.refresh(), w.drain_writes(), cache.refresh(), w._rebuild_safely())
    assert fakedb.open_max == 1 and cache.gate is w.db_gate


async def test_owner_lister_never_holds_two_sessions_at_once(scn, monkeypatch):
    """``read_tracked`` opens its own session: the list's session is closed before it (before #636 r4 the lister held
    its session across ``read_tracked``: two connections from one role)."""
    open_now, open_max = [0], [0]

    class _S:
        async def __aenter__(self):
            open_now[0] += 1
            open_max[0] = max(open_max[0], open_now[0])
            return self

        async def __aexit__(self, *_a):
            open_now[0] -= 1
            return False
    monkeypatch.setattr(db, "get_sessionmaker", lambda: _S)

    async def list_strategies(_db, _owner):
        return [SimpleNamespace(id=i) for i in (1, 2)]

    async def read_tracked(_sid, _x):
        async with _S():
            return _tracked(scn)

    async def resolve(_db, _owner, _sid, _stype):
        return SimpleNamespace(body=NO_RULES, is_system=True)
    monkeypatch.setattr(strategy_store, "list_strategies", list_strategies)
    monkeypatch.setattr(adjustment_readers, "read_tracked", read_tracked)
    monkeypatch.setattr(background.check, "strategy_type", lambda *_a: "short_strangle")
    monkeypatch.setattr(background.check, "resolve", resolve)
    out = await background.owner_lister(Prov(scn))
    assert [w.strategy_id for w in out] == [1, 2] and open_max[0] == 1
