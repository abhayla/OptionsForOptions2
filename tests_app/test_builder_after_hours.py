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

import struct  # noqa: E402

import test_drawer_after_hours as dah  # noqa: E402
import test_leg_picker_routes as lp  # noqa: E402
from marketdata._kite_fixture import all_instrument_ids, listed, new_provider, replay  # noqa: E402
from ofo.engine.legs import Instrument  # noqa: E402
from ofo.errors import render  # noqa: E402
from ofo.instruments.models import InstrumentId  # noqa: E402
from ofo.market_calendar import is_market_open  # noqa: E402
from ofo.marketdata.disconnect import market_closed_error  # noqa: E402
from ofo.marketdata.fanout import FanOut  # noqa: E402
from ofo.marketdata.feed_health import FEED_MARKET_CLOSED  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo.marketdata.quote import priced  # noqa: E402
from ofo.rules.inputs import DataHealth  # noqa: E402
from ofo_app import (  # noqa: E402
    index_push,
    live_market,
)
from ofo_app.chain_push import ChainRequest, chain_answer  # noqa: E402
from ofo_app.live_push import LiveFeed  # noqa: E402
from ofo_app.main import create_app  # noqa: E402
from ofo_app.routes import execute, leg_picker  # noqa: E402
from ofo_app.routes.broker_status import build_status  # noqa: E402
from ofo_app.routes.outcome import (  # noqa: E402
    MarketContext,
    MarketState,
    get_answer_clock,
    get_market_context,
    get_streaming,
    label_time,
)
from ofo_app.routes.planned_entry import get_live_feed  # noqa: E402

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
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == _own_time(last)
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
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == _own_time(last)
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

    assert execute.market_open is is_market_open
    assert execute.market_open(at) is False and execute.market_open(IN_HOURS) is True
    assert render("gate_market_closed").what_happened == "The market is closed. Orders can be placed once it opens."


@pytest.mark.parametrize("at", [AFTER_CLOSE, SATURDAY])
def test_after_close_a_held_last_close_never_reaches_an_execute_order_price(monkeypatch, at):
    """The Execute price source (``LiveDepthQuotes``, the basket's per-leg price) on the provider that prices the
    builder after hours: no leg quote at all, so no order or basket can be priced from the last close. In hours the
    same provider gives one (the recorded frames are full frames), so the refusal is the closed market's."""

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


# ---- fix round 1 (Tier A finding 2, ADR-200 (4)): the label time is the quotes' own time, never a frame's ------------

def _own_time(_last) -> datetime.datetime:
    """The latest own last-price time among the quotes the condor answer uses (its four legs and the NIFTY spot)."""
    provider, _clock, _ = _replayed()
    used = [provider.book.get(iid, IN_HOURS) for iid, _ in CONDOR] + [provider.underlying_quote("NIFTY")]
    return max(q.timestamp for q in used if q is not None)


def test_label_time_is_the_latest_quote_time_not_the_reconnect_frame():
    """Attack 3: quotes at 15:29:58 and 15:29:40, a reconnect frame at 21:05 -> the label is 15:29:58."""
    state = MarketState(closed=True, last_price_at=datetime.datetime(2026, 10, 8, 21, 5, tzinfo=IST))
    times = [datetime.datetime(2026, 10, 8, 15, 29, 58, tzinfo=IST),
             datetime.datetime(2026, 10, 8, 15, 29, 40, tzinfo=IST)]
    assert label_time(state, times) == times[0]
    assert label_time(state, []) is None  # no quote time: none invented (never the frame time)
    live = MarketState(closed=False, last_price_at=datetime.datetime(2026, 10, 8, 11, 0, 1, tzinfo=IST))
    assert label_time(live, times) == live.last_price_at  # in hours unchanged: the feed's last price frame


async def test_outcome_after_a_reconnect_frame_is_labelled_with_the_quotes_own_time():
    """Attack 3 through the route on the real replay: a 21:05 price frame time on the feed never labels the banner."""
    provider, clock, last = _replayed()
    body = _condor(provider, AFTER_CLOSE)
    reconnect = datetime.datetime(2026, 10, 8, 21, 5, tzinfo=IST)
    provider.feed._last_tick_frame = reconnect  # simulates a price frame arriving after hours
    clock.now = AFTER_CLOSE
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        out = (await ac.post("/api/strategies/outcome", json=body)).json()
    assert out["market_closed"] is True
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == _own_time(last)
    assert datetime.datetime.fromisoformat(out["last_price_at"]) != reconnect


