"""GC-TP step 3a core proof and rules: Profit left / Loss left and the original Max Profit / Max Loss (REQ-109 AC-9).

The real book: tests/fixtures/paper/strategy-63-roll.json is the live ``GET /paper/strategies/63`` reply after the
22900 CE -> 22950 CE roll on 2026-10-29 (its orders and each open contract's LTP). The expected figures are computed
by hand below at the strikes (a defined-risk book's at-expiry extremes lie at a strike or on a flat tail).
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

from ofo.engine.extremes import MULTI_EXPIRY, PRICES_NOT_LIVE, UNLIMITED, ContractTerms, book_extremes
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder, net_positions

D = Decimal
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "paper" / "strategy-63-roll.json"
EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65


def _book() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _real() -> tuple[list[PaperOrder], dict[str, ContractTerms], dict[str, Decimal]]:
    book = _book()
    orders = [PaperOrder(str(o["contract_id"]), o["side"], o["quantity"], D(o["price"]), o["kind"],
                         datetime.datetime.fromisoformat(o["placed_at"].replace("Z", "+00:00")))
              for o in book["orders"]]
    terms = {str(p["contract_id"]): ContractTerms(Instrument(p["instrument"]), D(p["strike"]),
                                                  datetime.date.fromisoformat(p["expiry"])) for p in book["positions"]}
    live = {str(p["contract_id"]): D(p["ltp"]) for p in book["positions"] if p["ltp"] is not None}
    return orders, terms, live


def _hand(entries: dict[str, Decimal], booked: Decimal) -> tuple[Decimal, Decimal]:
    """Max and min of the open legs' expiry P&L at 0 and every strike (the two tails are flat for this book)."""
    legs = [("PE", D("22600"), LOT, entries["PE22600"]), ("PE", D("22700"), -LOT, entries["PE22700"]),
            ("CE", D("23000"), LOT, entries["CE23000"]), ("CE", D("22950"), -LOT, entries["CE22950"])]

    def at(level: Decimal) -> Decimal:
        total = D(0)
        for kind, strike, net, entry in legs:
            value = max(level - strike, D(0)) if kind == "CE" else max(strike - level, D(0))
            total += (value - entry) * net
        return total + booked

    values = [at(x) for x in (D(0), D("22600"), D("22700"), D("22950"), D("23000"), D("30000"))]
    return max(values), min(values)


def test_core_strategy_63_after_the_roll_to_the_paisa() -> None:
    orders, terms, live = _real()
    view = net_positions(orders, live)
    got = book_extremes(view, terms, live)
    ltp = {"PE22600": D("60.65"), "PE22700": D("86.35"), "CE23000": D("86.95"), "CE22950": D("107.5")}
    avg = {"PE22600": D("72.60"), "PE22700": D("102.00"), "CE23000": D("80.95"), "CE22950": D("108.00")}
    left_high, left_low = _hand(ltp, D(0))
    orig_high, orig_low = _hand(avg, D("-633.75"))
    assert (left_high, left_low) == (D("3006.25"), D("-3493.75"))  # hand: credit 46.25 x 65; minus the 100-pt wing
    assert (orig_high, orig_low) == (D("3035.50"), D("-3464.50"))  # hand: credit 56.45 x 65 - 633.75 booked
    assert got.profit_left == left_high and got.loss_left == left_low
    assert got.max_profit == orig_high and got.max_loss == orig_low
    assert got.reason is None
    # the identity that ties both definitions together: original = live total + left, at every extreme
    assert got.max_profit == view.total + got.profit_left and got.max_loss == view.total + got.loss_left


def test_one_open_contract_not_live_pauses_left_but_keeps_the_original() -> None:
    orders, terms, live = _real()
    partial = {k: v for k, v in live.items() if k != "5572"}
    got = book_extremes(net_positions(orders, partial), terms, partial)
    assert (got.profit_left, got.loss_left, got.reason) == (None, None, PRICES_NOT_LIVE)
    assert (got.max_profit, got.max_loss) == (D("3035.50"), D("-3464.50"))


def test_fully_closed_book_is_zero_left_and_booked() -> None:
    orders = [PaperOrder("1", "SELL", 65, D("122.25"), "open", T0), PaperOrder("1", "BUY", 65, D("132.00"), "exit", T0)]
    terms = {"1": ContractTerms(Instrument.CE, D("22900"), EXPIRY)}
    got = book_extremes(net_positions(orders, {}), terms, {})
    assert (got.profit_left, got.loss_left, got.max_profit, got.max_loss, got.reason) == (
        D(0), D(0), D("-633.75"), D("-633.75"), None)


def test_open_contracts_on_two_expiries_have_no_figure() -> None:
    orders = [PaperOrder("1", "BUY", 65, D("80.00"), "open", T0), PaperOrder("2", "SELL", 65, D("90.00"), "open", T0)]
    terms = {"1": ContractTerms(Instrument.CE, D("23000"), EXPIRY),
             "2": ContractTerms(Instrument.CE, D("23000"), EXPIRY + datetime.timedelta(days=7))}
    live = {"1": D("81.00"), "2": D("91.00")}
    got = book_extremes(net_positions(orders, live), terms, live)
    assert got == type(got)(None, None, None, None, MULTI_EXPIRY)


def test_naked_short_call_loss_side_is_unlimited() -> None:
    orders = [PaperOrder("1", "SELL", 65, D("100.00"), "open", T0)]
    terms = {"1": ContractTerms(Instrument.CE, D("23000"), EXPIRY)}
    live = {"1": D("120.00")}
    got = book_extremes(net_positions(orders, live), terms, live)
    assert (got.profit_left, got.loss_left) == (D("7800.00"), UNLIMITED)  # 120 x 65 left to keep
    assert (got.max_profit, got.max_loss) == (D("6500.00"), UNLIMITED)


def test_original_uses_the_exact_average_not_the_rounded_one() -> None:
    # 3 buys at 100.00, 100.00, 100.05: average 100.01666..., rounded 100.02; at 0 the exact original is -300.05
    orders = [PaperOrder("1", "BUY", 1, D("100.00"), "open", T0), PaperOrder("1", "BUY", 1, D("100.00"), "add", T0),
              PaperOrder("1", "BUY", 1, D("100.05"), "add", T0)]
    terms = {"1": ContractTerms(Instrument.PE, D("100"), EXPIRY)}
    got = book_extremes(net_positions(orders, {}), terms, {})
    assert got.max_profit == D("-0.05") and got.max_loss == D("-300.05")


def test_partial_exit_keeps_booked_in_the_original_only() -> None:
    orders = [PaperOrder("1", "SELL", 130, D("100.00"), "open", T0), PaperOrder("1", "BUY", 65, D("60.00"), "exit", T0),
              PaperOrder("2", "BUY", 65, D("50.00"), "open", T0)]
    terms = {"1": ContractTerms(Instrument.PE, D("22700"), EXPIRY),
             "2": ContractTerms(Instrument.PE, D("22600"), EXPIRY)}
    live = {"1": D("70.00"), "2": D("40.00")}
    got = book_extremes(net_positions(orders, live), terms, live)
    # booked +2600; open short 22700 PE at 100 and long 22600 PE at 50: credit 50 x 65 = 3250, wing 6500
    assert (got.max_profit, got.max_loss) == (D("5850.00"), D("-650.00"))
    # from the LTP: credit 30 x 65 = 1950, wing 6500
    assert (got.profit_left, got.loss_left) == (D("1950.00"), D("-4550.00"))
