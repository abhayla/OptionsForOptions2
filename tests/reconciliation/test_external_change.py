"""REQ-060 AC-4: changes made directly in Zerodha are detected, recorded, and put the strategy into Reconciliation
Required (ADR-018 Q197: strategy says Sell 25,000 CE x 50, Zerodha shows x 25)."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from ofo.audit.catalogue import EventType
from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import MismatchKind, ReconciliationError, compare, unexplained_changes
from ofo.reconciliation.resolution import record_report
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import OutcomeKind, Position, VersionError
from recon_fixtures import CONDOR, CONDOR_UNITS, EXPIRY, SC23400, at, audit_log, clock, executed

CE25000 = ("NIFTY", Instrument.CE, D("25000"), EXPIRY)
Q197 = StrategyDefinition("NIFTY", (DefinitionLeg(Action.SELL, Instrument.CE, D("25000"), EXPIRY, 50),))


def test_ac4_q197_change_in_zerodha_detected_recorded_and_blocks():
    """AC-4: the Q197 example. Last snapshot -50, now -25, no platform fill -> external change of +25."""
    rec = executed(Q197)
    changes = unexplained_changes({CE25000: -50}, {CE25000: -25}, {})
    assert changes == {CE25000: 25}
    report = compare({CE25000: -25}, {"Q197": rec}, at=at(10), external=changes, clock=clock)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.EXTERNAL_MODIFICATION
    assert (m.broker_state, m.platform_state, m.difference) == (((CE25000, -25),), ((CE25000, -50),), ((CE25000, 25),))
    audit = audit_log()
    (outcome,) = record_report(report, {"Q197": rec}, audit=audit, run_id="run-1")
    assert rec.reconciliation_required                                   # Reconciliation Required
    assert outcome.kind is OutcomeKind.OBSERVED and outcome.actual == Position.of({CE25000: -25})
    assert rec.actual_position == Position.of({CE25000: -25})            # the broker wins
    (event,) = audit.events
    assert event.event_type is EventType.EXTERNAL_BROKER_CHANGE_DETECTED
    assert event.payload["difference"] == (("NIFTY 25000 CE 2026-10-27", 25),)  # the audit log freezes lists
    with pytest.raises(VersionError):                                    # execution refused while flagged
        rec.edit(CONDOR, at=at(11))


def _two_strategies():
    from recon_fixtures import SC23400 as _sc  # noqa: F401 - same fixtures module
    ic = executed()
    q197 = executed(Q197, "exec-q197")
    return ic, q197


def test_ac4_recording_is_all_or_nothing_when_a_later_strategy_refuses():
    """AC-4 fix round 2 (verifier attack): the run is computed at 10:00; strategy Q197 then records an event at
    10:02, so it refuses the 10:00 run. Nothing may change: IC-1 not flagged, no picture refreshed, no audit
    event, no reference kept. A retry of the same run id on a fresh run then succeeds and writes the audit."""
    ic, q197 = _two_strategies()
    broker = dict(CONDOR_UNITS) | {SC23400: -25, CE25000: -50}
    report = compare(broker, {"IC-1": ic, "Q197": q197}, at=at(10), clock=clock)
    assert report.blocked_strategy_ids == frozenset({"IC-1"})
    q197.observe_broker_position(Position.of({CE25000: -50}), at=at(12), reference="later")
    audit = audit_log()
    before = (ic.actual_position, ic.last_observed_at, len(ic.outcomes), q197.actual_position, len(q197.outcomes))
    with pytest.raises(ReconciliationError):
        record_report(report, {"IC-1": ic, "Q197": q197}, audit=audit, run_id="runP")
    assert not ic.reconciliation_required and audit.events == ()
    assert (ic.actual_position, ic.last_observed_at, len(ic.outcomes), q197.actual_position,
            len(q197.outcomes)) == before
    retry = compare(broker, {"IC-1": ic, "Q197": q197}, at=at(13), clock=clock)
    record_report(retry, {"IC-1": ic, "Q197": q197}, audit=audit, run_id="runP")       # same run id: allowed
    assert ic.reconciliation_required and len(audit.events) == 1
    assert audit.events[0].payload["strategy_ids"] == ("IC-1",)


def test_ac4_recording_is_all_or_nothing_when_an_outcome_log_is_full(monkeypatch):
    """AC-4 fix round 2: the second failure mode, a full outcome log on a later strategy, changes nothing either."""
    import ofo.strategy.versions as versions
    ic, q197 = _two_strategies()
    broker = dict(CONDOR_UNITS) | {SC23400: -25, CE25000: -50}
    q197.observe_broker_position(Position.of({CE25000: -25}), at=at(5), reference="earlier")   # one more outcome
    report = compare(broker, {"IC-1": ic, "Q197": q197}, at=at(10), clock=clock)
    assert (len(ic.outcomes), len(q197.outcomes)) == (1, 2)
    monkeypatch.setattr(versions, "MAX_OUTCOMES", 2)       # IC-1 (sorted first) has room; Q197 is at capacity
    audit = audit_log()
    with pytest.raises(ReconciliationError):
        record_report(report, {"IC-1": ic, "Q197": q197}, audit=audit, run_id="runF")
    assert not ic.reconciliation_required and ic.last_observed_at is None and audit.events == ()


def test_ac4_platform_fill_is_not_an_external_change():
    """AC-4 (negative): the same broker move explained by the platform's own fill is not external."""
    assert unexplained_changes({CE25000: -50}, {CE25000: -25}, {CE25000: 25}) == {}
    assert unexplained_changes({CE25000: -50}, {CE25000: -25}, {CE25000: 10}) == {CE25000: 15}


