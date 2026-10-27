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
