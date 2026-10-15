"""AC-6: the charges rate table reproduces Kite's real /charges/orders replies (W-074, ADR-082 part 1, F-35).

Spec basis: REQ-032 AC-6 ("The engine exposes margin-planning and charges interfaces (IC §5)."); REQ-032 AC-4 ("All
money is computed in exact decimal or integer paise, never binary floating point"); ADR-082 ("The rates are admin
settings with the date they were read; every amount is exact Decimal; STT and stamp duty are not rounded at order
level").

The 8 rows come from the recorded replies of 2026-10-15 (docs/research/kite-proof-2026-10-07/). The RATES below are
typed from F-35's published text (brokerage Rs 20 per executed order; STT 0.15% on the sell premium; NSE transaction
0.03553%; SEBI Rs 10 per crore; GST 18% on brokerage + SEBI + transaction; stamp 0.003% on the buy premium), not read
from the calculator, so the test is an independent check. Every component Kite returned must match to 4 decimals;
Kite's order-level reply carries stamp 0 on every BUY, which the rate does not give (F-35), so stamp is asserted
against the rate and the difference from Kite is named, not hidden.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.charges import ChargeOrder, ChargeRates, charges_for_order, charges_for_orders

ROOT = Path(__file__).resolve().parents[2]
KITE = ROOT / "docs" / "research" / "kite-proof-2026-10-07"
FILES = (
    KITE / "rest-2026-10-15" / "charges_orders.json",
    KITE / "rest-2026-10-15-order" / "charges_CE.json",
    KITE / "rest-2026-10-15-order" / "charges_PE.json",
)
SOURCE = "https://zerodha.com/charges (F&O options)"
KITE_STAMP_NOTE = ("Kite order-level reply carries stamp 0; contract-note rounding unmeasured until the 4b order, "
                   "F-35")
PLACE = Decimal("0.0001")


def rates(**changes) -> ChargeRates:
    base = ChargeRates(
        brokerage_per_order=Decimal("20"),
        stt_sell_rate=Decimal("0.0015"),
        stt_exercise_rate=Decimal("0.0015"),
        transaction_rates={"NSE_FO": Decimal("0.0003553"), "BSE_FO": Decimal("0.000325")},
        sebi_rate=Decimal("0.000001"),
        stamp_buy_rate=Decimal("0.00003"),
        gst_rate=Decimal("0.18"),
        read_on=date(2026, 10, 15),
        source_url=SOURCE,
    )
    return replace(base, **changes)


def kite_rows() -> list[dict]:
    out = []
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        out.extend(data["reply"]["data"])
    return out


def order_of(row: dict) -> ChargeOrder:
    assert row["exchange"] == "NFO"
    return ChargeOrder(segment="NSE_FO", side=row["transaction_type"], quantity=row["quantity"],
                       price=Decimal(str(row["price"])))  # JSON "34" has no point: an int


def close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) < PLACE


def row_id(r: dict) -> str:
    return f"{r['transaction_type']}-{r['tradingsymbol']}-{r['price']}"


def test_there_are_eight_real_rows():
    rows = kite_rows()
    assert len(rows) == 8
    assert sorted(r["transaction_type"] for r in rows) == ["BUY"] * 4 + ["SELL"] * 4


@pytest.mark.parametrize("row", kite_rows(), ids=row_id)
def test_every_component_equals_kite(row):
    """AC-6: brokerage, STT, exchange transaction, SEBI, GST and total equal Kite's to 4 decimals."""
    got = charges_for_order(order_of(row), rates())
    k = row["charges"]
    assert close(got.brokerage, k["brokerage"]), "brokerage"
    assert close(got.stt, k["transaction_tax"]), "stt"
    assert close(got.exchange_transaction, k["exchange_turnover_charge"]), "exchange transaction"
    assert close(got.sebi, k["sebi_turnover_charge"]), "sebi"
    assert close(got.gst, k["gst"]["total"]), "gst"
    assert close(got.total - got.stamp, k["total"]), "total without stamp"


@pytest.mark.parametrize("row", kite_rows(), ids=row_id)
def test_stamp_is_the_rate_value_and_differs_from_kites_zero_on_buys(row):
    """AC-6: stamp = 0.003% of the BUY premium, unrounded (ADR-082); Kite's order-level 0 is named, not matched."""
    got = charges_for_order(order_of(row), rates())
    premium = row["price"] * row["quantity"]
    assert row["charges"]["stamp_duty"] == 0, KITE_STAMP_NOTE
    if row["transaction_type"] == "BUY":
        assert got.stamp == premium * Decimal("0.00003")
        assert got.stamp - row["charges"]["stamp_duty"] > 0, KITE_STAMP_NOTE
    else:
        assert got.stamp == Decimal("0")


def test_the_worked_example_from_the_brief():
    """AC-6: BUY 22550 PE 34.00 x 65: premium 2,210.00, stamp 0.0663 (hand computation: 2210 x 0.00003)."""
    got = charges_for_order(ChargeOrder("NSE_FO", "BUY", 65, Decimal("34.00")), rates())
    assert got.stamp == Decimal("0.0663")
    assert got.stt == Decimal("0")
    assert got.exchange_transaction == Decimal("0.785213")  # 2210 x 0.0003553
    assert got.sebi == Decimal("0.00221")


def test_strategy_total_is_the_sum_of_order_totals():
    """AC-6: the four-leg proof strategy total is the sum of its order totals (hand sum of Kite's four totals
    30.253343593 + 24.072778033 + 31.7325578815 + 24.52915914 = 110.5878188475, plus the two buy stamps)."""
    rows = kite_rows()[:4]
    got = charges_for_orders([order_of(r) for r in rows], rates())
    assert got.total == sum((o.total for o in got.orders), Decimal("0"))
    stamps = Decimal("17.3") * 65 * Decimal("0.00003") + Decimal("34") * 65 * Decimal("0.00003")
    assert close(got.total - stamps, Decimal("110.5878188475"))


# --- mutation guards: each rate changed by one digit must turn the proof red -------------------------------------

MUTATIONS = {
    "brokerage 20->21": {"brokerage_per_order": Decimal("21")},
    "stt 0.15%->0.16%": {"stt_sell_rate": Decimal("0.0016")},
    "nse 0.03553%->0.03554%": {"transaction_rates": {"NSE_FO": Decimal("0.0003554"), "BSE_FO": Decimal("0.000325")}},
    "sebi 10->11 per crore": {"sebi_rate": Decimal("0.0000011")},
    "gst 18->19": {"gst_rate": Decimal("0.19")},
}


def matches_kite_everywhere(r: ChargeRates) -> bool:
    for row in kite_rows():
        got = charges_for_order(order_of(row), r)
        k = row["charges"]
        ok = (close(got.brokerage, k["brokerage"]) and close(got.stt, k["transaction_tax"])
              and close(got.exchange_transaction, k["exchange_turnover_charge"])
              and close(got.sebi, k["sebi_turnover_charge"]) and close(got.gst, k["gst"]["total"])
              and close(got.total - got.stamp, k["total"]))
        if not ok:
            return False
    return True


def test_the_unmutated_rates_match_everywhere():
    assert matches_kite_everywhere(rates())


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_a_one_digit_change_to_any_rate_goes_red(name):
    assert not matches_kite_everywhere(rates(**MUTATIONS[name])), name
