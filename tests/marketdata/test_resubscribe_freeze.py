"""Gate 4a D-1 (2026-10-16): an instrument released by one holder and acquired by another kept no Kite subscription.

RCA: ``KiteProvider`` queued every subscribe and unsubscribe call in two lists, and ``KiteSocket._send_changes`` sent
the subscribe list before the unsubscribe list, so a token released and taken again between two sends went out as
"subscribe t" then "unsubscribe t": Kite stopped sending it while the provider still wanted it, and the feed-level
health (other contracts kept ticking) called the frozen price live.

Class: every instrument whose holder set goes {A} -> {B} or {A} -> {} -> {B} between two sends, index spot and option
legs alike. Fix: the changes sent are the difference between what is wanted and what Kite was last told (a net diff),
a released quote is parked (unreadable) until the send and restored if taken again, and a tick for a token Kite was
told to drop never brings a quote back.
"""
import datetime

from _kite_fixture import NIFTY_CE_ID, NIFTY_PE_ID, all_instrument_ids, new_provider, replay
from ofo.marketdata.fanout import FanOut
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST_UNNAMED as SEC_TZ

SPOT_ID = "NSE_INDEX:1001"
SEC = datetime.timedelta(seconds=1)


def _ltp_frame(*token_paise: tuple[int, int]) -> bytes:
    body = b"".join((8).to_bytes(2, "big") + t.to_bytes(4, "big") + p.to_bytes(4, "big") for t, p in token_paise)
    return len(token_paise).to_bytes(2, "big") + body


def _wire(provider, wire: set[int]) -> set[int]:
    """Apply one send to a model of Kite's subscription set, in KiteSocket._send_changes' order (subscribe first)."""
    added, removed = provider.drain_subscription_changes()
    wire |= set(added)
    wire -= set(removed)
    return wire


def test_release_then_acquire_in_one_change_keeps_the_token_on_the_wire():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    spot = provider._token_of[SPOT_ID]
    h_a = fan.subscribe(lambda q: None, [SPOT_ID, NIFTY_CE_ID])
    wire = _wire(provider, set())
    assert spot in wire
    fan.unsubscribe(h_a)  # socket A closes ...
    fan.subscribe(lambda q: None, [SPOT_ID, NIFTY_PE_ID])  # ... socket B opens before the next send
    wire = _wire(provider, wire)
    assert spot in wire, "the spot index was unsubscribed on the wire while a holder still wants it"
    assert provider._token_of[NIFTY_CE_ID] not in wire  # the leg nobody holds is released
    assert wire == set(provider.subscribed_tokens())


def test_release_send_then_acquire_subscribes_again():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    spot = provider._token_of[SPOT_ID]
    h_a = fan.subscribe(lambda q: None, [SPOT_ID])
    wire = _wire(provider, set())
    fan.unsubscribe(h_a)
    wire = _wire(provider, wire)
    assert spot not in wire
    fan.subscribe(lambda q: None, [SPOT_ID])
    assert _wire(provider, wire) == {spot}


def test_acquire_then_release_before_any_send_sends_nothing():
    provider, _clock, _items = new_provider()
    fan = FanOut(provider)
    h = fan.subscribe(lambda q: None, [SPOT_ID])
    fan.unsubscribe(h)
    assert provider.drain_subscription_changes() == ([], [])


def test_quiet_contract_released_and_reacquired_before_the_send_keeps_its_price():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    end = replay(provider, clock)
    before = provider.book.get(NIFTY_CE_ID, end)
    assert before is not None and before.health is DataHealth.AVAILABLE
    provider.unsubscribe([NIFTY_CE_ID])
    assert provider.book.get(NIFTY_CE_ID, end) is None  # unheld: unreadable at once (REQ-049 AC-4)
    assert provider.last_quote_time(NIFTY_CE_ID) == before.timestamp  # ADR-077: the time is kept
    provider.subscribe([NIFTY_CE_ID])
    assert provider.drain_subscription_changes() == ([], [])  # Kite was never told to drop it
    again = provider.book.get(NIFTY_CE_ID, end)
    assert again is not None and again.ltp == before.ltp and again.health is DataHealth.AVAILABLE
    assert provider.last_quote_time(NIFTY_CE_ID) is None


