"""GC-IC1 step 1b (REQ-159 AC-4, S-06): the carry check's 2% gap figures at the next open, valued by the engine's
what-if estimate (``ofo.engine.model.estimate``), checked against an independent per-leg Black-Scholes sum (the
engine's ``bs_price`` per leg, q = 0 spot-fallback forward, years to the NEXT open, never expiry intrinsic), to the
paisa. Pure: the holiday table and ``now`` are passed in."""
from __future__ import annotations

import datetime
import sys
from decimal import ROUND_HALF_EVEN
from decimal import Decimal as D
from pathlib import Path

from ofo.adjustment import carry
from ofo.adjustment import playbook_eval as pe
from ofo.engine.black_scholes import bs_price, year_fraction
from ofo.engine.inputs import SpotReading, StrategyInput
from ofo.engine.legs import Action
from ofo.rules.inputs import DataHealth
from ofo.timeutil import IST

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scenario"))
from scenario_fixtures import GOLDEN_LEGS, RATE, gated, nifty_leg

FRI_1500 = datetime.datetime(2026, 10, 23, 15, 0, tzinfo=IST)  # a Friday session; next open Mon 26 Oct 09:15
NEXT_OPEN = datetime.datetime(2026, 10, 26, 9, 15, tzinfo=IST)
SPOT = D("23047")
BOOKED = D("-1250.50")
TABLE = {2026: frozenset({datetime.date(2026, 10, 20)})}


def _model(ivs: bool = True):
    legs = [nifty_leg(a, i, k, e, ltp, iv if ivs else None) for a, i, k, e, ltp, iv in GOLDEN_LEGS]
    return gated(StrategyInput(underlying="NIFTY", valuation_time=FRI_1500, rate=RATE, legs=tuple(legs),
                               spot=SpotReading(level=SPOT, at=FRI_1500, health=DataHealth.AVAILABLE)))


def _hand(level: D) -> D:
    """Independent: each leg's Black-Scholes value at ``level`` with years to the next open, P&L signed by side."""
    total = BOOKED
    for a, i, k, e, _ltp, iv in GOLDEN_LEGS:
        years = year_fraction(NEXT_OPEN, datetime.date(2026, 10, 27))  # to the 15:30 close of expiry day
        value = bs_price(i, level, D(k), years, RATE, D(iv))
        per = value - D(e) if a is Action.BUY else D(e) - value
        total += per * 75
    return total.quantize(D("0.01"), rounding=ROUND_HALF_EVEN)


def test_gap_levels_are_2_pct_up_and_down_rounded_to_a_paisa_point():
    assert carry.gap_levels(SPOT) == (D("23507.94"), D("22586.06"))


def test_core_gap_figures_equal_an_independent_leg_sum_at_the_next_open():
    figs = carry.carry_figures(_model(), BOOKED, D("98765.40"), FRI_1500, TABLE)
    assert figs.next_open == NEXT_OPEN
    assert figs.up == _hand(D("23507.94")) and figs.down == _hand(D("22586.06")), figs
    assert figs.gap_reason is None and figs.margin == D("98765.40") and figs.margin_reason is None
    assert figs.up != figs.down


def test_attack3_not_valued_at_expiry_intrinsic():
    figs = carry.carry_figures(_model(), BOOKED, None, FRI_1500, TABLE)
    up = D("23507.94")  # at expiry: short 23400 CE intrinsic 107.94, long 23600 CE 0, puts 0
    intrinsic = BOOKED + (D("-42.50") + D("86.00") + D("91.50") - D("107.94") - D("44.00")) * 75
    assert figs.up != intrinsic.quantize(D("0.01"))
    assert up > D("23400")


def test_margin_not_stated_says_so_never_a_number():
    figs = carry.carry_figures(_model(), BOOKED, None, FRI_1500, TABLE)
    assert figs.margin is None and figs.margin_reason == carry.MISSING_MARGIN and figs.up is not None


def test_a_leg_without_iv_gives_no_gap_figures_never_zero():
    figs = carry.carry_figures(_model(ivs=False), BOOKED, D("1"), FRI_1500, TABLE)
    assert figs.up is None and figs.down is None and figs.gap_reason == carry.CARRY_GAP_UNKNOWN


def test_no_spot_model_gives_no_gap_figures():
    figs = carry.carry_figures(None, BOOKED, D("1"), FRI_1500, TABLE)
    assert figs.up is None and figs.gap_reason == carry.CARRY_GAP_UNKNOWN


def test_next_open_in_a_year_with_no_holiday_list_is_not_known():
    figs = carry.carry_figures(_model(), BOOKED, D("1"), datetime.datetime(2026, 12, 31, 15, 0, tzinfo=IST), TABLE)
    assert figs.up is None and figs.gap_reason == pe.HOLIDAY_LIST_UNKNOWN and figs.next_open is None


def test_figures_are_exact_decimals_to_the_paisa():
    figs = carry.carry_figures(_model(), BOOKED, None, FRI_1500, TABLE)
    for v in (figs.up, figs.down):
        assert isinstance(v, D) and v == v.quantize(D("0.01"))


def test_gap_levels_exact_decimal_ties_round_half_even_never_through_float():
    # 0.75 x 1.02 = 0.765 exactly: half-even -> 0.76 (a float 0.765 is 0.76500000000000001 -> 0.77)
    assert carry.gap_levels(D("0.75"))[0] == D("0.76")
    assert carry.gap_levels(D("23500.25")) == (D("23970.26"), D("23030.24"))
