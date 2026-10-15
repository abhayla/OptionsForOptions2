"""Issue #222 / ADR-077: after the last unsubscribe the provider keeps each contract's last price TIME, never the price,
so the REST fallback shows REQ-049 AC-5's "Last updated: <time>" (not the draft label). Real 2026-10-08 replay through
the real fan-out and KiteProvider; a strategy that never subscribed keeps the ADR-020 Q185 draft label."""
import datetime

from ofo.errors.explanations import render_explanation
from ofo.marketdata.fanout import FanOut
from ofo.marketdata import feed_health
from ofo.outcome import NOT_CONNECTED_LABEL, OutcomeState, not_live, read_snapshot
from ofo.table import UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition


def _ids(provider, d):
    return [p.instrument_id for p in d.legs] + [provider.index_id("NIFTY")]


def test_adr077_unsubscribed_inputs_show_ac5_with_the_newest_price_time_17_minutes_later():
    provider, clock, items = new_provider()
    fan = FanOut(provider)
    handle = fan.subscribe(lambda q: None, all_instrument_ids(items))
    last = replay(provider, clock)
    d = definition(provider)
    ids = _ids(provider, d)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    newest = max([snap.spot.timestamp] + [lm.quote.timestamp for lm in snap.legs.values()])
    fan.unsubscribe(handle)  # the browser's socket closed: the last watcher leaves
    clock.now = last + datetime.timedelta(minutes=17)
    after = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    assert after.spot is None and all(lm.quote is None for lm in after.legs.values())  # no price outlives it
    out = not_live(d, after, UXLevel.STANDARD)
    expected = render_explanation("outcome_feed_disconnected", time=newest)
    assert out.state is OutcomeState.NOT_CONNECTED
    assert out.status_label == expected and "Last updated" in str(expected)
    assert all(leg.label == expected and leg.ltp is None for leg in out.legs)
    assert all(provider.last_quote_time(i) is not None for i in ids)


def test_adr077_only_the_time_is_kept_never_a_price():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    iid = provider.index_id("NIFTY")
    held = provider.underlying_quote("NIFTY")
    provider.unsubscribe([iid])
    assert provider.underlying_quote("NIFTY") is None
    assert provider.book.get(iid, clock.now) is None and provider.book.last_changed_at(iid) is None
    assert provider.last_quote_time(iid) == held.timestamp
    kept = provider.book._ended_times
    assert all(isinstance(t, datetime.datetime) for t in kept.values())  # times only: no quote object, no price


def test_adr077_never_subscribed_keeps_the_q185_draft_label():
    seeded, sclock, _ = new_provider()
    replay(seeded, sclock)
    d = definition(seeded)  # only to name real legs
    provider, clock, items = new_provider()  # a provider no frame ever reached
    provider.unsubscribe(all_instrument_ids(items))  # unsubscribing what was never held keeps no time
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    assert not snap.ended_times
    out = not_live(d, snap)
    assert out.status_label == NOT_CONNECTED_LABEL and "Last updated" not in out.status_label


def test_adr077_kept_times_are_bounded_oldest_removal_first(monkeypatch):
    provider, clock, items = new_provider()
    monkeypatch.setattr(feed_health, "MAX_KEPT_TIMES", 3)
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    held = [i for i in all_instrument_ids(items) if provider.book.get(i, clock.now) is not None][:5]
    assert len(held) == 5
    provider.unsubscribe(held)
    kept = list(provider.book._ended_times)
    assert len(kept) == 3 and kept == held[2:]  # the two oldest removals were evicted
    assert provider.last_quote_time(held[0]) is None and provider.last_quote_time(held[4]) is not None


def test_adr077_a_resubscribed_contract_speaks_with_its_new_quote_not_the_old_time():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    iid = provider.index_id("NIFTY")
    q = provider.underlying_quote("NIFTY")
    provider.unsubscribe([iid])
    assert provider.last_quote_time(iid) == q.timestamp
    provider.book.update(q)
    assert provider.last_quote_time(iid) is None
