"""ADR-092 / issue 255 (with 43 and 63): no order the platform prepares is split for the freeze limit.

Spec basis: ADR-092 "Complete, Retry and exit orders follow it too. The review shows the largest allowed order (NIFTY
today: 54 lots, 3,510 units) and never lists freeze slices. The fixed 1,755-unit placeholder used for slicing is
removed"; ADR-081 "A leg whose quantity is above the contract's freeze limit is blocked on the order review with the
reason and the limit, never split."; F-36: NIFTY's stored limit is 3,511 units (15 Oct 2026 file) and the largest
allowed order is the limit minus one, rounded down to whole lots.

Real case, hand-computed: NIFTY lot 65 (the real instrument-list fixture), limit 3,511. 54 lots = 3,510 units < 3,511
-> one order; 55 lots = 3,575 units -> blocked, "largest single order allowed is 3510 units (54 lots)". The old
behaviour listed 1,755 / 1,755 / 65 for 55 lots.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterator, Mapping
from decimal import Decimal as D

import pytest
from execution_inputs import condor_legs
from partial_inputs import (
    BROKER_IDS, CONTRACTS, FILL_AT, LOT, REFS, REJECT_TEXT, STRATEGY_ID, FakeBroker, FakePlanner, condor_record,
    entry_context, new_book,
)

from ofo.engine import Action, Instrument, Leg
from ofo.errors import display_text
from ofo.execution.freeze import (
    FreezeRefused, StoredFreeze, exceeded_message, freeze_check, require_within_freeze,
)
from ofo.execution.partial import (
    BrokerOrderStatus, BrokerPositionLine, ExecutionPlan, PlannedLeg, close_partial_strategy, complete_strategy,
    retry_failed_leg,
)
from ofo.execution.review import execution_review
from ofo.orders import FillEvent, Order, OrderState

LIMIT = 3511  # F-36, NIFTY, exchange file of 2026-10-15
FILE_DATE = datetime.date(2026, 10, 15)
TODAY = datetime.date(2026, 10, 16)
BLOCKED_LOTS, ALLOWED_LOTS = 55, 54
BUY_PE, SELL_PE, SELL_CE, BUY_CE = REFS
NIFTY = StoredFreeze(LIMIT, 65, FILE_DATE)
LARGEST = "the largest single order allowed is 3510 units (54 lots)"


class _Stored(Mapping):
    """The freeze store: every contract has ``limit`` (or none at all when ``limit`` is None)."""

    def __init__(self, limit: int | None) -> None:
        self.limit = limit

    def __getitem__(self, key: object) -> tuple[int, datetime.date]:
        if self.limit is None:
            raise KeyError(key)
        return (self.limit, FILE_DATE)

    def __contains__(self, key: object) -> bool:
        return self.limit is not None

    def __iter__(self) -> Iterator[object]:
        return iter(())

    def __len__(self) -> int:
        return 0


def _plan(qty: int) -> ExecutionPlan:
    return ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg) for r, c, lg in zip(REFS, CONTRACTS, condor_legs(qty), strict=True)))


def _state(qty: int, filled: tuple[int, ...]):  # noqa: ANN202
    """Legs at ``filled`` filled in full; every other leg's order REJECTED with nothing filled."""
    book = new_book(record=condor_record(qty))
    positions, sts = [], []
    for i, (ref, contract, lg) in enumerate(zip(REFS, CONTRACTS, condor_legs(qty), strict=True)):
        book.add(Order(STRATEGY_ID, ref, contract, lg.action, qty, lg.entry_price, broker_order_id=BROKER_IDS[i],
                       version_id="v1"))
        book.transition(BROKER_IDS[i], OrderState.SUBMITTED)
        if i in filled:
            book.apply_fill(FillEvent(f"T-{i + 1}", BROKER_IDS[i], contract, lg.action, qty, lg.entry_price, FILL_AT))
            sign = 1 if lg.action is Action.BUY else -1
            positions.append(BrokerPositionLine(contract, sign * qty, lg.entry_price, ltp=D("10.00")))
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.EXECUTED, qty))
        else:
            book.transition(BROKER_IDS[i], OrderState.REJECTED)
            sts.append(BrokerOrderStatus(BROKER_IDS[i], contract, OrderState.REJECTED, 0, REJECT_TEXT))
    return book, FakeBroker(positions, sts)


