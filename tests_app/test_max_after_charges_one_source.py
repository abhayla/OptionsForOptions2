"""GC-ICFIX issue 3 (ADR-008, ADR-263, REQ-109 AC-10): Max profit / Max loss after charges is ONE figure. The trade page
(``extremes_charges.with_charges`` over ``open_round_trip_charges``) and the adjustment review's "current state"
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
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.engine.extremes import ContractTerms, book_extremes
from ofo.engine.extremes_charges import open_round_trip_charges, with_charges
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder, net_positions
from ofo_app.routes import adjustment as route
from ofo_app.routes.paper import paid_charges
from ofo.charges.paper_charges import PaperFill

EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
MARKET = route.MarketInputs((), {}, None, None, None, None, None,
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


def _both(orders, live, terms):
    """(trade page extremes, review's after-charges figures) for the same open book."""
    view = net_positions(orders, live)
    page = with_charges(book_extremes(view, terms, live), open_round_trip_charges(view, terms, "NIFTY", RATES))
    legs = tuple(PositionLeg("BUY" if p.net_quantity > 0 else "SELL", terms[p.instrument_id].instrument.value,
                             terms[p.instrument_id].strike, EXPIRY, abs(p.net_quantity) // LOT, p.average,
                             "X" + p.instrument_id) for p in view.positions)
    paid, _why = paid_charges([PaperFill("open", o.side, o.quantity, o.price, True) for o in orders], "NIFTY", RATES)
    review = route.price_after(legs, Position("NIFTY", LOT, "weekly", T0.date(), legs), D("0"), paid, (), RATES, MARKET)
    assert review.after is not None
    assert review.charges_known
    return page, review.after.after_charges


def test_one_iron_condor_trade_page_and_review_agree_to_the_paisa() -> None:
    page, review = _both(*_condor(2, 22800, D("90"), False))
    assert (page.max_profit, page.max_loss) == (review.max_profit, -review.max_loss)


GRID = [(lots, base, D(prem), split) for lots in (1, 2, 3) for base in (22500, 23100) for prem in ("62.35", "88.8")
        for split in (False, True)]


@pytest.mark.parametrize(("lots", "base", "premium", "split"), GRID)
def test_grid_trade_page_and_review_agree_to_the_paisa(lots, base, premium, split) -> None:
    page, review = _both(*_condor(lots, base, premium, split))
    assert page.max_profit == review.max_profit
    assert page.max_loss == -review.max_loss
