"""Strategy modification: a proposed leg change to the active version, priced by the engine, applied only on
confirmation and only executed once (REQ-059) allows it.

Spec: REQ-037 AC-1 (a proposal is expressed only against the active version's own legs; a leg can never be traded
as an unrelated standalone trade), AC-2 (the proposal recalculates max profit/loss, breakevens, current P&L, margin
and charges), AC-3 (Before/After is shown before any order is prepared -- this module's ``propose_modification`` is
pure and creates no version), AC-4 (adjustment orders are prepared and executed only after the user confirms AND the
REQ-059 gate passes), AC-5 (every modification creates a new strategy version; old versions are kept). ADR-002
(every order belongs to a strategy). ADR-008 (one engine owns every number; exact Decimal).

Builds on, and does not duplicate:
- ``ofo.strategy.versions.StrategyRecord`` (REQ-038): ``edit()`` already refuses a second proposal while one is
  pending, or while reconciliation is required (``_refuse_while_blocked``); this module relies on that refusal
  rather than re-implementing it.
- ``ofo.engine`` (``strategy_metrics``, ``Strategy``) and ``ofo.engine.interfaces`` (``MarginPlanner``,
  ``ChargesModel``) for every recalculated number.
- ``ofo.execution.safety.check_pre_execution`` (W-014/REQ-059): the caller runs the gate and passes its
  ``SafetyResult`` in; a blocked result never reaches ``StrategyRecord.apply_result``.

Change model (AC-1): a proposal is a tuple of ``LegChange``, each naming a *slot* -- (instrument, strike, expiry) --
of the ACTIVE version's own definition. ADD is refused if the slot already exists; REMOVE and RESIZE are refused
unless the slot already exists in the active definition. The resulting definition is built with
``dataclasses.replace`` on the active definition, so every added leg is merged into that same strategy object: there
is no function in this module that can hand back a leg not attached to a ``StrategyDefinition``, so a leg can never
be constructed as a standalone, unrelated trade.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping

from ofo.engine.interfaces import ChargesModel, MarginPlanner, estimate_charges, plan_margin
from ofo.engine.legs import Action, Instrument, Leg, require_price
from ofo.engine.metrics import StrategyMetrics, _Unlimited, strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.execution.safety import SafetyResult
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import ExecutionOutcome, ExecutionResult, StrategyRecord, Version

#: A leg's identity within a definition, independent of side: which contract it occupies.
Slot = tuple[Instrument, "Decimal | None", datetime.date]


class ModificationError(ValueError):
    """A modification proposal, or the leg change describing it, is not allowed or is invalid."""


class ChangeKind(Enum):
    ADD = "add"
    REMOVE = "remove"
    RESIZE = "resize"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


MAX_UNITS = 1_000_000


@dataclass(frozen=True)
class LegChange:
    """One change to a single contract slot of the active version's definition. Never a bare, unattached leg."""

    kind: ChangeKind
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    action: Action | None = None
    quantity: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ChangeKind):
            raise ModificationError(f"kind must be a ChangeKind, got {self.kind!r}")
        if not isinstance(self.instrument, Instrument):
            raise ModificationError(f"instrument must be an Instrument, got {self.instrument!r}")
        if self.instrument is Instrument.FUT:
            if self.strike is not None:
                raise ModificationError("a futures leg has no strike")
        else:
            try:
                require_price(self.strike, "strike", allow_zero=False)
            except ValueError as exc:
                raise ModificationError(str(exc)) from exc
        if not isinstance(self.expiry, datetime.date) or isinstance(self.expiry, datetime.datetime):
            raise ModificationError(f"expiry must be a datetime.date, got {self.expiry!r}")
        if self.action is not None and not isinstance(self.action, Action):
            raise ModificationError(f"action must be an Action or None, got {self.action!r}")
        if self.kind is ChangeKind.ADD and (self.action is None or self.quantity is None):
            raise ModificationError("an ADD change needs an action and a quantity")
        if self.kind is ChangeKind.RESIZE and self.quantity is None:
            raise ModificationError("a RESIZE change needs a quantity")
        if self.quantity is not None and (not _is_int(self.quantity) or not 0 < self.quantity <= MAX_UNITS):
            raise ModificationError(f"quantity must be an int in 1..{MAX_UNITS} units, got {self.quantity!r}")

    @property
    def slot(self) -> Slot:
        return (self.instrument, self.strike, self.expiry)


