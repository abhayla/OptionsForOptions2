"""REQ-038 AC-2..AC-4: activity history before execution, versions after, proposed vs active, broker actual wins.

Core proof (W-012): the golden Iron Condor (spec/business-rules/scenario-calculations.md §6, the same four legs as
tests/engine/test_golden_iron_condor.py) goes through draft edits, a simulated execution result, a modification,
and a partial broker result.
"""
from __future__ import annotations

import dataclasses
import datetime
import time
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
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
CONDOR = StrategyDefinition.from_engine("NIFTY", GOLDEN, risk_limits={"max_loss": D("8175")})


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def clock() -> datetime.datetime:
    return T0 + datetime.timedelta(days=1)


def record() -> StrategyRecord:
    return StrategyRecord(CONDOR, at=T0, clock=clock)


def with_legs(definition: StrategyDefinition, legs) -> StrategyDefinition:
    return dataclasses.replace(definition, legs=tuple(legs))


def scaled(definition: StrategyDefinition, quantity: int) -> StrategyDefinition:
    return with_legs(definition, (dataclasses.replace(leg, quantity=quantity) for leg in definition.legs))


def contract(instrument: Instrument, strike: str) -> tuple:
    return ("NIFTY", instrument, D(strike), EXPIRY)


def broker(**units: int) -> Position:
    """Broker position by leg name: bp22800, sp23000, sc23400, bc23600 (signed units)."""
    names = {"bp22800": (Instrument.PE, "22800"), "sp23000": (Instrument.PE, "23000"),
             "sc23400": (Instrument.CE, "23400"), "bc23600": (Instrument.CE, "23600")}
    return Position(tuple((contract(*names[name]), value) for name, value in units.items()))


FILLED_1_LOT = dict(bp22800=75, sp23000=-75, sc23400=-75, bc23600=75)


def executed_record() -> StrategyRecord:
    rec = record()
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, broker(**FILLED_1_LOT), at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.ACTIVATED
    return rec


def test_core_golden_iron_condor_history_then_versions_then_partial_fill():
    """AC-2: draft edits are history, not versions; AC-3: the modification stays proposed until confirmed and
    reconciled; AC-4: a partial broker fill (1 of 2 lots on one leg) is recorded as the actual position."""
    rec = record()
    # Draft phase: move the short call 23400 -> 23500 (a strike change) -> one history entry, no version.
    moved = with_legs(CONDOR, (CONDOR.legs[0], CONDOR.legs[1],
                               dataclasses.replace(CONDOR.legs[2], strike=D("23500")), CONDOR.legs[3]))
    entry = rec.edit(moved, at=at(1))
    assert entry.seq == 1 and entry.before == CONDOR and entry.after == moved
    assert entry.changes == ("removed leg SELL 23400 CE 2026-10-27 x75", "added leg SELL 23500 CE 2026-10-27 x75")
    assert rec.versions == () and not rec.has_executed
    # Restore the original: the current (moved) configuration is kept in history first.
    restored = rec.restore(0, at=at(2))
    assert restored.kind == "restored entry 0" and restored.before == moved and rec.definition == CONDOR
    assert [e.seq for e in rec.history] == [0, 1, 2] and rec.versions == ()

    # Simulated first execution: proposed v1 -> confirmed -> COMPLETE and reconciled -> active.
    v1 = rec.propose_execution(at=at(3))
    assert rec.active_version is None and rec.proposed_version == v1
    rec.confirm(1, at=at(4))
    first = rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, broker(**FILLED_1_LOT), at(5), "exec-1"))
    assert first.kind is OutcomeKind.ACTIVATED and rec.active_version == v1 and rec.has_executed

    # The same kind of edit now creates proposed version 2 (2 lots per leg), not a history entry.
    two_lots = scaled(CONDOR, 150)
    v2 = rec.edit(two_lots, at=at(6), reason="add a lot")
    assert v2.number == 2 and v2.based_on == 1 and v2.definition == two_lots
    assert rec.proposed_version == v2 and rec.active_version == v1 and len(rec.history) == 3

    # Partial broker result: the short put filled 1 of 2 lots.
    rec.confirm(2, at=at(7))
    partial = broker(bp22800=150, sp23000=-75, sc23400=-150, bc23600=150)
    outcome = rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, partial, at(8), "exec-2"))
    assert outcome.kind is OutcomeKind.PARTIAL
    assert rec.active_version == v1                     # AC-3: active unchanged
    assert rec.actual_position == partial               # AC-4: broker actual wins
    assert rec.actual_position.as_dict()[contract(Instrument.PE, "23000")] == -75
    assert outcome.differences == ((contract(Instrument.PE, "23000"), -150, -75),)
    assert rec.version(2).definition == two_lots        # what the user asked for is not rewritten
    assert rec.version(1).definition == CONDOR
    assert [leg.quantity for leg in rec.version(2).definition.legs] == [150, 150, 150, 150]


