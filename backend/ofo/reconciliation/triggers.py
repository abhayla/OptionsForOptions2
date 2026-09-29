"""The reconciliation trigger policy, as data (REQ-060 AC-1; ADR-018 Q196).

Q196: "reconcile after execution, after reconnect, at app start/resume, periodically for active strategies, on
broker/order events". Each event maps to one run with a scope. The periodic interval is not set here: the spec
gives no number, and periodic runs after the daily Zerodha session expires are open question Q205.

Covered-set closure (W-021 fix round, 2026-09-29; not an owner decision; class: a subset compared against a
whole-account net map). ``compare()`` checks a contract's expected units against Zerodha's single ACCOUNT-WIDE net
number for that contract (REQ-060 AC-7); if two strategies share a contract and a run's covered set names only one
of them, the comparison is done against a number that also reflects the other's holding, and the named strategy is
falsely blocked (or, worse, falsely cleared). ORCHESTRATOR DEFAULT: for ``Scope.NAMED_STRATEGY`` the run's covered
set is the CLOSURE of every strategy sharing any contract with the named strategy, computed recursively (A shares a
contract with B, B shares a different contract with C -> the run covers A, B and C too). A named run whose strategy
shares no contract with any other still covers only that one strategy. The closure needs to know which contracts
each strategy holds; callers pass that via ``contracts_by_strategy`` (typically each strategy's active + proposed
version units). With none given, the closure is just the named strategy (unchanged behaviour, e.g. in tests that
don't exercise sharing).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

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
    contracts_by_strategy: Mapping[str, Iterable[object]] = ...,
) -> ReconciliationRun:
    """The run an event must start. Unknown triggers and inconsistent inputs are refused (fail closed).

    ``contracts_by_strategy`` (optional): each strategy id -> the contracts it currently holds (any contract, in
    any version). Used only for ``Scope.NAMED_STRATEGY`` to compute the shared-contract closure (module docstring).
    """
    if contracts_by_strategy is ...:
        contracts_by_strategy = {}
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
        holdings = _holdings(contracts_by_strategy, set(everyone))
        covered = _closure((strategy_id,), holdings)
        return ReconciliationRun(trigger, scope, covered)
    if strategy_id is not None:
        raise ReconciliationError(f"{trigger.value} covers {scope.value}; it names no single strategy")
    return ReconciliationRun(trigger, scope, everyone if scope is Scope.ALL_STRATEGIES else active)


def _holdings(contracts_by_strategy: object, everyone: set[str]) -> dict[str, frozenset]:
    if not isinstance(contracts_by_strategy, Mapping):
        raise ReconciliationError(
            f"contracts_by_strategy must be a mapping of strategy id -> contracts, got {contracts_by_strategy!r}"
        )
    result: dict[str, frozenset] = {}
    for sid, contracts in contracts_by_strategy.items():
        if sid not in everyone:
            raise ReconciliationError(f"contracts_by_strategy names unknown strategy {sid!r}")
        if isinstance(contracts, (str, bytes)):
            raise ReconciliationError(f"contracts_by_strategy[{sid!r}] must be a collection of contracts, not a string")
        result[sid] = frozenset(contracts)
    return result


def _closure(seed: tuple[str, ...], holdings: Mapping[str, frozenset]) -> tuple[str, ...]:
    """Every strategy in ``holdings`` reachable from ``seed`` through a chain of shared contracts."""
    covered = set(seed)
    changed = True
    while changed:
        changed = False
        covered_contracts: set = set()
        for sid in covered:
            covered_contracts |= holdings.get(sid, frozenset())
        for sid, contracts in holdings.items():
            if sid not in covered and contracts & covered_contracts:
                covered.add(sid)
                changed = True
    return tuple(sorted(covered))


def _ids(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReconciliationError(f"{label} must be a collection of ids, not a string")
    result = tuple(require_id(v) for v in values)
    if len(result) > MAX_STRATEGIES:
        raise ReconciliationError(f"{label}: at most {MAX_STRATEGIES} ids")
    if len(set(result)) != len(result):
        raise ReconciliationError(f"{label} has duplicate ids")
    return tuple(sorted(result))
