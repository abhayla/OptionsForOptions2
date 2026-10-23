"""REQ-050 AC-1/AC-3 (W-136, ADR-053): a market-wide figure is computed once per feed snapshot, never per reader.

Replays the real 2026-10-08 recording (tests/fixtures/kite_ws) into a provider, reads the snapshot twice (two readers
of one feed snapshot) and counts engine calls: the counter is 2 per contract without the shared cache and 1 with it.
Two users' feeds with identical data never share an entry (ADR-053, F-23). Counts work, not time."""
import dataclasses
import datetime
from collections import Counter
from decimal import Decimal

import ofo.outcome.snapshot as snapshot_module
import ofo.table.model as table_model
import pytest
from _kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Action
from ofo.engine.model import expiry_model, implied_vol
from ofo.marketdata.forward import mid_price
from ofo.marketdata.shared_compute import FeedScope, SharedCompute, SharedKey
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, read_snapshot, service
from ofo.scenario.spot import spot_reading
from ofo.table.model import CellKind

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
    assert len(cache) == CONTRACTS * 2 * 2  # two contracts x (IV, Greeks) x two feeds: no entry shared
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


def test_a_new_snapshot_instant_is_another_key_and_an_old_entry_is_never_served_for_it():
    cache, later = SharedCompute(), T0 + datetime.timedelta(seconds=1)
    cache.get_or_compute(key(), lambda: "old")
    assert cache.get_or_compute(key(instant=later), lambda: "new") == "new"
    assert cache.computations == 2 and len(cache) == 2  # a new instant computes; the old entry waits for the size cap
    assert cache.get_or_compute(key(instant=later), lambda: "x") == "new"
    assert cache.get_or_compute(key(), lambda: "x") == "old"  # each instant answers only its own key


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
    assert cache.get_or_compute(key(instrument="I0"), lambda: "again") == "again"  # the oldest was evicted by size


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


def test_a_changed_chain_in_another_order_shares_and_other_quotes_do_not(feed, monkeypatch):
    """Quotes in a different order are the same forward entry; the same quotes with other prices are not."""
    provider, at = feed
    calls: Counter = Counter()
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate):
        calls[expiry] += 1
        return real(chain, spot, expiry, valuation, rate)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    cache = FeedScope(SharedCompute(), "user-1")
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, cache)
    chain = provider.option_chain_snapshot
    monkeypatch.setattr(provider, "option_chain_snapshot", lambda u, e: list(reversed(chain(u, e))))
    read_snapshot(provider, "NIFTY", list(STRADDLE), at, RATE, cache)
    assert set(calls.values()) == {1}  # the reversed chain read the same entry


def test_core_a_second_reader_a_second_later_on_the_clock_computes_nothing(feed, iv_calls, monkeypatch):
    """The core, through the real outcome path: the clock moves on by one second between two readers of one recorded
    snapshot; every market-wide figure (each leg's IV, each expiry's forward) is read back, none recomputed."""
    provider, at = feed
    forwards: Counter = Counter()
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate):
        forwards[expiry] += 1
        return real(chain, spot, expiry, valuation, rate)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    cache = FeedScope(SharedCompute(), "user-1")
    first_snap = read(provider, at, STRADDLE, cache.cache, "user-1")
    first = outcome(first_snap, STRADDLE, cache.cache, "user-1")
    ivs, fwds = sum(iv_calls.values()), sum(forwards.values())
    assert ivs == CONTRACTS and fwds >= 1
    later = at + datetime.timedelta(seconds=1)
    second_snap = read(provider, later, STRADDLE, cache.cache, "user-1")
    second = outcome(second_snap, STRADDLE, cache.cache, "user-1")
    assert sum(iv_calls.values()) == ivs and sum(forwards.values()) == fwds  # the second reader computed nothing
    assert second_snap.valuation == first_snap.valuation  # one instant: the frames', not the clock's
    assert [leg.iv for leg in second.legs] == [leg.iv for leg in first.legs]


def test_a_newer_frame_for_one_contract_is_a_new_instant_with_new_entries(feed, iv_calls):
    provider, at = feed
    cache = SharedCompute()
    snap = read(provider, at, STRADDLE, cache, "user-1")
    outcome(snap, STRADDLE, cache, "user-1")
    before = sum(iv_calls.values())
    newer = snap.valuation + datetime.timedelta(milliseconds=500)
    legs = dict(snap.legs)
    quote = legs[STRADDLE[0]].quote
    legs[STRADDLE[0]] = dataclasses.replace(legs[STRADDLE[0]], quote=dataclasses.replace(quote, timestamp=newer))
    moved = dataclasses.replace(snap, legs=legs, valuation=newer)
    build_outcome(definition(STRADDLE), moved, valuation=newer, shared=FeedScope(cache, "user-1"))
    assert sum(iv_calls.values()) == before + CONTRACTS  # every figure of the new instant is computed afresh



