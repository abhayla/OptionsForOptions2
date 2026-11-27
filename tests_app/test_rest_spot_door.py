"""Lane U hotfix A (REQ-118, REQ-133, ADR-330 (39)): the REST index quote is a FALLBACK behind the tick store.
No database. Class: "a page poll calls the vendor REST before the tick store"; "a request's release parks a shared
subscription". Counters: REST reads per N requests, vendor unsubscribes per request, REST calls from the worker."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.shared_reading import SharedReading
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import live_market, live_push, paper_monitor
from ofo_app.kite_reads import BUSY_CODE, KiteReadError
from ofo_app.routes import outcome
from test_index_live import FakeProvider

BACKEND = Path(__file__).resolve().parents[1] / "backend" / "ofo_app"
NOW = datetime.datetime(2026, 11, 27, 5, 0, tzinfo=datetime.UTC)  # Friday 10:30 IST
INDEX, LEG = "NSE_INDEX:1001", "NFO:5001"
TWO = 2


def _market(feed: SourceReading | None):
    return SimpleNamespace(feed_at=lambda _judged: feed, last_close=None)


def _fresh_feed():
    return SourceReading(SourceState.STATED, Decimal("23000"), outcome.server_now())


class _Reader:
    def __init__(self):
        self.calls = 0

    async def __call__(self, _underlying):
        self.calls += 1
        return SourceReading(SourceState.STATED, Decimal("23001"), outcome.server_now())


@pytest.mark.anyio
async def test_twelve_plan_watch_requests_with_a_fresh_tick_make_zero_rest_calls():
    reader = _Reader()
    for _ in range(12):
        assert await outcome.rest_spot_if_needed(_market(_fresh_feed()), reader, "NIFTY", None) is None
    assert reader.calls == 0


@pytest.mark.anyio
async def test_no_tick_asks_rest_only_then():
    reader = _Reader()
    assert (await outcome.rest_spot_if_needed(_market(None), reader, "NIFTY", None)).state is SourceState.STATED
    assert reader.calls == 1


class _Reads:
    def __init__(self, outcome_):
        self.outcome, self.calls = outcome_, 0

    def fetch_index_quote(self, _name):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return {"last_price": 23000, "timestamp": "2026-11-27 10:30:00"}


def _door(monkeypatch, reads, clock):
    monkeypatch.setattr(live_market, "REST_SPOT", SharedReading(clock=clock))

    async def owner():
        return "key", reads
    monkeypatch.setattr(live_market, "owner_kite_reads", owner)


@pytest.mark.anyio
async def test_index_absent_twelve_requests_inside_the_ttl_make_one_rest_call(monkeypatch):
    reads = _Reads(None)
    _door(monkeypatch, reads, lambda: 50.0)
    for _ in range(12):
        assert (await live_market.index_spot("NIFTY 50")).state is SourceState.STATED
    assert reads.calls == 1


@pytest.mark.anyio
async def test_a_429_inside_the_cooldown_sends_no_call_and_leaves_leg_quotes_alone(monkeypatch):
    reads = _Reads(KiteReadError(BUSY_CODE))
    now = [50.0]
    _door(monkeypatch, reads, lambda: now[0])
    provider = FakeProvider({"NIFTY": INDEX})
    fan = FanOut(provider)
    fan.subscribe(lambda _q: None, [LEG, INDEX])
    for _ in range(12):
        assert (await live_market.index_spot("NIFTY 50")).state is SourceState.FAILED
    assert reads.calls == 1  # the failure is kept for the cooldown: nothing sent inside it
    assert provider.vendor_subscribed == {LEG, INDEX}  # a REST failure never touches a leg's subscription / health
    now[0] += 10.5
    await live_market.index_spot("NIFTY 50")
    assert reads.calls == TWO


def test_a_requests_release_never_parks_a_leg_the_monitor_holds():
    provider = FakeProvider({"NIFTY": INDEX})
    feed = SimpleNamespace(fanout=FanOut(provider), ctx=SimpleNamespace(provider=provider))
    # control: with no standing hold the request's own release unsubscribes the vendor (the live defect)
    handle = feed.fanout.subscribe(live_push.no_listener, [LEG, INDEX])
    feed.fanout.unsubscribe(handle)
    assert provider.vendor_subscribed == set()
    monitor = paper_monitor.PaperMonitor.__new__(paper_monitor.PaperMonitor)
    monitor._standing_feed, monitor._standing = None, []
    monitor._hold_open_legs(feed, [LEG, INDEX])
    for _ in range(12):  # twelve 5 s polls, each a hold then a release of its own reference
        request = feed.fanout.subscribe(live_push.no_listener, [LEG, INDEX], max_queue=1)
        feed.fanout.unsubscribe(request)
        assert provider.vendor_subscribed == {LEG, INDEX}
    monitor._hold_open_legs(None, [])  # the strategy closes: the hold is released
    assert provider.vendor_subscribed == set()


def test_the_standing_hold_skips_an_id_the_feed_cannot_hold_without_dropping_the_rest():
    class Picky(FakeProvider):
        def subscribe(self, ids):
            if "NFO:GONE" in ids:
                raise KeyError("no token")
            super().subscribe(ids)
    provider = Picky({"NIFTY": INDEX})
    feed = SimpleNamespace(fanout=FanOut(provider), ctx=SimpleNamespace(provider=provider))
    monitor = paper_monitor.PaperMonitor.__new__(paper_monitor.PaperMonitor)
    monitor._standing_feed, monitor._standing = None, []
    monitor._hold_open_legs(feed, ["NFO:GONE", LEG, INDEX])
    assert provider.vendor_subscribed == {LEG, INDEX}
