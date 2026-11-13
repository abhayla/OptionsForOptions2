"""GC-ICFIX u129 round 2 (F1, ADR-008, ADR-263, ADR-301, ADR-303): a position whose AVERAGE entry price has more than
two decimal places (a contract filled in two or more orders at different prices) must not crash the after-charges
figures. Paid = the charges of the REAL fills, each at its own fill price; the exit estimate = closing the open quantity
at the LIVE price; Max profit after = the round trip of the open quantity at its exact average turnover. No average is
ever rounded to two decimals and priced on.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from test_after_split import EXPIRY, LOT, PUT, RATES, T0

from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.charges.round_trip import round_trip_charges
from ofo.engine.extremes import ContractTerms, book_extremes
from ofo.engine.extremes_charges import (
    after_split,
    book_after_charges,
    open_exit_charges,
    open_round_trip_charges,
    with_charges,
)
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.orderbook import PaperOrder, net_positions

D = Decimal


def _paid(orders: list[PaperOrder]) -> Decimal:
    return paper_charges([PaperFill(o.kind, o.side, o.quantity, o.price, True) for o in orders], "NIFTY", RATES).shown


def _figures(orders: list[PaperOrder], terms: dict[str, ContractTerms], live: dict[str, Decimal]):
    view = net_positions(orders, live)
    exit_, why = open_exit_charges(view, terms, live, "NIFTY", RATES)
    after = book_after_charges(view, _paid(orders), exit_, why)
    return view, after, after_split(view, terms, live, "NIFTY", RATES, after)


def test_reviewer_case_two_sells_at_different_prices_gives_figures() -> None:
    # SELL 65 @ 100.00 + SELL 65 @ 100.05 (average 100.025, net -130), live 101.
    # Fill 1 (premium 6,500.00): brokerage 20, STT 9.75, txn 2.30945, SEBI 0.0065, GST 0.18 x 22.31595 = 4.016871
    #   -> 36.082821. Fill 2 (premium 6,503.25): STT 9.754875, txn 2.310604725, SEBI 0.00650325,
    #   GST 0.18 x 22.317107975 = 4.0170794355 -> 36.0890624105. Paid = 72.1718834105 -> 72.18.
    # Exit: BUY 130 @ 101 (premium 13,130): brokerage 20, txn 4.665089, SEBI 0.01313, stamp 0.3939,
    #   GST 0.18 x 24.678219 = 4.44207942 -> 29.51419842 -> 29.52.
    # Before: (100.025 - 101) x 130 = -126.75. Total after = -126.75 - 72.18 - 29.52 = -228.45.
    # Booked after = 0 - 72.18; Unbooked after = -126.75 - 29.52 = -156.27; sum -228.45.
    # Round trip at the average (turnover 13,003.25): SELL 48.5718834105 + BUY 29.4571059105 = 78.028989321 -> 78.03;
    #   Max profit after = 13,003.25 - 78.03 = 12,925.22. Profit left after = 13,130 - 72.18 - 29.52 = 13,028.30;
    #   recover = 13,028.30 - 12,925.22 = 103.08.
    orders = [PaperOrder("1", "SELL", LOT, D("100.00"), "open", T0), PaperOrder("1", "SELL", LOT, D("100.05"), "add", T0)]
    live = {"1": D("101")}
    view, after, got = _figures(orders, PUT, live)
    assert view.positions[0].average == D("100.025")
    assert (after.paid, after.open_exit, after.total_after) == (D("72.18"), D("29.52"), D("-228.45"))
    assert (got.booked_after, got.unbooked_after) == (D("-72.18"), D("-156.27"))
    assert open_round_trip_charges(view, PUT, "NIFTY", RATES) == D("78.03")
    assert with_charges(book_extremes(view, PUT, live), D("78.03")).max_profit == D("12925.22")
    assert (got.profit_left_after, got.recover) == (D("13028.30"), D("103.08"))


def _book(prices: list[str], side: str, kind_first: str = "open") -> list[PaperOrder]:
    return [PaperOrder("1", side, LOT, D(p), kind_first if i == 0 else "add", T0) for i, p in enumerate(prices)]


def _grid() -> list[tuple[list[PaperOrder], D]]:
    cases = []
    for n in (2, 3, 5, 7):  # n fills: n-1 at 100.00 and one dearer -> thirds, fifths, sevenths in the average
        for delta in ("0.01", "0.05", "0.15"):
            for side in ("SELL", "BUY"):
                for live in ("85.35", "112.70"):
                    cases.append((_book(["100.00"] * (n - 1) + [str(D("100.00") + D(delta))], side), D(live)))
    cases.append((_book(["33.33", "33.34", "33.35"], "SELL"), D("20.05")))
    cases.append((_book(["77.77", "77.70", "77.71"], "BUY"), D("90.10")))
    return cases


def test_grid_of_averaged_books_never_raises_and_booked_plus_unbooked_is_total_after() -> None:
    cases = _grid()
    assert len(cases) >= 30
    for orders, live_price in cases:
        live = {"1": live_price}
        view, after, got = _figures(orders, PUT, live)
        label = f"{orders[0].side} {[str(o.price) for o in orders]} live {live_price}"
        assert after.total_after is not None, label
        assert got.booked_after + got.unbooked_after == after.total_after, label
        assert after.total_after == view.total - after.paid - after.open_exit, label


def test_an_average_that_is_exactly_two_decimals_prices_like_the_old_single_leg() -> None:
    # SELL 65 @ 100.00 + SELL 65 @ 100.10: average 100.05 exactly. The round trip must equal the engine's own
    # round_trip_charges on one leg of 130 at 100.05 (the unchanged old path).
    view = net_positions(_book(["100.00", "100.10"], "SELL"), {"1": D("90")})
    old = round_trip_charges([Leg(Action.SELL, Instrument.PE, D("22700"), EXPIRY, 2 * LOT, D("100.05"))], "NIFTY", RATES)
    assert open_round_trip_charges(view, PUT, "NIFTY", RATES) == old


def test_one_fill_round_trip_is_unchanged_to_the_paisa() -> None:
    view = net_positions(_book(["100.00"], "SELL"), {"1": D("90")})
    assert open_round_trip_charges(view, PUT, "NIFTY", RATES) == D("62.62")  # 36.082821 + 26.527821 = 62.610642 -> up


def test_long_leg_with_an_averaged_entry() -> None:
    # BUY 65 @ 50.00 + BUY 65 @ 50.01 (average 50.005), live 55: a long leg closes with a SELL.
    orders = _book(["50.00", "50.01"], "BUY")
    view, after, got = _figures(orders, PUT, {"1": D("55")})
    assert after.total_after is not None
    assert got.booked_after + got.unbooked_after == after.total_after
    assert open_round_trip_charges(view, PUT, "NIFTY", RATES) is not None


def test_partly_closed_position_built_from_several_fills() -> None:
    # SELL 65 @ 100.00, SELL 65 @ 100.05, SELL 65 @ 100.10 (average 100.05), BUY 65 @ 90 closes a third; 130 open.
    orders = _book(["100.00", "100.05", "100.10"], "SELL") + [PaperOrder("1", "BUY", LOT, D("90"), "exit", T0)]
    view, after, got = _figures(orders, PUT, {"1": D("95")})
    assert view.positions[0].net_quantity == -2 * LOT
    assert got.booked_after + got.unbooked_after == after.total_after


def test_reopened_leg_flat_then_opened_again_at_two_prices() -> None:
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0), PaperOrder("1", "BUY", LOT, D("90"), "exit", T0),
              PaperOrder("1", "SELL", LOT, D("100.00"), "open", T0), PaperOrder("1", "SELL", LOT, D("100.05"), "add", T0)]
    view, after, got = _figures(orders, PUT, {"1": D("101")})
    assert view.positions[0].average == D("100.025")
    assert got.booked_after + got.unbooked_after == after.total_after


def test_unpriceable_leg_with_an_averaged_entry_is_none_not_priced_and_never_raises() -> None:
    terms = {"1": ContractTerms(Instrument.FUT, None, EXPIRY)}
    orders = _book(["100.00", "100.05"], "BUY")
    live = {"1": D("101")}
    view = net_positions(orders, live)
    assert open_round_trip_charges(view, terms, "NIFTY", RATES) is None
    exit_, why = open_exit_charges(view, terms, live, "NIFTY", RATES)
    after = book_after_charges(view, D("20"), exit_, why)
    assert (after.total_after, after.reason) == (None, "not_priced")
    assert after_split(view, terms, live, "NIFTY", RATES, after).booked_after is None


def test_averaged_entry_without_a_live_price_is_none_prices_not_live() -> None:
    view = net_positions(_book(["100.00", "100.05"], "SELL"), {})
    exit_, why = open_exit_charges(view, PUT, {}, "NIFTY", RATES)
    after = book_after_charges(view, D("72.18"), exit_, why)
    assert (after.total_after, after.reason) == (None, "prices_not_live")
    assert after_split(view, PUT, {}, "NIFTY", RATES, after).recover is None


def test_unknown_underlying_is_none_not_an_exception() -> None:
    view = net_positions(_book(["100.00", "100.05"], "SELL"), {"1": D("101")})
    assert open_round_trip_charges(view, PUT, "UNKNOWNINDEX", RATES) is None


def test_f5_when_the_round_trip_cannot_be_priced_recover_fails_closed() -> None:
    # F5: if the round trip is None (here: an average of 0 cannot be priced) the "Max profit after" would silently be
    # the BEFORE-charges figure; recover must then be None, never a mix of bases. Booked / Unbooked still add up.
    orders = [PaperOrder("1", "SELL", LOT, D("100"), "open", T0), PaperOrder("1", "BUY", 2 * LOT, D("100"), "exit", T0),
              PaperOrder("1", "BUY", LOT, D("0"), "settle", T0)]
    view = net_positions(orders, {"1": D("150")})
    # a hand-made view whose open position has average 0 (open, priced at nothing): the round trip is unpriceable
    zero = type(view.positions[0])(**{**view.positions[0].__dict__, "net_quantity": -LOT, "average": D("0")})
    bad = type(view)((zero,), view.booked, D("-100"), view.booked + D("-100"), view.cash)
    assert open_round_trip_charges(bad, PUT, "NIFTY", RATES) is None
    after = book_after_charges(bad, D("10"), D("5"))
    got = after_split(bad, PUT, {"1": D("150")}, "NIFTY", RATES, after)
    assert got.recover is None


@pytest.mark.parametrize("price", ["100.025"])
def test_a_fill_finer_than_a_paisa_is_still_refused_at_the_order_door(price: str) -> None:
    with pytest.raises(ValueError):
        PaperOrder("1", "SELL", LOT, D(price), "open", T0)


def test_list_sum_keeps_the_priceable_row_and_gives_the_reason_for_the_one_that_cannot_be_priced() -> None:
    from ofo.engine.extremes_charges import BookAfterCharges, sum_after_charges  # noqa: PLC0415
    orders = _book(["100.00", "100.05"], "SELL")
    _, good, _ = _figures(orders, PUT, {"1": D("101")})
    bad = book_after_charges(net_positions(orders, {"1": D("101")}), D("72.18"), None, "not_priced")
    assert good.total_after == D("-228.45") and bad.reason == "not_priced"  # the good row is untouched by the bad one
    assert sum_after_charges([good, bad]) == BookAfterCharges(None, None, None, None, "not_priced")
