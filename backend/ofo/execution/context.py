"""Execution context: every outside fact the pre-execution gate needs, supplied as input (REQ-059 AC-1).

Nothing here calls Zerodha or the network. Each status input is ``True`` (confirmed), ``False`` (confirmed not) or
``None`` (could not be confirmed); only ``True`` passes, so a missing fact fails closed. A wrong type raises
``ValueError`` at construction, never defaults.

Modelling choices (spec basis in each line):

- ``action`` distinguishes a new entry, an adjustment and an exit, because ADR-037 lets a Limited user exit an active
  strategy while new entries and adjustments stay Pro. ``pro_entitled`` is the entitlement layer's answer ("does this
  user currently hold Pro?"), passed in as a boolean; this module does not import the entitlement layer.
- ``version_state`` is the state of the version being executed. ADR-019 Q191: a proposed version becomes active only
  after execution + reconciliation, so an ADJUSTMENT executes a PROPOSED version, while a NEW_ENTRY or EXIT executes
  the strategy's current (ACTIVE) configuration; a SUPERSEDED version is never executed.
- ``reconciliation_blocked_strategy_ids`` is the set of strategies with an unresolved mismatch, from the reconciliation
  layer. REQ-060 AC-7: a mismatch blocks only its own strategy, and standalone positions are never mismatches, so the
  gate asks only whether THIS ``strategy_id`` is in the set. ADR-019 Q200 (Reconciliation Required: execute no) makes
  it block every action, exits included.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Protocol

from ofo.engine import Strategy
from ofo.engine.legs import require_decimal


class ExecutionAction(Enum):
    NEW_ENTRY = "NEW_ENTRY"
    ADJUSTMENT = "ADJUSTMENT"
    EXIT = "EXIT"


class VersionState(Enum):
    ACTIVE = "ACTIVE"
    PROPOSED = "PROPOSED"
    SUPERSEDED = "SUPERSEDED"


EXECUTABLE_VERSION_STATES: dict[ExecutionAction, frozenset[VersionState]] = {
    ExecutionAction.NEW_ENTRY: frozenset({VersionState.ACTIVE}),
    ExecutionAction.ADJUSTMENT: frozenset({VersionState.PROPOSED}),
    ExecutionAction.EXIT: frozenset({VersionState.ACTIVE}),
}

# ADR-037: exits stay open to a Limited user; everything else needs Pro.
ACTIONS_NEEDING_PRO: frozenset[ExecutionAction] = frozenset({ExecutionAction.NEW_ENTRY, ExecutionAction.ADJUSTMENT})


class DataInput(Enum):
    """Market-data inputs execution depends on; every one is required (REQ-059 AC-1 "market data healthy")."""

    UNDERLYING_PRICE = "UNDERLYING_PRICE"
    LEG_PRICES = "LEG_PRICES"
    INSTRUMENT_LIST = "INSTRUMENT_LIST"


class DataHealth(Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


REQUIRED_DATA_INPUTS: tuple[DataInput, ...] = tuple(DataInput)


class MarginPlanner(Protocol):
    """Estimates the margin a strategy needs; Zerodha's own figure stays final (ADR-016)."""

    def required_margin(self, strategy: Strategy) -> Decimal: ...


def margin_required_from(planner: MarginPlanner, strategy: Strategy) -> Decimal:
    """Ask ``planner`` for the strategy's margin and validate its answer (finite, non-negative Decimal)."""
    return require_decimal(planner.required_margin(strategy), "margin_required")


def _tristate(value: object, name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{name} must be True, False or None (unknown), got {value!r}")


def _optional_decimal(value: object, name: str) -> None:
    if value is not None:
        require_decimal(value, name)


@dataclass(frozen=True)
class ExecutionContext:
    """All inputs to the pre-execution gate for one strategy and one action. Immutable once built."""

    strategy_id: str
    underlying: str
    action: ExecutionAction
    as_of: datetime.datetime
    market_open: bool | None
    broker_connected: bool | None
    session_valid: bool | None
    pro_entitled: bool | None
    version_state: VersionState | None
    rules_valid: bool | None
    dependencies_satisfied: bool | None
    data_health: Mapping[DataInput, DataHealth]
    margin_available: Decimal | None
    margin_required: Decimal | None
    reconciliation_blocked_strategy_ids: frozenset[str] = field(default_factory=frozenset)
    charges_estimate: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError(f"strategy_id must be a non-empty string, got {self.strategy_id!r}")
        if not isinstance(self.underlying, str) or not self.underlying.strip():
            raise ValueError(f"underlying must be a non-empty string, got {self.underlying!r}")
        if not isinstance(self.action, ExecutionAction):
            raise ValueError(f"action must be an ExecutionAction, got {self.action!r}")
        if not isinstance(self.as_of, datetime.datetime) or self.as_of.utcoffset() is None:
            raise ValueError(f"as_of must be a timezone-aware datetime, got {self.as_of!r}")
        for name in (
            "market_open", "broker_connected", "session_valid", "pro_entitled", "rules_valid", "dependencies_satisfied"
        ):
            _tristate(getattr(self, name), name)
        if self.version_state is not None and not isinstance(self.version_state, VersionState):
            raise ValueError(f"version_state must be a VersionState or None, got {self.version_state!r}")
        if not isinstance(self.data_health, Mapping):
            raise ValueError(f"data_health must be a mapping of DataInput to DataHealth, got {self.data_health!r}")
        for key, value in self.data_health.items():
            if not isinstance(key, DataInput):
                raise ValueError(f"unknown data_health input {key!r}; expected one of {[d.value for d in DataInput]}")
            if not isinstance(value, DataHealth):
                raise ValueError(f"data_health[{key.value}] must be a DataHealth, got {value!r}")
        object.__setattr__(self, "data_health", dict(self.data_health))
        for name in ("margin_available", "margin_required", "charges_estimate"):
            _optional_decimal(getattr(self, name), name)
        blocked = self.reconciliation_blocked_strategy_ids
        if isinstance(blocked, str) or not all(isinstance(s, str) for s in blocked):
            raise ValueError("reconciliation_blocked_strategy_ids must be a collection of strategy id strings")
        object.__setattr__(self, "reconciliation_blocked_strategy_ids", frozenset(blocked))
