"""Apply a reconciliation report to strategy records, and the explicit, audited manual resolutions.

Spec: REQ-060 AC-4 (a change made directly in Zerodha is detected, recorded, and puts the strategy into
Reconciliation Required, Q197), AC-5 (manual reconciliation allowed, explicit and audited, Q198); ADR-018 Q198
choices "Adopt actual broker position · Close/reconcile through a prepared order · Mark as requiring attention; no
casual ignore"; ADR-019 Q200 (Exited); deferred issue #19 (broker flat -> strategy exited).

Premise rule (W-021 fix round; class: a resolution whose premise, the broker position, is read from a stored copy
instead of the latest run): every run refreshes the broker picture of EVERY strategy it covers, and every resolution
takes that run's report and checks its premise against it. The report must be the one last recorded on the
strategy (an older one is refused; one not yet recorded is refused), and its share must equal the recorded broker
position. Adopt adopts that report's quantities; exit needs that report to show the strategy flat.

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
from ofo.audit.models import canonical_json, check_payload_safe
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
    REVIEW_AND_MODIFY = "review and modify strategy"  # hands off to the modification flow (W-027); blocked until then
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
        raise ReconciliationError(detail=f"{label} must be a non-empty string of at most {MAX_TEXT} chars, got {value!r}")
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
    """Record every mismatch in the audit log, and EVERY covered strategy's broker share on its record.

    Agreeing strategies are refreshed too, so no later resolution can act on an older picture. Through
    ``StrategyRecord.observe_broker_position`` a differing share with no proposal in flight puts the strategy into
    Reconciliation Required (the sticky flag in versions.py; not duplicated here).

    All or nothing (W-021 fix rounds 2 and 3; class: a multi-strategy recording that mutates some strategies, or
    writes some audit events, before validating all of them). Phase 1 validates every covered strategy (exited,
    time order, capacity, duplicate reference, share) AND builds+validates every audit payload for audit-safety
    (``check_payload_safe`` / ``canonical_json`` — the same check ``AuditLog.append`` runs, run here first so it
    can never fail partway through phase 2), changing nothing. Only if all pass does phase 2 write the audit
    records, then apply the observations. A refused run leaves no strategy, audit event or reference behind, so the
    same run id can be recorded again once the state allows it. (``ReconciliationReport``/``Mismatch`` also validate
    their own field types on construction — see ``compare.py`` — so most bad reports are refused even earlier; this
    phase-1 payload check is defense in depth for a report reconstructed without going through that constructor,
    e.g. a mismatch field corrupted after loading from storage.)
    """
    if not isinstance(report, ReconciliationReport):
        raise ReconciliationError(f"record_report needs a ReconciliationReport, got {report!r}")
    _require_audit(audit)
    _require_text(run_id, "run id")
    _require_text(actor, "actor")
    missing = sorted((report.covered_strategy_ids | report.blocked_strategy_ids) - set(records))
    if missing:
        raise ReconciliationError(f"the report covers strategies with no record here: {missing}")

    # Phase 1: validate everything; mutate nothing.
    planned = []
    for sid in sorted(report.covered_strategy_ids):
        record = _require_record(records[sid])
        share, reference = report.share(sid), f"{run_id}:{sid}"
        try:
            record.check_observation(share, at=report.at, reference=reference)
        except VersionError as exc:
            raise ReconciliationError(f"strategy {sid!r}: {exc}; nothing was recorded for this run") from exc
        planned.append((record, share, reference))
    events = []
    for mismatch in report.mismatches:
        event = (EventType.EXTERNAL_BROKER_CHANGE_DETECTED if mismatch.kind is MismatchKind.EXTERNAL_MODIFICATION
                 else EventType.RECONCILIATION_RECORDED)
        payload = {
            "kind": mismatch.kind.value,
            "strategy_ids": list(mismatch.strategy_ids),
            "broker_state": [[describe_contract(c), u] for c, u in mismatch.broker_state],
            "platform_state": [[describe_contract(c), u] for c, u in mismatch.platform_state],
            "difference": [[describe_contract(c), u] for c, u in mismatch.difference],
            "next_action": mismatch.next_action,
        }
        try:
            check_payload_safe(payload)
            canonical_json({"payload": payload})
        except Exception as exc:  # PayloadValidationError or anything canonical_json/check_payload_safe raises
            raise ReconciliationError(
                f"mismatch {mismatch.kind.value!r} for {mismatch.strategy_ids!r} has a payload the audit cannot "
                f"store: {exc}; nothing was recorded for this run"
            ) from exc
        events.append((event, payload))

    # Phase 2: audit first, then the observations (each re-checks what phase 1 proved, so none can refuse now).
    for event, payload in events:
        audit.append(event, actor=actor, timestamp=report.at, correlation_id=run_id, payload=payload)
    outcomes = []
    for record, share, reference in planned:
        outcome = record.observe_broker_position(share, at=report.at, reference=reference)
        if outcome is not None:
            outcomes.append(outcome)
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


def _joint_holders(report: ReconciliationReport, strategy_id: str) -> tuple[str, ...]:
    """Every OTHER strategy this strategy shares a jointly-blocked mismatch with (W-021 fix round 6; class:
    per-strategy resolutions that need an attribution rule the spec does not define, flagged for owner question
    Q224). ``compare()`` attributes a shared contract's non-zero difference to EVERY holder when it cannot tell
    which one's quantity moved (``Mismatch.strategy_ids`` has more than one id) -- exactly the case where a
    per-strategy broker share cannot be trusted: it is computed as "broker minus the other holders' PLATFORM
    units", which silently assumes every other holder is exactly at its own intended quantity. When the broker
    itself disagrees across the group (Zerodha nets per contract, not per strategy), that assumption is exactly
    the thing in dispute, so the computed share can show an impossible position (e.g. two SELLers, broker flat,
    computed share +50 -- a LONG that was never opened)."""
    others: set[str] = set()
    for m in report.mismatches:
        if strategy_id in m.strategy_ids and len(m.strategy_ids) > 1:
            others.update(sid for sid in m.strategy_ids if sid != strategy_id)
    return tuple(sorted(others))


def _start(
    strategy_id: str, record: object, report: object, at: object, actor: object, reason: object, audit: object,
    *, blocked: bool = True, refuse_shared: bool = True,
):
    """Validate a resolution and check its premise against the latest recorded run. Returns (record, broker, platform).

    The broker picture returned is the REPORT's share for this strategy, never a stored copy on its own.

    ``refuse_shared`` (default True): refuse when this strategy shares a jointly-blocked mismatch with another
    non-exited strategy (see ``_joint_holders``) -- the spec has no rule for splitting a shared contract's broker
    quantity between strategies (owner question Q224), so adopt/prepare-closing-order/mark-exited-broker-flat
    refuse rather than invent one; only "mark as requiring attention" and "review and modify" (record only, invent
    nothing) pass ``refuse_shared=False``.
    """
    require_id(strategy_id)
    rec = _require_record(record)
    if not isinstance(report, ReconciliationReport):
        raise ReconciliationError(f"a resolution needs the latest ReconciliationReport, got {report!r}")
    _require_text(actor, "actor")
    _require_text(reason, "reason")
    _require_audit(audit)
    if rec.exited:
        raise ReconciliationError(f"strategy {strategy_id!r} has exited; nothing to reconcile")
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None or at < report.at:
        raise ReconciliationError(f"resolution time must be timezone-aware and not before the run, got {at!r}")
    if refuse_shared:
        others = _joint_holders(report, strategy_id)
        if others:
            raise ReconciliationError(
                f"strategy {strategy_id!r} shares a contract with {list(others)} whose broker quantity cannot be "
                "split between them (no spec rule for attribution, Q224); resolve jointly (Review manually)"
            )
    share = report.share(strategy_id)
    observed = rec.last_observed_at
    if observed is None or report.at > observed:
        raise ReconciliationError(f"strategy {strategy_id!r}: this run is not recorded on the strategy yet "
                                  "(record_report first, or a later execution result superseded it)")
    if report.at < observed:
        raise ReconciliationError(f"strategy {strategy_id!r}: the report ({report.at.isoformat()}) is older than the "
                                  f"latest recorded run ({observed.isoformat()}); resolve on the latest run")
    if share != rec.actual_position:
        raise ReconciliationError(f"strategy {strategy_id!r}: the report's broker position differs from the one "
                                  "recorded at the same time; resolve on the run that was recorded")
    if blocked and not rec.reconciliation_required:
        raise ReconciliationError(f"strategy {strategy_id!r} needs no reconciliation")
    return rec, share, _platform(rec)


def adopt_broker_position(
    strategy_id: str,
    record: StrategyRecord,
    *,
    report: ReconciliationReport,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
    definition: StrategyDefinition | None = None,
) -> Resolution:
    """Q198 "Adopt actual broker position": a new active version equal to the broker's position (versions.reconcile)."""
    rec, broker, platform = _start(strategy_id, record, report, at, actor, reason, audit)
    try:
        # versions.reconcile adopts the recorded position, which _start proved equal to the latest run's share.
        rec.reconcile(at=at, actor=actor, resolution=reason, definition=definition)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {strategy_id!r}: {exc}") from exc
    return _resolve(strategy_id, rec, ResolutionKind.ADOPT_BROKER_POSITION, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)


