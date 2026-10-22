"""REQ-050 AC-1/AC-3 (W-136, ADR-053): a market-wide figure is computed once per feed snapshot, never per reader.

Replays the real 2026-10-08 recording (tests/fixtures/kite_ws) into a provider, reads the snapshot twice (two readers
of one feed snapshot) and counts engine calls: the counter is 2 per contract without the shared cache and 1 with it.
Two users' feeds with identical data never share an entry (ADR-053, F-23). Counts work, not time."""
import dataclasses
import datetime
from collections import Counter
from decimal import Decimal

import ofo.outcome.snapshot as snapshot_module
import pytest
from _kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Action
from ofo.engine.model import expiry_model, implied_vol
from ofo.marketdata.forward import mid_price
from ofo.marketdata.shared_compute import FeedScope, SharedCompute, SharedKey
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, read_snapshot, service
from ofo.scenario.spot import spot_reading

RATE = Decimal("0.065")
STRADDLE = ("NSE_FO:44614", "NSE_FO:44615")  # the 22550 CE and PE of the 2026-10-13 expiry
STRANGLE = ("NSE_FO:44612", "NSE_FO:44615")  # the 22500 CE and the same 22550 PE: a second reader, other legs
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST)
CONTRACTS = len(STRADDLE)  # the contracts of one reader
DISTINCT = len({*STRADDLE, *STRANGLE})  # the contracts of the two strategies together


@pytest.fixture(scope="module")
def feed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    return provider, replay(provider, clock)


def definition(ids, premium="100.00"):
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(i, Action.SELL, 1, Decimal(premium), T0) for i in ids))


@pytest.fixture
def iv_calls(monkeypatch):
    """Counts the engine's implied-volatility calls per (kind, strike): the compute counter of the proof."""
    calls: Counter = Counter()
    real = service.implied_vol

    def counted(em, kind, price, strike):
        calls[(kind.value, strike)] += 1
        return real(em, kind, price, strike)

    monkeypatch.setattr(service, "implied_vol", counted)
    return calls


def scope(cache, owner):
    return None if cache is None else FeedScope(cache, owner)


def read(provider, at, ids, cache=None, owner=None):
    return read_snapshot(provider, "NIFTY", list(ids), at, RATE, scope(cache, owner))


def outcome(snap, ids, cache=None, owner=None):
    return build_outcome(definition(ids), snap, valuation=snap.valuation, shared=scope(cache, owner))


def test_core_two_readers_of_one_feed_snapshot_compute_once(feed, iv_calls):
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    first, second = outcome(snap, STRADDLE), outcome(snap, STRADDLE)  # today: no shared cache
    assert set(iv_calls.values()) == {2} and len(iv_calls) == CONTRACTS  # counter 2 per contract
    assert [leg.iv for leg in first.legs] == [leg.iv for leg in second.legs]
    iv_calls.clear()

    cache = SharedCompute()
    a, b = outcome(snap, STRADDLE, cache, "user-1"), outcome(snap, STRADDLE, cache, "user-1")
    assert set(iv_calls.values()) == {1} and len(iv_calls) == CONTRACTS  # counter 1 per contract after the build
    assert [leg.iv for leg in a.legs] == [leg.iv for leg in b.legs] == [leg.iv for leg in first.legs]
    assert all(leg.iv is not None for leg in a.legs)


def test_two_readers_with_different_strategies_share_the_common_contract(feed, iv_calls):
    provider, at = feed
    snap = read(provider, at, {*STRADDLE, *STRANGLE})
    cache = SharedCompute()
    outcome(snap, STRADDLE, cache, "user-1")
    outcome(snap, STRANGLE, cache, "user-1")
    assert iv_calls[("PE", Decimal("22550"))] == 1  # the contract both strategies hold
    assert sum(iv_calls.values()) == DISTINCT  # three distinct contracts, three computations


def test_two_users_feeds_with_identical_data_never_share(feed, iv_calls):
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    cache = SharedCompute()
    one, two = outcome(snap, STRADDLE, cache, "user-1"), outcome(snap, STRADDLE, cache, "user-2")
    assert set(iv_calls.values()) == {2}  # one computation per user per contract
    assert len(cache) == CONTRACTS * 2  # two contracts x two feeds: no entry shared
    assert [leg.iv for leg in one.legs] == [leg.iv for leg in two.legs]  # same data, same figures, separate entries


def test_shared_requires_a_feed_owner():
    for owner in (None, "", "  ", 7):
        with pytest.raises(ValueError, match="feed owner"):
            FeedScope(SharedCompute(), owner)
    with pytest.raises(ValueError, match="SharedCompute"):
        FeedScope(object(), "user-1")


def test_shared_ivs_equal_the_engines_per_contract_result_on_the_recorded_frames(feed):
    provider, at = feed
    ids = (*STRADDLE, *STRANGLE)
    snap = read(provider, at, ids)
    shared_out = outcome(snap, ids, SharedCompute(), "user-1")
    spot = spot_reading(snap.spot)
    for leg in shared_out.legs:
        quote = snap.legs[leg.instrument_id].quote
        em = expiry_model(spot, snap.forwards[leg.expiry], underlying="NIFTY")
        price = mid_price(quote.bid, quote.ask)
        assert leg.iv == implied_vol(em, leg.instrument, price, leg.strike).iv  # to the last digit
        assert leg.iv is not None


