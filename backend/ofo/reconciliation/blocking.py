"""Which strategies the execution gate must block (REQ-060 AC-6, AC-7; ADR-018 Q199).

A strategy is blocked for new execution and adjustment execution while it has an unresolved mismatch: either the
latest reconciliation report attributes a difference to it, or its record carries the sticky
``reconciliation_required`` flag (set by a result or an observation, cleared only by an explicit resolution).
Only those strategies: a mismatch on another strategy, an unexpected broker position or a changed standalone
blocks none (AC-7).
"""
from __future__ import annotations

from typing import Mapping

from ofo.reconciliation.compare import ReconciliationError, ReconciliationReport, require_id
from ofo.strategy.versions import StrategyRecord


def blocked_strategy_ids(
    report: ReconciliationReport | None, records: Mapping[str, StrategyRecord]
) -> frozenset[str]:
    """Strategy ids with an unresolved mismatch. ``report`` is the latest run (None before the first run)."""
    if report is not None and not isinstance(report, ReconciliationReport):
        raise ReconciliationError(f"report must be a ReconciliationReport or None, got {report!r}")
    if not isinstance(records, Mapping):
        raise ReconciliationError(f"records must be a mapping of strategy id -> StrategyRecord, got {records!r}")
    flagged = set()
    for sid, record in records.items():
        require_id(sid)
        if not isinstance(record, StrategyRecord):
            raise ReconciliationError(f"strategy {sid!r} must be a StrategyRecord, got {record!r}")
        if record.reconciliation_required:
            flagged.add(sid)
    from_report = set() if report is None else {
        sid for sid in report.blocked_strategy_ids if not (sid in records and records[sid].exited)
    }
    return frozenset(flagged | from_report)


def is_execution_blocked(
    strategy_id: str, report: ReconciliationReport | None, records: Mapping[str, StrategyRecord]
) -> bool:
    """The gate's question for one strategy: may it run new or adjustment execution? False only when unblocked."""
    require_id(strategy_id)
    return strategy_id in blocked_strategy_ids(report, records)
