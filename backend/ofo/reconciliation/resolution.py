"""Apply a reconciliation report to strategy records, and the explicit, audited manual resolutions.

Spec: REQ-060 AC-4 (a change made directly in Zerodha is detected, recorded, and puts the strategy into
Reconciliation Required, Q197), AC-5 (manual reconciliation allowed, explicit and audited, Q198); ADR-018 Q198
choices "Adopt actual broker position · Close/reconcile through a prepared order · Mark as requiring attention; no
casual ignore"; ADR-019 Q200 (Exited); deferred issue #19 (broker flat -> strategy exited).

Every resolution needs a named actor and a non-empty reason (no casual "ignore"), appends one hash-chained audit
event (``EventType.RECONCILIATION_RECORDED``) with before and after, and returns a ``Resolution``. Nothing here
places an order: a prepared closing order is a proposal object, and the block stays until the broker agrees.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from ofo.audit.catalogue import EventType
from ofo.audit.log import AuditLog
from ofo.engine.legs import Action
from ofo.reconciliation.compare import (
    MismatchKind,
    ReconciliationError,
    ReconciliationReport,
    active_units,
    require_id,
)
from ofo.strategy.definition import MAX_TEXT, Contract, StrategyDefinition, contract_sort_key, describe_contract
from ofo.strategy.versions import ExecutionOutcome, Position, StrategyRecord, VersionError


class ResolutionKind(Enum):
    ADOPT_BROKER_POSITION = "adopt actual broker position"
    PREPARE_CLOSING_ORDER = "close/reconcile through a prepared order"
    MARK_REQUIRES_ATTENTION = "mark as requiring attention"
    BROKER_FLAT_EXITED = "broker flat: strategy exited"


class ClosingTarget(Enum):
    """What a prepared order brings the strategy's broker position to."""

    ACTIVE_VERSION = "back to the active version"
    FLAT = "close every position of this strategy"


@dataclass(frozen=True)
class ProposedOrder:
    """One order line of a prepared proposal. Units are positive; the action carries the side."""

    action: Action
    contract: Contract
    units: int


@dataclass(frozen=True)
class ClosingOrderProposal:
    """A prepared order set for the user to review and confirm. It is never placed by this module."""

    strategy_id: str
    target: ClosingTarget
    orders: tuple[ProposedOrder, ...]
    prepared_at: datetime.datetime


@dataclass(frozen=True)
class Resolution:
    """The audited record of one manual resolution (AC-5): who, when, why, before and after."""

    strategy_id: str
    kind: ResolutionKind
    actor: str
    at: datetime.datetime
    reason: str
    before_broker: Position
    before_platform: Position
    after_platform: Position
    still_blocked: bool
    proposal: ClosingOrderProposal | None = None


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ReconciliationError(f"{label} must be a non-empty string of at most {MAX_TEXT} chars, got {value!r}")
    return value


def _lines(position: Position) -> list[list[object]]:
    return [[describe_contract(contract), units] for contract, units in position.lines]


def _require_record(record: object) -> StrategyRecord:
    if not isinstance(record, StrategyRecord):
        raise ReconciliationError(f"a resolution needs a StrategyRecord, got {record!r}")
    return record


def _require_audit(audit: object) -> AuditLog:
    if not isinstance(audit, AuditLog):
        raise ReconciliationError(f"a resolution needs an AuditLog, got {audit!r}")
    return audit


def _platform(record: StrategyRecord) -> Position:
    return Position.of(active_units(record))


# ---- applying a report (AC-4) ---------------------------------------------------------------------------------

def record_report(
    report: ReconciliationReport,
    records: Mapping[str, StrategyRecord],
    *,
    audit: AuditLog,
    run_id: str,
    actor: str = "system",
) -> tuple[ExecutionOutcome, ...]:
    """Record every mismatch in the audit log, and each blocked strategy's broker share on its record.

    Through ``StrategyRecord.observe_broker_position`` a differing share with no proposal in flight puts the
    strategy into Reconciliation Required (the sticky flag in versions.py; not duplicated here).
    """
    if not isinstance(report, ReconciliationReport):
        raise ReconciliationError(f"record_report needs a ReconciliationReport, got {report!r}")
    _require_audit(audit)
    _require_text(run_id, "run id")
    _require_text(actor, "actor")
    missing = sorted(report.blocked_strategy_ids - set(records))
    if missing:
        raise ReconciliationError(f"the report blocks strategies with no record here: {missing}")
    outcomes = []
    for sid in sorted(report.blocked_strategy_ids):
        try:
            outcome = _require_record(records[sid]).observe_broker_position(
                report.share(sid), at=report.at, reference=f"{run_id}:{sid}")
        except VersionError as exc:
            raise ReconciliationError(f"strategy {sid!r}: {exc}") from exc
        if outcome is not None:
            outcomes.append(outcome)
    for mismatch in report.mismatches:
        event = (EventType.EXTERNAL_BROKER_CHANGE_DETECTED if mismatch.kind is MismatchKind.EXTERNAL_MODIFICATION
                 else EventType.RECONCILIATION_RECORDED)
        audit.append(event, actor=actor, timestamp=report.at, correlation_id=run_id, payload={
            "kind": mismatch.kind.value,
            "strategy_ids": list(mismatch.strategy_ids),
            "broker_state": [[describe_contract(c), u] for c, u in mismatch.broker_state],
            "platform_state": [[describe_contract(c), u] for c, u in mismatch.platform_state],
            "difference": [[describe_contract(c), u] for c, u in mismatch.difference],
            "next_action": mismatch.next_action,
        })
    return tuple(outcomes)


