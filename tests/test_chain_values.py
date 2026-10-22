"""W-124 (REQ-087 AC-1/AC-4/AC-5, REQ-029 AC-3): the extra Option Chain values, computed once on the server.

Hand computation (written before the code), the REQ-087 AC-4 example: NIFTY 22,900 CE, LTP 150.00, spot 22,976.85, lot 65.
  intrinsic = 22976.85 - 22900 = 76.85;  time value = 150.00 - 76.85 = 73.15;  breakeven = 22900 + 150 = 23050;
  breakeven % = (23050 - 22976.85) / 22976.85 x 100 = 73.15 / 22976.85 x 100 = 0.31837... -> 0.32;
  per lot = 150.00 x 65 = 9750.00.
Put 23,100 PE, LTP 80.00, same spot: intrinsic = 23100 - 22976.85 = 123.15; time value = 80 - 123.15 = -43.15;
  breakeven = 23100 - 80 = 23020; % = (23020 - 22976.85) / 22976.85 x 100 = 43.15 / 22976.85 x 100 = 0.18779 -> 0.19.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.chain_values import CellValues, cell_values, chain_greeks

D = Decimal
SPOT = D("22976.85")
LOT = 65


def test_core_call_example_from_req_087_ac_4():
    v = cell_values("CE", D("22900"), D("150.00"), SPOT, LOT)
    assert v == CellValues(per_lot=D("9750.00"), intrinsic=D("76.85"), time_value=D("73.15"), breakeven=D("23050.00"),
                           breakeven_pct=D("0.32"))


def test_put_example_negative_time_value_is_shown_not_clamped():
    v = cell_values("PE", D("23100"), D("80.00"), SPOT, LOT)
    assert (v.intrinsic, v.time_value, v.breakeven, v.breakeven_pct, v.per_lot) == (
        D("123.15"), D("-43.15"), D("23020.00"), D("0.19"), D("5200.00"))


def test_out_of_the_money_has_zero_intrinsic_and_all_time_value():
    v = cell_values("CE", D("23000"), D("40.00"), SPOT, LOT)
    assert (v.intrinsic, v.time_value) == (D("0.00"), D("40.00"))


def test_no_spot_gives_a_dash_not_zero_for_spot_dependent_values_and_keeps_the_rest():
    v = cell_values("CE", D("22900"), D("150.00"), None, LOT)
    assert (v.intrinsic, v.time_value, v.breakeven_pct) == (None, None, None)
    assert (v.per_lot, v.breakeven) == (D("9750.00"), D("23050.00"))


@pytest.mark.parametrize("ltp", [None, D("0"), D("0.00")])
def test_missing_or_zero_ltp_is_absent_never_zero(ltp):
    v = cell_values("PE", D("22900"), ltp, SPOT, LOT)
    assert v.intrinsic == D("0.00")  # 22900 put, spot 22976.85: out of the money, a real zero
    assert v.per_lot is None and v.time_value is None and v.breakeven is None and v.breakeven_pct is None


def test_put_breakeven_at_or_below_zero_is_a_dash():
    assert cell_values("PE", D("50"), D("60"), SPOT, LOT).breakeven is None


def test_sensex_lot_20_per_lot():
    assert cell_values("CE", D("80000"), D("12.50"), D("80010"), 20).per_lot == D("250.00")


def test_a_future_is_not_an_option_side():
    with pytest.raises(ValueError):
        cell_values("FUT", D("1"), D("1"), SPOT, LOT)


def test_greeks_without_a_spot_quote_are_empty_not_guessed():
    import datetime
    now = datetime.datetime(2026, 10, 22, 10, 0, tzinfo=datetime.timezone.utc)
    assert chain_greeks([], None, datetime.date(2026, 10, 27), now, D("0.065")) == {}
