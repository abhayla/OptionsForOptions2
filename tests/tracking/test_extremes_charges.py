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
