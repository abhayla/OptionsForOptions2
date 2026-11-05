"""IC e2e paper contract, Stage A CORE proof (design decisions 1-7).

One scenario-marked paper iron condor (path scenario PATH-01, built from ADJ-02, 10 frames) on a throwaway database:
paper entry at frame 0 -> the shared frame index moves frame by frame -> the REAL background worker (no screen open,
the scenario's own fed provider, the frame read before every cycle) writes 0 T-01 records up to frame 5 and exactly 1
at frame 6 -> A-01 is prepared at frame 6 through the app's own approaches route -> its paper orders are placed through
the app (scenario mode, own scenario: allowed) at frame 6 mids, linked to the record (legs changed) -> paper exit of
every open leg -> the stored fills' signed total equals the history's booked P&L. Everything counted from the database.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal as D

from httpx import ASGITransport, AsyncClient
from ofo.adjustment.preferences import from_values
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
PATH_ID = "PATH-01"
CROSS_FRAME = 6
CYCLES_PER_FRAME = 75  # past one 1-minute candle close (intraday style) at one-second cycles
OK, CREATED = 200, 201


def _reset_engine() -> None:
    app_db.get_sessionmaker.cache_clear()
    app_db.get_engine.cache_clear()
    get_settings.cache_clear()


async def _db_url(app_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", app_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_SCENARIO", PATH_ID)
    _reset_engine()


class _Draining(background.Worker):
    async def cycle(self) -> None:
        await super().cycle()
        await self.drain_writes()


def frame_doc(k: int) -> dict:
    return json.loads(scenario_mode.frame_path(PATH_ID, k).read_text(encoding="utf-8"), parse_float=D)


def mid_of(k: int, symbol: str) -> D:
    """The frame's mid of a contract: (bid + ask) / 2 snapped to the 0.05 tick (the prepared basket's pre-fill)."""
    row = next(r for c in frame_doc(k)["market"]["chains"] for r in c["rows"] if r["tradingsymbol"] == symbol)
    mid = (D(str(row["bid"])) + D(str(row["ask"]))) / 2
    return (mid / D("0.05")).quantize(D(1)) * D("0.05")


async def _rows(engine, sql: str, **params) -> list:
    async with engine.connect() as conn:
        return list((await conn.execute(text(sql), params)).all())


async def _move(engine, k: int) -> None:
    async with engine.begin() as conn:
        await scenario_mode.write_frame(conn, PATH_ID, k)


async def test_core_path_frames_raise_one_record_adjusted_exited_and_totalled_on_paper(app_engine, monkeypatch):
    await _db_url(app_engine, monkeypatch)
    try:
        await _core(app_engine)
    finally:
        await app_db.close_db()
        _reset_engine()
        scenario_mode._loaded.clear()


async def _core(app_engine) -> None:  # noqa: PLR0915 - one readable walk of the proof
    scn = scenario_mode.load(PATH_ID)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF, force=True,
                                           reason="test: path scenario PATH-01 contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
    sid = await seed_mod.seed(PATH_ID)  # paper entry at frame 0 (the base position's entry fills)
    _reset_engine()
    marker = await _rows(app_engine, "SELECT scenario_id FROM public.strategies WHERE id = :s", s=sid)
    assert marker == [(PATH_ID,)]  # the seed's marker
    async with app_engine.connect() as conn:
        await strategy_alert_style_store.set_pin(conn, "owner", sid, "intraday")
        await conn.commit()
    now = [scn.clock_at]

    def settings(_at):
        return registry_defaults()

    async def preferences(_u):
        return from_values(registry_defaults())

    async def user_values(_u):
        return registry_defaults()
    provider, before_cycle = background.scenario_worker_parts(scn, app_db.get_sessionmaker())  # the process wiring
    assert provider is scn.provider  # the scenario feed: no KiteProvider built for the worker
    worker = _Draining(provider_for=lambda _o: provider, lister=lambda: background.owner_lister(provider),
                       clock=lambda: now[0], settings=settings, preferences=preferences, user_values=user_values,
                       before_cycle=before_cycle)
    t01_at: dict[int, int] = {}
    for k in range(CROSS_FRAME + 1):
        await _move(app_engine, k)
        start = datetime.datetime.fromisoformat(frame_doc(k)["clock"]["ist"])
        for s in range(CYCLES_PER_FRAME):
            now[0] = start + datetime.timedelta(seconds=s)
            await worker.cycle()
        assert scn.frame == k and str(scn.provider.underlying_quote("NIFTY").ltp) == str(frame_doc(k)["market"]["spot"])
        t01_at[k] = len(await _rows(app_engine, "SELECT id FROM public.adjustment_suggestions "
                                                "WHERE strategy_id = :s AND rule_id = 'T-01'", s=sid))
    assert worker.errors == [], worker.errors
    assert t01_at[CROSS_FRAME - 1] == 0 and t01_at[CROSS_FRAME] == 1, t01_at
    record = (await _rows(app_engine, "SELECT id, outcome FROM public.adjustment_suggestions "
                                      "WHERE strategy_id = :s AND rule_id = 'T-01'", s=sid))[0]
    assert record[1] == "open"
    all_records = await _rows(app_engine, "SELECT rule_id FROM public.adjustment_suggestions WHERE strategy_id = :s",
                              s=sid)

    from ofo_app.main import create_app  # noqa: PLC0415 - after the environment above
    scenario_mode._loaded.clear()
    _reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        check = await ac.get(f"/api/strategies/{sid}/adjustment-check")  # moves the API's scenario to frame 6
        assert check.status_code == OK, check.text
        assert scenario_mode.current().frame == CROSS_FRAME
        r = await ac.post(f"/api/strategies/{sid}/adjustment-approaches", json={})
        assert r.status_code == OK, r.text
        a01 = next(a for a in r.json()["approaches"] if a["id"] == "A-01")
        trades = a01["trades"]
        assert trades, a01
        acted = await ac.post(f"/api/adjustment-opportunities/{record[0]}/acted-on", json={})
        assert acted.status_code == OK, acted.text
        before = await _rows(app_engine, "SELECT count(*) FROM public.paper_orders WHERE strategy_id = :s", s=sid)
        orders = [{"contract_id": t["contract_id"], "side": t["side"], "quantity": t["quantity"],
                   "price": str(mid_of(CROSS_FRAME, t["tradingsymbol"])), "kind": t["kind"]} for t in trades]
        placed = await ac.post(f"/paper/strategies/{sid}/orders", json={"orders": orders,
                                                                        "suggestion_ids": [record[0]]})
        assert placed.status_code == CREATED, placed.text
        stored = await _rows(app_engine, "SELECT o.id, o.price, o.contract_id FROM public.paper_orders o "
                                         "WHERE o.strategy_id = :s ORDER BY o.id", s=sid)
        new = stored[before[0][0]:]
        assert [str(p) for _i, p, _c in new] == [o["price"] for o in orders]  # fill = frame 6 mid (REQ-109 AC-1)
        linked = await _rows(app_engine, "SELECT order_id FROM public.adjustment_suggestion_orders "
                                         "WHERE suggestion_id = :r ORDER BY order_id", r=record[0])
        assert [x[0] for x in linked] == [i for i, _p, _c in new]
        exit_r = await ac.post(f"/strategies/{sid}/tracking/exit", json={})
        assert exit_r.status_code == OK, exit_r.text
        history = await ac.get(f"/api/strategies/{sid}/adjustment-history")
        assert history.status_code == OK, history.text
    fills = await _rows(app_engine, "SELECT side, quantity, price FROM public.paper_orders WHERE strategy_id = :s",
                        s=sid)
    cash = sum((D(q) * D(p) * (1 if side == "SELL" else -1) for side, q, p in fills), D(0))
    open_net = await _rows(app_engine, "SELECT sum(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) "
                                       "FROM public.paper_orders WHERE strategy_id = :s GROUP BY contract_id", s=sid)
    assert all(n[0] == 0 for n in open_net)  # every leg exited
    totals = history.json()["totals"]
    assert D(totals["booked_pnl"]) == cash, (totals, cash)
    print(f"CORE-PROOF strategy={sid} marker={PATH_ID} t01_by_frame={t01_at} records_all={len(all_records)} "
          f"rules={sorted(r[0] for r in all_records)} a01_orders={len(new)} fills={len(fills)} booked={cash}")
