"""W-122 core proof on the recorded replay (REQ-109 AC-1, AC-2, AC-5; REQ-045 AC-2).

The recording: tests/fixtures/kite_ws, 2026-10-08 09:20:09 IST, NIFTY 50 at 22,533.25. The iron condor (65 units a leg,
expiry 2026-10-13) and its recorded LTPs at the last frame, read from the frames, are the paper entry:
SELL 22800 CE 39.15, BUY 23000 CE 12.95, SELL 22400 PE 82.75, BUY 22200 PE 35.80.
"""
from __future__ import annotations

import dataclasses
import datetime
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Action, Instrument
from ofo.outcome import read_snapshot
from ofo.rules.inputs import DataHealth
from ofo.tracking import paper

D = Decimal
EXPIRY = datetime.date(2026, 10, 13)
RATE = D("0.065")
CONDOR = [("NSE_FO:44624", Action.SELL, Instrument.CE, "22800"), ("NSE_FO:44632", Action.BUY, Instrument.CE, "23000"),
          ("NSE_FO:44604", Action.SELL, Instrument.PE, "22400"), ("NSE_FO:44595", Action.BUY, Instrument.PE, "22200")]
IDS = [c[0] for c in CONDOR]


def _frame(provider, instrument_id: str, rupees: str) -> bytes:
    token = provider._token_of[instrument_id]
    return (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + token.to_bytes(4, "big") + \
        int(D(rupees) * 100).to_bytes(4, "big")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    last = replay(provider, clock)
    return provider, last


def _snapshot(provider, at):
    return read_snapshot(provider, "NIFTY", IDS, at, RATE)


ALL_LIVE = (None, None, None, None)  # contract_reasons: every leg's stored contract live (required since issue #500)


def test_contract_reasons_is_a_required_argument():
    """Issue #500 (verifier minor 1): no default, so a caller cannot price legs without the catalogue's answer."""
    import inspect  # noqa: PLC0415

    param = inspect.signature(paper.tracking_view).parameters["contract_reasons"]
    assert param.default is inspect.Parameter.empty


def _legs():
    return [paper.TrackedLeg(i, a, k, D(s), EXPIRY, 65, D("0"), datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC))
            for i, a, k, s in CONDOR]


def test_ac1_ac2_core_proof_entry_paper_pnl_and_one_detection_on_the_replay(replayed):
    """AC-1/AC-2 core proof. Entry = the recorded LTPs (39.15, 12.95, 82.75, 35.80). Then the feed moves the legs to
    45.15, 14.95, 70.75, 30.80. Paper P&L by hand: SELL CE (39.15 - 45.15) x 65 = -390.00; BUY CE (14.95 - 12.95) x 65
    = +130.00; SELL PE (82.75 - 70.75) x 65 = +780.00; BUY PE (30.80 - 35.80) x 65 = -325.00; total +195.00.
    Breakevens: credit 39.15 - 12.95 + 82.75 - 35.80 = 73.15 -> 22400 - 73.15 = 22326.85 and 22800 + 73.15 = 22873.15.
    Detection at threshold 0.6: short strike 22400 vs index 22533.25 = 133.25 points, 133.25 / 22533.25 x 100 =
    0.5913... -> 0.59% (<= 0.6, fires). Others: 22800 -> 266.75 (1.18%), 22326.85 -> 206.40 (0.92%), 22873.15 ->
    339.90 (1.51%): none fire. At the 0.5 default nothing fires (0.5913 > 0.5)."""
    provider, last = replayed
    entry = paper.capture_entry(_snapshot(provider, last), _legs())
    assert [e.entry_price for e in entry] == [D("39.15"), D("12.95"), D("82.75"), D("35.80")]
    assert all(e.price_at is not None for e in entry)
    for iid, rupees in zip(IDS, ["45.15", "14.95", "70.75", "30.80"], strict=True):
        provider.on_frame(_frame(provider, iid, rupees), last)
    view = paper.tracking_view(_snapshot(provider, last), entry, D("0.6"), ALL_LIVE)
    assert view.paused is False and view.paper_pnl == D("195.00")
    assert view.breakevens == (D("22326.85"), D("22873.15"))
    assert view.index.price == D("22533.25")
    assert [(x.condition, x.level, x.index_level, x.distance_points, x.distance_percent, x.threshold_percent)
            for x in view.detections] == [("near_short_strike", D("22400"), D("22533.25"), D("133.25"), D("0.59"),
                                           D("0.6"))]
    assert paper.tracking_view(_snapshot(provider, last), entry, D("0.5"), ALL_LIVE).detections == ()


def _with_quote(snapshot, iid, **change):
    legs = dict(snapshot.legs)
    legs[iid] = dataclasses.replace(legs[iid], quote=dataclasses.replace(legs[iid].quote, **change))
    return dataclasses.replace(snapshot, legs=legs)


@pytest.mark.parametrize(("change", "state"), [({"health": DataHealth.STALE}, "stale"),
                                               ({"health": DataHealth.UNAVAILABLE}, "stale"),
                                               ({"ltp": None}, "missing"), ({"ltp": D("0")}, "missing")])
