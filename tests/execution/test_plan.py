"""REQ-056 AC-2 (execution plan with leg dependencies and an order sequence) and AC-3 (protective legs before the sells
that depend on them; 'all buys first' never hard-coded). W-022.

Expected values come from the spec, not from running the builder: the strategy is the golden Iron Condor of
scenario-calculations.md §6 on the real instrument-list contracts (partial_inputs.py); the order is ADR-017 Q26's
"Step 1 - Establish protection (both bought wings) · Step 2 - Establish short positions (both sold legs)"; the other
cases are hand-built so that which bought leg caps which sold leg's risk can be read off the strikes.
"""
from __future__ import annotations

import dataclasses
import datetime
import time
from decimal import Decimal as D

import pytest
from partial_inputs import CONTRACTS, LOT, REFS, plan
from plan_inputs import BUY, CE, EXP, FUT, NEXT, PE, PREV, SELL, FakeConstraints, FakeMargin, leg, mk

from ofo.execution.planned import MAX_PLAN_LEGS, ExecutionPlan, PlannedLeg
from ofo.execution.sequence import OrderSequence, PlanStep, StepKind, Undetermined, Unprotected, sequence_plan

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
    """AC-3: the golden condor plus an unrelated BUY 23,600 CE expiring the week BEFORE (it cannot protect a later
    sale), listed first: the condor's wings then sells come first, the unrelated buy last, so a sell precedes a buy."""
    legs = (leg(BUY, CE, "23600", expiry=PREV),) + tuple(p.leg for p in plan().legs)
    seq = sequence_plan(mk(*legs))
    assert seq.sequence == ("L2", "L5", "L3", "L4", "L1")
    actions = [dict((f"L{i + 1}", lg.action) for i, lg in enumerate(legs))[r] for r in seq.sequence]
    assert actions == [BUY, BUY, SELL, SELL, BUY]


def test_ac3_covered_call_entered_sell_first_places_the_future_first_and_its_failure_withholds_the_call() -> None:
    """AC-3: SELL 23,400 CE entered before BUY future (covered call). REQ-059: "closing the long future of a covered
    call -> UNLIMITED", so the future protects the call: future first, a failed future withholds the call, not naked."""
    seq = sequence_plan(mk(leg(SELL, CE, "23400"), leg(BUY, FUT, None, price="23100.00")))
    assert seq.dependencies == (("L1", ("L2",)),)
    assert seq.sequence == ("L2", "L1")
    assert seq.simulate({"L2"}).withheld == ("L1",)
    assert seq.unprotected == () and seq.undetermined == ()


def test_ac3_covered_put_short_future_protects_the_short_put() -> None:
    """AC-3: SELL 23,000 PE + SELL future (covered put): the short future gains as the level falls, where the put
    loses, so it is the put's protector and goes first."""
    seq = sequence_plan(mk(leg(SELL, PE, "23000"), leg(SELL, FUT, None, price="23100.00")))
    assert seq.dependencies == (("L1", ("L2",)),)
    assert seq.sequence == ("L2", "L1")
    assert seq.unprotected == ()


def test_ac3_long_future_never_protects_a_short_put_and_a_short_future_never_a_short_call() -> None:
    """AC-3 (red case): the wrong-direction future caps nothing: SELL PE + BUY future and SELL CE + SELL future have no
    dependency, and each sold option is flagged naked."""
    for sold, fut in ((leg(SELL, PE, "23000"), leg(BUY, FUT, None, price="23100.00")),
                      (leg(SELL, CE, "23400"), leg(SELL, FUT, None, price="23100.00"))):
        seq = sequence_plan(mk(sold, fut))
        assert seq.dependencies == ()
        assert seq.unprotected == (Unprotected(("L1",), 65),)


def test_ac3_future_expiring_before_the_option_does_not_protect_it() -> None:
    """AC-3 (orchestrator default: future expiry on or after the option's): a future expiring the week before the
    sold call leaves it naked after that date, so no dependency."""
    seq = sequence_plan(mk(leg(SELL, CE, "23400"), leg(BUY, FUT, None, expiry=PREV, price="23100.00")))
    assert seq.dependencies == ()


