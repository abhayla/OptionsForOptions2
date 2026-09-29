"""REQ-058 AC-6 (W-043, deferred #71): a slicing refusal in Complete or Retry is a result, not an exception.

Spec basis: REQ-058 AC-6 "V1 never resubmits a failed order automatically; the failure is shown with its reason and the
user chooses the next action (Q193)". Close has returned "Nothing prepared: <reason>" since W-036; Complete and Retry
raised ValueError from ``sequence_plan`` instead.

Real input: the golden Iron Condor on the REAL instrument-list fixture (tests/fixtures/instruments/instruments_slice.csv:
NIFTY lot 65, SENSEX lot 20); three legs filled, the long CE rejected (state builder shared with test_close_refusals).
Hand-computed expectations:
- NIFTY freeze 64 < one lot of 65 -> refused; SENSEX freeze 19 < one lot of 20 -> refused;
- freeze 0 is not a positive integer -> refused;
- 100 units of the long CE filled leaves 650 - 100 = 550 units missing = 8.46 lots of 65 -> refused.
"""
from __future__ import annotations

import pytest
from partial_inputs import CONTRACTS, FILL_AT, REFS, STRATEGY_ID, FakePlanner
from plan_inputs import FakeConstraints
from test_close_refusals import _state

from ofo.engine import Action
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    PartialChoice,
    complete_strategy,
    retry_failed_leg,
)
from ofo.orders import FillEvent, Order, OrderState

BUY_CE = REFS[3]


def _run(flow: str, plan, book, broker, ctx, catalogue, eligibility, **kw):  # noqa: ANN001, ANN003, ANN202
    if flow == "complete":
        return complete_strategy(plan, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)
    return retry_failed_leg(plan, BUY_CE, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)


def _assert_refused(prep, flow: str, book, *reason_parts: str) -> None:  # noqa: ANN001
    choice = PartialChoice.COMPLETE_STRATEGY if flow == "complete" else PartialChoice.RETRY_FAILED_LEG
    assert prep.choice is choice
    assert not prep.ready
    assert prep.orders == () and prep.gate is None and prep.cancels == ()
    assert prep.reason.startswith("Nothing prepared: "), prep.reason
    for part in reason_parts:
        assert part in prep.reason, prep.reason
    assert book.closing_read_at(STRATEGY_ID) is None  # no state change: no Close marker appeared ...
    assert not book.has_live_preparation(STRATEGY_ID)  # ... and nothing is held for confirmation


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_core_freeze_below_one_lot_returns_a_refusal_result_on_nifty(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6 (core): NIFTY freeze 64 < lot 65. Complete and Retry return "Nothing prepared: <reason>" (no exception)
    and change no state; the very next call with a usable freeze prepares the rejected 24,000 CE's 650 units."""
    plan, book, broker, ctx = _state()
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, constraints=FakeConstraints(freeze=64, per_batch=10))
    _assert_refused(prep, flow, book, "below one lot of 65")
    ok = _run(flow, plan, book, broker, ctx, catalogue, eligibility)
    assert ok.ready, ok.reason
    assert [(o.leg_ref, o.contract, o.side, o.quantity) for o in ok.orders] == [(BUY_CE, CONTRACTS[3], Action.BUY, 650)]


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_ac6_freeze_below_one_lot_returns_a_refusal_result_on_sensex(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: SENSEX freeze 19 < catalogue lot 20 gives the same refusal result, naming the lot of 20."""
    plan, book, broker, ctx = _state("SENSEX")
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, constraints=FakeConstraints(freeze=19, per_batch=10))
    _assert_refused(prep, flow, book, "below one lot of 20")


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_ac6_unusable_freeze_value_returns_a_refusal_result(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: a broker constraint of 0 (not a positive integer) is a refusal result, not an exception."""
    plan, book, broker, ctx = _state()
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, constraints=FakeConstraints(freeze=0, per_batch=10))
    _assert_refused(prep, flow, book, "positive integer")


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_ac6_missing_quantity_not_in_whole_lots_returns_a_refusal_result(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: 100 of the long CE's 650 units filled, so 550 are missing = 8.46 lots of 65: a refusal result."""
    plan, book, broker, ctx = _state()
    lg = plan.legs[3].leg
    book.add(Order(STRATEGY_ID, BUY_CE, CONTRACTS[3], lg.action, 100, lg.entry_price, broker_order_id="BRK-P",
                   version_id="v1"))
    book.transition("BRK-P", OrderState.SUBMITTED)
    book.apply_fill(FillEvent("T-P", "BRK-P", CONTRACTS[3], lg.action, 100, lg.entry_price, FILL_AT))
    broker.positions.append(BrokerPositionLine(CONTRACTS[3], 100, lg.entry_price))
    broker.order_statuses.append(BrokerOrderStatus("BRK-P", CONTRACTS[3], OrderState.EXECUTED, 100))
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility)
    _assert_refused(prep, flow, book, "550 units", "whole number of lots of 65")
