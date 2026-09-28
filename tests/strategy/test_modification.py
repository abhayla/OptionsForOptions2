"""REQ-037: strategy modification (roll a leg on the golden Iron Condor).

Core proof (W-027): the golden Iron Condor's sold 23,000 PE rolled to 22,900 PE returns engine-recalculated
Before/After metrics; version 2 is created only on confirmation; version 1 stays active until a broker execution
result activates the new version. Before values are the published golden numbers (scenario-calculations.md §6);
after values are hand-computed below from the same §1 formulas, never copied from a code run.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal as D

import pytest

from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.execution.safety import CheckCode, CheckFailure, SafetyResult
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.modification import (
    ChangeKind,
    LegChange,
    ModificationError,
    apply_changes,
    confirm_modification,
    execute_confirmed_modification,
    propose_modification,
)
from ofo.strategy.versions import (
    ExecutionResult,
    OutcomeKind,
    Position,
    ResultStatus,
    StrategyRecord,
    VersionError,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
QTY = 75

GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50")),
))
CONDOR = StrategyDefinition.from_engine("NIFTY", GOLDEN)

# The rolled put's price: an entry of 70.00 and an LTP of 65.00, chosen for this test (not published anywhere).
ROLLED_ENTRY = D("70.00")
ROLLED_LTP = D("65.00")

ENTRY_PRICES = {
    (Instrument.PE, D("22800"), EXPIRY): D("42.50"),
    (Instrument.PE, D("23000"), EXPIRY): D("86.00"),
    (Instrument.CE, D("23400"), EXPIRY): D("91.50"),
    (Instrument.CE, D("23600"), EXPIRY): D("44.00"),
    (Instrument.PE, D("22900"), EXPIRY): ROLLED_ENTRY,
}
LTPS = {
    (Instrument.PE, D("22800"), EXPIRY): D("38.20"),
    (Instrument.PE, D("23000"), EXPIRY): D("72.50"),
    (Instrument.CE, D("23400"), EXPIRY): D("78.00"),
    (Instrument.CE, D("23600"), EXPIRY): D("39.50"),
    (Instrument.PE, D("22900"), EXPIRY): ROLLED_LTP,
}

# The proposal: roll the sold 23,000 PE to the sold 22,900 PE (REQ-037's worked example).
ROLL = (
    LegChange(ChangeKind.REMOVE, Instrument.PE, D("23000"), EXPIRY),
    LegChange(ChangeKind.ADD, Instrument.PE, D("22900"), EXPIRY, action=Action.SELL, quantity=QTY),
)


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def clock() -> datetime.datetime:
    return T0 + datetime.timedelta(days=10)


def contract(instrument: Instrument, strike: str) -> tuple:
    return ("NIFTY", instrument, D(strike), EXPIRY)


FILLED = Position((
    (contract(Instrument.PE, "22800"), QTY),
    (contract(Instrument.PE, "23000"), -QTY),
    (contract(Instrument.CE, "23400"), -QTY),
    (contract(Instrument.CE, "23600"), QTY),
))

ROLLED_FILLED = Position((
    (contract(Instrument.PE, "22800"), QTY),
    (contract(Instrument.PE, "22900"), -QTY),
    (contract(Instrument.CE, "23400"), -QTY),
    (contract(Instrument.CE, "23600"), QTY),
))


def executed_record() -> StrategyRecord:
    """A StrategyRecord whose v1 (the golden condor) is active, as W-012's own core proof builds one."""
    rec = StrategyRecord(CONDOR, at=T0, clock=clock)
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, FILLED, at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.ACTIVATED
    return rec


@dataclass(frozen=True)
class _FakeMarginPlanner:
    total: D

    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        return MarginRequirement(total=self.total, source="fake-margin-planner")


@dataclass(frozen=True)
class _FakeChargesModel:
    total: D

    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        return ChargesBreakdown(items=(("brokerage", self.total),))


class _FailingMarginPlanner:
    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        raise RuntimeError("margin service unavailable")


class _FailingChargesModel:
    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        raise RuntimeError("charges service unavailable")


def _safety(*, blocked: bool) -> SafetyResult:
    failures = (CheckFailure(CheckCode.MARGIN_INSUFFICIENT, "not enough margin for the rolled strategy"),) \
        if blocked else ()
    return SafetyResult(
        failures=failures, passed=(), not_checked=(), not_applicable=(), flags=(),
        max_loss=None, margin_required=None, charges_estimate=None, blocked_execution=None,
    )


