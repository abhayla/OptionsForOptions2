"""Execution context: every outside fact the pre-execution gate needs, supplied as input (REQ-059 AC-1).

Nothing here calls Zerodha or the network. Each status input is ``True`` (confirmed), ``False`` (confirmed not) or
``None`` (could not be confirmed); only ``True`` passes, so a missing fact fails closed. A wrong type raises
``ValueError`` at construction, never defaults.

Decisions (orchestrator decisions under ADR-045, W-014 fix round 1; spec basis in each line):

- **Versions.** A NEW_ENTRY or EXIT executes the strategy's ACTIVE version (its current configuration); an ADJUSTMENT
  executes the PROPOSED version (ADR-019 Q191: a proposed version becomes active only after execution +
  reconciliation). A SUPERSEDED version is never executed.
- **Entitlement by actor intent (ADR-037 "risk-adding adjustments stay behind Pro"; REQ-059 Gate decisions rule 5,
  a SPEC CHANGE recorded by the orchestrator, fix round 3).** A Limited user may exit. A Limited user may run an
  adjustment only if (a) no position grows (no new contract, no quantity increase, no side flip) AND one of:
  (c) every leg is reduced by the same share; (d) for a multi-expiry strategy (calendar), only short options are
  closed or reduced; (b) for a single-expiry strategy, the worst case AT EXPIRY with OPTION PREMIUMS EXCLUDED
  (options at intrinsic value, entry price 0; futures level - entry) is no worse after than before, taken at level
  0, every strike and the upper tail via the engine's ``strategy_metrics``. An UNLIMITED after is allowed only if
  before was UNLIMITED, the upper-tail slope is not steeper, and the worst case at level 0 and every strike is not
  lower. Why premium-free: the entry-price worst case adds each open leg's entry credit, so closing any credit piece
  looked riskier even when real risk fell (2-lot condor put-spread close: -14,170 -> -19,825 with premiums,
  -26,000 -> -26,000 without). Classified from the legs, before (``active_legs``) vs after (the proposed strategy),
  never from a user flag; no active legs to compare needs Pro (fail closed).
  ``pro_entitled`` is the entitlement layer's answer, passed in as a boolean; this module does not import that layer.
- **An EXIT must really be an exit (Tier A review MAJOR 1).** Every exit order closes or reduces a position the
  strategy holds (``active_legs``): same contract, opposite side, never more than held. No active legs, or any order
  that would open or add to a position, blocks with ``EXIT_NOT_REDUCE_ONLY`` on every plan, Pro included.
- **What an EXIT needs (SPEC CHANGE to REQ-059 AC-1, review MAJOR 2, ADR-045).** Required: market open, broker
  connected, session valid, every contract exists in the catalogue, quantities valid (reduce-only, positive, whole
  lots), no unresolved reconciliation mismatch for this strategy, dependencies satisfied. Not required: margin (an
  exit frees margin), eligibility (closing orders are not fresh positions), rule validity, entitlement. Unhealthy
  data is a warning ("Prices shown may be stale — confirm to continue."), never a block. Entries and adjustments keep
  every check. Checks still applied to an exit and not named in that decision: version state, supported
  underlying, expiry not passed, contract still listed, no duplicate legs.
- **Active legs are verified, never trusted (adversarial round 2 MAJOR A).** The CALLER MUST read ``active_legs``
  from the stored active version (W-012's ``Version`` intended position) together with that version's id and its
  ``active_legs_hash(strategy_id, active_version_id, legs)``; the integration work item wires this. The gate
  recomputes the hash from the supplied legs and the executed strategy's id and blocks with
  ``ACTIVE_LEGS_UNVERIFIED`` on a mismatch or when the version id or hash is missing. Unverified legs are never
  used for the exit reduce-only check or the Limited-user entitlement decision.
- **Reconciliation status is required (round 2 MAJOR B).** ``reconciliation_blocked_strategy_ids`` has no
  default; ``None`` means unknown and blocks with ``RECONCILIATION_MISMATCH`` ("Reconciliation status unknown").
- **An exit on unhealthy data needs confirmation (round 2 MINOR).** The result carries
  ``requires_confirmation=True`` and the warning text; checks that do not apply to the action are listed as
  not applicable, never as passed.
- **The context belongs to one strategy (review Q4).** ``check_pre_execution`` takes the executed strategy's id and
  blocks with ``STRATEGY_MISMATCH`` when the context names another. Mappings in the context are read-only.
- **An internal error never passes (review P10).** Any exception inside the checks blocks with ``INTERNAL_ERROR``
  and still carries the blocked-execution record.
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
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
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
    # Required, no default (round 2 MAJOR B): None means the reconciliation status is unknown and blocks.
    reconciliation_blocked_strategy_ids: frozenset[str] | None
    charges_estimate: Decimal | None = None
    # The active version's intended position, read by the caller from the stored active version; trusted only
    # when ``active_legs_hash(strategy_id, active_version_id, active_legs)`` equals ``active_legs_hash``.
    active_legs: tuple[Leg, ...] | None = None
    active_version_id: str | None = None
    active_legs_hash: str | None = None

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
        object.__setattr__(self, "data_health", MappingProxyType(dict(self.data_health)))
        for name in ("margin_available", "margin_required", "charges_estimate"):
            _optional_decimal(getattr(self, name), name)
        blocked = self.reconciliation_blocked_strategy_ids
        if blocked is not None:
            if isinstance(blocked, str) or not all(isinstance(s, str) for s in blocked):
                raise ValueError("reconciliation_blocked_strategy_ids must be a collection of strategy id strings")
            object.__setattr__(self, "reconciliation_blocked_strategy_ids", frozenset(blocked))
        for name in ("active_version_id", "active_legs_hash"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None, got {value!r}")


def _canonical_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def active_legs_hash(strategy_id: str, active_version_id: str, legs: tuple[Leg, ...]) -> str:
    """Canonical SHA-256 of a stored active version's intended position (round 2 MAJOR A).

    The one function that both the version store's reader and the gate use. It covers the strategy id, the version
    id and the net units per (contract, side); leg order and a position split across legs do not change it.
    """
    units: dict[tuple[str, str, str, str], int] = {}
    for leg in legs:
        strike = "" if leg.strike is None else _canonical_decimal(leg.strike)
        key = (leg.expiry.isoformat(), leg.instrument.value, strike, leg.action.value)
        units[key] = units.get(key, 0) + leg.quantity
    payload = {
        "strategy_id": strategy_id,
        "active_version_id": active_version_id,
        "positions": [[*key, units[key]] for key in sorted(units)],
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()
