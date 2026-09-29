"""REQ-056 AC-2 (execution plan with leg dependencies and an order sequence) and AC-3 (protective legs before the sells
that depend on them; 'all buys first' never hard-coded). W-022.

Expected values come from the spec, not from running the builder: the strategy is the golden Iron Condor of
scenario-calculations.md §6 on the real instrument-list contracts (partial_inputs.py); the order is ADR-017 Q26's
"Step 1 - Establish protection (both bought wings) · Step 2 - Establish short positions (both sold legs)"; the other
cases are hand-built so that which bought leg caps which sold leg's risk can be read off the strikes.
"""
from __future__ import annotations

import datetime
import time
from decimal import Decimal as D

import pytest
from partial_inputs import CONTRACTS, LOT, REFS, plan

from ofo.engine import Action, Instrument, Leg
from ofo.execution.planned import MAX_PLAN_LEGS, ExecutionPlan, PlannedLeg
from ofo.execution.sequence import OrderSequence, PlanStep, StepKind, Undetermined, Unprotected, sequence_plan

EXP = datetime.date(2026, 10, 6)
NEXT = datetime.date(2026, 10, 13)
BUY, SELL = Action.BUY, Action.SELL
CE, PE, FUT = Instrument.CE, Instrument.PE, Instrument.FUT


def leg(action: Action, kind: Instrument, strike: str | None, qty: int = LOT, expiry: datetime.date = EXP,
        price: str = "50.00") -> Leg:
    return Leg(action, kind, D(strike) if strike else None, expiry, qty, D(price))


def mk(*legs: Leg) -> ExecutionPlan:
    return ExecutionPlan("S-9", tuple(PlannedLeg(f"L{i + 1}", f"C{i + 1}", lg) for i, lg in enumerate(legs)))


# leg-1 BUY 22,800 PE · leg-2 SELL 23,000 PE · leg-3 SELL 23,400 CE · leg-4 BUY 23,600 CE (§6)
BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS


def test_core_golden_condor_wing_before_its_sell_and_a_put_wing_failure_stops_only_the_put_sale() -> None:
    """AC-2: the golden Iron Condor's plan has each bought wing before the sold leg it protects; a failure of the
    22,800 PE purchase stops the 23,000 PE sale while the call side (23,600 CE buy, 23,400 CE sell) proceeds."""
    assert CONTRACTS == ("NIFTY26OCT22800PE", "NIFTY26OCT23000PE", "NIFTY26OCT23400CE", "NIFTY26OCT23600CE")
    seq = sequence_plan(plan())
    assert seq.dependencies == ((SELL_PE, (BUY_PE,)), (SELL_CE, (BUY_CE,)))
    assert seq.steps == (PlanStep(StepKind.PROTECTION, (BUY_PE, BUY_CE)),
                         PlanStep(StepKind.SHORT_POSITIONS, (SELL_PE, SELL_CE)))
    assert seq.sequence == (BUY_PE, BUY_CE, SELL_PE, SELL_CE)
    assert StepKind.PROTECTION.value == "Establish protection"  # ADR-017 Q26 wording
    assert StepKind.SHORT_POSITIONS.value == "Establish short positions"
    sim = seq.simulate({BUY_PE})
    assert sim.sent == (BUY_PE, BUY_CE, SELL_CE)
    assert sim.failed == (BUY_PE,)
    assert sim.withheld == (SELL_PE,)
    assert seq.undetermined == () and seq.unprotected == ()


def test_ac2_ratio_spread_one_buy_two_sells_both_after_the_buy_and_the_naked_units_named() -> None:
    """AC-2: call ratio spread, BUY 1 lot 23,000 CE vs SELL 2 lots 23,200 CE (one leg): the sell depends on the buy and
    goes after it; 1 lot (65 units) has no protector and is listed as unprotected; buy fails -> sell withheld whole."""
    seq = sequence_plan(mk(leg(BUY, CE, "23000"), leg(SELL, CE, "23200", qty=2 * LOT)))
    assert seq.dependencies == (("L2", ("L1",)),)
    assert seq.sequence == ("L1", "L2")
    assert seq.unprotected == (Unprotected(("L2",), 65),)
    assert seq.simulate({"L1"}).withheld == ("L2",)


def test_ac2_ratio_as_two_sold_legs_both_depend_on_the_one_buy() -> None:
    """AC-2: BUY 1 lot 23,000 CE, SELL 1 lot 23,200 CE, SELL 1 lot 23,400 CE: units are fungible, so neither sell is
    singled out as the naked one; both go after the buy, 65 units unprotected across both, both withheld if it fails."""
    seq = sequence_plan(mk(leg(SELL, CE, "23200"), leg(BUY, CE, "23000"), leg(SELL, CE, "23400")))
    assert seq.dependencies == (("L1", ("L2",)), ("L3", ("L2",)))
    assert seq.sequence == ("L2", "L1", "L3")
    assert seq.unprotected == (Unprotected(("L1", "L3"), 65),)
    sim = seq.simulate({"L2"})
    assert sim.sent == ("L2",) and sim.withheld == ("L1", "L3")


def test_ac2_bull_call_spread_bought_call_below_the_sold_call_still_protects_it() -> None:
    """AC-2: BUY 23,000 CE + SELL 23,200 CE: max loss is the debit, so the bought call caps the sold call's risk even
    though its strike is below; the sell depends on it and is placed after it although the user listed it first."""
    seq = sequence_plan(mk(leg(SELL, CE, "23200"), leg(BUY, CE, "23000")))
    assert seq.dependencies == (("L1", ("L2",)),)
    assert seq.sequence == ("L2", "L1")