def test_core_ac2_roll_recalculates_before_and_after():
    """AC-2 (core proof): propose_modification's Before equals the golden condor's published numbers
    (scenario-calculations.md §6: max profit 6,825; max loss 8,175; breakevens 22,909 / 23,491; live P&L 1,365.00),
    and After is hand-computed for BUY 22,800 PE / SELL 22,900 PE (rolled, entry 70.00, LTP 65.00) / SELL 23,400 CE
    / BUY 23,600 CE:

    Net credit = (70.00 + 91.50 - 42.50 - 44.00) x 75 = 75.00 x 75 = 5,625 = max profit.
    Expiry payoff at 0/22,800/22,900/23,400/23,600 = -1,875 / -1,875 / 5,625 / 5,625 / -9,375 (upper tail flat) ->
    min P&L -9,375 = max loss 9,375. Breakevens: 22,800 + 1,875x100/7,500 = 22,825; 23,400 + 5,625x200/15,000 = 23,475.
    Live P&L = -322.50 (unchanged leg 1) + (70.00-65.00)x75=375.00 (rolled leg) + 1,012.50 (unchanged leg 3)
    - 337.50 (unchanged leg 4) = 727.50.
    """
    rec = executed_record()
    comparison = propose_modification(
        rec, ROLL, entry_prices=ENTRY_PRICES, ltps=LTPS,
        margin_planner=_FakeMarginPlanner(D("50000.00")), charges_model=_FakeChargesModel(D("236.40")),
    )
    assert comparison.active_version_number == 1

    before = comparison.before
    assert before.max_profit == D("6825")
    assert before.max_loss == D("8175")
    assert before.breakevens == (D("22909"), D("23491"))
    assert before.current_pnl == D("1365.00")
    assert before.margin == D("50000.00") and before.margin_unknown_reason is None
    assert before.charges == D("236.40") and before.charges_unknown_reason is None

    after = comparison.after
    assert after.max_profit == D("5625")
    assert after.max_loss == D("9375")
    assert after.breakevens == (D("22825"), D("23475"))
    assert after.current_pnl == D("727.50")
    assert after.margin == D("50000.00")
    assert after.charges == D("236.40")

    # Consistency: after's max loss equals -min_pnl (the same relationship the engine itself locks, §3).
    assert after.max_loss == -after.min_pnl

    # AC-3 side-effect check: computing the comparison creates no version and touches nothing (read-only).
    assert len(rec.versions) == 1 and rec.proposed_version is None and rec.active_version.number == 1


def test_ac1_leg_change_must_reference_active_legs():
    """AC-1: a proposal is expressed only against the active version's own legs; a leg with no link to it is
    impossible by construction (REMOVE/RESIZE need an existing slot, ADD refuses an already-held slot, and removing
    every leg is refused rather than producing a standalone/empty result)."""
    rec = executed_record()
    active_def = rec.active_version.definition

    with pytest.raises(ModificationError):  # REMOVE a slot the active version never held
        apply_changes(active_def, (LegChange(ChangeKind.REMOVE, Instrument.PE, D("21000"), EXPIRY),))

    with pytest.raises(ModificationError):  # RESIZE a slot the active version never held
        apply_changes(active_def, (LegChange(ChangeKind.RESIZE, Instrument.PE, D("21000"), EXPIRY, quantity=QTY),))

    with pytest.raises(ModificationError):  # ADD a slot the active version already holds
        apply_changes(active_def, (
            LegChange(ChangeKind.ADD, Instrument.PE, D("23000"), EXPIRY, action=Action.SELL, quantity=QTY),
        ))

    all_removed = tuple(
        LegChange(ChangeKind.REMOVE, leg.instrument, leg.strike, leg.expiry) for leg in active_def.legs
    )
    with pytest.raises(ModificationError):  # would leave no legs at all
        apply_changes(active_def, all_removed)

    # The roll IS accepted: REMOVE names a held slot, ADD names a fresh one, and the result is one attached
    # StrategyDefinition (never a bare leg).
    changed = apply_changes(active_def, ROLL)
    assert isinstance(changed, StrategyDefinition)
    slots = {(leg.instrument, leg.strike) for leg in changed.legs}
    assert slots == {
        (Instrument.PE, D("22800")), (Instrument.PE, D("22900")),
        (Instrument.CE, D("23400")), (Instrument.CE, D("23600")),
    }


