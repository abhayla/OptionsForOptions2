"""W-196 real readers on the scenario library (no database, no Kite): the market and REST spot readers answer every
source state from the SAME provider / client path the live app uses, and never a made-up 0."""
from __future__ import annotations

import asyncio
import types
from decimal import Decimal as D

import pytest
from ofo.marketdata.spot_source import SourceState
from ofo_app import adjustment_readers as readers
from ofo_app import scenario_mode
from ofo_app.routes import outcome
from test_adjustment_approaches_route import load, tracked_of


def _scn(monkeypatch, sid: str):
    scn = scenario_mode.load(sid)
    monkeypatch.setattr(readers, "_scenario", lambda: scn)
    return scn, outcome.MarketContext(scn.provider, scn.clock, scn.rate)


def test_index_names_come_from_the_one_home():
    assert (readers.index_name("NIFTY"), readers.index_name("SENSEX"), readers.index_name("X")) == (
        "NSE:NIFTY 50", "BSE:SENSEX", None)


def test_market_reader_gives_chain_deltas_pop_inputs_and_the_feed_spot(monkeypatch):
    sc = load("ADJ-02")
    scn, ctx = _scn(monkeypatch, "ADJ-02")
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    listed = [r for c in sc["market"]["chains"] if c["expiry"] == sc["expiry"] for r in c["rows"] if r["listed"]]
    assert len(m.chain) == len(listed)
    assert all(r.delta is not None for r in m.chain if r.ltp is not None)
    assert m.forward is not None and m.years is not None and m.vol is not None
    assert m.feed.state is SourceState.STATED and m.feed.value == D(sc["market"]["spot"])
    assert m.expiry_kind == sc["expiry_kind"] and m.now == scn.clock()
    assert all(r.ltp is None or r.ltp > 0 for r in m.chain)  # an unpriced row stays None, never 0


def test_market_reader_without_a_context_is_absent_never_zero():
    m = asyncio.run(readers.read_market(tracked_of(load("ADJ-02")), None))
    assert m.chain == () and m.feed.state is SourceState.ABSENT and m.forward is None


@pytest.mark.parametrize(("sid", "state"), [("ADJ-24a", SourceState.STATED), ("ADJ-24b", SourceState.FAILED)])
def test_rest_spot_reader_answers_through_the_door_in_scenario_mode(monkeypatch, sid, state):
    sc = load(sid)
    _scn(monkeypatch, sid)
    r = asyncio.run(readers.read_rest_spot(sc["underlying"]))
    assert r.state is state
    if state is SourceState.STATED:
        assert r.value == D(sc["market"]["spot"]) and r.at is not None


def test_rest_spot_reader_unknown_underlying_is_not_found(monkeypatch):
    monkeypatch.setattr(readers, "_scenario", lambda: None)
    assert asyncio.run(readers.read_rest_spot("BANKNIFTY")).state is SourceState.NOT_FOUND


# ---- last close (ADR-212) ---------------------------------------------------------------------------------------
def test_last_close_scenario_stated_is_dated_to_the_session_before(monkeypatch):
    sid = "ADJ-04"  # states a previous close (gap scenarios)
    sc = load(sid)
    scn, ctx = _scn(monkeypatch, sid)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert m.last_close.state is SourceState.STATED and m.last_close.value == D(str(sc["market"]["prev_close"]))
    assert m.last_close.at < scn.clock() and m.last_close.at.weekday() < 5  # noqa: PLR2004


def test_last_close_scenario_null_is_absent(monkeypatch):
    sc = load("ADJ-02")
    assert sc["market"]["prev_close"] is None
    _, ctx = _scn(monkeypatch, "ADJ-02")
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert m.last_close.state is SourceState.ABSENT


def test_last_close_live_absent_when_nothing_held_or_market_open():
    import datetime  # noqa: PLC0415
    now = datetime.datetime(2026, 10, 30, 10, 0, tzinfo=datetime.UTC)
    assert readers.read_last_close(None, True, None, now).state is SourceState.ABSENT
    assert readers.read_last_close(object(), False, None, now).state is SourceState.ABSENT


