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
from ofo.charges import ChargeRates
from ofo.charges.round_trip import round_trip_charges
from ofo.engine.legs import Action, Instrument, Leg
from ofo_app import paper_store
from ofo_app.routes.outcome import load_charge_rates
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _DELIST, _RETIRE, IDS, _frame, _setup

D = Decimal
#: The Kite-reproduced rate set (tests/charges/test_rates_reproduce_kite.py, read 2026-10-15), as test_paper_totals.
RATES = ChargeRates(brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
                    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
                    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
                    source_url="https://zerodha.com/charges (F&O options)")
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
    # the hand figures of these tests are before charges; the charges-inclusive figures have their own test below
    app.dependency_overrides[load_charge_rates] = lambda: None
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
        ("SELL", 65, "100.00", "100.00", "open"), ("BUY", 65, "39.15", "39.15", "exit"),
        ("SELL", 65, "60.05", "60.05", "open")]
    assert all(o["contract_text"] and o["placed_at"] for o in body["orders"])
    assert D(body["booked"]) == D("3955.25")
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
    # GC-ICGUIDE g32 (Tier B finding 1): an exit is priced by the server from the contract's live feed key only; a dead
    # contract has none, so the exit is refused by name and nothing is stored (an expired leg is closed by expiry
    # settlement instead; a NIFTY option delisted before expiry stays open - accepted edge, issue #685).
    assert closed.status_code == HTTPStatus.CONFLICT, closed.text
    assert "no longer a live contract" in closed.text
    assert await _count(db, stored.id) == 1  # only the earlier open order


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


async def test_f94_max_profit_and_loss_include_the_charges_paid_and_the_cost_to_close_and_say_so(db):
    app, stored, *_ = await _seed_fixture(db)
    async with _client(app) as c:
        gross = (await c.get(f"/paper/strategies/{stored.id}")).json()
        app.dependency_overrides[load_charge_rates] = lambda: RATES
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
        listed = next(s for s in (await c.get("/paper/strategies")).json()["strategies"]
                      if s["strategy_id"] == stored.id)
    legs = [Leg(Action.BUY if p["net_quantity"] > 0 else Action.SELL, Instrument(p["instrument"]), D(p["strike"]),
                datetime.date.fromisoformat(p["expiry"]), abs(p["net_quantity"]), D(p["average"]))
            for p in gross["positions"] if p["net_quantity"] != 0]
    charges = round_trip_charges(legs, stored.saved.definition.underlying, RATES)
    assert charges == D("201.79")  # the three open legs' round trip (201.786262)
    # ADR-263: charges really PAID on every order + the estimate to close what is open. The one closed leg has two real
    # orders: SELL 65 @ 166.90 = 44.433828 and BUY 65 @ 190.05 = 29.164324 -> 73.598152; 201.786262 + 73.598152 =
    # 275.384414, shown 275.39 (rounded up once). Old expectation: before - 201.79.
    charges = D("275.39")
    assert D(body["max_profit"]) == D(gross["max_profit"]) - charges
    assert D(body["max_loss"]) == D(gross["max_loss"]) - charges
    assert (body["profit_left"], body["loss_left"]) == (gross["profit_left"], gross["loss_left"])
    assert D(body["extremes_charges"]) == charges
    assert "include about" in body["extremes_charges_text"] and "charges and taxes" in body["extremes_charges_text"]
    assert gross["extremes_charges"] is None and "before charges" in gross["extremes_charges_text"]
    assert {f: listed[f] for f in ("max_profit", "max_loss", "extremes_charges")} == {
        f: body[f] for f in ("max_profit", "max_loss", "extremes_charges")}  # the list equals the single route


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


# --- GC-ICFIX u122/u123: the total after charges (ADR-263), one engine function --------------------------------------

