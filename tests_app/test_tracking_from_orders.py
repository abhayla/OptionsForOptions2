"""GC-TP step 1a part 4 (REQ-109 AC-4; ADR-207): GET /tracking and GET /strategies/{id}/tracking read the paper order
book (public.paper_orders through ofo.engine.orderbook.net_positions), and the reply for migrated data is the reply the
old tables gave - same shape, same figures to the paisa.

Spec basis (quoted): REQ-109 AC-4 "The one engine derives the net position per contract from the orders".

Core proof: strategy 48's real rows (tests/fixtures/paper/before-2026-10-29.json, the live GET /tracking reply at 10:55
IST on 2026-10-29: 4 legs of 65, one exited) are seeded into the 0021/0027 tables as the owner, migration 0028's own
data step copies them into paper_orders, and GET /tracking at the fixture's live prices must equal the fixture's money
figures field by field. The test catalogue holds the 2026-10-08 recording's contracts, not the 2026-11-03 ones, so each
leg is seeded on a test contract of the same type (PE / CE); every money field, side, quantity, time and leg order is
the real one. Every test rolls back (the tables are insert-only).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_strategy_store import _app, _client, _user, _with_draft
from test_strategy_tracking import ANSWERED, IDS, THRESHOLD, _frame, _market

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "paper" / "before-2026-10-29.json"
MIGRATION = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0028_paper_orders.py"
STRATEGY = 48
# strategy 48's legs (BUY 22300 PE, SELL 22400 PE, SELL 22600 CE, BUY 22700 CE) on test contracts of the same type:
# IDS = SELL 22800 CE, BUY 23000 CE, SELL 22400 PE, BUY 22200 PE (test_strategy_tracking)
LEG_IDS = [IDS[3], IDS[2], IDS[0], IDS[1]]
MONEY = ("total", "booked", "unbooked", "total_text", "booked_text", "unbooked_text", "state", "pause_reason")
LEG_FIELDS = ("leg_index", "action", "instrument", "quantity", "entry_price", "entry_price_display", "entry_at",
              "price_state", "exit_price", "exit_price_display", "exited_at", "pnl", "pnl_text", "pnl_kind")


def _fixture() -> dict:
    with FIXTURE.open(encoding="utf-8") as stream:
        body = json.load(stream)
    return next(s for s in body["strategies"] if s["strategy_id"] == STRATEGY)


def _copy_sql() -> str:
    found = importlib.util.spec_from_file_location("ofo_test_0028_copy", MIGRATION)
    assert found is not None and found.loader is not None
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module._copy_sql()


def _at(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
async def owner(admin_engine):
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _contract_of(conn, instrument_id: str) -> int:
    from ofo.instruments.models import InstrumentId  # noqa: PLC0415
    from ofo_app.catalogue_store import live_contract_id  # noqa: PLC0415

    segment, token = instrument_id.split(":")
    found = await live_contract_id(conn, InstrumentId(segment, int(token)))
    assert found is not None
    return found


async def _seed_48(conn, user: str) -> int:
    """Strategy 48's legs and exit into the 0021/0027 tables, then 0028's data step (as the owner)."""
    _, stored = await _with_draft(conn, user)
    real = _fixture()
    await conn.execute(text(
        "INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, price_health, prices_at, started_at) "
        "VALUES (:s, :r, 'available', :at, :started)"),
        {"s": stored.id, "r": stored.revision, "at": min(_at(leg["entry_at"]) for leg in real["legs"]),
         "started": _at(real["started_at"])})
    for leg, iid in zip(real["legs"], LEG_IDS, strict=True):
        await conn.execute(text(
            "INSERT INTO public.strategy_tracking_legs (strategy_id, leg_index, contract_id, side, quantity, "
            "entry_price, price_at) VALUES (:s, :i, :c, :side, :q, :p, :at)"),
            {"s": stored.id, "i": leg["leg_index"], "c": await _contract_of(conn, iid), "side": leg["action"],
             "q": leg["quantity"], "p": Decimal(leg["entry_price"]), "at": _at(leg["entry_at"])})
        if leg["exit_price"] is not None:
            await conn.execute(text(
                "INSERT INTO public.strategy_tracking_exits (strategy_id, leg_index, exit_price, price_at, "
                "exited_at) VALUES (:s, :i, :p, :at, :at)"),
                {"s": stored.id, "i": leg["leg_index"], "p": Decimal(leg["exit_price"]), "at": _at(leg["exited_at"])})
    await conn.execute(text(_copy_sql()))
    return stored.id


def _app_on(conn, user: str, prices: dict[str, str] | None = None):
    from ofo_app.routes import tracking as tracking_routes  # noqa: PLC0415
    from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context  # noqa: PLC0415
    from ofo_app.routes.planned_entry import get_live_feed  # noqa: PLC0415

    provider, _, last = _market()
    real = _fixture()
    for leg, iid in zip(real["legs"], LEG_IDS, strict=True):
        if leg["current_price"] is not None:
            provider.on_frame(_frame(provider, iid, (prices or {}).get(iid, leg["current_price"])), last)
    maker = async_sessionmaker(bind=conn, class_=AsyncSession, expire_on_commit=False,
                               join_transaction_mode="create_savepoint")
    app = _app(maker, user)
    context = MarketContext(provider, lambda: last, Decimal("0.065"), None)
    app.dependency_overrides[get_market_context] = lambda: context
    app.dependency_overrides[get_live_feed] = lambda: None
    app.dependency_overrides[get_answer_clock] = lambda: lambda: ANSWERED
    app.dependency_overrides[tracking_routes.get_near_level_threshold] = lambda: THRESHOLD
    return app


def _assert_same_figures(row: dict, real: dict) -> None:
    assert {k: row[k] for k in MONEY} == {k: real[k] for k in MONEY}
    assert len(row["legs"]) == len(real["legs"])
    for got, want in zip(row["legs"], real["legs"], strict=True):
        assert {k: got[k] for k in LEG_FIELDS} == {k: want[k] for k in LEG_FIELDS} | {
            "entry_at": got["entry_at"] if _at(got["entry_at"]) == _at(want["entry_at"]) else want["entry_at"],
            "exited_at": got["exited_at"] if got["exited_at"] is None or want["exited_at"] is None
            or _at(got["exited_at"]) == _at(want["exited_at"]) else want["exited_at"]}


async def test_core_migrated_strategy_48_lists_the_same_figures_to_the_paisa(owner):
    user = _user()
    sid = await _seed_48(owner, user)
    async with _client(_app_on(owner, user)) as c:
        listed = await c.get("/tracking")
        one = await c.get(f"/strategies/{sid}/tracking")
    assert listed.status_code == HTTPStatus.OK, listed.text
    rows = [s for s in listed.json()["strategies"] if s["strategy_id"] == sid]
    assert len(rows) == 1
    _assert_same_figures(rows[0], _fixture())
    assert one.status_code == HTTPStatus.OK, one.text
    body = one.json()
    real = _fixture()
    assert (body["paper_pnl"], body["booked"], body["unbooked"], body["paper_pnl_text"], body["booked_text"],
            body["unbooked_text"]) == (real["total"], real["booked"], real["unbooked"], real["total_text"],
                                       real["booked_text"], real["unbooked_text"])
    assert [(leg["pnl"], leg["pnl_kind"]) for leg in body["legs"]] == [(leg["pnl"], leg["pnl_kind"])
                                                                       for leg in real["legs"]]


async def test_the_reply_comes_from_paper_orders_an_exit_order_there_shows_as_booked(owner):
    """Discriminates the source: an exit order written only to paper_orders (the old tables untouched) shows."""
    user = _user()
    sid = await _seed_48(owner, user)
    first = (await owner.execute(text("SELECT contract_id FROM public.paper_orders WHERE strategy_id = :s "
                                      "ORDER BY id LIMIT 1"), {"s": sid})).scalar_one()
    await owner.execute(text(
        "INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) "
        "VALUES (:s, :c, 'SELL', 65, 21.70, 'exit', :at)"), {"s": sid, "c": first, "at": ANSWERED})
    async with _client(_app_on(owner, user)) as c:
        row = next(s for s in (await c.get("/tracking")).json()["strategies"] if s["strategy_id"] == sid)
    leg = row["legs"][0]
    # (21.70 - 114.25) x 65 = -6,015.75 now booked; booked = -1,504.75 - 6,015.75 = -7,520.50; total unchanged
    assert (leg["price_state"], leg["exit_price"], leg["pnl"], leg["pnl_kind"]) == ("exited", "21.70", "-6015.75",
                                                                                    "booked")
    assert (row["booked"], row["unbooked"], row["total"]) == ("-7520.50", "16376.75", "8856.25")


async def test_a_partly_exited_contract_shows_its_open_quantity_and_books_the_closed_part(owner):
    user = _user()
    sid = await _seed_48(owner, user)
    first = (await owner.execute(text("SELECT contract_id FROM public.paper_orders WHERE strategy_id = :s "
                                      "ORDER BY id LIMIT 1"), {"s": sid})).scalar_one()
    await owner.execute(text(
        "INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) "
        "VALUES (:s, :c, 'SELL', 25, 21.70, 'exit', :at)"), {"s": sid, "c": first, "at": ANSWERED})
    async with _client(_app_on(owner, user)) as c:
        row = next(s for s in (await c.get("/tracking")).json()["strategies"] if s["strategy_id"] == sid)
    leg = row["legs"][0]
    # 25 closed: (21.70 - 114.25) x 25 = -2,313.75 booked; 40 open: (21.70 - 114.25) x 40 = -3,702.00 unbooked
    assert (leg["quantity"], leg["price_state"], leg["entry_price"], leg["pnl"], leg["pnl_kind"]) == (
        40, "live", "114.25", "-3702.00", "unbooked")
    assert (row["booked"], row["total"]) == ("-3818.50", "8856.25")


async def test_a_fractional_average_shows_to_the_paisa_and_figures_stay_exact(owner):
    """Three buys at 100.00, 100.00, 100.05 average 100.01666...: shown 100.02, P&L from the exact average."""
    user = _user()
    _, stored = await _with_draft(owner, user)
    contract = await _contract_of(owner, IDS[1])
    for price in ("100.00", "100.00", "100.05"):
        await owner.execute(text(
            "INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at) "
            "VALUES (:s, :c, 'BUY', 65, :p, 'open', :at)"), {"s": stored.id, "c": contract, "p": Decimal(price),
                                                             "at": ANSWERED})
    async with _client(_app_on(owner, user, {})) as c:
        row = next(s for s in (await c.get("/tracking")).json()["strategies"] if s["strategy_id"] == stored.id)
    leg = row["legs"][0]
    # 195 units, cost 19,503.25; at 258.80: 258.80 x 195 - 19,503.25 = 30,962.75 exactly
    assert (leg["quantity"], leg["entry_price"], leg["entry_price_display"], leg["pnl"]) == (195, "100.02", "100.02",
                                                                                          "30962.75")
    assert (row["total"], row["unbooked"], row["booked"]) == ("30962.75", "30962.75", "0.00")
