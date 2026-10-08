"""W-059 fix round 1 (Tier B review, 4 MAJOR + 4 MINOR). Class: a contract reported available while it receives no
current data (staleness, both directions), plus fan-out isolation. Counts work, not time."""
import dataclasses
import datetime

import pytest
from _kite_fixture import NIFTY_CE_ID, NIFTY_PE_ID, Clock, all_instrument_ids, new_provider, replay

from ofo.engine.legs import Instrument
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.feed_health import RECONNECT_WINDOW, FeedState
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth

SEC = datetime.timedelta(seconds=1)
T0 = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)


def _live():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    end = replay(provider, clock)
    return provider, clock, items, end


def _ltp_packet(token: int, paise: int = 10000) -> bytes:
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + paise.to_bytes(4, "big")


# 1 ------------------------------------------------------------------------------------------------------------
def test_ten_minute_outage_with_repeated_retries_goes_unavailable_and_stays():
    feed = FeedState()
    feed.on_connected(T0)
    feed.on_data(T0)
    feed.on_disconnected(T0 + SEC)
    now = T0 + SEC
    for delay in [1, 2, 4, 8, 16] + [30] * 20:  # every failed retry reports a drop again
        now += delay * SEC
        feed.on_disconnected(now)
        if now - (T0 + SEC) > RECONNECT_WINDOW:
            assert feed.health(now) is DataHealth.UNAVAILABLE
    assert now - T0 > datetime.timedelta(minutes=10)
    assert feed.health(now) is DataHealth.UNAVAILABLE


def test_failed_first_connect_stays_unavailable():
    feed = FeedState()
    feed.on_disconnected(T0)
    assert feed.health(T0) is DataHealth.UNAVAILABLE


# 2 ------------------------------------------------------------------------------------------------------------
def test_unsubscribed_contract_leaves_the_book_and_the_chain():
    provider, clock, _items, end = _live()
    expiry = datetime.date(2026, 10, 13)
    assert any(q.instrument_id == NIFTY_CE_ID for q in provider.option_chain_snapshot("NIFTY", expiry))
    provider.unsubscribe([NIFTY_CE_ID])
    for s in range(1, 4):
        clock.now = end + s * SEC
        provider.on_frame(b"\x00", clock.now)
    assert all(q.instrument_id != NIFTY_CE_ID for q in provider.option_chain_snapshot("NIFTY", expiry))
    assert provider.book.get(NIFTY_CE_ID, clock.now) is None
    assert any(q.instrument_id == NIFTY_PE_ID for q in provider.option_chain_snapshot("NIFTY", expiry))


# 3 ------------------------------------------------------------------------------------------------------------
def test_unknown_id_leaves_no_ghost_listener_and_next_subscriber_gets_a_vendor_subscription():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    with pytest.raises(KeyError):
        fan.subscribe(lambda q: None, ["NOPE:1"])
    assert fan.subscriber_count("NOPE:1") == 0
    fan.subscribe(lambda q: None, [NIFTY_CE_ID])
    assert provider.subscribed_tokens() != [] and provider.counters["vendor_subscribe"] == 1


def test_mixed_list_subscribes_nothing_and_leaves_no_state():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    with pytest.raises(KeyError):
        fan.subscribe(lambda q: None, [NIFTY_CE_ID, "NOPE:1"])
    assert provider.subscribed_tokens() == [] and provider.counters["vendor_subscribe"] == 0
    assert fan.subscriber_count(NIFTY_CE_ID) == 0
    fan.subscribe(lambda q: None, [NIFTY_CE_ID])  # the valid id still works afterwards
    assert provider.counters["vendor_subscribe"] == 1


def test_provider_that_half_applies_is_rolled_back():
    class Half:
        def __init__(self):
            self.subscribed = []
            self.unsubscribed = []

        def live_quote_stream(self, listener): ...
        def subscribe(self, ids):
            self.subscribed.append(ids[0])
            raise RuntimeError("second id failed")

        def unsubscribe(self, ids): self.unsubscribed += list(ids)

    half = Half()
    fan = FanOut(half)
    with pytest.raises(RuntimeError):
        fan.subscribe(lambda q: None, ["A:1", "B:2"])
    assert half.unsubscribed == ["A:1", "B:2"] and fan.subscriber_count("A:1") == 0


