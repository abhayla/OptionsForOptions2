"""REQ-034 AC-7 / ADR-082 (2) (W-075): the At Expiry scenario values include the round-trip charges, and a BOUGHT option
finishing in the money adds STT on exercise at that level's intrinsic value; SOLD options and out-of-the-money bought
options add none; Estimated Now and the per-leg rows are not touched.

Hand figures for the §6 condor (BUY 22800 PE 42.50, SELL 23000 PE 86.00, SELL 23400 CE 91.50, BUY 23600 CE 44.00, 75
units): premium 19,800 each side; brokerage 160 + STT 29.7 + exchange 14.06988 + SEBI 0.0396 + stamp 0.594 + GST
31.3397064 = 235.7431864 round trip. Exercise STT = 0.15% x intrinsic x 75: BUY 22800 PE at 22,000 -> 800 x 75 x
0.0015 = 90; BUY 23600 CE at 24,000 -> 400 x 75 x 0.0015 = 45.
"""
from datetime import date
from decimal import Decimal as D

from ofo.charges import ChargeRates
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import View, scenario_values

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")
ROUND_TRIP = D("235.7431864")


def values(golden, settings, rates=RATES, view=View.AT_EXPIRY):
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    return scenario_values(ls, golden, view, rates=rates)


def test_expiry_values_are_old_minus_round_trip_and_exercise_stt(golden, settings):
    plain, v = values(golden, settings, rates=None), values(golden, settings)
    assert v.charges == ROUND_TRIP
    old, new = dict(zip(plain.levels, plain.totals)), dict(zip(v.levels, v.totals))
    assert new[D("23047")] == D("6825") - ROUND_TRIP  # nothing bought is in the money
    assert new[D("22000")] == D("-8175") - ROUND_TRIP - D("90")  # bought 22800 PE: 800 x 75 x 0.15%
    assert new[D("24000")] == D("-8175") - ROUND_TRIP - D("45")  # bought 23600 CE: 400 x 75 x 0.15%
    for level in plain.levels:
        if level < D("22800"):
            extra = (D("22800") - level) * 75 * D("0.0015")
        elif level > D("23600"):
            extra = (level - D("23600")) * 75 * D("0.0015")
        else:
            extra = D("0")
        assert new[level] == old[level] - ROUND_TRIP - extra, level


def test_guard_a_sold_option_in_the_money_adds_no_exercise_stt(golden, settings):
    # at 22900 the SOLD 23000 PE is in the money by 100 and no bought option is
    plain, v = values(golden, settings, rates=None), values(golden, settings)
    assert dict(zip(v.levels, v.totals))[D("22900")] == dict(zip(plain.levels, plain.totals))[D("22900")] - ROUND_TRIP


def test_guard_charges_are_subtracted_never_added(golden, settings):
    plain, v = values(golden, settings, rates=None), values(golden, settings)
    assert all(n < o for n, o in zip(v.totals, plain.totals))


def test_guard_no_rates_leaves_the_values_exactly_as_before(golden, settings):
    plain = values(golden, settings, rates=None)
    assert plain.charges is None
    assert dict(zip(plain.levels, plain.totals))[D("23047")] == D("6825")


def test_guard_estimated_now_is_not_changed_by_rates(golden, settings):
    a = values(golden, settings, rates=None, view=View.ESTIMATED_NOW)
    b = values(golden, settings, view=View.ESTIMATED_NOW)
    assert a.totals == b.totals and b.charges is None


def test_guard_leg_rows_stay_the_legs_own_pnl(golden, settings):
    plain, v = values(golden, settings, rates=None), values(golden, settings)
    assert plain.leg_rows == v.leg_rows
