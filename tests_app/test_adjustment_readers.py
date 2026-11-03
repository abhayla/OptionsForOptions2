"""W-196 real readers on the scenario library (no database, no Kite): the market and REST spot readers answer every
source state from the SAME provider / client path the live app uses, and never a made-up 0."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import types
from decimal import Decimal as D

import pytest
from ofo.adjustment import liquidity
from ofo.adjustment.approaches import ChainRow, Position, PositionLeg, build_approach, planned_price
from ofo.adjustment.preferences import from_values
from ofo.marketdata.spot_source import SourceState
from ofo.settings import defaults
from ofo_app import adjustment_readers as readers
from ofo_app import scenario_mode
from ofo_app.routes import adjustment as route
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
    listed = [r for c in sc["market"]["chains"] for r in c["rows"] if r["listed"]]  # its expiry + the next (A-04)
    assert len(m.chain) == len(listed) and len({r.expiry for r in m.chain}) == len(sc["market"]["chains"])
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

    async def spy(provider, underlying, expiry, ids, feed, index_id=None, now=None, later=None):  # noqa: PLR0913
        seen.append(list(ids))
        return await real(provider, underlying, expiry, ids, feed, index_id, now, later)
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


# ---- GC-IC1 round 3: ONE frozen read inside the hold; nothing read after the release; the roll range held ---------

def _index_on_demand(monkeypatch, ctx):
    """The round-2 shape: nobody holds the index; it is quoted only while this read holds it."""
    spot = ctx.provider.underlying_quote("NIFTY")
    index_id = spot.instrument_id
    ctx.provider.index_id = lambda _u: index_id
    ctx.provider.underlying_quote = lambda _u: spot if index_id in ctx.provider.held else None

    async def rest(_u):
        return readers.SourceReading(SourceState.STATED, spot.ltp, ctx.clock())
    monkeypatch.setattr(readers, "read_rest_spot", rest)
    return spot, index_id


def test_gcic1_r3_no_provider_read_after_the_release(monkeypatch):
    """Attack 1: a provider that RAISES on any quote read once the hold is released; the check still answers in full."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    _index_on_demand(monkeypatch, ctx)
    p = ctx.provider
    snap, under = p.option_chain_snapshot, p.underlying_quote

    def guarded(read):
        def call(*a):
            if feed.released:
                raise AssertionError("provider read after the hold was released")
            return read(*a)
        return call
    p.option_chain_snapshot, p.underlying_quote = guarded(snap), guarded(under)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    legs = {x.tradingsymbol for x in tracked_of(sc).position.legs}
    assert feed.released == 1 and legs <= set(m.leg_greeks) and m.vol is not None and m.forward is not None
    assert m.feed.state is SourceState.STATED


def test_gcic1_r3_real_quote_book_parks_the_index_and_the_check_still_has_greeks(monkeypatch):
    """The live book itself: the index's quote lives in a real ``QuoteBook``; the release calls ``park`` on it (as
    ``kite_provider.unsubscribe`` does), after which the book answers None. The check read it before that."""
    import datetime  # noqa: PLC0415

    from ofo.marketdata.feed_health import FeedState, QuoteBook  # noqa: PLC0415
    from ofo.settings import calc, defaults  # noqa: PLC0415
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    spot = ctx.provider.underlying_quote("NIFTY")
    index_id = spot.instrument_id
    now = ctx.clock()
    state = FeedState(windows=calc.feed_windows(defaults()), market_open=lambda _t: True)
    state.on_connected(now - datetime.timedelta(seconds=1))
    state.on_data(now)
    book = QuoteBook(state)
    ctx.provider.index_id = lambda _u: index_id
    ctx.provider.underlying_quote = lambda _u: book.get(index_id, now)
    real_sub, real_unsub = feed.subscribe, feed.unsubscribe

    def sub(listener, ids, **kw):
        handle = real_sub(listener, ids, **kw)
        if index_id in ids:
            book.update(spot)
        return handle

    def unsub(handle):
        real_unsub(handle)
        if index_id in feed.subscribed[handle - 1]:
            book.park(index_id)
    feed.subscribe, feed.unsubscribe = sub, unsub

    async def rest(_u):
        return readers.SourceReading(SourceState.STATED, spot.ltp, now)
    monkeypatch.setattr(readers, "read_rest_spot", rest)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    legs = {x.tradingsymbol for x in tracked_of(sc).position.legs}
    assert book.get(index_id, now) is None and index_id in book.parked_ids()  # released and parked
    assert legs <= set(m.leg_greeks) and m.vol is not None and m.feed.value == spot.ltp


