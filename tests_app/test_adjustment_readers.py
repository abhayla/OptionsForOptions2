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

    def unsubscribe(self, _handle):
        self.released += 1


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