def test_last_close_live_held_quote_is_stated_with_its_time(monkeypatch):
    import datetime  # noqa: PLC0415
    now = datetime.datetime(2026, 10, 30, 20, 0, tzinfo=datetime.UTC)
    q = type("Q", (), {"ltp": D("23420.5"), "timestamp": now})()
    monkeypatch.setattr(readers, "planning_price_usable", lambda quote, *, market_closed: True)
    r = readers.read_last_close(q, True, None, now)
    assert r.state is SourceState.STATED and r.value == D("23420.5") and r.at == now
    monkeypatch.setattr(readers, "planning_price_usable", lambda quote, *, market_closed: False)
    assert readers.read_last_close(q, True, None, now).state is SourceState.ABSENT


# ---- GC-MU A5: adjustments used from the engine's adjustment history -----------------------------------------------

def _stored(cid, side, qty, price, kind, at):  # noqa: PLR0913 - one field each
    import types  # noqa: PLC0415
    return types.SimpleNamespace(order=types.SimpleNamespace(contract_id=cid, side=side, quantity=qty, price=D(price),
                                                             kind=kind, placed_at=at))


def test_history_count_gives_the_number_zero_and_none():
    import datetime  # noqa: PLC0415
    t0 = datetime.datetime(2026, 10, 28, 10, 0, tzinfo=datetime.UTC)
    t1 = t0 + datetime.timedelta(days=1)
    entry = [_stored(1, "SELL", 130, "20", "open", t0), _stored(2, "BUY", 130, "5", "open", t0)]
    always = lambda _cid: True  # noqa: E731
    # no adjustment yet -> 0
    assert readers.history_count(entry, always) == 0
    # one adjustment (an exit and a new open at a later time) -> 1
    adjusted = [*entry, _stored(1, "BUY", 130, "10", "exit", t1), _stored(3, "SELL", 130, "18", "open", t1)]
    assert readers.history_count(adjusted, always) == 1
    # the history cannot be read (no orders; a bad value) -> None, never 0
    assert readers.history_count([], always) is None
    bad = [*entry, _stored(1, "BUY", 130, "-1", "exit", t1)]
    assert readers.history_count(bad, always) is None


# ---- F-92: the Compare prices every leg the paper book prices (holds the position's own unheld legs) ----------

class _HidingProvider:
    """The scenario provider, except the chain snapshot omits ``hidden`` ids until a hold on them exists, as the live
    book omits a contract nobody holds (``QuoteBook.quotes`` lists held entries only)."""

    def __init__(self, inner, hidden: set[str], held: set[str]) -> None:
        self._inner, self.hidden, self.held = inner, hidden, held

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def option_chain_snapshot(self, underlying, expiry):
        return [q for q in self._inner.option_chain_snapshot(underlying, expiry)
                if q.instrument_id not in self.hidden or q.instrument_id in self.held]


class _FakeFanout:
    def __init__(self, provider, *, unknown: bool = False, gives_quote: bool = True) -> None:
        self.provider, self.unknown, self.gives_quote = provider, unknown, gives_quote
        self.subscribed: list[list[str]] = []
        self.released = 0

    def subscribe(self, _listener, ids, **_kw):
        if self.unknown:
            raise KeyError(ids)
        self.subscribed.append(list(ids))
        if self.gives_quote:
            self.provider.held |= set(ids)
        return len(self.subscribed)

    def unsubscribe(self, handle):
        """As the live book: a released contract is parked (``QuoteBook.park``), its quote gone from the snapshot."""
        self.released += 1
        self.provider.held -= set(self.subscribed[handle - 1])


def _hedge_case(monkeypatch, **fan):
    sc = load("ADJ-02")
    scn, _ = _scn(monkeypatch, "ADJ-02")
    hedge = next(x for x in sc["position"]["legs"] if x["side"] == "BUY" and x["type"] == "PE")
    iid = next(f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in scn.provider.instrument_master()
               if lc.broker_refs[0].broker_symbol == hedge["tradingsymbol"])
    provider = _HidingProvider(scn.provider, {iid}, set())
    feed = _FakeFanout(provider, **fan)
    monkeypatch.setattr(readers.live_market, "current_feed", lambda: types.SimpleNamespace(fanout=feed))
    monkeypatch.setattr(readers, "LEG_WAIT_S", 0.3)
    ctx = outcome.MarketContext(provider, scn.clock, scn.rate)
    return sc, hedge, iid, feed, ctx


