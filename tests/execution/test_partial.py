"""W-023 core and REQ-058 AC-1..AC-3: the golden Iron Condor with three legs filled and the 23,600 CE buy rejected.

Hand computation (scenario-calculations.md §1 per-leg expiry P&L, §3 strategy metrics), 65 units, the three filled legs
BUY 22,800 PE @ 42.50, SELL 23,000 PE @ 86.00, SELL 23,400 CE @ 91.50; net credit per unit -42.50+86+91.50 = 135.00:
- level 0:      (22800-42.50) + (86-23000) + 91.50 = -65.00/unit  -> -4,225.00
- level 22,800: -42.50 + (86-200) + 91.50           = -65.00/unit  -> -4,225.00
- 23,000..23,400: 135.00/unit                                      ->  8,775.00 (max profit)
- above 23,400 only the short call moves: slope -65 rupees/point    -> max loss UNLIMITED
- breakevens: 22,800 + 65/200*200 = 22,865 (between -65 and +135 over 200 points); 23,400 + 135 = 23,535
Live P&L at LTPs 40.00 / 80.00 / 120.00: (40-42.50)*65 + (86-80)*65 + (91.50-120)*65 = -162.50 + 390.00 - 1,852.50
= -1,625.00.
"""
from __future__ import annotations

from decimal import Decimal as D