@pytest.fixture
def greek_calls(monkeypatch):
    """Counts every per-unit Greek computation by the engine, wherever it is called from (table model or service)."""
    calls: Counter = Counter()
    real = table_model.leg_greeks_unrounded

    def counted(model, leg):
        calls[(leg.instrument.value, leg.strike)] += 1
        return real(model, leg)

    monkeypatch.setattr(table_model, "leg_greeks_unrounded", counted)
    monkeypatch.setattr(service, "leg_greeks_unrounded", counted)
    return calls


def greek_cells(out):
    """Every Greek cell's per-unit and rounded position value, by (row, column)."""
    return {(row.row_id, str(cid)): (cell.per_unit, cell.value)
            for row in out.table.rows for cid, cell in row.cells.items() if cell.kind is CellKind.GREEK}


def greek_keys(cache):
    return [k for k in cache._slots if k.figure == "leg_greeks"]  # the test reads what was cached


def test_core_the_second_reader_computes_no_greeks_through_the_real_outcome_path(feed, greek_calls):
    """AC-1 (shared Greeks) / AC-3: two readers of one recorded snapshot; the second reader's per-unit Greek
    computations are 0, and its Greeks equal an unshared read exactly (Decimal equality)."""
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    plain = outcome(snap, STRADDLE)
    assert sum(greek_calls.values()) == 2 * CONTRACTS  # unshared: the leg row and the TOTAL row each compute
    greek_calls.clear()
    cache = SharedCompute()
    first = outcome(snap, STRADDLE, cache, "user-1")
    assert set(greek_calls.values()) == {1} and len(greek_calls) == CONTRACTS  # once per contract, not per use
    greek_calls.clear()
    second = outcome(snap, STRADDLE, cache, "user-1")
    assert sum(greek_calls.values()) == 0  # the second reader computed no Greek
    assert greek_cells(first) == greek_cells(second) == greek_cells(plain)
    assert any(per_unit is not None for per_unit, _ in greek_cells(second).values())


def test_two_users_feeds_never_share_greeks(feed, greek_calls):
    """AC-3 / ADR-053: the feed owner is in the Greeks key."""
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    cache = SharedCompute()
    outcome(snap, STRADDLE, cache, "user-1")
    greek_calls.clear()
    outcome(snap, STRADDLE, cache, "user-2")
    assert set(greek_calls.values()) == {1} and len(greek_calls) == CONTRACTS
    assert {k.feed_owner for k in greek_keys(cache)} == {"user-1", "user-2"} and len(greek_keys(cache)) == 2 * CONTRACTS


def test_a_leg_with_no_iv_has_no_greeks_and_caches_nothing(feed, greek_calls):
    """A leg whose IV the engine cannot find has no Greeks; nothing is computed or cached for it."""
    provider, at = feed
    snap = read(provider, at, STRADDLE)
    legs = dict(snap.legs)
    quote = legs[STRADDLE[0]].quote
    legs[STRADDLE[0]] = dataclasses.replace(legs[STRADDLE[0]], quote=dataclasses.replace(
        quote, bid=Decimal("90000"), ask=Decimal("90000"), ltp=Decimal("90000")))  # a call above the spot: no IV
    cache = SharedCompute()
    out = outcome(dataclasses.replace(snap, legs=legs), STRADDLE, cache, "user-1")
    assert out.legs[0].iv is None and out.legs[1].iv is not None
    assert len(greek_calls) == 1 and (out.legs[0].instrument.value, out.legs[0].strike) not in greek_calls
    assert len(greek_keys(cache)) == 1  # only the leg with an IV


def test_a_spot_only_change_at_one_instant_recomputes_the_forward(feed, monkeypatch):
    """AC-3: same instant, same chain quotes, only the spot differs -> the forward is computed again (a forward key
    without the spot would serve the old one)."""
    provider, at = feed
    calls: Counter = Counter()
    real = snapshot_module.parity_forward

    def counted(chain, spot, expiry, valuation, rate):
        calls[expiry] += 1
        return real(chain, spot, expiry, valuation, rate)

    monkeypatch.setattr(snapshot_module, "parity_forward", counted)
    cache = SharedCompute()
    first = read(provider, at, STRADDLE, cache, "user-1")
    assert set(calls.values()) == {1}
    real_spot = provider.underlying_quote("NIFTY")
    moved = dataclasses.replace(real_spot, ltp=real_spot.ltp + Decimal("7"))  # same timestamp, other level
    monkeypatch.setattr(provider, "underlying_quote", lambda _u: moved)
    second = read(provider, at, STRADDLE, cache, "user-1")
    assert second.valuation == first.valuation and set(calls.values()) == {2}
