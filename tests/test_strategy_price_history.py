"""GC-UI step 5 server (D-B40 / D-B41; REQ-091 AC-2..AC-5, ADR-203, F-64): the Strategy Chart's data.

Core proof: the REAL Kite minute bodies measured in F-64 (2026-10-14, 09:15-15:29 IST, trimmed from the recorded
2026-10-14..28 bodies; market data only, no funds, no token). A one-leg BUY of NIFTY 03-Nov 25000 CE is -5.40 at 09:15
(the leg's close, a debit negative), the NIFTY Nov future's close is 22841.1, and every minute the future has but the
leg lacks is a gap (83 of 375 minutes that day), never interpolated."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine.legs import Action
from ofo.engine.money_summary import combined_price_per_unit, combined_price_series
from ofo.history.candles import parse_candles
from ofo.outcome import price_history as ph
from ofo.timeutil import IST

FIX = Path(__file__).parent / "fixtures" / "kite_history"
LEG_ID, FUT_ID = "NSE_FO:25000CE", "NSE_FO:NIFTYFUT"
LEG_BARS = parse_candles((FIX / "minute-NIFTY26N0325000CE-2026-10-14.json").read_text(encoding="utf-8"), LEG_ID)
FUT_BARS = parse_candles((FIX / "minute-NIFTY26NOVFUT-2026-10-14.json").read_text(encoding="utf-8"), FUT_ID)
AT_0915 = datetime.datetime(2026, 10, 14, 9, 15, tzinfo=IST)
MINUTES_ON_14_OCT, MINUTES_ON_TWO_DAYS = 375, 750
GAPS_ON_14_OCT = 83  # counted from the two recorded bodies: 375 future minutes, 292 leg minutes, all inside the 375


@dataclasses.dataclass(frozen=True)
class Leg:
    action: Action
    lots: int


BUY1 = Leg(Action.BUY, 1)


def _closes(bars):
    return {b.minute: b.close for b in bars}


# ---- the core: real bodies through the one engine -----------------------------------------------------------------

def test_core_real_bodies_one_leg_buy():
    minutes = [b.minute for b in FUT_BARS]
    series = combined_price_series([BUY1], [_closes(LEG_BARS)], minutes)
    assert len(minutes) == MINUTES_ON_14_OCT and minutes[0] == AT_0915
    assert series[0] == Decimal("-5.4") and type(series[0]) is Decimal
    assert FUT_BARS[0].close == Decimal("22841.1") and type(FUT_BARS[0].close) is Decimal
    assert sum(v is None for v in series) == GAPS_ON_14_OCT
    gap_at = minutes.index(datetime.datetime(2026, 10, 14, 9, 51, tzinfo=IST))  # the first minute the leg lacks
    assert series[gap_at] is None and series[gap_at - 1] is not None  # a gap, not the previous close carried


def test_core_chart_points_on_real_bodies():
    chart = ph.build_chart([BUY1], [LEG_BARS], FUT_BARS, leg_labels=["25000 CE"], days=10)
    first = chart.points[0]
    assert first.t == AT_0915 and first.strategy == Decimal("-5.4") and first.future == Decimal("22841.1")
    assert ph.strategy_display(first.strategy) == "-5.40" and ph.future_display(first.future) == "22,841.10"
    assert sum(p.strategy is None for p in chart.points) == GAPS_ON_14_OCT
    assert len(chart.points) == MINUTES_ON_14_OCT and chart.as_of == datetime.datetime(2026, 10, 14, 15, 29, tzinfo=IST)
    assert chart.notes == () and chart.state is ph.State.AVAILABLE


# ---- the quantity rule (REQ-091 AC-2 + ADR-203 consequence 1) -----------------------------------------------------

def test_ac2_example_equal_lots():
    legs = [Leg(Action.BUY, 2), Leg(Action.SELL, 2)]
    assert combined_price_per_unit(legs, [Decimal("81.30"), Decimal("30.00")]) == Decimal("-51.30")


def test_ratio_one_buy_two_sells():
    legs = [Leg(Action.BUY, 1), Leg(Action.SELL, 2)]
    assert combined_price_per_unit(legs, [Decimal("81.30"), Decimal("30.00")]) == Decimal("-21.30")
    legs = [Leg(Action.BUY, 2), Leg(Action.SELL, 4)]  # gcd 2: the same per-unit figure
    assert combined_price_per_unit(legs, [Decimal("81.30"), Decimal("30.00")]) == Decimal("-21.30")


def test_sell_is_positive_and_invert_flips_only_the_strategy():
    assert combined_price_per_unit([Leg(Action.SELL, 1)], [Decimal("5.40")]) == Decimal("5.40")
    assert combined_price_per_unit([BUY1], [Decimal("5.40")], invert=True) == Decimal("5.40")
    chart = ph.build_chart([BUY1], [LEG_BARS], FUT_BARS, leg_labels=["25000 CE"], days=10, invert=True)
    assert chart.points[0].strategy == Decimal("5.4") and chart.points[0].future == Decimal("22841.1")


def test_any_leg_without_a_close_is_a_gap():
    assert combined_price_per_unit([BUY1, Leg(Action.SELL, 1)], [Decimal("1"), None]) is None


@pytest.mark.parametrize("lots", [0, -1, True])
def test_bad_lots_refused(lots):
    with pytest.raises(ValueError):
        combined_price_per_unit([Leg(Action.BUY, lots)], [Decimal("1")])


# ---- answer states -------------------------------------------------------------------------------------------------

def _shift(bars, days):
    return [dataclasses.replace(b, minute=b.minute + datetime.timedelta(days=days)) for b in bars]


def test_window_is_the_last_n_trading_days_of_the_future():
    fut = FUT_BARS + _shift(FUT_BARS, 1) + _shift(FUT_BARS, 2)
    leg = LEG_BARS + _shift(LEG_BARS, 1) + _shift(LEG_BARS, 2)
    chart = ph.build_chart([BUY1], [leg], fut, leg_labels=["25000 CE"], days=2)
    assert chart.points[0].t == AT_0915 + datetime.timedelta(days=1) and len(chart.points) == MINUTES_ON_TWO_DAYS


def test_a_leg_listed_inside_the_window_starts_it_with_a_note():
    fut = FUT_BARS + _shift(FUT_BARS, 1)
    chart = ph.build_chart([BUY1], [_shift(LEG_BARS, 1)], fut, leg_labels=["25000 CE"], days=10)
    assert chart.points[0].t == AT_0915 + datetime.timedelta(days=1)
    assert chart.notes == (("leg_listed_from", "25000 CE", datetime.date(2026, 10, 15), 1),)


def test_an_expired_leg_ends_the_window_at_its_last_candle():
    fut = FUT_BARS + _shift(FUT_BARS, 1)
    chart = ph.build_chart([BUY1], [LEG_BARS], fut, leg_labels=["25000 CE"], days=10)
    assert chart.points[-1].t == LEG_BARS[-1].minute
    assert chart.notes == (("leg_ended_on", "25000 CE", datetime.date(2026, 10, 14)),)


def test_a_leg_with_no_candles_is_not_listed():
    chart = ph.build_chart([BUY1], [[]], FUT_BARS, leg_labels=["25000 CE"], days=10)
    assert chart.state is ph.State.LEG_NOT_LISTED and chart.points == () and chart.missing_leg == "25000 CE"


def test_every_minute_a_gap():
    even = [b for b in FUT_BARS if b.minute.minute % 2 == 0]
    odd = [b for b in FUT_BARS if b.minute.minute % 2 == 1]  # the two legs never share a minute
    chart = ph.build_chart([BUY1, BUY1], [even, odd], FUT_BARS, leg_labels=["A", "B"], days=10)
    assert chart.state is ph.State.ALL_GAPS


def test_no_future_candles():
    chart = ph.build_chart([BUY1], [LEG_BARS], [], leg_labels=["25000 CE"], days=10)
    assert chart.state is ph.State.NO_FUTURE_CANDLES and chart.points == ()


def test_a_futures_leg_and_a_calendar_combine_like_any_leg():
    chart = ph.build_chart([Leg(Action.SELL, 1), Leg(Action.BUY, 1)], [FUT_BARS, LEG_BARS], FUT_BARS,
                           leg_labels=["NIFTY Nov FUT", "25000 CE"], days=10)
    assert chart.points[0].strategy == Decimal("22841.1") - Decimal("5.4")
    assert sum(p.strategy is None for p in chart.points) == GAPS_ON_14_OCT


def test_an_int_close_ends_up_decimal():
    assert FUT_BARS[0].open == Decimal(22900) and type(FUT_BARS[0].open) is Decimal  # the body holds 22900 (int)
