"""I-63 (test plan 28 Nov 2026), a MONEY and EXIT path: an armed stop on a SOLD leg reads "above 135.00" while the
leg's price is lower. Which side is the stop on? Answer: a sold (short) leg loses when its premium RISES, so its loss
stop sits ABOVE the leg's price (a sold CE or PE alike; a bought leg's loss stop sits below). It fires when the live
price is at or above the level and never below it. No code is side-aware: the route only refuses a level the live price
is ALREADY at or beyond, and only in market hours (closed market: saved, ADR-327 (3)). So "above 135.00" with the
price at 39.15 is the correct side; "below 135.00" is refused in market hours ("straight away") and saves when the
market is closed (pinned below as it behaves today). A level below the price that is not yet crossed (e.g. 35.00)
also saves, with the widening line "max loss becomes ..." (observation, owner decision: word or refuse; pinned as
today's behaviour).
Real case: the S-21 book of ``test_paper_triggers_routes``: SELL 22800 CE at 39.15 (replay price 39.15), BUY 23000 CE
at 12.95; the user's level 135.00 (the review case of 28 Nov).
Spec basis: ADR-207 (5) (per-leg stop-loss; ``above`` fires AT or ABOVE the level), ADR-327 (3), ADR-330 (6).
Pure rule first (``ofo.tracking.stops.crossed``), then the route on a real database.
"""
from __future__ import annotations

from decimal import Decimal as D
from http import HTTPStatus

import pytest
from ofo.tracking import paper
from ofo.tracking.stops import Trigger, crossed
from test_paper_triggers_routes import (  # noqa: F401 - db and notified are fixtures, used by name
    _client,
    _close_the_market,
    _open,
    _orders,
    _stored,
    _url,
    db,
    notified,
)

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


@pytest.mark.parametrize("state", ["stale", "missing"])
def test_a_stale_or_missing_price_never_fires_either_side_even_when_it_carries_a_number(state):
    carrying = paper.Price(INSTRUMENT, state, D("200.00"), None)  # a number at or above 135, past the "below" level too
    assert crossed(_stop("above"), carrying) is False and crossed(_stop("below"), carrying) is False


def test_the_boundaries_are_inclusive_on_both_sides():
    assert crossed(_stop("above", D("39.15")), _price("39.15")) is True  # at the level
    assert crossed(_stop("below", D("39.15")), _price("39.15")) is True
    assert crossed(_stop("above", D("39.16")), _price("39.15")) is False
    assert crossed(_stop("below", D("39.14")), _price("39.15")) is False


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
    assert [r[:3] for r in await _stored(db, stored.id)] == [("leg_stop", "above", D("135.00"))]
    assert notified == [1]  # the monitor was told
    body = risk.json()
    assert (risk.status_code, body["state"]) == (HTTPStatus.OK, "yes")
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 7,072.00 (now Rs 11,297.00)."


async def test_the_route_refuses_a_level_below_135_the_sold_legs_price_is_already_under(db, notified):  # noqa: F811
    app, stored, ids = await _open(db)
    before = await _orders(db, stored.id)
    async with _client(app) as c:
        refused = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "below",
                                                   "level": "135.00"})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, refused.text
    assert "straight away" in refused.text and "use Exit" in refused.text
    assert await _stored(db, stored.id) == [] and notified == []  # nothing armed, nothing exited
    assert await _orders(db, stored.id) == before  # a refused save places no paper order


@pytest.mark.parametrize("level", ["39.15", "39.14"])
async def test_a_sold_legs_stop_above_a_price_it_has_already_reached_is_refused_in_market_hours(db, notified, level):  # noqa: F811
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        refused = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "above",
                                                   "level": level})
    assert refused.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, refused.text  # at or below: crossed
    assert await _stored(db, stored.id) == [] and notified == []


async def test_with_the_market_closed_a_below_level_on_the_sold_leg_saves_as_the_spec_says(db, notified):  # noqa: F811
    """ADR-327 (3): closed, the level is not checked against a price; it arms and judges at the next live tick. Today a
    "below 135.00" saved on a Saturday would fire at Monday's first tick (39 is below 135): an owner decision (word the
    side or refuse), recorded in RESULTS; pinned here so a change shows."""
    app, stored, ids = await _open(db)
    _close_the_market(app)
    async with _client(app) as c:
        saved = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "below",
                                                 "level": "135.00"})
    assert saved.status_code == HTTPStatus.CREATED, saved.text
    assert [r[:3] for r in await _stored(db, stored.id)] == [("leg_stop", "below", D("135.00"))]


async def test_a_level_below_the_sold_legs_price_saves_and_the_line_reads_like_protection(db, notified):  # noqa: F811
    """OBSERVATION pinned as today's behaviour (owner decision, see RESULTS): "below 35.00" on the SOLD leg at 39.15 is
    saved; it can only fire when the trade is winning, yet the widening line says max loss falls to Rs 572.00."""
    app, stored, ids = await _open(db)
    async with _client(app) as c:
        saved = await c.post(_url(stored), json={"kind": "leg_stop", "contract_id": ids[0], "direction": "below",
                                                 "level": "35.00"})
        risk = await c.get(f"/paper/strategies/{stored.id}/leg-stop-risk",
                           params={"contract_id": ids[0], "level": "35.00"})
    assert saved.status_code == HTTPStatus.CREATED, saved.text
    assert risk.json()["warning_text"] == "If this stop fires, max loss becomes Rs 572.00 (now Rs 11,297.00)."
