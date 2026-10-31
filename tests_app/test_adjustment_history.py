"""GC-ADJ2 step 6: GET /api/strategies/{id}/adjustment-history on a fresh migrated database (REQ-163 AC-1..AC-3, F-74).

Scenario ADJ-13 is seeded the way the adjustment-check test seeds (catalogue store writer, then
``scripts/seed_scenario.py``'s ``seed``; no raw write SQL). Expected figures are the generator's engine-free values in
tests/fixtures/adjust_scenarios/ADJ-13.json (booked 962 = -1176.5 + 2138.5, credit_received 5141.50, expected.pnl_now
-2015, expected.premium_left 7156.50), never read back from the code under test.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.engine.adjust_history import HistoryOrder, adjustment_history
from ofo.timeutil import IST
from ofo_app import catalogue_store, paper_book, scenario_mode
from ofo_app import db as app_db
from ofo_app.config import get_settings

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
DOC = json.loads((ROOT / "tests" / "fixtures" / "adjust_scenarios" / "ADJ-13.json").read_text(encoding="utf-8"),
                 parse_float=Decimal)
POS = DOC["position"]
OK, NOT_FOUND = 200, 404
IC_MAX = 2  # system_playbooks.json iron condor guards.max_adjustments
SEEDED_STEPS_AFTER_ENTRY = 2
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
PAPER = "Paper - not sent to Zerodha"
OWN = "Your own change"


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


async def _seeded(app_engine, monkeypatch, sid: str) -> int:
    monkeypatch.setenv("OFO_SCENARIO", sid)
    scn = scenario_mode.load(sid)
    async with app_engine.begin() as conn:
        await catalogue_store.apply_update(conn, scn.provider.instrument_master(), as_of=CATALOGUE_AS_OF,
                                           force=True, reason=f"test: scenario {sid} contracts", actor="test")
    return await seed_mod.seed(sid)


async def _history(strategy_id: int, overrides: dict | None = None) -> tuple[int, dict]:
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
    app.dependency_overrides.update(overrides or {})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(f"/api/strategies/{strategy_id}/adjustment-history")
    await app_db.close_db()
    return r.status_code, r.json()


async def _stored_orders(app_engine, strategy_id: int) -> list:
    async with app_engine.connect() as conn:
        return list(await paper_book.load_owned(conn, "owner", strategy_id))


async def test_adj13_history_rows_and_totals_equal_the_domain_and_the_generator(app_db_url, monkeypatch):
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    stored = await _stored_orders(app_db_url, sid)
    # the batch rule, measured on the seeded rows: three placed_at values, 2 + 2 + 4 orders
    clock = datetime.datetime.fromisoformat(POS["entry"]["clock"])
    times = [o.order.placed_at for o in stored]
    assert sorted({t - clock for t in times}) == [datetime.timedelta(hours=-2), datetime.timedelta(hours=-1),
                                                  datetime.timedelta(0)]
    assert [sum(1 for t in times if t == u) for u in sorted(set(times))] == [2, 2, 4]
    status, body = await _history(sid)
    assert status == OK, body
    rows, t = body["rows"], body["totals"]
    assert [r["step"] for r in rows] == ["entry", "adjustment", "adjustment"]
    assert [Decimal(r["booked"]) for r in rows] == [Decimal(0), Decimal("962.00"), Decimal(0)]
    assert Decimal(rows[1]["booked"]) == Decimal("-1176.50") + Decimal("2138.50")
    assert [Decimal(r["cash"]) for r in rows] == [Decimal("1202.50"), Decimal("-240.50"), Decimal("4179.50")]
    assert {r["fill_text"] for r in rows} == {PAPER} and {r["why_text"] for r in rows} == {OWN}
    assert all(r["booked_pending"] is None for r in rows)
    assert Decimal(t["booked"]) == sum(Decimal(r["booked"]) for r in rows) == Decimal(POS["booked_pnl"])
    assert Decimal(t["credit"]) == sum(Decimal(r["cash"]) for r in rows) == Decimal(POS["credit_received"])
    # the batch rule above: the seed places the roll's close and re-open 1 h apart
    assert t["adjustments_used"] == SEEDED_STEPS_AFTER_ENTRY
    assert t["adjustments_max"] == IC_MAX and t["max_reason"] is None  # the system iron condor playbook's guard
    if t["open_pnl"] is not None:  # scenario prices live: the generator's figures to the paisa
        assert Decimal(t["pnl"]) == Decimal(DOC["expected"]["pnl_now"])
        assert Decimal(t["premium_left"]) == Decimal(DOC["expected"]["premium_left"])
    else:  # not live: never 0, always a reason
        assert t["pnl"] is None and t["premium_left"] is None and t["prices_reason_text"]
    # the route equals the domain on the same stored orders (charges and prices aside)
    domain = adjustment_history([HistoryOrder(str(o.order.contract_id), o.order.side, o.order.quantity,
                                              o.order.price, o.order.kind, o.order.placed_at) for o in stored],
                                {}, adjustments_max=IC_MAX)
    assert [Decimal(r["booked"]) for r in rows] == [r.booked for r in domain.rows]
    assert Decimal(t["booked"]) == domain.totals.booked and Decimal(t["credit"]) == domain.totals.credit


async def test_another_users_strategy_is_not_found(app_db_url, monkeypatch):
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    status, _ = await _history(sid, {current_user_ref: lambda: "someone-else"})
    assert status == NOT_FOUND
    status, _ = await _history(sid + 1000)
    assert status == NOT_FOUND


async def test_no_market_means_open_figures_null_with_a_reason_and_booked_shown(app_db_url, monkeypatch):
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-13")
    status, body = await _history(sid, {get_market_context: lambda: None})
    assert status == OK, body
    t = body["totals"]
    assert t["open_pnl"] is None and t["pnl"] is None and t["premium_left"] is None
    assert t["prices_reason"] == "prices_not_live" and t["prices_reason_text"]
    assert Decimal(t["booked"]) == Decimal("962.00")
