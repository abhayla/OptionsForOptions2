"""GC-MU step 4 core (REQ-165 AC-1, AC-5; REQ-115 AC-3): the background role checks a tracked strategy with NO client
connected. Scenario ADJ-02 is seeded through the app's own stores (as ``test_adjustment_check.py``) and its fed
``KiteProvider`` (the real frame parser) is the worker's provider. A frame with spot 23000 (T-01 false) is checked
first; then the frame with the scenario's spot 23420 crosses T-01. Exactly one opportunity record is opened for T-01,
its found-time (the record's own first timeline time, the database clock) within 1 s of the moment the crossing
price reached the provider (read from the same database clock). A restarted worker monitors the same strategy within
60 s, re-opens nothing and keeps the rule memory.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
import time

import pytest
from ofo.adjustment.preferences import from_values
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background, catalogue_store, playbook_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
MAX_DELIST = settings_calc.max_delist_percent(registry_defaults())  # the registry default, passed explicitly
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


async def _seeded(app_engine, monkeypatch) -> tuple[int, scenario_mode.Scenario]:
    monkeypatch.setenv("OFO_SCENARIO", "ADJ-02")
    scn = scenario_mode.load("ADJ-02")
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason="test: scenario ADJ-02 contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
    return await seed_mod.seed("ADJ-02"), scn


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


def _worker(scn: scenario_mode.Scenario, clock) -> background.Worker:
    async def settings():
        return registry_defaults()  # the settings in force: the registry defaults, passed explicitly

    async def preferences(_user_ref):
        return from_values(registry_defaults())  # the owner's preferences: the registry defaults (REQ-168 AC-1)

    async def user_values(_user_ref):
        return registry_defaults()  # the owner's alert values in force: the admin defaults (REQ-170 AC-6)
    return background.Worker(provider_for=lambda _owner: scn.provider,
                             lister=lambda: background.owner_lister(scn.provider), clock=clock, settings=settings,
                             preferences=preferences, user_values=user_values)


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
    """Spot 23000 (T-01 1.3 %, clear by the band) until two 1-minute closes pass: any record a previous test of
    this file left open lapses and the rule is armed (the seed reuses one strategy per scenario)."""
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
    worker = _worker(scn, lambda: now[0])
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
    worker = _worker(scn, lambda: now[0])
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
    total_before = await _t01_total(app_db_url, sid)  # the seed reuses one strategy per scenario: history counts
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
