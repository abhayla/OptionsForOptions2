"""Stage B1 helpers: walk a path scenario frame by frame with the REAL background worker (scenario feed, shared frame
index, alert gate) on a throwaway database and read back the in-app records per frame.

One seeded paper iron condor per path (``scripts/seed_scenario.py``); the worker runs ``CYCLES_PER_FRAME`` one-second
cycles per frame (past one 1-minute candle close); the records are counted from ``adjustment_suggestions``.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from collections import Counter
from decimal import Decimal as D

from ofo.adjustment.preferences import from_values
from ofo.settings import calc as settings_calc
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background, catalogue_store, scenario_mode, strategy_alert_style_store
from ofo_app import db as app_db
from ofo_app.config import get_settings
from ofo_app.routes.outcome import load_charge_rates
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
MAX_DELIST = settings_calc.max_delist_percent(registry_defaults())
CYCLES_PER_FRAME = 14  # x STEP_S seconds = 70 s: past one 1-minute candle close
STEP_S = 5
OBSERVED: list = []  # per recompute: (hhmm, T-19 cost, cost reason, premium left, entry IV, entry day, today, S-12 %)


def reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


def set_env(app_engine, monkeypatch, path_id: str) -> None:
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", path_id)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    reset_engine()


async def teardown() -> None:
    await app_db.close_db()
    reset_engine()
    scenario_mode._loaded.clear()


class Draining(background.Worker):
    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


def last_frame(path_id: str) -> int:
    return len(list(scenario_mode.frame_path(path_id, 0).parent.glob("frame-*.json"))) - 1


def frame_doc(path_id: str, k: int) -> dict:
    return json.loads(scenario_mode.frame_path(path_id, k).read_text(encoding="utf-8"), parse_float=D)


async def rows(sql: str, **params) -> list:
    async with app_db.get_engine().connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


async def seed_path(app_engine, path_id: str, style: str = "intraday") -> int:
    scn = scenario_mode.load(path_id)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason=f"test: path scenario {path_id} contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
    await app_engine.dispose()
    sid = await seed_mod.seed(path_id)
    reset_engine()
    async with app_db.get_engine().connect() as conn:
        await strategy_alert_style_store.set_pin(conn, "owner", sid, style)
        await conn.commit()
    return sid


async def walk(app_engine, path_id: str, frames: list[int] | None = None, *, stale_by: int = 0,  # noqa: PLR0913
               sid: int | None = None, style: str = "intraday") -> tuple[int, dict[int, Counter], list]:
    """Walks ``frames`` (default all) with the real worker; returns (strategy id, {frame: Counter(rule_id) of ALL
    records of the strategy after that frame}, worker errors). ``stale_by`` seconds: the worker clock runs that far
    past the frame's own clock (the prices are then that old: T-21)."""
    scn = scenario_mode.load(path_id)
    if sid is None:
        sid = await seed_path(app_engine, path_id, style)
    last = last_frame(path_id)
    now = [scn.clock_at]

    def settings(_at):
        return registry_defaults()

    async def preferences(_u):
        return from_values(registry_defaults())

    async def user_values(_u):
        return registry_defaults()
    provider, before_cycle = background.scenario_worker_parts(scn, app_db.get_sessionmaker())
    worker = Draining(provider_for=lambda _o: provider,
                      lister=lambda: background.owner_lister(provider, rates_of=load_charge_rates),
                      clock=lambda: now[0], settings=settings, preferences=preferences, user_values=user_values,
                      before_cycle=before_cycle, observe=lambda _w, st: OBSERVED.append(
                          (st.hhmm, st.adjustment_cost, st.adjustment_cost_reason, st.premium_left, st.entry_atm_iv,
                           st.entry_day, st.today, st.s12_percent)))
    seen: dict[int, Counter] = {}
    for k in (frames if frames is not None else range(last + 1)):
        async with app_db.get_engine().begin() as conn:
            await scenario_mode.write_frame(conn, path_id, k)
        start = datetime.datetime.fromisoformat(frame_doc(path_id, k)["clock"]["ist"])
        for s in range(CYCLES_PER_FRAME):
            now[0] = start + datetime.timedelta(seconds=s * STEP_S + stale_by)
            await worker.cycle()
        found = await rows("SELECT rule_id FROM public.adjustment_suggestions WHERE strategy_id = :s", s=sid)
        seen[k] = Counter(r[0] for r in found)
    return sid, seen, worker.errors