async def test_a_five_day_old_quote_is_priced_and_labelled_with_its_own_time():
    """Attack 4: an older-session price (4 days 9 h; the recorded contracts expire 13 Oct, so 12 Oct 18:00 is the
    latest closed instant they still price) is still the last close: priced, labelled with its own time."""
    later = datetime.datetime(2026, 10, 12, 18, 0, tzinfo=IST)
    out, last = await _outcome_at(later)
    assert out["state"] == "COMPUTED" and out["market_closed"] is True
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == _own_time(last)


async def test_after_close_planned_entry_carries_the_close_time_adr_197():
    """ADR-197: an entry captured after hours carries ``close_at`` = the quote's own time ("Close, <time>")."""
    body, provider, _last = await _capture_at(AFTER_CLOSE)
    for entry, (iid, _action) in zip(body["entries"], CONDOR, strict=True):
        assert datetime.datetime.fromisoformat(entry["close_at"]) == provider.book.get(iid, IN_HOURS).timestamp


async def test_in_hours_planned_entry_has_no_close_time():
    body, _provider, _last = await _capture_at(IN_HOURS)
    assert body["entries"] and all(e["planned_entry"] is not None and e["close_at"] is None for e in body["entries"])


# ---- fix round 1 (Tier A finding 4): in hours an AVAILABLE quote with LTP 0 keeps its OI -----------------------------

@pytest.mark.parametrize(("at", "oi"), [(IN_HOURS, 500), (AFTER_CLOSE, None)])
def test_an_available_zero_ltp_quote_keeps_its_oi_in_hours_only(at, oi):
    """Attack 5: in hours an AVAILABLE quote with LTP 0 and OI 500 -> oi 500 (as before F-18); after hours unchanged
    (a zero last close is no price, so no OI from it)."""
    health = DataHealth.AVAILABLE if at == IN_HOURS else DataHealth.STALE
    _lp, feed = _picker(at, health)
    c = _lp.cid("22500", "CE")
    feed.ctx.provider.quotes[c] = _lp.quote(c, Instrument.CE, Decimal("22500"), "0", oi=500, health=health)
    try:
        out = leg_picker.strikes_answer(feed, "NIFTY", _lp.EXPIRY, 10, _lp.catalogue(), lambda: at)
    finally:
        leg_picker.LEASE.release()
    cell = next(x for x in _lp.cells(out) if x.instrument_id == c)
    assert (cell.ltp, cell.oi) == (None, oi)


@pytest.mark.parametrize(("at", "closed"), [(AFTER_CLOSE, True), (IN_HOURS, False)])
def test_the_drawer_carries_the_label_time_after_hours_only(at, closed):
    _lp, feed = _picker(at, DataHealth.STALE if closed else DataHealth.AVAILABLE)
    try:
        out = leg_picker.strikes_answer(feed, "NIFTY", _lp.EXPIRY, 10, _lp.catalogue(), lambda: at)
    finally:
        leg_picker.LEASE.release()
    assert out.market_closed is closed
    assert (out.last_price_at is not None) is closed


# ---- GC-BM F-19 (round 3 of the label-time class, ADR-200 (2)): before the open, every label is the session close ----
# Live 2026-10-28 07:46-07:52 IST: the banner said "Prices are from 28 Oct 2026, 07:46:17 IST" and entries "Close, 28
# Oct 2026, 07:47:44 IST": Kite's pre-open snapshot packets carry no exchange time, so ``timestamp`` is the frame's
# ARRIVAL time. Here: the real 2026-10-08 session replayed, then at Fri 2026-10-09 07:46:28 IST (before the open) every
# held contract gets a quote-mode packet (44 bytes, no exchange time) and the NIFTY index a 28-byte packet, both
# carrying the held last price - the live shape. Every label must read 08 Oct 2026, 15:30 IST.

PRE_OPEN = datetime.datetime(2026, 10, 9, 7, 46, 28, tzinfo=IST)
SESSION_CLOSE = datetime.datetime(2026, 10, 8, 15, 30, tzinfo=IST)
CHAIN_EXPIRY = datetime.date(2026, 10, 13)


