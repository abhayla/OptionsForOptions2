# ruff: noqa: E501 - catalogue texts quoted whole
"""ADR-239 (GC-IC1 step 3, REQ-155 AC-1 / AC-8): the roll approaches A-02, A-04 and A-06 - every answer state of the
brief (next expiry listed with prices / with none / not listed; deltas present / absent; target listed / not; debit
within / over the limit) and the brief's attack list. The equality with the generator's engine-free copy on every
iron condor scenario is ``test_approaches.test_every_scenario_and_approach_equals_the_hand_derived_legs``."""
from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal as D

from ofo.adjustment import liquidity
from ofo.adjustment.approaches import build_approach, planned_price
from test_approaches import CFG, inputs, load

N9, N17 = datetime.date(2026, 11, 9), datetime.date(2026, 11, 17)
OVER = liquidity.Limits(debit_state=liquidity.SET, debit=liquidity.DebitLimit(D("1")))
ROOMY = liquidity.Limits(debit_state=liquidity.SET, debit=liquidity.DebitLimit(D("1000000")))


def adj02():
    return inputs(load("ADJ-02"))  # call side tested: short 23,500 CE, wing 23,700 CE (09 Nov), next expiry 17 Nov


def _ce(after, side):
    return next(x for x in after if x.type == "CE" and x.side == side)


def test_a02_moves_only_the_short_and_keeps_the_wing():
    """Attack 1: the wing stays (else A-02 equals A-05); the spread narrows."""
    position, chain, spot = adj02()
    built = build_approach(position, chain, spot, "A-02", CFG)
    assert built.refusal is None
    assert _ce(built.after, "SELL").strike == D("23600") and _ce(built.after, "BUY").strike == D("23700")
    assert [(t.action, t.strike) for t in built.trades] == [("BUY", D("23500")), ("SELL", D("23600"))]


def test_a02_short_landing_at_its_wing_is_refused_naming_both_strikes():
    """Attack 1 boundary (>= not >): every strike below the wing is over the target delta, so the pick IS the wing."""
    position, chain, spot = adj02()
    hot = [replace(r, delta=D("0.50")) if r.expiry == N9 and r.type == "CE" and D("23500") < r.strike < D("23700")
           else r for r in chain]
    built = build_approach(position, hot, spot, "A-02", CFG)
    assert built.refusal == ("Moving Leg 3 (SELL NIFTY 23,500 CE, expiry 09 Nov 2026) to 23,700 would put it at or "
                             "beyond its wing at 23,700, so the wing would no longer protect it.")
    assert built.trades == ()


def test_a04_prices_the_new_legs_from_the_next_expiry_rows():
    """Attack 2: the new legs are the next expiry's contracts at that expiry's prices, never the current rows'."""
    position, chain, spot = adj02()
    built = build_approach(position, chain, spot, "A-04", CFG)
    assert built.refusal is None
    rows = {(r.expiry, r.type, r.strike): r for r in chain}
    opened = [t for t in built.trades if t.expiry == N17]
    assert {(t.action, t.strike) for t in opened} == {("SELL", D("23800")), ("BUY", D("24000"))}  # width 200 kept
    for t in opened:
        assert t.price == planned_price(rows[(N17, t.type, t.strike)])
        assert t.price != planned_price(rows[(N9, t.type, t.strike)])  # the two expiries really differ here
    assert {x.expiry for x in built.after} == {N9, N17}


def test_a04_next_expiry_listed_with_no_prices_is_refused_naming_it():
    position, chain, spot = adj02()
    dark = [replace(r, ltp=None, bid=None, ask=None) if r.expiry == N17 else r for r in chain]
    built = build_approach(position, dark, spot, "A-04", CFG)
    assert built.refusal == "The 17 Nov 2026 expiry has no prices in the chain read, so this approach is not built."


def test_a04_next_expiry_not_listed_is_refused_naming_the_position_expiry():
    position, chain, spot = adj02()
    built = build_approach(position, [r for r in chain if r.expiry == N9], spot, "A-04", CFG)
    assert built.refusal == "No expiry after 09 Nov 2026 is listed in the chain read, so this approach is not built."


def test_a04_without_deltas_on_the_next_expiry_moves_the_points_fallback():
    """Deltas absent on the next expiry (present on the current one): the points fallback, labelled."""
    position, chain, spot = adj02()
    flat = [replace(r, delta=None) if r.expiry == N17 else r for r in chain]
    built = build_approach(position, flat, spot, "A-04", CFG)
    assert (built.step_basis, built.step_value) == ("points", D("200"))
    assert {(t.action, t.strike) for t in built.trades if t.expiry == N17} == {("SELL", D("23700")), ("BUY", D("23900"))}


def test_a04_target_not_listed_on_the_next_expiry_is_the_landing_refusal():
    position, chain, spot = adj02()
    gone = [replace(r, listed=False) if (r.expiry, r.type, r.strike) == (N17, "CE", D("24000")) else r for r in chain]
    built = build_approach(position, gone, spot, "A-04", CFG)
    assert built.refusal == "No 24,000 CE is listed for 17 Nov 2026, so leg 4 cannot move there."


def test_a06_steps_the_listing_over_a_gap_never_arithmetic():
    """Attack 3: N = 2 with 23,550 CE not listed lands on 23,650 (the second LISTED strike), not 23,600."""
    position, chain, spot = adj02()
    gap = [r for r in chain if (r.expiry, r.type, r.strike) != (N9, "CE", D("23550"))]
    built = build_approach(position, gap, spot, "A-06", replace(CFG, shift_strikes=2))
    assert built.refusal is None
    assert _ce(built.after, "SELL").strike == D("23650") and _ce(built.after, "BUY").strike == D("23800")


def test_a06_one_step_keeps_the_width_and_moves_away_from_spot():
    position, chain, spot = adj02()
    built = build_approach(position, chain, spot, "A-06", CFG)
    assert _ce(built.after, "SELL").strike == D("23550") and _ce(built.after, "BUY").strike == D("23750")


def test_a06_past_the_last_listed_strike_is_the_step_rules_refusal():
    position, chain, spot = adj02()
    built = build_approach(position, chain, spot, "A-06", replace(CFG, shift_strikes=200))
    assert built.refusal is not None and built.refusal.endswith("has no further listed strike in that direction.")


def test_every_roll_over_the_debit_limit_is_refused_and_within_it_builds():
    """Attack 4 (ADR-230): each new roll passes the roll debit guard."""
    position, chain, spot = adj02()
    for a in ("A-02", "A-04", "A-06"):
        refused = build_approach(position, chain, spot, a, CFG, limits=OVER)
        assert refused.refusal is not None and refused.refusal.startswith("This roll costs "), a
        assert refused.refusal.endswith("more than the ₹1 your playbook allows for one roll."), a
        assert build_approach(position, chain, spot, a, CFG, limits=ROOMY).refusal is None, a
