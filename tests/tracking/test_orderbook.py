"""GC-TP step 1a core proof and rules of the paper order book (REQ-109 AC-4, AC-5; ADR-207).

The real figures: tests/fixtures/paper/before-2026-10-29.json is the live ``GET /tracking`` reply at 10:55:17 IST on
2026-10-29 for 18 paper strategies (ids 46-63). Each leg becomes orders exactly as migration 0028 writes them (one
``open`` order at entry_price; one opposite ``exit`` order at exit_price for an exited leg); the engine at the reply's
current prices must give every strategy's total / booked / unbooked and every leg's pnl to the paisa.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.tracking import paper
from ofo.tracking.orderbook import PaperOrder, net_positions

D = Decimal
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "paper" / "before-2026-10-29.json"
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
OPPOSITE = {"BUY": "SELL", "SELL": "BUY"}


def _at(text: str | None) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")) if text else T0


def _orders_as_migration(strategy: dict) -> list[PaperOrder]:
    opens = [PaperOrder(leg["instrument_id"], leg["action"], leg["quantity"], D(leg["entry_price"]), "open",
                        _at(leg["entry_at"])) for leg in strategy["legs"]]
    exits = [PaperOrder(leg["instrument_id"], OPPOSITE[leg["action"]], leg["quantity"], D(leg["exit_price"]), "exit",
                        _at(leg["exited_at"])) for leg in strategy["legs"] if leg["exit_price"] is not None]
    return opens + exits


def _strategies() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["strategies"]


def test_fixture_is_the_18_real_strategies() -> None:
    assert [s["strategy_id"] for s in _strategies()] == list(range(46, 64))


@pytest.mark.parametrize("strategy", _strategies(), ids=lambda s: str(s["strategy_id"]))
def test_real_figures_equal_the_live_reply_to_the_paisa(strategy: dict) -> None:
    live = {leg["instrument_id"]: D(leg["current_price"]) for leg in strategy["legs"] if leg["current_price"]}
    view = net_positions(_orders_as_migration(strategy), live)
    assert view.total == D(strategy["total"])
    assert view.booked == D(strategy["booked"])
    assert view.unbooked == D(strategy["unbooked"])
    assert [p.instrument_id for p in view.positions] == [leg["instrument_id"] for leg in strategy["legs"]]
    for pos, leg in zip(view.positions, strategy["legs"], strict=True):
        assert pos.total == D(leg["pnl"]), leg["instrument_id"]
        if leg["exit_price"] is not None:
            assert (pos.net_quantity, pos.unbooked, pos.last_price) == (0, D(0), D(leg["exit_price"]))
        else:
            sign = 1 if leg["action"] == "BUY" else -1
            assert (pos.net_quantity, pos.average) == (sign * leg["quantity"], D(leg["entry_price"]))


@pytest.mark.parametrize("strategy", _strategies(), ids=lambda s: str(s["strategy_id"]))
def test_engine_arithmetic_equals_paper_leg_pnl_on_every_real_leg(strategy: dict) -> None:
    for leg in strategy["legs"]:
        tracked = paper.TrackedLeg(leg["instrument_id"], Action[leg["action"]], Instrument[leg["instrument"]],
                                   D(leg["strike"]) if leg["strike"] else None,
                                   datetime.date.fromisoformat(leg["expiry"]), leg["quantity"], D(leg["entry_price"]),
                                   T0)
        price = D(leg["exit_price"] or leg["current_price"])
        orders = [PaperOrder(leg["instrument_id"], leg["action"], leg["quantity"], D(leg["entry_price"]), "open", T0)]
        assert net_positions(orders, {leg["instrument_id"]: price}).total == paper.leg_pnl(tracked, price)
        orders.append(PaperOrder(leg["instrument_id"], OPPOSITE[leg["action"]], leg["quantity"], price, "exit", T0))
        assert net_positions(orders, {}).booked == paper.leg_pnl(tracked, price)


def _o(side: str, qty: int, price: str, kind: str = "add", iid: str = "C1") -> PaperOrder:
    return PaperOrder(iid, side, qty, D(price), kind, T0)


def test_average_is_weighted_over_increasing_orders_only() -> None:
    view = net_positions([_o("BUY", 50, "100.00", "open"), _o("BUY", 25, "130.00"), _o("SELL", 25, "150.00", "exit"),
                          _o("BUY", 50, "90.00")], {"C1": D("100.00")})
    pos = view.positions[0]
    # avg after two buys = 110; the sell books (150-110)x25 = 1000 and leaves avg 110; buy 50 @ 90 -> (110x50+90x50)/100
    assert (pos.net_quantity, pos.average) == (100, D(100))
    assert pos.booked == D(1000)
    assert pos.unbooked == D(0)


def test_reducing_a_short_books_average_minus_exit() -> None:
    pos = net_positions([_o("SELL", 65, "200.00", "open"), _o("BUY", 30, "150.00", "exit")], {"C1": D("180.00")}
                        ).positions[0]
    assert pos.booked == D("1500.00")  # (200 - 150) x 30
    assert pos.average == D("200.00")
    assert pos.unbooked == D("700.00")  # (200 - 180) x 35
    assert (pos.net_quantity, pos.booked) == (-35, D("1500.00"))


def test_crossing_zero_books_the_closing_part_and_opens_the_rest_at_its_price() -> None:
    pos = net_positions([_o("BUY", 50, "100.00", "open"), _o("SELL", 80, "120.00")], {"C1": D("110.00")}).positions[0]
    assert pos.booked == D("1000.00")
    assert (pos.net_quantity, pos.average) == (-30, D("120.00"))
    assert pos.unbooked == D("300.00")


def test_flat_contract_has_only_booked() -> None:
    view = net_positions([_o("BUY", 10, "5.00", "open"), _o("SELL", 10, "7.50", "exit")], {})
    pos = view.positions[0]
    assert (pos.net_quantity, pos.average, pos.unbooked, pos.booked, pos.total) == (0, None, D(0), D(25), D(25))
    assert (view.booked, view.unbooked, view.total) == (D(25), D(0), D(25))


def test_fractional_average_still_sums_to_order_level_pnl_exactly() -> None:
    orders = [_o("BUY", 1, "100.00", "open"), _o("BUY", 1, "100.00"), _o("BUY", 1, "100.05"),
              _o("SELL", 1, "101.00", "exit"), _o("SELL", 2, "99.99", "exit")]
    partial = net_positions(orders[:4], {"C1": D("100.50")})
    assert partial.positions[0].average != partial.positions[0].average.quantize(D("0.01"))  # 100.0166...
    assert partial.booked + partial.unbooked == partial.total
    assert partial.total == D("101.00") + D("100.50") * 2 - D("300.05")
    flat = net_positions(orders, {})
    cash = sum((o.price * o.quantity * (-1 if o.side == "BUY" else 1) for o in orders), D(0))
    assert flat.booked == cash == flat.total
    assert flat.booked == flat.booked.quantize(D("0.01"))


def test_contracts_come_out_in_first_order_order() -> None:
    view = net_positions([_o("BUY", 1, "1.00", "open", "B"), _o("SELL", 1, "2.00", "open", "A"),
                          _o("BUY", 1, "3.00", iid="B")], {"A": D(1), "B": D(1)})
    assert [p.instrument_id for p in view.positions] == ["B", "A"]


def test_no_orders_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one order"):
        net_positions([], {})


def test_absent_live_price_gives_no_unbooked_and_no_total() -> None:
    view = net_positions([_o("BUY", 1, "1.00", "open", "A"), _o("BUY", 1, "1.00", "open", "B"),
                          _o("SELL", 1, "2.00", "exit", "B")], {})
    assert view.positions[0].unbooked is None and view.positions[0].total is None
    assert (view.booked, view.unbooked, view.total) == (D("1.00"), None, None)


@pytest.mark.parametrize("price", ["100.001", "0", "-1.00"])
def test_bad_order_price_is_refused(price: str) -> None:
    with pytest.raises(ValueError):
        _o("BUY", 1, price, "open")


def test_live_price_finer_than_a_paisa_is_refused() -> None:
    with pytest.raises(ValueError, match="finer than a paisa"):
        net_positions([_o("BUY", 1, "1.00", "open")], {"C1": D("1.005")})


def test_legacy_off_tick_paisa_price_is_accepted() -> None:
    assert net_positions([_o("BUY", 1, "187.37", "open")], {"C1": D("187.38")}).total == D("0.01")


@pytest.mark.parametrize("bad", [{"quantity": 0}, {"side": "HOLD"}, {"kind": "modify"}])
def test_bad_order_fields_are_refused(bad: dict) -> None:
    fields = {"instrument_id": "C1", "side": "BUY", "quantity": 1, "price": D(1), "kind": "open", "placed_at": T0}
    with pytest.raises(ValueError):
        PaperOrder(**(fields | bad))
