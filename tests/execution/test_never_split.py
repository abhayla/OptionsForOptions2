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
from ofo.engine import Action, Instrument, Leg
from ofo.errors import display_text
from ofo.execution.freeze import (
    ContractFreeze,
    FreezeRefused,
    StoredFreeze,
    exceeded_message,
    freeze_check,
    largest_allowed_units,
    require_within_freeze,
    usable,
)
from ofo.execution.partial import (
    BrokerOrderStatus,
    BrokerPositionLine,
    ExecutionPlan,
    PlannedLeg,
    close_partial_strategy,
    complete_strategy,
    retry_failed_leg,
)
from ofo.execution.review import execution_review
from ofo.orders import FillEvent, Order, OrderState
from partial_inputs import (
    BROKER_IDS,
    CONTRACTS,
    FILL_AT,
    LOT,
    REFS,
    REJECT_TEXT,
    STRATEGY_ID,
    FakeBroker,
    FakePlanner,
    condor_record,
    entry_context,
    new_book,
)

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
    return ExecutionPlan(STRATEGY_ID, tuple(PlannedLeg(r, c, lg)
                                            for r, c, lg in zip(REFS, CONTRACTS, condor_legs(qty), strict=True)))


def _state(qty: int, filled: tuple[int, ...]):
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


def _flow(kind: str, lots: int, catalogue, eligibility, limit: int | None = LIMIT):
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
def test_core_55_lots_blocked_with_the_limit_and_54_lots_is_one_order(kind, catalogue, eligibility) -> None:
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
            require_within_freeze("NIFTY26O0623600CE", units, NIFTY, today=TODAY)
        assert LARGEST in display_text(err.value.message)
    else:
        assert require_within_freeze("NIFTY26O0623600CE", units, NIFTY, today=TODAY) == ()
    (warning,) = require_within_freeze("NIFTY26O0623600CE", units, None, today=TODAY)
    assert display_text(warning).startswith("No exchange freeze limit is stored for NIFTY26O0623600CE")
    assert (exceeded_message("NIFTY26O0623600CE", units, NIFTY) is not None) is blocked


def test_attack_a_unit_count_equal_to_the_limit_is_blocked() -> None:
    """Attack 1 (boundary, F-36): the limit itself is not allowed (allowed exactly when units are BELOW it)."""
    at_limit = StoredFreeze(130, 65, FILE_DATE)
    with pytest.raises(FreezeRefused):
        require_within_freeze("NIFTY26O0623600CE", 130, at_limit, today=TODAY)
    assert require_within_freeze("NIFTY26O0623600CE", 65, at_limit, today=TODAY) == ()


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_no_stored_limit_warns_and_never_blocks_even_at_55_lots(kind, catalogue, eligibility) -> None:
    """Attack 3 (ADR-081 "the review warns"; ADR-037 never stop a user getting out of risk): no stored limit -> the
    55-lot order is prepared as ONE order with the review's warning for its contract, never blocked."""
    prep = _flow(kind, BLOCKED_LOTS, catalogue, eligibility, limit=None)
    assert prep.ready, prep.text
    assert [o.quantity for o in prep.orders] == [3575] * len(prep.orders)
    assert [display_text(w).startswith(f"No exchange freeze limit is stored for {o.contract}")
            for w, o in zip(prep.warnings, prep.orders, strict=True)] == [True] * len(prep.orders)
    with_limit = _flow(kind, BLOCKED_LOTS, catalogue, eligibility)
    assert not with_limit.ready and with_limit.warnings == ()


@pytest.mark.parametrize("limit", [64, 65])
@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_a_stored_limit_below_one_lot_warns_as_unknown_and_never_blocks(kind, limit, catalogue,
                                                                              eligibility) -> None:
    """Finding 2 (round 2): a stored limit that allows no whole lot (64 or 65 with NIFTY lot 65) is bad stored data;
    blocking on it would refuse even a 1-lot exit. It is treated as no limit: ONE order plus the unknown warning."""
    prep = _flow(kind, 1, catalogue, eligibility, limit=limit)
    assert prep.ready, prep.text
    assert [o.quantity for o in prep.orders] == [65] * len(prep.orders)
    assert [display_text(w).startswith(f"No exchange freeze limit is stored for {o.contract}")
            for w, o in zip(prep.warnings, prep.orders, strict=True)] == [True] * len(prep.orders)
    usable = _flow(kind, 1, catalogue, eligibility, limit=66)  # the smallest usable limit: one lot allowed, no warning
    assert usable.ready and usable.warnings == ()


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_a_zero_stored_limit_warns_as_unknown_and_never_blocks(kind, catalogue, eligibility) -> None:
    """Zero (bad stored data that cannot be a StoredFreeze): the order is prepared with the unknown warning."""
    prep = _flow(kind, BLOCKED_LOTS, catalogue, eligibility, limit=0)
    assert prep.ready, prep.text
    assert [display_text(w).startswith("No exchange freeze limit is stored for") for w in prep.warnings]         == [True] * len(prep.orders)


