"""REQ-060 AC-1: reconciliation runs after execution, after reconnect, on app start/resume, periodically for active
strategies and on relevant broker/order events (ADR-018 Q196).

Class (W-021 fix round 4, 2026-09-29; finding caller-supplied-verdict-trusted): a run's coverage must never depend
on a caller-supplied map that can be incomplete. A prior fix tried to cover just the strategies sharing a contract
with the one that triggered "after execution"/"order event", computed from a caller-passed contracts map; whenever
that map omitted a holder (nothing forced it to be complete), the run silently fell back to the named strategy
alone. Example: A and B each SELL the same contract x50, Zerodha nets -100; a run "after execution" for A that
does not know about B compares A alone against -100, finds a false quantity mismatch, and adopting corrupts A's
definition to x100. The fix: every trigger's run covers the WHOLE account (or, for PERIODIC, active strategies --
already whole-population); "after execution"/"order event" keep the triggering strategy only as an audit label."""
from __future__ import annotations

import pytest

from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import ReconciliationError, compare
from ofo.reconciliation.resolution import adopt_broker_position, record_report
from ofo.reconciliation.triggers import POLICY, Scope, Trigger, plan_run
from recon_fixtures import at, audit_log, c, clock, executed, single_leg

ALL = ("IC-1", "IC-2", "SC-1")
ACTIVE = ("IC-1", "SC-1")

# Hand-written from Q196, one row per event it names: (trigger, scope, ids the run must cover, triggered_by).
EXPECTED = [
    (Trigger.AFTER_EXECUTION, Scope.ALL_STRATEGIES, ALL, "IC-2"),
    (Trigger.AFTER_RECONNECT, Scope.ALL_STRATEGIES, ALL, None),
    (Trigger.APP_START, Scope.ALL_STRATEGIES, ALL, None),
    (Trigger.APP_RESUME, Scope.ALL_STRATEGIES, ALL, None),
    (Trigger.PERIODIC, Scope.ACTIVE_STRATEGIES, ACTIVE, None),
    (Trigger.BROKER_POSITION_EVENT, Scope.ALL_STRATEGIES, ALL, None),
    (Trigger.ORDER_EVENT, Scope.ALL_STRATEGIES, ALL, "IC-2"),
]


def test_ac1_policy_lists_exactly_the_q196_events():
    """AC-1: the policy covers every Q196 event and nothing unlisted."""
    assert set(POLICY) == {row[0] for row in EXPECTED} == set(Trigger)


@pytest.mark.parametrize("trigger, scope, ids, triggered_by", EXPECTED, ids=[row[0].name for row in EXPECTED])
def test_ac1_each_trigger_maps_to_a_run(trigger, scope, ids, triggered_by):
    """AC-1: every event's run covers the right strategies -- the WHOLE account except PERIODIC (module docstring);
    'after execution'/'order event' still name their triggering strategy, but only as an audit label."""
    run = plan_run(trigger, all_ids=reversed(ALL), active_ids=ACTIVE, strategy_id=triggered_by)
    assert (run.trigger, run.scope, run.strategy_ids, run.triggered_by) == (trigger, scope, ids, triggered_by)


def test_ac1_bad_trigger_inputs_are_refused():
    """AC-1 (negative): unknown trigger, unnamed/unknown strategy, stray name, duplicates, strings -> refused."""
    with pytest.raises(ReconciliationError):
        plan_run("after execution", all_ids=ALL)
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.AFTER_EXECUTION, all_ids=ALL)
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.ORDER_EVENT, all_ids=ALL, strategy_id="nope")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, all_ids=ALL, strategy_id="IC-1")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, all_ids=("IC-1", "IC-1"))
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, all_ids="IC-1")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.PERIODIC, all_ids=("IC-1",), active_ids=("SC-9",))
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.APP_START, all_ids=[f"S{i}" for i in range(1001)])


# ---- AC-1 end-to-end: the #33 A/B example, fixed by account-wide coverage --------------------------------------

def test_ac1_after_execution_run_covers_whole_account_shared_contract_no_false_mismatch():
    """The #33 example: A and B each SELL the same contract x50; Zerodha nets -100 (no real mismatch). A run
    triggered "after execution" for A must cover the WHOLE account, not just A, so the shared contract compares
    correctly: nothing blocked, and adopting is refused because there is no mismatch to reconcile."""
    contract = c(Instrument.CE, "23400")
    a = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-a")
    b = executed(single_leg(Action.SELL, Instrument.CE, "23400", 50), "exec-b")
    records = {"A": a, "B": b}

    run = plan_run(Trigger.AFTER_EXECUTION, all_ids=("A", "B"), strategy_id="A")
    assert run.scope is Scope.ALL_STRATEGIES
    assert set(run.strategy_ids) == {"A", "B"}
    assert run.triggered_by == "A"

    covered = {sid: records[sid] for sid in run.strategy_ids}
    report = compare({contract: -100}, covered, at=at(10), clock=clock)
    assert report.mismatches == ()
    assert report.blocked_strategy_ids == frozenset()

    audit = audit_log()
    record_report(report, covered, audit=audit, run_id="run-ab")
    assert audit.events == () and not a.reconciliation_required and not b.reconciliation_required

    with pytest.raises(ReconciliationError):  # nothing to reconcile: A needs no reconciliation
        adopt_broker_position("A", a, report=report, actor="tester", at=at(11), reason="test", audit=audit)
