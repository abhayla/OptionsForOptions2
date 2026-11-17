"""My Strategies list speed: ``closed_figures_many`` gives the figures of many CLOSED strategies from ONE order read and
ONE contract resolve, and each figure equals the per-strategy answer. Closed strategies are the seeded ADJ scenarios plus
an exit batch placed here (price 10.00 per unit); the expected final P&L is plain arithmetic over the stored orders
(sell adds quantity x price, buy subtracts it), never read back from the code under test.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
from decimal import Decimal

import pytest
from _scenario_catalogue import load_library
from ofo.tracking.orderbook import net_positions
from ofo_app import db as app_db
from ofo_app import paper_book, paper_store, tracked_contracts
from ofo_app.config import get_settings
from ofo_app.routes import adjustment_history as ah_route

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_scenario", ROOT / "scripts" / "seed_scenario.py")
seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_mod)
SCENARIOS = ("ADJ-13", "ADJ-14", "ADJ-15")
EXIT_AT = datetime.datetime(2026, 11, 2, 15, 0, tzinfo=datetime.timezone.utc)
EXIT_PRICE = Decimal("10.00")


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


def _pnl(orders) -> Decimal:
    return sum((o.order.quantity * o.order.price * (1 if o.order.side == "SELL" else -1) for o in orders), Decimal(0))


async def _closed(app_engine, monkeypatch) -> dict[int, Decimal]:
    """Seeds three scenarios, closes each with one exit batch; returns strategy id -> expected final P&L."""
    out: dict[int, Decimal] = {}
    await load_library(app_engine)
    for scenario in SCENARIOS:
        monkeypatch.setenv("OFO_SCENARIO", scenario)
        sid = await seed_mod.seed(scenario)
        async with app_engine.connect() as conn:
            book = await paper_book.load_owned(conn, "owner", sid)
            held = net_positions([o.order.as_paper() for o in book], {}).positions
            exits = [paper_store.NewOrder(int(p.instrument_id), "SELL" if p.net_quantity > 0 else "BUY", abs(p.net_quantity),
                                          EXIT_PRICE, "exit", EXIT_AT) for p in held if p.net_quantity]
            placed = await paper_store.place(conn, "owner", sid, exits) if exits else book  # some seeds are flat
            await conn.commit()
        out[sid] = _pnl(placed)
    return out


async def test_many_equals_per_strategy_values_with_one_order_read_and_one_resolve(app_db_url, monkeypatch):
    expected = await _closed(app_db_url, monkeypatch)
    ids = sorted(expected)
    reads, resolves = [], []
    real_many, real_resolve = paper_book.load_owned_many, tracked_contracts.resolve

    async def spy_many(*a, **k):
        reads.append(a)
        return await real_many(*a, **k)

    async def spy_resolve(*a, **k):
        resolves.append(a)
        return await real_resolve(*a, **k)

    monkeypatch.setattr(paper_book, "load_owned_many", spy_many)
    monkeypatch.setattr(tracked_contracts, "resolve", spy_resolve)
    async with app_db_url.connect() as db:
        got = await ah_route.closed_figures_many(db, "owner", ids, None)
        assert len(reads) == 1 and len(resolves) == 1  # one each, whatever the number of strategies
        one = await ah_route.closed_figures(db, "owner", ids[0], None)
    assert set(got) == set(ids)
    for sid in ids:
        assert Decimal(got[sid]["final_pnl"]) == expected[sid]
        assert got[sid]["adjustments_made"] is not None
        assert got[sid]["completed_reason_text"]  # no rates: the cost is unknown and says why, never 0
    assert one == got[ids[0]]


async def test_another_users_strategy_and_a_strategy_without_orders_get_the_none_figures(app_db_url, monkeypatch):
    expected = await _closed(app_db_url, monkeypatch)
    sid = min(expected)
    async with app_db_url.connect() as db:
        other = await ah_route.closed_figures_many(db, "someone-else", [sid], None)
        missing = await ah_route.closed_figures_many(db, "owner", [sid + 100000], None)
    for res, key in ((other, sid), (missing, sid + 100000)):
        assert res[key]["final_pnl"] is None and res[key]["adjustments_made"] is None
        assert res[key]["completed_reason_text"]


async def test_one_strategy_whose_engine_step_raises_gets_none_and_the_others_keep_their_figures(app_db_url,
                                                                                                monkeypatch):
    expected = await _closed(app_db_url, monkeypatch)
    ids = sorted(expected)
    real = ah_route._per_order_charges
    calls = []

    def boom_on_second(orders, found, underlying, rates):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("engine step failed")
        return real(orders, found, underlying, rates)

    monkeypatch.setattr(ah_route, "_per_order_charges", boom_on_second)
    async with app_db_url.connect() as db:
        got = await ah_route.closed_figures_many(db, "owner", ids, None)
    broken = [i for i in ids if got[i]["final_pnl"] is None]
    assert len(broken) == 1 and got[broken[0]]["completed_reason_text"]
    for sid in ids:
        if sid not in broken:
            assert Decimal(got[sid]["final_pnl"]) == expected[sid]


async def test_a_failed_batched_read_gives_every_row_the_none_figures(app_db_url, monkeypatch):
    expected = await _closed(app_db_url, monkeypatch)

    async def broken(*a, **k):
        raise RuntimeError("read failed")

    monkeypatch.setattr(paper_book, "load_owned_many", broken)
    async with app_db_url.connect() as db:
        got = await ah_route.closed_figures_many(db, "owner", sorted(expected), None)
    assert set(got) == set(expected)
    assert all(v["final_pnl"] is None and v["completed_reason_text"] for v in got.values())
