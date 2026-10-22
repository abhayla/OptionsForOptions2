"""ADR-167 (owner 2026-10-22; REQ-034 AC-7 as amended): EVERY scenario value is BEFORE charges and taxes, At Expiry and
Estimated Now alike; exercise STT is not in a curve; the round-trip charges are one separate breakdown from the
ADR-082 (1) rate table. Hand figures from scenario-calculations.md section 1 for the section 6 condor (BUY 22800 PE
42.50, SELL 23000 PE 86.00, SELL 23400 CE 91.50, BUY 23600 CE 44.00, 75 units), per unit then x 75:
 at 23,047 every option expires worthless: 86 + 91.5 - 42.5 - 44 = 91 -> 6,825;
 at 22,000: BUY PE 800 - 42.5 = 757.5, SELL PE 86 - 1000 = -914, CE legs 91.5 - 44 = 47.5 -> -109 -> -8,175
 (the same at 24,000);
 at 22,900: SELL 23000 PE value 100 -> -14, BUY PE -42.5, CE legs 47.5 -> -9 -> -675.
Round trip (each leg entered and left at its planned price): premium 19,800 each side; brokerage 160, STT 29.7,
exchange 14.06988, SEBI 0.0396, stamp 0.594, GST 31.3397064, total 235.7431864 -> 235.75 rounded up.
"""
from datetime import date
from decimal import Decimal as D

import pytest
from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesNotComputable, round_trip_breakdown
from ofo.engine.legs import Action, Instrument
from ofo.scenario.levels import build_level_set
from ofo.scenario.views import View, scenario_values
from scenario_fixtures import nifty_input, nifty_leg

RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://zerodha.com/charges")
ROUND_TRIP = D("235.75")  # 235.7431864 rounded UP to the paisa (ADR-082 (2))


def values(golden, settings, view=View.AT_EXPIRY):
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    return scenario_values(ls, golden, view)


def test_at_expiry_values_are_the_section_1_formula_before_charges(golden, settings):
    """AC-7: totals equal the hand figures with no charge and no exercise STT, including in the money at both wings."""
    v = values(golden, settings)
    by = dict(zip(v.levels, v.totals, strict=True))
    assert by[D("23047")] == D("6825")
    assert by[D("22000")] == D("-8175") and by[D("24000")] == D("-8175")
    assert by[D("22900")] == D("-675")


def test_guard_the_values_carry_no_charges_field_and_take_no_rates(golden, settings):
    """ADR-167: no 'charges' on the values, and passing rates is refused (red case: the old call shape)."""
    assert not hasattr(values(golden, settings), "charges")
    ls = build_level_set(golden, settings.for_index("NIFTY"))
    with pytest.raises(TypeError):
        scenario_values(ls, golden, View.AT_EXPIRY, rates=RATES)


def test_guard_leg_rows_sum_to_the_total_in_every_column(golden, settings):
    """AC-7: with no charges row, the leg rows add to the TOTAL exactly in every column."""
    v = values(golden, settings)
    for i, total in enumerate(v.totals):
        assert sum((row[i] for row in v.leg_rows), D("0")) == total


def test_guard_estimated_now_is_before_charges_too(golden, settings):
    v = values(golden, settings, view=View.ESTIMATED_NOW)
    assert not hasattr(v, "charges")
    for i, total in enumerate(v.totals):
        assert sum((row[i] for row in v.leg_rows), D("0")) == total


def test_the_breakdown_is_the_rate_table_by_component_and_totals_the_round_trip(golden):
    """ADR-167: components rounded half-even to the paisa, the total rounded up once (235.7431864 -> 235.75)."""
    b = round_trip_breakdown(golden.strategy.legs, "NIFTY", RATES)
    assert (b.brokerage, b.stt, b.exchange_transaction, b.sebi, b.stamp, b.gst, b.total) == (
        D("160.00"), D("29.70"), D("14.07"), D("0.04"), D("0.59"), D("31.34"), ROUND_TRIP)


def test_guard_a_futures_leg_has_no_rate_so_the_breakdown_refuses_instead_of_guessing(settings):
    fut = nifty_input([nifty_leg(Action.BUY, Instrument.FUT, None, "23000"),
                       nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349")])
    with pytest.raises(ChargesNotComputable):
        round_trip_breakdown(fut.strategy.legs, "NIFTY", RATES)
    ls = build_level_set(fut, settings.for_index("NIFTY"))
    assert scenario_values(ls, fut, View.AT_EXPIRY).available  # the curve itself still computes
