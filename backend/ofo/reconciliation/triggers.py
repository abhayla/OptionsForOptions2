"""The reconciliation trigger policy, as data (REQ-060 AC-1; ADR-018 Q196).

Q196: "reconcile after execution, after reconnect, at app start/resume, periodically for active strategies, on
broker/order events". Each event maps to one run with a scope. The periodic interval is not set here: the spec
gives no number, and periodic runs after the daily Zerodha session expires are open question Q205.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from ofo.reconciliation.compare import MAX_STRATEGIES, ReconciliationError, require_id


class Trigger(Enum):
    AFTER_EXECUTION = "after execution"
    AFTER_RECONNECT = "after reconnect"
    APP_START = "app start"
    APP_RESUME = "app resume"
    PERIODIC = "periodic, active strategies"
    BROKER_POSITION_EVENT = "broker position event"
    ORDER_EVENT = "order event"


class Scope(Enum):
    ALL_STRATEGIES = "every strategy of the account"  # the whole account's broker positions are re-read
    ACTIVE_STRATEGIES = "active strategies"
    NAMED_STRATEGY = "the strategy the event names"


#: The policy. Every trigger runs reconciliation; the scope says over which strategies.
POLICY: dict[Trigger, Scope] = {
    Trigger.AFTER_EXECUTION: Scope.NAMED_STRATEGY,
    Trigger.AFTER_RECONNECT: Scope.ALL_STRATEGIES,
    Trigger.APP_START: Scope.ALL_STRATEGIES,
    Trigger.APP_RESUME: Scope.ALL_STRATEGIES,
    Trigger.PERIODIC: Scope.ACTIVE_STRATEGIES,
    Trigger.BROKER_POSITION_EVENT: Scope.ALL_STRATEGIES,  # a position event may touch any strategy's contract
    Trigger.ORDER_EVENT: Scope.NAMED_STRATEGY,
}


@dataclass(frozen=True)
class ReconciliationRun:
    trigger: Trigger
    scope: Scope
    strategy_ids: tuple[str, ...]


def plan_run(
    trigger: Trigger,
    *,
    all_ids: Iterable[str],
    active_ids: Iterable[str] = (),
    strategy_id: str | None = None,
) -> ReconciliationRun:
    """The run an event must start. Unknown triggers and inconsistent inputs are refused (fail closed)."""
    if not isinstance(trigger, Trigger):
        raise ReconciliationError(f"unknown reconciliation trigger {trigger!r}")
    scope = POLICY[trigger]
    everyone = _ids(all_ids, "all_ids")
    active = _ids(active_ids, "active_ids")
    if not set(active) <= set(everyone):
        raise ReconciliationError(f"active ids not among all ids: {sorted(set(active) - set(everyone))}")
    if scope is Scope.NAMED_STRATEGY:
        if strategy_id is None or require_id(strategy_id) not in everyone:
            raise ReconciliationError(f"{trigger.value} must name a known strategy, got {strategy_id!r}")
        return ReconciliationRun(trigger, scope, (strategy_id,))
    if strategy_id is not None:
        raise ReconciliationError(f"{trigger.value} covers {scope.value}; it names no single strategy")
    return ReconciliationRun(trigger, scope, everyone if scope is Scope.ALL_STRATEGIES else active)


def _ids(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReconciliationError(f"{label} must be a collection of ids, not a string")
    result = tuple(require_id(v) for v in values)
    if len(result) > MAX_STRATEGIES:
        raise ReconciliationError(f"{label}: at most {MAX_STRATEGIES} ids")
    if len(set(result)) != len(result):
        raise ReconciliationError(f"{label} has duplicate ids")
    return tuple(sorted(result))
