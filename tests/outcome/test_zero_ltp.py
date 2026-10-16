"""Gate 4a D-3: a last price of 0 is "no live price", never a value (ADR-020 Q185 "no fake prices"). The 2026-10-16
gate run showed an AVAILABLE quote with LTP 0 valued at Current Value 0.00 / P&L -100%. Real 2026-10-08 replay; the
state is made by changing ONE input (the leg's last price) of the real snapshot."""
import dataclasses
from decimal import Decimal

import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.outcome import OutcomeState, build_outcome, read_snapshot
from ofo.outcome.planned_entry import is_live_price, planned_entry_of
from ofo.rules.inputs import DataHealth
from ofo.table import TOTAL_ROW_ID, ColumnId
from outcome.test_same_engine import RATE, VALUATION, definition

LEG = "NSE_FO:44632"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _snap(provider, leg_ltp):
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    legs = dict(snap.legs)
    q = legs[LEG].quote
    assert q.health is DataHealth.AVAILABLE
    legs[LEG] = dataclasses.replace(legs[LEG], quote=dataclasses.replace(q, ltp=leg_ltp))
    return d, dataclasses.replace(snap, legs=legs)


def _leg(out):
    return next(leg for leg in out.legs if leg.instrument_id == LEG)


def test_zero_ltp_leg_is_no_live_price_not_a_value(replayed):
    d, snap = _snap(replayed, Decimal("0"))
    out = build_outcome(d, snap)
    leg = _leg(out)
    assert (leg.label, leg.ltp, leg.iv) == ("no live quote", None, None)
    total = next(r for r in out.table.rows if r.row_id == TOTAL_ROW_ID)
    assert total.cell(ColumnId.UNREALIZED_PNL).value is None  # not computed from 0 (was -100%)


def test_one_tick_ltp_is_a_valid_price(replayed):
    d, snap = _snap(replayed, Decimal("0.05"))
    leg = _leg(build_outcome(d, snap))
    assert leg.ltp == Decimal("0.05") and leg.label != "no live quote"


def test_one_shared_rule_for_planned_entry_and_outcome(replayed):
    assert not is_live_price(Decimal("0")) and not is_live_price(None) and is_live_price(Decimal("0.05"))
    _, snap = _snap(replayed, Decimal("0"))
    assert planned_entry_of(snap.legs[LEG].quote) is None


def test_zero_spot_is_refused(replayed):
    d, snap = _snap(replayed, Decimal("1"))
    out = build_outcome(d, dataclasses.replace(snap, spot=dataclasses.replace(snap.spot, ltp=Decimal("0"))))
    assert out.state is OutcomeState.REFUSED
