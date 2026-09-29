"""REQ-037 AC-1, AC-4, AC-5: strategy modification (roll a leg on the golden Iron Condor).

AC-2 (the recalculated Before/After metrics) is tests/strategy/test_modification_metrics.py, per work/W-027.md's
tests_required. This file covers: AC-1 (a leg change is impossible without an active-version slot), AC-4 (nothing
is prepared/executed before confirmation and the REQ-059 gate, which THIS module runs itself), AC-5 (every
modification creates a new version; old versions are kept, unchanged, active, until execution).

Fix round (verifier finding): ``execute_confirmed_modification`` used to trust a caller-supplied ``SafetyResult``
and check only ``.blocked`` -- a hand-built always-passing result activated v2 with no real gate ever run. Class:
any step that accepts a caller-supplied verdict object as proof a check ran (same shape as W-020's caller-supplied
version and W-014's active-legs hash). Fix: the modification flow calls ``check_pre_execution`` itself, on the
record's own pending proposal, grounding ``strategy_id``/active-leg identity from the record
(``gate_inputs_from_record``); no public function here takes a ``SafetyResult`` as input.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D
from unittest import mock

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.execution import (
    CheckCode,
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    VersionState,
    active_legs_hash,
)
from ofo.instruments import Catalogue, EligibilityRegistry, EligibilityStatus
from ofo.instruments.models import Contract
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.modification import (
    ChangeKind,
    LegChange,
    ModificationError,
    apply_changes,
    confirm_modification,
    execute_confirmed_modification,
    prepare_confirmed_modification,
    propose_modification,
)
from ofo.engine.interfaces import ChargesBreakdown, MarginRequirement
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
STRATEGY_ID = "S-1"

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


class _Margin:
    def margin_for(self, strategy: Strategy) -> MarginRequirement:
        return MarginRequirement(total=D("50000.00"), source="test")


class _Charges:
    def charges_for(self, strategy: Strategy) -> ChargesBreakdown:
        return ChargesBreakdown(items=(("brokerage", D("236.40")),))


_PRICES = {(leg.instrument, leg.strike, leg.expiry): leg.entry_price for leg in GOLDEN.legs}
_PRICES[(Instrument.PE, D("22900"), EXPIRY)] = D("70.00")


def roll_ack(rec: StrategyRecord) -> str:
    """W-026 (REQ-036 AC-5): the Before/After step runs the Strategy Guard; the roll changes the risk profile, so the
    gate step needs that decision's own acknowledgement."""
    decision = propose_modification(rec, ROLL, strategy_id=STRATEGY_ID, entry_prices=_PRICES, ltps=None,
                                    margin_planner=_Margin(), charges_model=_Charges()).guard
    assert decision.changes_risk_profile and decision.acknowledgement
    return decision.acknowledgement


def at(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def clock() -> datetime.datetime:
    return T0 + datetime.timedelta(days=10)


def contract_tuple(instrument: Instrument, strike: str) -> tuple:
    return ("NIFTY", instrument, D(strike), EXPIRY)


FILLED = Position((
    (contract_tuple(Instrument.PE, "22800"), QTY),
    (contract_tuple(Instrument.PE, "23000"), -QTY),
    (contract_tuple(Instrument.CE, "23400"), -QTY),
    (contract_tuple(Instrument.CE, "23600"), QTY),
))

ROLLED_FILLED = Position((
    (contract_tuple(Instrument.PE, "22800"), QTY),
    (contract_tuple(Instrument.PE, "22900"), -QTY),
    (contract_tuple(Instrument.CE, "23400"), -QTY),
    (contract_tuple(Instrument.CE, "23600"), QTY),
))


def executed_record() -> StrategyRecord:
    """A StrategyRecord whose v1 (the golden condor) is active, as W-012's own core proof builds one."""
    rec = StrategyRecord(CONDOR, at=T0, clock=clock)
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    outcome = rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, FILLED, at(3), "exec-1"))
    assert outcome.kind is OutcomeKind.ACTIVATED
    return rec


_STRIKES = {
    (Instrument.PE, "22800"): 900001, (Instrument.PE, "22900"): 900002, (Instrument.PE, "23000"): 900003,
    (Instrument.CE, "23400"): 900004, (Instrument.CE, "23600"): 900005,
}


