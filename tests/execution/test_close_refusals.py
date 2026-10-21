"""REQ-058 AC-6 (W-036, deferred #62): a Close/Complete/Retry refusal is decided before any state change.

Spec basis: REQ-058 AC-6 "V1 never resubmits a failed order automatically; the failure is shown with its reason and the
user chooses the next action (Q193)"; REQ-058 AC-2 (the four choices). Issue #62: a freeze below one lot, or a held
quantity that is not whole lots, made ``close_partial_strategy`` RAISE after ``mark_closing`` had run, so the user got
an error instead of a reason, and Complete/Retry then waited for a newer broker read although nothing was prepared.

State under test: the Close choice marker (``OrderBook.closing_read_at``), set only when a Close preparation is ready,
and cleared by Complete/Retry only when their preparation is ready on a strictly later read.

Real input: the golden Iron Condor on the REAL instrument-list fixture (tests/fixtures/instruments/instruments_slice.csv:
NIFTY 2026-10-06, lot 65; SENSEX 2026-10-01, lot 20). Hand-computed expectations:
- a stored NIFTY limit of 64 < one lot of 65 -> no whole lot fits -> blocked (largest allowed 0 lots, ADR-092);
- a stored SENSEX limit of 19 < one lot of 20 -> blocked (largest allowed 0 lots, ADR-092);
- 650 held - 100 already exiting = 550 units = 8.46 lots of 65 -> not whole lots -> refused;
- Complete after a refused Close on the SAME read: the rejected 24,000 CE's 650 units, one order below the
  stored 3,511-unit limit (ADR-092: never split).
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

from execution_inputs import condor_legs
from partial_inputs import (
    BROKER_IDS,
    CONTRACTS,
    FILL_AT,
    LOT,
    READ_AT,
    REFS,
    REJECT_TEXT,
    STRATEGY_ID,
    Clock,
    FakeBroker,
    FakePlanner,
    entry_context,
    new_book,
    record_for_legs,
)
from partial_inputs import STORED_FREEZE, stored_limit
from plan_inputs import FakeConstraints
import pytest

from ofo.errors import display_text
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution.partial import (
    IN_FLIGHT,
    NEEDS_FRESH_READ,
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionPlan,
    PartialChoice,
    PlannedLeg,
    close_partial_strategy,
    complete_strategy,
    discard_preparation,
    retry_failed_leg,
)
from ofo.orders import FillEvent, Order, OrderState
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import StrategyRecord

QTY = 10 * LOT  # 650 units per leg
BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS
LTPS = (D("40.00"), D("80.00"), D("120.00"), D("30.00"))
SENSEX_LOT = 20
SENSEX_QTY = 12 * SENSEX_LOT  # 240
SENSEX_CONTRACTS = ("SENSEX26O0173500PE", "SENSEX26O0173800PE", "SENSEX26O0174200CE", "SENSEX26O0174500CE")
LATER = READ_AT + datetime.timedelta(seconds=5)  # inside the book clock's window (clock = READ_AT + 10 s)


def _legs(market: str) -> tuple[Leg, ...]:
    if market == "NIFTY":
        return condor_legs(QTY)
    e = datetime.date(2026, 10, 1)
    return (Leg(Action.BUY, Instrument.PE, D("73500"), e, SENSEX_QTY, D("110.00")),
            Leg(Action.SELL, Instrument.PE, D("73800"), e, SENSEX_QTY, D("190.00")),
            Leg(Action.SELL, Instrument.CE, D("74200"), e, SENSEX_QTY, D("205.00")),
            Leg(Action.BUY, Instrument.CE, D("74500"), e, SENSEX_QTY, D("100.00")))


def _state(market: str = "NIFTY", clock: Clock | None = None):  # noqa: ANN202
    """Three legs filled in full (LTP on each), the fourth (the long CE) REJECTED with nothing filled."""
    legs = _legs(market)
    contracts = CONTRACTS if market == "NIFTY" else SENSEX_CONTRACTS
    qty = legs[0].quantity
    if market == "NIFTY":
        record = record_for_legs(legs)
    else:
        record = StrategyRecord(StrategyDefinition.from_engine("SENSEX", Strategy(legs)),
                                at=FILL_AT - datetime.timedelta(minutes=10), clock=lambda: READ_AT)
        record.propose_execution(at=FILL_AT - datetime.timedelta(minutes=9))
    book = new_book(clock=clock, record=record)
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, contracts, legs)):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, qty, lg.entry_price, broker_order_id=BROKER_IDS[i],
                       version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i < 3:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, qty, lg.entry_price, FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * qty, lg.entry_price, LTPS[i]))
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, qty))
        else:
            book.transition(BROKER_IDS[i], OrderState.REJECTED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.REJECTED, 0, REJECT_TEXT))
    plan = ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg) for r, c, lg in zip(REFS, contracts, legs)))
    return plan, book, FakeBroker(positions, sts), entry_context(underlying=market)


def _close(plan, book, broker, ctx, catalogue, eligibility, **kw):  # noqa: ANN001, ANN003, ANN202
    kw.setdefault("stored_freeze", STORED_FREEZE)
    return close_partial_strategy(plan, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)


def _complete(plan, book, broker, ctx, catalogue, eligibility, **kw):  # noqa: ANN001, ANN003, ANN202
    kw.setdefault("stored_freeze", STORED_FREEZE)
    return complete_strategy(plan, broker, book, FakePlanner(), ctx, catalogue, eligibility, **kw)


def _assert_blocked(prep, *reason_parts: str) -> None:
    """ADR-092: the freeze block (above a known stored limit): no order, the limit and largest allowed order named."""
    assert not prep.ready and prep.orders == () and prep.gate is None
    for part in reason_parts:
        assert part in prep.reason, prep.reason


def _assert_refused(prep, *reason_parts: str) -> None:  # noqa: ANN001
    assert prep.choice is PartialChoice.CLOSE_PARTIAL_STRATEGY
    assert not prep.ready
    assert prep.orders == () and prep.gate is None and prep.cancels == ()
    assert prep.reason.startswith("Nothing prepared: "), prep.reason
    for part in reason_parts:
        assert part in prep.reason, prep.reason


# -- Core ------------------------------------------------------------------------------------------------------------


def test_core_close_with_freeze_below_one_lot_returns_a_refusal_and_does_not_mark_closing(catalogue,  # noqa: ANN001
                                                                                          eligibility) -> None:
    """AC-6 (core, #62, ADR-092): a stored NIFTY limit of 66 (the smallest usable one: 1 lot of 65) blocks the 10-lot
    exits. Close returns the block (no exception), the strategy is NOT marked closing, nothing is held, and Complete on the SAME read with the real stored limit (3,511)
    is not told to wait for a newer read: it prepares the rejected 24,000 CE's 650 units as one order."""
    plan, book, broker, ctx = _state()
    prep = _close(plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(66))
    _assert_blocked(prep, "freeze limit of 66 units", "65 units (1 lots)")
    assert book.closing_read_at(STRATEGY_ID) is None
    assert not book.has_live_preparation(STRATEGY_ID)
    after = _complete(plan, book, broker, ctx, catalogue, eligibility)
    assert after.reason != NEEDS_FRESH_READ
    assert after.ready, after.reason
    assert [(o.leg_ref, o.contract, o.side, o.quantity) for o in after.orders] == [(BUY_CE, CONTRACTS[3], Action.BUY,
                                                                                    650)]


# -- Other Close refusal paths ---------------------------------------------------------------------------------------


def test_ac6_sensex_freeze_below_one_lot_is_a_refusal_without_marking_closing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: a stored SENSEX limit of 21 (1 lot of 20 allowed): the block, not marked closing; Retry of the rejected leg
    on the same read is not held back by the Close choice."""
    plan, book, broker, ctx = _state("SENSEX")
    prep = _close(plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(21))
    _assert_blocked(prep, "freeze limit of 21 units", "20 units (1 lots)")
    assert book.closing_read_at(STRATEGY_ID) is None
    retry = retry_failed_leg(plan, BUY_CE, broker, book, FakePlanner(), ctx, catalogue, eligibility,
            stored_freeze=STORED_FREEZE)
    assert retry.reason != NEEDS_FRESH_READ
    assert retry.ready, retry.reason
    assert [(o.leg_ref, o.quantity) for o in retry.orders] == [(BUY_CE, 240)]


def test_ac6_held_quantity_not_in_whole_lots_is_a_refusal_without_marking_closing(catalogue,  # noqa: ANN001
                                                                                  eligibility) -> None:
    """AC-6: 100 of the 650 short 23,000 PE units already have an exit open, leaving 550 = 8.46 lots of 65: refusal
    result, not marked closing. Complete on the same read is then refused ONLY because an order is in flight."""
    plan, book, broker, ctx = _state()
    book.add(Order(STRATEGY_ID, SELL_PE, CONTRACTS[1], Action.BUY, 100, D("80.00"), broker_order_id="BRK-X",
                   version_id="v1"))
    book.transition("BRK-X", OrderState.SUBMITTED)
    broker.order_statuses.append(BrokerOrderStatus("BRK-X", CONTRACTS[1], OrderState.SUBMITTED, 0))
    prep = _close(plan, book, broker, ctx, catalogue, eligibility)
    _assert_refused(prep, "550 units", "whole number of lots of 65")
    assert book.closing_read_at(STRATEGY_ID) is None
    assert _complete(plan, book, broker, ctx, catalogue, eligibility).reason == IN_FLIGHT


@pytest.mark.parametrize("limit", [0, 19, 64, 65])
def test_round2_unusable_stored_limit_warns_and_close_prepares_one_order_per_leg(limit, catalogue,  # noqa: ANN001
                                                                                 eligibility) -> None:
    """Round 2 finding 2 (ADR-081 "the review warns"; ADR-037): a stored limit of 0 or one that allows no whole lot of
    65 is bad stored data, never a block on the exit: Close prepares each held leg as ONE order with the unknown
    warning for its contract."""
    plan, book, broker, ctx = _state()
    prep = _close(plan, book, broker, ctx, catalogue, eligibility, stored_freeze=stored_limit(limit))
    assert prep.ready, prep.reason
    assert [o.quantity for o in prep.orders] == [650] * len(prep.orders)
    assert [display_text(w).startswith(f"No exchange freeze limit is stored for {o.contract},")
            for w, o in zip(prep.warnings, prep.orders, strict=True)] == [True] * len(prep.orders)


def test_ac6_missing_ltp_refusal_does_not_mark_closing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: Zerodha gave no LTP for the short 23,000 PE: nothing prepared, and the refused Close leaves no marker."""
    plan, book, broker, ctx = _state()
    broker.positions[1] = dataclasses.replace(broker.positions[1], ltp=None)
    prep = _close(plan, book, broker, ctx, catalogue, eligibility)
    assert not prep.ready and prep.orders == ()
    assert "did not give a current price" in prep.reason
    assert book.closing_read_at(STRATEGY_ID) is None


def test_ac6_exits_already_in_flight_refusal_does_not_mark_closing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: every held leg already has its full exit open (650 each): nothing to prepare, no marker."""
    plan, book, broker, ctx = _state()
    exits = ((SELL_PE, CONTRACTS[1], Action.BUY), (SELL_CE, CONTRACTS[2], Action.BUY),
             (BUY_PE, CONTRACTS[0], Action.SELL))
    for n, (ref, contract, side) in enumerate(exits):
        book.add(Order(STRATEGY_ID, ref, contract, side, QTY, D("50.00"), broker_order_id=f"BRK-E{n}",
                       version_id="v1"))
        book.transition(f"BRK-E{n}", OrderState.SUBMITTED)
        broker.order_statuses.append(BrokerOrderStatus(f"BRK-E{n}", contract, OrderState.SUBMITTED, 0))
    prep = _close(plan, book, broker, ctx, catalogue, eligibility)
    assert not prep.ready and prep.orders == ()
    assert "already in flight" in prep.reason
    assert book.closing_read_at(STRATEGY_ID) is None


def test_ac6_safety_gate_block_does_not_mark_closing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: the broker is disconnected, so the pre-execution gate blocks the Close: nothing prepared, no marker."""
    plan, book, broker, _ = _state()
    ctx = entry_context(broker_connected=False)
    prep = _close(plan, book, broker, ctx, catalogue, eligibility)
    assert not prep.ready and prep.orders == ()
    assert prep.gate is not None and prep.gate.blocked
    assert book.closing_read_at(STRATEGY_ID) is None


# -- The marker still works when Close DOES prepare ------------------------------------------------------------------


def test_ac6_a_ready_close_still_marks_closing_and_holds_complete_on_the_same_read(catalogue,  # noqa: ANN001
                                                                                  eligibility) -> None:
    """AC-6 control: a Close that prepares orders marks the strategy closing on its read (READ_AT); after the user
    discards it, Complete on the SAME read is refused with NEEDS_FRESH_READ (W-023 fix (d) unchanged)."""
    plan, book, broker, ctx = _state()
    prep = _close(plan, book, broker, ctx, catalogue, eligibility)
    assert prep.ready, prep.reason
    assert book.closing_read_at(STRATEGY_ID) == READ_AT
    discard_preparation(prep)
    assert _complete(plan, book, broker, ctx, catalogue, eligibility).reason == NEEDS_FRESH_READ


def test_ac6_complete_refusal_on_a_later_read_keeps_the_close_marker(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: after a ready Close (marker = READ_AT), Complete on a later read with a stored limit of 66 is blocked
    (largest allowed 1 lot of 65) and returns a refusal result; the Close marker is NOT cleared by the refused attempt; a later Complete that does prepare clears it."""
    plan, book, broker, ctx = _state()
    discard_preparation(_close(plan, book, broker, ctx, catalogue, eligibility))
    broker.read_at = LATER
    refused = _complete(plan, book, broker, ctx, catalogue, eligibility,
                        stored_freeze=stored_limit(66))  # W-043 (#71): a result, not a raise
    assert not refused.ready and refused.orders == ()
    assert "65 units (1 lots)" in refused.reason
    assert book.closing_read_at(STRATEGY_ID) == READ_AT
    ok = _complete(plan, book, broker, ctx, catalogue, eligibility)
    assert ok.ready, ok.reason
    assert book.closing_read_at(STRATEGY_ID) is None


class _SlowPlanner(FakePlanner):
    """Each margin question takes 30 s of platform time, so the broker read goes stale while Close prepares."""

    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self.clock = clock

    def required_margin(self, strategy: Strategy) -> D:
        self.clock.advance(30)
        return super().required_margin(strategy)


def test_ac6_a_read_gone_stale_while_preparing_leaves_no_marker_and_no_held_preparation(catalogue,  # noqa: ANN001
                                                                                       eligibility) -> None:
    """AC-6: the read (READ_AT) was fresh when taken (clock READ_AT + 10 s) but three 30 s margin questions later the
    clock is READ_AT + 100 s, past the 60 s age limit, so the Close choice cannot be recorded on it: the ready
    preparation is discarded (nothing held, cannot be sent) and a "Nothing prepared: stale broker read" result comes
    back instead of an exception."""
    clock = Clock()
    plan, book, broker, ctx = _state(clock=clock)
    prep = close_partial_strategy(plan, broker, book, _SlowPlanner(clock), ctx, catalogue, eligibility,
            stored_freeze=STORED_FREEZE)
    assert clock() == READ_AT + datetime.timedelta(seconds=70)
    _assert_refused(prep, "stale broker read")
    assert book.closing_read_at(STRATEGY_ID) is None
    assert not book.has_live_preparation(STRATEGY_ID)
