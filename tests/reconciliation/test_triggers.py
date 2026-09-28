"""REQ-060 AC-1: reconciliation runs after execution, after reconnect, on app start/resume, periodically for active
strategies and on relevant broker/order events (ADR-018 Q196)."""
from __future__ import annotations

import pytest

from ofo.reconciliation.compare import ReconciliationError
from ofo.reconciliation.triggers import POLICY, Scope, Trigger, plan_run

ALL = ("IC-1", "IC-2", "SC-1")
ACTIVE = ("IC-1", "SC-1")

# Hand-written from Q196, one row per event it names: (trigger, scope, ids the run must cover).
EXPECTED = [
    (Trigger.AFTER_EXECUTION, Scope.NAMED_STRATEGY, ("IC-2",)),
    (Trigger.AFTER_RECONNECT, Scope.ALL_STRATEGIES, ALL),
    (Trigger.APP_START, Scope.ALL_STRATEGIES, ALL),
    (Trigger.APP_RESUME, Scope.ALL_STRATEGIES, ALL),
    (Trigger.PERIODIC, Scope.ACTIVE_STRATEGIES, ACTIVE),
    (Trigger.BROKER_POSITION_EVENT, Scope.ALL_STRATEGIES, ALL),
    (Trigger.ORDER_EVENT, Scope.NAMED_STRATEGY, ("IC-2",)),
]


def test_ac1_policy_lists_exactly_the_q196_events():
    """AC-1: the policy covers every Q196 event and nothing unlisted."""
    assert set(POLICY) == {row[0] for row in EXPECTED} == set(Trigger)


@pytest.mark.parametrize("trigger, scope, ids", EXPECTED, ids=[row[0].name for row in EXPECTED])
def test_ac1_each_trigger_maps_to_a_run(trigger, scope, ids):
    """AC-1: each event produces a reconciliation run over the right strategies."""
    named = "IC-2" if scope is Scope.NAMED_STRATEGY else None
    run = plan_run(trigger, all_ids=reversed(ALL), active_ids=ACTIVE, strategy_id=named)
    assert (run.trigger, run.scope, run.strategy_ids) == (trigger, scope, ids)


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
