"""#636 round 6: the worker's cycle loop never waits on the role's one database gate (``db_gate``).

Live 2026-11-04: minutes 09:21 / 09:42 ran 16 / 24 cycles against ~55, and record 129 (confirmed at the 09:42:00 close)
was written at 09:42:33, because (1) the alert gate's record write was awaited INSIDE the cycle under ``db_gate`` and
(2) the strategy-list rebuild held ``db_gate`` for the whole list. Here: a lister that holds the gate strategy after
strategy (a 60 s hold in six 10 s steps, each step released by the test: no wall clock) never stops the cycle loop, a
gate event queued meanwhile is written by the ONE writer within one per-strategy hold, events of one strategy are
written in order (never merged, never dropped), a failing event write stays queued in order, and at most one
connection is open at a time. The worker is the REAL ``background.Worker`` (``_cycle_rig``); only the gate store, the
lister and ``alert_gate.step`` (to place an event on a chosen cycle) are fakes.
"""
from __future__ import annotations

import asyncio
import datetime
import inspect
from types import SimpleNamespace

import pytest
from ofo_app import background, scenario_mode

from tests_app.test_background_settings_cache import FakeDb, _cycle_rig, _tick

LISTED = 6  # strategies the lister reads, one gate hold each (the 60 s hold = 6 x 10 s)
YIELDS = 50  # event-loop turns a cycle gets to finish; a cycle that waits on the gate never finishes in them


@pytest.fixture(scope="module")
def scn():
    return scenario_mode.load("ADJ-02")


async def _turns(n: int = YIELDS) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


class _Store:
    """The gate store: every applied batch kept as (strategy, event names, lister step at the write)."""

    def __init__(self, step_of=lambda: None) -> None:
        self.batches: list[tuple[int, tuple, object]] = []
        self.fail = 0
        self._step_of = step_of

    async def load(self, _w, _today):
        return background.GateLoad(background.alert_gate.GateRows((), 0))

    async def apply(self, w, events, _ctx):
        await asyncio.sleep(0)
        if self.fail:
            self.fail -= 1
            raise RuntimeError("write refused")
        self.batches.append((w.strategy_id, tuple(e.name for e in events), self._step_of()))
        return {}


def _fire_on_next_step(monkeypatch):
    """``alert_gate.step`` answers the real state plus the queued events, one queued list per call (strategy order)."""
    queued: list[list] = []

    def step(state, *, now, preset, readings):
        del now, preset, readings
        return state, (queued.pop(0) if queued else [])
    monkeypatch.setattr(background.alert_gate, "step", step)
    return queued


def _ev(name: str):
    return SimpleNamespace(name=name, rule_id="T-01")


async def _gated(scn, monkeypatch, store, n=1):
    fakedb = FakeDb()
    fakedb.add_speed("1", scn.clock_at - datetime.timedelta(days=1))
    prov, now, calls, cache, w = _cycle_rig(scn, fakedb, n=n, gate_store=store)
    await cache.refresh()
    await w.cycle()  # the first list (quick lister), checks, the writer queue
    await w.drain_writes()
    for m in w.monitors:  # every strategy gated (the close pass steps it each cycle)
        w._gate.setdefault(m.strategy_id, background.alert_gate.initial_state())
        w._preset.setdefault(m.strategy_id, object())
    return prov, now, calls, cache, w, fakedb


async def test_core_a_lister_holding_the_gate_60s_never_stops_the_loop_and_the_event_lands_within_one_hold(
        scn, monkeypatch):
    queued = _fire_on_next_step(monkeypatch)
    step = [0]  # the lister step running now (0..LISTED-1), LISTED when done
    store = _Store(lambda: step[0])
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store)
    monitors = list(w.monitors)
    released = [asyncio.Event() for _ in range(LISTED)]

    async def lister():  # the real lister's shape: one gate hold per strategy's reads (10 s each, the test releases)
        for i in range(LISTED):
            async with w.db_gate:
                step[0] = i
                await released[i].wait()
        step[0] = LISTED
        return monitors
    w._lister = lister
    rebuild = asyncio.create_task(w._rebuild_safely())
    await _turns()
    assert w.db_gate.locked() and step[0] == 0  # the 60 s hold is under way
    queued.append([_ev("opened")])  # a confirmed crossing at this cycle's close
    cycles = []
    for _ in range(5):  # the loop keeps cycling once a second through the hold
        _tick(prov, now)
        task = asyncio.create_task(w.cycle())
        await _turns()
        cycles.append(task.done())
        if not task.done():
            break
    assert cycles == [True] * 5, cycles  # red on 5bf9a342: the first cycle waits on db_gate for the whole hold
    writer = asyncio.create_task(w.drain_writes())
    await _turns()
    released[0].set()  # the first per-strategy hold ends
    await _turns()
    assert [(sid, names) for sid, names, _s in store.batches] == [(monitors[0].strategy_id, ("opened",))]
    assert store.batches[0][2] == 0  # written before the lister's second hold began: within one per-strategy hold
    for e in released:
        e.set()
    await asyncio.gather(rebuild, writer)
    print(f"CORE-PROOF cycles_during_hold={len(cycles)} event_written_at_lister_step={store.batches[0][2]} "
          f"holds={LISTED}")


