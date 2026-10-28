"""Finding live-read-without-own-subscription (#583): a request that needs the NIFTY index takes its own hold on it.

Production shape, no seeding: a REAL ``FanOut`` over a provider whose index quote exists ONLY while the index is
subscribed on the vendor (the real book's rule, ADR-077). No other screen holds the index. Neither the chain reader's
answer nor the provider's quote is handed over by the test; the route must subscribe the index itself.

Index answer states and what each does (ready-made routes): present+usable -> strikes placed; present+stale ->
SPOT_STALE (503, no wait: a quote that arrived is not waited for); absent after the bounded wait -> SPOT_MISSING;
provider error on subscribe / unknown instrument (lease holds nothing) -> SPOT_MISSING at once, no wait; no feed ->
the old path (SPOT_MISSING when the context holds no quote).
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
from decimal import Decimal

import pytest
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.live_push import LiveFeed
from ofo_app.routes import chain, leg_picker, outcome, ready_made
from ofo_app.routes.outcome import MarketContext
from starlette.testclient import TestClient
from test_leg_picker_routes import EXPIRY, contracts_for
from test_ready_made_route import LOAD, NEAR, NIFTY_ID, PICK, Reader

HTTP_OK, HTTP_UNAVAILABLE = 200, 503
LEASE_SECONDS, WAIT_BOUND, THREE_POLLS, TWO_READS = 30.0, 3.0, 3, 2
T0 = datetime.datetime(2026, 10, 27, 9, 23, 37, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


class HeldOnlyProvider:
    """A quote exists only while the instrument is subscribed (and, optionally, only after N further reads)."""

    def __init__(self, *, ltp="22810", health=DataHealth.AVAILABLE, polls_before_quote=0, unknown=False) -> None:
        self.vendor_subscribed: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.reads = 0
        self.polls_before_quote, self.unknown = polls_before_quote, unknown
        self.quote = NormalizedQuote(NIFTY_ID, "NIFTY", "NSE", "INDICES", None, None, None, Decimal(ltp), None, None,
                                     None, None, None, None, None, None, None, None, T0,
                                     SourceMetadata("fake", "fake-feed"), health)

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        if self.unknown:
            raise KeyError("unknown")
        self.subscribe_calls.append(list(ids))
        self.vendor_subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.vendor_subscribed.difference_update(ids)

    def index_id(self, underlying):
        return NIFTY_ID if underlying == "NIFTY" else None

    def underlying_quote(self, underlying):
        if NIFTY_ID not in self.vendor_subscribed:
            return None
        self.reads += 1
        return self.quote if self.reads > self.polls_before_quote else None

    def instrument_master(self) -> list:  # GC-UI F-3: the futures lease reads it for the forward strikes
        return []

    def option_chain_snapshot(self, underlying, expiry):
        return []

    def futures_quote(self, underlying, expiry):
        return None


def _feed(provider: HeldOnlyProvider) -> LiveFeed:
    return LiveFeed(MarketContext(provider, lambda: T0, Decimal("0.065")), FanOut(provider))


def _client(monkeypatch, tmp_path, feed: LiveFeed | None):
    from ofo_app.main import create_app  # noqa: PLC0415

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    app = create_app()
    reader = Reader()
    app.dependency_overrides[outcome.get_market_context] = lambda: None if feed is None else feed.ctx
    app.dependency_overrides[leg_picker.get_feed] = lambda: feed
    app.dependency_overrides[chain.get_chain_reader] = lambda: reader
    return TestClient(app)


@pytest.fixture(autouse=True)
def _release():
    yield
    ready_made.INDEX_LEASE.release()
    leg_picker.LEASE.release()
    leg_picker.FUTURES_LEASE.release()


BODY = {"underlying": "NIFTY", "template_id": "bull_call_spread", "expiry": NEAR.isoformat()}
PICK_BODY = {"underlying": "NIFTY", "kind": "straddle", "distance": 0, "side": "BUY", "expiry": NEAR.isoformat()}


def test_core_load_template_and_quick_pick_subscribe_the_index_themselves(monkeypatch, tmp_path):
    """Core / attack 1: nobody else holds the index; the empty builder's load-template places strikes."""
    provider = HeldOnlyProvider()
    feed = _feed(provider)
    client = _client(monkeypatch, tmp_path, feed)
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0
    r = client.post(LOAD, json=BODY)
    assert r.status_code == HTTP_OK, r.text
    assert feed.fanout.subscriber_count(NIFTY_ID) == 1 and NIFTY_ID in provider.vendor_subscribed
    q = client.post(PICK, json=PICK_BODY)
    assert q.status_code == HTTP_OK, q.text
    assert feed.fanout.subscriber_count(NIFTY_ID) == 1  # the same request again reuses its hold (no growth)
    assert len(provider.subscribe_calls) == 1


