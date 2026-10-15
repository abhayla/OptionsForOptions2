"""AC-6: every guard and side rule of the charges calculator has a test that dies without it (W-074).

Spec basis: REQ-032 AC-4 ("All money is computed in exact decimal or integer paise, never binary floating point");
ADR-082 ("every amount is exact Decimal; STT and stamp duty are not rounded at order level").

Expected values are hand computations (stated in each test), not calculator output.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from ofo.charges import SEGMENTS, ChargeOrder, ChargeRates, charges_for_order, charges_for_orders, exercise_stt

D = Decimal


def rates(**changes) -> ChargeRates:
    base = ChargeRates(
        brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
        transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
        stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 10, 15), source_url="https://example/x")
    return replace(base, **changes)


def test_stt_only_on_sell_and_stamp_only_on_buy():
    """AC-6: premium 1000 (10.00 x 100): SELL stt = 1.5, stamp 0; BUY stt 0, stamp = 0.03 (hand: 1000 x 0.00003)."""
    sell = charges_for_order(ChargeOrder("NSE_FO", "SELL", 100, D("10.00")), rates())
    buy = charges_for_order(ChargeOrder("NSE_FO", "BUY", 100, D("10.00")), rates())
    assert (sell.stt, sell.stamp) == (D("1.5"), D("0"))
    assert (buy.stt, buy.stamp) == (D("0"), D("0.03"))


def test_gst_base_is_brokerage_plus_sebi_plus_transaction():
    """AC-6: premium 1000: transaction 0.3553, sebi 0.001; gst = 0.18 x (20 + 0.001 + 0.3553) = 3.664 (hand: 20.3563 x
    0.18 = 3.664134)."""
    got = charges_for_order(ChargeOrder("NSE_FO", "BUY", 100, D("10")), rates())
    assert got.gst == D("3.664134")


def test_bse_uses_its_own_rate():
    """AC-6: 1 lot SENSEX option, 20 units at 150.00 = premium 3000; BSE 0.0325% = 0.975 (hand: 3000 x 0.000325)."""
    got = charges_for_order(ChargeOrder("BSE_FO", "BUY", 20, D("150.00")), rates())
    assert got.exchange_transaction == D("0.975")
    assert got.gst == (D("20") + D("0.003") + D("0.975")) * D("0.18")


def test_nothing_is_rounded_at_order_level():
    """AC-6 (ADR-082): premium 3.95 x 65 = 256.75; stt 0.385125 keeps all six places (hand: 256.75 x 0.0015)."""
    got = charges_for_order(ChargeOrder("NSE_FO", "SELL", 65, D("3.95")), rates())
    assert got.stt == D("0.385125")


def test_total_is_the_sum_of_its_components():
    """AC-6: total = brokerage + stt + transaction + sebi + stamp + gst for an order."""
    got = charges_for_order(ChargeOrder("NSE_FO", "SELL", 65, D("53.3")), rates())
    assert got.total == got.brokerage + got.stt + got.exchange_transaction + got.sebi + got.stamp + got.gst


def test_a_float_price_is_refused():
    """AC-6 (REQ-032 AC-4): price=3.95 as a float raises."""
    with pytest.raises(ValueError, match="Decimal"):
        ChargeOrder("NSE_FO", "BUY", 65, 3.95)  # type: ignore[arg-type]


def test_a_float_rate_is_refused():
    with pytest.raises(ValueError, match="Decimal"):
        rates(gst_rate=0.18)


@pytest.mark.parametrize("quantity", [0, -1, 65.0, True, 10_000_001, "65"])
def test_bad_quantity_is_refused(quantity):
    with pytest.raises(ValueError, match="quantity"):
        ChargeOrder("NSE_FO", "BUY", quantity, D("1"))


@pytest.mark.parametrize("price", [D("-0.05"), D("0"), D("NaN"), D("Infinity"), D("100000001")])
def test_bad_price_is_refused(price):
    with pytest.raises(ValueError, match="price"):
        ChargeOrder("NSE_FO", "BUY", 65, price)


@pytest.mark.parametrize("side", ["buy", "HOLD", "", None])
def test_side_is_an_allow_list(side):
    with pytest.raises(ValueError, match="side"):
        ChargeOrder("NSE_FO", side, 65, D("1"))  # type: ignore[arg-type]


@pytest.mark.parametrize("segment", ["NSE_CM", "NFO", "", "nse_fo"])
def test_unknown_segment_has_no_default_rate(segment):
    with pytest.raises(ValueError, match="segment"):
        charges_for_order(ChargeOrder(segment, "BUY", 65, D("1")), rates())


def test_no_orders_is_refused():
    with pytest.raises(ValueError, match="no orders"):
        charges_for_orders([], rates())


@pytest.mark.parametrize("name", ["brokerage_per_order", "stt_sell_rate", "stt_exercise_rate", "sebi_rate",
                                  "stamp_buy_rate", "gst_rate"])
@pytest.mark.parametrize("bad", [D("-0.1"), D("NaN"), D("Infinity")])
def test_bad_rate_is_refused(name, bad):
    with pytest.raises(ValueError, match=name):
        rates(**{name: bad})


@pytest.mark.parametrize("keys", [{"NSE_FO": D("0.1")}, {"NSE_FO": D("0.1"), "BSE_FO": D("0.1"), "MCX": D("0.1")},
                                  {}])
def test_transaction_rates_have_exactly_the_closed_segment_set(keys):
    assert set(SEGMENTS) == {"NSE_FO", "BSE_FO"}
    with pytest.raises(ValueError, match="segments"):
        rates(transaction_rates=keys)


def test_a_negative_segment_rate_is_refused():
    with pytest.raises(ValueError, match="transaction_rates"):
        rates(transaction_rates={"NSE_FO": D("-0.1"), "BSE_FO": D("0.1")})


def test_read_date_and_source_are_required():
    with pytest.raises(ValueError, match="read_on"):
        rates(read_on=datetime(2026, 10, 15, 9, 0))
    with pytest.raises(ValueError, match="read_on"):
        rates(read_on="2026-10-15")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source_url"):
        rates(source_url="  ")


def test_rates_cannot_be_changed_after_construction():
    r = rates()
    with pytest.raises(TypeError):
        r.transaction_rates["NSE_FO"] = D("0.5")  # type: ignore[index]


def test_exercise_stt_is_rate_times_intrinsic_times_quantity():
    """AC-6: bought 23000 CE settles at 23100: intrinsic 100 x 65 x 0.15% = 9.75 (hand: 6500 x 0.0015)."""
    assert exercise_stt(D("100"), 65, rates()) == D("9.75")
    assert exercise_stt(D("100"), 65, rates(stt_exercise_rate=D("0.002"))) == D("13")


def test_exercise_stt_refuses_bad_input():
    with pytest.raises(ValueError, match="intrinsic"):
        exercise_stt(D("-1"), 65, rates())
    with pytest.raises(ValueError, match="intrinsic"):
        exercise_stt(100.0, 65, rates())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="quantity"):
        exercise_stt(D("1"), 0, rates())


@pytest.mark.parametrize("name", ["stt_sell_rate", "stt_exercise_rate", "sebi_rate", "stamp_buy_rate"])
def test_a_percentage_typed_as_a_fraction_is_refused(name):
    """AC-6: Zerodha prints 0.15%; Decimal("0.15") would make STT 100x (519.675 instead of 5.19675 on the 3464.50
    premium). A percentage-type rate must be a fraction below 1%."""
    with pytest.raises(ValueError, match="fraction"):
        rates(**{name: D("0.15")})
    assert rates(**{name: D("0.0099")})  # just under the cap is accepted


def test_a_percentage_exchange_rate_is_refused_and_gst_keeps_its_own_cap():
    with pytest.raises(ValueError, match="fraction"):
        rates(transaction_rates={"NSE_FO": D("0.03553"), "BSE_FO": D("0.000325")})
    with pytest.raises(ValueError, match="fraction"):
        rates(gst_rate=D("18"))
    assert rates(gst_rate=D("0.18")).gst_rate == D("0.18")


def test_brokerage_is_rupees_not_a_fraction():
    assert rates(brokerage_per_order=D("20")).brokerage_per_order == D("20")
