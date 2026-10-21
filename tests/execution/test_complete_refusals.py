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
from partial_inputs import STORED_FREEZE, stored_limit
from plan_inputs import FakeConstraints
from test_close_refusals import _state

from ofo.errors import display_text
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
BELOW = "is not below the exchange freeze limit of"


def _run(flow: str, plan, book, broker, ctx, catalogue, eligibility, **kw):  # noqa: ANN001, ANN003, ANN202
    kw.setdefault("stored_freeze", STORED_FREEZE)
    if flow == "complete":
        return complete_strategy(plan, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)
    return retry_failed_leg(plan, BUY_CE, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)


def _assert_refused(prep, flow: str, book, *reason_parts: str, prefix: str = "Nothing prepared: ") -> None:  # noqa: ANN001
    choice = PartialChoice.COMPLETE_STRATEGY if flow == "complete" else PartialChoice.RETRY_FAILED_LEG
    assert prep.choice is choice
    assert not prep.ready
    assert prep.orders == () and prep.gate is None and prep.cancels == ()
    assert prep.reason.startswith(prefix), prep.reason
    for part in reason_parts:
        assert part in prep.reason, prep.reason
    assert book.closing_read_at(STRATEGY_ID) is None  # no state change: no Close marker appeared ...
    assert not book.has_live_preparation(STRATEGY_ID)  # ... and nothing is held for confirmation


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_core_freeze_below_one_lot_returns_a_refusal_result_on_nifty(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6 (core, ADR-092): a STORED NIFTY limit of 66 allows 1 lot of 65. Complete and Retry return the block for the
    10-lot leg with the limit and the largest allowed order (1 lot), no exception, no state change; the very next call with the
    real stored limit (3,511) prepares the rejected 24,000 CE's 650 units as one order."""
    plan, book, broker, ctx = _state()
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(66))
    _assert_refused(prep, flow, book, BELOW + " 66 units", "65 units (1 lots)", prefix=CONTRACTS[3])
    ok = _run(flow, plan, book, broker, ctx, catalogue, eligibility)
    assert ok.ready, ok.reason
    assert [(o.leg_ref, o.contract, o.side, o.quantity) for o in ok.orders] == [(BUY_CE, CONTRACTS[3], Action.BUY, 650)]


@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_ac6_freeze_below_one_lot_returns_a_refusal_result_on_sensex(flow, catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: a stored SENSEX limit of 21 (1 lot of 20 allowed) gives the same block (largest allowed 1 lot)."""
    plan, book, broker, ctx = _state("SENSEX")
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(21))
    _assert_refused(prep, flow, book, BELOW + " 21 units", "20 units (1 lots)", prefix="SENSEX")


@pytest.mark.parametrize("limit", [0, 64, 65])
@pytest.mark.parametrize("flow", ["complete", "retry"])
def test_round2_unusable_stored_limit_warns_and_prepares_one_order(flow, limit, catalogue, eligibility) -> None:  # noqa: ANN001
    """Round 2 finding 2 (ADR-081, ADR-037): a stored limit of 0, or one that allows no whole lot of 65, is bad stored
    data: the rejected 24,000 CE's 650 units are prepared as ONE order with the unknown warning, never a block."""
    plan, book, broker, ctx = _state()
    prep = _run(flow, plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(limit))
    assert prep.ready, prep.reason
    assert [(o.leg_ref, o.quantity) for o in prep.orders] == [(BUY_CE, 650)]
    assert [display_text(w).startswith(f"No exchange freeze limit is stored for {CONTRACTS[3]}, so Zerodha may reject")
            for w in prep.warnings] == [True]


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