def test_ac5_a_stale_or_missing_leg_refuses_the_entry_and_pauses_the_view(replayed, change, state):
    """AC-5: a leg whose quote is not AVAILABLE (stale) or has no positive LTP (missing) refuses the paper entry (no
    guessed price) and pauses paper P&L with the quote's time as "as of"."""
    provider, last = replayed
    snap = _with_quote(_snapshot(provider, last), IDS[0], **change)
    with pytest.raises(paper.PricesNotLive) as refused:
        paper.capture_entry(snap, _legs())
    assert [(p.instrument_id, p.state) for p in refused.value.prices] == [(IDS[0], state)]
    entry = paper.capture_entry(_snapshot(provider, last), _legs())
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert view.paused is True and view.paper_pnl is None
    assert view.as_of == snap.legs[IDS[0]].quote.timestamp


def test_ac1_a_leg_with_no_quote_at_all_is_missing(replayed):
    """AC-1: a contract the feed holds no quote for is 'missing'; the entry is refused."""
    provider, last = replayed
    snap = _snapshot(provider, last)
    legs = dict(snap.legs)
    legs[IDS[1]] = dataclasses.replace(legs[IDS[1]], quote=None)
    with pytest.raises(paper.PricesNotLive):
        paper.capture_entry(dataclasses.replace(snap, legs=legs), _legs())


@pytest.mark.parametrize("spot_change", [{"health": DataHealth.STALE}, {"ltp": None}])
def test_ac2_a_stale_or_missing_index_computes_no_detection(replayed, spot_change):
    """AC-2: no detection is computed from an index price that is not live (the view's index state says why)."""
    provider, last = replayed
    snap = _snapshot(provider, last)
    entry = paper.capture_entry(snap, _legs())
    bad = dataclasses.replace(snap, spot=dataclasses.replace(snap.spot, **spot_change))
    view = paper.tracking_view(bad, entry, D("100"), ALL_LIVE)
    assert view.detections == () and view.index.state != "live"
    assert paper.tracking_view(snap, entry, D("100"), ALL_LIVE).detections != ()  # fires with a live index


def test_ac2_a_multi_expiry_strategy_has_no_breakeven_condition_but_keeps_paper_pnl():
    """AC-2: legs on two expiries have no exact breakevens (MultiExpiryError): breakevens None, P&L still computed.
    SELL 24400 CE at 100 now 90 x 65 = +650.00; BUY 24600 CE (next expiry) at 40 now 35 x 65 = -325.00;
    total +325.00."""
    at = datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC)
    legs = [paper.TrackedLeg("NSE_FO:1", Action.SELL, Instrument.CE, D("24400"), EXPIRY, 65, D("100"), at),
            paper.TrackedLeg("NSE_FO:2", Action.BUY, Instrument.CE, D("24600"), datetime.date(2026, 10, 20), 65,
                             D("40"), at)]
    assert paper.entry_breakevens(legs) is None
    assert paper.paper_pnl(legs, [D("90"), D("35")]) == D("325.00")


def test_ac2_paper_pnl_refuses_a_missing_current_price():
    """AC-2: one current price per leg; fewer is refused, never summed short."""
    at = datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC)
    leg = paper.TrackedLeg("NSE_FO:1", Action.SELL, Instrument.CE, D("24400"), EXPIRY, 65, D("100"), at)
    with pytest.raises(ValueError):
        paper.paper_pnl([leg, leg], [D("90")])


def test_ac5_a_stale_quote_that_still_carries_a_price_pauses_and_refuses_on_its_state(replayed, monkeypatch):
    """AC-5 (GC-BP step 8 review M1): the decision is the price's STATE, never "a price is present". A stale answer
    that keeps its last price (45.15 here) must pause paper P&L (no total, no unbooked, reason prices_not_live) and
    refuse an entry and an exit, exactly as a stale answer without one."""
    provider, last = replayed
    entry = paper.capture_entry(_snapshot(provider, last), _legs())
    real = paper.leg_price

    def stale_with_price(snapshot, instrument_id):
        found = real(snapshot, instrument_id)
        if instrument_id != IDS[0]:
            return found
        return paper.Price(instrument_id, "stale", D("45.15"), found.at)

    monkeypatch.setattr(paper, "leg_price", stale_with_price)
    snap = _snapshot(provider, last)
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert (view.paused, view.pause_reason, view.paper_pnl, view.unbooked, view.booked) == (
        True, "prices_not_live", None, None, D("0"))
    assert view.legs[0].state == "stale"
    with pytest.raises(paper.PricesNotLive):
        paper.exit_prices_now(snap, entry[:1])
    with pytest.raises(paper.PricesNotLive):
        paper.capture_entry(snap, _legs())
    exited = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE, {1: D("14.95")})  # open leg 0 still pauses
    assert (exited.paused, exited.paper_pnl, exited.unbooked) == (True, None, None)
