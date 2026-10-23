"""REQ-072 AC-2 (W-140): a connected feed with only the index quote missing tells the user the INDEX value is missing,
not that the forward could not be derived. The spot gate runs before the forward errors. Real 2026-10-08 replay; each
state is made by leaving ONE group of recorded instruments unsubscribed (or changing one input of the real snapshot).
Answer states of the spot: present and live (computed), stale, unavailable, absent, a last price of 0."""
import dataclasses
from decimal import Decimal

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.errors.explanations import render_explanation
from ofo.outcome import OutcomeState, build_outcome, read_snapshot
from ofo.rules.inputs import DataHealth
from ofo.table import TOTAL_ROW_ID, ColumnId
from outcome.test_same_engine import RATE, VALUATION, definition

SPOT_MISSING = render_explanation("outcome_spot_missing", underlying="NIFTY")


def _replayed(keep):
    provider, clock, items = new_provider()
    index_id = provider.index_id("NIFTY")
    assert index_id is not None
    provider.subscribe([i for i in all_instrument_ids(items) if keep(i, index_id)])
    replay(provider, clock)
    return provider


def _full():
    return _replayed(lambda i, index_id: True)


def _outcome(provider, spot=None):
    d = definition(_full())  # planned entries from the full replay; the legs are the same ids
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    if spot is not None:
        snap = dataclasses.replace(snap, spot=dataclasses.replace(snap.spot, **spot))
    return snap, build_outcome(d, snap)


def _nothing_computed(out):
    assert out.state is OutcomeState.REFUSED
    assert out.scenario is None and out.summary is None and out.payoff_points == ()
    assert all(leg.iv is None for leg in out.legs)


def test_ac2_index_missing_chain_present_names_the_index():
    """AC-2: connected, chain present, index quote absent -> the index reason, never the forward reason."""
    snap, out = _outcome(_replayed(lambda i, index_id: i != index_id))
    assert snap.spot is None and snap.forward_errors  # the forward cannot be derived without the index
    assert out.reason == SPOT_MISSING
    _nothing_computed(out)


def test_ac2_index_unhealthy_names_the_health():
    """AC-2: an unhealthy index quote -> outcome_spot_unusable naming the health. (A STALE or DELAYED index is computed
    and labelled, REQ-072 AC-3; only UNHEALTHY and UNAVAILABLE are refused.)"""
    _, out = _outcome(_full(), {"health": DataHealth.UNHEALTHY})
    assert out.reason == render_explanation("outcome_spot_unusable", underlying="NIFTY", health=DataHealth.UNHEALTHY)
    _nothing_computed(out)


def test_ac2_index_unavailable_names_the_health():
    """AC-2: an unavailable index quote -> outcome_spot_unusable naming that health."""
    _, out = _outcome(_full(), {"health": DataHealth.UNAVAILABLE})
    assert out.reason == render_explanation("outcome_spot_unusable", underlying="NIFTY",
                                            health=DataHealth.UNAVAILABLE)
    _nothing_computed(out)


def test_ac2_index_last_price_zero_is_missing():
    """AC-2: a last price of 0 is no live price -> the index-missing reason."""
    _, out = _outcome(_full(), {"ltp": Decimal("0")})
    assert out.reason == SPOT_MISSING
    _nothing_computed(out)


def test_ac2_index_good_forward_not_derived_keeps_the_forward_reason():
    """AC-2: good index, the expiry's forward could not be derived -> the forward reason, unchanged. The state is the
    real snapshot with that one expiry's forward moved to forward_errors (what read_snapshot does on a failed one)."""
    full = _full()
    d = definition(full)
    real = read_snapshot(full, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    (expiry,) = real.forwards
    snap = dataclasses.replace(real, forwards={}, forward_errors={expiry: render_explanation("outcome_why_forward")})
    out = build_outcome(d, snap)
    assert snap.spot is not None and snap.spot.health is DataHealth.AVAILABLE
    assert out.state is OutcomeState.REFUSED
    assert "the forward price could not be derived" in out.reason
    assert out.reason != SPOT_MISSING
    _nothing_computed(out)


def test_ac2_both_missing_the_index_reason_wins():
    """AC-2: index absent AND a forward error present -> the earlier gate (the index) wins."""
    full = _full()
    d = definition(full)
    real = read_snapshot(full, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    (expiry,) = real.forwards
    snap = dataclasses.replace(real, spot=None, forwards={}, forward_errors={expiry: "x"})
    out = build_outcome(d, snap)
    assert out.reason == SPOT_MISSING
    _nothing_computed(out)


def test_ac2_good_index_and_chain_still_computes():
    """AC-2 control: nothing refused when both are present (no change to what is computed)."""
    _, out = _outcome(_full())
    assert out.state is OutcomeState.COMPUTED, out.reason
    total = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    assert total.cell(ColumnId.UNREALIZED_PNL).value is not None
