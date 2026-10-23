"""REQ-050 (W-136 fix round 1): one snapshot instant for the whole answer, judged on real frames (2026-10-08 09:20).

The instant is the latest frame time read, never later than the clock. It values every figure and the strategy's own
P&L, so the CURRENT column reprices to the quote it was solved from; but the expiry check stays on the REAL clock, so
after the 15:30 close nothing is valued with time left. Counts and values, never wall-clock timing."""
import dataclasses
import datetime
from decimal import Decimal

import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Action
from ofo.marketdata.forward import mid_price
from ofo.marketdata.kite_provider import IST
from ofo.outcome import OutcomeState, PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.views import View
from ofo.table import TOTAL_ROW_ID

RATE = Decimal("0.065")
LEGS = ("NSE_FO:44614", "NSE_FO:44615")  # the 22550 CE and PE of the 2026-10-13 expiry
LOT = 65
T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST)


@pytest.fixture(scope="module")
def feed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    return provider, replay(provider, clock)


def definition(provider, at):
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(i, Action.SELL, 1, provider.book.get(i, at).ltp, T0)
                                             for i in LEGS))


def test_the_snapshot_instant_is_the_latest_frame_read_and_never_after_the_clock(feed):
    provider, at = feed
    late = read_snapshot(provider, "NIFTY", list(LEGS), at + datetime.timedelta(minutes=1), RATE)
    assert late.valuation <= at  # a clock a minute on does not move it
    latest = max([late.spot.timestamp, *(lm.quote.timestamp for lm in late.legs.values())])
    assert late.valuation >= latest
    early = read_snapshot(provider, "NIFTY", list(LEGS), latest - datetime.timedelta(seconds=30), RATE)
    assert early.valuation == latest - datetime.timedelta(seconds=30)  # capped at the clock


def test_the_current_column_reprices_to_the_quote_at_the_snapshot_instant(feed):
    provider, at = feed
    clock = at + datetime.timedelta(minutes=1)  # the request clock is a minute after the last frame
    d = definition(provider, at)
    snap = read_snapshot(provider, "NIFTY", list(LEGS), clock, RATE)
    out = build_outcome(d, snap, snap.valuation, view=View.ESTIMATED_NOW)
    assert out.state is OutcomeState.COMPUTED, out.reason
    total = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    now_pnl = total.cell(out.spot_level).value
    expected = Decimal(0)
    for p in d.legs:
        q = snap.legs[p.instrument_id].quote
        expected += (p.planned_entry - mid_price(q.bid, q.ask)) * LOT
    assert abs(now_pnl - expected) <= Decimal("1")  # the same instant: no time-decay gap to close
    # one instant end to end: the answer, the snapshot and every expiry's forward carry the same time
    assert out.valuation == snap.valuation == {f.valuation_time for f in snap.forwards.values()}.pop()


def test_after_the_close_an_expiring_contract_is_not_valued_with_time_left(feed):
    provider, at = feed
    expiry = datetime.date(2026, 10, 13)
    last_frame = datetime.datetime.combine(expiry, datetime.time(15, 29, 58), tzinfo=IST)
    d = definition(provider, at)
    for clock, valued in ((last_frame + datetime.timedelta(seconds=1), True),
                          (last_frame + datetime.timedelta(seconds=3), False)):  # 15:29:59 / 15:30:01 IST
        snap = read_snapshot(provider, "NIFTY", list(LEGS), clock, RATE)
        assert all((lm.problem is None) is valued for lm in snap.legs.values()), clock
        if not valued:
            assert snap.forwards == {}
            assert build_outcome(d, snap, snap.valuation).state is not OutcomeState.COMPUTED


def test_the_serialized_outcome_carries_no_level_and_the_full_column_set(feed):
    """REQ-006 / ADR-168 (4): the serialized outcome has no `ux_level` key and every fixed column is visible."""
    provider, at = feed
    snap = read_snapshot(provider, "NIFTY", list(LEGS), at, RATE)
    out = build_outcome(definition(provider, at), snap, snap.valuation)
    assert out.state is OutcomeState.COMPUTED, out.reason
    assert "ux_level" not in {f.name for f in dataclasses.fields(out)}
    body = outcome_to_dict(out)
    assert "ux_level" not in body
    shown = {c["id"] for c in body["table"]["columns"] if c["visible"]}
    assert {"iv", "delta", "gamma", "theta", "vega", "pnl_percent", "lower_be", "upper_be"} <= shown
    assert all(c["visible"] for c in body["table"]["columns"])
