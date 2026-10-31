# ruff: noqa: PLR2004 - exact expected amounts are the assertions
"""ADR-221 / ADR-222 (8): T-19 compares premium left with the CHEAPEST offered approach's Compare cost.

Class one-money-figure-two-formulas: the Compare's "This adjustment" cell and the T-19 cost both come from
``compare.approach_cost``; the old full-spread + Rs 40 a leg helper is gone. Expected values are the scenario
library's hand path (``adjust_scenarios_gen.hand_cheapest``: charges at the library's rates + half spread), so the
engine path (route build + ``approach_cost``) and the generator check each other.

Answer states of "cheapest approach cost": all priced -> cheapest named; some unpriceable -> cheapest of the priced;
none priceable -> T-19 not checked (reason); nothing offered -> not checked (reason); a tie -> first in playbook order.
"""
from __future__ import annotations

import dataclasses
import json
from decimal import Decimal as D

import pytest
import t19_support as s
from ofo.adjustment import compare as cmp
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.compare import Column, MarginRead, approach_cost, cheapest_approach, offered_approaches
from ofo.engine import adjust_money
from ofo_app import adjustment_check as check
from ofo_app.routes.adjustment import priced_approach

IDS = sorted(p.stem for p in s.FIX.glob("ADJ-*.json"))


def _columns(sid: str) -> tuple[dict, dict[str, Column], object]:
    sc = s.load(sid)
    tracked, market, spot = s.inputs(sc)
    cols = {}
    for a in offered_approaches(s.body_of(sc)):
        built, priced = priced_approach(a, tracked, market, spot, s.RATES)
        if built is not None and priced is not None:
            cols[a] = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None))
    return sc, cols, market


@pytest.mark.parametrize("sid", IDS)
def test_t19_cost_equals_the_cheapest_compare_cell_for_every_scenario(sid):
    """Task 6: for EVERY scenario, the checker's T-19 cost is the Compare's lowest offered "This adjustment" cell (to
    the paisa) and equals the generator's hand figure; no cell priced -> the not-checked reason."""
    sc = s.load(sid)
    tracked, market, spot = s.inputs(sc)
    offered = offered_approaches(s.body_of(sc))
    _, cols, _ = _columns(sid)
    cells = {a: c for a, c in s.compare_costs(tracked, market, spot).items()
             if a in offered and c.value is not None and cols[a].built.trades}  # a no-trade column is not an adjustment
    got = s.cheapest(sc)
    if not cells:
        assert (got.approach, got.cost, got.reason) == (None, None, cmp.NO_APPROACH_PRICED)
    else:
        low = min(c.value for c in cells.values())
        assert got.cost == low and cells[got.approach].value == low
        assert got.approach == next(a for a in offered if a in cells and cells[a].value == low)  # playbook order
    assert (None if got.cost is None else str(got.cost)) == sc["expected"]["adjustment_cost"]
    assert got.approach == sc["expected"]["adjustment_approach"]


def test_core_adj02_cheapest_is_a29_at_rs_92_35_the_compare_cell():
    """The core proof, pinned: ADJ-02's Compare cells and T-19's cost (old formula gave Rs 342.00)."""
    sc = s.load("ADJ-02")
    tracked, market, spot = s.inputs(sc)
    cells = {a: c.value for a, c in s.compare_costs(tracked, market, spot).items()}
    assert cells == {"A-36": D("0.00"), "A-01": D("173.36"), "A-05": D("250.44"), "A-29": D("92.35"),
                     "A-28": D("137.49"), "A-11": D("575.99"), "A-31": D("198.06")}
    got = s.cheapest(sc)
    assert (got.approach, got.cost) == ("A-29", D("92.35"))


def test_all_priced_names_the_cheapest():
    sc, cols, market = _columns("ADJ-02")
    assert len(cols) == 6
    assert cheapest_approach(offered_approaches(s.body_of(sc)), cols, market.chain) == cmp.Cheapest("A-29", D("92.35"))


