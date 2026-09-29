"""REQ-060 AC-5: manual reconciliation is allowed, explicit and audited (ADR-018 Q198: adopt actual broker position,
close/reconcile through a prepared order, mark as requiring attention; no casual ignore), plus broker flat ->
strategy Exited (ADR-019 Q200; deferred issue #19)."""
from __future__ import annotations

import pytest

from ofo.audit.catalogue import EventType
from ofo.engine import Action
from ofo.reconciliation.blocking import blocked_strategy_ids
from ofo.reconciliation.compare import ReconciliationError, compare
from ofo.reconciliation.resolution import (
    ClosingTarget,
    ProposedOrder,
    ResolutionKind,
    adopt_broker_position,
    mark_exited_broker_flat,
    mark_requires_attention,
    prepare_closing_order,
    record_report,
    review_and_modify,
)
from ofo.strategy.versions import OutcomeKind, Position, VersionError
from recon_fixtures import BC23600, BP22800, CONDOR, CONDOR_UNITS, SC23400, SP23000, at, audit_log, clock, executed

# The user closed the 23600 CE hedge in Kite: broker = condor without it.
HEDGE_CLOSED = {BP22800: 75, SP23000: -75, SC23400: -75}


def flagged(broker=None):
    rec = executed()
    audit = audit_log()
    report = compare(HEDGE_CLOSED if broker is None else broker, {"IC-1": rec}, at=at(10), clock=clock)
    record_report(report, {"IC-1": rec}, audit=audit, run_id="run-1")
    assert rec.reconciliation_required
    return rec, audit, len(audit.events), report


def test_ac5_adopt_broker_position_audited_and_unblocks():
    """AC-5: adopt -> new active version = broker position; audited with actor, time, reason, before/after."""
    rec, audit, n, report = flagged()
    res = adopt_broker_position("IC-1", rec, report=report, actor="user:abhay", at=at(20), reason="I closed the hedge in Kite",
                                audit=audit)
    assert res.kind is ResolutionKind.ADOPT_BROKER_POSITION and not res.still_blocked
    assert res.before_platform == Position.of(CONDOR_UNITS) and res.before_broker == Position.of(HEDGE_CLOSED)
    assert res.after_platform == Position.of(HEDGE_CLOSED)
    assert rec.active_version.number == 2 and rec.outcomes[-1].kind is OutcomeKind.RECONCILED
    event = audit.events[n]
    assert (event.event_type, event.actor, event.timestamp) == (EventType.RECONCILIATION_RECORDED, "user:abhay", at(20))
    assert event.payload["resolution"] == "adopt actual broker position"
    assert event.payload["reason"] == "I closed the hedge in Kite"
    # Lines are in contract order (underlying, instrument CE before PE, strike); the audit log freezes lists.
    assert event.payload["before_platform"] == (("NIFTY 23400 CE 2026-10-27", -75), ("NIFTY 23600 CE 2026-10-27", 75),
                                                ("NIFTY 22800 PE 2026-10-27", 75), ("NIFTY 23000 PE 2026-10-27", -75))
    assert event.payload["after_platform"] == (("NIFTY 23400 CE 2026-10-27", -75), ("NIFTY 22800 PE 2026-10-27", 75),
                                               ("NIFTY 23000 PE 2026-10-27", -75))
    assert audit.verify().ok
    # The next run agrees with the new active version -> nothing blocked.
    after = compare(HEDGE_CLOSED, {"IC-1": rec}, at=at(21), clock=clock)
    assert after.mismatches == () and blocked_strategy_ids(after, {"IC-1": rec}) == frozenset()