def test_before_first_execution_edits_are_history_with_restore_and_no_versions():
    """AC-2: before the first execution every meaningful change is a history entry; restore keeps the current."""
    rec = record()
    three_lots = scaled(CONDOR, 225)
    rec.edit(three_lots, at=at(1))
    no_wing = with_legs(three_lots, three_lots.legs[:3])
    removed = rec.edit(no_wing, at=at(2))
    assert removed.changes == ("removed leg BUY 23600 CE 2026-10-27 x225",)
    later = datetime.date(2026, 11, 24)
    rolled = with_legs(no_wing, (dataclasses.replace(leg, expiry=later) for leg in no_wing.legs))
    assert len(rec.edit(rolled, at=at(3)).changes) == 6  # expiry change: 3 removed + 3 added
    limits = dataclasses.replace(rolled, risk_limits={"max_loss": D("5000")})
    assert rec.edit(limits, at=at(4)).changes == ("risk_limits (('max_loss', Decimal('8175')),) -> (('max_loss', Decimal('5000')),)",)
    assert rec.versions == () and len(rec.history) == 5
    rec.restore(1, at=at(5))
    assert rec.definition == three_lots and rec.history[-1].before == limits and len(rec.history) == 6


def test_after_first_execution_every_meaningful_change_is_a_new_preserved_version():
    """AC-2: from the first execution on, each meaningful change is a new version; old ones stay retrievable."""
    rec = executed_record()
    v2 = rec.edit(scaled(CONDOR, 150), at=at(10), based_on=1)
    rec.confirm(2, at=at(11))
    rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE,
                                     broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150), at(12), "exec-2"))
    v3 = rec.edit(dataclasses.replace(scaled(CONDOR, 150), rules_ref="exit-rules-2"), at=at(13))
    assert [v.number for v in rec.versions] == [1, 2, 3]
    assert rec.active_version == v2 and rec.proposed_version == v3 and v3.based_on == 2
    assert rec.version(1).definition == CONDOR and rec.version(2).definition == scaled(CONDOR, 150)
    assert len(rec.history) == 1  # no history entries after execution


def test_version_is_immutable_and_an_old_version_cannot_be_edited():
    """AC-2 red: a stored version refuses mutation, and an edit based on a non-active version is refused."""
    rec = executed_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.version(1).definition = scaled(CONDOR, 150)
    rec.edit(scaled(CONDOR, 150), at=at(10))
    rec.confirm(2, at=at(11))
    rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE,
                                     broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150), at(12), "exec-2"))
    with pytest.raises(VersionError, match="old versions are read-only"):
        rec.edit(scaled(CONDOR, 225), at=at(13), based_on=1)
    with pytest.raises(VersionError, match="restore by proposing"):
        rec.restore(0, at=at(13))


def test_change_with_no_meaningful_difference_records_nothing():
    """AC-2 red: reordering legs or re-typing an equal number is not a change, before or after execution."""
    rec = record()
    reordered = with_legs(CONDOR, reversed(CONDOR.legs))
    retyped = with_legs(CONDOR, (dataclasses.replace(leg, strike=leg.strike.quantize(D("0.01"))) for leg in CONDOR.legs))
    assert rec.edit(reordered, at=at(1)) is None and rec.edit(retyped, at=at(1)) is None
    assert len(rec.history) == 1 and rec.restore(0, at=at(1)) is None and len(rec.history) == 1
    executed = executed_record()
    assert executed.edit(reordered, at=at(10)) is None
    assert len(executed.versions) == 1 and executed.proposed_version is None


def test_proposed_activates_only_after_confirmation_and_complete_reconciled_result():
    """AC-3: the proposal is separate from the active version until both conditions hold."""
    rec = executed_record()
    v2 = rec.edit(scaled(CONDOR, 150), at=at(10))
    assert rec.active_version.number == 1 and rec.proposed_version == v2
    rec.confirm(2, at=at(11))
    assert rec.active_version.number == 1  # confirmation alone does not activate
    two = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150)
    outcome = rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE, two, at(12), "exec-2"))
    assert outcome.kind is OutcomeKind.ACTIVATED and outcome.differences == ()
    assert rec.active_version == v2 and rec.proposed_version is None and rec.definition == scaled(CONDOR, 150)


def test_activate_without_confirmation_is_refused():
    """AC-3 red: a result for an unconfirmed proposal is refused and nothing changes."""
    rec = executed_record()
    rec.edit(scaled(CONDOR, 150), at=at(10))
    two = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150)
    with pytest.raises(VersionError, match="never confirmed"):
        rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE, two, at(11), "exec-2"))
    assert rec.active_version.number == 1 and rec.actual_position == broker(**FILLED_1_LOT)
    with pytest.raises(VersionError, match="not the pending"):
        rec.confirm(1, at=at(11))


