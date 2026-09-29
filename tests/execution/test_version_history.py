"""REQ-059 AC-5 (version-history half): an unavailable contract is kept in the version history, the user chooses an
offered alternative explicitly, and that choice becomes an activity-history entry before the first execution or a new
proposed version after it (Q44, Q135, Q190; ADR-019 Q191). Wired to W-012's StrategyRecord; real instrument list."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from execution_inputs import AS_OF, EXPIRY, all_true_context, check, closing_orders, find_token
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import CheckCode, ExecutionAction, VersionState, active_legs_hash
from ofo.execution.alternatives import gate_inputs_from_record, record_alternative_choice
from ofo.instruments import EligibilityStatus
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import (
    ExecutionResult,
    HistoryEntry,
    OutcomeKind,
    Position,
    ResultStatus,
    StrategyRecord,
    Version,
    VersionError,
)

LEGS = (
    DefinitionLeg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 65),
    DefinitionLeg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, 65),
    DefinitionLeg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 65),
    DefinitionLeg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 65),
)
CONDOR = StrategyDefinition("NIFTY", LEGS)


def _at(minutes: int) -> datetime.datetime:
    return AS_OF + datetime.timedelta(minutes=minutes)


def _record() -> StrategyRecord:
    return StrategyRecord(CONDOR, at=AS_OF, clock=lambda: AS_OF + datetime.timedelta(days=1))


def _executed(broker: Position | None = None) -> StrategyRecord:
    rec = _record()
    v1 = rec.propose_execution(at=_at(1))
    rec.confirm(v1.number, at=_at(2))
    rec.apply_result(ExecutionResult(v1.number, ResultStatus.COMPLETE,
                                     broker or Position.of(CONDOR.intended_position()), _at(3), "fill-1", attempt=rec.live_attempt))
    return rec


def _as_engine(definition: StrategyDefinition) -> Strategy:
    return Strategy(tuple(Leg(leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, D("50.00"))
                          for leg in definition.legs))


def _unavailable_report(rec: StrategyRecord, catalogue, eligibility):
    """The gate's report when the sold 23,000 PE is not accepting fresh orders."""
    eligibility.record(EligibilityStatus(find_token(catalogue, "PE", "23000"), False, AS_OF, "OI limit reached"))
    strategy = _as_engine(rec.definition)
    result = check(strategy, all_true_context(), catalogue, eligibility)
    (failure,) = result.failures
    assert failure.code is CheckCode.CONTRACT_NOT_ELIGIBLE and failure.alternatives == (D("22950"), D("23050"))
    return strategy, failure


def test_before_first_execution_choice_is_an_activity_history_entry(catalogue, eligibility):
    """AC-5: before the first execution the explicit choice is a history entry; no version; original kept."""
    rec = _record()
    strategy, failure = _unavailable_report(rec, catalogue, eligibility)
    entry = record_alternative_choice(rec, strategy, failure, D("22950"), at=_at(5), actor="user:U-42")
    assert isinstance(entry, HistoryEntry) and rec.versions == ()
    assert entry.before == CONDOR  # the configuration with the unavailable contract stays in the history
    assert entry.changes == ("removed leg SELL 23000 PE 2026-10-06 x65", "added leg SELL 22950 PE 2026-10-06 x65")
    assert rec.definition.legs[1].strike == D("22950") and rec.history[0].after == CONDOR


def test_after_first_execution_choice_is_a_new_proposed_version(catalogue, eligibility):
    """AC-5 (ADR-019 Q190/Q191): after execution the choice is proposed version v2; v1 stays active and unchanged."""
    rec = _executed()
    v1_before = rec.version(1)
    strategy, failure = _unavailable_report(rec, catalogue, eligibility)
    version = record_alternative_choice(rec, strategy, failure, D("23050"), at=_at(5), actor="user:U-42")
    assert isinstance(version, Version) and version.number == 2 and version.based_on == 1
    assert rec.proposed_version == version and rec.active_version.number == 1
    assert rec.version(1) == v1_before and rec.version(1).definition == CONDOR
    assert version.definition.legs[1].strike == D("23050")
    assert version.initiator == "user:U-42" and "23,000" in version.reason and "23,050" in version.reason