async def _closed_141_like(db):
    """SELL 65 @ 100.00 then BUY 65 @ 100.50: booked (100.00 - 100.50) x 65 = -32.50, the size of strategy 141's result.
    Hand charges (RATES): SELL premium 6,500 -> 20 + STT 9.75 + 2.30945 + 0.0065 + GST 4.016871 = 36.082821; BUY premium
    6,532.50 -> 20 + 2.32099725 + 0.0065325 + stamp 0.195975 + GST 4.018955355 = 26.542460105; sum 62.625281105 shown
    rounded up 62.63. After = -32.50 - 62.63 - 0 = -95.13."""
    app, stored, *_ = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00"),
                                                              _new(c0, "BUY", 65, "100.50", "exit")])
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    return app, stored


async def test_core_a_closed_book_sends_the_total_after_charges_beside_the_old_before_figure(db):
    app, stored = await _closed_141_like(db)
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
        listed = (await c.get("/paper/strategies")).json()
    assert D(body["total"]) == D("-32.50")  # the old field keeps its meaning (before charges)
    assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
        D("-95.13"), D("62.63"), D("0"))
    assert (body["total_after_text"], body["after_charges_reason"]) == (MINUS + "95.13", None)
    row = next(s for s in listed["strategies"] if s["strategy_id"] == stored.id)
    assert {f: row[f] for f in ("total_after", "charges_paid", "charges_to_close")} == {
        f: body[f] for f in ("total_after", "charges_paid", "charges_to_close")}  # the list equals the single route
    assert D(listed["totals"]["total_after"]) == D("-95.13")
    assert D(listed["totals"]["charges_to_close"]) == D("0")  # the list total of what it costs to close


async def test_tracking_and_history_replies_carry_the_same_after_figure_from_the_same_function(db):
    app, stored = await _closed_141_like(db)  # hand: -32.50 - 62.63 - 0 = -95.13 (see _closed_141_like)
    async with _client(app) as c:
        tracked = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        listed = next(s for s in (await c.get("/tracking")).json()["strategies"] if s["strategy_id"] == stored.id)
        history = (await c.get(f"/api/strategies/{stored.id}/adjustment-history")).json()["totals"]
    assert D(tracked["paper_pnl"]) == D("-32.50")  # before charges: unchanged field
    for body in (tracked, listed, history):
        assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
            D("-95.13"), D("62.63"), D("0")), body
        assert body["total_after_text"] == MINUS + "95.13" and body["after_charges_reason"] is None


async def test_tracking_without_rates_keeps_the_before_figure_and_says_why_there_is_no_after_figure(db):
    app, stored = await _closed_141_like(db)
    app.dependency_overrides[load_charge_rates] = lambda: None
    async with _client(app) as c:
        tracked = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    assert D(tracked["paper_pnl"]) == D("-32.50")
    assert (tracked["total_after"], tracked["after_charges_reason"]) == (None, "rates_unavailable")


async def _open_book(db, orders: list[tuple[str, int, str, str]], live: str):
    app, stored, provider, _clock, last = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, side, qty, price, kind)
                                                              for side, qty, price, kind in orders])
    provider.on_frame(_frame(provider, IDS[0], live), last)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    async with _client(app) as c:
        return (await c.get(f"/paper/strategies/{stored.id}")).json()


async def test_an_open_long_leg_exits_with_a_sell_and_carries_its_stt(db):
    # BUY 65 @ 100 now 120: +1,300.00; paid 26.53 and exit SELL 65 @ 120 = 38.58 (sums in the engine test); 1,234.89.
    body = await _open_book(db, [("BUY", 65, "100.00", "open")], "120.00")
    assert D(body["total"]) == D("1300.00")
    assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
        D("1234.89"), D("26.53"), D("38.58"))


async def test_a_partly_closed_book_prices_the_exit_on_the_open_quantity_only(db):
    # SELL 130 @ 100, BUY 65 @ 90 exit, now 80: booked 650 + unbooked 1,300 = 1,950.00; paid 74.81; exit 25.95;
    # after 1,849.24.
    body = await _open_book(db, [("SELL", 130, "100.00", "open"), ("BUY", 65, "90.00", "exit")], "80.00")
    assert D(body["total"]) == D("1950.00")
    assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
        D("1849.24"), D("74.81"), D("25.95"))