@pytest.mark.parametrize("status,kind", [(ResultStatus.REJECTED, OutcomeKind.REJECTED),
                                         (ResultStatus.FAILED, OutcomeKind.FAILED)])
def test_failed_or_rejected_result_leaves_active_unchanged_and_records_outcome(status, kind):
    """AC-3 red: a rejected/failed result never activates; the outcome is recorded and the proposal closes."""
    rec = executed_record()
    rec.edit(scaled(CONDOR, 150), at=at(10))
    rec.confirm(2, at=at(11))
    outcome = rec.apply_result(ExecutionResult(2, status, broker(**FILLED_1_LOT), at(12), "exec-2"))
    assert outcome.kind is kind and rec.active_version.number == 1 and rec.proposed_version is None
    assert rec.outcomes_for(2) == (outcome,) and outcome.intended == rec.version(2).intended_position


def test_complete_claim_that_disagrees_with_broker_position_is_a_mismatch_not_activation():
    """AC-3/AC-4 red: 'complete' with a broker position that differs from the version does not activate."""
    rec = executed_record()
    rec.edit(scaled(CONDOR, 150), at=at(10))
    rec.confirm(2, at=at(11))
    short = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=75)
    outcome = rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE, short, at(12), "exec-2"))
    assert outcome.kind is OutcomeKind.MISMATCH and rec.active_version.number == 1
    assert rec.actual_position == short and rec.proposed_version.number == 2
    moved = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150)
    rejected_but_moved = rec.apply_result(ExecutionResult(2, ResultStatus.REJECTED, moved, at(13), "exec-2b"))
    assert rejected_but_moved.kind is OutcomeKind.MISMATCH and rec.actual_position == moved


def test_first_execution_partial_fill_counts_as_executed_and_broker_actual_wins():
    """AC-4: 1 of 2 lots filled on the first execution: actual = the fill, no active version, edits blocked."""
    rec = StrategyRecord(scaled(CONDOR, 150), at=T0, clock=clock)
    rec.propose_execution(at=at(1))
    rec.confirm(1, at=at(2))
    fill = broker(bp22800=75, sp23000=-75, sc23400=-75, bc23600=75)
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.PARTIAL, fill, at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.PARTIAL and rec.has_executed and rec.active_version is None
    assert rec.actual_position == fill and len(outcome.differences) == 4
    assert rec.version(1).definition == scaled(CONDOR, 150)
    with pytest.raises(VersionError, match="awaiting its execution result"):
        rec.edit(CONDOR, at=at(4))


def test_first_execution_rejected_with_nothing_filled_keeps_draft_history_mode():
    """AC-2: a proposal that filled nothing is not an execution; later edits are history entries again."""
    rec = record()
    rec.propose_execution(at=at(1))
    rec.confirm(1, at=at(2))
    rec.apply_result(ExecutionResult(1, ResultStatus.REJECTED, Position(), at(3), "exec-1"))
    assert not rec.has_executed and rec.active_version is None
    entry = rec.edit(scaled(CONDOR, 150), at=at(4))
    assert entry.seq == 1 and len(rec.versions) == 1


def test_input_domain_guards():
    """AC-3 red: duplicate result, raw state change, naive/future/backdated time, wrong version, no-op confirm."""
    rec = executed_record()
    rec.edit(scaled(CONDOR, 150), at=at(10))
    with pytest.raises(VersionError, match="awaiting its execution result"):
        rec.edit(scaled(CONDOR, 225), at=at(10))
    with pytest.raises(VersionError, match="already executed"):
        rec.propose_execution(at=at(10))
    rec.confirm(2, at=at(11))
    with pytest.raises(VersionError, match="already confirmed"):
        rec.confirm(2, at=at(11))
    with pytest.raises(VersionError, match="already applied"):
        rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, broker(**FILLED_1_LOT), at(12), "exec-1"))
    with pytest.raises(VersionError, match="not the pending"):
        rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, broker(**FILLED_1_LOT), at(12), "x"))
    with pytest.raises(AttributeError, match="only through its methods"):
        rec._active = 2
    with pytest.raises(VersionError, match="timezone-aware"):
        ExecutionResult(2, ResultStatus.COMPLETE, Position(), datetime.datetime(2026, 10, 1, 10, 0), "r")
    with pytest.raises(VersionError, match="in the future"):
        rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, Position(), clock() + datetime.timedelta(hours=1), "f"))
    with pytest.raises(VersionError, match="before the last recorded event"):
        rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, Position(), at(5), "b"))
    with pytest.raises(VersionError, match="duplicate position line"):
        Position(((contract(Instrument.PE, "23000"), -75), (contract(Instrument.PE, "23000"), -75)))
    with pytest.raises(VersionError, match="within"):
        Position(((contract(Instrument.PE, "23000"), 10**9),))
    assert rec.active_version.number == 1 and rec.proposed_version.number == 2


