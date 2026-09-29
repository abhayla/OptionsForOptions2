"""REQ-056 AC-5: the execution review shows strategy, margin, max loss, max profit, current P&L, leg count, execution
sequence and broker; unknown is unknown, never 0. W-022.

Expected numbers are the golden Iron Condor of scenario-calculations.md §6 (quantity 75, entries 42.50 / 86.00 /
91.50 / 44.00, LTPs 38.20 / 72.50 / 78.00 / 39.50): max profit ₹6,825, max loss ₹8,175, live P&L +₹1,365.00. The
one-lot (65) figures are hand-computed from the same per-unit values: 91 x 65 = 5,915; 109 x 65 = 7,085;
(-4.30 + 13.50 + 13.50 - 4.50) x 65 = 18.20 x 65 = 1,183.00.
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from partial_inputs import CONTRACTS, LOT, REFS
from plan_inputs import BUY, CE, FUT, NEXT, PE, SELL, FakeMargin, leg, mk

from ofo.engine import UNLIMITED, Strategy
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.review import ReviewLine, execution_review

PRICES = (("BUY", PE, "22800", "42.50", "38.20"), ("SELL", PE, "23000", "86.00", "72.50"),
          ("SELL", CE, "23400", "91.50", "78.00"), ("BUY", CE, "23600", "44.00", "39.50"))


def golden(qty: int, with_ltp: bool = True) -> ExecutionPlan:
    legs = [leg(BUY if a == "BUY" else SELL, kind, strike, qty=qty, price=entry, ltp=ltp if with_ltp else None)
            for a, kind, strike, entry, ltp in PRICES]
    return ExecutionPlan("S-1", tuple(PlannedLeg(r, c, lg) for r, c, lg in zip(REFS, CONTRACTS, legs)))


def planner(total: str = "48210.75") -> FakeMargin:
    return FakeMargin({}, base=D(total))


def test_ac5_golden_condor_review_shows_every_field_from_the_engine() -> None:
    """AC-5: §6 golden condor at quantity 75: max profit 6,825, max loss 8,175, current P&L 1,365.00, 4 legs, the
    Q26 two-step sequence, margin from the planner, broker Zerodha, nothing unknown."""
    fake = planner()
    review = execution_review(golden(75), fake)
    assert review.strategy_id == "S-1"
    assert review.max_profit == D("6825")
    assert review.max_loss == D("8175")
    assert review.current_pnl == D("1365.00")
    assert review.margin_required == D("48210.75")
    assert review.leg_count == 4
    assert review.broker == "Zerodha"
    assert review.sequence == (
        ReviewLine(1, "Establish protection", "leg-1", BUY, "NIFTY26OCT22800PE", 75),
        ReviewLine(1, "Establish protection", "leg-4", BUY, "NIFTY26OCT23600CE", 75),
        ReviewLine(2, "Establish short positions", "leg-2", SELL, "NIFTY26OCT23000PE", 75, batch=2),
        ReviewLine(2, "Establish short positions", "leg-3", SELL, "NIFTY26OCT23400CE", 75, batch=2),
    )  # a batch never spans two steps
    assert review.unknown == () and review.notes == ()
    assert "unverified against real Zerodha margin behaviour" in review.margin_basis
    # the review's own figure (whole strategy), then the sequence's base + one without each of the 4 legs
    assert fake.asked[0] == Strategy(tuple(p.leg for p in golden(75).legs)) and len(fake.asked) == 6


def test_ac5_one_real_lot_values_and_decimal_types() -> None:
    """AC-5: one real lot (65): 5,915 / 7,085 / 1,183.00, every money value an exact Decimal (never float)."""
    review = execution_review(golden(LOT), planner())
    assert (review.max_profit, review.max_loss, review.current_pnl) == (D("5915"), D("7085"), D("1183.00"))
    for value in (review.max_profit, review.max_loss, review.current_pnl, review.margin_required):
        assert type(value) is D


def test_ac5_missing_ltp_leaves_current_pnl_unknown_not_zero() -> None:
    """AC-5 (red case): no LTP on the legs -> current P&L is None with a reason, never 0."""
    review = execution_review(golden(LOT, with_ltp=False), planner())
    assert review.current_pnl is None
    assert [f for f, _ in review.unknown] == ["current_pnl"]


class BrokenPlanner:
    def __init__(self, answer: object = None, fail: bool = False) -> None:
        self.answer, self.fail = answer, fail

    def margin_for(self, strategy: Strategy) -> object:
        if self.fail:
            raise ConnectionError("margin service timed out")
        return self.answer


@pytest.mark.parametrize("bad", [BrokenPlanner(fail=True), BrokenPlanner(answer=48210.75),
                                 BrokenPlanner(answer=D("48210.75")), None])
def test_ac5_margin_unavailable_or_invalid_is_unknown_not_zero_and_not_used(bad: object) -> None:
    """AC-5 (red case): a planner that fails, answers a bare number instead of a MarginRequirement, or is missing ->
    margin unknown, and the review says margin impact was not used for the order."""
    review = execution_review(golden(LOT), bad)  # type: ignore[arg-type]
    assert review.margin_required is None
    assert [f for f, _ in review.unknown] == ["margin_required"]
    assert review.margin_basis.startswith("margin impact unknown — not used")
    assert [line.leg_ref for line in review.sequence] == ["leg-1", "leg-4", "leg-2", "leg-3"]


def test_ac5_naked_short_call_shows_unlimited_loss_and_a_naked_note() -> None:
    """AC-5: SELL 23,400 CE alone: max loss UNLIMITED (engine sentinel), the naked units named in the notes."""
    review = execution_review(mk(leg(SELL, CE, "23400", price="91.50")), planner())
    assert review.max_loss is UNLIMITED
    assert review.max_profit == D("91.50") * LOT
    assert review.notes == ("L1: 65 sold units have no protective leg (naked)",)


def test_ac5_covered_call_is_not_called_naked_and_its_loss_is_finite() -> None:
    """AC-5: SELL 23,400 CE @50 + BUY future @23,100 (65 units): the engine's max loss is finite, (23,100 - 50) x 65
    = 14,98,250 at level 0, and the review does not call the call naked (same relation as the sequence)."""
    review = execution_review(mk(leg(SELL, CE, "23400"), leg(BUY, FUT, None, price="23100.00")), planner())
    assert review.max_loss == D("1498250.00")
    assert review.notes == ()
    assert [line.leg_ref for line in review.sequence] == ["L2", "L1"]


def test_ac5_multi_expiry_metrics_unknown_and_calendar_protected() -> None:
    """AC-5: a calendar (SELL 23,400 CE this week, BUY 23,400 CE next week): no exact at-expiry max profit / max loss
    exists, so both are unknown; the far long protects the near short, so it is not called naked."""
    review = execution_review(mk(leg(SELL, CE, "23400"), leg(BUY, CE, "23400", expiry=NEXT)), planner())
    assert review.max_loss is None and review.max_profit is None
    assert [f for f, _ in review.unknown] == ["max_loss", "max_profit", "current_pnl"]
    assert review.notes == ()


def test_ac5_review_needs_a_real_plan() -> None:
    """AC-5 (input domain): anything but an ExecutionPlan is refused."""
    with pytest.raises(ValueError, match="needs an ExecutionPlan"):
        execution_review(REFS, planner())  # type: ignore[arg-type]