def test_ac5_prepared_order_is_a_proposal_and_keeps_the_block():
    """AC-5: prepared orders (restore the hedge, or close all) are proposals; the strategy stays blocked."""
    rec, audit, n, report = flagged()
    res = prepare_closing_order("IC-1", rec, report=report, actor="user", at=at(20), reason="restore hedge", audit=audit)
    assert res.proposal.orders == (ProposedOrder(Action.BUY, BC23600, 75),)          # 75 - 0
    assert res.still_blocked and rec.reconciliation_required
    flat = prepare_closing_order("IC-1", rec, report=report, actor="user", at=at(21), reason="close all", audit=audit,
                                 target=ClosingTarget.FLAT)
    # Closing each broker line: -75 short call -> BUY 75; +75 long put -> SELL 75; -75 short put -> BUY 75.
    assert flat.proposal.orders == (ProposedOrder(Action.BUY, SC23400, 75), ProposedOrder(Action.SELL, BP22800, 75),
                                    ProposedOrder(Action.BUY, SP23000, 75))
    assert audit.events[n].payload["prepared_orders"] == (("BUY", "NIFTY 23600 CE 2026-10-27", 75),)
    assert rec.versions[-1].number == 1                     # nothing placed, no version, nothing changed


def test_ac5_mark_requires_attention_keeps_block_and_is_audited():
    """AC-5: marked as requiring attention -> audited, still blocked."""
    rec, audit, n, report = flagged()
    res = mark_requires_attention("IC-1", rec, report=report, actor="user", at=at(20), reason="checking with Zerodha", audit=audit)
    assert res.still_blocked and rec.reconciliation_required
    assert audit.events[n].payload["resolution"] == "mark as requiring attention"


def test_ac5_broker_flat_exits_the_strategy_issue_19():
    """AC-5 / issue #19: everything closed in Kite -> adopt is refused, exit is allowed, the block is gone."""
    rec, audit, n, report = flagged(broker={})
    with pytest.raises(ReconciliationError):
        adopt_broker_position("IC-1", rec, report=report, actor="user", at=at(20), reason="adopt", audit=audit)
    res = mark_exited_broker_flat("IC-1", rec, report=report, actor="user", at=at(21), reason="closed all in Kite", audit=audit)
    assert res.kind is ResolutionKind.BROKER_FLAT_EXITED and rec.exited and not rec.reconciliation_required
    assert res.after_platform == Position() and audit.events[-1].payload["exited"] is True
    assert blocked_strategy_ids(None, {"IC-1": rec}) == frozenset()
    with pytest.raises(VersionError):
        rec.edit(CONDOR, at=at(22))
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report=report, actor="user", at=at(23), reason="again", audit=audit)


def test_ac5_exited_record_refuses_every_later_change():
    """AC-5 (versions.py support): once exited, results, confirmations, observations and reconciles are refused;
    exit is refused for a never-executed record and while a proposal is in flight."""
    from ofo.strategy.versions import ExecutionResult, ResultStatus, StrategyRecord
    from recon_fixtures import T0, scaled
    rec, audit, _, report = flagged(broker={})
    rec.mark_exited(at=at(20), actor="user", resolution="flat in Kite")
    for attempt in (
        lambda: rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, Position(), at(21), "late")),
        lambda: rec.confirm(1, at=at(21)),
        lambda: rec.observe_broker_position(Position.of({SC23400: -75}), at=at(21), reference="again"),
        lambda: rec.reconcile(at=at(21), actor="user", resolution="x"),
        lambda: rec.mark_exited(at=at(21), actor="user", resolution="twice"),
        lambda: rec.propose_execution(at=at(21)),
    ):
        with pytest.raises(VersionError):
            attempt()
    fresh = StrategyRecord(CONDOR, at=T0, clock=clock)
    with pytest.raises(VersionError):
        fresh.mark_exited(at=at(1), actor="user", resolution="never traded")
    in_flight = executed()
    in_flight.edit(scaled(CONDOR, 150), at=at(4))
    in_flight.observe_broker_position(Position(), at=at(5), reference="flat")
    with pytest.raises(VersionError):
        in_flight.mark_exited(at=at(6), actor="user", resolution="flat with a proposal pending")


