"""GC-TP step 1b (REQ-109 AC-1, AC-4, AC-5; ADR-207): GET /paper/strategies, GET /paper/strategies/{id} and
POST /paper/strategies/{id}/orders, on the recorded replay market, real PostgreSQL, every test rolled back.

Core proof: strategy 48 of the real fixture tests/fixtures/paper/before-2026-10-29.json (4 legs, one exited) is seeded
as orders - one `open` per leg at its entry price, one `exit` for the exited leg at its exit price - and the reply's
booked / unbooked / total equal the fixture's to the paisa at the fixture's current prices. The fixture's legs sit on
the test catalogue's four condor contracts in leg order (the fixture's own contracts are not in the test catalogue).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import sys
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo_app import paper_store
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _DELIST, _RETIRE, IDS, _frame, _setup

D = Decimal
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests/fixtures/paper/before-2026-10-29.json"
AT = datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC)
MINUS = chr(0x2212)  # the server's minus on money text


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _new(contract: int, side: str, qty: int, price: str, kind: str = "open") -> paper_store.NewOrder:
    return paper_store.NewOrder(contract, side, qty, D(price), kind, AT)


FIXTURE_STRATEGY = 48  # 4 legs, one exited (the real paper strategy of 2026-10-29)


def _strategy_48() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return next(s for s in data["strategies"] if s["strategy_id"] == FIXTURE_STRATEGY)


async def _seed_fixture(db):
    """The fixture's strategy 48 as orders on the app's four contracts, the feed at the fixture's current prices."""
    app, stored, provider, _clock, last = await _setup(db)
    fixture = _strategy_48()
    ids = stored.saved.contract_ids
    orders = [_new(ids[i], leg["action"], leg["quantity"], leg["entry_price"]) for i, leg in enumerate(fixture["legs"])]
    for i, leg in enumerate(fixture["legs"]):
        if leg["exit_price"] is not None:
            orders.append(_new(ids[i], "SELL" if leg["action"] == "BUY" else "BUY", leg["quantity"],
                               leg["exit_price"], "exit"))
    await paper_store.place(db, stored.user_ref, stored.id, orders)
    for iid, leg in zip(IDS, fixture["legs"], strict=True):
        provider.on_frame(_frame(provider, iid, leg["current_price"] or "100"), last)
    return app, stored, provider, _clock, last, fixture


async def _count(db, strategy_id: int) -> int:
    return int((await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                                 {"i": strategy_id})).scalar_one())


# --- the core proof ---------------------------------------------------------------------------------------------------

async def test_core_strategy_48_net_positions_equal_the_fixture_to_the_paisa(db):
    app, stored, *_rest, fixture = await _seed_fixture(db)
    async with _client(app) as c:
        reply = await c.get(f"/paper/strategies/{stored.id}")
    assert reply.status_code == HTTPStatus.OK, reply.text
    body = reply.json()
    shown = (D(body["booked"]), D(body["unbooked"]), D(body["total"]))
    assert shown == (D(fixture["booked"]), D(fixture["unbooked"]), D(fixture["total"]))
    assert shown == (D("-1504.75"), D("10361.00"), D("8856.25"))
    assert (body["state"], body["pause_reason"]) == ("LIVE", None)
    assert (body["booked_text"], body["unbooked_text"], body["total_text"]) == (
        MINUS + "1,504.75", "+10,361.00", "+8,856.25")
    by_contract = {p["contract_id"]: p for p in body["positions"]}
    for i, leg in enumerate(fixture["legs"]):  # each leg's own figure is the fixture's pnl, booked or unbooked
        pos = by_contract[stored.saved.contract_ids[i]]
        figure = pos["booked"] if leg["pnl_kind"] == "booked" else pos["unbooked"]
        assert D(figure) == D(leg["pnl"]), (i, pos)
        sign = 1 if leg["action"] == "BUY" else -1
        assert pos["net_quantity"] == (0 if leg["exit_price"] else leg["quantity"] * sign)
    assert [o["kind"] for o in body["orders"]] == ["open"] * 4 + ["exit"]


