"""GC-TP step 1a part 4: ofo.tracking.book shows a paper order book as one leg per contract (REQ-109 AC-4).

Real figures: strategy 48's leg 2 (SELL 65 x 22600 CE at 166.90, exited at 190.05 -> booked -1,504.75) and leg 0
(BUY 65 x 22300 PE at 114.25), tests/fixtures/paper/before-2026-10-29.json.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.tracking.book import contract_legs
from ofo.tracking.orderbook import PaperOrder

D = Decimal
T0 = datetime.datetime(2026, 10, 28, 5, 2, 45, tzinfo=datetime.UTC)


def _at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def test_open_and_exited_contracts_in_first_order_order():
    orders = [PaperOrder("53663", "BUY", 65, D("114.25"), "open", _at(0)),
              PaperOrder("53720", "SELL", 65, D("166.90"), "open", _at(0)),
              PaperOrder("53720", "BUY", 65, D("190.05"), "exit", _at(48))]
    legs = contract_legs(orders)
    assert [(leg.instrument_id, leg.side, leg.quantity, leg.average, leg.exit_price, leg.booked) for leg in legs] == [
        ("53663", "BUY", 65, D("114.25"), None, D(0)),
        ("53720", "SELL", 65, D("166.90"), D("190.05"), D("-1504.75"))]
    assert (legs[1].exited, legs[1].exited_at, legs[1].entry_at, legs[0].exited) == (True, _at(48), _at(0), False)


def test_a_partly_exited_contract_shows_its_open_quantity_and_keeps_its_booked_part():
    orders = [PaperOrder("53663", "BUY", 65, D("114.25"), "open", _at(0)),
              PaperOrder("53663", "SELL", 25, D("21.70"), "exit", _at(5))]
    (leg,) = contract_legs(orders)
    # (21.70 - 114.25) x 25 = -2,313.75
    assert (leg.side, leg.quantity, leg.average, leg.exited, leg.booked) == ("BUY", 40, D("114.25"), False,
                                                                            D("-2313.75"))


def test_an_exited_contract_shows_the_quantity_and_average_it_closed():
    orders = [PaperOrder("1", "BUY", 65, D("100.00"), "open", _at(0)),
              PaperOrder("1", "BUY", 65, D("100.05"), "add", _at(1)),
              PaperOrder("1", "SELL", 130, D("101.00"), "exit", _at(2))]
    (leg,) = contract_legs(orders)
    # average 100.025; booked (101.00 - 100.025) x 130 = 126.75
    assert (leg.side, leg.quantity, leg.average, leg.exit_price, leg.booked) == ("BUY", 130, D("100.025"),
                                                                                 D("101.00"), D("126.75"))


def test_no_orders_is_refused():
    with pytest.raises(ValueError, match="at least one order"):
        contract_legs([])
