"""ADR-330 (6), P6: GET /paper/strategies/{id}/leg-stop-risk?contract_id=&level=, replay market, real PostgreSQL, every
test rolled back. A one-leg exit basket is priced AT THE STOP LEVEL (a given price, never a live read) through the one
engine (exit_risk, ADR-008) and answered with the widening line; it informs only and never blocks a save.

The book is the app's iron condor (65 units a leg, both spreads 200 wide): SELL 22800 CE 80, BUY 23000 CE 20,
SELL 22400 PE 130, BUY 22200 PE 34. Net credit 156 a unit = 10,140.00; Max Loss before = 13,000.00 - 10,140.00 =
2,860.00 (the 25 Nov "now" figure). A stop on the short call at 140.70 buys it back for 9,145.50, leaving the long call
and the put spread: Max Loss after = 2,860.00 + 9,145.50 = 12,005.50. The 25 Nov cent (12,005.51) is not reachable with
orders at 0.05 steps in any quantity (every booked amount is a multiple of 0.05). The real stop fills at the live
price, which can carry paisa; this line is an estimate at the stop level. The engine figure for this book is 12,005.50
and the test pins that, not a bent number."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.engine.extremes import ExitRisk
from ofo_app import paper_store
from ofo_app.routes import paper as paper_routes
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _setup

D = Decimal
AT = datetime.datetime(2026, 11, 25, 5, 0, tzinfo=datetime.UTC)
PRICES = ("80", "20", "130", "34")  # SELL 22800 CE, BUY 23000 CE, SELL 22400 PE, BUY 22200 PE
SIDES = ("SELL", "BUY", "SELL", "BUY")
SHORT_CALL, LONG_CALL, SHORT_PUT, LONG_PUT = range(4)
LEGS = len(SIDES)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _book(db, **kw):
    app, stored, *_ = await _setup(db, **kw)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[i], SIDES[i], 65, D(PRICES[i]), "open", AT) for i in range(4)])
    return app, stored, ids


async def _ask(app, strategy_id, contract_id, level):
    async with _client(app) as c:
        return await c.get(f"/paper/strategies/{strategy_id}/leg-stop-risk",
                           params={"contract_id": contract_id, "level": level})


async def _orders(db, strategy_id) -> int:
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": strategy_id})).scalar_one()


async def test_25_nov_short_call_stop(db):
    app, stored, ids = await _book(db)
    reply = await _ask(app, stored.id, ids[SHORT_CALL], "140.70")
    assert reply.status_code == HTTPStatus.OK, reply.text
    body = reply.json()
    assert body["state"] == "yes"
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 12,005.50 (now Rs 2,860.00)."
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-12005.50")
    assert await _orders(db, stored.id) == LEGS  # read only


async def test_a_small_change_still_shows_the_line_whatever_its_size(db):
    """ADR-330 (6) states no threshold (ADR-256's "more than double" is the exit confirmation's): 2,860 -> 3,510."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[SHORT_PUT], "10.00")).json()
    assert body["state"] == "yes"
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 3,510.00 (now Rs 2,860.00)."
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-3510.00")


async def _locked_profit_book(db):
    """Put side closed (short put bought back at 1, long put sold at 100): cash 16,575.00, calls open, so max loss is
    16,575.00 - 13,000.00 = +3,575.00, a profit, never a loss (M2)."""
    app, stored, ids = await _book(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[SHORT_PUT], "BUY", 65, D("1"), "exit", AT),
        paper_store.NewOrder(ids[LONG_PUT], "SELL", 65, D("100"), "exit", AT)])
    return app, stored, ids


async def test_a_book_with_locked_in_profit_still_a_profit_after_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "140.70")).json()
    assert body["state"] == "yes"
    assert body["warning_text"] == ("If this stop fires, the book shows a profit of at least Rs 7,429.50 "
                                    "(now at least Rs 3,575.00).")


