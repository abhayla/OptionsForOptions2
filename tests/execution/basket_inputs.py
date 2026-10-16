"""Shared inputs for the W-080 basket tests: the real 2026-10-15 iron condor (request legs of margins_basket.json that
Kite accepted) and the catalogue rows of those four contracts (the recorded Zerodha list in tests/fixtures/kite_ws)."""
from __future__ import annotations

import csv
import json
from decimal import Decimal as D
from pathlib import Path

from ofo.engine import Action, Instrument, Leg
from ofo.execution.freeze import FreezeCheck
from ofo.execution.margin_gate import check_margin
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA
from ofo.instruments.parser import parse_instruments_rows

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "docs" / "research" / "kite-proof-2026-10-07" / "rest-2026-10-15" / "margins_basket.json"
LIST_CSV = ROOT / "tests" / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"


def request_legs() -> list[dict]:
    """The real request Kite accepted: exchange, tradingsymbol, transaction_type, quantity, price per leg."""
    return json.loads(PROOF.read_text(encoding="utf-8"))["request"]


def real_catalogue() -> Catalogue:
    wanted = {r["tradingsymbol"] for r in request_legs()}
    with LIST_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["tradingsymbol"] in wanted]
    assert len(rows) == 4, f"the recorded list must hold the four proof contracts, found {len(rows)}"  # noqa: PLR2004
    cat = Catalogue()
    cat.load(parse_instruments_rows(rows))
    return cat


def real_plan(cat: Catalogue, strategy_id: str = "S-9") -> ExecutionPlan:
    legs = []
    for i, req in enumerate(request_legs(), start=1):
        (entry,) = cat.entries_for_broker_symbol(ZERODHA, req["tradingsymbol"])
        c = entry.contract
        leg = Leg(Action(req["transaction_type"]), Instrument(c.instrument_type), c.strike, c.expiry, req["quantity"],
                  D(str(req["price"])))
        legs.append(PlannedLeg(f"L{i}", req["tradingsymbol"], leg))
    return ExecutionPlan(strategy_id, tuple(legs))


class OkMargin:
    """Fake margin gate returning W-081's real verdict (funds 1.00 vs required 0.00, or 0.00 vs 1.00 when blocked);
    records the orders it was asked about."""

    def __init__(self, allowed: bool = True) -> None:
        self.allowed, self.calls = allowed, []

    def __call__(self, orders):
        self.calls.append(orders)
        return check_margin(D("1.00"), D("0.00")) if self.allowed else check_margin(D("0.00"), D("1.00"))


class FakeFreeze:
    """Fake freeze gate returning a FreezeCheck with the given blocks (empty = pass); records its calls."""

    def __init__(self, blocks: tuple = ()) -> None:
        self.blocks, self.calls = blocks, []

    def __call__(self, plan):
        self.calls.append(plan)
        return FreezeCheck(self.blocks, ())
