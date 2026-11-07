"""ADR-266: a leg whose LTP is outside its bid/ask is marked at the bid-ask mid (rows from the scenario library)."""
from __future__ import annotations

import sys
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.adjustment.approaches import ChainRow
from ofo_app.adjustment_check import mark_of

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "adjustment"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_adjust_scenarios import load
from test_playbook_eval import _row


def _chain_row(ltp, bid, ask):
    sc = load("ADJ-01")
    leg = next(x for x in sc["position"]["legs"] if x["type"] != "FUT")
    r = _row(sc, leg)
    return ChainRow(D(r["strike"]), r["type"], None, r["tradingsymbol"],
                    ltp=ltp if ltp != "own" else D(r["ltp"]),
                    bid=bid if bid != "own" else D(r["bid"]), ask=ask if ask != "own" else D(r["ask"]))


@pytest.mark.parametrize(("ltp", "bid", "ask", "want"), [
    ("own", "own", "own", "own"),               # consistent: the LTP
    (D("9.00"), D("4.00"), D("4.10"), D("4.05")),  # LTP above the ask: the mid
    (D("1.00"), D("4.00"), D("4.10"), D("4.05")),  # LTP below the bid: the mid
    (D("4.05"), D("4.00"), D("4.10"), D("4.05")),
    (D("9.00"), D("4.00"), D("4.01"), D("4.00")),  # half-paisa mid 4.005 -> half-even 4.00
    (D("9.00"), None, D("4.10"), D("9.00")),    # bid missing: the LTP
    (D("9.00"), D("4.00"), None, D("9.00")),    # ask missing: the LTP
    (D("9.00"), D("0"), D("4.10"), D("9.00")),  # zero book: the LTP
    (D("9.00"), D("4.20"), D("4.10"), D("9.00")),  # crossed: the LTP
    (None, D("4.00"), D("4.10"), None),         # no LTP: unpriced, never a stand-in
])
def test_mark(ltp, bid, ask, want):
    row = _chain_row(ltp, bid, ask)
    assert mark_of(row) == (row.ltp if want == "own" else want)


def test_no_row_is_unpriced():
    assert mark_of(None) is None
