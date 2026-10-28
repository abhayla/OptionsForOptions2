"""GC-UI step 4 server round 3, item 2 (D-B28, the Match-now half): the table's TOTAL row carries the strategy's NET
per-unit Entry and LTP from the engine (sells +, buys -, summed per unit over the legs: the basis the summary's "per
unit" net premium uses), Decimal, with Cr / Dr display text; never computed in the browser. The "Projected" label is
Later and not built here.

Real rows: strategy 54 (BUY 22600 CE / SELL 22800 CE, 1 lot, 13-Oct) on the recorded 2026-10-08 NIFTY replay; every
expected figure is the legs' own cells. Answer states: both legs priced; a leg with no LTP (TOTAL LTP absent with the
existing reason "not every leg has an LTP"); unequal quantities (no per-unit net, the reason says so)."""
from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from ofo.errors.explanations import render_explanation
from ofo.outcome import build_outcome
from ofo.outcome.serialize import outcome_to_dict
from outcome._both_curves_cases import S54, as_json, definition, market, snapshot
from outcome.test_same_engine import VALUATION


@pytest.fixture(scope="module")
def provider():
    return market()


def _rows(out) -> dict:
    return {r["row_id"]: r["cells"] for r in as_json(outcome_to_dict(out))["table"]["rows"]}


def _signed(cells, column) -> Decimal:
    side = -1 if cells["action"]["value"] == "BUY" else 1
    return side * Decimal(cells[column]["value"])


def _expected_cell(net: Decimal) -> tuple[str, str | None, str]:
    template = "cell_rupees_cr" if net > 0 else "cell_rupees_dr" if net < 0 else "cell_rupees"
    side = "Cr" if net > 0 else "Dr" if net < 0 else None
    return f"{abs(net):f}", side, render_explanation(template, amount=abs(net))


@pytest.mark.parametrize("column", ["entry_price", "ltp"])
def test_total_row_net_per_unit_is_the_signed_sum_of_the_legs_per_unit_prices(provider, column):
    d = definition(provider, S54)
    rows = _rows(build_outcome(d, snapshot(provider, d), VALUATION))
    legs = [cells for rid, cells in rows.items() if rid != "TOTAL"]
    net = sum((_signed(c, column) for c in legs), Decimal(0))
    total = rows["TOTAL"][column]
    assert (total["value"], total["side"], total["display"]) == _expected_cell(net)
    assert total["kind"] == "money" and total["reason"] is None
    assert net == Decimal("-62.40") or column == "ltp"  # 39.15 sold - 101.55 bought = 62.40 Dr per unit


def test_total_entry_matches_the_summarys_per_unit_net_premium(provider):
    d = definition(provider, S54)
    body = as_json(outcome_to_dict(build_outcome(d, snapshot(provider, d), VALUATION)))
    total = {r["row_id"]: r for r in body["table"]["rows"]}["TOTAL"]["cells"]["entry_price"]
    assert total["value"] == body["summary"]["net_premium"]["per_unit"]  # one basis: "62.40 per unit"


def test_a_leg_with_no_ltp_leaves_the_total_ltp_absent_with_the_existing_reason(provider):
    d = definition(provider, S54)
    snap = snapshot(provider, d)
    legs = dict(snap.legs)
    leg = S54[1][0]
    legs[leg] = dataclasses.replace(legs[leg], quote=dataclasses.replace(legs[leg].quote, ltp=Decimal("0")))
    rows = _rows(build_outcome(d, dataclasses.replace(snap, legs=legs), VALUATION))
    total = rows["TOTAL"]
    assert total["ltp"]["value"] is None and total["ltp"]["reason"] == render_explanation("table_reason_not_all_ltp")
    assert total["ltp"]["display"] == render_explanation("cell_dash")
    assert total["entry_price"]["value"] is not None  # the entry side does not need an LTP


def test_unequal_quantities_have_no_per_unit_net_and_say_why(provider):
    d = definition(provider, S54)
    d = dataclasses.replace(d, legs=(dataclasses.replace(d.legs[0], lots=2), d.legs[1]))
    rows = _rows(build_outcome(d, snapshot(provider, d), VALUATION))
    for column in ("entry_price", "ltp"):
        cell = rows["TOTAL"][column]
        assert cell["value"] is None and cell["reason"] == render_explanation("table_reason_not_same_quantity")
