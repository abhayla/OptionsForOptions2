"""AC-4 (REQ-054, ADR-081): on the order review a leg whose units are not below the contract's stored freeze limit is
blocked with the reason and the limit; a leg with no stored limit carries the warning; nothing is split.

Values: NIFTY26O1923550CE (token 47185) has freeze limit 3511 on NSE's 15 Oct 2026 file and lot 65 (F-36, real row).
3511 = 54 x 65 + 1, so 54 lots = 3,510 units is the largest allowed order and 55 lots = 3,575 units is blocked.
Tests marked synthetic use lot 1 so that units == limit is reachable (a real lot of 65 never lands on 3,511)."""
from __future__ import annotations

import datetime

import pytest
from plan_inputs import CE, SELL, FakeMargin, leg

from ofo.errors.templates import display_text
from ofo.execution.freeze import StoredFreeze, freeze_check, largest_allowed_units
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.review import execution_review

SYMBOL = "NIFTY26O1923550CE"
EXPIRY = datetime.date(2026, 10, 19)
REAL = StoredFreeze(limit=3511, lot=65, file_date=datetime.date(2026, 10, 15))


def plan_of(units: int, symbol: str = SYMBOL) -> ExecutionPlan:
    lg = leg(SELL, CE, "23550", qty=units, expiry=EXPIRY)
    return ExecutionPlan("S-1", (PlannedLeg("leg-1", symbol, lg),))


def review(units: int, limits):
    return execution_review(plan_of(units), FakeMargin({}), freeze_limits=limits)


def test_core_55_lots_blocked_54_lots_passes() -> None:
    """AC-4 core: 3,575 units (55 lots) is blocked, 3,510 units (54 lots) passes, on the real limit 3511."""
    blocked = review(55 * 65, {SYMBOL: REAL})
    assert blocked.can_execute is False
    [finding] = blocked.blocked
    assert (finding.leg_ref, finding.contract) == ("leg-1", SYMBOL)
    text = display_text(finding.message)
    assert "3575 units (55 lots)" in text
    assert "3511 units" in text
    assert "3510 units (54 lots)" in text
    assert blocked.warnings == ()
    ok = review(54 * 65, {SYMBOL: REAL})
    assert ok.can_execute is True and ok.blocked == () and ok.warnings == ()


def test_largest_allowed_is_limit_minus_one_rounded_to_lots() -> None:
    """AC-4: F-36 arithmetic by hand: 3511 - 1 = 3510 = 54 x 65; BANKNIFTY 1441 -> 1440 = 48 x 30."""
    assert largest_allowed_units(REAL) == 3510
    assert largest_allowed_units(StoredFreeze(1441, 30, datetime.date(2026, 10, 15))) == 1440
    # synthetic: a limit that IS a lot multiple (3510 = 54 x 65): an order of 3,510 is not below it, so 53 lots is the top
    assert largest_allowed_units(StoredFreeze(3510, 65, datetime.date(2026, 10, 15))) == 3445


def test_boundary_units_equal_to_limit_is_blocked_synthetic() -> None:
    """AC-4 (synthetic, lot 1): limit 100 -> 99 passes, 100 blocks, 101 blocks. Kills `<` mutated to `<=`."""
    stored = StoredFreeze(limit=100, lot=1, file_date=datetime.date(2026, 10, 15))
    assert freeze_check(plan_of(99), {SYMBOL: stored}).blocks == ()
    assert len(freeze_check(plan_of(100), {SYMBOL: stored}).blocks) == 1
    assert len(freeze_check(plan_of(101), {SYMBOL: stored}).blocks) == 1


def test_missing_limit_warns_and_never_blocks_or_passes_silently() -> None:
    """AC-4: no stored limit (none given, an empty map, or only another contract's limit) -> the warning, no block."""
    for limits in (None, {}, {"NIFTY26O1923600CE": REAL}):
        r = review(55 * 65, limits)
        assert r.can_execute is True and r.blocked == ()
        [w] = r.warnings
        assert w.contract == SYMBOL
        assert "Zerodha may reject a large order" in display_text(w.message)


def test_limits_are_matched_by_the_plan_contract_symbol_not_by_position() -> None:
    """AC-4: a limit stored for another symbol never applies to this leg."""
    other = {"NIFTY26O1923600CE": StoredFreeze(100, 1, datetime.date(2026, 10, 15))}
    assert freeze_check(plan_of(5000), other).blocks == ()


def test_four_part_messages_and_codes() -> None:
    """AC-4 (REQ-065, ADR-086): both messages carry the four parts; the block says what it blocks."""
    blocked = review(55 * 65, {SYMBOL: REAL}).blocked[0].message
    warn = review(55 * 65, None).warnings[0].message
    for m in (blocked, warn):
        assert m.what_happened and m.impact and m.what_is_blocked and m.next_action
    assert blocked.code == "STRATEGY_VALIDATION_501" and warn.code == "STRATEGY_VALIDATION_502"
    assert "Reduce this leg to 54 lots or fewer" in blocked.next_action


def test_blocked_review_is_not_executable_and_slicing_is_left_as_it_was() -> None:
    """AC-4: ADR-081 'never split' - a blocked leg makes the review not executable. The existing entry sequence
    (REQ-058, unchanged by this item) still shows 3,575 units as slices of the 1,755 default; reported, not edited."""
    r = review(55 * 65, {SYMBOL: REAL})
    assert r.can_execute is False
    assert [ln.quantity for ln in r.sequence] == [1755, 1755, 65]


def test_stored_freeze_refuses_non_positive_and_bool() -> None:
    """AC-4: the stored limit and lot are positive integers; bool and 0 are refused."""
    d = datetime.date(2026, 10, 15)
    for limit, lot in ((0, 65), (-1, 65), (3511, 0), (True, 65), (3511, True), (3511.0, 65)):
        with pytest.raises(ValueError):
            StoredFreeze(limit, lot, d)


def test_review_still_needs_an_execution_plan() -> None:
    """AC-4: freeze_check never accepts a hand-built plan substitute."""
    with pytest.raises(ValueError):
        freeze_check("plan", {})  # type: ignore[arg-type]
