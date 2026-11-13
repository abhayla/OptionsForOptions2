"""GC-ICFIX u123/u124 (ADR-301, ADR-302, ADR-303, ADR-008): the one engine function ``after_split`` gives Booked after,
Unbooked after, Profit left after, Loss left after and ``recover`` of a paper book. Exact Decimal; hand sums in
comments.

Readings taken (ADR text leaves them open; all live in ``after_split`` so each is one line to change):
- Profit left / Loss left after = the before-charges figure (measured from now) minus ALL charges paid minus the
  estimated charges to close what is open (the brief's wording of ADR-301); never capped (ADR-302).
- ``recover`` = Profit left after - Max profit after, only when that is above zero: the amount that makes
  "Max profit + recover = Profit left" true on the screen (ADR-302 real case: 5,173.50 = 4,673.50 + 500, the loss).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.engine.extremes import ContractTerms
from ofo.engine.extremes_charges import (
    AfterSplit,
    after_split,
    book_after_charges,
    open_exit_charges,
)
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import BookView, PaperOrder, net_positions

D = Decimal
EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
NONE_SPLIT = AfterSplit(None, None, None, None, None)
PUT = {"1": ContractTerms(Instrument.PE, D("22700"), EXPIRY)}
LEGS = (("1", Instrument.PE, D("22600"), "BUY", D("60.65")), ("2", Instrument.PE, D("22700"), "SELL", D("86.35")),
        ("3", Instrument.CE, D("22950"), "SELL", D("107.50")), ("4", Instrument.CE, D("23000"), "BUY", D("86.95")))


def _split(orders: list[PaperOrder], terms: dict[str, ContractTerms], live: dict[str, Decimal], paid: str | None):
    view = net_positions(orders, live)
    exit_, why = open_exit_charges(view, terms, live, "NIFTY", RATES)
    after = book_after_charges(view, None if paid is None else D(paid), exit_, why)
    return view, after, after_split(view, terms, live, "NIFTY", RATES, after)


def test_core_strategy_141_closed_booked_after_carries_all_charges_unbooked_is_zero() -> None:
    # ADR-303 real case: booked -32.50, paid 403.45, nothing open. Booked after = -32.50 - 403.45 = -435.95;
    # Unbooked after = 0; Total after = -435.95 = Booked after + Unbooked after.
    view = BookView((), D("-32.50"), D(0), D("-32.50"), D(0))
    after = book_after_charges(view, D("403.45"), D("0"))
    got = after_split(view, {}, {}, "NIFTY", RATES, after)
    assert (got.booked_after, got.unbooked_after) == (D("-435.95"), D("0"))
    assert got.booked_after + got.unbooked_after == after.total_after == D("-435.95")
    assert (got.profit_left_after, got.loss_left_after, got.recover) == (D("0"), D("0"), None)  # closed: nothing left


def test_open_book_just_opened_has_booked_minus_the_charges_paid_and_unbooked_minus_the_exit() -> None:
    # SELL 65 @ 100, live 80: before +1,300.00. Paid 36.09 (hand sum in test_extremes_charges), exit estimate 25.95.
    # Booked after = 0 - 36.09 = -36.09 (the cost the owner accepted); Unbooked after = 1,300.00 - 25.95 = 1,274.05;
    # sum = 1,237.96 = Total after.
    _view, after, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], PUT, {"1": D("80")}, "36.09")
    assert after.total_after == D("1237.96")
    assert (got.booked_after, got.unbooked_after) == (D("-36.09"), D("1274.05"))
    assert got.booked_after + got.unbooked_after == D("1237.96")


def test_partly_closed_book_split_adds_up_to_total_after() -> None:
    # SELL 130 @ 100, BUY 65 @ 90 (exit), live 80: booked 650, unbooked 1,300, total 1,950. Paid 74.81, exit 25.95.
    # Booked after = 650 - 74.81 = 575.19; Unbooked after = 1,300 - 25.95 = 1,274.05; sum 1,849.24 = Total after.
    orders = [PaperOrder("1", "SELL", 2 * LOT, D("100"), "open", T0), PaperOrder("1", "BUY", LOT, D("90"), "exit", T0)]
    _, after, got = _split(orders, PUT, {"1": D("80")}, "74.81")
    assert (got.booked_after, got.unbooked_after) == (D("575.19"), D("1274.05"))
    assert got.booked_after + got.unbooked_after == after.total_after == D("1849.24")


def test_profit_left_and_loss_left_after_charges_of_an_iron_condor_at_entry_equal_max_profit_and_loss_after() -> None:
    # Condor of test_extremes_charges at live = entry: before-charges left = 3,006.25 / -3,493.75 (total 0).
    # Exit estimate (SELL 60.65 and 86.95, BUY 86.35 and 107.50, x 65): sell premium 9,594.00, buy premium 12,600.25,
    #   brokerage 4 x 20 = 80, STT 0.0015 x 9,594 = 14.391, transaction 0.0003553 x 22,194.25 = 7.885617025,
    #   SEBI 0.02219425, stamp 0.00003 x 12,600.25 = 0.3780075, GST 0.18 x (80 + 7.885617025 + 0.02219425)
    #   = 15.8234060295 -> 118.5002248045 -> rounded up 118.51.
    # Paid (given) 122.91, chosen so paid + exit = 241.42, the round-trip charges inside Max profit / Max loss.
    # Profit left after = 3,006.25 - 122.91 - 118.51 = 2,764.83 (= Max profit after 3,006.25 - 241.42, so no recover);
    # Loss left after = -3,493.75 - 122.91 - 118.51 = -3,735.17 (= Max loss after).
    terms = {cid: ContractTerms(kind, strike, EXPIRY) for cid, kind, strike, _, _ in LEGS}
    orders = [PaperOrder(cid, side, LOT, price, "open", T0) for cid, _, _, side, price in LEGS]
    live = {cid: price for cid, _, _, _, price in LEGS}
    _view, after, got = _split(orders, terms, live, "122.91")
    assert after.open_exit == D("118.51")
    assert (got.profit_left_after, got.loss_left_after) == (D("2764.83"), D("-3735.17"))
    assert got.recover is None  # at or below Max profit after: absent, not 0


def test_losing_book_profit_left_after_is_not_capped_and_recover_is_the_excess_over_max_profit() -> None:
    # SELL 65 @ 100 (put), live 150: total before = (100 - 150) x 65 = -3,250.00. Profit left before = 150 x 65 =
    # 9,750.00
    # (expiry worthless); Max profit before = 100 x 65 = 6,500.00; round trip at 100: 36.082821 + 26.528821 = 62.611642
    # -> 62.62, so Max profit after = 6,437.38. Paid 36.09, exit BUY 65 @ 150 = 28.00.
    # Profit left after = 9,750.00 - 36.09 - 28.00 = 9,685.91, ABOVE Max profit after: not capped.
    # recover = 9,685.91 - 6,437.38 = 3,248.53 (the 3,250.00 loss, less the 1.47 by which paid + exit 64.09 is
    # above the round trip 62.62): Max profit after + recover = Profit left after, exactly.
    _, _, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], PUT, {"1": D("150")}, "36.09")
    assert got.profit_left_after == D("9685.91")
    assert got.recover == D("3248.53")
    assert D("6437.38") + got.recover == got.profit_left_after


def test_profit_left_at_or_below_max_profit_has_no_recover() -> None:
    # SELL 65 @ 100, live 80 (winning): Profit left before 5,200.00; after 5,200.00 - 36.09 - 25.95 = 5,137.96;
    # Max profit after 6,437.38: below it, so recover is absent.
    _, _, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], PUT, {"1": D("80")}, "36.09")
    assert got.profit_left_after == D("5137.96")
    assert got.recover is None


def test_unknown_charge_rates_give_no_after_figure_for_any_part() -> None:
    view = net_positions([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], {"1": D("80")})
    exit_, why = open_exit_charges(view, PUT, {"1": D("80")}, "NIFTY", None)
    after = book_after_charges(view, D("36.09"), exit_, why)
    assert (after.total_after, after.reason) == (None, "rates_unavailable")
    assert after_split(view, PUT, {"1": D("80")}, "NIFTY", None, after) == NONE_SPLIT


def test_a_leg_the_charges_engine_cannot_price_gives_no_after_figure_not_priced() -> None:
    terms = {"1": ContractTerms(Instrument.FUT, None, EXPIRY)}
    view = net_positions([PaperOrder("1", "BUY", LOT, D("100"), "open", T0)], {"1": D("101")})
    exit_, why = open_exit_charges(view, terms, {"1": D("101")}, "NIFTY", RATES)
    after = book_after_charges(view, D("20"), exit_, why)
    assert (after.total_after, after.reason) == (None, "not_priced")
    assert after_split(view, terms, {"1": D("101")}, "NIFTY", RATES, after) == NONE_SPLIT


def test_an_open_leg_without_a_live_price_gives_no_number() -> None:
    view = net_positions([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], {})
    exit_, why = open_exit_charges(view, PUT, {}, "NIFTY", RATES)
    after = book_after_charges(view, D("36.09"), exit_, why)
    assert (after.total_after, after.reason) == (None, "prices_not_live")
    assert after_split(view, PUT, {}, "NIFTY", RATES, after) == NONE_SPLIT