def test_no_choice_records_nothing(catalogue, eligibility):
    """AC-5 (AC-4): reporting an unavailable contract changes nothing in the stored strategy."""
    rec = _executed()
    history, versions, definition = rec.history, rec.versions, rec.definition
    _unavailable_report(rec, catalogue, eligibility)
    assert (rec.history, rec.versions, rec.definition, rec.proposed_version) == (history, versions, definition, None)


def test_choice_refused_while_reconciliation_is_required(catalogue, eligibility):
    """AC-5 (ADR-018): with reconciliation required, W-012 refuses the edit, so the choice is refused."""
    overfilled = Position.of(CONDOR.intended_position() | {("NIFTY", Instrument.PE, D("23000"), EXPIRY): -130})
    rec = _executed(overfilled)
    assert rec.outcomes[-1].kind is OutcomeKind.MISMATCH and rec.reconciliation_required
    strategy, failure = _unavailable_report(rec, catalogue, eligibility)
    with pytest.raises(VersionError, match="reconciliation required"):
        record_alternative_choice(rec, strategy, failure, D("22950"), at=_at(5), actor="user:U-42")
    assert len(rec.versions) == 1


@pytest.mark.parametrize("strike", [D("23000"), D("22900"), D("23450")], ids=["same", "not-offered", "random"])
def test_only_an_offered_alternative_can_be_chosen(strike, catalogue, eligibility):
    """AC-5: the user chooses among the offered alternatives; anything else is refused and nothing is recorded."""
    rec = _record()
    strategy, failure = _unavailable_report(rec, catalogue, eligibility)
    with pytest.raises(ValueError, match="offered"):
        record_alternative_choice(rec, strategy, failure, strike, at=_at(5), actor="user:U-42")
    assert len(rec.history) == 1


def test_only_an_unavailable_contract_report_can_be_answered(condor, catalogue, eligibility):
    """AC-5: a choice answers an unavailable-contract report for a leg of THIS strategy, nothing else."""
    rec = _record()
    closed = check(condor, all_true_context(market_open=False), catalogue, eligibility).failures[0]
    with pytest.raises(ValueError, match="unavailable contract"):
        record_alternative_choice(rec, condor, closed, D("22950"), at=_at(5), actor="user:U-42")
    # A leg-scoped report that is not about availability (a duplicate leg) is refused even if it carried a strike.
    doubled = Strategy(condor.legs + (condor.legs[1],))
    duplicate = check(doubled, all_true_context(), catalogue, eligibility).failures[0]
    assert duplicate.code is CheckCode.DUPLICATE_LEG
    with pytest.raises(ValueError, match="unavailable contract"):
        record_alternative_choice(rec, doubled, dataclasses.replace(duplicate, alternatives=(D("22950"),)),
                                  D("22950"), at=_at(5), actor="user:U-42")
    strategy, failure = _unavailable_report(rec, catalogue, eligibility)
    other = Strategy((Leg(Action.SELL, Instrument.PE, D("22700"), EXPIRY, 65, D("20.00")),) * 1)
    with pytest.raises(ValueError, match="not a leg"):
        record_alternative_choice(rec, other, dataclasses.replace(failure, leg_number=1), D("22950"), at=_at(5),
                                  actor="user:U-42")
    assert len(rec.history) == 1


NEAR = datetime.date(2026, 9, 29)  # real NIFTY future and options expiry in the fixture
COVERED_CALL = StrategyDefinition("NIFTY", (
    DefinitionLeg(Action.BUY, Instrument.FUT, None, NEAR, 65),
    DefinitionLeg(Action.SELL, Instrument.CE, D("23400"), NEAR, 65),
))
FUTURES_REASON = "Entry price of a futures leg is not known yet — adjustment needs Pro until it is."