def _make_catalogue(*, missing: frozenset[tuple[Instrument, str]] = frozenset()) -> Catalogue:
    """The real Zerodha-shaped catalogue for every leg the roll touches, minus ``missing`` (to force a gate block)."""
    cat = Catalogue()
    contracts = [
        Contract(
            instrument_token=token, exchange_token=token, tradingsymbol=f"NIFTY{strike}{instrument.value}",
            name="NIFTY", expiry=EXPIRY, strike=D(strike), tick_size=D("0.05"), lot_size=QTY,
            instrument_type=instrument.value, segment="NFO-OPT", exchange="NFO",
        )
        for (instrument, strike), token in _STRIKES.items() if (instrument, strike) not in missing
    ]
    cat.load(contracts)
    return cat


def _make_eligibility(catalogue: Catalogue) -> EligibilityRegistry:
    registry = EligibilityRegistry()
    for entry in catalogue.all_entries():
        registry.record(EligibilityStatus(entry.contract.instrument_token, True, T0))
    return registry


def _context(version_number: int, **overrides) -> ExecutionContext:
    base = ExecutionContext(
        strategy_id=STRATEGY_ID, version_id=f"v{version_number}", actor="user:U-1", underlying="NIFTY",
        action=ExecutionAction.ADJUSTMENT, as_of=at(20), market_open=True, broker_connected=True,
        session_valid=True, pro_entitled=True, version_state=VersionState.PROPOSED, rules_valid=True,
        dependencies_satisfied=True, data_health={d: DataHealth.HEALTHY for d in DataInput},
        margin_available=D("500000.00"), margin_required=D("50000.00"),
        reconciliation_blocked_strategy_ids=frozenset(), charges_estimate=D("236.40"),
    )
    return dataclasses.replace(base, **overrides)


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


def test_ac4_nothing_prepared_before_confirmation():
    """AC-4: an order is never prepared/executed for a roll that was never confirmed."""
    rec = executed_record()
    catalogue = _make_catalogue()
    eligibility = _make_eligibility(catalogue)
    premature = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(10), "premature")
    with pytest.raises(ModificationError):
        execute_confirmed_modification(
            rec, 2, strategy_id=STRATEGY_ID, context=_context(2), catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
            result=premature,
        )
    assert rec.active_version.number == 1
    assert len(rec.versions) == 1


def test_ac4_forged_safety_result_is_impossible_via_the_api():
    """Fix-round regression: the old API accepted a caller-built ``SafetyResult`` as proof a check ran. The new
    function signature has no such parameter at all, so a forged "always passes" verdict cannot be handed in."""
    import inspect
    params = inspect.signature(execute_confirmed_modification).parameters
    assert "safety" not in params
    assert set(params) == {"record", "version_number", "strategy_id", "context", "catalogue", "eligibility", "result",
                           "acknowledgement"}  # W-026: the guard's own token, never a verdict
    with pytest.raises(TypeError):
        execute_confirmed_modification(safety="forged", result=None)  # not an accepted keyword at all


def test_ac4_gate_is_actually_run_a_missing_contract_blocks_and_leaves_v1_active():
    """The gate is REAL: a catalogue missing the rolled-to contract blocks execution (CONTRACT_NOT_FOUND), and the
    block leaves the active version exactly as it was."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    catalogue = _make_catalogue(missing=frozenset({(Instrument.PE, "22900")}))
    eligibility = _make_eligibility(catalogue)
    result = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(11), "adj-blocked")

    safety = prepare_confirmed_modification(
        rec, 2, strategy_id=STRATEGY_ID, context=_context(2), catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
    )
    assert safety.blocked  # the gate really ran and really found the missing contract

    with pytest.raises(ModificationError):
        execute_confirmed_modification(
            rec, 2, strategy_id=STRATEGY_ID, context=_context(2), catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
            result=result,
        )
    assert rec.active_version.number == 1
    assert rec.proposed_version.number == 2  # still pending: the blocked attempt was never applied
    assert rec.version(1).definition == CONDOR


def test_ac4_gate_passing_activates_v2_and_runs_exactly_once():
    """AC-4/AC-5: with every contract listed and eligible, the real gate passes and the confirmed proposal
    activates; the gate (``check_pre_execution``) is called exactly once for this one execution."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    catalogue = _make_catalogue()
    eligibility = _make_eligibility(catalogue)
    result = ExecutionResult(2, ResultStatus.COMPLETE, ROLLED_FILLED, at(12), "adj-1")

    with mock.patch(
        "ofo.strategy.modification.check_pre_execution", wraps=__import__(
            "ofo.execution.safety", fromlist=["check_pre_execution"]
        ).check_pre_execution,
    ) as spy:
        outcome = execute_confirmed_modification(
            rec, 2, strategy_id=STRATEGY_ID, context=_context(2), catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
            result=result,
        )
        assert spy.call_count == 1

    assert outcome.kind is OutcomeKind.ACTIVATED
    assert rec.active_version.number == 2
    assert rec.version(1).definition == CONDOR  # AC-5: v1 is kept, unchanged


