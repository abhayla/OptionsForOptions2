"""W-196 real readers on the scenario library (no database, no Kite): the market and REST spot readers answer every
source state from the SAME provider / client path the live app uses, and never a made-up 0."""
from __future__ import annotations

import asyncio
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
