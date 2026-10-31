"""GC-ADJ2 step 6 review: adjust_history over the WHOLE scenario library (walks the fixture folder, so repo_scan).

Credit collected and premium still left equal the generator's own values for every scenario (futures are not premium;
a net-long option book shows no premium left)."""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.adjust_history import HistoryOrder, adjustment_history

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[2]
FOLDER = ROOT / "tests" / "fixtures" / "adjust_scenarios"
_spec = importlib.util.spec_from_file_location("seed_scenario_library", ROOT / "scripts" / "seed_scenario.py")
SEED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEED)


def _scenario_orders(doc: dict) -> list[HistoryOrder]:
    pos = doc["position"]
    clock = datetime.datetime.fromisoformat(pos["entry"]["clock"])
    return [HistoryOrder(leg.get("tradingsymbol") or f"{leg['type']}{leg['strike']}{leg['expiry']}", side,
                         int(leg["quantity"]), Decimal(price), kind, at,
                         is_option=leg["type"] != "FUT")
            for at, batch in SEED.placement_batches(pos, clock) for side, leg, price, kind in batch]


def test_every_library_scenario_matches_the_generators_credit_and_premium_left():
    """tests/adjust_scenarios_gen.py: credit_received = the option legs' cash (open_cash + hist_cash, futures out);
    premium_left = the open option legs' value, None for a debit (net long premium) book. 44 of 44 agree."""
    checked, bad, negative = 0, {}, []
    for path in sorted(FOLDER.glob("ADJ-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        quotes = {q["tradingsymbol"]: Decimal(str(q["last_price"])).quantize(Decimal("0.01"))
                  for q in (doc.get("broker", {}).get("quote") or {}).get("legs", [])
                  if q.get("last_price") is not None}
        t = adjustment_history(_scenario_orders(doc), quotes, adjustments_max=None).totals
        want_credit = Decimal(str(doc["position"]["credit_received"]))
        left = doc["expected"].get("premium_left")
        want_left = None if left is None else Decimal(str(left))
        if want_left is not None and want_left < 0:  # the generator prints a negative figure for a short family
            want_left = None  # whose options are net long (ADJ-37, ADJ-38); the product rule shows none (review 2)
            negative.append((doc["id"], t.premium_reason))
        if t.credit != want_credit or t.premium_left != want_left:
            bad[doc["id"]] = (t.credit, want_credit, t.premium_left, want_left)
        checked += 1
    assert (checked, bad) == (44, {})
    assert negative == [("ADJ-37", "net_long_premium"), ("ADJ-38", "net_long_premium")]