def test_the_hold_ends_when_its_lease_ends_and_never_leaks(monkeypatch, tmp_path):
    """Attack 2: the hold is a WindowLease (30 s, ADR-077): releasing it (what its timer does) frees the index."""
    provider = HeldOnlyProvider()
    feed = _feed(provider)
    client = _client(monkeypatch, tmp_path, feed)
    assert client.post(LOAD, json=BODY).status_code == HTTP_OK
    assert ready_made.INDEX_LEASE.held_ids == {NIFTY_ID}
    assert leg_picker.LEASE_SECONDS == LEASE_SECONDS
    ready_made.INDEX_LEASE.release()
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0 and NIFTY_ID not in provider.vendor_subscribed


def test_the_lease_timer_is_armed_for_the_pickers_window(monkeypatch, tmp_path):
    """Attack 2 (timer): the hold's end is scheduled LEASE_SECONDS after the read, on the running loop."""
    provider = HeldOnlyProvider()
    feed = _feed(provider)
    seen: list[float] = []

    async def go():
        loop = asyncio.get_running_loop()
        real = loop.call_later
        loop.call_later = lambda delay, cb, *a: seen.append(delay) or real(delay, cb, *a)
        try:
            await ready_made._hold_and_read(feed, feed.ctx, "NIFTY", "owner")
        finally:
            loop.call_later = real

    asyncio.run(go())
    assert seen == [leg_picker.LEASE_SECONDS]


def test_a_stale_index_quote_still_refuses_with_the_spot_message_and_does_not_wait(monkeypatch, tmp_path):
    """Attack 3: present+stale -> refused at once (a quote that arrived is not waited for)."""
    provider = HeldOnlyProvider(health=DataHealth.UNHEALTHY)
    client = _client(monkeypatch, tmp_path, _feed(provider))
    r = client.post(LOAD, json=BODY)
    assert r.status_code == HTTP_UNAVAILABLE and "missing or out of date" in r.text and "legs" not in r.text
    assert provider.reads == TWO_READS  # one spot read (value + health), no polling


def test_the_first_read_null_is_waited_for_within_the_bound(monkeypatch, tmp_path):
    """The first frame arrives after a few polls: the route polls (no busy loop), then places strikes."""
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(delay):
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(ready_made.asyncio, "sleep", sleep)
    provider = HeldOnlyProvider(polls_before_quote=3)
    client = _client(monkeypatch, tmp_path, _feed(provider))
    r = client.post(LOAD, json=BODY)
    assert r.status_code == HTTP_OK, r.text
    assert len(sleeps) == THREE_POLLS and all(s > 0 for s in sleeps)


def test_an_index_that_never_arrives_is_refused_after_the_bounded_wait(monkeypatch, tmp_path):
    """Absent after the wait -> SPOT_MISSING; the wait is bounded (<= 3 s of polling, a sleep between polls)."""
    assert ready_made.SPOT_WAIT_SECONDS <= WAIT_BOUND
    clock = {"t": 0.0}
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(delay):
        sleeps.append(delay)
        clock["t"] += delay
        await real_sleep(0)

    monkeypatch.setattr(ready_made.asyncio, "sleep", sleep)
    monkeypatch.setattr(ready_made, "_now", lambda: clock["t"])
    provider = HeldOnlyProvider(polls_before_quote=10**9)
    client = _client(monkeypatch, tmp_path, _feed(provider))
    r = client.post(LOAD, json=BODY)
    assert r.status_code == HTTP_UNAVAILABLE and "missing or out of date" in r.text
    assert sleeps and sum(sleeps) <= ready_made.SPOT_WAIT_SECONDS + ready_made.SPOT_POLL_SECONDS
    assert len(sleeps) <= int(ready_made.SPOT_WAIT_SECONDS / ready_made.SPOT_POLL_SECONDS) + 1


def test_a_lease_the_provider_refuses_is_refused_at_once_without_a_wait(monkeypatch, tmp_path):
    """Unknown instrument / provider error on subscribe: the lease holds nothing -> SPOT_MISSING, zero sleeps."""
    slept: list[float] = []

    async def sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(ready_made.asyncio, "sleep", sleep)
    client = _client(monkeypatch, tmp_path, _feed(HeldOnlyProvider(unknown=True)))
    r = client.post(LOAD, json=BODY)
    assert r.status_code == HTTP_UNAVAILABLE and slept == []


def test_futures_read_holds_the_index_so_spot_and_forwards_come_back_from_the_second_read(monkeypatch, tmp_path):
    """Attack 4: no strikes window open; the futures lease includes the index, the second read has spot + forwards."""
    from ofo_app.routes.leg_picker import FuturesCatalogue, futures_answer  # noqa: PLC0415

    provider = HeldOnlyProvider()
    feed = _feed(provider)
    fut = dataclasses.replace(contracts_for([Decimal(1)], expiry=datetime.date(2026, 11, 24), base=70000)[0],
                              instrument_type="FUT", strike=None)
    cat = FuturesCatalogue(option_expiries=(EXPIRY,), futures=(fut,))
    first = futures_answer(feed, "NIFTY", cat, lambda: T0)
    second = futures_answer(feed, "NIFTY", cat, lambda: T0)
    assert NIFTY_ID in provider.vendor_subscribed and feed.fanout.subscriber_count(NIFTY_ID) == 1
    assert first.spot is not None or second.spot is not None
    assert second.spot == Decimal("22810.00") and second.reason is None
    assert second.forwards[0].reason != "SPOT_MISSING"