def test_gcic1_r3_roll_range_is_held_with_the_window(monkeypatch):
    """Item 3: every strike from each short to the spot and out past its wing by the roll points is in the ONE hold."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    asyncio.run(readers.read_market(tracked_of(sc), ctx))
    position = tracked_of(sc).position
    spot = ctx.provider.underlying_quote("NIFTY").ltp
    points = readers._roll_points()["NIFTY"]
    held = set(feed.subscribed[0])
    master = ctx.provider.instrument_master()
    by = {(lc.contract.instrument_type, lc.contract.strike):
          f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"
          for lc in master if lc.contract.expiry == position.legs[0].expiry and lc.contract.name == "NIFTY"}
    legs = set(readers.own_leg_ids(position, master))
    checked = 0
    for short in (x for x in position.legs if x.side == "SELL"):
        wing = next(x.strike for x in position.legs if x.side == "BUY" and x.type == short.type)
        if short.type == "CE":
            lo, hi = min(short.strike, spot), wing + points
        else:
            lo, hi = wing - points, max(short.strike, spot)
        need = {i for (t, k), i in by.items() if t == short.type and lo <= k <= hi} - legs
        assert need and need <= held, short
        checked += len(need)
    assert checked > 0 and len(feed.subscribed) == 1 and feed.released == 1


def test_gcic1_r3_second_pass_holds_once_and_releases(monkeypatch):
    """Item 4: ``read_market_more`` takes exactly one more hold with the extra ids in it, released once; it answers
    None (no hold) with nothing to hold or no feed."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    asyncio.run(readers.read_market(tracked_of(sc), ctx))
    first = set(feed.subscribed[0])
    far = next(i for i in sorted(ctx.provider.hidden) if i not in first)
    feed.subscribed.clear()
    feed.released = 0
    m = asyncio.run(readers.read_market_more(tracked_of(sc), ctx, [far]))
    assert m is not None and len(feed.subscribed) == 1 and far in feed.subscribed[0] and feed.released == 1
    assert asyncio.run(readers.read_market_more(tracked_of(sc), ctx, [])) is None
    monkeypatch.setattr(readers.live_market, "current_feed", lambda: None)
    assert asyncio.run(readers.read_market_more(tracked_of(sc), ctx, [far])) is None
    assert len(feed.subscribed) == 1