@pytest.mark.parametrize("kind", ["complete", "retry", "close"])
def test_attack_a_stale_stored_limit_warns_on_every_path(kind, catalogue, eligibility) -> None:
    """Finding 3 (round 2): the stale-file warning reaches Complete / Retry / Close, as the review's freeze_check:
    the limit still applies (55 lots blocked), and a 54-lot order is prepared with the age warning."""
    stale = datetime.date(2026, 9, 1)  # 28 days before the fake broker read's IST day (more than 8)

    class _StaleStore(_Stored):
        def __getitem__(self, key: object) -> tuple[int, datetime.date]:
            return (LIMIT, stale)

    qty = ALLOWED_LOTS * LOT
    book, broker = _state(qty, (0, 1, 2))
    args = (_plan(qty), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    if kind == "complete":
        prep = complete_strategy(*args, stored_freeze=_StaleStore(LIMIT))
    elif kind == "retry":
        plan, *rest = args
        prep = retry_failed_leg(plan, BUY_CE, *rest, stored_freeze=_StaleStore(LIMIT))
    else:
        prep = close_partial_strategy(*args, stored_freeze=_StaleStore(LIMIT))
    assert prep.ready, prep.text
    texts = [display_text(w) for w in prep.warnings]
    blocked_book, blocked_broker = _state(BLOCKED_LOTS * LOT, (0, 1, 2))
    blocked_args = (_plan(BLOCKED_LOTS * LOT), blocked_broker, blocked_book, FakePlanner(), entry_context(), catalogue,
                    eligibility)
    if kind == "complete":
        blocked = complete_strategy(*blocked_args, stored_freeze=_StaleStore(LIMIT))
    elif kind == "retry":
        bplan, *brest = blocked_args
        blocked = retry_failed_leg(bplan, BUY_CE, *brest, stored_freeze=_StaleStore(LIMIT))
    else:
        blocked = close_partial_strategy(*blocked_args, stored_freeze=_StaleStore(LIMIT))
    assert not blocked.ready and LARGEST in blocked.text  # the stale limit still applies
    assert len(texts) == len(prep.orders)
    assert all(t.startswith("The freeze limit for ") and "exchange file of 01 Sep 2026, 28 days ago" in t for t in texts), texts
    fresh = _flow(kind, ALLOWED_LOTS, catalogue, eligibility)
    assert fresh.ready and fresh.warnings == ()


def test_require_within_freeze_warns_stale_exactly_after_eight_days() -> None:
    """The shared check's age boundary equals freeze_check's: 8 days old is fresh, 9 days warns."""
    eight = StoredFreeze(LIMIT, 65, TODAY - datetime.timedelta(days=8))
    nine = StoredFreeze(LIMIT, 65, TODAY - datetime.timedelta(days=9))
    assert require_within_freeze("NIFTY26O0623600CE", 65, eight, today=TODAY) == ()
    (warning,) = require_within_freeze("NIFTY26O0623600CE", 65, nine, today=TODAY)
    assert "9 days ago" in display_text(warning)
    with pytest.raises(FreezeRefused):  # stale still blocks above the limit
        require_within_freeze("NIFTY26O0623600CE", 3575, nine, today=TODAY)
    with pytest.raises(ValueError):  # today is required to be a date
        require_within_freeze("NIFTY26O0623600CE", 65, eight, today=datetime.datetime(2026, 10, 16))


@pytest.mark.parametrize("bad", [0, -1, True, "3511"])
def test_attack_a_zero_or_malformed_stored_limit_is_refused(bad) -> None:
    """B4(d) zero: a stored limit that is not a positive integer cannot be built (so it can never allow an order)."""
    with pytest.raises(ValueError):
        StoredFreeze(bad, 65, FILE_DATE)  # type: ignore[arg-type]


@pytest.mark.parametrize("units", [0, -65, True, 100])
def test_attack_units_that_are_not_positive_whole_lots_are_refused(units) -> None:
    """Allow-list: only a positive whole number of lots is checked; anything else is an error, never a pass."""
    with pytest.raises(ValueError):
        require_within_freeze("NIFTY26O0623600CE", units, NIFTY, today=TODAY)


class _Forged:
    limit, lot = 10**9, 65


_WRONG_TYPES = [1800, "3511", 18.0, {"limit": 1800, "lot": 65}, _Forged(), True, (1800, 65)]


@pytest.mark.parametrize("bad", _WRONG_TYPES)
def test_attack_a_wrongly_typed_stored_limit_is_a_type_error_on_every_entry(bad) -> None:
    """Allow-list (class: programmer error downgraded to "limit unknown"): only StoredFreeze or None. Dies if
    ``_require_stored_type`` is dropped from ``usable`` (and so from require_within_freeze/_assess/freeze_check)."""
    with pytest.raises(TypeError, match="StoredFreeze"):
        require_within_freeze("NIFTY26O0623600CE", 65, bad, today=TODAY)
    with pytest.raises(TypeError):
        usable(bad)
    with pytest.raises(TypeError):
        exceeded_message("NIFTY26O0623600CE", 65, bad)
    with pytest.raises(TypeError):
        largest_allowed_units(bad)
    with pytest.raises(TypeError):  # dies if ContractFreeze.__post_init__ guard is removed
        ContractFreeze("NIFTY26O0623600CE", bad)
    leg = Leg(Action.BUY, Instrument.CE, D("23600"), datetime.date(2026, 10, 6), 65, D("50.00"))
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", "NIFTY26O0623600CE", leg),))
    with pytest.raises(TypeError):
        freeze_check(plan, {"NIFTY26O0623600CE": bad}, today=TODAY)


def test_none_stored_limit_still_gives_the_limit_unknown_warning() -> None:
    (warning,) = require_within_freeze("NIFTY26O0623600CE", 65, None, today=TODAY)
    assert display_text(warning).startswith("No exchange freeze limit is stored for NIFTY26O0623600CE")
    assert usable(None) is None


def test_attack_freeze_check_review_still_warns_without_a_stored_limit() -> None:
    """ADR-081 "While no freeze limit is stored for a contract, the review warns": warns, never blocks."""
    leg = Leg(Action.BUY, Instrument.CE, D("23600"), datetime.date(2026, 10, 6), 65, D("50.00"))
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", "NIFTY26O0623600CE", leg),))
    check = freeze_check(plan, {}, today=TODAY)
    assert check.blocks == () and len(check.warnings) == 1
