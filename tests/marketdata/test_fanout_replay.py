"""REQ-048 AC-4: provider streams are shared and fanned out internally; no vendor subscription per user.

Replays the real recording to 1,000 subscribers. Counts work, not time."""
from _kite_fixture import NIFTY_CE_ID, all_instrument_ids, new_provider, replay

from ofo.marketdata.fanout import FanOut

SUBSCRIBERS = 1000


def test_1000_subscribers_share_one_vendor_subscription_per_instrument():
    provider, clock, items = new_provider()
    fan = FanOut(provider)
    ids = all_instrument_ids(items)
    inboxes = [[] for _ in range(SUBSCRIBERS)]
    for inbox in inboxes:
        fan.subscribe(inbox.append, ids)

    assert provider.counters["vendor_subscribe"] == len(ids) == 1090  # 1 per instrument, not 1,000 per instrument (INDIA VIX left out, W-060)
    assert len(provider.subscribed_tokens()) == 1090
    replay(provider, clock)
    fan.pump()

    first = inboxes[0]
    assert len(first) == 7281  # every tick of the recording reached the subscriber
    assert all(inbox == first for inbox in inboxes)  # same updates, same order, for all 1,000
    assert fan.listener_errors == 0
    assert fan.subscriber_count(NIFTY_CE_ID) == SUBSCRIBERS


def test_last_unsubscribe_releases_the_vendor_subscription_and_a_bad_subscriber_is_isolated():
    provider, clock, items = new_provider()
    fan = FanOut(provider)
    good = []

    def bad(_quote):
        raise RuntimeError("subscriber bug")

    h_bad = fan.subscribe(bad, [NIFTY_CE_ID])
    h_good = fan.subscribe(good.append, [NIFTY_CE_ID])
    assert provider.counters["vendor_subscribe"] == 1
    replay(provider, clock)
    fan.pump()
    assert good and fan.listener_errors == len(good)  # the bad one failed every time, the good one got every update
    fan.unsubscribe(h_bad)
    assert len(provider.subscribed_tokens()) == 1  # still one subscriber left
    fan.unsubscribe(h_good)
    assert provider.subscribed_tokens() == []
    added, removed = provider.drain_subscription_changes()
    assert len(added) == 1 and removed == added