def test_gcic1_r3_second_pass_hold_released_on_an_exception(monkeypatch):
    """Attack 4: the second pass's read raises while held; the hold is still released."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    real = ctx.provider.option_chain_snapshot

    def boom(u, e):
        if feed.subscribed:
            raise RuntimeError("feed down")
        return real(u, e)
    ctx.provider.option_chain_snapshot = boom
    far = sorted(ctx.provider.hidden)[0]
    with pytest.raises(RuntimeError):
        asyncio.run(readers.read_market_more(tracked_of(sc), ctx, [far]))
    assert feed.released == 1


def test_gcic1_s3_next_expiry_read_inside_the_one_hold_with_its_own_greeks(monkeypatch):
    """ADR-239 (2) / finding live-subscription-lost-on-release-reacquire: A-04's next-expiry chain is read in the SAME
    hold as the position's expiry (its landing range held too), priced with that expiry's own model, and nothing is
    read after the release (the provider raises then). The book hides every contract of BOTH expiries until held."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    nxt = datetime.date(2026, 11, 17)
    p = ctx.provider
    p.hidden |= {q.instrument_id for q in p._inner.option_chain_snapshot("NIFTY", nxt)}
    _index_on_demand(monkeypatch, ctx)
    snap, under = p.option_chain_snapshot, p.underlying_quote

    def guarded(read):
        def call(*a):
            if feed.released:
                raise AssertionError("provider read after the hold was released")
            return read(*a)
        return call
    p.option_chain_snapshot, p.underlying_quote = guarded(snap), guarded(under)
    m = asyncio.run(readers.read_market(tracked_of(sc), ctx))
    later = {(r.type, r.strike): r for r in m.chain if r.expiry == nxt}
    assert later[("CE", D("23800"))].delta is not None and later[("CE", D("24000"))].ltp is not None
    assert len(feed.subscribed) == 1 and feed.released == 1  # one hold, one release
    current = {(r.type, r.strike): r for r in m.chain if r.expiry != nxt}
    assert later[("CE", D("23800"))].delta != current[("CE", D("23800"))].delta  # that expiry's own model
    position = tracked_of(sc).position
    built = build_approach(position, m.chain, D(sc["market"]["spot"]), "A-04", from_values(defaults()).approach)
    assert built.refusal is None and {t.expiry for t in built.trades} == {position.legs[0].expiry, nxt}


# ---- GC-IC1 round 5 (second review): the ONE second pass holds the whole delta reach of a roll -----------------------

NEAR = datetime.date(2026, 11, 9)
FAR_NEXT = datetime.date(2026, 11, 17)
WING_LANDING = D("24100")


def _reach_case(monkeypatch, target: str):
    """A book listing only the position's legs; the first hold's fixed reach ends AT the wing (roll points 0, window 2
    strikes each side), so the fit (23,900 CE) is 4 strikes past it and the wing lands on 24,100 CE. The fixture chain
    ends 400 points past the wing, so the 200-point default reach is narrowed to show the same 4-strike shortfall."""
    sc, _leg_ids, feed, ctx = _book_of_legs_only(monkeypatch)
    p = ctx.provider
    p.hidden |= {q.instrument_id for q in p._inner.option_chain_snapshot("NIFTY", FAR_NEXT)}
    ctx = dataclasses.replace(ctx, chain_strikes_each_side=2)
    monkeypatch.setattr(readers, "_roll_points", lambda: {"NIFTY": D(0), "SENSEX": D(0)})
    cfg = from_values(defaults()).approach
    cfg = dataclasses.replace(cfg, target_short_delta={k: D(target) for k in cfg.target_short_delta})
    return sc, feed, ctx, cfg


def _second_pass(sc, ctx, cfg, ids_of, approaches):  # noqa: PLR0913
    """The route's order: first read, build, the second-pass ids (``ids_of``), ONE more read, build again."""
    tracked = tracked_of(sc)
    spot = D(sc["market"]["spot"])
    first = asyncio.run(readers.read_market(tracked, ctx))
    built = [build_approach(tracked.position, first.chain, spot, a, cfg) for a in approaches]
    extra = ids_of(built, first, tracked.position, cfg)
    final = asyncio.run(readers.read_market_more(tracked, ctx, extra)) or first
    return built, extra, final, {a: build_approach(tracked.position, final.chain, spot, a, cfg) for a in approaches}