def test_parked_quote_is_forgotten_once_the_unsubscribe_is_sent():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    end = replay(provider, clock)
    provider.unsubscribe([NIFTY_CE_ID])
    _added, removed = provider.drain_subscription_changes()
    assert removed == [provider._token_of[NIFTY_CE_ID]]
    provider.subscribe([NIFTY_CE_ID])
    assert provider.book.get(NIFTY_CE_ID, end) is None  # a fresh subscription waits for Kite's own first tick


def test_a_tick_after_the_unsubscribe_was_sent_never_brings_a_ghost_quote_back():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    end = replay(provider, clock)
    token = provider._token_of[NIFTY_CE_ID]
    provider.unsubscribe([NIFTY_CE_ID])
    provider.drain_subscription_changes()
    provider.on_frame(_ltp_frame((token, 12345)), end + SEC)  # in flight when Kite got the unsubscribe
    assert provider.book.get(NIFTY_CE_ID, end + SEC) is None
    chain = provider.option_chain_snapshot("NIFTY", datetime.date(2026, 10, 13))
    assert NIFTY_CE_ID not in {q.instrument_id for q in chain}
    assert provider.counters["released_tick"] == 1
    provider.subscribe([NIFTY_CE_ID])  # taken again: its ticks count once more
    provider.on_frame(_ltp_frame((token, 12345)), end + 2 * SEC)
    assert provider.book.get(NIFTY_CE_ID, end + 2 * SEC) is not None


def test_a_tick_between_release_and_send_is_given_to_no_one_and_restored_on_a_re_take():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    end = replay(provider, clock)
    seen = []
    provider.live_quote_stream(seen.append)
    token = provider._token_of[NIFTY_CE_ID]
    provider.unsubscribe([NIFTY_CE_ID])
    provider.on_frame(_ltp_frame((token, 77700)), end + SEC)  # Kite still sends it: the unsubscribe is not out yet
    assert provider.book.get(NIFTY_CE_ID, end + SEC) is None and seen == []
    provider.subscribe([NIFTY_CE_ID])
    again = provider.book.get(NIFTY_CE_ID, end + SEC)
    assert again is not None and str(again.ltp) == "777"


def test_released_before_its_first_quote_then_ticked_before_the_send_never_becomes_readable():
    # Tier A reviewer repro: subscribe X, send, unsubscribe X, tick X, send -> no holderless quote, nothing delivered
    provider, _clock, _items = new_provider()
    seen = []
    provider.live_quote_stream(seen.append)
    token = provider._token_of[NIFTY_CE_ID]
    at = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=SEC_TZ)
    provider.on_connected(at)
    provider.subscribe([NIFTY_CE_ID])
    provider.drain_subscription_changes()
    provider.unsubscribe([NIFTY_CE_ID])
    provider.on_frame(_ltp_frame((token, 12345)), at + SEC)
    provider.drain_subscription_changes()
    assert provider.book.get(NIFTY_CE_ID, at + SEC) is None and seen == []
    assert provider.subscribed_tokens() == []
    assert provider.counters["unwanted_tick"] == 1


def test_a_not_wanted_token_with_no_parked_entry_is_dropped_and_counted_and_a_re_take_gets_the_next_tick():
    provider, _clock, _items = new_provider()
    token = provider._token_of[NIFTY_CE_ID]
    at = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=SEC_TZ)
    provider.on_connected(at)
    provider.on_frame(_ltp_frame((token, 12345)), at)  # never subscribed
    assert provider.book.get(NIFTY_CE_ID, at) is None and provider.counters["unwanted_tick"] == 1
    provider.subscribe([NIFTY_CE_ID])
    provider.drain_subscription_changes()
    provider.on_frame(_ltp_frame((token, 12400)), at + SEC)
    fresh = provider.book.get(NIFTY_CE_ID, at + SEC)
    assert fresh is not None and str(fresh.ltp) == "124" and fresh.health is DataHealth.AVAILABLE