# ---- manual resolutions (AC-5) --------------------------------------------------------------------------------

def _resolve(
    strategy_id: str,
    record: StrategyRecord,
    kind: ResolutionKind,
    *,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
    before_broker: Position,
    before_platform: Position,
    proposal: ClosingOrderProposal | None = None,
) -> Resolution:
    after = _platform(record)
    blocked = record.reconciliation_required
    payload: dict[str, object] = {
        "strategy_id": strategy_id,
        "resolution": kind.value,
        "reason": reason,
        "before_broker": _lines(before_broker),
        "before_platform": _lines(before_platform),
        "after_platform": _lines(after),
        "still_blocked": blocked,
        "exited": record.exited,
    }
    if proposal is not None:
        payload["prepared_orders"] = [
            [order.action.value, describe_contract(order.contract), order.units] for order in proposal.orders
        ]
    audit.append(EventType.RECONCILIATION_RECORDED, actor=actor, timestamp=at,
                 correlation_id=f"resolution:{strategy_id}", payload=payload)
    return Resolution(strategy_id, kind, actor, at, reason, before_broker, before_platform, after, blocked, proposal)


def _start(strategy_id: str, record: object, actor: object, reason: object, audit: object, *, blocked: bool = True):
    require_id(strategy_id)
    rec = _require_record(record)
    _require_text(actor, "actor")
    _require_text(reason, "reason")
    _require_audit(audit)
    if rec.exited:
        raise ReconciliationError(f"strategy {strategy_id!r} has exited; nothing to reconcile")
    if blocked and not rec.reconciliation_required:
        raise ReconciliationError(f"strategy {strategy_id!r} needs no reconciliation")
    return rec, rec.actual_position, _platform(rec)


def adopt_broker_position(
    strategy_id: str,
    record: StrategyRecord,
    *,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
    definition: StrategyDefinition | None = None,
) -> Resolution:
    """Q198 "Adopt actual broker position": a new active version equal to the broker's position (versions.reconcile)."""
    rec, broker, platform = _start(strategy_id, record, actor, reason, audit)
    try:
        rec.reconcile(at=at, actor=actor, resolution=reason, definition=definition)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {strategy_id!r}: {exc}") from exc
    return _resolve(strategy_id, rec, ResolutionKind.ADOPT_BROKER_POSITION, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)


def prepare_closing_order(
    strategy_id: str,
    record: StrategyRecord,
    *,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
    target: ClosingTarget = ClosingTarget.ACTIVE_VERSION,
) -> Resolution:
    """Q198 "Close/reconcile through a prepared order": an order proposal, never placed; the block stays."""
    rec, broker, platform = _start(strategy_id, record, actor, reason, audit)
    if not isinstance(target, ClosingTarget):
        raise ReconciliationError(f"target must be a ClosingTarget, got {target!r}")
    goal = platform.as_dict() if target is ClosingTarget.ACTIVE_VERSION else {}
    now = broker.as_dict()
    orders = []
    for contract in sorted(goal.keys() | now.keys(), key=contract_sort_key):
        delta = goal.get(contract, 0) - now.get(contract, 0)
        if delta:
            orders.append(ProposedOrder(Action.BUY if delta > 0 else Action.SELL, contract, abs(delta)))
    if not orders:
        raise ReconciliationError(f"strategy {strategy_id!r}: the broker already matches the target; no order")
    proposal = ClosingOrderProposal(strategy_id, target, tuple(orders), at)
    return _resolve(strategy_id, rec, ResolutionKind.PREPARE_CLOSING_ORDER, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform, proposal=proposal)


def mark_requires_attention(
    strategy_id: str,
    record: StrategyRecord,
    *,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
) -> Resolution:
    """Q198 "Mark as requiring attention": recorded and audited; the strategy stays blocked."""
    rec, broker, platform = _start(strategy_id, record, actor, reason, audit)
    return _resolve(strategy_id, rec, ResolutionKind.MARK_REQUIRES_ATTENTION, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)


def mark_exited_broker_flat(
    strategy_id: str,
    record: StrategyRecord,
    *,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
) -> Resolution:
    """Broker flat -> strategy Exited (ADR-019 Q200; closes the stuck case of deferred issue #19)."""
    rec, broker, platform = _start(strategy_id, record, actor, reason, audit, blocked=False)
    try:
        rec.mark_exited(at=at, actor=actor, resolution=reason)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {strategy_id!r}: {exc}") from exc
    return _resolve(strategy_id, rec, ResolutionKind.BROKER_FLAT_EXITED, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)
