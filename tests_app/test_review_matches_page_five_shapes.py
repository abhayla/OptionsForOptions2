"""GC-ICFIX (ADR-008, ADR-263, ADR-306): the adjustment review's current-state Max profit / Max loss after charges is
the trade page's figure at the engine level (exact Decimal equality of the engine figures, before the reply boundary
rounds them); two-decimal reply text is proven in test_review_money_text_two_decimals.py. No database.

Hand sum for the two-fill-then-partly-closed shape: a leg SOLD 65 at 100.00 then 65 at 100.15 -> average 100.075; 65
bought back at 98.00 -> booked = (100.075 - 98.00) * 65 = 134.875 (a third decimal: the review used to round it to
134.88 while the page kept 134.875, so the two differed by half a paisa).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.engine.extremes import ContractTerms, book_extremes
from ofo.engine.extremes_charges import max_after_charges
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder, net_positions
from ofo_app import adjustment_readers
from ofo_app.routes import adjustment as route

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
TERMS = {"1": ContractTerms(Instrument.PE, D("22400"), EXPIRY), "2": ContractTerms(Instrument.PE, D("22500"), EXPIRY),
         "3": ContractTerms(Instrument.CE, D("23050"), EXPIRY), "4": ContractTerms(Instrument.CE, D("23100"), EXPIRY)}
LIVE = {k: D("50") for k in TERMS}


def _o(cid: str, side: str, price: str, kind: str = "open", lots: int = 1) -> PaperOrder:
    return PaperOrder(cid, side, lots * LOT, D(price), kind, T0)


def _condor() -> list[PaperOrder]:
    return [_o("1", "BUY", "20.10"), _o("2", "SELL", "35.25"), _o("3", "SELL", "40.40"), _o("4", "BUY", "22.30")]


def _both(orders: list[PaperOrder]):
    """(page's extremes, review's after-charges figures) for the same book."""
    view = net_positions(orders, LIVE)
    paid = paper_charges([PaperFill(o.kind, o.side, o.quantity, o.price, True) for o in orders], "NIFTY", RATES)
    page = max_after_charges(view, TERMS, LIVE, "NIFTY", RATES, paid.total)
    legs = tuple(PositionLeg("BUY" if p.net_quantity > 0 else "SELL", TERMS[p.instrument_id].instrument.value,
                             TERMS[p.instrument_id].strike, EXPIRY, abs(p.net_quantity) // LOT, p.average,
                             "X" + p.instrument_id) for p in view.positions if p.net_quantity)
    review = route.price_after(legs, Position("NIFTY", LOT, "weekly", T0.date(), legs), view.booked, paid.shown, (),
                               RATES, MARKET, paid.total)
    assert review.after is not None
    assert review.charges_known
    return page, review.after.after_charges


def _closed(orders: list[PaperOrder], ids: str) -> list[PaperOrder]:
    flip = {"BUY": "SELL", "SELL": "BUY"}
    base = {o.instrument_id: o for o in orders}
    return orders + [_o(i, flip[base[i].side], str(base[i].price + D("1.35")), "exit") for i in ids]


def _two_fill_partly_closed() -> list[PaperOrder]:
    return [_o("1", "SELL", "100.00"), _o("1", "SELL", "100.15"), _o("1", "BUY", "98.00", "exit"),
            _o("2", "BUY", "60.00", lots=2), _o("3", "SELL", "40.40"), _o("4", "BUY", "22.30")]


@pytest.mark.parametrize("orders", [_condor(), _closed(_condor(), "12"), _closed(_condor(), "1234"),
                                    _two_fill_partly_closed()],
                         ids=["fully open", "one spread closed", "fully closed", "two fills then partly closed"])
def test_review_and_page_give_the_identical_figure(orders) -> None:
    page, review = _both(orders)
    assert page.max_profit == review.max_profit  # exact Decimal equality of the engine figures
    assert page.max_loss == -review.max_loss
    text = lambda v: format(route._rupees(v), "f")  # noqa: E731 - the reply text of one figure
    assert text(page.max_profit) == text(review.max_profit)  # and the same reply text, string for string
    assert text(page.max_loss) == text(-review.max_loss)


def test_partly_closed_two_fill_book_really_has_a_third_decimal() -> None:
    # the shape is only a test of the class if the booked figure is finer than a paisa
    assert net_positions(_two_fill_partly_closed(), LIVE).booked == D("134.875")


# ---- the closed futures leg: the review reads the paid charges the way the page does -------------------------------

def _rows(kinds: dict[str, str], orders: list[tuple[str, str, str, str, str]]):
    found = {cid: SimpleNamespace(stored=SimpleNamespace(listed=SimpleNamespace(
        contract=SimpleNamespace(instrument_type=t)))) for cid, t in kinds.items()}
    rows = [SimpleNamespace(order=SimpleNamespace(contract_id=cid, kind=k, side=s, quantity=LOT, price=D(p)))
            for cid, k, s, p, _ in orders]
    return rows, found


def test_a_closed_futures_leg_has_no_paid_charges_so_the_review_says_before_charges() -> None:
    rows, found = _rows({"1": "FUT", "2": "CE"}, [("1", "open", "BUY", "22800.00", ""),
                                                  ("1", "exit", "SELL", "22810.00", ""),
                                                  ("2", "open", "SELL", "90.00", "")])
    assert adjustment_readers.paid_of(rows, found, "NIFTY", RATES) == (None, None)  # not 3,567.07 at option rates


def test_an_unknown_contract_type_is_not_computable_either() -> None:
    rows, found = _rows({"2": "CE"}, [("2", "open", "SELL", "90.00", "")])
    found["2"].stored = None  # fails closed: unknown instrument type
    assert adjustment_readers.paid_of(rows, found, "NIFTY", RATES) == (None, None)


def test_an_options_only_book_gets_the_charges_of_the_page() -> None:
    rows, found = _rows({"1": "CE", "2": "PE"},
                        [("1", "open", "SELL", "90.00", ""), ("2", "open", "SELL", "80.00", "")])
    got = paper_charges([PaperFill(r.order.kind, r.order.side, r.order.quantity, r.order.price, True) for r in rows],
                        "NIFTY", RATES)
    assert adjustment_readers.paid_of(rows, found, "NIFTY", RATES) == (got.shown, got.total)


def test_review_with_charges_not_computable_is_the_pages_before_charges_figure() -> None:  # CE legs, paid None
    view = net_positions([_o("3", "SELL", "40.40"), _o("4", "BUY", "22.30")], LIVE)
    page = book_extremes(view, TERMS, LIVE)  # the page: paid None -> before charges
    legs = tuple(PositionLeg("BUY" if p.net_quantity > 0 else "SELL", TERMS[p.instrument_id].instrument.value,
                             TERMS[p.instrument_id].strike, EXPIRY, 1, p.average, "X" + p.instrument_id)
                 for p in view.positions)
    review = route.price_after(legs, Position("NIFTY", LOT, "weekly", T0.date(), legs), view.booked, None, (), RATES,
                               MARKET, None)
    assert not review.charges_known
    assert (review.after.after_charges.max_profit, -review.after.after_charges.max_loss) == \
        (page.max_profit, page.max_loss)