def _row(m, symbol):
    return next(r for r in m.chain if r.tradingsymbol == symbol)


def test_f92_unheld_hedge_leg_is_held_and_priced_then_released(monkeypatch):
    """Answer state 'not held yet': the leg nobody holds is held for the read, gets its price, the hold is released."""
    sc, hedge, iid, feed, ctx = _hedge_case(monkeypatch)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert _row(m, hedge["tradingsymbol"]).ltp is not None and m.instrument_ids[hedge["tradingsymbol"]] == iid
    assert feed.subscribed == [[iid]] and feed.released == 1  # only the missing leg, released exactly once


def test_f92_leg_that_never_ticks_stays_unpriced_never_zero(monkeypatch):
    """Answer states 'no price' / 'market closed' (a hold that brings no quote): the row stays None, hold released."""
    sc, hedge, _iid, feed, ctx = _hedge_case(monkeypatch, gives_quote=False)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert _row(m, hedge["tradingsymbol"]).ltp is None and _row(m, hedge["tradingsymbol"]).bid is None
    assert feed.released == 1


def test_f92_leg_the_feed_has_no_token_for_stays_unpriced(monkeypatch):
    sc, hedge, _iid, feed, ctx = _hedge_case(monkeypatch, unknown=True)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert _row(m, hedge["tradingsymbol"]).ltp is None and feed.released == 0


def test_f92_no_live_feed_reads_the_book_as_it_is(monkeypatch):
    sc, hedge, _iid, feed, ctx = _hedge_case(monkeypatch)
    monkeypatch.setattr(readers.live_market, "current_feed", lambda: None)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert _row(m, hedge["tradingsymbol"]).ltp is None and feed.subscribed == []


def test_f92_legs_already_held_take_no_hold(monkeypatch):
    sc, _hedge, iid, feed, ctx = _hedge_case(monkeypatch)
    ctx.provider.held.add(iid)
    asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert feed.subscribed == [] and feed.released == 0


# ---- GC-IC1: the screen check holds the near-the-money window (Greeks and ATM IV with no chain screen open) ----

FOUR_LEGS = 4


def _book_of_legs_only(monkeypatch, **fan):
    """The live book lists only the position's 4 legs until a hold on other ids exists (no chain screen is open)."""
    sc = load("ADJ-02")
    scn, _ = _scn(monkeypatch, "ADJ-02")
    position = tracked_of(sc).position
    leg_symbols = {x.tradingsymbol for x in position.legs}
    everything = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}":
                  lc.broker_refs[0].broker_symbol for lc in scn.provider.instrument_master()}
    leg_ids = {i for i, sym in everything.items() if sym in leg_symbols}
    snapshot = scn.provider.option_chain_snapshot(position.underlying, position.legs[0].expiry)
    all_ids = {q.instrument_id for q in snapshot}
    provider = _HidingProvider(scn.provider, all_ids - leg_ids, set())
    feed = _FakeFanout(provider, **fan)
    monkeypatch.setattr(readers.live_market, "current_feed", lambda: types.SimpleNamespace(fanout=feed))
    monkeypatch.setattr(readers, "LEG_WAIT_S", 0.3)
    return sc, leg_ids, feed, outcome.MarketContext(provider, scn.clock, scn.rate)


def test_gcic1_check_holds_the_window_so_legs_have_greeks_and_the_vol_is_stated(monkeypatch):
    sc, leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    legs = {x.tradingsymbol for x in tracked_of(sc).position.legs}
    assert len(legs) == FOUR_LEGS and legs <= set(m.leg_greeks) and m.vol is not None and m.forward is not None
    assert feed.released == 1 and feed.subscribed and set(feed.subscribed[0]) - leg_ids  # window ids asked, one release


