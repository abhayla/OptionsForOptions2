"""W-063 input states (run-discipline B4 (d)): each not-live input produces its named label or refusal, never a
silent computation. Real 2026-10-08 replay; a state is made by changing ONE input of the real snapshot."""
import dataclasses
import datetime
from decimal import Decimal

import pytest

from ofo.engine.legs import Action
from ofo.marketdata.forward import FALLBACK_LABEL, spot_fallback_forward
from ofo.marketdata.kite_provider import IST
from ofo.outcome import NOT_CONNECTED_LABEL, OutcomeState, build_outcome, read_snapshot
from ofo.rules.inputs import DataHealth
from ofo.table import TOTAL_ROW_ID, ColumnId, UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition, formula_pnl

STALE_LEG = "NSE_FO:44632"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    last = replay(provider, clock)
    return provider, clock, last


def _snap(provider, valuation=VALUATION):
    d = definition(provider)
    return d, read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], valuation, RATE)


def _with_leg(snap, iid, quote):
    legs = dict(snap.legs)
    legs[iid] = dataclasses.replace(legs[iid], quote=quote)
    return dataclasses.replace(snap, legs=legs)


def _leg(out, iid):
    return next(leg for leg in out.legs if leg.instrument_id == iid)


def _total(out):
    return next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)


def test_all_live_has_no_label(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    out = build_outcome(d, snap)
    assert out.state is OutcomeState.COMPUTED
    assert out.output_label is None and out.status_label is None
    assert all(leg.label is None and leg.health is DataHealth.AVAILABLE for leg in out.legs)
    assert all(leg.iv is not None for leg in out.legs)


def test_one_leg_stale_is_computed_with_its_label(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    q = snap.legs[STALE_LEG].quote
    out = build_outcome(d, _with_leg(snap, STALE_LEG, dataclasses.replace(q, health=DataHealth.STALE)))
    assert out.state is OutcomeState.COMPUTED
    hhmm = q.timestamp.astimezone(IST).strftime("%H:%M")
    leg = _leg(out, STALE_LEG)
    assert leg.label == f"stale since {hhmm} IST" and leg.strike == Decimal("23000")
    assert f"{leg.symbol}: stale since {hhmm} IST" in out.output_label


def test_leg_with_no_quote_keeps_expiry_scenarios_and_shows_no_live_pnl(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    out = build_outcome(d, _with_leg(snap, STALE_LEG, None))
    leg = _leg(out, STALE_LEG)
    assert (leg.label, leg.ltp, leg.iv) == ("no live quote", None, None)
    total = _total(out)
    assert total.cell(ColumnId.UNREALIZED_PNL).value is None
    for level in out.level_set.levels:  # expiry scenarios still use the planned entries
        assert total.cell(level).value == formula_pnl(level, provider)


def test_unhealthy_leg_quote_is_not_used(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    q = snap.legs[STALE_LEG].quote
    out = build_outcome(d, _with_leg(snap, STALE_LEG, dataclasses.replace(q, health=DataHealth.UNHEALTHY)))
    leg = _leg(out, STALE_LEG)
    assert (leg.label, leg.ltp) == ("quote unhealthy; not used", None)


def test_forward_fallback_is_labelled_estimated_from_spot(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    exp = datetime.date(2026, 10, 13)
    s = snap.spot
    fwd = spot_fallback_forward(exp, s.ltp, s.timestamp, VALUATION, RATE, spot_health=s.health)
    out = build_outcome(d, dataclasses.replace(snap, forwards={exp: fwd}))
    assert out.state is OutcomeState.COMPUTED
    assert out.output_label.startswith(FALLBACK_LABEL)


def test_spot_and_feed_stale_carry_labels_and_the_ac5_message():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    last = replay(provider, clock)
    clock.now = last + datetime.timedelta(seconds=10)  # no frame for 10 s: the feed is stale (FEED_STALE 3 s)
    d, snap = _snap(provider)
    out = build_outcome(d, snap)
    assert out.state is OutcomeState.COMPUTED
    hhmm = snap.spot.timestamp.astimezone(IST).strftime("%H:%M")
    assert out.output_label.startswith(f"stale since {hhmm} IST; {FALLBACK_LABEL}")
    assert out.status_label.startswith("Live market data disconnected. Last updated: ")
    assert out.status_label.endswith("Live strategy monitoring is paused.")


def test_missing_spot_is_refused(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider)
    out = build_outcome(d, dataclasses.replace(snap, spot=None))
    assert out.state is OutcomeState.REFUSED
    assert "index value is missing" in out.reason
    assert out.table is None and out.payoff_points == ()


def test_expired_leg_is_refused(replayed):
    provider, _, _ = replayed
    d, snap = _snap(provider, valuation=datetime.datetime(2026, 10, 14, 9, 20, tzinfo=IST))
    out = build_outcome(d, snap)
    assert out.state is OutcomeState.REFUSED
    assert out.reason.count(": expired") == 4
    assert out.table is None


def test_no_provider_is_the_not_connected_state(replayed):
    provider, _, _ = replayed
    d = definition(provider)
    out = build_outcome(d, None, UXLevel.GUIDED)
    assert out.state is OutcomeState.NOT_CONNECTED
    assert out.status_label == NOT_CONNECTED_LABEL == "Draft - Live data not connected"
    assert out.margin.state == "NOT_AVAILABLE_YET"
    assert [leg.planned_entry for leg in out.legs] == [p.planned_entry for p in d.legs]
    assert out.table is None