def _checker():
    spec = importlib.util.spec_from_file_location("ui_data_check_routes", ROOT / "scripts/checks/ui_data_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


async def test_core_the_independent_checker_recomputes_the_same_figures_from_the_orderbook_rows(db):
    """The checker (imports nothing from the app) rebuilds net, average, booked, unbooked and total from the reply's
    orderbook rows and live prices alone: every figure matches, none is skipped."""
    app, stored, *_ = await _seed_fixture(db)
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    rep = _checker().check_paper_orders(body)
    counts = rep.counts()
    assert counts["mismatch"] == 0 and counts["not checkable"] == 0 and counts["match"] > 30, rep.figures  # noqa: PLR2004
    totals = {f.name: f.independent for f in rep.figures}
    assert (totals["strategy booked"], totals["strategy unbooked"], totals["strategy total"]) == (
        "-1504.75", "10361.00", "8856.25")


# --- answer states ----------------------------------------------------------------------------------------------------

async def test_missing_strategy_and_no_orders_and_another_users_strategy_are_404(db):
    app, stored, *_ = await _setup(db)
    other, *_ = await _setup(db)
    async with _client(app) as c:
        assert (await c.get("/paper/strategies/999999999")).status_code == HTTPStatus.NOT_FOUND
        assert (await c.get(f"/paper/strategies/{stored.id}")).status_code == HTTPStatus.NOT_FOUND  # no orders yet
        post = await c.post("/paper/strategies/999999999/orders", json={"orders": [
            _order(stored.saved.contract_ids[0], "BUY", 65, "10.00")]})
        assert post.status_code == HTTPStatus.NOT_FOUND
    await paper_store.place(db, stored.user_ref, stored.id, [_new(stored.saved.contract_ids[0], "BUY", 65, "10.00")])
    async with _client(other) as c:
        assert (await c.get(f"/paper/strategies/{stored.id}")).status_code == HTTPStatus.NOT_FOUND
        posted = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(stored.saved.contract_ids[0], "BUY", 1, "10.00")]})
        assert posted.status_code == HTTPStatus.NOT_FOUND
        assert (await c.get("/paper/strategies")).json()["strategies"] == []
    assert await _count(db, stored.id) == 1


async def test_stale_prices_drop_unbooked_and_total_but_keep_booked_with_the_reason(db):
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["pause_reason"], body["booked"], body["unbooked"], body["total"]) == (
        "PAUSED", "prices_not_live", "-1504.75", None, None)
    assert (body["unbooked_text"], body["total_text"]) == (None, None)
    open_rows = [p for p in body["positions"] if p["net_quantity"] != 0]
    assert {p["price_state"] for p in open_rows} == {"stale"} and all(p["unbooked"] is None for p in open_rows)


async def test_a_contract_that_is_not_live_pauses_with_its_reason_and_missing_is_never_zero(db):
    app, stored, *_ = await _seed_fixture(db)
    await db.execute(text(_RETIRE), {"id": stored.saved.contract_ids[0]})
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["pause_reason"], body["unbooked"], body["total"]) == (
        "PAUSED", "contract_retired", None, None)
    first = next(p for p in body["positions"] if p["contract_id"] == stored.saved.contract_ids[0])
    assert (first["price_state"], first["ltp"], first["unbooked"]) == ("contract_retired", None, None)


async def test_not_connected_keeps_booked_only(db):
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    app, stored, *_ = await _seed_fixture(db)
    app.dependency_overrides[get_market_context] = lambda: None
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["booked"], body["unbooked"], body["total"]) == ("NOT_CONNECTED", "-1504.75", None, None)


async def test_a_fully_exited_strategy_is_exited_and_needs_no_price(db):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["state"], body["booked"], body["unbooked"], body["total"], body["booked_text"]) == (
        "EXITED", "1300.00", "0.00", "1300.00", "+1,300.00")


# --- the list ---------------------------------------------------------------------------------------------------------

async def test_list_is_newest_first_with_net_per_contract_and_the_three_figures(db):
    app, stored, *_ = await _seed_fixture(db)
    from ofo_app import strategy_store as store  # noqa: PLC0415
    from test_strategy_store import _ids, _saved_in  # noqa: PLC0415

    newer = await store.save_draft(db, stored.user_ref, await _saved_in(db, stored.user_ref, await _ids(db)))
    await paper_store.place(db, stored.user_ref, newer.id, [_new(newer.saved.contract_ids[0], "BUY", 65, "10.00")])
    async with _client(app) as c:
        body = (await c.get("/paper/strategies")).json()
    assert [s["strategy_id"] for s in body["strategies"]] == [newer.id, stored.id]
    older = body["strategies"][1]
    assert (D(older["booked"]), D(older["unbooked"]), D(older["total"])) == (D("-1504.75"), D("10361.00"), D("8856.25"))
    assert len(older["positions"]) == 4 and "orders" not in older  # noqa: PLR2004 - the fixture's four legs


