"""GC-MU step 4 core (REQ-165 AC-1, AC-5; REQ-115 AC-3): the background role checks a tracked strategy with NO client
connected. Scenario ADJ-02 is seeded through the app's own stores (as ``test_adjustment_check.py``) and its fed
``KiteProvider`` (the real frame parser) is the worker's provider. A frame with spot 23000 (T-01 false) is checked
first; then the frame with the scenario's spot 23420 crosses T-01. Exactly one opportunity record is opened for T-01,
its found-time (the record's own first timeline time, the database clock) within 1 s of the moment the crossing
price reached the provider (read from the same database clock). A restarted worker monitors the same strategy within
60 s, re-opens nothing and keeps the rule memory.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import datetime
import importlib.util
import itertools
import pathlib
import time
from decimal import Decimal as D

import pytest
from _scenario_catalogue import load_library
from ofo.adjustment import alert_gate
from ofo.adjustment.preferences import from_values
from ofo.settings import defaults as registry_defaults
from ofo_app import background, playbook_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
BEFORE_CROSS_SPOT = "23000"  # 2.1 % below the 23500 CE short and 1.3 % above the 22700 PE short: T-01 (0.5 %) false
ONE_SECOND = datetime.timedelta(seconds=1)
REBUILD_LIMIT_S = 60
CROSS_SPOT = "23420"  # the scenario's spot: 80 points under the 23500 CE short, 0.34 %: T-01 (0.5 %) true
INSIDE_BAND_SPOT = "23375"  # 125 points, 0.53 %: T-01 false but inside the intraday 10 % band (re-arms at 0.55 %)
WOBBLE_EVERY_S = 18  # 20 moves in 6 minutes = 10 crossings and 10 re-crossings, each after a full 10 s interval


async def _held_total(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.adjustment_held_crossings "
                                        "WHERE strategy_id = :s"), {"s": sid})).scalar_one()


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
async def app_db_url(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()
    yield app_engine
    await app_db.close_db()
    _reset_engine()


_SEED_RUN = itertools.count(1)


async def _seeded(app_engine, monkeypatch) -> tuple[int, scenario_mode.Scenario]:
    """ADJ-02 seeded as THIS test's own strategy, and the owner's strategy list narrowed to it for the test (#663).
    The scenario clock is fixed but records carry the database clock: a record a previous test left on a shared
    strategy is stamped days after the scenario clock and its cool-down never passes. A fresh strategy per test (the
    seed is idempotent by name, so each test gets its own name) and a list of only that strategy mean no test reads
    another's records, rule memory, held rows or day count."""
    from ofo_app import strategy_store  # noqa: PLC0415
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    scn = scenario_mode.load("ADJ-02")
    await load_library(app_engine)  # the whole library's list, once per database
    run = next(_SEED_RUN)
    monkeypatch.setattr(seed_mod, "strategy_name", lambda scenario_id: f"{seed_mod.NAME_PREFIX}{scenario_id} t{run}")
    sid = await seed_mod.seed("ADJ-02")
    real_list = strategy_store.list_strategies

    async def own(conn, user_ref):
        return [s for s in await real_list(conn, user_ref) if s.id == sid]
    monkeypatch.setattr(strategy_store, "list_strategies", own)
    return sid, scn


def _push_spot(scn: scenario_mode.Scenario, spot: str, received: datetime.datetime) -> None:
    """One Kite index frame through the provider's real parser (as scenario_mode.load feeds it)."""
    quote = scn.provider.underlying_quote("NIFTY")
    token = int(quote.instrument_id.split(":")[-1])
    lc = next(x for x in scn.provider.instrument_master() if str(x.contract.exchange_token) == str(token))
    broker_token = int(lc.broker_refs[0].broker_token)
    packet = scenario_mode._index_packet(broker_token, spot, int(received.timestamp()))
    scn.provider.on_frame(scenario_mode._frame([packet]), received)


async def _db_now(engine) -> datetime.datetime:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def _t01_records(engine, sid: int) -> list:
    async with engine.connect() as conn:
        rows = await playbook_store.open_suggestions(conn, "owner", sid)
    return [r for r in rows if r.rule_id == "T-01"]


async def _t01_total(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-01'"), {"s": sid})).scalar_one()


class _Draining(background.Worker):
    """The real Worker with its writer queue written at the end of each cycle (#636 r4; no writer task here)."""

    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


def _worker(scn: scenario_mode.Scenario, clock, *, overrides: dict | None = None, lister=None) -> background.Worker:
    """The real Worker. ``overrides`` = alert values that differ from the registry defaults (a lower daily cap, a
    later quiet time); ``lister`` = another way to list the watched strategies (a changed plan)."""
    def settings(_at):
        return registry_defaults()  # the settings in force: the registry defaults, passed explicitly

    async def preferences(_user_ref):
        return from_values(registry_defaults())  # the owner's preferences: the registry defaults (REQ-168 AC-1)

    async def user_values(_user_ref):
        return {**registry_defaults(), **(overrides or {})}  # the owner's alert values in force (REQ-170 AC-6)
    return _Draining(provider_for=lambda _owner: scn.provider,
                     lister=lister or (lambda: background.owner_lister(scn.provider)), clock=clock,
                     settings=settings, preferences=preferences, user_values=user_values)


async def _pin_intraday(engine, sid: int) -> None:
    """The user pins the intraday style (REQ-170 Q-AD-2): 1-minute candles, 10 s checks, 10 % band."""
    async with engine.connect() as conn:
        if (await strategy_alert_style_store.pin_of(conn, "owner", sid)).style != "intraday":
            await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
            await conn.commit()


async def _t01_ids(engine, sid: int) -> list[tuple[int, str]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, outcome FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-01' ORDER BY id"), {"s": sid})).all()
    return [(r[0], r[1]) for r in rows]


async def _settle_clear(worker, scn, now, start) -> datetime.datetime:
    """Spot 23000 (T-01 1.3 %, clear by the band) until two 1-minute closes pass: the rule is armed and cleared
    before the test's crossing (each test has its own strategy since #663, so nothing earlier is open)."""
    _push_spot(scn, BEFORE_CROSS_SPOT, start)
    for s in range(121):
        now[0] = start + datetime.timedelta(seconds=s)
        await worker.cycle()
    return now[0]


async def test_core_wobble_10_crossings_in_6_minutes_opens_one_record_at_a_candle_close(app_db_url, monkeypatch):
    """GC-ALERT1 core (REQ-170 AC-1/AC-2, ADR-237 (2)-(4)): T-01 crosses its 0.5 % line and comes back inside the
    10 % band (0.50-0.55 %) ten times in six minutes, one check each 18 s. ONE record opens, at the first 1-minute
    candle close after the crossing (plus at most one 10 s interval); no Lapsed until a close clears the band."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    await _pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    worker = _worker(scn, lambda now=now: now[0])
    start = await _settle_clear(worker, scn, now, scn.clock_at)
    assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE
    before = await _t01_ids(app_db_url, sid)
    assert all(o != "open" for _i, o in before), before
    opened_at = None
    for s in range(1, 361):
        now[0] = start + datetime.timedelta(seconds=s)
        if s % WOBBLE_EVERY_S == 0:
            _push_spot(scn, CROSS_SPOT if (s // WOBBLE_EVERY_S) % 2 else INSIDE_BAND_SPOT, now[0])
        await worker.cycle()
        if opened_at is None and len(await _t01_ids(app_db_url, sid)) > len(before):
            opened_at = now[0]
    new = (await _t01_ids(app_db_url, sid))[len(before):]
    assert len(new) == 1 and new[0][1] == "open", new  # one record, still open (inside the band: no Lapsed)
    first_cross = start + datetime.timedelta(seconds=WOBBLE_EVERY_S)
    close = first_cross.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    assert close <= opened_at <= close + datetime.timedelta(seconds=10), (first_cross, close, opened_at)
    for s in range(361, 361 + 75):
        now[0] = start + datetime.timedelta(seconds=s)
        if s == 361:  # noqa: PLR2004 - a frame strictly newer than the last one: clears the band, the episode ends at the next close
            _push_spot(scn, BEFORE_CROSS_SPOT, now[0])
        await worker.cycle()
    after = (await _t01_ids(app_db_url, sid))[len(before):]
    assert after == [(new[0][0], "lapsed")] and worker.errors == [], (after, worker.errors)
    print(f"CORE-PROOF crossings=10 records={len(new)} first_cross={first_cross.time()} close={close.time()} "
          f"opened_at={opened_at.time()} record={new[0][0]} lapsed_after_band_cleared=yes")


async def test_crossing_opens_one_record_at_the_confirming_candle_close_not_at_the_crossing(app_db_url, monkeypatch):
    """Was ..._within_one_second (red on base 85dbd6f9): under ADR-237 (3) the record opens at the close of the
    1-minute candle that confirms the crossing, at most one check interval after it, never at the crossing price."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    await _pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    worker = _worker(scn, lambda now=now: now[0])
    start = await _settle_clear(worker, scn, now, scn.clock_at)
    before = await _t01_ids(app_db_url, sid)
    now[0] = start + datetime.timedelta(seconds=5)
    _push_spot(scn, CROSS_SPOT, now[0])
    await worker.cycle()
    assert await _t01_ids(app_db_url, sid) == before  # the crossing itself opens nothing
    close = now[0].replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    while now[0] < close:
        now[0] += ONE_SECOND
        started = time.monotonic()
        await worker.cycle()
    took = time.monotonic() - started
    new = (await _t01_ids(app_db_url, sid))[len(before):]
    assert len(new) == 1 and new[0][1] == "open", new
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE and worker.errors == []
    print(f"CLOSE-PROOF close={close.time()} opened_at={now[0].time()} cycle={took:.3f}s record={new[0][0]}")


async def test_restart_reopens_nothing_writes_no_second_held_and_keeps_rule_memory(app_db_url, monkeypatch):
    """Was test_restart_monitors_within_60s_... (red on base): a restarted worker restores the gate from the stored
    records (ADR-237 (5)), monitors within 60 s, opens no second record and writes no Held row."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    await _pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    first = _worker(scn, lambda: now[0])
    start = await _settle_clear(first, scn, now, scn.clock_at)
    now[0] = start + datetime.timedelta(seconds=5)
    _push_spot(scn, CROSS_SPOT, now[0])
    for _ in range(70):
        now[0] += ONE_SECOND
        await first.cycle()
    before = await _t01_records(app_db_url, sid)
    async with app_db_url.connect() as conn:
        memory = await playbook_store.rule_state(conn, "owner", sid)
    assert len(before) == 1 and memory["T-01"][0] is False  # T-01 false at entry: not held at entry
    total_before = await _t01_total(app_db_url, sid)
    first.stop()  # stopped mid-session
    now[0] += datetime.timedelta(seconds=2)
    second = _worker(scn, lambda: now[0])
    restarted_at = now[0]  # the injected clock: the restart's first check is counted against it, never wall time
    held_before = await _held_total(app_db_url, sid)
    await second.cycle()
    assert [m.strategy_id for m in second.monitors] == [sid] and [c[0] for c in second.checks] == [sid]
    assert second.checks[0][1] - restarted_at <= datetime.timedelta(seconds=REBUILD_LIMIT_S)
    for _ in range(70):  # still beyond the line through the next closes: quiet (not cleared since the record)
        now[0] += ONE_SECOND
        await second.cycle()
    assert second.errors == [] and await _held_total(app_db_url, sid) == held_before
    after = await _t01_records(app_db_url, sid)
    assert [r.id for r in after] == [r.id for r in before]  # the open record is the same one, never re-opened
    async with app_db_url.connect() as conn:
        assert await playbook_store.rule_state(conn, "owner", sid) == memory
    assert await _t01_total(app_db_url, sid) == total_before  # no record of any outcome written by the restart


async def _watched_and_fresh_t03(app_engine, monkeypatch) -> tuple[background.Watched, int]:
    """The seeded strategy as the worker lists it, with every earlier open record lapsed and one T-03 record open."""
    sid, scn = await _seeded(app_engine, monkeypatch)
    w = next(x for x in await background.owner_lister(scn.provider) if x.strategy_id == sid)
    async with app_engine.begin() as conn:
        await playbook_store.lapse_all(conn, "owner", sid, playbook_store.LAPSE_CONDITION_STOPPED)
        rec = await playbook_store.open_suggestion(conn, "owner", sid, "T-03", trigger_id="T-03", stage="Middle",
                                                   value=D("0.36"), threshold=D("0.35"))
    return w, rec.id


async def _t03_rows(engine, sid: int, since: int) -> list[tuple]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, outcome, worse, threshold FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-03' AND id >= :i ORDER BY id"),
                                   {"s": sid, "i": since})).all()
    return [tuple(r) for r in rows]


async def test_an_escalation_of_an_open_record_lapses_it_and_opens_the_worse_one_in_one_transaction(app_db_url,
                                                                                                  monkeypatch):
    """Review #1 of 0036 (REQ-112: one open record per rule): Opened(worse="last") while the rule's record is open ->
    the old one lapsed and the worse one opened, both or neither (a failing insert leaves the old record open)."""
    w, old = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    at = await _db_now(app_db_url)
    worse = alert_gate.Opened("T-03", at, 2, D("0.40"), D("0.41"), "last")

    async def refused(*_a, **_k):
        raise RuntimeError("insert refused")
    with monkeypatch.context() as m:
        m.setattr(playbook_store, "open_suggestion", refused)
        with pytest.raises(RuntimeError, match="insert refused"):
            await background.DbGateStore().apply(w, [worse], None)
    assert await _t03_rows(app_db_url, w.strategy_id, old) == [(old, "open", None, D("0.35"))]  # rolled back
    opened = await background.DbGateStore().apply(w, [worse], None)
    rows = await _t03_rows(app_db_url, w.strategy_id, old)
    assert rows == [(old, "lapsed", None, D("0.35")), (opened["T-03"], "open", "last", D("0.40"))], rows


async def test_a_record_acted_on_mid_session_makes_no_lapse_call_when_the_band_clears(app_db_url, monkeypatch):
    """Review #4 of 0036: the user acted on the record (the gate does not know); the band clears -> the gate's Lapsed
    finds no open record: no lapse call, no OF031 error, the record stays acted on."""
    w, old = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    async with app_db_url.begin() as conn:
        await playbook_store.act_on(conn, "owner", old)
    calls = []
    real = playbook_store.lapse

    async def counted(*a, **k):
        calls.append(a)
        return await real(*a, **k)
    monkeypatch.setattr(playbook_store, "lapse", counted)
    at = await _db_now(app_db_url)
    assert await background.DbGateStore().apply(w, [alert_gate.Lapsed("T-03", at, D("0.20"))], None) == {}
    assert calls == [] and await _t03_rows(app_db_url, w.strategy_id, old) == [(old, "acted_on", None, D("0.35"))]


# ---- GC-ALERT1 step 5: the gate as the REAL Worker drives it (REQ-170 AC-1..AC-4, ADR-236, ADR-237) ---------------
LEVEL_ONE_SPOT = "23440"  # 60 points = 0.256 %: beyond the second rung (0.3 %) of the T-01 ladder (0.5, 0.3)
LEVEL_ONE_NEW_PLAN_SPOT = "23460"  # 40 points = 0.17 %: beyond 0.2 %, the new plan's second rung
NEW_RUNG = "0.2"
QUIET_UNTIL_1150 = D("1150")  # the owner's intraday quiet time: 11:50 (the scenario clock reads 11:40)
CAP_ONE = {"alerts.intraday.daily_cap": D("1")}


async def _ready(app_db_url, monkeypatch, overrides: dict | None = None, lister_for=None):
    """A seeded, intraday-pinned strategy, a real Worker and a clock settled clear (two closes at 23000).
    ``lister_for(scn)`` builds another lister from the seeded scenario (the worker's first rebuild calls it)."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    await _pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    worker = _worker(scn, lambda: now[0], overrides=overrides, lister=None if lister_for is None else lister_for(scn))
    await _settle_clear(worker, scn, now, scn.clock_at)
    assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE
    return sid, scn, now, worker


async def _advance(worker, now, seconds: int, step: int = 1) -> None:
    for _ in range(0, seconds, step):
        now[0] += datetime.timedelta(seconds=step)
        await worker.cycle()


async def _t01_rows(engine, sid: int, since: int) -> list[tuple]:
    """(id, outcome, worse) of the T-01 records newer than ``since``."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, outcome, worse FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-01' AND id > :i ORDER BY id"),
                                   {"s": sid, "i": since})).all()
    return [tuple(r) for r in rows]


async def _last_id(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT coalesce(max(id), 0) FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s"), {"s": sid})).scalar_one()


async def _held_reasons(engine, sid: int) -> list[str]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT reason FROM public.adjustment_held_crossings "
                                        "WHERE strategy_id = :s AND rule_id = 'T-01' ORDER BY held_at, reason"),
                                   {"s": sid})).all()
    return [r[0] for r in rows]


async def _cross(engine, worker, scn, now, spot: str, sid: int, base: int, wait: int = 130) -> int:  # noqa: PLR0913
    """Push ``spot`` and run one-second cycles until a T-01 record newer than ``base`` exists; its id."""
    now[0] += datetime.timedelta(seconds=5)
    _push_spot(scn, spot, now[0])
    for _ in range(wait):
        await worker.cycle()
        rows = await _t01_rows(engine, sid, base)
        if rows:
            return rows[-1][0]
        now[0] += ONE_SECOND
    raise AssertionError(f"no T-01 record within {wait} s of the crossing at {spot}")


async def _open_one(engine, worker, scn, now, sid) -> tuple[int, int]:
    base = await _last_id(engine, sid)
    return base, await _cross(engine, worker, scn, now, CROSS_SPOT, sid, base)


async def _dismiss_and_reload(engine, worker, rec: int) -> None:
    async with engine.begin() as conn:
        await playbook_store.dismiss(conn, "owner", rec)
    await worker.rebuild()  # the rebuild task reads the dismissed row into the gate (ADR-236)


async def test_a_dismissed_record_stays_quiet_at_the_same_level(app_db_url, monkeypatch):
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    base, rec = await _open_one(app_db_url, worker, scn, now, sid)
    await _dismiss_and_reload(app_db_url, worker, rec)
    held = await _held_reasons(app_db_url, sid)
    await _advance(worker, now, 300, step=5)  # five more closes, still beyond the line
    assert await _t01_rows(app_db_url, sid, base) == [(rec, "dismissed", None)]
    assert await _held_reasons(app_db_url, sid) == held and worker.errors == []


async def test_dismiss_then_the_next_ladder_level_opens_a_record_worse_than_dismissed(app_db_url, monkeypatch):
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    base, rec = await _open_one(app_db_url, worker, scn, now, sid)
    await _dismiss_and_reload(app_db_url, worker, rec)
    worse = await _cross(app_db_url, worker, scn, now, LEVEL_ONE_SPOT, sid, rec)
    assert await _t01_rows(app_db_url, sid, base) == [(rec, "dismissed", None), (worse, "open", "dismissed")]
    assert worker.errors == []


async def test_a_plan_change_restores_the_gate_against_the_new_ladder(app_db_url, monkeypatch):
    """The first record opens at the SECOND rung of the old ladder (0.5, 0.3). The plan then moves that rung to 0.2:
    the stored threshold 0.3 is the first rung of the new ladder (0.5, 0.2), so 0.17 % is one level worse -> a
    record worse than the last. With the old level kept (1) it would stay quiet. #638 RCA: the test's lister read
    ``scn`` before ``_ready`` returned it (NameError at the worker's first rebuild, caught into ``worker.errors``); the
    lister is now built from the seeded scenario (``lister_for``). The worker was not at fault."""
    changed = [False]
    new_body: list = []

    def lister_for(scn):
        return lambda: lister(scn)

    async def lister(scn):
        watched = await background.owner_lister(scn.provider)
        if not changed[0]:
            return watched
        if not new_body:
            body = copy.deepcopy(dict(watched[0].body))
            for kind, values in body["triggers"]["T-01"].items():
                if isinstance(values, list):
                    body["triggers"]["T-01"][kind] = [v if v == "" or D(v) >= D("0.5") else NEW_RUNG for v in values]
            new_body.append(body)
        return [dataclasses.replace(w, body=new_body[0]) for w in watched]
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch, lister_for=lister_for)
    base = await _last_id(app_db_url, sid)
    first = await _cross(app_db_url, worker, scn, now, LEVEL_ONE_SPOT, sid, base)
    assert await _t01_rows(app_db_url, sid, base) == [(first, "open", None)]
    changed[0] = True
    await worker.rebuild()
    assert sid not in worker._gate  # dropped: restored at the next check against the new ladder
    second = await _cross(app_db_url, worker, scn, now, LEVEL_ONE_NEW_PLAN_SPOT, sid, first)
    assert await _t01_rows(app_db_url, sid, base) == [(first, "lapsed", None), (second, "open", "last")]
    assert worker._gate_body[sid] == new_body[0] and worker.errors == []


async def test_cap_reached_writes_exactly_one_held_row_for_the_episode(app_db_url, monkeypatch):
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch, overrides=CAP_ONE)
    base, rec = await _open_one(app_db_url, worker, scn, now, sid)  # the day's one record
    held = await _held_reasons(app_db_url, sid)
    now[0] += ONE_SECOND
    _push_spot(scn, LEVEL_ONE_SPOT, now[0])  # one level worse, but the cap is used
    await _advance(worker, now, 300, step=5)
    assert await _held_reasons(app_db_url, sid) == [*held, "daily_limit"]
    assert await _t01_rows(app_db_url, sid, base) == [(rec, "open", None)] and worker.errors == []


async def test_the_ist_day_rollover_resets_the_cap(app_db_url, monkeypatch):
    """The cap holds the worse level today; the next trading day (IST) it opens. #638 RCA: ADJ-02's next trading day
    (Monday 9 Nov) is its expiry day, whose stage carries the stricter T-01 ladder (0.3); the gate kept the record's
    level from the old ladder, so 0.256 % read as the same level and stayed quiet. ADR-237 (8): a stage change
    re-levels the record like a playbook change (pure tests ``test_a_stage_change_re_levels_...`` in
    tests/adjustment/test_alert_gate.py). The cap reset alone, on one ladder, at IST and never UTC midnight:
    ``test_the_cap_resets_at_ist_midnight`` / ``test_the_cap_does_not_reset_at_utc_midnight`` there. Here a cap that
    did not reset holds the worse record on Monday too (no open), so this stays red without the reset."""
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch, overrides=CAP_ONE)
    base, rec = await _open_one(app_db_url, worker, scn, now, sid)
    now[0] += ONE_SECOND
    _push_spot(scn, LEVEL_ONE_SPOT, now[0])
    await _advance(worker, now, 120, step=5)
    assert await _t01_rows(app_db_url, sid, base) == [(rec, "open", None)]  # held today
    held = await _held_reasons(app_db_url, sid)
    now[0] += datetime.timedelta(days=3)  # the next trading day (the scenario day is a Friday), same clock time
    _push_spot(scn, LEVEL_ONE_SPOT, now[0])
    for _ in range(130):
        await worker.cycle()
        now[0] += ONE_SECOND
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE, worker.paused_reason
    rows = await _t01_rows(app_db_url, sid, base)
    assert [(r[1], r[2]) for r in rows] == [("lapsed", None), ("open", "last")], rows  # the cap no longer holds it
    assert await _held_reasons(app_db_url, sid) == held


async def test_quiet_time_holds_once_then_opens_at_the_first_close_after(app_db_url, monkeypatch):
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch,
                                         overrides={"alerts.intraday.quiet_until": QUIET_UNTIL_1150})
    base = await _last_id(app_db_url, sid)
    held = await _held_reasons(app_db_url, sid)
    now[0] += ONE_SECOND
    _push_spot(scn, CROSS_SPOT, now[0])
    opened_at = None
    while now[0] < scn.clock_at.replace(hour=11, minute=52):
        await worker.cycle()
        if opened_at is None and await _t01_rows(app_db_url, sid, base):
            opened_at = now[0]
        now[0] += datetime.timedelta(seconds=2)
    assert await _held_reasons(app_db_url, sid) == [*held, "quiet_time"]  # one row for all the quiet closes
    assert opened_at is not None
    close = scn.clock_at.replace(hour=11, minute=51, second=0)  # 11:50:00 is still quiet: the first close after
    assert close <= opened_at <= close + datetime.timedelta(seconds=12), opened_at
    assert [(r[1], r[2]) for r in await _t01_rows(app_db_url, sid, base)] == [("open", None)]


async def test_each_style_is_checked_at_its_own_interval(app_db_url, monkeypatch):
    """ADR-235 (1): intraday 10 s, weekly 30 s, monthly 120 s; the price changes every second so only the interval
    decides how often the Worker checks. #638 RCA: a check is read from ``_last_check`` (set by every check that ran),
    never from the per-minute ``_recomputes`` count: ``flush_minute`` empties that count at the start of the cycle
    that crosses a minute, so a check ON a minute boundary (weekly 11:41:00, monthly 11:42:00) read as no check and
    the gap came out 60 / 240."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    try:
        for style, every, run_s in (("intraday", 10, 60), ("weekly", 30, 100), ("monthly", 120, 250)):
            async with app_db_url.connect() as conn:
                await strategy_alert_style_store.set_pin(conn, "owner", sid, style)
                await conn.commit()
            now = [scn.clock_at]
            worker = _worker(scn, lambda now=now: now[0])
            at: list[datetime.datetime] = []
            for s in range(run_s):
                now[0] = scn.clock_at + datetime.timedelta(seconds=s)
                _push_spot(scn, "23000" if s % 2 else "23001", now[0])
                before = worker._last_check.get(sid)
                await worker.cycle()
                if worker._last_check.get(sid) != before:
                    at.append(now[0])
            gaps = {int((b - a).total_seconds()) for a, b in itertools.pairwise(at)}
            assert len(at) >= 3 and gaps == {every}, (style, at, gaps)  # noqa: PLR2004
    finally:
        await _pin_intraday(app_db_url, sid)


async def test_after_a_style_change_the_next_check_uses_the_new_interval(app_db_url, monkeypatch):
    """#639 item 3: pinned monthly (120 s) and checked at 0 s; the user pins intraday (10 s) and the rebuild reads it
    at 3 s. The next check comes 10 s after the last one, never the old style's 120 s once."""
    sid, scn = await _seeded(app_db_url, monkeypatch)
    try:
        async with app_db_url.connect() as conn:
            await strategy_alert_style_store.set_pin(conn, "owner", sid, "monthly")
            await conn.commit()
        now = [scn.clock_at]
        worker = _worker(scn, lambda: now[0])
        at: list[datetime.datetime] = []
        for s in range(40):
            now[0] = scn.clock_at + datetime.timedelta(seconds=s)
            if s == 3:  # noqa: PLR2004
                await _pin_intraday(app_db_url, sid)
                await worker.rebuild()  # the rebuild task reads the new pin
            _push_spot(scn, "23000" if s % 2 else "23001", now[0])
            before = worker._last_check.get(sid)
            await worker.cycle()
            if worker._last_check.get(sid) != before:
                at.append(now[0])
        assert worker._style[sid] == "intraday"
        assert [int((t - scn.clock_at).total_seconds()) for t in at] == [0, 10, 20, 30], at
    finally:
        await _pin_intraday(app_db_url, sid)


async def test_a_dismiss_read_by_the_rebuild_never_dismisses_a_record_opened_in_its_read_window(app_db_url,
                                                                                                monkeypatch):
    """#639 item 2, under the one DB gate (#636 r4/r5): the rebuild reads R1 dismissed; a crossing that would open R2
    (one level worse) is started inside the read window. The open WAITS for the gate the read holds, so R2's apply
    runs after the read returned; the dismiss still matches by record id, so R2 stays open and not dismissed.
    The crossing runs as a task, never awaited inside the read (it would wait for the gate the read holds); every
    worker call is bounded so a regression fails instead of hanging."""
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    base, first = await _open_one(app_db_url, worker, scn, now, sid)
    async with app_db_url.begin() as conn:
        await playbook_store.dismiss(conn, "owner", first)
    real_load, real_apply = worker._gate_store.load, worker._gate_store.apply
    order: list[str] = []
    crossing: list[asyncio.Task] = []

    async def load_with_a_crossing_in_its_window(w, today):
        got = await real_load(w, today)  # R1 dismissed, as read
        crossing.append(asyncio.create_task(_cross(app_db_url, worker, scn, now, LEVEL_ONE_SPOT, sid, first)))
        order.append("read_returned")
        return got

    async def marked_apply(*args, **kwargs):
        order.append("apply")
        return await real_apply(*args, **kwargs)
    monkeypatch.setattr(worker._gate_store, "load", load_with_a_crossing_in_its_window)
    monkeypatch.setattr(worker._gate_store, "apply", marked_apply)
    await asyncio.wait_for(worker.rebuild(), 120)
    opened = await asyncio.wait_for(crossing[0], 120)
    assert "apply" in order and order.index("read_returned") < order.index("apply"), order  # the open waited
    # R2 opened after the read, so the gate it was judged against already holds R1 dismissed: worse = 'dismissed'
    # (ADR-237 (5)); 'last' would mean it was judged before the read applied. Either way it is open, never dismissed.
    assert [r for r in (await _t01_rows(app_db_url, sid, base)) if r[0] == opened] == [(opened, "open", "dismissed")]
    assert alert_gate.is_dismissed(worker._gate[sid], "T-01") is False
    monkeypatch.setattr(worker._gate_store, "load", real_load)
    await asyncio.wait_for(worker.rebuild(), 120)  # the next read sees R2 open and not dismissed
    assert alert_gate.is_dismissed(worker._gate[sid], "T-01") is False and worker.errors == []
    async with app_db_url.connect() as conn:
        assert (await conn.execute(text("SELECT outcome FROM public.adjustment_suggestions WHERE id = :i"),
                                   {"i": first})).scalar_one() == "dismissed"  # R1 stays dismissed


async def test_a_close_is_processed_with_no_check_that_wake(app_db_url, monkeypatch):
    """Mutation guard (ADR-237 (2)): the crossing is checked 4 s before the 1-minute close, so the check at the close
    is 'too soon' (10 s interval) and does not run. The record must still open AT the close, from the empty-readings
    close pass; without that pass it opens a check later (6 s on)."""
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    base = await _last_id(app_db_url, sid)
    close = now[0].replace(second=0) + datetime.timedelta(minutes=1)
    now[0] = close - datetime.timedelta(seconds=4)
    _push_spot(scn, CROSS_SPOT, now[0])
    await worker.cycle()  # the crossing's one check
    assert await _t01_rows(app_db_url, sid, base) == []
    opened_at = None
    for _ in range(12):
        now[0] += ONE_SECOND
        await worker.cycle()
        if await _t01_rows(app_db_url, sid, base):
            opened_at = now[0]
            break
    assert opened_at == close, (opened_at, close)
    assert worker.errors == []


async def test_a_candle_that_saw_a_pause_has_no_close_and_the_next_full_candle_opens(app_db_url, monkeypatch):
    """Review round 2, finding 2 (ADR-237 (2)): T-01 crosses at second 20 of the candle (pending), the feed goes stale
    at second 25 (PAUSED, "Monitoring paused") and comes back at second 35 with the crossing still there. The close of
    that candle must open NOTHING (it was not fully watched); the next, fully watched candle opens one record."""
    from ofo.marketdata.provider import DataHealth  # noqa: PLC0415
    sid, scn, now, worker = await _ready(app_db_url, monkeypatch)
    base = await _last_id(app_db_url, sid)
    close = now[0].replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    real_status, stale = scn.provider.status, [False]
    monkeypatch.setattr(scn.provider, "status",
                        lambda: dataclasses.replace(real_status(), health=DataHealth.STALE)
                        if stale[0] else real_status())
    now[0] = close - datetime.timedelta(seconds=40)
    _push_spot(scn, CROSS_SPOT, now[0])
    await worker.cycle()  # the crossing is read: the candle has a pending close beyond the line
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE
    stale[0] = True
    now[0] = close - datetime.timedelta(seconds=35)
    await worker.cycle()
    assert worker.status[sid] is background.MonitoringStatus.PAUSED
    assert worker.paused_reason[sid] is background.PriceState.STALE
    await _advance(worker, now, 9)
    stale[0] = False  # the feed is back inside the same candle, the crossing still there
    await _advance(worker, now, 1)
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE
    while now[0] < close + datetime.timedelta(seconds=2):
        await _advance(worker, now, 1)
    assert await _t01_rows(app_db_url, sid, base) == []  # the paused candle's close opened nothing
    opened_at = None
    for _ in range(70):
        await _advance(worker, now, 1)
        if await _t01_rows(app_db_url, sid, base):
            opened_at = now[0]
            break
    next_close = close + datetime.timedelta(minutes=1)
    assert next_close <= opened_at <= next_close + datetime.timedelta(seconds=10), (opened_at, next_close)
    assert len(await _t01_rows(app_db_url, sid, base)) == 1 and worker.errors == []


async def test_one_exited_strategys_failing_lapse_never_drops_the_others_or_their_gate_read(app_db_url, monkeypatch):
    """Review round 2, finding 4: strategy 987654 has every leg exited and its ``lapse_all`` raises
    SUGGESTION_NOT_OPEN (a record closed meanwhile). Before the fix the error escaped the lister: the old list was kept
    and ``_load_gates`` skipped (at start-up 0 strategies monitored). Now it is contained, counted and logged once."""
    from ofo_app import adjustment_readers, strategy_store  # noqa: PLC0415
    sid, _scn, _now, worker = await _ready(app_db_url, monkeypatch)
    exited = 987654
    real_list, real_read, real_open = (strategy_store.list_strategies, adjustment_readers.read_tracked,
                                       playbook_store.open_suggestions)

    async def listed(conn, user_ref):
        rows = await real_list(conn, user_ref)
        return [dataclasses.replace(rows[0], id=exited), *rows]

    async def read(strategy_id, ctx):
        if strategy_id == exited:
            raise adjustment_readers.TrackedExited("every leg exited")
        return await real_read(strategy_id, ctx)

    async def open_of(conn, user_ref, strategy_id):
        return ["one open record"] if strategy_id == exited else await real_open(conn, user_ref, strategy_id)

    async def refused(*_a, **_k):
        raise strategy_store.StrategyStoreError(playbook_store.SUGGESTION_NOT_OPEN, "suggestion 1 is lapsed")
    monkeypatch.setattr(strategy_store, "list_strategies", listed)
    monkeypatch.setattr(adjustment_readers, "read_tracked", read)
    monkeypatch.setattr(playbook_store, "open_suggestions", open_of)
    monkeypatch.setattr(playbook_store, "lapse_all", refused)
    monkeypatch.setattr(background, "LISTER_LAPSE_FAILURES", {}, raising=False)
    worker.monitors, worker._gate_load = [], {}  # as at start-up: nothing listed, no gate read yet
    for _ in range(2):
        await worker.rebuild()
    assert [w.strategy_id for w in worker.monitors] == [sid]
    assert list(worker._gate_load) == [sid]
    assert {exited: 2} == background.LISTER_LAPSE_FAILURES  # counted each time, logged once


async def test_an_escalation_lapses_the_old_record_as_superseded_by_worse_and_a_cleared_one_as_condition_stopped(
        app_db_url, monkeypatch):
    """Review round 2, finding 5: the record an escalation closes lapsed because a worse one replaced it, not because
    the condition stopped; its own reason, shown through the catalogue (the inbox and opportunities words)."""
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415
    w, old = await _watched_and_fresh_t03(app_db_url, monkeypatch)
    at = await _db_now(app_db_url)
    opened = await background.DbGateStore().apply(w, [alert_gate.Opened("T-03", at, 2, D("0.40"), D("0.41"), "last")],
                                                  None)
    await background.DbGateStore().apply(w, [alert_gate.Lapsed("T-03", at, D("0.20"))], None)
    async with app_db_url.connect() as conn:
        recs = {s.id: s for s in await playbook_store.suggestions(conn, "owner", w.strategy_id)}
    assert (recs[old].outcome, recs[old].lapse_reason) == ("lapsed", "superseded_by_worse")
    assert (recs[opened["T-03"]].outcome, recs[opened["T-03"]].lapse_reason) == ("lapsed", "condition_stopped")
    shown = render_explanation("suggestion_lapsed_" + recs[old].lapse_reason)
    assert str(shown) == "A worse reading of the same rule replaced it"
