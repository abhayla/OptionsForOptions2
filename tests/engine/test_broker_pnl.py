"""Lane S (REQ-044 AC-3; ADR-008, ADR-016/018): the engine re-derives Zerodha's own `pnl` from Zerodha's own fields.

Real input: tests/fixtures/kite_replies/positions-151006.json data.net[0] (NIFTY26O1923650CE, the owner's 16 Oct 2026
round trip): sell_value 201.5 - buy_value 331.5 + 0 x 3.1 x 1 = -130.00 == Zerodha's pnl -130.
"""
from __future__ import annotations

import copy
import json
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.broker_pnl import BrokerPnl, broker_contract_pnl, broker_total

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "kite_replies" / "positions-151006.json"
FIELDS = ("pnl", "buy_value", "sell_value", "quantity", "last_price", "multiplier")


def real_row() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]["net"][0]


def fields(row: dict) -> dict:
    return {k: row[k] for k in FIELDS if k in row}


def test_real_closed_row_is_stated():
    got = broker_contract_pnl(fields(real_row()))
    assert got == BrokerPnl("stated", Decimal("-130.00"), Decimal("-130.00"), Decimal("-130.00"))
    assert str(got.value) == "-130.00"


def test_real_open_row_is_stated():
    """The owner's real OPEN row (positions-122104.json, 16 Oct 2026 12:21:07): 0 - 331.5 + 65 x 5.1 x 1 = 0.00."""
    path = FIXTURE.with_name("positions-122104.json")
    row = json.loads(path.read_text(encoding="utf-8"))["data"]["net"][0]
    assert row["quantity"] == 65 and row["pnl"] == 0
    got = broker_contract_pnl(fields(row))
    assert got == BrokerPnl("stated", Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))


def test_derived_open_row_is_stated():
    row = copy.deepcopy(real_row())
    row.update(quantity=-65, buy_value=0, buy_quantity=0, sell_value="331.5", last_price="3.1", pnl=130)
    # 65 sold at 5.1 = 331.5; held short 65 at 3.1: 331.5 - 0 + (-65 x 3.1 x 1) = 130.0
    got = broker_contract_pnl(fields(row))
    assert got.state == "stated" and str(got.value) == "130.00"


def test_tampered_row_is_mismatch_with_no_value():
    row = real_row()
    row["pnl"] = -131
    got = broker_contract_pnl(fields(row))
    assert got.state == "mismatch" and got.value is None
    assert got.reported == Decimal("-131.00") and got.derived == Decimal("-130.00")


@pytest.mark.parametrize("name", FIELDS)
def test_each_missing_field_is_not_available(name):
    f = fields(real_row())
    del f[name]
    got = broker_contract_pnl(f)
    assert got.state == "not_available" and got.value is None


@pytest.mark.parametrize("bad", [None, True, False, "abc", "", "1e2", "NaN", 1.5, [1], {}, Decimal("NaN"),
                                 Decimal("Infinity")])
@pytest.mark.parametrize("name", FIELDS)
def test_bad_value_is_not_available_never_zero(name, bad):
    f = fields(real_row())
    f[name] = bad
    got = broker_contract_pnl(f)
    assert got.state == "not_available" and got.value is None


def test_float_noise_in_reported_quantizes_to_stated():
    f = fields(real_row())
    f["pnl"] = Decimal("-129.999999999")
    got = broker_contract_pnl(f)
    assert got.state == "stated" and got.value == Decimal("-130.00")


def test_half_even_quantize_of_both_sides():
    f = {"pnl": "0.125", "buy_value": "0", "sell_value": "0.125", "quantity": 0, "last_price": "1", "multiplier": 1}
    got = broker_contract_pnl(f)  # 0.125 -> 0.12 on both sides (ROUND_HALF_EVEN)
    assert got.state == "stated" and got.value == Decimal("0.12")


def test_several_rows_of_one_contract_are_summed_before_the_check():
    a = fields(real_row())
    b = copy.deepcopy(a)
    got = broker_contract_pnl([a, b])
    assert got.state == "stated" and got.value == Decimal("-260.00")
    # a row whose own pnl is off but whose sum matches is still stated: the check is per contract
    assert broker_contract_pnl([{**a, "pnl": -100}, {**b, "pnl": -160}]).state == "stated"
    assert broker_contract_pnl([a, {**b, "pnl": -131}]).state == "mismatch"


def test_one_unreadable_row_makes_the_contract_not_available():
    a = fields(real_row())
    assert broker_contract_pnl([a, {**a, "pnl": None}]).state == "not_available"
    assert broker_contract_pnl([]).state == "not_available"


def test_total_is_exact_sum_only_when_every_row_is_stated():
    ok = broker_contract_pnl(fields(real_row()))
    assert broker_total([ok, ok]) == Decimal("-260.00")
    assert broker_total([ok, BrokerPnl("mismatch", None, Decimal("1.00"), Decimal("2.00"))]) is None
    assert broker_total([]) is None


def test_count_without_figure():
    from ofo.engine.broker_pnl import count_without_figure

    ok = broker_contract_pnl(fields(real_row()))
    assert count_without_figure([ok, BrokerPnl("mismatch", None, None, None), BrokerPnl("not_available", None, None,
                                                                                        None)]) == 2
    assert count_without_figure([]) == 0