def test_gcic1_read_market_asks_held_read_for_the_window_ids(monkeypatch):
    sc, leg_ids, _feed, ctx = _book_of_legs_only(monkeypatch)
    seen = []
    real = readers.held_read

    async def spy(provider, underlying, expiry, ids, feed, index_id=None):  # noqa: PLR0913
        seen.append(list(ids))
        return await real(provider, underlying, expiry, ids, feed, index_id)
    monkeypatch.setattr(readers, "held_read", spy)
    asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert leg_ids <= set(seen[0]) and len(set(seen[0]) - leg_ids) >= ctx.chain_strikes_each_side  # legs plus window


def test_gcic1_no_spot_means_no_window_legs_only_no_crash(monkeypatch):
    sc, _ids, feed, ctx = _book_of_legs_only(monkeypatch)
    ctx.provider.underlying_quote = lambda _u: None

    async def no_rest(_u):
        return readers.SourceReading(SourceState.ABSENT)
    monkeypatch.setattr(readers, "read_rest_spot", no_rest)
    monkeypatch.setattr(readers, "read_last_close", lambda *_a: readers.SourceReading(SourceState.ABSENT))
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    # the legs are in the book already; no spot -> no window and no inward roll range: the index and the outward
    # roll range (past each wing) only, in ONE hold released once
    legs = tracked_of(sc).position.legs
    shorts = sorted(x.strike for x in legs if x.side == "SELL")
    strike_of = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}": lc.contract.strike
                 for lc in ctx.provider.instrument_master()}
    held = feed.subscribed[0]
    assert m.vol is None and len(feed.subscribed) == 1 and feed.released == 1 and "NSE_INDEX:1001" in held
    assert all(not shorts[0] <= strike_of[i] <= shorts[1] for i in held if i != "NSE_INDEX:1001")


def test_gcic1_window_released_when_the_provider_raises(monkeypatch):
    sc, _ids, feed, ctx = _book_of_legs_only(monkeypatch)
    real = ctx.provider.option_chain_snapshot

    def boom(u, e):
        if feed.subscribed:
            raise RuntimeError("feed down")
        return real(u, e)
    ctx.provider.option_chain_snapshot = boom
    with pytest.raises(RuntimeError):
        asyncio.run(readers.read_market(tracked_of(sc), ctx))
    assert feed.released == 1


def test_gcic1_window_ids_skip_strikes_without_a_contract_and_unlisted_expiry():
    import datetime
    ns = types.SimpleNamespace
    expiry = datetime.date(2026, 11, 26)

    def lc(strike, typ, tok):
        return ns(contract=ns(name="NIFTY", expiry=expiry, strike=D(strike), instrument_type=typ,
                              exchange_segment="NFO", exchange_token=str(tok)))
    listed = [lc(100, "CE", 1), lc(100, "PE", 2), lc(200, "CE", 3), lc(300, "CE", 4), lc(300, "PE", 5)]
    spot = D(200)
    assert readers.window_ids(listed, "NIFTY", expiry, spot, 1) == ["NFO:1", "NFO:2", "NFO:3", "NFO:4", "NFO:5"]
    assert readers.window_ids(listed, "NIFTY", datetime.date(2027, 1, 1), spot, 1) == []
    assert readers.window_ids(listed, "NIFTY", expiry, None, 1) == []


def test_gcic1_no_index_quote_on_the_feed_the_window_is_centred_on_the_rest_spot(monkeypatch):
    """Round 2: nobody holds the index on the feed (only a strategy open); REST centres the window."""
    sc, leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    spot = ctx.provider.underlying_quote("NIFTY")
    index_id = spot.instrument_id
    ctx.provider.index_id = lambda _u: index_id
    ctx.provider.underlying_quote = lambda _u: spot if index_id in ctx.provider.held else None  # held on demand only
    asked = []

    async def rest(u):
        asked.append(u)
        return readers.SourceReading(SourceState.STATED, spot.ltp, ctx.clock())
    monkeypatch.setattr(readers, "read_rest_spot", rest)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    legs = {x.tradingsymbol for x in tracked_of(sc).position.legs}
    assert asked == ["NIFTY"] and feed.subscribed and set(feed.subscribed[0]) - leg_ids
    assert index_id in feed.subscribed[0]
    assert legs <= set(m.leg_greeks) and m.vol is not None
