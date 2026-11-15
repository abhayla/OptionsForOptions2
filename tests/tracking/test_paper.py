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
from ofo.settings import calc as _fq_calc
from ofo.settings import defaults as _fq_defaults
from ofo.tracking import paper

_FQ = _fq_calc.forward_quality(_fq_defaults())

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
    return read_snapshot(provider, "NIFTY", IDS, at, RATE, quality=_FQ)


ALL_LIVE = (None, None, None, None)  # contract_reasons: every leg's stored contract live (required since issue #500)


def test_contract_reasons_is_a_required_argument():
    """Issue #500 (verifier minor 1): no default, so a caller cannot price legs without the catalogue's answer."""
    import inspect  # noqa: PLC0415

    param = inspect.signature(paper.tracking_view).parameters["contract_reasons"]
    assert param.default is inspect.Parameter.empty


def _legs():
    return [paper.TrackedLeg(i, a, k, D(s), EXPIRY, 65, D("0"), datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC))
            for i, a, k, s in CONDOR]


def _entry(snapshot) -> tuple:
    """The condor entered at each leg's live price in ``snapshot`` (paper entries are typed orders since GC-TP step 2;
    this only builds the legs the view tests need)."""
    prices = [paper.leg_price(snapshot, leg.instrument_id) for leg in _legs()]
    assert all(paper.is_live(p) for p in prices), prices
    return tuple(dataclasses.replace(leg, entry_price=p.price, price_at=p.at)
                 for leg, p in zip(_legs(), prices, strict=True))


def test_ac1_ac2_core_proof_entry_paper_pnl_and_one_detection_on_the_replay(replayed):
    """AC-1/AC-2 core proof. Entry = the recorded LTPs (39.15, 12.95, 82.75, 35.80). Then the feed moves the legs to
    45.15, 14.95, 70.75, 30.80. Paper P&L by hand: SELL CE (39.15 - 45.15) x 65 = -390.00; BUY CE (14.95 - 12.95) x 65
    = +130.00; SELL PE (82.75 - 70.75) x 65 = +780.00; BUY PE (30.80 - 35.80) x 65 = -325.00; total +195.00.
    Breakevens: credit 39.15 - 12.95 + 82.75 - 35.80 = 73.15 -> 22400 - 73.15 = 22326.85 and 22800 + 73.15 = 22873.15.
    Detection at threshold 0.6: short strike 22400 vs index 22533.25 = 133.25 points, 133.25 / 22533.25 x 100 =
    0.5913... -> 0.59% (<= 0.6, fires). Others: 22800 -> 266.75 (1.18%), 22326.85 -> 206.40 (0.92%), 22873.15 ->
    339.90 (1.51%): none fire. At the 0.5 default nothing fires (0.5913 > 0.5)."""
    provider, last = replayed
    entry = _entry(_snapshot(provider, last))
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
def test_ac5_a_stale_or_missing_leg_refuses_the_exit_and_pauses_the_view(replayed, change, state):
    """AC-5: a leg whose quote is not AVAILABLE (stale) or has no positive LTP (missing) refuses a paper exit (no
    guessed price) and pauses paper P&L with the quote's time as "as of"."""
    provider, last = replayed
    entry = _entry(_snapshot(provider, last))
    snap = _with_quote(_snapshot(provider, last), IDS[0], **change)
    with pytest.raises(paper.PricesNotLive) as refused:
        paper.exit_prices_now(snap, entry)
    assert [(p.instrument_id, p.state) for p in refused.value.prices] == [(IDS[0], state)]
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert view.paused is True and view.paper_pnl is None
    assert view.as_of == snap.legs[IDS[0]].quote.timestamp


def test_ac1_a_leg_with_no_quote_at_all_is_missing(replayed):
    """AC-1: a contract the feed holds no quote for is 'missing'; an exit of it is refused."""
    provider, last = replayed
    snap = _snapshot(provider, last)
    entry = _entry(snap)
    legs = dict(snap.legs)
    legs[IDS[1]] = dataclasses.replace(legs[IDS[1]], quote=None)
    no_quote = dataclasses.replace(snap, legs=legs)
    assert paper.leg_price(no_quote, IDS[1]).state == "missing"
    with pytest.raises(paper.PricesNotLive):
        paper.exit_prices_now(no_quote, entry[1:2])