def test_ac5_exit_refused_while_the_broker_still_holds_a_position():
    """AC-5 (negative): broker not flat -> exit refused, strategy still blocked."""
    rec, audit, _, report = flagged()
    with pytest.raises(ReconciliationError):
        mark_exited_broker_flat("IC-1", rec, report=report, actor="user", at=at(20), reason="exit", audit=audit)
    assert not rec.exited and rec.reconciliation_required


@pytest.mark.parametrize("field, value", [("actor", ""), ("reason", ""), ("reason", "   "), ("reason", "x" * 201),
                                          ("actor", None)])
def test_ac5_no_casual_ignore_actor_and_reason_required(field, value):
    """AC-5 (negative): every resolution needs a named actor and a real reason."""
    rec, audit, n, report = flagged()
    kwargs = dict(report=report, actor="user", at=at(20), reason="why", audit=audit) | {field: value}
    for resolve in (adopt_broker_position, prepare_closing_order, mark_requires_attention):
        with pytest.raises(ReconciliationError):
            resolve("IC-1", rec, **kwargs)
    assert len(audit.events) == n and rec.reconciliation_required


def test_ac5_resolution_refused_when_nothing_to_reconcile_or_backdated():
    """AC-5 (negative): no mismatch -> refused; a backdated resolution -> refused by the record's clock order."""
    rec = executed()
    agree = compare(dict(CONDOR_UNITS), {"IC-1": rec}, at=at(10), clock=clock)
    record_report(agree, {"IC-1": rec}, audit=audit_log(), run_id="agree")
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report=agree, actor="user", at=at(20), reason="why", audit=audit_log())
    rec2, audit, _, report = flagged()
    with pytest.raises(ReconciliationError):
        adopt_broker_position("IC-1", rec2, report=report, actor="user", at=at(0), reason="why", audit=audit)
    assert rec2.reconciliation_required


# ---- W-021 fix round: a resolution's premise comes from the latest run, never a stale stored copy ---------------

def _run(rec, broker, minute, run_id, audit):
    report = compare(broker, {"IC-1": rec}, at=at(minute), clock=clock)
    record_report(report, {"IC-1": rec}, audit=audit, run_id=run_id)
    return report


def test_ac5_attack1_exit_refused_after_a_later_run_sees_the_condor_again():
    """AC-5 verifier attack 1: run 1 sees the broker flat, run 2 sees the full condor (0 mismatches). Exit must be
    refused with either report: the latest shows 4 contracts, and the older one is no longer the latest."""
    rec, audit = executed(), audit_log()
    run1 = _run(rec, {}, 10, "run-1", audit)
    run2 = _run(rec, dict(CONDOR_UNITS), 11, "run-2", audit)
    assert run2.mismatches == () and rec.actual_position == Position.of(CONDOR_UNITS)   # refreshed though agreeing
    for report in (run2, run1):
        with pytest.raises(ReconciliationError):
            mark_exited_broker_flat("IC-1", rec, report=report, actor="user", at=at(20), reason="exit", audit=audit)
    assert not rec.exited and rec.reconciliation_required


def test_ac5_attack2_adopt_uses_the_latest_run_not_a_stale_copy():
    """AC-5 verifier attack 2: run 1 sees the short put at -50, run 2 sees -75 (agrees). Adopting on run 1 is
    refused; adopting on run 2 adopts -75 (the condor), never the stale -50."""
    rec, audit = executed(), audit_log()
    run1 = _run(rec, dict(CONDOR_UNITS) | {SP23000: -50}, 10, "run-1", audit)
    run2 = _run(rec, dict(CONDOR_UNITS), 11, "run-2", audit)
    with pytest.raises(ReconciliationError):
        adopt_broker_position("IC-1", rec, report=run1, actor="user", at=at(20), reason="adopt", audit=audit)
    res = adopt_broker_position("IC-1", rec, report=run2, actor="user", at=at(20), reason="adopt", audit=audit)
    assert rec.active_version.intended_position == Position.of(CONDOR_UNITS)          # -75, not -50
    assert res.before_broker == Position.of(CONDOR_UNITS) and not rec.reconciliation_required