def apply_changes(definition: StrategyDefinition, changes: tuple[LegChange, ...]) -> StrategyDefinition:
    """Build the proposed definition: every change resolved against ``definition``'s OWN legs only (AC-1).

    ADD refuses an already-occupied slot; REMOVE and RESIZE refuse a slot the active definition does not hold.
    Two changes on the same slot are refused. The result is a NEW ``StrategyDefinition`` (``dataclasses.replace``),
    so every leg -- kept, resized or newly added -- is always a leg of one strategy: nothing here can produce a leg
    detached from a definition.
    """
    if not isinstance(definition, StrategyDefinition):
        raise ModificationError(f"apply_changes needs a StrategyDefinition, got {definition!r}")
    if not isinstance(changes, tuple) or not changes:
        raise ModificationError("a modification needs at least one leg change")
    for change in changes:
        if not isinstance(change, LegChange):
            raise ModificationError(f"every change must be a LegChange, got {change!r}")
    legs_by_slot: dict[Slot, DefinitionLeg] = {
        (leg.instrument, leg.strike, leg.expiry): leg for leg in definition.legs
    }
    seen: set[Slot] = set()
    for change in changes:
        slot = change.slot
        if slot in seen:
            raise ModificationError(f"two changes name the same contract slot {slot!r}")
        seen.add(slot)
        if change.kind is ChangeKind.ADD:
            if slot in legs_by_slot:
                raise ModificationError(
                    f"cannot add {slot!r}: the active version already holds this contract; use RESIZE"
                )
            legs_by_slot[slot] = DefinitionLeg(change.action, change.instrument, change.strike, change.expiry,
                                                change.quantity)
        elif change.kind is ChangeKind.REMOVE:
            if slot not in legs_by_slot:
                raise ModificationError(f"cannot remove {slot!r}: it is not a leg of the active version")
            del legs_by_slot[slot]
        else:  # RESIZE
            if slot not in legs_by_slot:
                raise ModificationError(f"cannot resize {slot!r}: it is not a leg of the active version")
            existing = legs_by_slot[slot]
            action = existing.action if change.action is None else change.action
            legs_by_slot[slot] = dataclasses.replace(existing, action=action, quantity=change.quantity)
    if not legs_by_slot:
        raise ModificationError("a modification cannot remove every leg; the strategy would have no legs left")
    return dataclasses.replace(definition, legs=tuple(legs_by_slot.values()))


def _engine_legs(
    definition: StrategyDefinition,
    entry_prices: Mapping[Slot, Decimal],
    ltps: Mapping[Slot, Decimal] | None,
) -> tuple:
    if not isinstance(entry_prices, Mapping):
        raise ModificationError(f"entry_prices must be a mapping, got {entry_prices!r}")
    out = []
    for d in definition.legs:
        slot = (d.instrument, d.strike, d.expiry)
        if slot not in entry_prices:
            raise ModificationError(f"no entry price supplied for {d.describe()}")
        ltp = None if ltps is None else ltps.get(slot)
        out.append(Leg(d.action, d.instrument, d.strike, d.expiry, d.quantity, entry_prices[slot], ltp))
    return tuple(out)


@dataclass(frozen=True)
class SideMetrics:
    """One side (Before or After) of a modification comparison. ``None`` + a reason means "unknown", never 0."""

    max_profit: Decimal | _Unlimited
    max_loss: Decimal | _Unlimited
    min_pnl: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]
    current_pnl: Decimal | None
    current_pnl_unknown_reason: str | None
    margin: Decimal | None
    margin_unknown_reason: str | None
    charges: Decimal | None
    charges_unknown_reason: str | None


def _side_metrics(strategy: Strategy, margin_planner: MarginPlanner, charges_model: ChargesModel) -> SideMetrics:
    metrics: StrategyMetrics = strategy_metrics(strategy)
    try:
        current_pnl: Decimal | None = strategy.live_pnl()
        pnl_reason = None
    except ValueError as exc:
        current_pnl, pnl_reason = None, str(exc)
    try:
        margin: Decimal | None = plan_margin(strategy, margin_planner).total
        margin_reason = None
    except Exception as exc:  # a provider fails closed to "unknown", never 0 (reviewer checklist)
        margin, margin_reason = None, str(exc)
    try:
        charges: Decimal | None = estimate_charges(strategy, charges_model).total
        charges_reason = None
    except Exception as exc:
        charges, charges_reason = None, str(exc)
    return SideMetrics(
        max_profit=metrics.max_profit, max_loss=metrics.max_loss, min_pnl=metrics.min_pnl,
        breakevens=metrics.breakevens, current_pnl=current_pnl, current_pnl_unknown_reason=pnl_reason,
        margin=margin, margin_unknown_reason=margin_reason, charges=charges, charges_unknown_reason=charges_reason,
    )


