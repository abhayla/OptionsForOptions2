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
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # t19_support sits next to this file
import t19_support as s
from ofo.adjustment import compare as cmp
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.compare import Column, MarginRead, approach_cost, cheapest_approach, offered_approaches
from ofo.adjustment.offered import EXIT_REDUCE, offered_now
from ofo.engine import adjust_money
from ofo_app import adjustment_check as check
from ofo_app.routes.adjustment import priced_approach

pytestmark = pytest.mark.repo_scan  # reads every scenario fixture file

IDS = sorted(p.stem for p in s.FIX.glob("ADJ-*.json"))


def _columns(sid: str) -> tuple[dict, dict[str, Column], object]:
    sc = s.load(sid)
    tracked, market, spot = s.inputs(sc)
    cols = {}
    for a in offered_approaches(s.body_of(sc)):
        built, priced = priced_approach(a, tracked, market, spot, s.RATES, s.PREFS.approach)
        if built is not None and priced is not None:
            cols[a] = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None))
    return sc, cols, market


@pytest.mark.parametrize("sid", IDS)
def test_t19_cost_equals_the_cheapest_compare_cell_for_every_scenario(sid):
    """Task 6: for EVERY scenario, the checker's T-19 cost is the Compare's lowest offered "This adjustment" cell (to
    the paisa) and equals the generator's hand figure; no cell priced -> the not-checked reason."""
    sc = s.load(sid)
    tracked, market, spot = s.inputs(sc)
    cells = {a: c for a, c in s.compare_costs(tracked, market, spot).items() if c.value is not None}
    got = s.cheapest(sc)  # the engine path; the expected figures are the generator's independent hand path
    if sc["expected"]["adjustment_approach"] is None:
        assert (got.approach, got.cost, got.reason) == (None, None, cmp.NO_APPROACH_PRICED)
    else:
        assert (got.approach, str(got.cost)) == (sc["expected"]["adjustment_approach"], sc["expected"]["adjustment_cost"])  # noqa: E501
        if got.approach in cells:  # a column the Compare shows carries the same figure (to the paisa)
            assert cells[got.approach].value == got.cost
        assert all(c.value >= got.cost for a, c in cells.items() if a != "A-36")  # nothing shown is cheaper
    assert (None if got.cost is None else str(got.cost)) == sc["expected"]["adjustment_cost"]
    assert got.approach == sc["expected"]["adjustment_approach"]


def _hand_costs(sc: dict) -> dict[str, D]:
    """The generator's own Compare cost per built approach (``expected.compare_cost``, hand path), A-36 and A-04 left out."""  # noqa: E501
    return {a: D(v["cost"]) for a, v in sc["expected"]["compare_cost"].items() if a not in ("A-36", "A-04")}  # A-04 needs the next expiry chain: the route test covers it  # noqa: E501


def test_core_adj02_cheapest_is_the_generators_pick_and_every_compare_cell_equals_its_hand_cost():
    """The core proof: ADJ-02's Compare cells equal the generator's hand costs, and T-19's cost is the generator's
    cheapest offered approach (A-26 at Rs 30.26 since step 2: the untested short's buy-back, ADR-238 (3); it was A-29 at
    Rs 92.35 when only the original seven were built; the old formula gave Rs 342.00)."""
    sc = s.load("ADJ-02")
    tracked, market, spot = s.inputs(sc)
    cells = {a: c.value for a, c in s.compare_costs(tracked, market, spot).items()}
    assert cells == {"A-36": D("0.00"), **_hand_costs(sc)}
    got = s.cheapest(sc)
    assert (got.approach, str(got.cost)) == (sc["expected"]["adjustment_approach"], sc["expected"]["adjustment_cost"])
    assert (got.approach, got.cost) == ("A-26", min(_hand_costs(sc).values()))


def test_all_priced_names_the_cheapest():
    sc, cols, market = _columns("ADJ-02")
    hand = _hand_costs(sc)
    assert set(cols) == set(hand) and len(cols) == 9  # A-01 A-05 A-29 A-28 A-11 A-31 A-26 A-02 A-06
    want = cmp.Cheapest(sc["expected"]["adjustment_approach"], D(sc["expected"]["adjustment_cost"]))
    assert cheapest_approach(offered_approaches(s.body_of(sc)), cols, market.chain) == want


def test_some_unpriceable_takes_the_cheapest_of_the_priced():
    sc, cols, market = _columns("ADJ-02")
    hand = _hand_costs(sc)
    first = sc["expected"]["adjustment_approach"]  # A-26: its charges unknown -> "-" -> left out, and counted
    no_charges = dataclasses.replace(cols[first], charges_known=False)
    order = offered_approaches(s.body_of(sc))
    rest = {a: c for a, c in hand.items() if a != first and a in order}
    nxt = next(a for a in order if a in rest and rest[a] == min(rest.values()))  # playbook order on a tie
    got = cheapest_approach(order, {**cols, first: no_charges}, market.chain)
    assert got == cmp.Cheapest(nxt, rest[nxt], None, 1)
    line = str(check.condition_line_t19("Premium left", "0.5000", "1.0000", got.approach, got.cost, got.unpriced))
    assert line.startswith("Premium left: 0.5000 (rule 1.0000); cheapest adjustment we could price: ")
    assert f"cost ₹{rest[nxt]}. 1 could not be priced." in line
    a29 = cols["A-29"]
    no_whole = dataclasses.replace(a29, whole=None)
    assert cheapest_approach(("A-29", "A-31"), {**cols, "A-29": no_whole}, market.chain) ==         cmp.Cheapest("A-31", hand["A-31"], None, 1)  # noqa: E501
    no_quote = tuple(dataclasses.replace(r, bid=None) if r.tradingsymbol == a29.built.trades[0].tradingsymbol else r
                     for r in market.chain)
    assert cheapest_approach(("A-29", "A-01"), cols, no_quote) == cmp.Cheapest("A-01", hand["A-01"], None, 1)