def test_ac5_unrecorded_or_superseded_report_is_refused():
    """AC-5 (negative): a report never recorded, a resolution timed before its run, or a non-report -> refused."""
    rec, audit, _, report = flagged()
    later = compare(HEDGE_CLOSED, {"IC-1": rec}, at=at(12), clock=clock)                # compared, not recorded
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report=later, actor="user", at=at(20), reason="why", audit=audit)
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report=report, actor="user", at=at(9), reason="before the run",
                                audit=audit)
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report="latest", actor="user", at=at(20), reason="why", audit=audit)


def test_ac5_same_time_report_from_another_account_is_refused():
    """AC-5 guard M3: a report with the SAME timestamp as the recorded run but a different broker picture (another
    account's positions) passes the time checks; the share check must still refuse it."""
    rec, audit, n, report = flagged()
    other_account = compare({}, {"IC-1": rec}, at=report.at, clock=clock)            # flat, same 10:00 stamp
    assert other_account.at == report.at and other_account.share("IC-1") != report.share("IC-1")
    for resolve in (adopt_broker_position, prepare_closing_order, mark_requires_attention, mark_exited_broker_flat):
        with pytest.raises(ReconciliationError):
            resolve("IC-1", rec, report=other_account, actor="user", at=at(20), reason="why", audit=audit)
    assert not rec.exited and rec.reconciliation_required and len(audit.events) == n


def test_ac5_resolution_after_a_new_fill_waits_for_a_fresh_run():
    """AC-5 guard M5: an execution result after the recorded run resets the observation, so a resolution on that
    run is refused until a fresh run is recorded."""
    from ofo.strategy.versions import ExecutionResult, ResultStatus
    rec, audit, n, report = flagged()
    rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, Position.of(HEDGE_CLOSED), at(15), "late-fill"))
    assert rec.last_observed_at is None
    with pytest.raises(ReconciliationError):
        mark_requires_attention("IC-1", rec, report=report, actor="user", at=at(20), reason="why", audit=audit)
    fresh = compare(HEDGE_CLOSED, {"IC-1": rec}, at=at(16), clock=clock)
    record_report(fresh, {"IC-1": rec}, audit=audit, run_id="run-2")
    res = mark_requires_attention("IC-1", rec, report=fresh, actor="user", at=at(20), reason="why", audit=audit)
    assert res.still_blocked


def test_ac5_review_and_modify_is_recorded_and_keeps_the_block():
    """AC-5 (ADR-018 Q198 "Review and modify strategy"): the choice is audited, hands off to W-027, stays blocked."""
    rec, audit, n, report = flagged()
    res = review_and_modify("IC-1", rec, report=report, actor="user", at=at(20), reason="rebuild hedge",
                            audit=audit)
    assert res.kind is ResolutionKind.REVIEW_AND_MODIFY and res.still_blocked and rec.reconciliation_required
    assert audit.events[n].payload["resolution"] == "review and modify strategy"
    assert len(rec.versions) == 1                                                      # no modification built


def test_ac5_mutant_refreshing_only_blocked_strategies_is_caught(monkeypatch):
    """AC-5 mutation: the round-1 behaviour (refresh only blocked strategies) lets attack 1 through."""
    from ofo.reconciliation.compare import ReconciliationReport
    monkeypatch.setattr(ReconciliationReport, "covered_strategy_ids",
                        property(lambda self: self.blocked_strategy_ids))
    rec, audit = executed(), audit_log()
    run1 = _run(rec, {}, 10, "run-1", audit)
    _run(rec, dict(CONDOR_UNITS), 11, "run-2", audit)
    res = mark_exited_broker_flat("IC-1", rec, report=run1, actor="user", at=at(20), reason="exit", audit=audit)
    assert res.kind is ResolutionKind.BROKER_FLAT_EXITED       # the defect reappears under the mutant
