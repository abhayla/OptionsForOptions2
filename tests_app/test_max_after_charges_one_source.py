"""GC-ICFIX issue 3 (ADR-008, ADR-263, REQ-109 AC-10): Max profit / Max loss after charges is ONE figure. The trade page
(``extremes_charges.max_after_charges``) and the adjustment review's "current state"
(``routes.adjustment.price_after``) must agree to the paisa. Real case, strategy 148 (PATH-61): 8,116.22 / -17,883.78
on the review against 8,116.23 / -17,883.77 on the trade page. No database.

Rounding rule (``round_trip.to_paise_up``, F-35): the shown charges are the exact total rounded UP to the paisa ONCE.
Hand sum, one case: exact entry charges 100.0040 and exact exit charges 100.0040 -> total 200.0080 -> shown 200.01
(once). Rounding the two halves separately gives 100.01 + 100.01 = 200.02: a paisa more, and the wrong one.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment.approaches import ChainRow, Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.engine.extremes import UNLIMITED, ContractTerms, book_extremes
from ofo.engine.extremes_charges import (
    after_split,
    book_after_charges,
    max_after_charges,
    open_exit_charges,
    open_round_trip_charges,
)
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import BookView, PaperOrder, net_positions
from ofo_app.routes import adjustment as route

EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
# D-14: the review prices the cost to close at the chain's live LTP, the price the page uses (50 for every leg)
CHAIN = tuple(ChainRow(D(0), "CE", EXPIRY, "X" + str(i), D("50")) for i in range(1, 5))
MARKET = route.MarketInputs(CHAIN, {}, None, None, None, None, None,
                            datetime.datetime(2026, 11, 2, 5, 0, tzinfo=datetime.UTC))
SHAPE = (("PE", "BUY", -400), ("PE", "SELL", -300), ("CE", "SELL", 250), ("CE", "BUY", 300))  # type, side, offset


def _condor(lots: int, base: int, premium: D, split: bool):
    """(orders, live, terms) of an iron condor; ``split`` fills the first leg in two orders at different prices."""
    orders, terms = [], {}
    for i, (kind, side, off) in enumerate(SHAPE, 1):
        cid, price = str(i), premium + D(i) * D("1.15") * (1 if side == "SELL" else -1) + D(off) / 100
        terms[cid] = ContractTerms(Instrument(kind), D(base + off), EXPIRY)
        if split and i == 1 and lots > 1:
            orders += [PaperOrder(cid, side, LOT, price, "open", T0),
                       PaperOrder(cid, side, (lots - 1) * LOT, price + D("0.15"), "open", T0)]
        else:
            orders.append(PaperOrder(cid, side, lots * LOT, price, "open", T0))
    return orders, {str(i): D("50") for i in range(1, 5)}, terms




def _paid(orders):
    return paper_charges([PaperFill(o.kind, o.side, o.quantity, o.price, True) for o in orders], "NIFTY", RATES)


def _page(orders, live, terms, rates=RATES):
    """The trade page's Max profit / Max loss: the one engine function, with the charges paid (as paper._extremes)."""
    view = net_positions(orders, live)
    return view, max_after_charges(view, terms, live, "NIFTY", rates, _paid(orders).total)


def _both(orders, live, terms):
    """(trade page extremes, review's after-charges figures) for the same book."""
    view, page = _page(orders, live, terms)
    legs = tuple(PositionLeg("BUY" if p.net_quantity > 0 else "SELL", terms[p.instrument_id].instrument.value,
                             terms[p.instrument_id].strike, EXPIRY, abs(p.net_quantity) // LOT, p.average,
                             "X" + p.instrument_id) for p in view.positions if p.net_quantity)
    paid = _paid(orders)
    review = route.price_after(legs, Position("NIFTY", LOT, "weekly", T0.date(), legs), view.booked, paid.shown, (),
                               RATES, MARKET, paid.total)
    assert review.after is not None
    assert review.charges_known
    return page, review.after.after_charges


GRID = [(lots, base, D(prem), split) for lots in (1, 2, 3) for base in (22500, 23100, 23700)
        for prem in ("62.35", "88.8") for split in (False, True) if lots > 1 or not split]


def test_one_iron_condor_trade_page_and_review_agree_to_the_paisa() -> None:
    page, review = _both(*_condor(2, 22800, D("90"), False))
    assert (page.max_profit, page.max_loss) == (review.max_profit, -review.max_loss)


@pytest.mark.parametrize(("lots", "base", "premium", "split"), GRID)
def test_grid_one_fill_and_two_fill_books_agree_to_the_paisa(lots, base, premium, split) -> None:
    # ADR-263: the charges are what was really paid (every filled order) + the estimate to close: a two-fill leg pays
    # two brokerages (20 + 20 + their GST), not one.
    page, review = _both(*_condor(lots, base, premium, split))
    assert page.max_profit == review.max_profit
    assert page.max_loss == -review.max_loss