def _executed_covered_call() -> StrategyRecord:
    rec = StrategyRecord(COVERED_CALL, at=AS_OF, clock=lambda: AS_OF + datetime.timedelta(days=1))
    v1 = rec.propose_execution(at=_at(1))
    rec.confirm(v1.number, at=_at(2))
    rec.apply_result(ExecutionResult(v1.number, ResultStatus.COMPLETE,
                                     Position.of(COVERED_CALL.intended_position()), _at(3), "fill-cc", attempt=rec.live_attempt))
    return rec


CLOSE_SHORT_CE = Strategy((Leg(Action.BUY, Instrument.FUT, None, NEAR, 65, D("23250.00")),))


def _adjust(fields: dict[str, object], pro: bool = False):
    return all_true_context(action=ExecutionAction.ADJUSTMENT, version_state=VersionState.PROPOSED,
                            pro_entitled=pro, **fields)


def test_unknown_futures_entry_price_needs_pro_for_a_limited_adjustment(catalogue, eligibility):
    """AC-1 (orchestrator default, fail closed): the stored version has no futures entry price, so a Limited user's
    adjustment of a strategy with a futures leg needs Pro, with the stated reason; a Pro user passes."""
    fields = gate_inputs_from_record(_executed_covered_call(), strategy_id="S-1")
    assert fields["active_futures_entry_known"] is False
    result = check(CLOSE_SHORT_CE, _adjust(fields), catalogue, eligibility)
    assert [(f.code, f.reason) for f in result.failures] == [(CheckCode.ENTITLEMENT_REQUIRED, FUTURES_REASON)]
    assert check(CLOSE_SHORT_CE, _adjust(fields, pro=True), catalogue, eligibility).failures == ()


def test_known_futures_entry_price_lets_rule_5_decide(catalogue, eligibility):
    """AC-1: when the caller supplies the futures entry price, rule 5 applies normally (closing the short call of a
    covered call is allowed for a Limited user)."""
    fields = gate_inputs_from_record(_executed_covered_call(), strategy_id="S-1",
                                     futures_entry_prices={NEAR: D("23250.00")})
    assert fields["active_futures_entry_known"] is True
    assert check(CLOSE_SHORT_CE, _adjust(fields), catalogue, eligibility).failures == ()


def test_unknown_futures_entry_price_does_not_affect_an_exit(catalogue, eligibility):
    """AC-1: an exit needs no prices - the reduce-only check passes with the entry unknown."""
    fields = gate_inputs_from_record(_executed_covered_call(), strategy_id="S-1")
    ctx = all_true_context(action=ExecutionAction.EXIT, pro_entitled=False, **fields)
    assert check(Strategy(closing_orders(fields["active_legs"])), ctx, catalogue, eligibility).failures == ()


def test_gate_inputs_come_from_the_active_version(catalogue, eligibility):
    """AC-5 / round 2 MAJOR A: the active legs, version id and hash are built from the stored active version, and
    an exit of that version passes the gate."""
    rec = _executed()
    fields = gate_inputs_from_record(rec, strategy_id="S-1")
    assert fields["active_version_id"] == "v1"
    assert fields["active_legs_hash"] == active_legs_hash("S-1", "v1", fields["active_legs"])
    ctx = all_true_context(action=ExecutionAction.EXIT, **fields)
    result = check(Strategy(closing_orders(fields["active_legs"])), ctx, catalogue, eligibility)
    assert result.failures == ()
    assert fields["active_futures_entry_known"] is True  # no futures leg: nothing unknown
    assert gate_inputs_from_record(_record(), strategy_id="S-1") == {
        "active_legs": None, "active_version_id": None, "active_legs_hash": None,
        "active_futures_entry_known": None}