def test_one_thousand_history_appends_stay_fast():
    """AC-2: history append is O(1): 1,000 meaningful draft edits finish well under a second."""
    rec = record()
    start = time.perf_counter()
    for i in range(1000):
        rec.edit(scaled(CONDOR, 75 * (2 + i % 2)), at=at(1))
    assert len(rec.history) == 1001 and time.perf_counter() - start < 1.0


FUT = ("NIFTY", Instrument.FUT, None, EXPIRY)


def pending_two_lots() -> StrategyRecord:
    rec = executed_record()
    rec.edit(scaled(CONDOR, 150), at=at(10))
    rec.confirm(2, at=at(11))
    return rec


def test_partial_with_unrequested_futures_position_is_a_mismatch():
    """AC-4 red: a PARTIAL result that also holds an unasked 75-unit future is a MISMATCH, whatever the word says."""
    rec = pending_two_lots()
    held = broker(bp22800=150, sp23000=-75, sc23400=-150, bc23600=150)
    extra = Position(held.lines + ((FUT, 75),))
    outcome = rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, extra, at(12), "exec-2"))
    assert outcome.kind is OutcomeKind.MISMATCH and rec.actual_position == extra
    assert (FUT, 0, 75) in outcome.differences and rec.active_version.number == 1


def test_partial_with_an_overfilled_leg_is_a_mismatch():
    """AC-4 red: one leg filled 300 against 150 intended under a PARTIAL status is a MISMATCH."""
    rec = pending_two_lots()
    over = broker(bp22800=300, sp23000=-75, sc23400=-150, bc23600=150)
    outcome = rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, over, at(12), "exec-2"))
    assert outcome.kind is OutcomeKind.MISMATCH and rec.actual_position == over


def test_partial_with_a_side_flip_is_a_mismatch():
    """AC-4 red: a leg held on the opposite side of what was asked is a MISMATCH, even on the first execution."""
    rec = record()
    rec.propose_execution(at=at(1))
    rec.confirm(1, at=at(2))
    flipped = broker(bp22800=-75)
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.PARTIAL, flipped, at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.MISMATCH


def test_genuine_partial_stays_partial_and_complete_equal_activates():
    """AC-4: every leg on its intended side and between the previous and intended quantity, no extra contract,
    is PARTIAL; a later COMPLETE equal to the intended position activates."""
    rec = pending_two_lots()
    partial = broker(bp22800=150, sp23000=-75, sc23400=-150, bc23600=75)
    assert rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, partial, at(12), "exec-2")).kind is OutcomeKind.PARTIAL
    full = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150)
    assert rec.apply_result(ExecutionResult(2, ResultStatus.COMPLETE, full, at(13), "exec-2b")).kind is OutcomeKind.ACTIVATED
    assert rec.active_version.number == 2


def test_partial_on_a_reduction_between_previous_and_intended_stays_partial():
    """AC-4: reducing 150 -> 75 per leg, a broker holding 100 on one leg (between the two) is PARTIAL, not MISMATCH."""
    rec = StrategyRecord(scaled(CONDOR, 150), at=T0, clock=clock)
    rec.propose_execution(at=at(1))
    rec.confirm(1, at=at(2))
    two = broker(bp22800=150, sp23000=-150, sc23400=-150, bc23600=150)
    rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, two, at(3), "exec-1"))
    rec.edit(CONDOR, at=at(4))
    rec.confirm(2, at=at(5))
    part = broker(bp22800=100, sp23000=-150, sc23400=-150, bc23600=150)
    assert rec.apply_result(ExecutionResult(2, ResultStatus.PARTIAL, part, at(6), "exec-2")).kind is OutcomeKind.PARTIAL


@pytest.mark.parametrize("strike", [23000.0, D(23000.1), D("23000.001"), D("0"), "23000"])
def test_position_contract_refuses_float_or_sub_paisa_strike(strike):
    """AC-4 red: a broker position's contract strike passes the engine money guard (Decimal, <= 2 dp, > 0)."""
    with pytest.raises(VersionError):
        Position(((("NIFTY", Instrument.PE, strike, EXPIRY), -75),))


def test_position_contract_refuses_bad_underlying_expiry_and_future_strike():
    """AC-4 red: unknown underlying, datetime expiry and a futures contract with a strike are refused."""
    for contract_ in (("BANKNIFTY", Instrument.PE, D("23000"), EXPIRY),
                      ("NIFTY", Instrument.PE, D("23000"), datetime.datetime(2026, 10, 27, 15, 30)),
                      ("NIFTY", Instrument.FUT, D("23000"), EXPIRY)):
        with pytest.raises(VersionError):
            Position(((contract_, 75),))
