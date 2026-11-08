"""A-23 (GC-IC1 step 4a): net delta over EVERY leg, lots to the nearest whole lot (not truncated), the lot size used,
the remaining delta stated, a leg with no delta named as not known (never 0)."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from ofo.adjustment import delta_neutral as dn

SHORT_STRANGLE = [dn.LegDelta("SELL 23500 CE", "SELL", 3, D("0.55")),
                  dn.LegDelta("SELL 22700 PE", "SELL", 3, D("-0.05"))]


@pytest.mark.parametrize(("lot", "net", "future", "future_left"), [
    (65, D("-97.50"), 2, D("32.50")),  # 97.5 / 65 = 1.5 -> 2 (truncation would say 1)
    (75, D("-112.50"), 2, D("37.50")),  # 112.5 / 75 = 1.5 -> 2
])
def test_net_delta_sums_every_leg_and_the_future_lots_round_to_the_nearest_lot(lot, net, future, future_left):
    got = dn.figures(SHORT_STRANGLE, lot, D("0.50"), D("-0.50"))
    assert got.net_delta == net  # one leg only would give -107.25 / -123.75
    assert got.future == dn.Hedge(future, future_left)
    assert got.option_type == "CE"
    assert got.option == dn.Hedge(3, D("0"))  # 97.5 / 32.5 and 112.5 / 37.5 are exactly 3


def test_the_option_lots_round_down_below_a_half_and_state_what_is_left():
    got = dn.figures(SHORT_STRANGLE, 75, D("0.45"), D("-0.55"))
    assert got.option == dn.Hedge(3, D("-11.25"))  # 112.5 / 33.75 = 3.33 -> 3


def test_a_long_delta_position_is_brought_back_with_puts_and_a_short_future():
    got = dn.figures([dn.LegDelta("BUY 23500 CE", "BUY", 2, D("0.6"))], 75, D("0.5"), D("-0.5"))
    assert (got.net_delta, got.option_type) == (D("90.0"), "PE")
    assert got.option == dn.Hedge(2, D("15.0"))  # 90 / 37.5 = 2.4 -> 2 long puts
    assert got.future == dn.Hedge(-1, D("15.0"))  # 1.2 -> 1 short future


def test_a_leg_with_no_delta_is_not_known_naming_the_leg():
    legs = [*SHORT_STRANGLE, dn.LegDelta("BUY 24000 CE", "BUY", 3, None)]
    assert dn.figures(legs, 65, D("0.5"), D("-0.5")) == dn.NotKnown("BUY 24000 CE")


def test_an_atm_delta_not_known_still_gives_the_future():
    got = dn.figures(SHORT_STRANGLE, 65, None, D("-0.5"))
    assert got.option is None and got.future == dn.Hedge(2, D("32.50"))


def test_a_lot_below_one_is_refused():
    with pytest.raises(ValueError, match="lot size"):
        dn.figures(SHORT_STRANGLE, 0, D("0.5"), D("-0.5"))
