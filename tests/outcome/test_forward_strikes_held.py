"""D-C33 (GC-UI checker 2026-10-28): a leg expiry whose chain is live is priced on its parity forward, not the spot
fallback.

Core: on the REAL recorded Kite frames of 2026-10-08 09:20 (tests/fixtures/kite_ws), a provider that holds only the
condor's 4 legs + the index hands ``parity_forward`` fewer than 3 two-sided strikes, so the forward is "estimated from
spot" (the defect: the live chain snapshot is the book, which holds only subscribed contracts). Holding the legs + the
index + ``forward_strike_ids`` (5 strikes nearest the money, CE and PE) gives ``source == "parity"`` and no label.
With fewer than 3 two-sided strikes the fallback and its label stay (ADR-061, unchanged).
"""
import datetime
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketdata._kite_fixture import Clock, new_provider, replay
from ofo.marketdata.forward import FALLBACK_LABEL, MIN_STRIKES, PARITY, SPOT_FALLBACK
from ofo.marketdata.kite_provider import IST
from ofo.outcome.snapshot import FORWARD_STRIKES, forward_strike_ids, read_snapshot

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
LEGS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]  # test_strategy_live_push condor


def _snapshot(extra: list[str]):
    provider, _clock, _items = new_provider()
    held = [*LEGS, provider.index_id("NIFTY"), *extra]
    provider.subscribe(held)
    provider.drain_subscription_changes()
    replay(provider, Clock(VALUATION))
    return provider, read_snapshot(provider, "NIFTY", LEGS, VALUATION, RATE)


def _only(snap):
    (fwd,) = snap.forwards.values()
    return fwd


def test_red_legs_only_falls_back_to_spot_although_the_chain_is_live():
    _p, snap = _snapshot([])
    fwd = _only(snap)
    assert fwd.source == SPOT_FALLBACK and fwd.label == FALLBACK_LABEL  # the defect, reproduced on real frames


def test_holding_the_forward_strikes_prices_the_expiry_on_parity():
    provider, _ = _snapshot([])
    ids = forward_strike_ids(provider.instrument_master(), "NIFTY", LEGS, provider.underlying_quote("NIFTY").ltp)
    assert 0 < len(ids) <= 2 * FORWARD_STRIKES and not set(ids) & set(LEGS)
    _p, snap = _snapshot(ids)
    fwd = _only(snap)
    assert fwd.source == PARITY and fwd.label is None and fwd.strikes_used >= MIN_STRIKES, fwd


def test_no_spot_centres_on_the_middle_leg_strike():
    provider, _ = _snapshot([])
    ids = forward_strike_ids(provider.instrument_master(), "NIFTY", LEGS, None)
    assert len(ids) > 0 and not set(ids) & set(LEGS)


def test_fewer_than_three_two_sided_strikes_keeps_the_fallback_and_its_label():
    provider, _ = _snapshot([])
    ids = forward_strike_ids(provider.instrument_master(), "NIFTY", LEGS, provider.underlying_quote("NIFTY").ltp, n=1)
    _p, snap = _snapshot(ids)  # 1 strike nearest the money + the legs' strikes: under 3 two-sided pairs
    fwd = _only(snap)
    assert fwd.strikes_used < MIN_STRIKES and fwd.source == SPOT_FALLBACK and fwd.label == FALLBACK_LABEL


def test_unknown_and_future_legs_add_nothing():
    provider, _ = _snapshot([])
    assert forward_strike_ids(provider.instrument_master(), "NIFTY", ["NSE_FO:999999999"], None) == []
    assert forward_strike_ids(provider.instrument_master(), "SENSEX", LEGS, None) == []
