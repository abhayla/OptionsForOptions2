"""The reconciliation trigger policy, as data (REQ-060 AC-1; ADR-018 Q196).

Q196: "reconcile after execution, after reconnect, at app start/resume, periodically for active strategies, on
broker/order events". Each event maps to one run with a scope. The periodic interval is not set here: the spec
gives no number, and periodic runs after the daily Zerodha session expires are open question Q205.

Account-wide coverage, always (W-021 fix round 4, 2026-09-29; ORCHESTRATOR DEFAULT, not an owner decision; class:
a caller-supplied map deciding safety coverage -- finding caller-supplied-verdict-trusted). An earlier version of
this module scoped "after execution" and "order event" to the single strategy that triggered them, then (fix round
3) tried to repair that by covering the CLOSURE of every strategy sharing a contract with it -- computed from a
caller-supplied ``contracts_by_strategy`` map. That still failed open: whenever the caller omitted, emptied, or
simply forgot a holder in that map (which nothing forced them to keep complete), the run silently fell back to
covering only the named strategy again. Example: A and B each SELL the same contract x50; Zerodha nets -100. A run
"after execution" for A with no (or an incomplete) map compares A alone against -100, reports a false quantity
mismatch, and adopting writes -100 into A's own definition -- corrupting it, while B still shows its true -50.

Zerodha nets strategies per contract: it has no notion of which strategy a unit belongs to, so a comparison over
any strategy subset can never be safe -- the subset might be missing another holder of the same contract, and
nothing about a single contract can prove it isn't. The only input that is NEVER incomplete is "the whole account",
because it needs no map at all. So every trigger's scope is now account-wide (``ALL_STRATEGIES`` or, for the
periodic trigger, ``ACTIVE_STRATEGIES``, which was already whole-population and safe). "After execution" and "order
event" still name the strategy whose action triggered the run -- kept on ``ReconciliationRun.triggered_by`` purely
for the audit trail ("triggered by S") -- but the run itself compares and can block every strategy, exactly like
every other trigger.
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


#: The policy. Every trigger runs reconciliation over the WHOLE account (module docstring) except PERIODIC, which
#: is scoped to active strategies only (that scope was already whole-population, so no caller map can leave it
#: incomplete).
POLICY: dict[Trigger, Scope] = {
    Trigger.AFTER_EXECUTION: Scope.ALL_STRATEGIES,
    Trigger.AFTER_RECONNECT: Scope.ALL_STRATEGIES,
    Trigger.APP_START: Scope.ALL_STRATEGIES,
    Trigger.APP_RESUME: Scope.ALL_STRATEGIES,
    Trigger.PERIODIC: Scope.ACTIVE_STRATEGIES,
    Trigger.BROKER_POSITION_EVENT: Scope.ALL_STRATEGIES,  # a position event may touch any strategy's contract
    Trigger.ORDER_EVENT: Scope.ALL_STRATEGIES,
}

#: Triggers caused by one strategy's own action. The run still covers the whole account (module docstring); the
#: causing strategy id is required and kept only as ``ReconciliationRun.triggered_by``, for the audit trail.
NAMES_TRIGGERING_STRATEGY = frozenset({Trigger.AFTER_EXECUTION, Trigger.ORDER_EVENT})


@dataclass(frozen=True)
class ReconciliationRun:
    trigger: Trigger
    scope: Scope
    strategy_ids: tuple[str, ...]
    triggered_by: str | None = None  # the strategy whose action caused the run, for the audit trail only


def plan_run(
    trigger: Trigger,
    *,
    all_ids: Iterable[str],
    active_ids: Iterable[str] = (),
    strategy_id: str | None = None,
) -> ReconciliationRun:
    """The run an event must start. Unknown triggers and inconsistent inputs are refused (fail closed).

    ``strategy_id`` is required for, and only for, a trigger in ``NAMES_TRIGGERING_STRATEGY`` (the strategy whose
    execution/order caused the run) -- it never narrows the run's coverage (module docstring).
    """
    if not isinstance(trigger, Trigger):
        raise ReconciliationError(f"unknown reconciliation trigger {trigger!r}")
    scope = POLICY[trigger]
    everyone = _ids(all_ids, "all_ids")
    active = _ids(active_ids, "active_ids")
    if not set(active) <= set(everyone):
        raise ReconciliationError(f"active ids not among all ids: {sorted(set(active) - set(everyone))}")
    if trigger in NAMES_TRIGGERING_STRATEGY:
        if strategy_id is None or require_id(strategy_id) not in everyone:
            raise ReconciliationError(f"{trigger.value} must name a known strategy, got {strategy_id!r}")
        return ReconciliationRun(trigger, scope, everyone, triggered_by=strategy_id)
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
