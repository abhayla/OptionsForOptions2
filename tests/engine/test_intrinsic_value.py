"""R5 (modular doors Phase 4): ``ofo.engine.legs.intrinsic_value(instrument, strike, level)`` is the ONE intrinsic
value; ``_long_value_at`` calls it and the paper settlement's old ``settle_price`` (REQ-109 AC-7) is gone. Nine rows:
CE / PE / FUT, each in, at and out of the money, equal to ``_long_value_at`` and to the values ``settle_price`` gave
(CE max(0, close - strike), PE max(0, strike - close), FUT close). Exact decimal, no float.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.engine import legs
from ofo.engine.legs import Action, Instrument, Leg, intrinsic_value

D = Decimal
CLOSE = D("73246.03")
#: (instrument, strike, level, the value the old ``paper_settlement.settle_price`` returned)
ROWS = [
    (Instrument.CE, "73000", "73246.03", "246.03"), (Instrument.CE, "73246.03", "73246.03", "0"),
    (Instrument.CE, "73300", "73246.03", "0"),
    (Instrument.PE, "73300", "73246.03", "53.97"), (Instrument.PE, "73246.03", "73246.03", "0"),
    (Instrument.PE, "73000", "73246.03", "0"),
    (Instrument.FUT, "0", "73246.03", "73246.03"), (Instrument.FUT, "0", "0.05", "0.05"),
    (Instrument.FUT, "73000", "73246.03", "73246.03"),
]


@pytest.mark.parametrize(("instrument", "strike", "level", "want"), ROWS)
def test_intrinsic_value_is_the_old_settle_price(instrument, strike, level, want):
    value = intrinsic_value(instrument, D(strike), D(level))
    assert value == D(want) and isinstance(value, Decimal)


@pytest.mark.parametrize(("instrument", "strike", "level", "_want"), ROWS)
def test_the_engine_marks_a_leg_at_expiry_through_the_same_function(instrument, strike, level, _want):
    leg = Leg(Action.BUY, instrument, D(strike), None, 1, D("1"))  # type: ignore[arg-type] - expiry is not read
    assert legs._long_value_at(leg, D(level)) == intrinsic_value(instrument, D(strike), D(level))
    assert legs.expiry_value(leg, D(level)) == intrinsic_value(instrument, D(strike), D(level))