@pytest.mark.parametrize(("approach", "target", "expiry"), [("A-05", "0.08", NEAR), ("A-04", "0.25", FAR_NEXT)])
def test_gcic1_r5_delta_reach_prices_a_far_roll_after_exactly_one_second_pass(monkeypatch, approach, target, expiry):
    """Proof (brief step 1): the fan-out quotes ONLY held ids; the first read leaves the roll 'no price'; the one second
    pass holds the delta reach (to one past the fit, plus the wing landing) and the roll is priced from quotes."""
    sc, feed, ctx, cfg = _reach_case(monkeypatch, target)
    built, extra, final, after = _second_pass(sc, ctx, cfg, route.second_pass_ids, [approach])
    assert built[0].refusal is not None and "has no price" in built[0].refusal
    rows = {(r.expiry, r.type, r.strike): r for r in final.chain}
    landing = final.instrument_ids[rows[(expiry, "CE", WING_LANDING)].tradingsymbol]
    assert landing in extra and landing in feed.subscribed[1]  # the wing landing was in the ONE second hold
    assert len(feed.subscribed) == 2 and feed.released == 2  # noqa: PLR2004 - the first hold and exactly one more
    got = after[approach]
    assert got.refusal is None, got.refusal
    assert {(t.action, t.strike) for t in got.trades if t.expiry == expiry} >= {("SELL", D("23900")),
                                                                                 ("BUY", WING_LANDING)}
    for t in got.trades:  # ADR-068 (1): every price is the quote's planned price, never a model value
        assert t.price is not None and t.price == planned_price(rows[(t.expiry, t.type, t.strike)])


def test_gcic1_r5_unpriced_only_second_pass_still_has_no_price(monkeypatch):
    """Discrimination: today's second pass (the unpriced ids only) holds one strike more and A-04 stays 'no price'."""
    sc, _feed, ctx, cfg = _reach_case(monkeypatch, "0.25")
    _b, _e, _f, after = _second_pass(sc, ctx, cfg, lambda b, m, _p, _c: route.unpriced_ids(b, m), ["A-04"])
    assert after["A-04"].refusal is not None and "has no price" in after["A-04"].refusal


def test_gcic1_r5_a02_past_its_wing_refusal_unchanged_by_the_reach(monkeypatch):
    """A-02 at the same target lands at 23,900, past the 23,700 wing: still refused for THAT reason after the reach."""
    sc, _feed, ctx, cfg = _reach_case(monkeypatch, "0.08")
    _b, _e, _f, after = _second_pass(sc, ctx, cfg, route.second_pass_ids, ["A-02", "A-05"])
    assert "23,900" in after["A-02"].refusal and "23,700" in after["A-02"].refusal
    assert after["A-05"].refusal is None


def test_gcic1_r5_a05_debit_limit_refusal_unchanged_by_the_reach(monkeypatch):
    sc, _feed, ctx, cfg = _reach_case(monkeypatch, "0.08")
    tracked = tracked_of(sc)
    _b, _e, final, after = _second_pass(sc, ctx, cfg, route.second_pass_ids, ["A-05"])
    assert after["A-05"].refusal is None
    limits = liquidity.limits_from_guards({"roll_debit_limit": "Rs 1"})
    refused = build_approach(tracked.position, final.chain, D(sc["market"]["spot"]), "A-05", cfg, limits=limits,
                             max_profit=D("100000"))
    assert refused.refusal is not None and "₹1 your playbook allows" in refused.refusal


class _FakeReach:
    """|delta| 0.40 at 23,500, falling 0.05 per 50 points away from it (only the walk is under test)."""

    def __init__(self, *, flat: bool = False) -> None:
        self.flat = flat

    def delta(self, kind, strike):
        if self.flat:
            return D("0.9")
        return max(D("0.40") - abs(strike - D("23500")) / 50 * D("0.05"), D(0)) * (1 if kind == "CE" else -1)


def _grid(expiries, unlisted=()):
    rows, ids = [], {}
    for e in expiries:
        for k in range(21000, 26001, 50):
            for t in ("CE", "PE"):
                sym = f"N{e:%m%d}{k}{t}"
                rows.append(ChainRow(D(k), t, e, sym, listed=(t, k) not in unlisted))
                ids[sym] = f"NFO:{sym}"
    return rows, ids


def _strikes(out, ids, kind, expiry):
    back = {v: k for k, v in ids.items()}
    return sorted(int(back[i][5:-2]) for i in out if back[i].endswith(kind) and back[i][1:5] == f"{expiry:%m%d}")