def _pre_open_frame(provider) -> bytes:
    packets = []
    for iid, token in provider._token_of.items():
        held = provider.book.get(iid, IN_HOURS)
        if held is None or held.ltp is None:
            continue
        paise = int(held.ltp * 100)
        if held.instrument_type is None:  # an index: the 28-byte packet, no exchange time
            packets.append(struct.pack(">7i", token, paise, paise, paise, paise, paise, 0))
        else:  # a contract: the 44-byte quote packet, no exchange time
            packets.append(struct.pack(">11i", token, paise, 1, paise, held.volume or 0, 0, 0, paise, paise, paise,
                                       paise))
    out = len(packets).to_bytes(2, "big")
    for p in packets:
        out += len(p).to_bytes(2, "big") + p
    return out


def _pre_open():
    provider, clock, _last = _replayed()
    clock.now = PRE_OPEN
    assert provider.on_frame(_pre_open_frame(provider), PRE_OPEN)  # the snapshot lands in the book
    held = provider.book.get(CONDOR[0][0], PRE_OPEN)
    assert held.timestamp == PRE_OPEN and held.price_at == SESSION_CLOSE  # the shape the live miss had
    return provider, clock


async def test_pre_open_outcome_and_planned_entry_are_labelled_with_the_session_close():
    provider, clock = _pre_open()
    body = _condor(provider, PRE_OPEN)
    async with AsyncClient(transport=ASGITransport(app=_app(provider, clock)), base_url="http://test") as ac:
        out = (await ac.post("/api/strategies/outcome", json=body)).json()
        entries = (await ac.post("/api/strategies/planned-entry",
                                 json={"underlying": "NIFTY", "instrument_ids": [i for i, _ in CONDOR]})).json()
    assert out["market_closed"] is True
    assert datetime.datetime.fromisoformat(out["last_price_at"]) == SESSION_CLOSE
    assert entries["entries"]
    assert all(datetime.datetime.fromisoformat(e["close_at"]) == SESSION_CLOSE for e in entries["entries"])


def test_pre_open_index_and_chain_are_labelled_with_the_session_close():
    provider, clock = _pre_open()
    ctx = MarketContext(provider, clock, RATE)
    idx = index_push.indices_answer(ctx, live=True, now=clock)
    nifty = next(r for r in idx.indices if r.underlying == "NIFTY")
    assert (idx.market_closed, idx.last_price_at, nifty.at) == (True, SESSION_CLOSE, SESSION_CLOSE)
    for live in (True, False):
        chain = chain_answer(ctx, ChainRequest(underlying="NIFTY", expiry=CHAIN_EXPIRY),
                             dah._catalogue(listed()), None, live=live, now=clock)
        assert (chain.market_closed, chain.spot_at, chain.last_price_at) == (True, SESSION_CLOSE, SESSION_CLOSE)


def test_pre_open_broker_status_text_shows_the_session_close_not_the_frame_time():
    """The broker status reads the feed's last PRICE frame time (07:46:28 here); its closed text shows the close."""
    provider, _clock = _pre_open()
    assert provider.feed.last_price_at == PRE_OPEN
    status = build_status((PRE_OPEN - datetime.timedelta(hours=1), False), None, live_market.LIVE, FEED_MARKET_CLOSED,
                          market_is_open=False, last_price_at=provider.feed.last_price_at)
    assert status.live_market_closed is not None
    assert status.live_market_closed.what_happened == market_closed_error(SESSION_CLOSE).what_happened
    assert "07:46" not in status.live_market_closed.what_happened


def test_pre_open_strikes_and_depth_popup_are_labelled_with_the_session_close():
    provider, clock = _pre_open()
    feed = LiveFeed(MarketContext(provider, clock, RATE), FanOut(provider))
    try:
        out = leg_picker.strikes_answer(feed, "NIFTY", CHAIN_EXPIRY, 10, dah._catalogue(listed()), clock)
    finally:
        leg_picker.LEASE.release()
    assert (out.market_closed, out.last_price_at) == (True, SESSION_CLOSE)
    held = CONDOR[0][0]
    handle = feed.fanout.subscribe(lambda _q: None, [held], max_queue=1)
    try:
        depth = leg_picker.depth_answer(feed, held, clock)
    finally:
        feed.fanout.unsubscribe(handle)
    assert (depth.market_closed, depth.last_price_at) == (True, SESSION_CLOSE)
    assert depth.reason != "FEED_STALE"