async def test_an_open_book_at_live_prices_is_after_charges_paid_and_estimated_exit(db):
    # SELL 65 @ 100 now 80: +1,300.00 before; paid 36.09; exit BUY 65 @ 80 = 25.95 (sums in the engine test); 1,237.96.
    app, stored, provider, _clock, last = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00")])
    provider.on_frame(_frame(provider, IDS[0], "80.00"), last)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert D(body["total"]) == D("1300.00")
    assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
        D("1237.96"), D("36.09"), D("25.95"))
    assert body["after_charges_reason"] is None


async def test_f7_charges_paid_text_is_sent_wherever_charges_paid_is_and_the_list_totals_carry_both(db):
    # Same book as above: paid 36.09. The text is the money text form of the sibling charges_to_close_text.
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open")], "80.00")
    for reply in (body, row, totals):
        assert D(reply["charges_paid"]) == D("36.09")
        assert "36.09" in reply["charges_paid_text"]
        assert "25.95" in reply["charges_to_close_text"] and "36.09" not in reply["charges_to_close_text"]
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open")], "80.00", rates=None)
    for reply in (body, row, totals):  # rates unknown: nothing paid can be given, no text either
        assert (reply["charges_paid"], reply["charges_paid_text"]) == (None, None)


async def test_unknown_charge_rates_send_no_after_figure_with_the_reason_and_keep_the_before_figure(db):
    app, stored = await _closed_141_like(db)
    app.dependency_overrides[load_charge_rates] = lambda: None
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert D(body["total"]) == D("-32.50")
    assert (body["total_after"], body["total_after_text"], body["charges_paid"]) == (None, None, None)
    assert body["after_charges_reason"] == "rates_unavailable" and body["after_charges_reason_text"]


async def test_prices_not_live_send_no_after_figure_and_the_reason(db):
    app, stored, provider, clock, last = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, "SELL", 65, "100.00")])
    provider.on_frame(_frame(provider, IDS[0], "80.00"), last)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    clock.now = last + datetime.timedelta(minutes=10)  # REQ-109 AC-5: stale -> paused
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
    assert (body["total"], body["total_after"], body["charges_to_close"]) == (None, None, None)
    assert body["after_charges_reason"] == "prices_not_live"
    assert D(body["charges_paid"]) == D("36.09")  # what was paid is still known and still sent


# --- GC-TP step 4b round 2: lot_size on every position ------------------------------------------------------------

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


# --- GC-ICFIX u123/u124 (ADR-301, ADR-302, ADR-303): Booked / Unbooked / Profit left / Loss left after charges --------
SPLIT_KEYS = ("booked_after", "unbooked_after", "profit_left_after", "loss_left_after", "recover")


async def _one_put(db, orders: list[tuple[str, int, str, str]], live: str | None, rates=RATES, stale: bool = False):
    """The single reply and the list row of a one-contract book; ``stale``: the quote is 10 minutes old (REQ-109
    AC-5)."""
    app, stored, provider, _clock, last = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id, [_new(c0, side, qty, price, kind)
                                                              for side, qty, price, kind in orders])
    if live is not None:
        provider.on_frame(_frame(provider, IDS[0], live), last)
    app.dependency_overrides[load_charge_rates] = lambda: rates
    if stale:
        _clock.now = last + datetime.timedelta(minutes=10)
    async with _client(app) as c:
        body = (await c.get(f"/paper/strategies/{stored.id}")).json()
        listed = (await c.get("/paper/strategies")).json()
    return body, next(s for s in listed["strategies"] if s["strategy_id"] == stored.id), listed["totals"]


async def test_core_closed_book_booked_after_is_booked_minus_all_charges_and_unbooked_after_is_zero(db):
    # ADR-303: booked -32.50, paid 62.63 (hand sum in _closed_141_like) -> Booked after -95.13, Unbooked after 0.
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open"), ("BUY", 65, "100.50", "exit")], None)
    for reply in (body, row):
        assert (D(reply["booked_after"]), D(reply["unbooked_after"])) == (D("-95.13"), D("0"))
        assert D(reply["booked_after"]) + D(reply["unbooked_after"]) == D(reply["total_after"])
        assert (reply["booked_after_text"], reply["unbooked_after_text"]) == (MINUS + "95.13", "0.00")
        assert (D(reply["profit_left_after"]), D(reply["loss_left_after"]), reply["recover"]) == (0, 0, None)
        assert (D(reply["booked"]), D(reply["total"])) == (D("-32.50"), D("-32.50"))  # old fields keep their meaning
    assert (D(totals["booked_after"]), D(totals["unbooked_after"])) == (D("-95.13"), D("0"))