async def test_the_cycle_path_never_awaits_the_gate_even_when_it_is_held_forever(scn, monkeypatch):
    """B4 (a): a gate held for the whole test; 20 cycles with an event on every other one all finish."""
    queued = _fire_on_next_step(monkeypatch)
    store = _Store()
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store)
    never = asyncio.Event()

    async def hold():
        async with w.db_gate:
            await never.wait()
    holder = asyncio.create_task(hold())
    await _turns()
    for i in range(20):
        if i % 2 == 0:
            queued.append([_ev(f"e{i}")])
        _tick(prov, now)
        task = asyncio.create_task(w.cycle())
        await _turns()
        assert task.done(), i
    assert store.batches == [] and len(w._gate_events[w.monitors[0].strategy_id]) == 10  # noqa: PLR2004 - queued
    never.set()
    await holder
    await w.drain_writes()
    assert [names for _s, names, _x in store.batches] == [(f"e{i}",) for i in range(0, 20, 2)]


def test_the_cycle_path_names_no_db_gate():
    """Structural half of B4 (a): no method the cycle reaches names ``db_gate``."""
    path = (background.Worker.cycle, background.Worker._check_one, background.Worker._check_unpaused,
            background.Worker._evaluate_and_gate, background.Worker._evaluate_and_write, background.Worker._gate_step,
            background.Worker._close_pass, background.Worker._write_wants, background.Worker._pause)
    named = [f.__name__ for f in path if "db_gate" in inspect.getsource(f)]
    assert named == []


async def test_open_then_lapse_of_one_rule_are_written_in_that_order_never_merged(scn, monkeypatch):
    queued = _fire_on_next_step(monkeypatch)
    store = _Store()
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store)
    queued.append([_ev("opened")])
    _tick(prov, now)
    await w.cycle()
    queued.append([_ev("lapsed")])
    _tick(prov, now)
    await w.cycle()
    await w.drain_writes()
    assert [names for _s, names, _x in store.batches] == [("opened",), ("lapsed",)]


async def test_a_failing_event_write_stays_queued_in_order_and_lands_at_the_next_drain(scn, monkeypatch):
    queued = _fire_on_next_step(monkeypatch)
    store = _Store()
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store)
    store.fail = 1
    queued.append([_ev("opened")])
    _tick(prov, now)
    await w.cycle()
    queued.append([_ev("lapsed")])
    _tick(prov, now)
    await w.cycle()
    await w.drain_writes()  # the first write raises: both stay queued, nothing written out of order
    assert store.batches == [] and w.gate_writes_failed == 1
    assert [b.events[0].name for b in w._gate_events[w.monitors[0].strategy_id]] == ["opened", "lapsed"]
    await w.drain_writes()  # the next wake retries
    assert [names for _s, names, _x in store.batches] == [("opened",), ("lapsed",)]


async def test_a_writer_task_that_dies_is_restarted_and_its_queued_events_land_in_order(scn, monkeypatch):
    queued = _fire_on_next_step(monkeypatch)
    store = _Store()
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store)
    queued.append([_ev("opened")])
    _tick(prov, now)
    await w.cycle()
    queued.append([_ev("lapsed")])
    _tick(prov, now)
    await w.cycle()
    real, raised = w._write_gate_batch, []

    async def dies(sid):
        if not raised:
            raised.append(sid)
            raise RuntimeError("writer bug")
        return await real(sid)
    w._write_gate_batch = dies
    w._watch_writer()
    await _turns()
    assert w._writer.done() and store.batches == []
    w._watch_writer()  # the next cycle's watch: logged and restarted
    await _turns()
    assert w.writer_restarts == 1 and [names for _s, names, _x in store.batches] == [("opened",), ("lapsed",)]
    w.stop()
    w._write_wake.set()
    await _turns()