# 4 ------------------------------------------------------------------------------------------------------------
def test_subscriber_that_never_drains_does_not_delay_or_stop_others():
    provider, clock, items = new_provider()
    fan = FanOut(provider)
    ids = all_instrument_ids(items)
    fast: list = []
    fan.subscribe(fast.append, ids, max_queue=10_000)
    stuck = fan.subscribe(lambda q: None, ids, max_queue=100)  # nobody ever drains it
    replay(provider, clock)
    assert fan.pump_one(stuck, limit=0) == 0  # never drained
    fan.pump_one(1)  # only the healthy subscriber drains
    assert len(fast) == 7281  # the other subscriber got every update
    assert fan.dropped(stuck) == 7281 - 100 and fan.is_lagging(stuck) is True
    assert fan.queue_len(stuck) == 100  # bounded: drop-oldest
    assert fan.is_lagging(1) is False


def test_drop_oldest_keeps_the_newest():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    h = fan.subscribe(lambda q: None, [NIFTY_CE_ID], max_queue=2)
    from ofo.marketdata.kite_provider import NormalizedQuote  # noqa: F401
    for n in range(5):
        fan._publish(dataclasses.replace(_quote(n), instrument_id=NIFTY_CE_ID))
    assert [q.ltp for q in fan.drain(h)] == [_quote(3).ltp, _quote(4).ltp]


def _quote(n):
    from decimal import Decimal

    from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
    return NormalizedQuote(
        instrument_id="X", underlying="NIFTY", exchange="NSE", segment="INDEX", instrument_type=None, expiry=None,
        strike=None, ltp=Decimal(100 + n), bid=None, ask=None, volume=None, oi=None, oi_change=None, iv=None,
        delta=None, gamma=None, theta=None, vega=None, timestamp=T0, source=SourceMetadata("p", "f"),
        health=DataHealth.AVAILABLE)


# 5 ------------------------------------------------------------------------------------------------------------
def test_poison_packet_is_counted_and_skipped_not_raised():
    provider, clock, items = new_provider()
    poisoned = dataclasses.replace(items[0].contract, instrument_type="XX")
    bad = KiteProvider([dataclasses.replace(items[0], contract=poisoned)] + items[1:], clock=clock)
    token = int(items[0].ref("zerodha").broker_token)
    good = int(items[1].ref("zerodha").broker_token)
    bad.on_connected(T0)
    out = bad.on_frame(_ltp_packet(token), T0)  # must not raise
    assert out == [] and bad.counters["unmappable"] == 1
    assert len(bad.on_frame(_ltp_packet(good), T0)) == 1  # the next packet still flows


# 7 ------------------------------------------------------------------------------------------------------------
def test_malformed_frame_is_not_activity():
    provider, clock, _items = new_provider()
    from _kite_fixture import recorded_frames
    provider.on_connected(T0)
    provider.on_frame(next(f for _, f in recorded_frames() if len(f) > 1), T0)
    cut = (1).to_bytes(2, "big") + (44).to_bytes(2, "big") + b"\x00" * 10
    provider.on_frame(cut, T0 + 10 * SEC)
    assert provider.counters["malformed"] == 1
    assert provider.feed.health(T0 + 10 * SEC) is DataHealth.STALE  # the malformed frame did not refresh the feed
    provider.on_frame(b"\x00", T0 + 10 * SEC)
    assert provider.feed.health(T0 + 10 * SEC) is DataHealth.AVAILABLE


# 8 ------------------------------------------------------------------------------------------------------------
def test_after_reconnect_quotes_stay_stale_until_the_first_data_frame():
    """Stated rule: heartbeats do not clear it; the first data frame (a well-formed frame with a tick) does."""
    provider, clock, _items, end = _live()
    provider.on_disconnected(end)
    back = end + 20 * SEC
    provider.on_connected(back)
    assert {q.health for q in provider.book.quotes(back)} == {DataHealth.STALE}
    provider.on_frame(b"\x00", back + SEC)  # a heartbeat alone proves the link, not fresh prices
    assert {q.health for q in provider.book.quotes(back + SEC)} == {DataHealth.STALE}
    from _kite_fixture import recorded_frames
    data_frame = next(f for _, f in recorded_frames() if len(f) > 1)
    provider.on_frame(data_frame, back + 2 * SEC)
    assert {q.health for q in provider.book.quotes(back + 2 * SEC)} == {DataHealth.AVAILABLE}