def test_ac4_a_result_for_another_version_cannot_be_injected():
    """A caller cannot execute a version that is not this record's own pending proposal -- there is no argument
    that lets a different strategy's or version's verdict stand in for this record's own gate run."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))  # v2 pending
    catalogue = _make_catalogue()
    eligibility = _make_eligibility(catalogue)
    with pytest.raises(ModificationError):
        prepare_confirmed_modification(
            rec, 99, strategy_id=STRATEGY_ID, context=_context(99), catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
        )
    assert rec.active_version.number == 1
    assert rec.proposed_version.number == 2


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
        (contract_tuple(Instrument.PE, "22800"), 10 * QTY),  # far outside 75..75 for this untouched leg -> MISMATCH
        (contract_tuple(Instrument.PE, "23000"), -QTY),
        (contract_tuple(Instrument.CE, "23400"), -QTY),
        (contract_tuple(Instrument.CE, "23600"), 2 * QTY),
    ))
    outcome = rec.apply_result(ExecutionResult(v2.number, ResultStatus.COMPLETE, mismatched, at(12), "mismatch-1"))
    assert outcome.kind is OutcomeKind.MISMATCH
    assert rec.reconciliation_required

    with pytest.raises(VersionError):
        confirm_modification(rec, ROLL, at=at(13))


def test_ac4_context_active_legs_identity_is_grounded_from_the_record_not_the_caller():
    """Regression (2nd fix round): prepare_confirmed_modification must overwrite strategy_id and the active-leg
    identity fields (active_legs/active_version_id/active_legs_hash) from the record itself, never trust the
    caller's context for them. Exploit: a forged context claims the ACTIVE legs already equal the PROPOSED
    (rolled) legs, with a self-consistent hash and pro_entitled=False -- faking a pure reduction to dodge Pro
    entitlement. With the real (pre-roll) active legs correctly substituted in, the reduction claim is false and
    the gate still blocks with ENTITLEMENT_REQUIRED."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    catalogue = _make_catalogue()
    eligibility = _make_eligibility(catalogue)

    proposed_def = rec.proposed_version.definition
    forged_active_legs = tuple(
        Leg(d.action, d.instrument, d.strike, d.expiry, d.quantity, D("0.00")) for d in proposed_def.legs
    )
    forged_version_id = "v1"
    forged_hash = active_legs_hash(STRATEGY_ID, forged_version_id, forged_active_legs)
    forged_context = _context(
        2, pro_entitled=False, active_legs=forged_active_legs, active_version_id=forged_version_id,
        active_legs_hash=forged_hash, active_futures_entry_known=True,
    )

    safety = prepare_confirmed_modification(
        rec, 2, strategy_id=STRATEGY_ID, context=forged_context, catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
    )
    assert safety.blocked
    assert CheckCode.ENTITLEMENT_REQUIRED in safety.failed_codes


def test_ac4_context_strategy_id_is_ignored_grounded_from_the_call():
    """Regression: a context naming a DIFFERENT strategy_id is ignored -- the gate always runs for the strategy_id
    this call actually names, never whatever the caller's context happened to carry."""
    rec = executed_record()
    confirm_modification(rec, ROLL, at=at(10))
    catalogue = _make_catalogue()
    eligibility = _make_eligibility(catalogue)
    forged_context = _context(2, strategy_id="S-OTHER")

    safety = prepare_confirmed_modification(
        rec, 2, strategy_id=STRATEGY_ID, context=forged_context, catalogue=catalogue, eligibility=eligibility, acknowledgement=roll_ack(rec),
    )
    assert not safety.blocked
    assert CheckCode.STRATEGY_MISMATCH not in safety.failed_codes