async def test_events_of_a_strategy_that_left_the_list_are_dropped_with_a_log_line(scn, monkeypatch, caplog):
    queued = _fire_on_next_step(monkeypatch)
    store = _Store()
    prov, now, _calls, _cache, w, _db = await _gated(scn, monkeypatch, store, n=2)
    gone, kept = (m.strategy_id for m in w.monitors)
    queued.extend([[_ev("opened-gone")], [_ev("opened-kept")]])
    _tick(prov, now)
    await w.cycle()
    still = [m for m in w.monitors if m.strategy_id == kept]

    async def lister():
        return still
    w._lister = lister
    await w._rebuild_safely()
    await w.drain_writes()
    assert [(sid, names) for sid, names, _x in store.batches] == [(kept, ("opened-kept",))]
    assert w.gate_events_dropped == 1
    assert any(f"alert events of strategy {gone} were dropped" in r.getMessage() for r in caplog.records)


async def test_the_writer_is_served_before_the_poll_and_the_poll_before_the_rebuild():
    """Order of service at the gate: event writes, then the settings poll, then the rebuild (ADR-237 (3) 10 s)."""
    gate = background.DbGate()
    served: list[str] = []
    first = asyncio.Event()

    async def take(name, rank):
        async with gate.hold(rank):
            served.append(name)
            if name == "first":
                await first.wait()
    holder = asyncio.create_task(take("first", background.GATE_REBUILD))
    await _turns(3)
    tasks = [asyncio.create_task(take(n, r)) for n, r in (("rebuild", background.GATE_REBUILD),
                                                           ("poll", background.GATE_POLL),
                                                           ("writer", background.GATE_WRITER))]
    await _turns(3)
    first.set()
    await asyncio.gather(holder, *tasks)
    assert served == ["first", "writer", "poll", "rebuild"]


async def test_a_cancelled_waiter_never_keeps_the_gate():
    gate = background.DbGate()
    release = asyncio.Event()

    async def hold():
        async with gate:
            await release.wait()
    holder = asyncio.create_task(hold())
    await _turns(3)
    waiter = asyncio.create_task(gate.hold(background.GATE_WRITER).__aenter__())
    await _turns(3)
    waiter.cancel()
    await _turns(3)
    release.set()
    await holder
    assert not gate.locked()


async def test_the_owner_lister_opens_each_session_inside_its_own_gate_hold(scn, monkeypatch):
    """Attack 4: one connection at a time, and each strategy's reads are their own hold (never one for the list)."""
    from ofo_app import adjustment_readers, db, strategy_store  # noqa: PLC0415

    from tests_app.test_background_cycle import NO_RULES, Prov, _tracked  # noqa: PLC0415
    gate = background.DbGate()
    holds, seen = [0], []
    real_hold = gate.hold

    def counted(rank=background.GATE_REBUILD):
        holds[0] += 1
        return real_hold(rank)
    gate.hold = counted

    class _S:
        async def __aenter__(self):
            seen.append(gate.locked())
            return self

        async def __aexit__(self, *_a):
            return False
    monkeypatch.setattr(db, "get_sessionmaker", lambda: _S)

    async def list_strategies(_db, _owner):
        return [SimpleNamespace(id=i) for i in (1, 2, 3)]

    async def read_tracked(_sid, _x):
        async with _S():
            return _tracked(scn)

    async def resolve(_db, _owner, _sid, _stype):
        return SimpleNamespace(body=NO_RULES, is_system=True)
    monkeypatch.setattr(strategy_store, "list_strategies", list_strategies)
    monkeypatch.setattr(adjustment_readers, "read_tracked", read_tracked)
    monkeypatch.setattr(background.check, "strategy_type", lambda *_a: "short_strangle")
    monkeypatch.setattr(background.check, "resolve", resolve)
    out = await background.owner_lister(Prov(scn), gate=gate)
    assert [w.strategy_id for w in out] == [1, 2, 3]
    assert seen and all(seen)  # every session opened while the gate was held
    assert holds[0] == 1 + 3  # noqa: PLR2004 - the list read, then one hold per strategy