def test_ac3_calendar_later_long_protects_the_near_short() -> None:
    """AC-3: calendar SELL 23,400 CE (06 Oct) + BUY 23,400 CE (13 Oct), sell entered first. Mirrors W-014 rule 5d
    (closing only the sold options of a multi-expiry strategy is open to all; the long is the protection): the far
    long goes first and its failure withholds the near short."""
    seq = sequence_plan(mk(leg(SELL, CE, "23400"), leg(BUY, CE, "23400", expiry=NEXT)))
    assert seq.dependencies == (("L1", ("L2",)),)
    assert seq.sequence == ("L2", "L1")
    assert seq.simulate({"L2"}).withheld == ("L1",)


def test_ac3_diagonal_later_long_other_strike_protects_and_earlier_long_does_not() -> None:
    """AC-3: diagonal SELL 23,000 PE (06 Oct) + BUY 22,800 PE (13 Oct) -> protected; the reverse (long expiring
    first) leaves the short naked after the near expiry -> no dependency, flagged naked."""
    seq = sequence_plan(mk(leg(SELL, PE, "23000"), leg(BUY, PE, "22800", expiry=NEXT)))
    assert seq.dependencies == (("L1", ("L2",)),)
    rev = sequence_plan(mk(leg(SELL, PE, "23000", expiry=NEXT), leg(BUY, PE, "22800")))
    assert rev.dependencies == ()
    assert rev.unprotected == (Unprotected(("L1",), 65),)


def test_ac3_genuinely_naked_short_is_still_flagged() -> None:
    """AC-3 (red case): a short strangle has no protector at all: both sold legs flagged naked in full."""
    seq = sequence_plan(mk(leg(SELL, PE, "22800"), leg(SELL, CE, "23600")))
    assert seq.dependencies == ()
    assert seq.unprotected == (Unprotected(("L1",), 65), Unprotected(("L2",), 65))


def test_ac2_protective_put_on_a_future_is_undetermined() -> None:
    """AC-2: BUY future + BUY 23,000 PE: the spec defines no protection OF a futures leg; the future is listed as
    undetermined (it protects nothing here) and the order is the user's."""
    seq = sequence_plan(mk(leg(BUY, FUT, None, price="23100.00"), leg(BUY, PE, "23000")))
    assert seq.dependencies == ()
    assert seq.undetermined == (Undetermined("L1", seq.undetermined[0].reason),)
    assert seq.sequence == ("L1", "L2")


def test_ac2_margin_impact_breaks_ties_within_a_step_lower_impact_first() -> None:
    """AC-2: three unrelated legs (no dependency: the bought call expires before the sold call). The fake planner charges 100,000 + a fixed amount per leg: +500 for
    L1, -100 for L2 (reduces margin), +200 for L3. Impact = margin with - without the leg = that amount, so the order
    is L2 (-100), L3 (+200), L1 (+500), and the basis says it is unverified against Zerodha."""
    legs = (leg(SELL, PE, "22800"), leg(BUY, CE, "23600", expiry=PREV), leg(SELL, CE, "24000", expiry=NEXT))
    planner = FakeMargin({legs[0]: D("500"), legs[1]: D("-100"), legs[2]: D("200")})
    seq = sequence_plan(mk(*legs), planner)
    assert seq.sequence == ("L2", "L3", "L1")
    assert seq.margin_used is True
    assert "unverified against real Zerodha margin behaviour (ADR-017 Q26)" in seq.margin_note
    assert len(planner.asked) == 4  # the whole strategy once, then once without each leg
    assert sequence_plan(mk(*legs)).sequence == ("L1", "L2", "L3")  # no planner: the user's order


def test_ac2_failing_planner_falls_back_to_protection_order_and_says_so() -> None:
    """AC-2 (red case): a planner that raises -> the user's order within each step, margin_used False, and the note
    reads "margin impact unknown — not used"."""
    legs = (leg(SELL, PE, "22800"), leg(BUY, CE, "23600", expiry=PREV), leg(SELL, CE, "24000", expiry=NEXT))
    seq = sequence_plan(mk(*legs), FakeMargin({}, fail=True))
    assert seq.sequence == ("L1", "L2", "L3")
    assert seq.margin_used is False
    assert seq.margin_note.startswith("margin impact unknown — not used")