def test_some_unpriceable_takes_the_cheapest_of_the_priced():
    sc, cols, market = _columns("ADJ-02")
    a29 = cols["A-29"]
    no_charges = dataclasses.replace(a29, charges_known=False)  # A-29's charges unknown -> "-" -> left out
    got = cheapest_approach(offered_approaches(s.body_of(sc)), {**cols, "A-29": no_charges}, market.chain)
    assert got == cmp.Cheapest("A-28", D("137.49"))
    no_whole = dataclasses.replace(a29, whole=None)
    assert cheapest_approach(("A-29", "A-31"), {**cols, "A-29": no_whole}, market.chain) == \
        cmp.Cheapest("A-31", D("198.06"))
    no_quote = tuple(dataclasses.replace(r, bid=None) if r.tradingsymbol == a29.built.trades[0].tradingsymbol else r
                     for r in market.chain)
    assert cheapest_approach(("A-29", "A-01"), cols, no_quote) == cmp.Cheapest("A-01", D("173.36"))


def test_none_priceable_is_not_checked_with_the_reason():
    sc = s.load("ADJ-14")
    got = s.cheapest(sc)
    assert got == cmp.Cheapest(None, None, cmp.NO_APPROACH_PRICED)
    ev = pe.evaluate(s.body_of(sc), pe.StrategyState("weekly", days_left=1, hhmm="15:00", spot=D("23020"),
                                                       premium_left=D("110.50"), adjustment_cost_reason=got.reason,
                                                       prices_fresh=True))
    t19 = next(r for r in ev.results if r.trigger_id == "T-19")
    assert isinstance(t19, pe.NotChecked) and t19.code == cmp.NO_APPROACH_PRICED
    assert pe.reason_text(t19.code).startswith("No adjustment approach this playbook offers can be priced now")


def test_no_approach_offered_is_not_checked_with_the_reason():
    sc, cols, market = _columns("ADJ-02")
    body = s.body_of(sc)
    body["approaches"]["applicable"] = ["A-36"]  # only "No change": nothing to price
    assert offered_approaches(body) == ()
    assert cheapest_approach((), cols, market.chain) == cmp.Cheapest(None, None, cmp.NO_APPROACH_OFFERED)
    tracked, market, spot = s.inputs(sc)
    got = check.cheapest_offered(body, tracked, market, spot, s.RATES)
    assert got.reason == cmp.NO_APPROACH_OFFERED
    assert pe.reason_text(got.reason).startswith("This playbook offers no adjustment approach to price")


def test_a_tie_keeps_the_first_in_playbook_order():
    sc, cols, market = _columns("ADJ-02")
    a28 = cols["A-28"]
    whole = dataclasses.replace(a28.whole, adjustment_charges=a28.whole.adjustment_charges - D("45.14"))
    tied = {**cols, "A-28": dataclasses.replace(a28, whole=whole)}
    rows = cmp.chain_index(market.chain)
    assert approach_cost(tied["A-28"], rows).value == approach_cost(cols["A-29"], rows).value == D("92.35")
    assert cheapest_approach(("A-28", "A-29"), tied, market.chain).approach == "A-28"
    assert cheapest_approach(("A-29", "A-28"), tied, market.chain).approach == "A-29"


def test_t19_fires_below_and_not_above_the_cheapest_cost():
    """Task 5's two cases, through the evaluator on the engine's own cost."""
    for sid, fires in (("ADJ-43", True), ("ADJ-44", False)):
        sc = s.load(sid)
        got = s.cheapest(sc)
        left = D(sc["expected"]["premium_left"])
        assert (left < got.cost) is fires, sid
        assert any(f["id"] == "T-19" for f in sc["expected"]["triggers_fired"]) is fires, sid


def test_the_flag_line_names_the_approach_and_its_cost():
    line = check.condition_line_t19("Premium still left is below this x the adjustment cost", "0.3629", "1.0000",
                                    "A-28", D("53.73"))
    text = str(line)
    assert "Close the tested leg or spread" in text or "A-28" not in text
    assert "53.73" in text and "0.3629" in text and "1.0000" in text
    fallback = check.condition_line_t19("Premium still left", "0.3629", "1.0000", "A-99", D("53.73"))
    assert "53.73" not in str(fallback)  # an approach the slot refuses -> the plain line, never a guessed name


def test_the_old_per_leg_cost_is_gone_everywhere():
    assert not hasattr(adjust_money, "adjustment_cost")
    assert not hasattr(check, "COST_PER_LEG")
    conv = json.loads((s.FIX / "_playbooks.json").read_text(encoding="utf-8"))["conventions"]["adjustment_cost"]
    assert "40" not in conv and "ADR-221" in conv
