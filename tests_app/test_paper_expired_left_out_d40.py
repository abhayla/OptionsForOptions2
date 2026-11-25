"""D-40 (23 Nov live test): old scenario strategies on expired contracts must not blank the paper page header, and a
strategy whose contract row cannot be read answers a plain reason, not a server error. Real routes, real database.

Real case: PATH-60 / PATH-61 hold open legs on expired contracts. The header Total / Unbooked / Decay were dashes and
Booked / Charges mixed every strategy. Here the seeded set of test_paper_totals (48 open, 50 fully exited, 46 open) has
one open contract retired: strategy 46 is the expired one; 48 (hand figures -1,504.75 / +10,361.00 / +8,856.25) and 50
are the strategies that can be priced.
"""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

from ofo.errors.explanations import render_explanation
from ofo_app.paper_reasons import reason_text
from sqlalchemy import text
from test_paper_totals import _list, _seed_three, db  # noqa: F401 - db is the rolled-back connection fixture
from test_strategy_store import _client
from test_strategy_tracking import _RETIRE

D = Decimal


async def test_expired_strategy_is_left_out_of_every_header_figure_and_the_line_says_how_many(db):  # noqa: F811
    app, _provider, _clock, _last, seeded = await _seed_three(db)
    await db.execute(text(_RETIRE), {"id": seeded["contracts"][2]})  # 46's BUY leg: its contract has expired
    body = await _list(app)
    rows = {s["strategy_id"]: s for s in body["strategies"]}
    expired = rows[seeded["46"]]
    assert expired["unbooked"] is None and [u["expired"] for u in expired["unpriced_legs"]] == [True]
    kept = [rows[seeded["48"]], rows[seeded["50"]]]
    assert (D(kept[0]["booked"]), D(kept[0]["unbooked"]), D(kept[0]["total"])) == (
        D("-1504.75"), D("10361.00"), D("8856.25"))
    totals = body["totals"]
    booked = sum((D(s["booked"]) for s in kept), D(0))
    unbooked = sum((D(s["unbooked"]) for s in kept), D(0))
    assert (D(totals["booked"]), D(totals["unbooked"]), D(totals["total"])) == (booked, unbooked, booked + unbooked)
    assert totals["totals_reason"] is None and totals["totals_reason_text"] is None
    assert totals["decay"] is not None and totals["decay_reason"] is None
    assert totals["left_out_count"] == 1
    assert totals["left_out_text"] == render_explanation("paper_totals_left_out_one")
    assert totals["left_out_text"] == "1 strategy left out: its contract has expired."


async def test_no_expired_strategy_means_no_left_out_line(db):  # noqa: F811
    app, *_ = await _seed_three(db)
    totals = (await _list(app))["totals"]
    assert (totals["left_out_count"], totals["left_out_text"]) == (0, None)


async def test_a_price_that_is_not_live_still_blanks_the_totals_with_its_reason(db):  # noqa: F811
    app, _provider, clock, last, _seeded = await _seed_three(db)
    import datetime  # noqa: PLC0415
    clock.now = last + datetime.timedelta(minutes=10)  # every price stale: not an expiry, so nothing is left out
    totals = (await _list(app))["totals"]
    assert (totals["unbooked"], totals["total"], totals["totals_reason"]) == (None, None, "prices_not_live")
    assert (totals["left_out_count"], totals["left_out_text"]) == (0, None)


async def test_a_book_on_expired_contracts_answers_200_with_the_plain_reason_the_card_shows(db):  # noqa: F811
    """The route is not the 500: it answers with the reason (the card's failure was in the browser, which read the
    catalogue for the book's expiry, found nothing and threw "unreadable paper book": see live-strategies.test.js)."""
    app, _provider, _clock, _last, seeded = await _seed_three(db)
    for cid in seeded["contracts"]:  # every contract of the books has expired and been retired
        await db.execute(text(_RETIRE), {"id": cid})
    async with _client(app) as c:
        single = await c.get(f"/paper/strategies/{seeded['46']}")
        listed = await c.get("/paper/strategies")
    assert single.status_code == HTTPStatus.OK, single.text
    body = single.json()
    assert (body["state"], body["pause_reason"], body["total"]) == ("PAUSED", "contract_retired", None)
    assert body["pause_reason_text"] == reason_text("contract_retired")
    assert body["unpriced_text"] and body["unpriced_text"].startswith("Expired contracts have no price: ")
    assert listed.status_code == HTTPStatus.OK, listed.text
    totals = listed.json()["totals"]
    assert totals["left_out_count"] == 2  # 46 and 48 hold open legs (50 is fully exited)
    assert totals["left_out_text"] == render_explanation("paper_totals_left_out_many", count=2)
