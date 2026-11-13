"""GC-ICFIX u123/u124 (ADR-301, ADR-302, ADR-303, ADR-008): the one engine function ``after_split`` gives Booked after,
Unbooked after, Profit left after, Loss left after and ``recover`` of a paper book. Exact Decimal; hand sums in
comments.

ADR-306 (owner, 13 Nov): Profit left after = Max profit after - Total after; Loss left after = Max loss after - Total
after; so Total + Profit left = Max profit and Total + Loss left = Max loss, exactly. ``recover`` = minus Total after when
Total after is negative (the loss on screen), else None. Never capped (ADR-302). A closed book gives 0 and 0.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.engine.extremes import UNLIMITED, ContractTerms
from ofo.engine.extremes_charges import (
    AfterSplit,
    BookAfterCharges,
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


def test_iron_condor_at_entry_total_plus_profit_left_is_max_profit_and_total_plus_loss_left_is_max_loss() -> None:
    # ADR-306. Condor of test_extremes_charges at live = entry: total before 0, Max profit 3,006.25, Max loss -3,493.75.
    # Exit estimate (SELL 60.65 and 86.95, BUY 86.35 and 107.50, x 65): sell premium 9,594.00, buy premium 12,600.25,
    #   brokerage 4 x 20 = 80, STT 0.0015 x 9,594 = 14.391, transaction 0.0003553 x 22,194.25 = 7.885617025,
    #   SEBI 0.02219425, stamp 0.00003 x 12,600.25 = 0.3780075, GST 0.18 x (80 + 7.885617025 + 0.02219425)
    #   = 15.8234060295 -> 118.5002248045 -> rounded up 118.51.
    # Paid = the engine's own figure for the four entry fills: 122.9194123045 -> 122.92 (rounded up once). The round
    # trip inside Max profit / Max loss is 241.42 (rounded up once); paid + exit shown = 241.43, because the pieces
    # are each rounded up on their own, so they can differ from the round trip by a paisa.
    # Total after = 0 - 122.92 - 118.51 = -241.43. Max profit after = 3,006.25 - 241.42 = 2,764.83; Max loss after =
    # -3,493.75 - 241.42 = -3,735.17.
    # Profit left after = 2,764.83 - (-241.43) = 3,006.26; check -241.43 + 3,006.26 = 2,764.83.
    # Loss left after = -3,735.17 - (-241.43) = -3,493.74; check -241.43 + -3,493.74 = -3,735.17.
    # recover = 241.43 (the loss on screen).
    terms = {cid: ContractTerms(kind, strike, EXPIRY) for cid, kind, strike, _, _ in LEGS}
    orders = [PaperOrder(cid, side, LOT, price, "open", T0) for cid, _, _, side, price in LEGS]
    live = {cid: price for cid, _, _, _, price in LEGS}
    _view, after, got = _split(orders, terms, live, "122.92")
    assert (after.open_exit, after.total_after) == (D("118.51"), D("-241.43"))
    assert (got.profit_left_after, got.loss_left_after) == (D("3006.26"), D("-3493.74"))
    assert after.total_after + got.profit_left_after == D("2764.83")
    assert after.total_after + got.loss_left_after == D("-3735.17")
    assert got.recover == D("241.43")
    # paper_charges' own paid figure for these fills is 122.92 (not a hand-picked number): the test reflects the engine
    paid = paper_charges([PaperFill("open", side, LOT, price, True) for _, _, _, side, price in LEGS], "NIFTY", RATES)
    assert paid.shown == D("122.92")


def test_losing_book_profit_left_after_is_not_capped_and_recover_is_the_loss_on_screen() -> None:
    # SELL 65 @ 100 (put), live 150: total before -3,250.00; paid 36.09; exit BUY 65 @ 150 = 28.00;
    # Total after = -3,250.00 - 36.09 - 28.00 = -3,314.09. Max profit after = 6,500.00 - 62.62 = 6,437.38.
    # Profit left after = 6,437.38 - (-3,314.09) = 9,751.47 (above Max profit: not capped); recover = 3,314.09.
    # Check -3,314.09 + 9,751.47 = 6,437.38. Max loss after = -1,469,000 - 62.62 = -1,469,062.62;
    # Loss left after = -1,469,062.62 + 3,314.09 = -1,465,748.53.
    _, after, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], PUT, {"1": D("150")}, "36.09")
    assert after.total_after == D("-3314.09")
    assert got.profit_left_after == D("9751.47")
    assert got.loss_left_after == D("-1465748.53")
    assert got.recover == D("3314.09")
    assert after.total_after + got.profit_left_after == D("6437.38")


def test_winning_open_position_profit_left_is_max_profit_less_total_and_recover_is_absent() -> None:
    # SELL 65 @ 100, live 80: Total after = 1,300.00 - 36.09 - 25.95 = 1,237.96. Max profit after 6,437.38, Max loss
    # after -1,469,062.62. Profit left after = 6,437.38 - 1,237.96 = 5,199.42;
    # Loss left after = -1,469,062.62 - 1,237.96 = -1,470,300.58. In profit: no recover.
    _, after, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], PUT, {"1": D("80")}, "36.09")
    assert after.total_after == D("1237.96")
    assert got.profit_left_after == D("5199.42")
    assert got.loss_left_after == D("-1470300.58")
    assert got.recover is None


def test_total_exactly_zero_has_no_recover_and_profit_left_is_max_profit() -> None:
    # Total after exactly 0.00 (paid and exit given as 0): Profit left after = Max profit after 6,437.38 - 0.00.
    view = net_positions([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], {"1": D("100")})
    after = BookAfterCharges(D("0"), D("0"), D("0"), D("0"), None)
    got = after_split(view, PUT, {"1": D("100")}, "NIFTY", RATES, after)
    assert got.profit_left_after == D("6437.38")
    assert got.recover is None


def test_unlimited_max_loss_gives_unlimited_loss_left_and_a_finite_profit_left() -> None:
    # SELL 65 @ 100 call (Max loss UNLIMITED), live 80: Profit left after = 6,437.38 - 1,237.96 = 5,199.42; "unlimited"
    # in code is the UNLIMITED marker, the same one Max loss carries.
    terms = {"1": ContractTerms(Instrument.CE, D("22700"), EXPIRY)}
    _, _, got = _split([PaperOrder("1", "SELL", LOT, D("100"), "open", T0)], terms, {"1": D("80")}, "36.09")
    assert got.profit_left_after == D("5199.42")
    assert got.loss_left_after is UNLIMITED
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
