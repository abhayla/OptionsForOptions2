"""GC-ICFIX Issue 10 round 2 (ADR-256 and amendment, ADR-143, ADR-008): ``exit_risk`` answers yes / no / cannot_tell;
``no`` only when proven.
(counted per type, a bought leg covers a sold leg only with the same or a later expiry), or when the book's own Max Loss
after is unlimited or more than double the Max Loss before while legs stay open. The whole basket (exits and entries)
is judged on the legs after ALL orders. Real shape: trade 139, a 1-lot NIFTY 23 Nov condor B 25000 PE, S 25100 PE,
S 25300 CE, B 25400 CE at the paper fills 162.55 / 201.50 / 218.35 / 176.40 (Max Loss -1,241.50).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.extremes import UNLIMITED, ContractTerms, exit_risk
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder

D = Decimal
E1, E2 = datetime.date(2026, 11, 23), datetime.date(2026, 12, 28)
T0 = datetime.datetime(2026, 11, 13, 4, 48, tzinfo=datetime.UTC)
T1 = datetime.datetime(2026, 11, 13, 5, 30, tzinfo=datetime.UTC)
LOT = 65

# contract id -> (instrument, strike, expiry)
TERMS = {"1": ContractTerms(Instrument.PE, D(25000), E1), "2": ContractTerms(Instrument.PE, D(25100), E1),
         "3": ContractTerms(Instrument.CE, D(25300), E1), "4": ContractTerms(Instrument.CE, D(25400), E1),
         "5": ContractTerms(Instrument.CE, D(25350), E1), "6": ContractTerms(Instrument.CE, D(26000), E2),
         "7": ContractTerms(Instrument.CE, D(27000), E1), "8": ContractTerms(Instrument.CE, D(25300), E2),
         "9": ContractTerms(Instrument.CE, D(25400), E2), "10": ContractTerms(Instrument.FUT, None, E1),
         "11": ContractTerms(Instrument.CE, D(24950), E1), "12": ContractTerms(Instrument.CE, D(25050), E1),
         "13": ContractTerms(Instrument.CE, D(25500), E1)}


def _o(cid: str, side: str, price: str, kind: str = "open", lots: int = 1) -> PaperOrder:
    return PaperOrder(cid, side, lots * LOT, D(price), kind, T0 if kind == "open" else T1)


def _x(cid: str, side: str, price: str, lots: int = 1) -> PaperOrder:
    return _o(cid, side, price, "exit", lots)


PE_B, PE_S = _o("1", "BUY", "162.55"), _o("2", "SELL", "201.50")
CE_S, CE_B = _o("3", "SELL", "218.35"), _o("4", "BUY", "176.40")
IC = [PE_B, PE_S, CE_S, CE_B]
LATER_LONG = _o("6", "BUY", "5.00")


def _ask(book: list[PaperOrder], *basket: PaperOrder):
    return exit_risk(book, list(basket), TERMS)


def test_ic_bought_call_closed_alone_is_yes_unlimited_after_and_names_the_sold_call() -> None:
    got = _ask(IC, _x("4", "SELL", "170.00"))
    assert got.state == "yes" and got.max_loss_after is UNLIMITED
    assert got.max_loss_before == D("-1241.50") and got.exposed == ("3",)


def test_ic_bought_put_closed_alone_is_yes_and_names_the_sold_put() -> None:
    got = _ask(IC, _x("1", "SELL", "150.00"))
    assert got.state == "yes" and got.exposed == ("2",)
    assert got.max_loss_after is not UNLIMITED and got.max_loss_after < got.max_loss_before


@pytest.mark.parametrize(("book", "closed"), [
    ([PE_B, PE_S], _x("1", "SELL", "150.00")),   # put credit spread
    ([CE_S, CE_B], _x("4", "SELL", "170.00")),   # call credit spread
    ([_o("4", "BUY", "176.40", lots=2), _o("3", "SELL", "218.35", lots=2)], _x("4", "SELL", "170.00")),  # 1 of 2 lots
    ([CE_S, _o("7", "BUY", "5.00")], _x("7", "SELL", "4.00")),   # far strike protection
])
def test_a_protective_bought_leg_closed_is_yes(book: list[PaperOrder], closed: PaperOrder) -> None:
    assert _ask(book, closed).state == "yes"


def test_ratio_book_already_unlimited_judges_cover_per_type() -> None:
    ratio = [_o("4", "BUY", "176.40"), _o("3", "SELL", "218.35", lots=2), PE_B, PE_S]
    assert _ask(ratio, _x("1", "SELL", "150.00")).state == "yes"   # put side: 0 -> 1 naked
    assert _ask(ratio, _x("4", "SELL", "170.00")).state == "yes"   # call side: 1 -> 2 naked


def test_calendar_and_diagonal_use_expiry_aware_cover() -> None:
    calendar = [_o("3", "SELL", "218.35"), _o("8", "BUY", "260.00")]       # sold near, bought far
    diagonal = [_o("3", "SELL", "218.35"), _o("9", "BUY", "240.00")]
    for book, far in ((calendar, "8"), (diagonal, "9")):
        assert _ask(book, _x(far, "SELL", "250.00")).state == "yes"        # the far long covered the near short
        assert _ask(book, _x("3", "BUY", "210.00")).state == "cannot_tell"  # two expiries: no Max Loss figure


def test_a_bought_leg_of_an_earlier_expiry_does_not_cover_a_later_sold_leg() -> None:
    book = [_o("8", "SELL", "260.00"), _o("3", "BUY", "218.35")]            # sold far, bought near: naked already
    assert _ask(book, _x("3", "SELL", "210.00")).state != "no"


def test_condor_plus_an_unrelated_later_expiry_long_cannot_be_judged() -> None:
    assert _ask([*IC, LATER_LONG], _x("4", "SELL", "170.00")).state == "cannot_tell"


def test_a_future_leg_cannot_be_counted_but_an_unlimited_result_is_still_proven() -> None:
    covered_call = [_o("10", "BUY", "25000.00"), _o("13", "SELL", "100.00")]
    assert _ask(covered_call, _x("13", "BUY", "90.00")).state == "cannot_tell"      # a future leg is left: not counted
    assert _ask(covered_call, _x("10", "SELL", "25010.00")).state == "yes"             # the call is naked: unlimited


def test_an_exit_larger_than_what_is_open_is_never_no() -> None:
    assert _ask(IC, _x("4", "SELL", "170.00", lots=2)).state == "cannot_tell"


def test_sold_leg_alone_warns_only_when_the_max_loss_more_than_doubles() -> None:
    # ADR-256 amendment, strategy 91 shape: S2 24950 CE / B2 25050 CE, one sold lot exited at a loss: -5,200 -> -18,200
    book = [_o("11", "SELL", "160.00", lots=2), _o("12", "BUY", "100.00", lots=2)]
    got = _ask(book, _x("11", "BUY", "300.00"))
    assert got.state == "yes" and got.max_loss_before == D("-5200") and got.max_loss_after == D("-18200")
    assert got.max_loss_after < 2 * got.max_loss_before
    # a plain reduction (one sold lot bought back at what it sold for, wider spread kept) does not double the loss
    flat = [_o("11", "SELL", "100.00", lots=2), _o("12", "BUY", "95.00", lots=2)]
    assert _ask(flat, _x("11", "BUY", "100.00")).state == "no"


def test_closing_everything_is_no() -> None:
    got = _ask(IC, _x("1", "SELL", "150.00"), _x("2", "BUY", "210.00"), _x("3", "BUY", "230.00"),
                _x("4", "SELL", "160.00"))
    assert got.state == "no"


def test_closing_one_whole_spread_follows_the_double_rule_not_the_cover_count() -> None:
    # cover is unchanged (no sold lot becomes naked); the call spread gone leaves the put spread, Max Loss -1,241.50 ->
    # -3,971.50, which is more than double (ADR-256 amendment): yes, with no sold leg named as less protected
    got = _ask(IC, _x("3", "BUY", "218.00"), _x("4", "SELL", "176.00"))
    assert got.state == "yes" and got.exposed == () and got.max_loss_after == D("-3971.50")


def test_roll_basket_is_judged_on_the_legs_after_all_orders() -> None:
    # close B 25400 CE, open B 25350 CE: the sold call stays covered, so no leg is named as less protected
    got = _ask(IC, _x("4", "SELL", "170.00"), _o("5", "BUY", "190.00"))
    assert got.exposed == ()
    assert got.max_loss_after == D("-2541.50")
    assert _ask(IC, _x("4", "SELL", "170.00")).exposed == ("3",)  # without the entry the same exit does expose it
