"""Execution: the pre-execution safety gate (REQ-059). Pure; the Zerodha adapter lives elsewhere."""
from ofo.execution.context import (
    DataHealth,
    DataInput,
    ExecutionAction,
    ExecutionContext,
    MarginPlanner,
    VersionState,
    active_legs_hash,
    margin_required_from,
)
from ofo.execution.safety import (
    BlockedExecution,
    CheckCode,
    CheckFailure,
    Flag,
    FlagCode,
    SafetyResult,
    check_pre_execution,
    pro_requirement,
)

__all__ = [
    "BlockedExecution",
    "CheckCode",
    "CheckFailure",
    "DataHealth",
    "DataInput",
    "ExecutionAction",
    "ExecutionContext",
    "Flag",
    "FlagCode",
    "MarginPlanner",
    "SafetyResult",
    "VersionState",
    "active_legs_hash",
    "check_pre_execution",
    "margin_required_from",
    "pro_requirement",
]