async def test_a_book_with_locked_in_profit_turned_into_a_loss_by_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "400.00")).json()  # buys back for 26,000.00: 16,575 - 26,000
    assert body["warning_text"] == ("If this stop fires, max loss becomes Rs 9,425.00 "
                                    "(now a profit: at least Rs 3,575.00).")


async def test_a_book_with_locked_in_profit_turned_unlimited_by_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[LONG_CALL], "5.00")).json()
    assert body["warning_text"].startswith("If this stop fires, there is no fixed maximum loss "
                                           "(now a profit: at least Rs 3,575.00).")
    assert "-" not in body["warning_text"].split("Sold option")[0]


async def test_a_stop_on_a_long_wing_leaves_the_short_leg_bare_so_it_is_yes_with_no_fixed_maximum(db):
    """The plan expected "no" here; the engine says yes: selling the long call leaves the short call with no cover."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[LONG_CALL], "5.00")).json()
    assert body["state"] == "yes" and body["max_loss_after"] == "unlimited"
    assert body["warning_text"].startswith(
        "If this stop fires, there is no fixed maximum loss (now Rs 2,860.00). Sold option with less protection: ")


async def test_a_stop_that_cannot_be_priced_is_cannot_tell_with_no_figure(db, monkeypatch):
    monkeypatch.setattr(paper_routes, "exit_risk", lambda *a, **k: ExitRisk("cannot_tell", None, None, ()))
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "140.70")).json()
    assert body["state"] == "cannot_tell"
    assert body["max_loss_before"] is None and body["warning_text"] is None


async def test_another_users_or_a_missing_strategy_answers_not_found(db):
    app, stored, ids = await _book(db)
    other, *_ = await _setup(db)
    assert (await _ask(other, stored.id, ids[SHORT_CALL], "140.70")).status_code == HTTPStatus.NOT_FOUND
    assert (await _ask(app, 999999999, ids[SHORT_CALL], "140.70")).status_code == HTTPStatus.NOT_FOUND


async def test_a_contract_that_is_not_open_is_refused_like_the_save(db):
    app, stored, ids = await _book(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[SHORT_CALL], "BUY", 65, D("80"), "exit", AT)])  # the short call is now closed
    for contract in (ids[SHORT_CALL], 999999999):
        reply = await _ask(app, stored.id, contract, "140.70")
        assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, reply.text
        assert "state" not in reply.json()
        assert reply.json()["code"] == "STRATEGY_VALIDATION_441", reply.text


async def test_a_level_that_is_not_a_multiple_of_five_paise_is_refused_like_the_save(db):
    app, stored, ids = await _book(db)
    for bad in ("140.72", "0", "-5"):
        reply = await _ask(app, stored.id, ids[SHORT_CALL], bad)
        assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (bad, reply.text)
        assert "state" not in reply.json()
        assert reply.json()["code"] == "STRATEGY_VALIDATION_440", reply.text


async def test_m1_a_stop_that_leaves_a_sold_put_uncovered_prints_no_index_to_zero_figure_and_no_iso_date(db):
    """Lane M, 27 Nov (B-N1 #194 on screen: "max loss becomes Rs 16,62,316.50 (now Rs 1,732.25)" and an ISO date).
    A stop on the LONG put at 5.00 leaves the short 22400 PE bare: the lowest point is the index at 0,
    -22400 x 65 + 10,465.00 = -14,45,535.00, a figure no one can act on. The line says the loss is not capped by the
    trade's own legs instead (wording pending owner read), and names the leg as the screens do (REQ-151), never ISO."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[LONG_PUT], "5.00")).json()
    assert body["state"] == "yes"
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-1445535.00")  # the engine's figures
    text_ = body["warning_text"]
    assert "14,45,535" not in text_ and "-" not in text_.split(".")[0]
    assert text_.startswith("If this stop fires, a sold option is left without a bought option of its type covering "
                            "it, so its loss grows as the index moves past its strike (now Rs 2,860.00). "
                            "Sold option with less protection: NIFTY ")
    assert text_.endswith("Sold option with less protection: NIFTY 13 Oct 22400 PE.") and "2026-" not in text_