def _ic(expiry=NEAR):
    legs = tuple(PositionLeg(s, t, D(k), expiry, 1, D(10), f"L{k}{t}") for s, t, k in
                 (("BUY", "PE", 22500), ("SELL", "PE", 22700), ("SELL", "CE", 23500), ("BUY", "CE", 23700)))
    return Position("NIFTY", 65, "weekly", expiry, legs)


def test_gcic1_r5_delta_reach_walks_to_one_past_the_fit_plus_the_wing_shift():
    rows, ids = _grid([NEAR])
    out = readers.delta_reach_ids(rows, ids, _ic(), {NEAR: _FakeReach()}, D("0.25"))
    # CE: |delta| <= 0.25 first at 23,650; one more -> 23,700; the same shifted by the 200 wing -> 23,750..23,900
    assert _strikes(out, ids, "CE", NEAR) == [23550, 23600, 23650, 23700, 23750, 23800, 23850, 23900]
    # PE: |delta| of 22,700 is 0 already (fake); one more -> 22,600; shifted by -200 -> 22,450, 22,400
    assert _strikes(out, ids, "PE", NEAR) == [22400, 22450, 22600, 22650]
    assert len(out) == len(set(out))


def test_gcic1_r5_delta_reach_is_capped_per_short():
    rows, ids = _grid([NEAR])
    out = readers.delta_reach_ids(rows, ids, _ic(), {NEAR: _FakeReach(flat=True)}, D("0.25"))  # never reaches it
    cap = readers.REACH_MAX_STRIKES
    ce = _strikes(out, ids, "CE", NEAR)
    assert [k for k in ce if k <= 23500 + 50 * cap] == list(range(23550, 23500 + 50 * cap + 1, 50))
    assert max(ce) == 23500 + 50 * cap + 200 and len(ce) == cap + 4  # the shifted copy overlaps all but 4


def test_gcic1_r5_delta_reach_covers_the_next_expiry_skips_unlisted_and_no_model():
    rows, ids = _grid([NEAR, FAR_NEXT], unlisted={("CE", 23600)})
    out = readers.delta_reach_ids(rows, ids, _ic(), {NEAR: _FakeReach(), FAR_NEXT: _FakeReach()}, D("0.25"))
    assert _strikes(out, ids, "CE", FAR_NEXT) == [23550, 23650, 23700, 23750, 23850, 23900]  # 23,600 unlisted
    assert readers.delta_reach_ids(rows, ids, _ic(), {}, D("0.25")) == []
    earlier = datetime.date(2026, 11, 3)  # an expiry before the short's own: never walked
    assert readers.delta_reach_ids(rows, ids, _ic(), {earlier: _FakeReach()}, D("0.25")) == []


def test_gcic1_r5_conservative_iv_is_the_highest():
    g = {"a": types.SimpleNamespace(iv=D("0.11")), "b": types.SimpleNamespace(iv=D("0.19")),
         "c": types.SimpleNamespace(iv=D("0.14"))}
    assert readers.conservative_iv(g) == D("0.19") and readers.conservative_iv({}) is None


def test_gcic1_r5_second_pass_ids_answer_states():
    rows, ids = _grid([NEAR])
    cfg = from_values(defaults()).approach
    market = route.MarketInputs(tuple(rows), ids, None, None, None, None, None,
                                datetime.datetime(2026, 11, 9, 10, 0, tzinfo=datetime.UTC), reach={NEAR: _FakeReach()})
    priced = types.SimpleNamespace(unpriced=(), refusal_message=None, after=())
    assert route.second_pass_ids([priced], market, _ic(), cfg) == []  # nothing unpriced: no second pass at all
    gap = types.SimpleNamespace(unpriced=((NEAR, "CE", D("23750")),), refusal_message=object(), after=())
    with_reach = route.second_pass_ids([gap], market, _ic(), cfg)
    assert with_reach[0] == ids[f"N{NEAR:%m%d}23750CE"] and len(with_reach) > 1
    no_model = dataclasses.replace(market, reach={})
    assert route.second_pass_ids([gap], no_model, _ic(), cfg) == [ids[f"N{NEAR:%m%d}23750CE"]]