def test_none_priceable_is_not_checked_with_the_reason():
    """ADJ-14 without A-26 (ADR-238: A-26 buys back the decayed untested short, the one contract with a bid): every
    other offered approach trades a contract with bid 0, so none is priced."""
    sc = s.load("ADJ-14")
    body = s.body_of(sc)
    tracked, market, spot = s.inputs(sc)
    unpriced = {a for a, c in s.compare_costs(tracked, market, spot).items() if c.value is None}
    # keep only the approaches that price to nothing: A-26 (the one decayed untested short with a bid), A-02, A-27 and
    # every other priced approach are the ones the playbook offers that DO price (ADR-238 / ADR-239)
    body["approaches"]["applicable"] = [a for a in body["approaches"]["applicable"] if a in unpriced or a == "A-36"]
    assert unpriced and "A-26" not in body["approaches"]["applicable"]
    got = check.cheapest_offered(body, tracked, market, spot, s.RATES, s.PREFS.approach)
    assert (got.approach, got.cost, got.reason) == (None, None, cmp.NO_APPROACH_PRICED) and got.unpriced > 0
    ev = pe.evaluate(s.body_of(sc), pe.StrategyState("weekly", days_left=1, hhmm="15:00", spot=D("23020"),
                                                       premium_left=D("110.50"), adjustment_cost_reason=got.reason,
                                                       prices_fresh=True), gap_until=s.PREFS.gap_until)
    t19 = next(r for r in ev.results if r.trigger_id == "T-19")
    assert isinstance(t19, pe.NotChecked) and t19.code == cmp.NO_APPROACH_PRICED
    assert pe.reason_text(t19.code).startswith("No adjustment this playbook lists can be priced now")


def test_no_approach_offered_is_not_checked_with_the_reason():
    sc, cols, market = _columns("ADJ-02")
    body = s.body_of(sc)
    body["approaches"]["applicable"] = ["A-36"]  # only "No change": nothing to price
    assert offered_approaches(body) == ()
    assert cheapest_approach((), cols, market.chain) == cmp.Cheapest(None, None, cmp.NO_APPROACH_OFFERED)
    tracked, market, spot = s.inputs(sc)
    got = check.cheapest_offered(body, tracked, market, spot, s.RATES, s.PREFS.approach)
    assert got.reason == cmp.NO_APPROACH_OFFERED
    # wording per the #629 decisions (commit 9ab9aabf)
    assert pe.reason_text(got.reason).startswith("This playbook lists no adjustment we can price")


def test_a_tie_keeps_the_first_in_playbook_order():
    _, cols, market = _columns("ADJ-02")
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
    assert str(line) == ("Premium still left is below this x the adjustment cost: 0.3629 (rule 1.0000); cheapest "
                         "adjustment we could price: Close the tested spread, cost \u20b953.73")
    fallback = check.condition_line_t19("Premium still left", "0.3629", "1.0000", "A-99", D("53.73"))
    assert "53.73" not in str(fallback)  # an approach the slot refuses -> the plain line, never a guessed name


def test_the_old_per_leg_cost_is_gone_everywhere():
    assert not hasattr(adjust_money, "adjustment_cost")
    assert not hasattr(check, "COST_PER_LEG")
    conv = json.loads((s.FIX / "_playbooks.json").read_text(encoding="utf-8"))["conventions"]["adjustment_cost"]
    assert "40" not in conv and "ADR-221" in conv


def test_s11_at_the_limit_only_exit_and_reduce_are_priced():
    """Review MINOR 3: at the adjustment limit (S-11) the T-19 pick reads only exit and reduce approaches, even when a
    roll would be cheaper; below the limit the roll is picked."""
    sc, cols, market = _columns("ADJ-02")
    body = s.body_of(sc)
    a01 = cols["A-01"]
    cheap_roll = dataclasses.replace(a01, whole=dataclasses.replace(a01.whole, adjustment_charges=D(0)))
    tilted = {**cols, "A-01": cheap_roll}
    pool = tuple(a for a in offered_now(body, 1) if a != "A-26")  # A-26 (Rs 30.26) is an exit: it would win anyway
    below = cheapest_approach(pool, tilted, market.chain)
    assert below.approach == "A-01" and below.cost < D("92.35")
    at = offered_now(body, body["guards"]["max_adjustments"])
    assert "A-01" not in at and set(at) <= EXIT_REDUCE and "A-26" in at
    assert cheapest_approach(at, tilted, market.chain) == cmp.Cheapest("A-26", _hand_costs(sc)["A-26"])
    assert offered_now(body, None) == offered_approaches(body)  # an unread count filters nothing (T-18 says why)


def test_s11_generator_case_adj45_picks_an_exit_or_reduce_approach():
    sc = s.load("ADJ-45")
    assert "S-11" in sc["expected"]["situations"]
    got = s.cheapest(sc)
    assert got.approach in EXIT_REDUCE and str(got.cost) == sc["expected"]["adjustment_cost"]
