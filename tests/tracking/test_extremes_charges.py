"""F-94 (ADR-082 (2), ADR-008): the paper book's original Max Profit / Max Loss include the round-trip charges, equal to
the builder's figures for the same legs (one engine, one number), to the paisa."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.charges import ChargeRates
from ofo.charges.round_trip import round_trip_charges
from ofo.engine.extremes import ContractTerms, book_extremes
from ofo.engine.extremes_charges import (
    BookAfterCharges,
    book_after_charges,
    open_exit_charges,
    open_round_trip_charges,
    sum_after_charges,
    with_charges,
)
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import strategy_metrics
from ofo.engine.orderbook import BookView, PaperOrder, net_positions
from ofo.engine.strategy import Strategy

D = Decimal
EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
# an iron condor: (contract id, instrument, strike, BUY or SELL, price)
LEGS = (("1", Instrument.PE, D("22600"), "BUY", D("60.65")), ("2", Instrument.PE, D("22700"), "SELL", D("86.35")),
        ("3", Instrument.CE, D("22950"), "SELL", D("107.50")), ("4", Instrument.CE, D("23000"), "BUY", D("86.95")))


def _book():
    orders = [PaperOrder(cid, side, LOT, price, "open", T0) for cid, _, _, side, price in LEGS]
    terms = {cid: ContractTerms(kind, strike, EXPIRY) for cid, kind, strike, _, _ in LEGS}
    return net_positions(orders, {}), terms


def _builder_figures() -> tuple[Decimal, Decimal, Decimal]:
    strategy = Strategy(tuple(Leg(Action(side), kind, strike, EXPIRY, LOT, price)
                              for _, kind, strike, side, price in LEGS))
    charges = round_trip_charges(strategy.legs, "NIFTY", RATES)
    m = strategy_metrics(strategy)
    return m.max_profit - charges, m.max_loss + charges, charges  # outcome.service._summary, ADR-082 (2)


def test_core_paper_max_profit_and_loss_equal_the_builders_charges_inclusive_figures_to_the_paisa() -> None:
    view, terms = _book()
    gross = book_extremes(view, terms, {})
    charges = open_round_trip_charges(view, terms, "NIFTY", RATES)
    got = with_charges(gross, charges)
    profit, loss, builder_charges = _builder_figures()
    assert charges == builder_charges
    assert (got.max_profit, got.max_loss) == (profit, -loss)  # the builder's loss is a magnitude, the book's is signed
    assert (gross.max_profit, gross.max_loss, charges) == (D("3006.25"), D("-3493.75"), D("241.42"))  # hand check
    assert (got.max_profit, got.max_loss) == (D("2764.83"), D("-3735.17"))


def test_no_rates_or_nothing_open_leaves_the_figures_before_charges() -> None:
    view, terms = _book()
    gross = book_extremes(view, terms, {})
    assert open_round_trip_charges(view, terms, "NIFTY", None) is None
    assert with_charges(gross, None) == gross


# --- GC-ICFIX u122/u123: the one after-charges total (ADR-263, ADR-008) ---------------------------------------------
def _closed(total: str) -> BookView:
    return BookView((), D(total), D(0), D(total), D(0))


def _one_short_put(live: dict[str, Decimal]):
    terms = {"1": ContractTerms(Instrument.PE, D("22700"), EXPIRY)}
    return net_positions([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], live), terms


def test_core_real_case_strategy_141_closed_is_minus_32_50_before_and_minus_435_95_after() -> None:
    got = book_after_charges(_closed("-32.50"), D("403.45"), D("0"))
    assert got == BookAfterCharges(D("-32.50"), D("-435.95"), D("403.45"), D("0"), None)  # hand: -32.50 - 403.45 - 0
    assert isinstance(got.total_after, Decimal)


def test_core_real_case_strategy_139_closed_is_minus_159_25_before_and_minus_511_65_after() -> None:
    got = book_after_charges(_closed("-159.25"), D("352.40"), D("0"))
    assert (got.total_before, got.total_after) == (D("-159.25"), D("-511.65"))  # hand: -159.25 - 352.40


def test_a_closed_book_has_no_exit_estimate_whatever_the_rates() -> None:
    view = _closed("-32.50")
    assert open_exit_charges(view, {}, {}, "NIFTY", None) == (D("0"), None)
    assert open_exit_charges(view, {}, {}, "NIFTY", RATES) == (D("0"), None)


def test_an_open_book_at_live_prices_takes_off_paid_and_the_estimated_exit() -> None:
    # SELL 65 @ 100.00 now at 80.00: unbooked (100 - 80) x 65 = +1,300.00.
    # Exit = BUY 65 @ 80 (premium 5,200): brokerage 20 + transaction 5200 x 0.0003553 = 1.84756 + SEBI 0.0052
    #   + stamp 5200 x 0.00003 = 0.156 + GST (20 + 0.0052 + 1.84756) x 0.18 = 3.9334968 -> 25.9422568, rounded up 25.95.
    # Paid = the SELL @ 100 (premium 6,500): 20 + STT 9.75 + 2.30945 + 0.0065 + 0 + GST 4.016871 = 36.082821 -> 36.09.
    # After = 1,300.00 - 36.09 - 25.95 = 1,237.96.
    view, terms = _one_short_put({"1": D("80")})
    exit_, why = open_exit_charges(view, terms, {"1": D("80")}, "NIFTY", RATES)
    assert (exit_, why) == (D("25.95"), None)
    got = book_after_charges(view, D("36.09"), exit_)
    assert (got.total_before, got.total_after, got.reason) == (D("1300"), D("1237.96"), None)


def test_charge_rates_unknown_gives_no_after_figure_with_the_reason_and_keeps_the_before_figure() -> None:
    view, terms = _one_short_put({"1": D("80")})
    exit_, why = open_exit_charges(view, terms, {"1": D("80")}, "NIFTY", None)
    assert (exit_, why) == (None, "rates_unavailable")
    got = book_after_charges(view, D("36.09"), exit_, why)
    assert (got.total_before, got.total_after, got.reason) == (D("1300"), None, "rates_unavailable")


def test_paid_absent_gives_no_after_figure_with_the_reason_never_zero() -> None:
    got = book_after_charges(_closed("-32.50"), None, D("0"), "not_priced")
    assert (got.total_before, got.total_after, got.reason) == (D("-32.50"), None, "not_priced")
    assert book_after_charges(_closed("-32.50"), None, D("0")).reason == "rates_unavailable"  # never a bare None


def test_a_futures_leg_cannot_be_priced_so_no_after_figure_not_priced() -> None:
    terms = {"1": ContractTerms(Instrument.FUT, None, EXPIRY)}
    view = net_positions([PaperOrder("1", "BUY", LOT, D("100"), "open", T0)], {"1": D("101")})
    assert open_exit_charges(view, terms, {"1": D("101")}, "NIFTY", RATES) == (None, "not_priced")


def test_an_unknown_underlying_or_a_refused_price_is_not_priced_and_never_a_silent_zero() -> None:
    view, terms = _one_short_put({"1": D("80")})
    assert open_exit_charges(view, terms, {"1": D("80")}, "BANKNIFTY", RATES) == (None, "not_priced")
    assert open_exit_charges(view, terms, {"1": D("0")}, "NIFTY", RATES) == (None, "not_priced")  # price must be > 0


def test_an_open_leg_without_a_live_price_gives_no_exit_estimate_and_no_total_prices_not_live() -> None:
    view, terms = _one_short_put({})  # no live price: the engine's own unbooked / total are absent
    assert view.total is None
    assert open_exit_charges(view, terms, {}, "NIFTY", RATES) == (None, "prices_not_live")
    got = book_after_charges(view, D("36.09"), D("0"))
    assert (got.total_before, got.total_after, got.reason) == (None, None, "prices_not_live")


def test_one_of_two_open_legs_without_a_price_is_prices_not_live() -> None:
    terms = {"1": ContractTerms(Instrument.PE, D("22700"), EXPIRY),
             "2": ContractTerms(Instrument.CE, D("22950"), EXPIRY)}
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0), PaperOrder("2", "SELL", LOT, D("90"), "open", T0)]
    view = net_positions(orders, {"1": D("80")})
    assert open_exit_charges(view, terms, {"1": D("80")}, "NIFTY", RATES) == (None, "prices_not_live")


def test_an_empty_book_is_refused_by_the_engine_not_given_a_zero() -> None:
    with pytest.raises(ValueError, match="at least one order"):
        net_positions([], {})


# --- round 2: every money behaviour of the after figure has a test that fails when it is broken ---------------------
def _after_of(orders: list[PaperOrder], terms: dict[str, ContractTerms], live: dict[str, Decimal], paid: str):
    view = net_positions(orders, live)
    exit_, why = open_exit_charges(view, terms, live, "NIFTY", RATES)
    assert why is None
    return view, exit_, book_after_charges(view, D(paid), exit_)


_PUT = {"1": ContractTerms(Instrument.PE, D("22700"), EXPIRY)}
_CALL = {"2": ContractTerms(Instrument.CE, D("22950"), EXPIRY)}


def test_a_long_leg_exits_with_a_sell_so_the_exit_carries_stt_not_stamp_duty() -> None:
    # BUY 65 @ 100 now 120: unbooked (120 - 100) x 65 = +1,300.00.
    # Paid, the BUY (premium 6,500): 20 + transaction 2.30945 + SEBI 0.0065 + stamp 0.195 + GST (20 + 0.0065 + 2.30945)
    #   x 0.18 = 4.016871 -> 26.528821 -> 26.53.
    # Exit, SELL 65 @ 120 (premium 7,800): 20 + STT 11.70 + transaction 2.77134 + SEBI 0.0078 + GST (20 + 0.0078 +
    #   2.77134) x 0.18 = 4.1002452 -> 38.5793852 -> 38.58 (a BUY exit would be 26.9 and have no STT).
    # After = 1,300.00 - 26.53 - 38.58 = 1,234.89.
    _, exit_, got = _after_of([PaperOrder("1", "BUY", LOT, D("100"), "open", T0)], _PUT, {"1": D("120")}, "26.53")
    assert exit_ == D("38.58")
    assert (got.total_before, got.total_after) == (D("1300"), D("1234.89"))


def test_the_exit_is_priced_on_the_open_quantity_only_not_a_lot_of_65() -> None:
    # SELL 130 @ 100 now 80: unbooked 20 x 130 = +2,600.00.
    # Exit BUY 130 @ 80 (premium 10,400): 20 + transaction 3.69512 + SEBI 0.0104 + stamp 0.312 + GST (20 + 0.0104 +
    #   3.69512) x 0.18 = 4.2669936 -> 28.2845136 -> 28.29 (65 units would be 25.95).
    # Paid, the SELL (premium 13,000): 20 + STT 19.50 + 4.6189 + 0.013 + GST (20 + 0.013 + 4.6189) x 0.18 = 4.433742
    #   -> 48.565642 -> 48.57. After = 2,600.00 - 48.57 - 28.29 = 2,523.14.
    _, exit_, got = _after_of([PaperOrder("1", "SELL", 2 * LOT, D("100"), "open", T0)], _PUT, {"1": D("80")}, "48.57")
    assert exit_ == D("28.29")
    assert got.total_after == D("2523.14")


def test_a_partly_closed_book_prices_the_exit_on_what_is_still_open() -> None:
    # SELL 130 @ 100, BUY 65 @ 90 (exit): booked (100 - 90) x 65 = 650;
    # open 65 now 80: unbooked 20 x 65 = 1,300; total 1,950.
    # Paid = SELL 130 @ 100 (48.565642) + BUY 65 @ 90 (premium 5,850: 20 + 2.078505 + 0.00585 + stamp 0.1755 + GST
    #   3.9751839 = 26.2350389) = 74.8006809 -> 74.81. Exit BUY 65 @ 80 = 25.95.
    # After = 1,950.00 - 74.81 - 25.95 = 1,849.24.
    orders = [PaperOrder("1", "SELL", 2 * LOT, D("100"), "open", T0), PaperOrder("1", "BUY", LOT, D("90"), "exit", T0)]
    view, exit_, got = _after_of(orders, _PUT, {"1": D("80")}, "74.81")
    assert (view.booked, exit_, got.total_before, got.total_after) == (D("650"), D("25.95"), D("1950"), D("1849.24"))


def test_a_reopened_leg_is_priced_at_its_new_open_position() -> None:
    # SELL 65 @ 100, BUY 65 @ 90 (exit), SELL 65 @ 95 (reopen); now 80.
    # Booked 650; unbooked (95 - 80) x 65 = 975; total 1,625.
    # Paid = 36.082821 + 26.2350389 + SELL 65 @ 95 (premium 6,175: 20 + STT 9.2625 + 2.1939775 + 0.006175 + GST
    #   3.99602745 = 35.45867995) = 97.77653985 -> 97.78. Exit BUY 65 @ 80 = 25.95.
    # After = 1,625.00 - 97.78 - 25.95 = 1,501.27.
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0), PaperOrder("1", "BUY", LOT, D("90"), "exit", T0),
              PaperOrder("1", "SELL", LOT, D("95"), "open", T0)]
    _, exit_, got = _after_of(orders, _PUT, {"1": D("80")}, "97.78")
    assert (exit_, got.total_before, got.total_after) == (D("25.95"), D("1625"), D("1501.27"))


def test_a_mixed_long_and_short_book_rounds_the_exit_once_over_both_legs() -> None:
    # SELL 65 @ 100 (put, now 80) +1,300 and BUY 65 @ 100 (call, now 120) +1,300: total 2,600.
    # Paid = 36.082821 + 26.528821 = 62.611642 -> 62.62. Exit = BUY 65 @ 80 (25.9422568) + SELL 65 @ 120 (38.5793852)
    #   = 64.521642 -> 64.53 (rounded once). After = 2,600.00 - 62.62 - 64.53 = 2,472.85.
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0), PaperOrder("2", "BUY", LOT, D("100"), "open", T0)]
    _, exit_, got = _after_of(orders, _PUT | _CALL, {"1": D("80"), "2": D("120")}, "62.62")
    assert (exit_, got.total_after) == (D("64.53"), D("2472.85"))


def test_the_exit_is_priced_at_the_live_price_not_the_entry_price() -> None:
    # SELL 65 @ 100 now 150: exit BUY 65 @ 150 (premium 9,750): 20 + 3.464175 + 0.00975 + stamp 0.2925 + GST (20 +
    # 0.00975 + 3.464175) x 0.18 = 4.2253065 -> 27.9917315 -> 28.00; at the entry price 100 it would be 26.55.
    view, terms = _one_short_put({"1": D("150")})
    assert open_exit_charges(view, terms, {"1": D("150")}, "NIFTY", RATES)[0] == D("28.00")


def test_the_sum_of_books_is_exact_and_never_partial() -> None:
    a = BookAfterCharges(D("-32.50"), D("-95.13"), D("62.63"), D("0"), None)
    b = BookAfterCharges(D("1300"), D("1237.96"), D("36.09"), D("25.95"), None)
    assert sum_after_charges([a, b]) == BookAfterCharges(D("1267.50"), D("1142.83"), D("98.72"), D("25.95"), None)
    # hand: -95.13 + 1,237.96 = 1,142.83; 62.63 + 36.09 = 98.72
    none = BookAfterCharges(D("5"), None, D("1"), None, "prices_not_live")
    assert sum_after_charges([a, none, b]) == BookAfterCharges(None, None, None, None, "prices_not_live")