def test_ac2_option_type_decides_dependency_a_bought_call_never_protects_a_sold_put() -> None:
    """AC-2: SELL 23,000 PE + BUY 23,600 CE, same expiry (a risk reversal): a call caps no put risk, so no dependency,
    the user's order is kept and the put is listed as naked."""
    seq = sequence_plan(mk(leg(SELL, PE, "23000"), leg(BUY, CE, "23600")))
    assert seq.dependencies == ()
    assert seq.steps == (PlanStep(StepKind.OTHER, ("L1", "L2")),)
    assert seq.unprotected == (Unprotected(("L1",), 65),)


def test_ac3_no_dependency_keeps_the_users_order_so_a_sell_can_precede_a_buy() -> None:
    """AC-3: a short put plus an unrelated long call on another expiry: nothing depends on anything, so the sell stays
    first. 'All buys first' would put the call first."""
    seq = sequence_plan(mk(leg(SELL, PE, "23000"), leg(BUY, CE, "23600", expiry=NEXT)))
    assert seq.sequence == ("L1", "L2")
    assert seq.dependencies == ()


def test_ac3_long_straddle_has_no_dependency_and_one_step_in_user_order() -> None:
    """AC-3: a long straddle (BUY 23,200 CE, BUY 23,200 PE) has nothing to protect: one step, the user's order."""
    seq = sequence_plan(mk(leg(BUY, PE, "23200"), leg(BUY, CE, "23200")))
    assert seq.steps == (PlanStep(StepKind.OTHER, ("L1", "L2")),)
    assert seq.unprotected == ()


def test_ac3_unrelated_bought_leg_goes_after_the_protected_structure_not_to_the_front() -> None:
    """AC-3: the golden condor plus an unrelated BUY 23,600 CE on the next expiry, listed first: the condor's wings then
    sells come first, the unrelated buy last, so a sell precedes a buy in the sequence."""
    legs = (leg(BUY, CE, "23600", expiry=NEXT),) + tuple(p.leg for p in plan().legs)
    seq = sequence_plan(mk(*legs))
    assert seq.sequence == ("L2", "L5", "L3", "L4", "L1")
    actions = [dict((f"L{i + 1}", lg.action) for i, lg in enumerate(legs))[r] for r in seq.sequence]
    assert actions == [BUY, BUY, SELL, SELL, BUY]


def test_ac2_covered_call_future_protection_is_undetermined_not_invented() -> None:
    """AC-2: BUY future + SELL 23,400 CE (covered call): the spec defines no protection by a futures leg, so there is
    no dependency, both legs are listed as undetermined with the reason, and the user's order is kept."""
    seq = sequence_plan(mk(leg(SELL, CE, "23400"), leg(BUY, FUT, None, price="23100.00")))
    assert seq.dependencies == ()
    assert seq.sequence == ("L1", "L2")
    assert [u.leg_ref for u in seq.undetermined] == ["L1", "L2"]
    assert "futures leg" in seq.undetermined[0].reason and "futures leg" in seq.undetermined[1].reason


def test_ac2_calendar_protection_across_expiries_is_undetermined() -> None:
    """AC-2: SELL 23,400 CE (06 Oct) + BUY 23,400 CE (13 Oct): no cross-expiry protection rule in the spec, so no
    dependency and the sell is listed as undetermined."""
    seq = sequence_plan(mk(leg(SELL, CE, "23400"), leg(BUY, CE, "23400", expiry=NEXT)))
    assert seq.dependencies == ()
    assert seq.undetermined == (Undetermined("L1", seq.undetermined[0].reason),)
    assert "another expiry" in seq.undetermined[0].reason


def test_ac2_margin_impact_basis_is_stated_not_hidden() -> None:
    """AC-2: per-leg margin impact is not used to reorder legs (ADR-017 Q26: verify Zerodha margin first); the plan
    says so in its ordering basis."""
    assert "not yet verified" in sequence_plan(plan()).ordering_basis


def test_ac2_twenty_legs_plan_fast_and_twenty_one_refused() -> None:
    """AC-2: broker/plan-size constraint: a 20-leg plan (5 condors on different expiries) sequences in well under
    50 ms with each condor's wings first; 21 legs are refused."""
    legs = []
    for week in range(5):
        exp = EXP + datetime.timedelta(days=7 * week)
        legs += [leg(BUY, PE, "22800", expiry=exp), leg(SELL, PE, "23000", expiry=exp),
                 leg(SELL, CE, "23400", expiry=exp), leg(BUY, CE, "23600", expiry=exp)]
    big = mk(*legs)
    start = time.perf_counter()
    seq = sequence_plan(big)
    assert time.perf_counter() - start < 0.05
    assert len(seq.sequence) == MAX_PLAN_LEGS == 20
    assert len(seq.dependencies) == 10
    assert all(lg.action is BUY for lg in (big.by_ref(r).leg for r in seq.steps[0].leg_refs))
    with pytest.raises(ValueError, match="1..20 legs"):
        mk(*legs, leg(BUY, CE, "24000"))


def test_ac2_a_sequence_cannot_be_forged_by_the_caller() -> None:
    """AC-2: the dependency plan is built only by sequence_plan; a hand-built OrderSequence is refused."""
    with pytest.raises(ValueError, match="built by sequence_plan"):
        OrderSequence("S-1", (PlanStep(StepKind.OTHER, REFS),), (), (), (), "mine")
    with pytest.raises(ValueError, match="needs an ExecutionPlan"):
        sequence_plan([p for p in plan().legs])  # type: ignore[arg-type]