# --- POST -------------------------------------------------------------------------------------------------------------

def _order(contract: int, side: str, qty: int, price: str, kind: str = "open") -> dict:
    return {"contract_id": contract, "side": side, "quantity": qty, "price": price, "kind": kind}


async def test_post_stores_all_orders_in_one_call_and_answers_the_book(db):
    app, stored, *_ = await _setup(db)
    c0, c1 = stored.saved.contract_ids[:2]
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "SELL", 65, "100.00"), _order(c0, "BUY", 65, "80.00", "exit"), _order(c1, "SELL", 65, "60.05")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text
    body = reply.json()
    assert [(o["side"], o["quantity"], o["price"], o["price_text"], o["kind"]) for o in body["orders"]] == [
        ("SELL", 65, "100.00", "100.00", "open"), ("BUY", 65, "80.00", "80.00", "exit"),
        ("SELL", 65, "60.05", "60.05", "open")]
    assert all(o["contract_text"] and o["placed_at"] for o in body["orders"])
    assert D(body["booked"]) == D("1300.00")
    assert await _count(db, stored.id) == 3  # noqa: PLR2004 - three orders sent


@pytest.mark.parametrize("price", ["0", "-5.00", "100.03", "100.123", "99999999", "0.01"])
async def test_a_bad_price_is_422_with_the_reason_and_nothing_is_stored(db, price):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "BUY", 65, "10.00"), _order(c0, "BUY", 65, price)]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "a multiple of 0.05" in reply.text
    assert await _count(db, stored.id) == 0


async def test_a_multiple_of_the_tick_is_accepted(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(stored.saved.contract_ids[0], "BUY", 65, "0.05")]})
    assert reply.status_code == HTTPStatus.CREATED, reply.text


async def test_an_empty_order_list_is_422(db):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": []})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _count(db, stored.id) == 0


@pytest.mark.parametrize("kind", ["settle", "stop", "bogus"])
async def test_settle_and_stop_are_server_only(db, kind):
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(stored.saved.contract_ids[0], "BUY", 65, "10.00", kind)]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await _count(db, stored.id) == 0


@pytest.mark.parametrize(("side", "qty"), [("SELL", 71), ("BUY", 10)], ids=["larger-than-open", "wrong-side"])
async def test_an_exit_larger_than_the_open_quantity_is_422_with_the_reason_and_stores_nothing(db, side, qty):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "BUY", 65, "10.00")])
    async with _client(app) as c:
        reply = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "BUY", 5, "10.00"), _order(c0, side, qty, "11.00", "exit")]})
    assert reply.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, reply.text
    assert "larger than the quantity you have open" in reply.text
    assert await _count(db, stored.id) == 1  # the earlier order of the same call is not stored either


async def test_an_unknown_contract_and_a_new_position_on_a_dead_contract_are_422(db):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    async with _client(app) as c:
        unknown = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(2_000_000_000, "BUY", 65, "10.00")]})
        await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "BUY", 65, "10.00")])
        await db.execute(text(_DELIST), {"id": c0})
        opened = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [_order(c0, "BUY", 5, "10.00")]})
        closed = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
            _order(c0, "SELL", 65, "12.00", "exit")]})
    assert unknown.status_code == opened.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "not a live contract" in unknown.text and "not a live contract" in opened.text
    assert closed.status_code == HTTPStatus.CREATED, closed.text  # an exit only closes what is open


# --- display rule (step 1a) -------------------------------------------------------------------------------------------

async def test_an_uneven_average_is_shown_to_the_paisa_and_the_figures_stay_exact(db):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [
        _new(c0, "BUY", 1, "100.00"), _new(c0, "BUY", 1, "100.00"), _new(c0, "BUY", 1, "100.05")])
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    pos = body["positions"][0]
    assert (pos["net_quantity"], pos["average"], pos["average_text"]) == (3, "100.02", "100.02")  # 300.05 / 3
    ltp = D(pos["ltp"])
    assert D(pos["unbooked"]) == ltp * 3 - D("300.05") and D(pos["total"]) == D(pos["booked"]) + D(pos["unbooked"])


# --- Profit left / Loss left and the original Max Profit / Max Loss (step 3a, REQ-109 AC-9) ---------------------------