from partial_inputs import (
    CONTRACTS,
    LOT,
    REJECT_TEXT,
    FakeBroker,
    FakePlanner,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import UNLIMITED, Action, Instrument
from ofo.execution.partial import (
    CHOICE_ORDER,
    ExecutionStatus,
    PartialChoice,
    assess,
    close_partial_strategy,
    complete_strategy,
    retry_failed_leg,
    review_manually,
)
from ofo.orders import OrderState


def test_core_golden_condor_three_filled_fourth_rejected(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-1 core: exception state, engine metrics from the broker's three real legs (upside UNLIMITED), and Complete
    Strategy re-reads positions and order status, then prepares ONLY the missing BUY 23,600 CE order."""
    broker = FakeBroker(three_positions(), statuses())
    book, planner = book_with_three_filled(), FakePlanner()

    a = assess(plan(), broker.positions, broker.order_statuses, book, planner)
    assert a.status is ExecutionStatus.PARTIAL_EXCEPTION
    assert a.metrics.max_loss is UNLIMITED and a.metrics.min_pnl is UNLIMITED
    assert a.metrics.max_profit == D("8775.00")
    assert a.metrics.breakevens == (D("22865"), D("23535"))
    assert [(leg.action, leg.instrument, leg.strike, leg.quantity) for leg in a.actual_legs] == [
        (Action.BUY, Instrument.PE, D("22800"), LOT),
        (Action.SELL, Instrument.PE, D("23000"), LOT),
        (Action.SELL, Instrument.CE, D("23400"), LOT),
    ]
    assert a.choices == CHOICE_ORDER

    prep = complete_strategy(plan(), broker, book, planner, entry_context(), catalogue, eligibility)
    assert broker.calls[:2] == ["positions", "order_statuses"]
    assert prep.gate is not None and not prep.gate.blocked
    assert len(prep.orders) == 1
    (order,) = prep.orders
    assert (order.leg_ref, order.contract, order.side, order.quantity, order.price) == (
        "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"))
    assert order.state is OrderState.PREPARED and order.broker_order_id is None  # prepared, not sent


def test_ac1_margin_and_live_pnl_recomputed_from_broker_legs() -> None:
    """AC-1: live P&L comes from the engine on the broker's legs and LTPs (hand value -1,625.00); margin is asked of
    the planner for exactly those three real legs, not the four intended ones."""
    planner = FakePlanner(D("61234.50"))
    positions = three_positions((D("40.00"), D("80.00"), D("120.00")))
    a = assess(plan(), positions, statuses(), book_with_three_filled(), planner)
    assert a.live_pnl == D("-1625.00")
    assert a.margin_required == D("61234.50")
    (asked,) = planner.asked
    assert [(leg.strike, leg.action) for leg in asked.legs] == [
        (D("22800"), Action.BUY), (D("23000"), Action.SELL), (D("23400"), Action.SELL)]


def test_ac1_broker_average_price_not_plan_price_drives_metrics() -> None:
    """AC-1: the broker's average price is the entry. Short 23,400 CE filled at 101.50 instead of 91.50 raises the
    credit to 145.00/unit: max profit 145*65 = 9,425.00; upper breakeven 23,400+145 = 23,545."""
    positions = three_positions()
    positions[2] = type(positions[2])(CONTRACTS[2], -LOT, D("101.50"))
    a = assess(plan(), positions, statuses(), book_with_three_filled(), FakePlanner())
    assert a.metrics.max_profit == D("9425.00")
    assert a.metrics.breakevens[-1] == D("23545")


def test_ac1_ledger_disagreeing_with_broker_is_not_an_exception_but_a_block() -> None:
    """AC-1 negative: the broker's order status says 60 of the 23,400 CE sell filled while the ledger holds 65 ->
    reconciliation required, no choices, and the book blocks the strategy (ADR-018, issue #29 item 1)."""
    positions = three_positions()
    sts = statuses()
    sts[2] = type(sts[2])("BRK-3", CONTRACTS[2], OrderState.EXECUTED, 60)  # broker says 60 filled, ledger 65
    book = book_with_three_filled()
    a = assess(plan(), positions, sts, book, FakePlanner())
    assert a.status is ExecutionStatus.RECONCILIATION_REQUIRED
    assert a.choices == ()
    assert book.is_submit_blocked("S-1")


def test_ac2_choices_in_spec_order_only_in_the_exception() -> None:
    """AC-2: Complete Strategy, Retry Failed Leg, Review Manually, Close Partial Strategy -- in that order, with the
    spec's words; offered only in the exception state (not when complete)."""
    assert [c.value for c in CHOICE_ORDER] == [
        "Complete Strategy", "Retry Failed Leg", "Review Manually", "Close Partial Strategy"]
    a = assess(plan(), three_positions(), statuses(), book_with_three_filled(), FakePlanner())
    assert a.choices == CHOICE_ORDER
    assert review_manually(a).orders == ()
    assert review_manually(a).choice is PartialChoice.REVIEW_MANUALLY


def test_ac3_filled_legs_never_unwound_automatically(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-3: assessing, completing, retrying and reviewing never prepare an order in a filled leg's contract; only the
    user's own Close Partial Strategy prepares exits -- reduce-only, exactly the three filled legs, through the gate."""
    filled = set(CONTRACTS[:3])
    a = assess(plan(), three_positions(), statuses(), book_with_three_filled(), FakePlanner())
    preps = [
        complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book_with_three_filled(), FakePlanner(),
                          entry_context(), catalogue, eligibility),
        retry_failed_leg(plan(), "leg-4", FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                         FakePlanner(), entry_context(), catalogue, eligibility),
        review_manually(a),
    ]
    for prep in preps:
        assert not {o.contract for o in prep.orders} & filled

    positions = three_positions((D("40.00"), D("80.00"), D("120.00")))
    close = close_partial_strategy(plan(), FakeBroker(positions, statuses()), book_with_three_filled(),
                                   FakePlanner(), entry_context(), catalogue, eligibility)
    assert close.gate is not None and not close.gate.blocked
    assert close.gate.not_applicable and "EXIT_NOT_REDUCE_ONLY" in {c.value for c in close.gate.passed}
    # shorts bought back first, then the long sold; exactly the held quantities, at the broker's LTP
    assert [(o.contract, o.side, o.quantity, o.price) for o in close.orders] == [
        (CONTRACTS[1], Action.BUY, LOT, D("80.00")),
        (CONTRACTS[2], Action.BUY, LOT, D("120.00")),
        (CONTRACTS[0], Action.SELL, LOT, D("40.00")),
    ]


def test_ac3_close_without_ltp_prepares_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-3 negative: a filled leg without a broker price -> nothing prepared (fail closed)."""
    close = close_partial_strategy(plan(), FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                                   FakePlanner(), entry_context(), catalogue, eligibility)
    assert close.orders == () and close.gate is None


def test_reject_reason_is_the_brokers_text() -> None:
    """AC-1/AC-6 support: the failure names the leg and carries the broker's text verbatim."""
    a = assess(plan(), three_positions(), statuses(), book_with_three_filled(), FakePlanner())
    (failure,) = a.failures
    assert (failure.leg_ref, failure.contract, failure.reason) == ("leg-4", CONTRACTS[3], REJECT_TEXT)
