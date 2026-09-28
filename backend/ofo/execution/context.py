"""Execution context: every outside fact the pre-execution gate needs, supplied as input (REQ-059 AC-1).

Nothing here calls Zerodha or the network. Each status input is ``True`` (confirmed), ``False`` (confirmed not) or
``None`` (could not be confirmed); only ``True`` passes, so a missing fact fails closed. A wrong type raises
``ValueError`` at construction, never defaults.

Decisions (orchestrator decisions under ADR-045, W-014 fix round 1; spec basis in each line):

- **Versions.** A NEW_ENTRY or EXIT executes the strategy's ACTIVE version (its current configuration); an ADJUSTMENT
  executes the PROPOSED version (ADR-019 Q191: a proposed version becomes active only after execution +
  reconciliation). A SUPERSEDED version is never executed.
- **Entitlement by actor intent (ADR-037).** A Limited user may exit, and an adjustment made ONLY of closing or
  reducing orders on legs of the active strategy (no new contract, no quantity increase, no side flip) is a partial
  exit, so it is allowed too. Anything else (new entry, risk-adding or rolling adjustment) needs Pro. The adjustment is
  classified from the legs, before (``active_legs``) vs after (the proposed strategy), never from a user flag.
  ``pro_entitled`` is the entitlement layer's answer, passed in as a boolean; this module does not import that layer.
- **Unknown eligibility blocks.** A contract with no recorded Zerodha eligibility read is not executable (fail closed,
  matching ``EligibilityRegistry.is_tradable``).
- **Duplicate legs block, never merged.** The same contract twice is reported; the user edits the strategy.
- **A reconciliation mismatch blocks exits too.** ADR-019 Q200 (Reconciliation Required: execute no): acting on a
  wrong position picture could open an unintended naked position; the user can still act in Kite. REQ-060 AC-7: a
  mismatch blocks only its own strategy and standalone positions are never mismatches, so the gate asks only whether
  THIS ``strategy_id`` is in ``reconciliation_blocked_strategy_ids``.
- **No quantity cap beyond margin.** Zerodha's RMS is the authority on order size (ADR-016); the margin gate is the
  platform's only upper bound.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Protocol

from ofo.engine import Leg, Strategy
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
    version_id: str
    actor: str
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
    active_legs: tuple[Leg, ...] | None = None  # the active version's legs; needed to classify an ADJUSTMENT

    def __post_init__(self) -> None:
        for name in ("strategy_id", "version_id", "actor", "underlying"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string, got {value!r}")
        if self.active_legs is not None:
            if isinstance(self.active_legs, (str, bytes)) or not all(isinstance(x, Leg) for x in self.active_legs):
                raise ValueError("active_legs must be a collection of Leg or None")
            object.__setattr__(self, "active_legs", tuple(self.active_legs))
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