def test_closed_put_spread_and_two_open_legs_agree_and_count_the_closed_leg_charges() -> None:
    # After an adjustment the put spread (legs 1, 2) was closed, the call spread (3, 4) stays open (closing one leg of a
    # condor would leave a naked leg: unlimited loss). Hand sum, charges: paid = the 6 orders'
    # exact charges, exit estimate = the 2 open legs' closing orders at their average price; shown = ceil(paid +
    # exit) once. Max profit = (open legs' credit + booked of the closed leg) - that total.
    orders, live, terms = _condor(1, 22800, D("90"), False)
    orders += [PaperOrder("1", "SELL", LOT, orders[0].price + D("3.40"), "exit", T0),
               PaperOrder("2", "BUY", LOT, orders[1].price - D("2.10"), "exit", T0)]
    page, review = _both(orders, live, terms)
    assert page.max_profit == review.max_profit
    assert page.max_loss == -review.max_loss
    one_fill_estimate = open_round_trip_charges(net_positions(orders, live), terms, "NIFTY", RATES)
    assert one_fill_estimate is not None
    assert open_round_trip_charges(net_positions(orders, live), terms, "NIFTY", RATES, _paid(orders).total) \
        != one_fill_estimate  # the closed leg's charges are inside the placed-book figure


@pytest.mark.parametrize(("lots", "base", "premium", "split"), GRID)
def test_adr306_identities_hold_exactly(lots, base, premium, split) -> None:
    orders, live, terms = _condor(lots, base, premium, split)
    view, page = _page(orders, live, terms)
    paid = _paid(orders)
    exit_, why = open_exit_charges(view, terms, live, "NIFTY", RATES)
    after = book_after_charges(view, paid.shown, exit_, why)
    got = after_split(view, terms, live, "NIFTY", RATES, after, paid.total)
    assert after.total_after + got.profit_left_after == page.max_profit
    assert after.total_after + got.loss_left_after == page.max_loss


def test_no_rates_gives_the_before_figures() -> None:
    orders, live, terms = _condor(2, 22800, D("90"), True)
    view = net_positions(orders, live)
    before = book_extremes(view, terms, live)
    assert max_after_charges(view, terms, live, "NIFTY", None, D("100")) == before
    assert open_round_trip_charges(view, terms, "NIFTY", None, D("100")) is None


def test_a_futures_leg_cannot_be_priced_gives_the_before_figures() -> None:
    terms = {"1": ContractTerms(Instrument.FUT, None, EXPIRY)}
    live = {"1": D("22800")}
    view = net_positions([PaperOrder("1", "BUY", LOT, D("22800"), "open", T0)], live)
    assert open_round_trip_charges(view, terms, "NIFTY", RATES, D("10")) is None
    assert max_after_charges(view, terms, live, "NIFTY", RATES, D("10")) == book_extremes(view, terms, live)


def test_prices_not_live_gives_the_before_max_never_an_average_price_exit() -> None:
    # D-14: the cost to close is priced at the live price only (one exit cost with Total after); with no live price the
    # max is before charges (the reply then says so) - never the average price standing in for the live one.
    orders, _live, terms = _condor(1, 22800, D("90"), False)
    view = net_positions(orders, {})
    got = max_after_charges(view, terms, {}, "NIFTY", RATES, _paid(orders).total)
    assert got.reason == "prices_not_live"
    assert got == book_extremes(view, terms, {})
    assert open_round_trip_charges(view, terms, "NIFTY", RATES, _paid(orders).total, {}) is None


CLOSED = BookView((), D("-32.50"), D(0), D("-32.50"), D(0))  # booked -32.50, nothing open (strategy 141)


def test_fully_closed_book_max_is_booked_minus_the_charges_paid() -> None:
    # Strategy 141: booked -32.50, paid 403.45, nothing open (exit estimate 0): -32.50 - 403.45 = -435.95 = Total after
    got = max_after_charges(CLOSED, {}, {}, "NIFTY", RATES, D("403.45"))
    assert (got.max_profit, got.max_loss) == (D("-435.95"), D("-435.95"))
    after = book_after_charges(CLOSED, D("403.45"), D("0"))
    assert after.total_after == D("-435.95")
    split = after_split(CLOSED, {}, {}, "NIFTY", RATES, after, D("403.45"))
    assert (split.profit_left_after, split.loss_left_after) == (D("0"), D("0"))  # ADR-306 (5)
    # reviewer's probe: booked -32.50, paid 62.63 -> -95.13
    probe = max_after_charges(CLOSED, {}, {}, "NIFTY", RATES, D("62.63"))
    assert (probe.max_profit, probe.max_loss) == (D("-95.13"), D("-95.13"))


def test_fully_closed_book_without_rates_keeps_the_before_figure_and_says_no_charges() -> None:
    got = max_after_charges(CLOSED, {}, {}, "NIFTY", None, D("403.45"))
    assert (got.max_profit, got.max_loss) == (D("-32.50"), D("-32.50"))
    assert open_round_trip_charges(CLOSED, {}, "NIFTY", None, D("403.45")) is None
    after = book_after_charges(CLOSED, None, D("0"), "rates_unavailable")
    assert (after.total_after, after.reason) == (None, "rates_unavailable")


def test_unlimited_max_loss_stays_unlimited() -> None:
    terms = {"1": ContractTerms(Instrument.CE, D("23000"), EXPIRY)}
    live = {"1": D("90")}
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0)]
    _view, got = _page(orders, live, terms)
    assert got.max_loss is UNLIMITED
    # placed book: paid exact + the exit at the live 90, rounded up once (D-14)
    charges = open_round_trip_charges(net_positions(orders, live), terms, "NIFTY", RATES, _paid(orders).total, live)
    assert charges is not None
    assert got.max_profit == D("6500.00") - charges
