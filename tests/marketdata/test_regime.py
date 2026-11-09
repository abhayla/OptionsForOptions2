"""GC-ICTRACK task 25 (ADR-280 (6), (12)): VIX percentile and Wilder's ADX on hand-worked numbers."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from ofo.marketdata.regime import adx, vix_percentile

# Hand-worked ADX, period 2 (H, L, C):
#   b0 10 8 9 | b1 12 9 11: +DM 2, -DM 0, TR 3 | b2 11 7 8: +DM 0, -DM 2, TR 4
#   b3 13 9 12: +DM 2, -DM 0, TR 5 | b4 14 11 13: +DM 1, -DM 0, TR 3
#   seed (b1, b2): TR 7, +DM 2, -DM 2 -> DX 0
#   b3: TR 7 - 3.5 + 5 = 8.5, +DM 2 - 1 + 2 = 3, -DM 2 - 1 + 0 = 1 -> DX 100 x 2 / 4 = 50
#   first ADX = (0 + 50) / 2 = 25
#   b4: +DM 3 - 1.5 + 1 = 2.5, -DM 1 - 0.5 = 0.5 -> DX 100 x 2 / 3 = 66.67; ADX = (25 + 66.67) / 2 = 275 / 6
FIVE = [(D(10), D(8), D(9)), (D(12), D(9), D(11)), (D(11), D(7), D(8)), (D(13), D(9), D(12)), (D(14), D(11), D(13))]


def test_adx_period_2_equals_the_hand_worked_275_over_6():
    assert abs(adx(FIVE, period=2) - D(275) / D(6)) < D("1e-25")  # 275/6 here is at the default 28 digits


def test_adx_of_the_first_four_bars_is_the_seed_average_25():
    assert adx(FIVE[:4], period=2) == D(25)


def test_a_steady_one_point_rise_every_day_is_adx_100_trending():
    # each day H = C + 1, L = C - 1, C up by 1: +DM 1, -DM 0 every day -> DX 100 every day -> ADX 100
    bars = [(D(100 + i + 1), D(100 + i - 1), D(100 + i)) for i in range(30)]
    assert adx(bars) == D(100)


def test_an_alternating_market_reads_range_bound():
    bars = [(D(101 + i % 2), D(99 + i % 2), D(100 + i % 2)) for i in range(60)]
    assert adx(bars) <= D(20)


@pytest.mark.parametrize("bars", [
    FIVE[:3],                                             # fewer than 2 x period
    [*FIVE[:3], (D(10), D(12), D(11))],                   # low above high
    [*FIVE[:3], (D(10), D(0), D(9))],                     # a non-positive price
    [(D(1), D(1), D(1))] * 4,                             # every bar flat: no true range
])
def test_adx_refuses_bad_input(bars):
    with pytest.raises(ValueError):
        adx(bars, period=2)


def test_vix_percentile_hand_worked_60():
    assert vix_percentile(D(14), [D(10), D(12), D(14), D(16), D(18)], sessions=5) == D(60)  # 3 of 5 at or below


def test_vix_percentile_uses_only_the_last_sessions_and_the_extremes():
    closes = [D(99)] * 10 + [D(10), D(12), D(14), D(16), D(18)]
    assert vix_percentile(D(9), closes, sessions=5) == D(0)
    assert vix_percentile(D(18), closes, sessions=5) == D(100)


@pytest.mark.parametrize(("vix", "closes"), [
    (D(14), [D(10)] * 249),          # fewer than 250 closes: not the 250-session percentile
    (D(0), [D(10)] * 250),           # no VIX
    (D(14), [D(10)] * 249 + [D(-1)]),  # a bad close
    (14.0, [D(10)] * 250),           # a float, never
])
def test_vix_percentile_refuses_bad_input(vix, closes):
    with pytest.raises(ValueError):
        vix_percentile(vix, closes)
