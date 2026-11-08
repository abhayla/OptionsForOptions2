
"""#633 (ADR-221, ADR-230 (1)): T-19 builds approaches with the SAME liquidity limits and max profit as the Compare.

Class two-callers-two-answers: ``priced_approach`` has callers (route, T-19 ``cheapest_offered``, tests); before the
fix the route passed ``limits`` / ``max_profit`` and T-19 passed neither. Answer states of the guards: stated (limits
applied), absent / no playbook body (no limits, as the route's ``guards is None``), a failed read (the route's reader
answers None, so no limits; the checker reads the already-resolved body, so a failed resolve is upstream: body None),
max profit unlimited / not priced (None, as the route's ``_before_max_profit``).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t19_support as s
from ofo.adjustment import liquidity
from ofo.adjustment.compare import Column, MarginRead, cheapest_approach
from ofo.adjustment.offered import offered_now
from ofo_app import adjustment_check as check
from ofo_app.routes import adjustment as route

pytestmark = pytest.mark.repo_scan


def _route_cheapest(sc: dict, guards: dict | None):
    """The Compare route's inputs by hand (guards -> limits, the Before's max profit), then the cheapest of the
    approaches the route did not refuse."""
    tracked, market, spot = s.inputs(sc)
    tracked = route.as_of_market(tracked, market)
    before = route.price_after(tracked.position.legs, tracked.position, tracked.booked, tracked.paid_charges, (),
                               s.RATES, market)
    limits = None if guards is None else liquidity.limits_from_guards(guards)
    offered = offered_now(s.body_of(sc), tracked.adjustments_used)
    cols = {}
    for a in offered:
        built, priced = route.priced_approach(a, tracked, market, spot, s.RATES, s.PREFS.approach, roll_basis=s.BASIS,
                                              limits=limits,
                                              max_profit=route._before_max_profit(before))
        if built is not None and priced is not None:
            cols[a] = Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None))
    return cheapest_approach(offered, cols, market.chain), cols


def test_adj50_t19_names_the_cheapest_approach_the_compare_does_not_refuse():
    sc = s.load("ADJ-50")
    want, _ = _route_cheapest(sc, s.body_of(sc)["guards"])
    got = s.cheapest(sc)
    assert (got.approach, got.cost) == (want.approach, want.cost)


def test_adj50_limits_refuse_an_approach_so_the_comparison_can_discriminate():
    sc = s.load("ADJ-50")
    _, with_limits = _route_cheapest(sc, s.body_of(sc)["guards"])
    _, without = _route_cheapest(sc, None)
    assert set(without) - set(with_limits), "ADJ-50 limits refuse nothing: the test cannot discriminate"


def test_a_roll_the_compare_refuses_is_not_named_by_t19():
    """Where the limits DO change the answer: the playbook offers only A-05, the roll ADJ-50's debit limit refuses.
    The Compare prices nothing; T-19 must not quote a cost for it (before the fix it named A-05)."""
    sc = s.load("ADJ-50")
    body = s.body_of(sc)
    body["approaches"]["applicable"] = ["A-05"]
    tracked, market, spot = s.inputs(sc)
    tracked2 = route.as_of_market(tracked, market)
    before = route.price_after(tracked2.position.legs, tracked2.position, tracked2.booked, tracked2.paid_charges, (),
                               s.RATES, market)
    built, priced = route.priced_approach("A-05", tracked2, market, spot, s.RATES, s.PREFS.approach, roll_basis=s.BASIS,
                                          limits=liquidity.limits_from_guards(body["guards"]),
                                          max_profit=route._before_max_profit(before))
    assert built.refusal is not None and priced is None  # the Compare refuses it
    got = check.cheapest_offered(body, tracked, market, spot, s.RATES, s.PREFS.approach, roll_basis=s.BASIS)
    assert (got.approach, got.cost) == (None, None)


def test_no_body_offers_nothing_and_applies_no_limits():
    sc = s.load("ADJ-50")
    tracked, market, spot = s.inputs(sc)
    assert check.cheapest_offered(None, tracked, market, spot, s.RATES, s.PREFS.approach,
                                  roll_basis=s.BASIS).approach is None


def test_body_without_guards_applies_no_limits_as_the_route_with_no_guards():
    sc = s.load("ADJ-50")
    body = {**s.body_of(sc), "guards": {}}
    tracked, market, spot = s.inputs(sc)
    want, _ = _route_cheapest(sc, {})
    got = check.cheapest_offered(body, tracked, market, spot, s.RATES, s.PREFS.approach, roll_basis=s.BASIS)
    assert (got.approach, got.cost) == (want.approach, want.cost)
    assert (got.approach, str(got.cost)) == ("A-29", "73.24")  # the expected value of the no-limits build


def test_unreadable_guard_value_is_fail_closed_like_the_route():
    """An unreadable limit (not a number) is the route's UNREADABLE state: T-19 follows it through the same helper."""
    sc = s.load("ADJ-50")
    guards = {**s.body_of(sc)["guards"], "roll_debit_limit": "garbage"}
    want, _ = _route_cheapest(sc, guards)
    tracked, market, spot = s.inputs(sc)
    got = check.cheapest_offered({**s.body_of(sc), "guards": guards}, tracked, market, spot, s.RATES, s.PREFS.approach,
                                 roll_basis=s.BASIS)
    assert (got.approach, got.cost) == (want.approach, want.cost)
