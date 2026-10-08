"""W-062 AC-5 (REQ-051): a failing history store never disturbs the live feed; the recorder adds no subscription."""
import datetime

from _history_fixture import replay_window
from test_minute_bars_replay import NIFTY_CE

from ofo.history.recorder import Recorder
from ofo.history.store import InMemoryHistoryStore

W = "1506-1512"


class RaisingStore:
    def __init__(self):
        self.calls = 0

    def put_bars(self, bars):
        self.calls += 1
        raise RuntimeError("secret-looking-value 123.45")

    def bars_for_day(self, day):
        return []


def run(store, with_recorder=True):
    delivered: list = []
    holder = {}

    def wire(fan, ids):
        fan.subscribe(delivered.append, ids)  # another consumer, subscribed first: the feed already carries the ids
        if with_recorder:
            holder["rec"] = Recorder(store)
            holder["attached"] = holder["rec"].attach(fan, [*ids, "NSE_FO:999999"])

    provider, fan, last = replay_window(W, wire)
    if with_recorder:
        holder["rec"].flush(last + datetime.timedelta(minutes=1))
    return delivered, holder, provider, fan


def test_a_raising_store_does_not_stop_another_listener_and_is_counted(caplog):
    base, _, _, _ = run(None, with_recorder=False)
    with caplog.at_level("WARNING"):
        delivered, holder, _, fan = run(RaisingStore())
    assert len(delivered) == len(base) > 1000  # every quote still reaches the other listener
    assert [q.timestamp for q in delivered] == [q.timestamp for q in base]
    rec = holder["rec"]
    assert rec.counters["errors"] > 0 and rec.counters["bars_lost"] > 0 and rec.counters["bars_written"] == 0
    assert fan.listener_errors == 0  # the recorder swallowed it itself; the fan-out never saw an exception
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in text and "secret-looking-value" not in text and "123.45" not in text


def test_the_recorder_adds_no_vendor_subscription_and_skips_ids_the_feed_does_not_carry():
    delivered, holder, provider, fan = run(InMemoryHistoryStore())
    assert provider.counters["vendor_subscribe"] == 8  # the same 8 as without a recorder
    assert "NSE_FO:999999" not in holder["attached"] and len(holder["attached"]) == 8
    assert holder["rec"].counters["not_carried"] == 1
    assert fan.subscriber_count(NIFTY_CE) == 2


def test_with_a_working_store_the_other_listener_still_gets_every_quote_and_bars_are_written():
    base, _, _, _ = run(None, with_recorder=False)
    store = InMemoryHistoryStore()
    delivered, holder, _, _ = run(store)
    assert len(delivered) == len(base)
    assert holder["rec"].counters["bars_written"] > 40 and holder["rec"].counters["errors"] == 0
    assert len(store.all_stored()) == holder["rec"].counters["bars_written"]


def test_an_unsubscribed_recorder_stops_receiving():
    store = InMemoryHistoryStore()
    holder = {}

    def wire(fan, ids):
        fan.subscribe(lambda q: None, ids)
        holder["rec"] = Recorder(store)
        holder["rec"].attach(fan, ids)
        holder["rec"].detach()

    replay_window(W, wire)
    assert store.all_stored() == [] and holder["rec"].builder.counters["unusable"] == 0
