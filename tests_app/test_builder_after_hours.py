"""GC-BM F-17 / ADR-200: outside market hours the builder prices from the last close, labelled; orders still refuse.

Spec basis (quoted): ADR-200 "(1) Outside market hours (ADR-119 calendar) the Strategy Builder and its strike drawer
use the last price each contract had at the close as its price: planned entries are captured from it, and the summary,
payoff chart, tables and Greeks are computed from it by the one engine"; "(2) Every such number sits under the shared
label "Market closed. Prices are from <time>." (ADR-177) ... Nothing is ever shown as live (ADR-015)"; "(3) Execution is
unchanged"; "(4) ... a contract with no such price stays unpriced with the existing reason, never a default".

Real rows: the recorded 2026-10-08 NIFTY session (tests/fixtures/kite_ws), replayed into the REAL KiteProvider, then the
injected clock moved to 18:00 IST the same trading day (the ADR-119 calendar says closed). Driven through the project's
clock seam (``get_answer_clock`` / ``MarketContext.clock``), never the wall clock. No database, no Kite connection.

Quote states (standing item d), each with what it does:
  live (in hours, frames inside 3 s)        -> AVAILABLE: priced, no label (unchanged)
  stale (in hours, frames stopped > 3 s)    -> STALE: never captured as an entry (unchanged)
  market closed, a price held from the session -> health STALE on the wire (never "available", ADR-015), priced for
      planning; the answer carries market_closed true + last_price_at (the one ADR-177 banner); no "stale since",
      no "disconnected" text; every order path still refuses (it needs AVAILABLE or the open calendar)
  market closed, no price held              -> unpriced with the existing reason (no_live_price), never a default
  market closed, the price from an older session (a holiday before) -> the same rule (the weekend case below: the
      last price is two days old and still the last close)
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402

RATE = Decimal("0.065")
CONDOR = (("NSE_FO:44624", "SELL"), ("NSE_FO:44632", "BUY"), ("NSE_FO:44604", "SELL"), ("NSE_FO:44595", "BUY"))
IN_HOURS = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)  # inside the recording: the feed is live
AFTER_CLOSE = datetime.datetime(2026, 10, 8, 18, 0, tzinfo=IST)  # same trading day, market closed (ADR-119)
SATURDAY = datetime.datetime(2026, 10, 10, 11, 0, tzinfo=IST)  # weekend: closed, the same as after the close
HTTP_OK = 200


def _replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    last = replay(provider, clock)
    return provider, clock, last


def _app(provider, clock):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context, get_streaming
    from ofo_app.routes.planned_entry import get_live_feed

    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, clock, RATE)
    app.dependency_overrides[get_answer_clock] = lambda: clock
    app.dependency_overrides[get_streaming] = lambda: None
    app.dependency_overrides[get_live_feed] = lambda: None
    return app


def _held_ltp(provider, instrument_id: str) -> str:
    """The last price the book holds (read at a time the feed was live, so the read itself is not the rule tested)."""
    return f"{provider.book.get(instrument_id, IN_HOURS).ltp:f}"


def _condor(provider, captured_at: datetime.datetime) -> dict:
    return {"underlying": "NIFTY", "legs": [{"instrument_id": iid, "action": action, "lots": 1,
                                             "planned_entry": _held_ltp(provider, iid),
                                             "captured_at": captured_at.isoformat()} for iid, action in CONDOR]}


async def _outcome_at(at: datetime.datetime):
    provider, clock, last = _replayed()
    body = _condor(provider, at)
    clock.now = at
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/outcome", json=body)
    assert resp.status_code == HTTP_OK, resp.text
    return resp.json(), last


async def _capture_at(at: datetime.datetime, ids=None):
    provider, clock, last = _replayed()
    clock.now = at
    ids = ids or [iid for iid, _ in CONDOR]
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/planned-entry", json={"underlying": "NIFTY", "instrument_ids": ids})
    assert resp.status_code == HTTP_OK, resp.text
    return resp.json(), provider, last


# ---- attack 1: outcome COMPUTED after the close, labelled, the same numbers as in hours --------------------------

async def test_after_close_the_outcome_is_computed_from_the_last_prices_labelled_market_closed():
    out, last = await _outcome_at(AFTER_CLOSE)
    assert out["state"] == "COMPUTED", (out["state"], out["status_label"])
    assert out["market_closed"] is True
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == last
    assert out["summary"] is not None and out["payoff"] is not None and out["payoff"]["points"]
    assert out["status_label"] is None  # never REQ-049 AC-5's "disconnected" text: a closed market is expected silence
    assert out["output_label"] in (None, "estimated from spot")  # never "stale since HH:MM IST"
    for leg in out["legs"]:  # priced from the held last close, never shown as live
        assert leg["ltp"] is not None and leg["health"] == "stale" and leg["label"] is None
    assert {q["health"] for q in out["leg_quotes"]} == {"stale"}


async def test_after_close_the_numbers_equal_those_at_the_same_prices_in_hours():
    """ADR-200 (1) "exactly as during market hours": the at-expiry payoff and summary are the engine's numbers on the
    held prices; only the labels differ."""
    closed, _ = await _outcome_at(AFTER_CLOSE)
    live, _ = await _outcome_at(IN_HOURS)
    assert live["state"] == "COMPUTED" and live["output_label"] is None
    assert closed["payoff"]["points"] == live["payoff"]["points"]
    for key in ("max_profit", "max_loss", "breakevens"):
        assert closed["summary"][key] == live["summary"][key]
    assert closed["spot_level"] == live["spot_level"]


async def test_weekend_is_the_same_as_after_the_close():
    out, last = await _outcome_at(SATURDAY)
    assert out["state"] == "COMPUTED" and out["market_closed"] is True
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == last
    assert out["status_label"] is None and all(leg["label"] is None for leg in out["legs"])


# ---- attack 2: planned-entry captures from the held price after the close -----------------------------------------

async def test_after_close_planned_entry_captures_the_held_last_price():
    body, provider, _last = await _capture_at(AFTER_CLOSE)
    for entry, (iid, _action) in zip(body["entries"], CONDOR, strict=True):
        assert entry["reason_code"] is None, entry
        assert Decimal(entry["planned_entry"]) == Decimal(_held_ltp(provider, iid))  # the held LTP, to the paisa
        assert entry["source"] == "ltp"
        assert datetime.datetime.fromisoformat(entry["captured_at"]) == AFTER_CLOSE


# ---- attack 4: in hours unchanged (3 s staleness still refuses a capture) ------------------------------------------

async def test_in_hours_a_stale_feed_still_captures_nothing():
    body, _provider, last = await _capture_at(last_plus := datetime.datetime(2026, 10, 8, 11, 0, tzinfo=IST))
    assert last_plus - last > datetime.timedelta(seconds=3)
    assert {e["reason_code"] for e in body["entries"]} == {"no_live_price"}
    assert all(e["planned_entry"] is None for e in body["entries"])


async def test_in_hours_a_stale_feed_keeps_the_stale_label_not_the_market_closed_one():
    out, _last = await _outcome_at(datetime.datetime(2026, 10, 8, 11, 0, tzinfo=IST))
    assert out["market_closed"] is False
    assert all(leg["health"] == "stale" for leg in out["legs"])
    assert all(leg["label"] == "stale since 09:20 IST" for leg in out["legs"])  # REQ-072 AC-2, unchanged
    assert out["output_label"].startswith("stale since 09:20 IST")


# ---- attack 5: no held price after hours stays unpriced with the reason -------------------------------------------

async def test_after_close_a_contract_with_no_held_price_stays_unpriced_with_the_reason():
    provider, clock, _last = _replayed()
    iid = CONDOR[0][0]
    provider.book.remove(iid)  # its subscription ended: the price is gone (the time alone is kept, ADR-077)
    clock.now = AFTER_CLOSE
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        resp = await ac.post("/api/strategies/planned-entry", json={"underlying": "NIFTY", "instrument_ids": [iid]})
    entry = resp.json()["entries"][0]
    assert (entry["planned_entry"], entry["reason_code"], entry["source"]) == (None, "no_live_price", None)


@pytest.mark.parametrize("at", [AFTER_CLOSE, SATURDAY])
def test_a_closed_market_quote_is_never_available(at):
    """ADR-015: the held price is a planning price, never live: no order path that requires AVAILABLE accepts it."""
    from ofo.marketdata.quote import priced
    from ofo.rules.inputs import DataHealth

    provider, _clock, _last = _replayed()
    quotes = provider.book.quotes(at)
    assert quotes and {q.health for q in quotes} == {DataHealth.STALE}
    assert not any(priced(q) for q in quotes)
    assert provider.latest_depth(CONDOR[0][0], at) is None


async def test_after_close_the_outcome_names_a_leg_with_no_held_price_and_gives_it_no_default():
    """ADR-200 (4) through the outcome route: the leg whose price is gone has no LTP and the existing reason."""
    provider, clock, _last = _replayed()
    body = _condor(provider, AFTER_CLOSE)
    gone = CONDOR[0][0]
    provider.book.remove(gone)
    clock.now = AFTER_CLOSE
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        out = (await ac.post("/api/strategies/outcome", json=body)).json()
    leg = next(x for x in out["legs"] if x["instrument_id"] == gone)
    assert leg["ltp"] is None and leg["iv"] is None and leg["label"] == "no live quote"
    assert all(x["ltp"] is not None for x in out["legs"] if x["instrument_id"] != gone)


# ---- attack 3: every order path keeps refusing after the close -------------------------------------------------------

@pytest.mark.parametrize("at", [AFTER_CLOSE, SATURDAY])
def test_after_close_the_execute_market_gate_refuses_with_the_req_056_text(at):
    """ADR-200 (3) / ADR-119: Execute's market check is the shared calendar; closed -> the gate refuses with the
    catalogue text, whatever prices the builder shows."""
    from ofo.errors import render
    from ofo.market_calendar import is_market_open
    from ofo_app.routes import execute

    assert execute.market_open is is_market_open
    assert execute.market_open(at) is False and execute.market_open(IN_HOURS) is True
    assert render("gate_market_closed").what_happened == "The market is closed. Orders can be placed once it opens."


@pytest.mark.parametrize("at", [AFTER_CLOSE, SATURDAY])
def test_after_close_a_held_last_close_never_reaches_an_execute_order_price(monkeypatch, at):
    """The Execute price source (``LiveDepthQuotes``, the basket's per-leg price) on the provider that prices the
    builder after hours: no leg quote at all, so no order or basket can be priced from the last close. In hours the
    same provider gives one (the recorded frames are full frames), so the refusal is the closed market's."""
    from ofo.instruments.models import InstrumentId
    from ofo_app import live_market
    from ofo_app.routes import execute
    from ofo_app.routes.outcome import MarketContext

    provider, clock, _last = _replayed()
    monkeypatch.setattr(live_market, "current_context", lambda: MarketContext(provider, clock, RATE))
    segment, _, token = CONDOR[0][0].partition(":")
    leg = InstrumentId(segment, int(token))
    clock.now = IN_HOURS
    assert execute.LiveDepthQuotes(lambda: IN_HOURS).leg_quote(leg, "x") is not None
    clock.now = at
    assert execute.LiveDepthQuotes(lambda: at).leg_quote(leg, "x") is None


# ---- the strike drawer (leg picker strikes and futures cells, ADR-200 (1) "and its strike drawer") ------------------

def _picker(at: datetime.datetime, health):
    """The leg-picker fakes (tests_app/test_leg_picker_routes.py) with every quote at ``health`` and the feed clock at
    ``at``: the FakeProvider keeps no FeedState, so the ADR-119 calendar answers (``market_closed_for``)."""
    import test_leg_picker_routes as lp
    from ofo.engine.legs import Instrument
    from ofo.marketdata.fanout import FanOut
    from ofo_app.live_push import LiveFeed
    from ofo_app.routes.outcome import MarketContext

    provider, _ = lp.priced_provider(spot_health=health)
    for (strike, kind), (ltp, oi) in lp.PRICES.items():
        c = lp.cid(strike, kind)
        provider.quotes[c] = lp.quote(c, Instrument(kind), Decimal(strike), ltp, oi=oi, health=health)
    provider.futures[lp.FAR_EXPIRY] = lp.quote(lp.FUT.instrument_id, Instrument.FUT, None, "22611.40",
                                               expiry=lp.FAR_EXPIRY, health=health)
    return lp, LiveFeed(MarketContext(provider, lambda: at, RATE), FanOut(provider))


@pytest.mark.parametrize(("at", "health", "shown"), [
    (AFTER_CLOSE, "stale", True),   # the last close held: priced
    (SATURDAY, "stale", True),      # weekend: the same
    (IN_HOURS, "stale", False),     # in hours a stale quote is never a price (unchanged)
    (AFTER_CLOSE, "unhealthy", False),  # an unsound quote never counts, closed or not
])
def test_the_strike_drawer_prices_the_last_close_after_hours_only(at, health, shown):
    from ofo.rules.inputs import DataHealth
    from ofo_app.routes import leg_picker

    lp, feed = _picker(at, DataHealth(health))
    try:
        out = leg_picker.strikes_answer(feed, "NIFTY", lp.EXPIRY, 10, lp.catalogue(), lambda: at)
        futures = leg_picker.futures_answer(feed, "NIFTY", lp.futures_catalogue(), lambda: at)
    finally:
        leg_picker.LEASE.release()
        leg_picker.FUTURES_LEASE.release()
    ltps = sorted(c.ltp for c in lp.cells(out) if c.ltp is not None)
    fut = futures.futures[0]
    if shown:
        assert out.market_closed is True
        assert ltps == [Decimal("145.10"), Decimal("151.30")]
        assert all(c.health == "stale" for c in lp.cells(out) if c.ltp is not None)  # never shown as live
        assert (fut.ltp, fut.ltp_reason, fut.health) == (Decimal("22611.40"), None, "stale")
    else:
        assert ltps == []
        assert fut.ltp is None and fut.ltp_reason == "FEED_STALE"