def _hand_range(body: dict, entry: str, booked: Decimal) -> tuple[Decimal, Decimal]:
    """Max and min of the reply's open contracts' expiry P&L at 0, every strike and far above (flat tails here)."""
    open_ = [p for p in body["positions"] if p["net_quantity"] != 0]
    strikes = sorted({D(p["strike"]) for p in open_})

    def at(level: Decimal) -> Decimal:
        total = booked
        for p in open_:
            k = D(p["strike"])
            value = max(level - k, D(0)) if p["instrument"] == "CE" else max(k - level, D(0))
            total += (value - D(p[entry])) * p["net_quantity"]
        return total

    values = [at(x) for x in [D(0), *strikes, strikes[-1] + 1000]]
    return max(values), min(values)


async def test_core_strategy_48_extremes_equal_the_hand_figures_with_their_texts(db):
    app, stored, *_ = await _seed_fixture(db)
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    left = _hand_range(body, "ltp", D(0))
    # the original uses the exact average; every average of this book is a single order's price (exact to the paisa)
    original = _hand_range(body, "average", D(body["booked"]))
    assert (D(body["profit_left"]), D(body["loss_left"])) == left
    assert (D(body["max_profit"]), D(body["max_loss"])) == original
    assert body["extremes_reason"] is None
    assert D(body["max_profit"]) == D(body["total"]) + D(body["profit_left"])  # both definitions tie at the extremes
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415

    for name in ("profit_left", "loss_left", "max_profit", "max_loss"):  # the same money template as booked_text
        assert body[f"{name}_text"] == render_explanation("summary_paisa_signed", amount=D(body[name])), name
    assert body["profit_left_text"] == "+14,26,792.25"  # Indian grouping, read from the run of 2026-10-29


async def test_stale_prices_drop_profit_left_and_loss_left_but_keep_the_original(db):
    app, stored, _provider, clock, last, _fixture = await _seed_fixture(db)
    async with _client(app) as c:
        live = (await c.get(f"/paper/strategies/{stored.id}")).json()
        clock.now = last + datetime.timedelta(minutes=10)
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["profit_left"], body["loss_left"], body["profit_left_text"], body["loss_left_text"]) == (
        None, None, None, None)
    assert body["extremes_reason"] == "prices_not_live"
    assert (body["max_profit"], body["max_loss"]) == (live["max_profit"], live["max_loss"])


async def test_a_fully_exited_strategy_has_zero_left_and_booked_as_the_original(db):
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "80.00", "exit")])
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["profit_left"], body["loss_left"], body["max_profit"], body["max_loss"], body["extremes_reason"]) == (
        "0.00", "0.00", "1300.00", "1300.00", None)
    assert (body["max_profit_text"], body["loss_left_text"]) == ("+1,300.00", "0.00")


# --- GC-TP step 4b round 2: lot_size on every position -----------------------------------------------------------------

async def _contract_lot(db, contract_id: int) -> int:
    return int((await db.execute(text("SELECT lot_size FROM public.broker_instruments WHERE contract_id = :i "
                                      "AND broker = 'zerodha'"), {"i": contract_id})).scalar_one())


async def test_positions_carry_the_catalogue_lot_size_open_and_closed_in_both_replies(db):
    app, stored, *_ = await _seed_fixture(db)  # three open NIFTY legs and one closed one
    async with _client(app) as c:
        one = (await c.get(f"/paper/strategies/{stored.id}")).json()
        many = (await c.get("/paper/strategies")).json()["strategies"][0]
    for body in (one, many):
        assert {p["net_quantity"] == 0 for p in body["positions"]} == {True, False}
        for p in body["positions"]:
            assert p["lot_size"] == await _contract_lot(db, p["contract_id"]) == 65  # noqa: PLR2004 - NIFTY


async def test_a_sensex_contract_position_carries_its_own_lot_size_20(db):
    app, stored, *_ = await _setup(db)
    sensex = (await db.execute(text(
        "SELECT c.id FROM public.catalogue_contracts c JOIN public.broker_instruments b ON b.contract_id = c.id "
        "WHERE b.broker = 'zerodha' AND b.lot_size = 20 AND c.name = 'SENSEX' AND NOT c.retired AND NOT c.delisted "
        "AND c.instrument_type IN ('CE', 'PE') LIMIT 1"))).scalar_one_or_none()
    assert sensex is not None, "the test catalogue has no SENSEX option"
    await paper_store.place(db, stored.user_ref, stored.id, [_new(sensex, "BUY", 20, "100.00"),
                                                              _new(sensex, "SELL", 20, "90.00", "exit")])
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert [(p["contract_id"], p["lot_size"]) for p in body["positions"]] == [(sensex, 20)]
