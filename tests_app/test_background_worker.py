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
from ofo.timeutil import IST
from ofo_app import background, catalogue_store, playbook_store, scenario_mode
from ofo_app import db as app_db
from ofo_app.config import get_settings
from ofo_app.live_market import LIVE_RATE
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
BEFORE_CROSS_SPOT = "23000"  # 2.1 % below the 23500 CE short and 1.3 % above the 22700 PE short: T-01 (0.5 %) false
ONE_SECOND = datetime.timedelta(seconds=1)
REBUILD_LIMIT_S = 60


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
                                           reason="test: scenario ADJ-02 contracts", actor="test")
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
    return background.Worker(provider_for=lambda _owner: scn.provider,
                             lister=lambda: background.owner_lister(scn.provider), clock=clock, rate=LIVE_RATE)


async def test_core_adj02_crossing_t01_opens_one_record_within_one_second_with_no_client(app_db_url, monkeypatch):
    sid, scn = await _seeded(app_db_url, monkeypatch)
    now = [scn.clock_at]
    worker = _worker(scn, lambda: now[0])
    _push_spot(scn, BEFORE_CROSS_SPOT, scn.clock_at)
    await worker.cycle()
    assert [m.strategy_id for m in worker.monitors] == [sid] and worker.errors == []
    assert [c[0] for c in worker.checks] == [sid] and await _t01_records(app_db_url, sid) == []
    now[0] = scn.clock_at + datetime.timedelta(seconds=5)  # 11:40:05: the price that crosses T-01
    price_at = await _db_now(app_db_url)
    _push_spot(scn, scn.data["market"]["spot"], now[0])
    started = time.monotonic()
    await worker.cycle()
    took = time.monotonic() - started
    records = await _t01_records(app_db_url, sid)
    assert len(records) == 1, records
    found_at = datetime.datetime.fromisoformat(records[0].timeline[0]["at"])
    assert datetime.timedelta(0) <= found_at - price_at <= ONE_SECOND, (price_at, found_at, took)
    assert worker.status[sid] is background.MonitoringStatus.ACTIVE and worker.errors == []
    print(f"CORE-PROOF price_at={price_at.isoformat()} found_at={found_at.isoformat()} "
          f"gap={(found_at - price_at).total_seconds():.3f}s cycle={took:.3f}s record={records[0].id}")


async def test_restart_monitors_within_60s_reopens_nothing_and_keeps_rule_memory(app_db_url, monkeypatch):
    sid, scn = await _seeded(app_db_url, monkeypatch)
    now = [scn.clock_at]
    first = _worker(scn, lambda: now[0])
    _push_spot(scn, BEFORE_CROSS_SPOT, scn.clock_at)
    await first.cycle()
    now[0] = scn.clock_at + datetime.timedelta(seconds=5)
    _push_spot(scn, scn.data["market"]["spot"], now[0])
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
    await second.cycle()
    assert [m.strategy_id for m in second.monitors] == [sid] and [c[0] for c in second.checks] == [sid]
    assert second.checks[0][1] - restarted_at <= datetime.timedelta(seconds=REBUILD_LIMIT_S)
    after = await _t01_records(app_db_url, sid)
    assert [r.id for r in after] == [r.id for r in before]  # the open record is the same one, never re-opened
    async with app_db_url.connect() as conn:
        assert await playbook_store.rule_state(conn, "owner", sid) == memory
    assert await _t01_total(app_db_url, sid) == total_before  # no record of any outcome written by the restart
