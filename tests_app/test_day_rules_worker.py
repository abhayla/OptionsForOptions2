"""GC-IC1 step 1a core proof (REQ-159 AC-4, REQ-170, ADR-216): the iron condor's switched-on expiry-day rule
(14:30, close a spread whose short is within 0.3% of spot, action 5) opens ONE record through the alert gate, run by
the REAL background Worker with a pinned clock on a fresh database. Scenarios ADJ-51 (short CE 0.21% from spot, far
short PE below Rs 2) and ADJ-52 (nearest short 0.4% away) are seeded through the app's own stores, as
``test_background_worker.py`` does. Records are counted by SQL against ``public.adjustment_suggestions``."""
from __future__ import annotations

import datetime
import importlib.util
import pathlib

from ofo.adjustment.preferences import from_values
from ofo.errors.explanations import PLAYBOOK_DAY_RULE_ACTION_TEXT
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background, catalogue_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
MAX_DELIST = settings_calc.max_delist_percent(registry_defaults())
RID = "day:expiry:5"
T1429 = datetime.datetime(2026, 11, 3, 14, 29, 0, tzinfo=IST)
T1430 = T1429 + datetime.timedelta(minutes=1)
LAST_SECOND = 59


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


async def _app_db(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    _reset_engine()


async def _seeded(app_engine, monkeypatch, sid_name: str) -> tuple[int, scenario_mode.Scenario]:
    await _app_db(app_engine, monkeypatch)
    monkeypatch.setenv("OFO_SCENARIO", sid_name)
    scn = scenario_mode.load(sid_name)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason=f"test: scenario {sid_name} contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
    sid = await seed_mod.seed(sid_name)
    async with app_engine.connect() as conn:  # 1-minute candles (REQ-170 Q-AD-2), as the worker tests pin
        await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
        await conn.commit()
    return sid, scn


def _push_spot(scn: scenario_mode.Scenario, spot: str, received: datetime.datetime) -> None:
    quote = scn.provider.underlying_quote("NIFTY")
    token = int(quote.instrument_id.split(":")[-1])
    lc = next(x for x in scn.provider.instrument_master() if str(x.contract.exchange_token) == str(token))
    packet = scenario_mode._index_packet(int(lc.broker_refs[0].broker_token), spot, int(received.timestamp()))
    scn.provider.on_frame(scenario_mode._frame([packet]), received)


def _worker(scn: scenario_mode.Scenario, clock) -> background.Worker:
    async def settings():
        return registry_defaults()

    async def preferences(_user_ref):
        return from_values(registry_defaults())

    async def user_values(_user_ref):
        return registry_defaults()
    return background.Worker(provider_for=lambda _owner: scn.provider,
                             lister=lambda: background.owner_lister(scn.provider), clock=clock,
                             settings=settings, preferences=preferences, user_values=user_values)


async def _day_rows(engine, sid: int) -> list[tuple]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT id, outcome, trigger_id, timeline->0->>'approach', timeline->0->>'label', value, threshold "
            "FROM public.adjustment_suggestions WHERE strategy_id = :s AND rule_id = :r ORDER BY id"),
            {"s": sid, "r": RID})).all()
    return [tuple(r) for r in rows]


async def _run(worker, now, scn, spot: str, start: datetime.datetime, seconds: int) -> None:  # noqa: PLR0913
    """One check a second from ``start`` for ``seconds``; a fresh spot frame each second (the feed keeps ticking)."""
    for s in range(seconds):
        now[0] = start + datetime.timedelta(seconds=s)
        _push_spot(scn, spot, now[0])
        await worker.cycle()


async def test_core_expiry_rule_opens_one_record_at_1430_through_the_gate_and_never_at_1429(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-51")
    try:
        now = [T1429]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23400", T1429, LAST_SECOND + 1)  # 14:29:00 .. 14:29:59
        assert worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, worker.errors
        at_1429 = await _day_rows(app_engine, sid)
        assert at_1429 == [], at_1429
        await _run(worker, now, scn, "23400", T1430, 75)  # 14:30:00 .. 14:31:14: the 14:30 candle closes at 14:31
        at_1431 = await _day_rows(app_engine, sid)
        assert len(at_1431) == 1, at_1431
        rec = at_1431[0]
        assert rec[1:5] == ("open", RID, "A-28,A-27", PLAYBOOK_DAY_RULE_ACTION_TEXT["5"]), rec
        await _run(worker, now, scn, "23400", T1430 + datetime.timedelta(seconds=75), 300)  # 5 more closes
        later = await _day_rows(app_engine, sid)
        assert later == at_1431 and worker.errors == [], (later, worker.errors)
        print(f"CORE-PROOF ADJ-51 sid={sid} rows_at_1429={len(at_1429)} rows_after_1431_close={len(at_1431)} "
              f"rows_after_5_more_closes={len(later)} record={rec}")
    finally:
        await app_db.close_db()
        _reset_engine()


async def test_short_04_pct_away_opens_no_record(app_engine, monkeypatch):
    sid, scn = await _seeded(app_engine, monkeypatch, "ADJ-52")
    try:
        now = [T1429]
        worker = _worker(scn, lambda now=now: now[0])
        await _run(worker, now, scn, "23356.55", T1429, 60 + 180)  # 14:29 .. 14:32:59
        rows = await _day_rows(app_engine, sid)
        assert rows == [] and worker.errors == [] and worker.status[sid] is background.MonitoringStatus.ACTIVE, \
            (rows, worker.errors)
        print(f"CORE-PROOF ADJ-52 sid={sid} rows={len(rows)}")
    finally:
        await app_db.close_db()
        _reset_engine()