def _flow(kind: str, lots: int, catalogue, eligibility, limit: int | None = LIMIT):  # noqa: ANN001, ANN202
    qty = lots * LOT
    book, broker = _state(qty, (0, 1, 2))
    args = (_plan(qty), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    if kind == "complete":
        return complete_strategy(*args, stored_freeze=_Stored(limit))
    if kind == "retry":
        plan, *rest = args
        return retry_failed_leg(plan, BUY_CE, *rest, stored_freeze=_Stored(limit))
    return close_partial_strategy(*args, stored_freeze=_Stored(limit))


# -- Core ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_core_55_lots_blocked_with_the_limit_and_54_lots_is_one_order(kind, catalogue, eligibility) -> None:  # noqa: ANN001
    """ADR-092 (core): 55 NIFTY lots (3,575 units) prepares nothing and names the largest allowed order; 54 lots
    (3,510 units) prepares ONE order per leg, never 1,755 / 1,755 / 65."""
    blocked = _flow(kind, BLOCKED_LOTS, catalogue, eligibility)
    assert not blocked.ready and blocked.orders == () and blocked.slices == ()
    assert "3575 units (55 lots) is not below the exchange freeze limit of 3511 units" in blocked.text
    assert LARGEST in blocked.text

    allowed = _flow(kind, ALLOWED_LOTS, catalogue, eligibility)
    assert allowed.ready, allowed.text
    assert [o.quantity for o in allowed.orders] == [3510] * len(allowed.orders)
    expected_legs = [BUY_CE] if kind != "close" else [SELL_PE, SELL_CE, BUY_PE]  # close: buy-backs of shorts first
    assert [o.leg_ref for o in allowed.orders] == expected_legs  # one order per leg, no slices


def test_core_review_lists_one_line_per_leg_and_blocks_55_lots() -> None:
    """ADR-092 (core, review): the review's sequence lists the 3,575-unit leg ONCE (never 1,755 / 1,755 / 65) and the
    block names the limit and the largest allowed order."""
    leg = Leg(Action.BUY, Instrument.CE, D("23600"), datetime.date(2026, 10, 6), BLOCKED_LOTS * 65, D("50.00"))
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", "NIFTY26O0623600CE", leg),))
    review = execution_review(plan, None, freeze_limits={"NIFTY26O0623600CE": NIFTY}, today=TODAY)
    assert [ln.quantity for ln in review.sequence] == [3575]
    assert not review.can_execute and LARGEST in display_text(review.blocked[0].message)


# -- Attack cases ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("units,blocked", [(3510, False), (3575, True), (3445, False)])
def test_attack_exactly_at_the_largest_allowed_order_is_one_order_one_lot_more_is_blocked(units, blocked) -> None:
    """Attack 1: 54 lots (3,510) passes; 55 lots (3,575) blocks; the shared check and the review agree."""
    if blocked:
        with pytest.raises(FreezeRefused) as err:
            require_within_freeze("NIFTY26O0623600CE", units, NIFTY)
        assert LARGEST in display_text(err.value.message)
    else:
        require_within_freeze("NIFTY26O0623600CE", units, NIFTY)
    assert (exceeded_message("NIFTY26O0623600CE", units, NIFTY) is not None) is blocked


def test_attack_a_unit_count_equal_to_the_limit_is_blocked() -> None:
    """Attack 1 (boundary, F-36): the limit itself is not allowed (allowed exactly when units are BELOW it)."""
    at_limit = StoredFreeze(130, 65, FILE_DATE)
    with pytest.raises(FreezeRefused):
        require_within_freeze("NIFTY26O0623600CE", 130, at_limit)
    require_within_freeze("NIFTY26O0623600CE", 65, at_limit)


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_no_stored_limit_blocks_with_a_clear_reason(kind, catalogue, eligibility) -> None:  # noqa: ANN001
    """Attack 3 (fail closed): no stored limit for the contract -> nothing prepared, the reason says so."""
    prep = _flow(kind, 1, catalogue, eligibility, limit=None)
    assert not prep.ready and prep.orders == ()
    assert "no exchange freeze limit is stored for NIFTY" in prep.text


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_a_stored_limit_below_one_lot_blocks_every_order(kind, catalogue, eligibility) -> None:  # noqa: ANN001
    """B4(d) below one lot: a limit of 65 with lot 65 allows no order at all (largest allowed 0 lots)."""
    prep = _flow(kind, 1, catalogue, eligibility, limit=65)
    assert not prep.ready and prep.orders == ()
    assert "the largest single order allowed is 0 units (0 lots)" in prep.text


@pytest.mark.parametrize("bad", [0, -1, True, "3511"])
def test_attack_a_zero_or_malformed_stored_limit_is_refused(bad) -> None:
    """B4(d) zero: a stored limit that is not a positive integer cannot be built (so it can never allow an order)."""
    with pytest.raises(ValueError):
        StoredFreeze(bad, 65, FILE_DATE)  # type: ignore[arg-type]


@pytest.mark.parametrize("units", [0, -65, True, 100])
def test_attack_units_that_are_not_positive_whole_lots_are_refused(units) -> None:
    """Allow-list: only a positive whole number of lots is checked; anything else is an error, never a pass."""
    with pytest.raises(ValueError):
        require_within_freeze("NIFTY26O0623600CE", units, NIFTY)


def test_attack_a_forged_limit_object_is_refused() -> None:
    """Allow-list: the limit must be a real StoredFreeze, not any object with ``limit``/``lot`` attributes."""
    class Forged:
        limit, lot = 10**9, 65
    with pytest.raises(ValueError):
        require_within_freeze("NIFTY26O0623600CE", 65, Forged())  # type: ignore[arg-type]


def test_attack_freeze_check_review_still_warns_without_a_stored_limit() -> None:
    """ADR-081 "While no freeze limit is stored for a contract, the review warns": the entry review warns, not blocks."""
    leg = Leg(Action.BUY, Instrument.CE, D("23600"), datetime.date(2026, 10, 6), 65, D("50.00"))
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", "NIFTY26O0623600CE", leg),))
    check = freeze_check(plan, {}, today=TODAY)
    assert check.blocks == () and len(check.warnings) == 1
