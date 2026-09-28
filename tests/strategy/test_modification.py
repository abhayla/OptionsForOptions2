"""REQ-037 AC-1, AC-4, AC-5: strategy modification (roll a leg on the golden Iron Condor).

AC-2 (the recalculated Before/After metrics) is tests/strategy/test_modification_metrics.py, per work/W-027.md's
tests_required. This file covers: AC-1 (a leg change is impossible without an active-version slot), AC-4 (nothing
is prepared/executed before confirmation and the REQ-059 gate), AC-5 (every modification creates a new version;
old versions are kept, unchanged, active, until execution).
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest

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


def _safety(*, blocked: bool) -> SafetyResult:
    failures = (CheckFailure(CheckCode.MARGIN_INSUFFICIENT, "not enough margin for the rolled strategy"),) \
        if blocked else ()
    return SafetyResult(
        failures=failures, passed=(), not_checked=(), not_applicable=(), flags=(),
        max_loss=None, margin_required=None, charges_estimate=None, blocked_execution=None,
    )


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