async def test_open_book_split_adds_up_and_left_figures_are_after_all_charges(db):
    # SELL 65 @ 100, now 80: Booked after = 0 - 36.09 = -36.09; Unbooked after = 1,300.00 - 25.95 = 1,274.05;
    # sum 1,237.96. ADR-306: Profit left after = Max profit after 6,437.38 - Total after 1,237.96 = 5,199.42 (in profit:
    # no recover). Loss left is "unlimited" for this short put (no number to take charges from), so it stays so.
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open")], "80.00")
    for reply in (body, row):
        assert (D(reply["booked_after"]), D(reply["unbooked_after"]), D(reply["total_after"])) == (
            D("-36.09"), D("1274.05"), D("1237.96"))
        assert D(reply["profit_left"]) == D("5200.00")  # the old field keeps its meaning (before charges)
        assert D(reply["profit_left_after"]) == D("5199.42")
        assert reply["loss_left"] == reply["loss_left_after"] == "unlimited"
        assert reply["recover"] is None and reply["profit_left_after_text"] == "+5,199.42"
    assert (D(totals["booked_after"]), D(totals["unbooked_after"])) == (D("-36.09"), D("1274.05"))


async def test_partly_closed_book_split_adds_up_to_total_after(db):
    # SELL 130 @ 100, BUY 65 @ 90 exit, now 80: Booked after = 650 - 74.81 = 575.19; Unbooked after = 1,300 - 25.95 =
    # 1,274.05; sum 1,849.24 = Total after.
    body, *_ = await _one_put(db, [("SELL", 130, "100.00", "open"), ("BUY", 65, "90.00", "exit")], "80.00")
    assert (D(body["booked_after"]), D(body["unbooked_after"]), D(body["total_after"])) == (
        D("575.19"), D("1274.05"), D("1849.24"))


async def test_losing_book_profit_left_is_not_capped_and_recover_is_sent(db):
    # SELL 65 @ 100, now 150: Total after = -3,250.00 - 36.09 - 28.00 = -3,314.09; Max profit after 6,437.38; ADR-306:
    # Profit left after = 6,437.38 + 3,314.09 = 9,751.47; recover = 3,314.09 (the loss shown as Total P&L).
    body, row, _ = await _one_put(db, [("SELL", 65, "100.00", "open")], "150.00")
    for reply in (body, row):
        assert D(reply["max_profit"]) == D("6437.38") and D(reply["total_after"]) == D("-3314.09")
        assert (D(reply["profit_left_after"]), D(reply["recover"])) == (D("9751.47"), D("3314.09"))
        assert D(reply["total_after"]) + D(reply["profit_left_after"]) == D(reply["max_profit"])
        assert reply["recover_text"] == "+3,314.09"


async def test_unknown_rates_keep_the_before_figures_and_send_no_after_figure(db):
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open")], "80.00", rates=None)
    for reply in (body, row):
        assert D(reply["profit_left"]) == D("5200.00") and D(reply["booked"]) == D("0")
        assert all(reply[k] is None for k in SPLIT_KEYS) and reply["after_charges_reason"] == "rates_unavailable"
    assert (totals["booked_after"], totals["unbooked_after"]) == (None, None)