def prepare_closing_order(
    strategy_id: str,
    record: StrategyRecord,
    *,
    report: ReconciliationReport,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
    target: ClosingTarget = ClosingTarget.ACTIVE_VERSION,
) -> Resolution:
    """Q198 "Close/reconcile through a prepared order": an order proposal, never placed; the block stays.

    Note (not built): two proposals prepared on the same report are both allowed here; the confirm/submit step
    must dedupe them (W-023 blocks a second live preparation).
    """
    rec, broker, platform = _start(strategy_id, record, report, at, actor, reason, audit)
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
    report: ReconciliationReport,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
) -> Resolution:
    """Q198 "Mark as requiring attention": recorded and audited; the strategy stays blocked.

    Allowed even when this strategy shares a contract with another jointly-blocked strategy (Q224): it invents no
    attribution, just records the choice.
    """
    rec, broker, platform = _start(strategy_id, record, report, at, actor, reason, audit, refuse_shared=False)
    return _resolve(strategy_id, rec, ResolutionKind.MARK_REQUIRES_ATTENTION, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)


def mark_exited_broker_flat(
    strategy_id: str,
    record: StrategyRecord,
    *,
    report: ReconciliationReport,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
) -> Resolution:
    """Broker flat -> strategy Exited (ADR-019 Q200; closes the stuck case of deferred issue #19)."""
    rec, broker, platform = _start(strategy_id, record, report, at, actor, reason, audit, blocked=False)
    if broker.lines:
        raise ReconciliationError(f"strategy {strategy_id!r}: the latest run shows the broker still holding "
                                  f"{len(broker.lines)} of its contracts; it is not flat")
    try:
        rec.mark_exited(at=at, actor=actor, resolution=reason)
    except VersionError as exc:
        raise ReconciliationError(f"strategy {strategy_id!r}: {exc}") from exc
    return _resolve(strategy_id, rec, ResolutionKind.BROKER_FLAT_EXITED, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)


def review_and_modify(
    strategy_id: str,
    record: StrategyRecord,
    *,
    report: ReconciliationReport,
    actor: str,
    at: datetime.datetime,
    reason: str,
    audit: AuditLog,
) -> Resolution:
    """Q198 "Review and modify strategy": records the choice and hands off to the modification flow (W-027).

    Builds no modification. The strategy stays blocked; it is unblocked only through the existing paths once a
    fresh run agrees (an adopted or executed version the broker matches).

    Allowed even when this strategy shares a contract with another jointly-blocked strategy (Q224): it invents no
    attribution, just records the choice.
    """
    rec, broker, platform = _start(strategy_id, record, report, at, actor, reason, audit, refuse_shared=False)
    return _resolve(strategy_id, rec, ResolutionKind.REVIEW_AND_MODIFY, actor=actor, at=at, reason=reason,
                    audit=audit, before_broker=broker, before_platform=platform)
