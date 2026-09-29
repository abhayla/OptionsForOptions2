"""REQ-060 AC-1: reconciliation runs after execution, after reconnect, on app start/resume, periodically for active
strategies and on relevant broker/order events (ADR-018 Q196).

Class (W-021 fix round 5, 2026-09-29; finding caller-supplied-verdict-trusted): any run whose COMPARISON set is
narrower than the set of strategies that can hold positions in the account. Fix round 4 made "after
execution"/"order event" account-wide but left PERIODIC comparing only the caller-supplied ``active_ids``. Example
(verifier, #33 round): A is active, B is Monitoring Paused (ADR-019 Q200 -- not exited, still holds positions);
both SELL the same contract x50, Zerodha nets -100. A periodic run scoped to ``active_ids={A}`` compares A alone
against -100, finds a false -50 mismatch, and adopting corrupts A. Fix: coverage is always every NON-EXITED
strategy, derived by ``plan_run`` from the ``records`` mapping it is given; ``active_ids`` decides only whether a
PERIODIC run fires (scheduling), never what it covers."""
from __future__ import annotations

import pytest

from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import ReconciliationError, compare
from ofo.reconciliation.resolution import adopt_broker_position, record_report
from ofo.reconciliation.triggers import POLICY, Scope, Trigger, plan_run
from ofo.strategy.versions import Position
from recon_fixtures import at, audit_log, c, clock, executed, single_leg

ALL = ("IC-1", "IC-2", "SC-1")
ACTIVE = ("IC-1", "SC-1")


def _records(ids=ALL):
    return {sid: executed(single_leg(Action.SELL, Instrument.CE, "23400", 1), f"exec-{sid}") for sid in ids}


# Hand-written from Q196, one row per event it names: (trigger, ids the run must cover, triggered_by).
EXPECTED = [
    (Trigger.AFTER_EXECUTION, ALL, "IC-2"),
    (Trigger.AFTER_RECONNECT, ALL, None),
    (Trigger.APP_START, ALL, None),
    (Trigger.APP_RESUME, ALL, None),
    (Trigger.PERIODIC, ALL, None),
    (Trigger.BROKER_POSITION_EVENT, ALL, None),
    (Trigger.ORDER_EVENT, ALL, "IC-2"),
]


def test_ac1_policy_lists_exactly_the_q196_events():
    """AC-1: the policy covers every Q196 event and nothing unlisted."""
    assert set(POLICY) == {row[0] for row in EXPECTED} == set(Trigger)


@pytest.mark.parametrize("trigger, ids, triggered_by", EXPECTED, ids=[row[0].name for row in EXPECTED])
def test_ac1_each_trigger_covers_every_non_exited_strategy(trigger, ids, triggered_by):
    """AC-1: every event's run covers every non-exited strategy of the account (module docstring) -- 'after
    execution'/'order event' still name their triggering strategy, but only as an audit label, never narrowing
    coverage; PERIODIC needs at least one active id to fire (here ACTIVE is non-empty)."""
    run = plan_run(trigger, records=_records(), active_ids=ACTIVE, strategy_id=triggered_by)
    assert run is not None
    assert (run.trigger, run.scope, run.strategy_ids, run.triggered_by) == (
        trigger, Scope.ALL_STRATEGIES, ids, triggered_by,
    )


def test_ac1_bad_trigger_inputs_are_refused():
    """AC-1 (negative): unknown trigger, unnamed/unknown strategy, stray name, duplicates, strings, bad records
    mapping -> refused."""
    records = _records()
    with pytest.raises(ReconciliationError):
        plan_run("after execution", records=records)
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.AFTER_EXECUTION, records=records)
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.ORDER_EVENT, records=records, strategy_id="nope")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, records=records, strategy_id="IC-1")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, records={"IC-1": records["IC-1"]}, active_ids=("SC-9",))
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, records="IC-1")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, records={"IC-1": "not-a-record"})
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, records={f"S{i}": executed(single_leg(Action.SELL, Instrument.CE, "23400", 1),
                                                                f"e{i}") for i in range(1001)})


# ---- AC-1 coverage class: non-exited (active or paused) always covered, exited never ---------------------------

def test_ac1_periodic_covers_a_monitoring_paused_strategy_sharing_a_contract_no_false_mismatch():
    """The verifier's example: A active, B Monitoring Paused (not exited); both SELL the same contract x50, Zerodha
    nets -100. The periodic run must cover B too, so nothing is falsely blocked and adopt is refused (no mismatch)."""
    contract = c(Instrument.CE, "23400")
    a = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-a")
    b = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-b")  # Monitoring Paused: not exited
    records = {"A": a, "B": b}

    run = plan_run(Trigger.PERIODIC, records=records, active_ids=("A",))
    assert run is not None and set(run.strategy_ids) == {"A", "B"}

    covered = {sid: records[sid] for sid in run.strategy_ids}
    report = compare({contract: -100}, covered, at=at(10), clock=clock)
    assert report.mismatches == () and report.blocked_strategy_ids == frozenset()

    audit = audit_log()
    record_report(report, covered, audit=audit, run_id="run-periodic")
    assert audit.events == () and not a.reconciliation_required and not b.reconciliation_required
    with pytest.raises(ReconciliationError):
        adopt_broker_position("A", a, report=report, actor="tester", at=at(11), reason="test", audit=audit)


def test_ac1_an_exited_strategy_is_excluded_from_coverage():
    """An exited strategy holds nothing (ADR-019 Q200) and is the one state safe to leave out of coverage."""
    a = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-a")
    b = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-b")
    b.observe_broker_position(Position.of({}), at=at(4), reference="flat-1")  # broker went flat
    b.mark_exited(at=at(5), actor="tester", resolution="closed flat")
    assert b.exited
    run = plan_run(Trigger.APP_START, records={"A": a, "B": b})
    assert run.strategy_ids == ("A",)


def test_ac1_periodic_does_not_fire_when_no_strategy_is_active():
    """Scheduling: PERIODIC only fires when something is active; coverage itself is unaffected by that gate."""
    records = _records(("A", "B"))
    assert plan_run(Trigger.PERIODIC, records=records, active_ids=()) is None
