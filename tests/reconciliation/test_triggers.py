"""REQ-060 AC-1: reconciliation runs after execution, after reconnect, on app start/resume, periodically for active
strategies and on relevant broker/order events (ADR-018 Q196).

Class (W-021 fix round, 2026-09-29): a run scoped to a NAMED strategy must cover every strategy that shares a
contract with it, recursively, or ``compare()``'s single account-wide broker number for a shared contract falsely
blocks (or clears) the named strategy alone. Example: A and B each sell 25000 CE x50, Zerodha shows x100; a run
covering only A finds 0 mismatches on A's own check and blocks nothing, but neither has actually been reconciled."""
from __future__ import annotations

from ofo.engine import Instrument
import pytest

from ofo.reconciliation.compare import ReconciliationError
from ofo.reconciliation.triggers import POLICY, Scope, Trigger, plan_run
from recon_fixtures import c

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


# ---- AC-1 closure: a named run covers every strategy sharing a contract, recursively -------------------------

X = c(Instrument.CE, "25000")
Y = c(Instrument.PE, "22000")
Z = c(Instrument.CE, "26000")


def test_ac1_named_run_with_no_shared_contract_covers_just_the_named_strategy():
    """A named run where no contract is shared still covers just A (unchanged from before this fix)."""
    holdings = {"A": {X}, "B": {Y}, "C": {Z}}
    run = plan_run(
        Trigger.AFTER_EXECUTION, all_ids=("A", "B", "C"), strategy_id="A", contracts_by_strategy=holdings
    )
    assert run.strategy_ids == ("A",)


def test_ac1_named_run_covers_a_strategy_sharing_a_contract_directly():
    """A and B each sell contract X (the 25000 CE x50/x100 example): a run named for A must also cover B."""
    holdings = {"A": {X}, "B": {X}}
    run = plan_run(Trigger.AFTER_EXECUTION, all_ids=("A", "B"), strategy_id="A", contracts_by_strategy=holdings)
    assert run.strategy_ids == ("A", "B")
    run2 = plan_run(Trigger.ORDER_EVENT, all_ids=("A", "B"), strategy_id="B", contracts_by_strategy=holdings)
    assert run2.strategy_ids == ("A", "B")


def test_ac1_named_run_covers_the_transitive_closure_of_shared_contracts():
    """A-B share contract X, B-C share a different contract Y: a run named for A covers A, B and C."""
    holdings = {"A": {X}, "B": {X, Y}, "C": {Y}}
    run = plan_run(Trigger.AFTER_EXECUTION, all_ids=("A", "B", "C"), strategy_id="A", contracts_by_strategy=holdings)
    assert run.strategy_ids == ("A", "B", "C")


def test_ac1_closure_ignores_a_strategy_that_shares_nothing_with_the_chain():
    """D shares no contract with A/B/C's chain: a run named for A never covers D."""
    holdings = {"A": {X}, "B": {X, Y}, "C": {Y}, "D": {Z}}
    run = plan_run(
        Trigger.AFTER_EXECUTION, all_ids=("A", "B", "C", "D"), strategy_id="A", contracts_by_strategy=holdings
    )
    assert run.strategy_ids == ("A", "B", "C")


def test_ac1_contracts_by_strategy_rejects_unknown_strategy_or_string_contracts():
    """Fail closed: an unknown id or a bare string (mistaken for a collection of one) is refused."""
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.AFTER_EXECUTION, all_ids=("A",), strategy_id="A", contracts_by_strategy={"nope": {X}})
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.AFTER_EXECUTION, all_ids=("A",), strategy_id="A", contracts_by_strategy="A")
    with pytest.raises(ReconciliationError):
        plan_run(Trigger.AFTER_EXECUTION, all_ids=("A",), strategy_id="A", contracts_by_strategy={"A": "not-a-set"})