def test_ac2_freeze_limit_splits_legs_and_every_protective_slice_precedes_any_dependent_slice() -> None:
    """AC-2: golden condor at 3 lots (195 units), fake freeze 130 units, 3 orders per batch. Each leg -> 130 + 65.
    Step 1: 4 slices (batches 1, 1, 1, 2); step 2 starts a new batch: 4 slices (batches 3, 3, 3, 4)."""
    p = ExecutionPlan("S-1", tuple(PlannedLeg(x.leg_ref, x.contract, dataclasses.replace(x.leg, quantity=3 * LOT))
                                   for x in plan().legs))
    seq = sequence_plan(p, constraints=FakeConstraints(freeze=130, per_batch=3))
    assert [(o.step, o.batch, o.leg_ref, o.slice_no, o.quantity) for o in seq.orders] == [
        (1, 1, BUY_PE, 1, 130), (1, 1, BUY_PE, 2, 65), (1, 1, BUY_CE, 1, 130), (1, 2, BUY_CE, 2, 65),
        (2, 3, SELL_PE, 1, 130), (2, 3, SELL_PE, 2, 65), (2, 3, SELL_CE, 1, 130), (2, 4, SELL_CE, 2, 65),
    ]
    assert sum(o.quantity for o in seq.orders if o.leg_ref == SELL_CE) == 195
    unsplit = sequence_plan(p, constraints=FakeConstraints(freeze=1755, per_batch=10))
    assert [o.quantity for o in unsplit.orders] == [195, 195, 195, 195]


@pytest.mark.parametrize("freeze,per_batch", [(0, 3), (130, 0), (130, 101), (1, 3), (True, 3)])
def test_ac2_invalid_broker_constraints_are_refused(freeze: object, per_batch: object) -> None:
    """AC-2 (input domain): zero/boolean freeze, zero or absurd batch size, or a split into more than 50 orders
    (65 units at a freeze of 1) is refused, never silently built."""
    with pytest.raises(ValueError):
        sequence_plan(plan(), constraints=FakeConstraints(freeze=freeze, per_batch=per_batch))


def test_ac2_default_constraints_are_labelled_unverified() -> None:
    """AC-2: the default broker constraints are a labelled placeholder (AC-10 verifies the real values)."""
    from ofo.execution.sequence import DEFAULT_FREEZE_UNITS, UnverifiedDefaultConstraints

    assert UnverifiedDefaultConstraints.unverified is True
    assert UnverifiedDefaultConstraints().freeze_quantity("NIFTY26OCT23000PE") == DEFAULT_FREEZE_UNITS == 27 * 65


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


def test_ac3_complete_strategy_orders_missing_legs_by_the_plan_not_buys_first(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-3: W-023's Complete now follows this plan. BUY 22,800 PE (filled) · SELL 23,000 PE · BUY 23,600 CE (both
    rejected). The sold put depends on the filled put wing (step 2); the bought call protects nothing (step 3). So
    Complete prepares SELL 23,000 PE then BUY 23,600 CE; a buys-first sort would reverse them."""
    from partial_inputs import (BROKER_IDS, FILL_AT, REJECT_TEXT, STRATEGY_ID, FakeBroker, FakePlanner,
                                entry_context, new_book)

    from ofo.execution.partial import BrokerOrderStatus, BrokerPositionLine, complete_strategy
    from ofo.orders import FillEvent, Order, OrderState

    full = plan().legs
    three = ExecutionPlan(STRATEGY_ID, (full[0], full[1], full[3]))
    assert sequence_plan(three).sequence == (BUY_PE, SELL_PE, BUY_CE)
    book = new_book()
    ids = (BROKER_IDS[0], BROKER_IDS[1], BROKER_IDS[3])
    for p, bid in zip(three.legs, ids):
        book.add(Order(STRATEGY_ID, p.leg_ref, p.contract, p.leg.action, p.leg.quantity, p.leg.entry_price,
                       broker_order_id=bid))
        book.transition(bid, OrderState.SUBMITTED)
    book.apply_fill(FillEvent("T-1", ids[0], full[0].contract, BUY, LOT, D("42.50"), FILL_AT))
    book.transition(ids[1], OrderState.REJECTED)
    book.transition(ids[2], OrderState.REJECTED)
    broker = FakeBroker(
        [BrokerPositionLine(full[0].contract, LOT, D("42.50"), None)],
        [BrokerOrderStatus(ids[0], full[0].contract, OrderState.EXECUTED, LOT),
         BrokerOrderStatus(ids[1], full[1].contract, OrderState.REJECTED, 0, REJECT_TEXT),
         BrokerOrderStatus(ids[2], full[3].contract, OrderState.REJECTED, 0, REJECT_TEXT)])
    prep = complete_strategy(three, broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert [(o.contract, o.side, o.quantity) for o in prep.orders] == [
        ("NIFTY26OCT23000PE", SELL, LOT), ("NIFTY26OCT23600CE", BUY, LOT)]
