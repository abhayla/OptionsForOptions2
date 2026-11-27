"""I-63 (test plan 28 Nov 2026), a MONEY and EXIT path: an armed stop on a SOLD leg reads "above 135.00" while the
leg's price is lower. Which side is the stop on? Answer pinned here: a sold (short) leg loses when its price
RISES, so its loss stop sits ABOVE the leg's price; it fires when the live price is at or above the level
(buy to close) and never below
it. The wrong side (a level below the price, for a stop that must sit above) would exit at once: the route
refuses a level the price is already at or beyond ("straight away"), so an above level is the only one that saves with
a lower price, and the reply says the direction it stored.

Real case: the S-21 book of ``test_paper_triggers_routes``: SELL 22800 CE at 39.15 (replay price 39.15), BUY 22600 CE.
The user's level 135.00 above that price (the review case of 28 Nov) and 45.00.
Spec basis: ADR-207 (5) (per-leg stop-loss; ``above`` fires AT or ABOVE the level), ADR-330 (6) (the widening line),
REQ-109 AC-8. Pure rule first (``ofo.tracking.stops.crossed``), then the route on a real database.
"""
from __future__ import annotations

from decimal import Decimal as D
from http import HTTPStatus

import pytest
from ofo.tracking import paper
from ofo.tracking.stops import Trigger, crossed
from test_paper_triggers_routes import _client, _open, _stored, _url, db, notified  # noqa: F401 - fixtures by name

SOLD_PRICE = D("39.15")
LEVEL = D("135.00")
INSTRUMENT = "NSE_FO:44624"


def _price(value: str) -> paper.Price:
    return paper.Price(INSTRUMENT, paper.LIVE, D(value), None)


def _stop(direction: str, level: D = LEVEL) -> Trigger:
    return Trigger(1, 1, "leg_stop", direction, level, contract_id=9496)  # type: ignore[arg-type]


@pytest.mark.parametrize(("live", "fires"), [("39.15", False), ("134.99", False), ("135.00", True), ("135.01", True),
                                             ("200.00", True)])
def test_a_stop_above_135_on_a_sold_leg_fires_only_at_or_above_135(live, fires):
    assert crossed(_stop("above"), _price(live)) is fires


def test_a_stop_below_135_would_fire_at_once_for_a_sold_leg_priced_lower_so_it_is_the_wrong_side():
    assert crossed(_stop("below"), _price("39.15")) is True  # the wrong side: the sold leg would close on arming
    assert crossed(_stop("below"), _price("135.01")) is False


def test_a_stale_price_never_fires_either_side():
    stale = paper.Price(INSTRUMENT, "stale", None, None)
    assert crossed(_stop("above"), stale) is False and crossed(_stop("below"), stale) is False


async def test_the_route_arms_above_135_on_the_sold_leg_and_says_so(db, notified):  # noqa: F811
    app, stored, ids = await _open(db)  # ids[0] is SOLD at 39.15
    async with _client(app) as c:
        saved = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above",
                                                 "level": "135.00"})
        listed = await c.get(_url(stored))
        risk = await c.get(f"/paper/strategies/{stored.id}/leg-stop-risk",
                           params={"contract_id": ids[0], "level": "135.00"})
    assert saved.status_code == HTTPStatus.CREATED, saved.text
    row = next(t for t in listed.json()["triggers"] if t["contract_id"] == ids[0])
    assert (row["kind"], row["direction"], row["level"], row["level_text"], row["state"]) == (
        "leg_stop", "above", "135.00", "135.00", "armed")
    assert D(row["level"]) > SOLD_PRICE  # the stop sits ABOVE the sold leg's price
    assert [r[:3] for r in await _stored(db, stored.id)] == [("leg_stop", "above", D("135.00"))]
    assert notified == [1]  # the monitor was told
    body = risk.json()
    assert (risk.status_code, body["state"]) == (HTTPStatus.OK, "yes")
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 7,072.00 (now Rs 11,297.00)."


async def test_the_route_refuses_a_level_below_135_the_sold_legs_price_is_already_under(db, notified):  # noqa: F811
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        refused = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "below",
                                                   "level": "135.00"})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, refused.text
    assert "straight away" in refused.text and "use Exit" in refused.text
    assert await _stored(db, stored.id) == [] and notified == []  # nothing armed, nothing exited