def test_ac5_confirm_creates_new_version_and_keeps_v1_active_and_unchanged():
    """AC-5: confirming the roll creates proposed version 2, based on version 1; version 1 stays active and its own
    definition is not overwritten in place (both objects are kept, distinct and unchanged)."""
    rec = executed_record()
    v1_definition_before = rec.version(1).definition
    assert v1_definition_before == CONDOR

    v2 = confirm_modification(rec, ROLL, at=at(10), reason="roll the short put down")
    assert v2.number == 2 and v2.based_on == 1
    assert len(rec.versions) == 2
    assert rec.active_version.number == 1
    assert rec.version(1).definition == v1_definition_before == CONDOR  # v1 not overwritten in place
    assert rec.proposed_version.number == 2
    assert v2.definition != CONDOR
    assert {(leg.instrument, leg.strike) for leg in v2.definition.legs} == {
        (Instrument.PE, D("22800")), (Instrument.PE, D("22900")),
        (Instrument.CE, D("23400")), (Instrument.CE, D("23600")),
    }


def test_ac4_nothing_prepared_before_confirmation():
    """AC-4: an order is never prepared/executed for a roll that was never confirmed."""
    rec = executed_record()
    premature = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(10), "premature")
    with pytest.raises(VersionError):
        execute_confirmed_modification(rec, _safety(blocked=False), premature)
    assert rec.active_version.number == 1
    assert len(rec.versions) == 1


def test_ac4_execution_passes_through_the_gate_a_block_leaves_v1_active():
    """AC-4: confirmed adjustment orders execute only when the REQ-059 gate passes; a blocked gate leaves the
    active version exactly as it was and consumes nothing (the confirmed proposal stays available to retry)."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    assert rec.proposed_version.number == 2

    blocked_result = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(11), "adj-blocked")
    with pytest.raises(ModificationError):
        execute_confirmed_modification(rec, _safety(blocked=True), blocked_result)
    assert rec.active_version.number == 1
    assert rec.proposed_version.number == 2  # still pending: the blocked attempt was never applied

    ok_result = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(12), "adj-1")
    outcome = execute_confirmed_modification(rec, _safety(blocked=False), ok_result)
    assert outcome.kind is OutcomeKind.ACTIVATED
    assert rec.active_version.number == 2
    assert rec.version(1).definition == CONDOR  # AC-5: v1 is kept, unchanged


def test_ac4_second_proposal_while_one_is_pending_is_refused():
    """AC-4/AC-5: confirming one roll then proposing a second change while it is still pending is refused
    (W-012's StrategyRecord.edit already refuses this; this module relies on it rather than re-implementing it)."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    other_change = (LegChange(ChangeKind.RESIZE, Instrument.CE, D("23600"), EXPIRY, quantity=2 * QTY),)
    with pytest.raises(VersionError):
        confirm_modification(rec, other_change, at=at(11))
    assert len(rec.versions) == 2  # no third version was created


def test_ac4_reconciliation_required_refuses_a_new_proposal():
    """AC-4: while a broker mismatch leaves reconciliation required, no new modification can be proposed."""
    rec = executed_record()
    active_def = rec.version(1).definition
    resized = dataclasses.replace(active_def, legs=tuple(
        dataclasses.replace(leg, quantity=2 * QTY) if leg.instrument is Instrument.CE and leg.action is Action.BUY
        else leg
        for leg in active_def.legs
    ))
    v2 = rec.edit(resized, at=at(10))
    rec.confirm(v2.number, at=at(11))
    mismatched = Position((
        (contract(Instrument.PE, "22800"), 10 * QTY),  # far outside this untouched leg's 75..75 path -> MISMATCH
        (contract(Instrument.PE, "23000"), -QTY),
        (contract(Instrument.CE, "23400"), -QTY),
        (contract(Instrument.CE, "23600"), 2 * QTY),
    ))
    outcome = rec.apply_result(ExecutionResult(v2.number, ResultStatus.COMPLETE, mismatched, at(12), "mismatch-1"))
    assert outcome.kind is OutcomeKind.MISMATCH
    assert rec.reconciliation_required

    with pytest.raises(VersionError):
        confirm_modification(rec, ROLL, at=at(13))


def test_ac2_a_failing_margin_or_charges_provider_gives_unknown_never_zero():
    """AC-2: margin and charges come from the interfaces; a failing provider reports unknown, never a silent 0."""
    rec = executed_record()
    comparison = propose_modification(
        rec, ROLL, entry_prices=ENTRY_PRICES, ltps=None,
        margin_planner=_FailingMarginPlanner(), charges_model=_FailingChargesModel(),
    )
    for side in (comparison.before, comparison.after):
        assert side.margin is None and side.margin_unknown_reason
        assert side.charges is None and side.charges_unknown_reason
        assert side.current_pnl is None and side.current_pnl_unknown_reason  # no LTPs supplied either
