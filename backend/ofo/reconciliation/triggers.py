"""The reconciliation trigger policy, as data (REQ-060 AC-1; ADR-018 Q196).

Q196: "reconcile after execution, after reconnect, at app start/resume, periodically for active strategies, on
broker/order events". Each event maps to one run; the periodic interval is not set here: the spec gives no number,
and periodic runs after the daily Zerodha session expires are open question Q205.

Scheduling vs coverage, and the trust boundary (W-021 fix round 5, 2026-09-29; ORCHESTRATOR DEFAULT, not an owner
decision; class: any run whose COMPARISON set is narrower than the set of strategies that can hold positions in the
account -- finding caller-supplied-verdict-trusted). Fix round 4 made "after execution"/"order event" account-wide,
but PERIODIC still compared only the caller-supplied ``active_ids``. That reintroduced the same class: a strategy
can be Monitoring Paused (ADR-019 Q200 -- not exited, so it still holds positions) without being "active". Example:
A is active, B is Monitoring Paused; both SELL the same contract x50; Zerodha nets -100. A periodic run scoped to
``active_ids={A}`` compares A alone against -100, finds a false -50 quantity mismatch, and adopting rewrites A to
-100 while B's true -50 is never seen.

Zerodha nets strategies per contract with no notion of which strategy a unit belongs to, so COVERAGE (the set
``compare()`` is run against) must always be every strategy that can hold a position -- every NON-EXITED strategy
of the account, active or paused alike. Only "exited" strictly means the strategy holds nothing (ADR-019 Q200), so
it is the one state safe to leave out. SCHEDULING (whether a periodic tick is worth running at all) is a separate,
weaker question, answered by whether anything is active; it must never narrow WHAT is compared once a run does
happen. So: ``plan_run`` takes every strategy's ``StrategyRecord`` and derives coverage itself (every non-exited
one), never a caller-supplied id list; ``active_ids`` is used ONLY to decide whether a PERIODIC run fires at all
(returns ``None`` when nothing is active), never to narrow coverage.

Trust boundary (the one this layer cannot remove): ``plan_run`` filters OUT exited records from what it is given,
but it has no way to detect a non-exited record left OUT of the ``records`` mapping entirely -- the caller (the
strategy store / integration layer) must pass every non-exited record of the account, and that completeness is
guaranteed one layer up, not here. (Fix round 4's docstring called ``ACTIVE_STRATEGIES`` "already whole-population",
which was false -- Monitoring Paused strategies are excluded from "active" and are exactly the gap this round
closes; corrected here.)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from ofo.reconciliation.compare import MAX_STRATEGIES, ReconciliationError, require_id
from ofo.strategy.versions import StrategyRecord


class Trigger(Enum):
    AFTER_EXECUTION = "after execution"
    AFTER_RECONNECT = "after reconnect"
    APP_START = "app start"
    APP_RESUME = "app resume"
    PERIODIC = "periodic, active strategies"
    BROKER_POSITION_EVENT = "broker position event"
    ORDER_EVENT = "order event"


class Scope(Enum):
    ALL_STRATEGIES = "every non-exited strategy of the account"  # every trigger's coverage, always


#: Every trigger's coverage is the whole account's non-exited strategies (module docstring); PERIODIC additionally
#: needs at least one strategy active to fire at all (scheduling), but that never narrows its coverage.
POLICY: dict[Trigger, Scope] = {trigger: Scope.ALL_STRATEGIES for trigger in Trigger}

#: Triggers caused by one strategy's own action. The run still covers the whole account (module docstring); the
#: causing strategy id is required and kept only as ``ReconciliationRun.triggered_by``, for the audit trail.
NAMES_TRIGGERING_STRATEGY = frozenset({Trigger.AFTER_EXECUTION, Trigger.ORDER_EVENT})


@dataclass(frozen=True)
class ReconciliationRun:
    trigger: Trigger
    scope: Scope
    strategy_ids: tuple[str, ...]
    triggered_by: str | None = None  # the strategy whose action caused the run, for the audit trail only


def _records(records: object) -> dict[str, StrategyRecord]:
    if not isinstance(records, Mapping):
        raise ReconciliationError(f"records must be a mapping of strategy id -> StrategyRecord, got {records!r}")
    if len(records) > MAX_STRATEGIES:
        raise ReconciliationError(detail=f"{len(records)} strategies; at most {MAX_STRATEGIES}")
    result: dict[str, StrategyRecord] = {}
    seen: set[int] = set()
    for sid, record in records.items():
        require_id(sid)
        if not isinstance(record, StrategyRecord):
            raise ReconciliationError(f"strategy {sid!r} must be a StrategyRecord, got {record!r}")
        if id(record) in seen:
            raise ReconciliationError(f"strategy {sid!r} is the same record as another id; one record, one id")
        seen.add(id(record))
        result[sid] = record
    return result


def plan_run(
    trigger: Trigger,
    *,
    records: Mapping[str, StrategyRecord],
    active_ids: Iterable[str] = (),
    strategy_id: str | None = None,
) -> ReconciliationRun | None:
    """The run an event must start, or ``None`` if it does not fire (module docstring: only PERIODIC can decline,
    when nothing is active). Unknown triggers and inconsistent inputs are refused (fail closed).

    ``records``: every strategy of the account, id -> its ``StrategyRecord``; coverage is derived from it (every
    non-exited record), never from a caller-narrowed id list. ``active_ids`` decides ONLY whether a PERIODIC run
    fires; it is not a coverage input. ``strategy_id`` is required for, and only for, a trigger in
    ``NAMES_TRIGGERING_STRATEGY`` -- kept as ``triggered_by`` for the audit trail, never narrowing coverage.
    """
    if not isinstance(trigger, Trigger):
        raise ReconciliationError(f"unknown reconciliation trigger {trigger!r}")
    scope = POLICY[trigger]
    all_records = _records(records)
    everyone = tuple(sorted(all_records))
    active = _ids(active_ids, "active_ids")
    if not set(active) <= set(everyone):
        raise ReconciliationError(f"active ids not among all ids: {sorted(set(active) - set(everyone))}")
    if trigger in NAMES_TRIGGERING_STRATEGY:
        if strategy_id is None or require_id(strategy_id) not in everyone:
            raise ReconciliationError(detail=f"{trigger.value} must name a known strategy, got {strategy_id!r}")
        if all_records[strategy_id].exited:
            raise ReconciliationError(detail=f"{trigger.value} names strategy {strategy_id!r}, which has exited")
    elif strategy_id is not None:
        raise ReconciliationError(detail=f"{trigger.value} names no single strategy")
    if trigger is Trigger.PERIODIC and not active:
        return None  # scheduling only: nothing active, no run needed (coverage is unaffected either way)
    covered = tuple(sorted(sid for sid, record in all_records.items() if not record.exited))
    triggered_by = strategy_id if trigger in NAMES_TRIGGERING_STRATEGY else None
    return ReconciliationRun(trigger, scope, covered, triggered_by=triggered_by)


def _ids(values: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReconciliationError(detail=f"{label} must be a collection of ids, not a string")
    result = tuple(require_id(v) for v in values)
    if len(result) > MAX_STRATEGIES:
        raise ReconciliationError(detail=f"{label}: at most {MAX_STRATEGIES} ids")
    if len(set(result)) != len(result):
        raise ReconciliationError(detail=f"{label} has duplicates")
    return tuple(sorted(result))