def test_ac4_agreeing_run_changes_nothing_and_never_clears_the_flag():
    """AC-4: a run with no mismatch records nothing; once flagged, agreement alone does not unblock."""
    rec = executed()
    audit = audit_log()
    report = compare(dict(CONDOR_UNITS), {"IC-1": rec}, at=at(10), clock=clock)
    assert record_report(report, {"IC-1": rec}, audit=audit, run_id="r1") == () and audit.events == ()
    bad = compare(dict(CONDOR_UNITS) | {SC23400: -25}, {"IC-1": rec}, at=at(11), clock=clock)
    record_report(bad, {"IC-1": rec}, audit=audit, run_id="r2")
    assert rec.reconciliation_required
    good = compare(dict(CONDOR_UNITS), {"IC-1": rec}, at=at(12), clock=clock)
    record_report(good, {"IC-1": rec}, audit=audit, run_id="r3")
    assert rec.reconciliation_required                      # sticky until an explicit resolution


def test_ac4_record_report_refuses_bad_input():
    """AC-4 (input domain): unknown strategy, replayed run id, wrong types -> refused."""
    rec = executed()
    report = compare(dict(CONDOR_UNITS) | {SC23400: -25}, {"IC-1": rec}, at=at(10), clock=clock)
    audit = audit_log()
    with pytest.raises(ReconciliationError):
        record_report(report, {}, audit=audit, run_id="r1")
    with pytest.raises(ReconciliationError):
        record_report(report, {"IC-1": rec}, audit=[], run_id="r1")
    with pytest.raises(ReconciliationError):
        record_report(report, {"IC-1": rec}, audit=audit, run_id="")
    record_report(report, {"IC-1": rec}, audit=audit, run_id="r1")
    with pytest.raises(ReconciliationError):                 # the same run applied twice
        record_report(compare(dict(CONDOR_UNITS) | {SC23400: 0}, {"IC-1": rec}, at=at(11), clock=clock),
                      {"IC-1": rec}, audit=audit, run_id="r1")


def test_ac4_observation_rejects_backdated_and_raw_state_change():
    """AC-4 (input domain): a backdated observation is refused; the flag cannot be set by assignment."""
    rec = executed()
    with pytest.raises(VersionError):
        rec.observe_broker_position(Position(), at=at(0), reference="old")
    with pytest.raises(VersionError):
        rec.observe_broker_position({SC23400: -75}, at=at(5), reference="dict")
    with pytest.raises(AttributeError):
        rec._reconcile = True  # noqa: SLF001 - the raw state change must be impossible