async def test_a_missing_price_pauses_total_and_unbooked_after_but_booked_after_is_booked_minus_paid(db):
    # ADR-311 (4): Total / Unbooked / Profit left / Loss left after charges stay absent with the price reason; Booked
    # after = booked (0.00: nothing closed) - ALL charges paid, a figure that needs no price.
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open")], "80.00", stale=True)
    for reply in (body, row):
        assert all(reply[k] is None for k in SPLIT_KEYS if k != "booked_after")
        assert reply["total_after"] is None and reply["after_charges_reason"] == "prices_not_live"
        assert reply["charges_paid"] is not None and D(reply["booked"]) == D("0")
        assert D(reply["booked_after"]) == D("0") - D(reply["charges_paid"]) and D(reply["booked_after"]) < 0
        assert reply["booked_after_reason"] is None
    # the all-strategies row: Booked after = the sum over every book (one book here: its own figure, minus the charges
    # paid on its one order); Unbooked after and Total after stay absent while a book is paused
    assert D(totals["booked_after"]) == D(body["booked_after"]) == D("0") - D(body["charges_paid"])
    assert (totals["unbooked_after"], totals["total_after"], totals["booked_after_reason"]) == (None, None, None)


async def test_tracking_replies_carry_the_split_from_the_same_function(db):
    app, stored = await _closed_141_like(db)  # booked -32.50, paid 62.63 -> Booked after -95.13, Unbooked after 0
    async with _client(app) as c:
        tracked = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        listed = next(s for s in (await c.get("/tracking")).json()["strategies"] if s["strategy_id"] == stored.id)
    for body in (tracked, listed):
        assert (D(body["booked_after"]), D(body["unbooked_after"])) == (D("-95.13"), D("0"))
        assert body["booked_after_text"] == MINUS + "95.13" and D(body["booked"]) == D("-32.50")


# --- GC-ICFIX u129 round 2 (F1): an AVERAGE entry price with more than two decimals must not crash any route ---------

async def test_f1_averaged_entry_answers_200_with_the_same_figures_on_paper_and_tracking_routes(db):
    # SELL 65 @ 100.00 + SELL 65 @ 100.05 (average 100.025), now 101. Hand sums: test_after_split_average.
    # paid 72.18 (two real fills), exit BUY 130 @ 101 = 29.52, before (100.025 - 101) x 130 = -126.75, total after
    # -228.45, Booked after -72.18, Unbooked after -156.27.
    app, stored, provider, _clock, last = await _setup(db)
    c0 = stored.saved.contract_ids[0]
    await paper_store.place(db, stored.user_ref, stored.id,
                            [_new(c0, "SELL", 65, "100.00"), _new(c0, "SELL", 65, "100.05", "add")])
    provider.on_frame(_frame(provider, IDS[0], "101.00"), last)
    app.dependency_overrides[load_charge_rates] = lambda: RATES
    async with _client(app) as c:
        replies = {"paper": await c.get(f"/paper/strategies/{stored.id}"),
                   "paper_list": await c.get("/paper/strategies"),
                   "tracking": await c.get(f"/strategies/{stored.id}/tracking"),
                   "tracking_list": await c.get("/tracking")}
    assert {k: r.status_code for k, r in replies.items()} == dict.fromkeys(replies, HTTPStatus.OK)
    rows = [next(s for s in replies[k].json()["strategies"] if s["strategy_id"] == stored.id)
            for k in ("paper_list", "tracking_list")]
    for body in (replies["paper"].json(), replies["tracking"].json(), *rows):
        assert (D(body["total_after"]), D(body["charges_paid"]), D(body["charges_to_close"])) == (
            D("-228.45"), D("72.18"), D("29.52"))
        assert (D(body["booked_after"]), D(body["unbooked_after"])) == (D("-72.18"), D("-156.27"))
    assert D(replies["paper_list"].json()["totals"]["total_after"]) == D("-228.45")


async def test_f1_a_list_row_the_engine_cannot_price_keeps_its_reason_and_the_list_still_answers(db):
    # the paper list answers 200 for an averaged book whose quote is stale: that row carries prices_not_live, no number.
    body, row, totals = await _one_put(db, [("SELL", 65, "100.00", "open"), ("SELL", 65, "100.05", "add")], "101.00",
                                       stale=True)
    for reply in (body, row):
        assert reply["total_after"] is None and reply["after_charges_reason"] == "prices_not_live"
    assert totals["total_after"] is None