@pytest.mark.parametrize("spot_change", [{"health": DataHealth.STALE}, {"ltp": None}])
def test_ac2_a_stale_or_missing_index_computes_no_detection(replayed, spot_change):
    """AC-2: no detection is computed from an index price that is not live (the view's index state says why)."""
    provider, last = replayed
    snap = _snapshot(provider, last)
    entry = _entry(snap)
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
    refuse an exit, exactly as a stale answer without one."""
    provider, last = replayed
    entry = _entry(_snapshot(provider, last))
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
    exited = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE, {1: D("14.95")})  # open leg 0 still pauses
    assert (exited.paused, exited.paper_pnl, exited.unbooked) == (True, None, None)
    # ADR-311: an unpriced open leg has no figure (never 0); the exited leg keeps its booked figure
    live = [paper.leg_price(snap, IDS[i]).price for i in (2, 3)]  # ADR-311: priced legs keep their figure
    assert exited.leg_pnls == (None, (D("14.95") - entry[1].entry_price) * 65, paper.leg_pnl(entry[2], live[0]),
                               paper.leg_pnl(entry[3], live[1]))


def test_d_b48_view_leg_pnls_live_exited_at_exit_price_and_they_add_to_the_total(replayed):
    """Feed at 45.15 / 14.95 / 70.75 / 30.80 from 39.15 / 12.95 / 82.75 / 35.80, 65 a leg: -390.00, +130.00, +780.00,
    -325.00 = +195.00. SELL 22800 CE (leg 0) exited at 40.00 books (39.15 - 40.00) x 65 = -55.25, not the -390.00 it
    would be at the current 45.15; total -55.25 + 130 + 780 - 325 = +529.75."""
    provider, last = replayed  # module-scoped: other tests move its prices, so set them here and state the entries
    for iid, rupees in zip(IDS, ["45.15", "14.95", "70.75", "30.80"], strict=True):
        provider.on_frame(_frame(provider, iid, rupees), last)
    snap = _snapshot(provider, last)
    entry = [dataclasses.replace(leg, entry_price=D(price))
             for leg, price in zip(_legs(), ["39.15", "12.95", "82.75", "35.80"], strict=True)]
    live = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert live.leg_pnls == (D("-390.00"), D("130.00"), D("780.00"), D("-325.00"))
    assert sum(live.leg_pnls) == live.paper_pnl == D("195.00")
    mixed = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE, {0: D("40.00")})
    assert mixed.leg_pnls == (D("-55.25"), D("130.00"), D("780.00"), D("-325.00"))
    assert sum(mixed.leg_pnls) == mixed.paper_pnl == D("529.75")


def test_adr212_display_price_uses_the_held_close_after_hours_but_fills_still_refuse(replayed):
    """ADR-212: market closed + a sound STALE quote -> the display price is the held close (45.15 here, its own time);
    no quote -> unpriced; market open + stale -> paused (not priced); and the fill predicate/exit still refuse it."""
    provider, last = replayed
    entry = _entry(_snapshot(provider, last))
    stale = _with_quote(_snapshot(provider, last), IDS[0], health=DataHealth.STALE)
    held = stale.legs[IDS[0]].quote
    closed = dataclasses.replace(stale, market_closed=True)
    shown = paper.display_price(closed, IDS[0])
    assert (shown.state, shown.price, shown.at) == ("live", held.ltp, held.timestamp)
    # market open: a stale quote is not displayed (REQ-109 AC-5 unchanged)
    assert paper.display_price(dataclasses.replace(stale, market_closed=False), IDS[0]).state == "stale"
    # closed but no quote / no price: unpriced, never a default (ADR-200 (4))
    legs = dict(closed.legs)
    legs[IDS[1]] = dataclasses.replace(legs[IDS[1]], quote=None)
    assert paper.display_price(dataclasses.replace(closed, legs=legs), IDS[1]).price is None
    assert paper.display_price(_with_quote(closed, IDS[0], ltp=None), IDS[0]).price is None
    # an UNAVAILABLE (session ended) quote is never a close
    ended = _with_quote(closed, IDS[0], health=DataHealth.UNAVAILABLE)
    assert paper.display_price(ended, IDS[0]).price is None
    # fills: leg_price and exit_prices_now still refuse the stale close even though the market is closed
    assert not paper.is_live(paper.leg_price(closed, IDS[0]))
    with pytest.raises(paper.PricesNotLive):
        paper.exit_prices_now(closed, entry[:1])


# ---- ADR-311 / issue 24: an open leg with no live price pauses every TOTAL, is named; the other legs keep their figure
def _no_quote(snap, *ids):
    legs = dict(snap.legs)
    for iid in ids:
        legs[iid] = dataclasses.replace(legs[iid], quote=None)
    return dataclasses.replace(snap, legs=legs)


def _fresh(provider, last):
    """The condor at the last frame's prices, entered at those prices (every leg's own figure is then exactly 0.00)."""
    snap = _snapshot(provider, last)
    return snap, _entry(snap)


def _own_figure(entry, snap, i):
    return paper.leg_pnl(entry[i], paper.leg_price(snap, IDS[i]).price)


def test_adr311_all_priced_nothing_is_unpriced(replayed):
    snap, entry = _fresh(*replayed)
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert (view.paused, view.unpriced) == (False, ())
    assert all(isinstance(x, D) for x in view.leg_pnls) and view.paper_pnl is not None


def test_adr311_the_notes_case_one_far_leg_without_a_price_pauses_the_total_and_names_that_leg(replayed):
    """The user test: a four-leg condor, the far BUY 23000 CE (leg 1) has no price. Totals stay paused (never a sum of
    three), the other three legs keep their own figure, leg 1 has no figure (None, never 0), and it is named."""
    snap, entry = _fresh(*replayed)
    view = paper.tracking_view(_no_quote(snap, IDS[1]), entry, D("0.5"), ALL_LIVE)
    assert (view.paused, view.paper_pnl, view.unbooked) == (True, None, None)
    assert [(u.index, u.instrument_id, u.state, u.expired) for u in view.unpriced] == [(1, IDS[1], "missing", False)]
    assert view.leg_pnls[1] is None
    assert [view.leg_pnls[i] for i in (0, 2, 3)] == [_own_figure(entry, snap, i) for i in (0, 2, 3)]
    assert not any(f in dir(view) for f in ("partial_total", "priced_total"))  # a partial total is never produced


def test_adr311_several_unpriced_one_missing_one_stale_both_named_in_leg_order(replayed):
    snap, entry = _fresh(*replayed)
    snap = _with_quote(_no_quote(snap, IDS[2]), IDS[0], health=DataHealth.STALE)
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert [(u.index, u.state) for u in view.unpriced] == [(0, "stale"), (2, "missing")]  # ADR-272: stale = not priced
    assert (view.leg_pnls[0], view.leg_pnls[2]) == (None, None)
    assert (view.leg_pnls[1], view.leg_pnls[3]) == (_own_figure(entry, snap, 1), _own_figure(entry, snap, 3))
    assert view.paper_pnl is None


def test_adr311_an_expired_contract_is_called_expired_by_its_catalogue_state_or_by_its_date(replayed):
    snap, entry = _fresh(*replayed)
    by_state = paper.tracking_view(snap, entry, D("0.5"), (None, None, None, "contract_retired"))
    assert [(u.index, u.state, u.expired) for u in by_state.unpriced] == [(3, "contract_retired", True)]
    assert by_state.leg_pnls[3] is None and by_state.pause_reason == "contract_retired"
    old = tuple(dataclasses.replace(e, expiry=datetime.date(2026, 10, 1)) if i == 0 else e for i, e in enumerate(entry))
    by_date = paper.tracking_view(_no_quote(snap, IDS[0]), old, D("0.5"), ALL_LIVE)  # valuation is 8 Oct 2026
    assert [(u.index, u.expired) for u in by_date.unpriced] == [(0, True)]
    live_old = paper.tracking_view(_no_quote(snap, IDS[1]), entry, D("0.5"), ALL_LIVE)
    assert [u.expired for u in live_old.unpriced] == [False]  # expiry 13 Oct is not past on 8 Oct


def test_adr311_every_leg_unpriced_no_figure_anywhere_and_all_four_named(replayed):
    snap, entry = _fresh(*replayed)
    view = paper.tracking_view(_no_quote(snap, *IDS), entry, D("0.5"), ALL_LIVE)
    assert (view.paused, view.paper_pnl, view.leg_pnls) == (True, None, (None, None, None, None))
    assert [u.index for u in view.unpriced] == [0, 1, 2, 3]


def test_adr311_a_stale_quote_that_still_carries_a_price_is_unpriced_not_shown(replayed, monkeypatch):
    snap, entry = _fresh(*replayed)
    real = paper.leg_price
    monkeypatch.setattr(paper, "leg_price", lambda s, i: paper.Price(i, "stale", D("45.15"), real(s, i).at)
                        if i == IDS[0] else real(s, i))
    view = paper.tracking_view(snap, entry, D("0.5"), ALL_LIVE)
    assert view.leg_pnls[0] is None and [u.index for u in view.unpriced] == [0]
    assert view.leg_pnls[1:] == tuple(_own_figure(entry, snap, i) for i in (1, 2, 3))