def test_a_forward_is_computed_once_per_feed_snapshot_and_equals_the_unshared_one(feed, monkeypatch):
    provider, at = feed
    calls: Counter = Counter()
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate):
        calls[expiry] += 1
        return real(chain, spot, expiry, valuation, rate)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    plain = read(provider, at, STRADDLE)
    assert set(calls.values()) == {1}
    calls.clear()
    cache = SharedCompute()
    one, two = read(provider, at, STRADDLE, cache, "user-1"), read(provider, at, STRADDLE, cache, "user-1")
    assert set(calls.values()) == {1}  # two readers, one computation of the expiry's forward
    assert one.forwards == two.forwards == plain.forwards
    read(provider, at, STRADDLE, cache, "user-2")
    assert set(calls.values()) == {2}  # another user's feed computes its own


def test_a_changed_input_at_the_same_instant_never_reads_the_old_entry(feed):
    """A poisoned or stale entry cannot answer other inputs, through the real outcome path (not only the cache)."""
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    cache = SharedCompute()
    first = outcome(snap, STRADDLE, cache, 'user-1')
    legs = dict(snap.legs)
    for iid in STRADDLE:
        quote = legs[iid].quote
        moved = dataclasses.replace(quote, ltp=quote.ltp + Decimal('10'), bid=quote.bid + Decimal('10'),
                                    ask=quote.ask + Decimal('10'))
        legs[iid] = dataclasses.replace(legs[iid], quote=moved)  # same timestamp, other prices
    second = outcome(dataclasses.replace(snap, legs=legs), STRADDLE, cache, 'user-1')
    assert [leg.iv for leg in second.legs] != [leg.iv for leg in first.legs]
    assert all(leg.iv is not None for leg in second.legs)


def key(owner="u1", instant=T0, figure="iv", instrument="X", inputs=(1,)):
    return SharedKey(owner, "NIFTY", datetime.date(2026, 10, 13), instant, figure, instrument, inputs)


def test_a_new_snapshot_instant_computes_again_and_the_old_entry_is_evicted():
    cache, later = SharedCompute(), T0 + datetime.timedelta(seconds=1)
    cache.get_or_compute(key(), lambda: "old")
    assert cache.get_or_compute(key(instant=later), lambda: "new") == "new"
    assert cache.computations == 2 and len(cache) == 1  # two computations, the old entry gone
    assert cache.get_or_compute(key(), lambda: "recomputed") == "recomputed"  # evicted: this is a fresh computation
    assert len(cache) == 1  # and an older instant than the feed's newest is not kept
    assert cache.get_or_compute(key(instant=later), lambda: "x") == "new"  # the newest entry is still there


def test_other_feeds_entries_survive_a_new_instant_of_one_feed():
    cache = SharedCompute()
    cache.get_or_compute(key(owner="u1"), lambda: 1)
    cache.get_or_compute(key(owner="u2"), lambda: 2)
    cache.get_or_compute(key(owner="u1", instant=T0 + datetime.timedelta(seconds=1)), lambda: 3)
    assert cache.get_or_compute(key(owner="u2"), lambda: "again") == 2


def test_memory_is_bounded_by_the_hard_cap():
    cache = SharedCompute(max_entries=3)
    for n in range(10):
        cache.get_or_compute(key(instrument=f"I{n}"), lambda n=n: n)
    assert len(cache) == 3


def test_different_inputs_never_read_another_entry():
    """A poisoned or stale entry cannot answer other inputs: the exact inputs are part of the key."""
    cache = SharedCompute()
    cache.get_or_compute(key(inputs=(Decimal("100"),)), lambda: "for 100")
    assert cache.get_or_compute(key(inputs=(Decimal("101"),)), lambda: "for 101") == "for 101"
    assert cache.get_or_compute(key(figure="greeks"), lambda: "greeks") == "greeks"
    assert cache.computations == 3


def test_the_key_refuses_what_it_cannot_scope():
    for bad in ({"owner": ""}, {"owner": None}, {"figure": " "}, {"instant": T0.replace(tzinfo=None)},
                {"inputs": [1]}, {"inputs": ([],)}):
        with pytest.raises((ValueError, TypeError)):
            key(**bad)
    with pytest.raises(ValueError, match="SharedKey"):
        SharedCompute().get_or_compute(("u1", "NIFTY"), lambda: 1)
    with pytest.raises(ValueError, match="max_entries"):
        SharedCompute(max_entries=0)


def test_a_changed_chain_at_the_same_instant_never_reads_the_old_forward(feed, monkeypatch):
    """The quotes the forward reads are in its key: other quotes at the same valuation instant are another entry."""
    provider, at = feed
    cache = FeedScope(SharedCompute(), "user-1")
    before = read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, cache)
    real = provider.option_chain_snapshot

    def shifted(underlying, expiry):
        return [dataclasses.replace(q, bid=q.bid + Decimal("10"), ask=q.ask + Decimal("10"))
                if q.instrument_type.value == "CE" and q.bid and q.ask else q for q in real(underlying, expiry)]

    monkeypatch.setattr(provider, "option_chain_snapshot", shifted)
    after = read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, cache)
    assert after.forwards != before.forwards