@dataclass(frozen=True)
class ModificationComparison:
    """The Before/After a UI would show (AC-2, AC-3). Read-only: producing this never changes ``record``."""

    active_version_number: int
    changes_description: tuple[str, ...]
    before: SideMetrics
    after: SideMetrics


def propose_modification(
    record: StrategyRecord,
    changes: tuple[LegChange, ...],
    *,
    entry_prices: Mapping[Slot, Decimal],
    ltps: Mapping[Slot, Decimal] | None,
    margin_planner: MarginPlanner,
    charges_model: ChargesModel,
) -> ModificationComparison:
    """Compute the Before/After comparison for ``changes`` against the active version. Creates no version (AC-3).

    ``entry_prices`` must cover every leg of BOTH the active and the proposed definition (existing legs keep their
    real entry price; an added leg's entry price is the price at which the roll is being priced). ``ltps`` may be
    partial or ``None``; a missing LTP makes ``current_pnl`` unknown rather than raising.
    """
    if not isinstance(record, StrategyRecord):
        raise ModificationError(f"record must be a StrategyRecord, got {record!r}")
    active = record.active_version
    if active is None:
        raise ModificationError("no active version to modify; propose and execute the first version instead")
    active_def = active.definition
    new_def = apply_changes(active_def, changes)
    description = new_def.changes_from(active_def)
    if not description:
        raise ModificationError("this change makes no meaningful difference to the active version")
    before = _side_metrics(Strategy(_engine_legs(active_def, entry_prices, ltps)), margin_planner, charges_model)
    after = _side_metrics(Strategy(_engine_legs(new_def, entry_prices, ltps)), margin_planner, charges_model)
    return ModificationComparison(active.number, description, before, after)


def confirm_modification(
    record: StrategyRecord,
    changes: tuple[LegChange, ...],
    *,
    at: datetime.datetime,
    initiator: str = "user",
    reason: str = "",
) -> Version:
    """The user's confirmation: create proposed version N+1 (AC-5) from ``changes`` against the active version, and
    mark it confirmed (AC-4's first half). The active version stays unchanged and active until a broker execution
    result activates the new one (``execute_confirmed_modification``).

    Refuses (``VersionError`` from ``StrategyRecord.edit``, propagated) when a proposal is already pending or
    reconciliation is required -- this module does not re-implement that check, it relies on W-012's.
    """
    if not isinstance(record, StrategyRecord):
        raise ModificationError(f"record must be a StrategyRecord, got {record!r}")
    active = record.active_version
    if active is None:
        raise ModificationError("no active version to modify")
    new_def = apply_changes(active.definition, changes)
    version = record.edit(new_def, at=at, initiator=initiator, reason=reason, based_on=active.number)
    if version is None:
        raise ModificationError("this change makes no meaningful difference to the active version")
    record.confirm(version.number, at=at)
    return version


def execute_confirmed_modification(
    record: StrategyRecord,
    safety: SafetyResult,
    result: ExecutionResult,
) -> ExecutionOutcome:
    """Apply a broker execution result for the confirmed proposal, ONLY when the REQ-059 gate passed (AC-4).

    A blocked ``safety`` is refused before ``StrategyRecord.apply_result`` is ever called: no order is treated as
    prepared, and the active version (v1, or whichever version is currently active) is left exactly as it was.
    """
    if not isinstance(safety, SafetyResult):
        raise ModificationError(f"safety must be a SafetyResult, got {safety!r}")
    if safety.blocked:
        reasons = "; ".join(f.reason for f in safety.failures)
        raise ModificationError(
            f"execution is blocked by the pre-execution gate; no order has been prepared and the active version is "
            f"unchanged: {reasons}"
        )
    if not isinstance(record, StrategyRecord):
        raise ModificationError(f"record must be a StrategyRecord, got {record!r}")
    return record.apply_result(result)
