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
- ``ofo.execution.safety.check_pre_execution`` (W-014/REQ-059): THIS module calls the gate itself, on this
  record's own pending proposal (``prepare_confirmed_modification`` / ``execute_confirmed_modification``). No
  public function here accepts a caller-supplied ``SafetyResult`` -- a hand-built "always passes" verdict cannot
  be injected, because none of these functions take one as input.

Change model (AC-1): a proposal is a tuple of ``LegChange``, each naming a *slot* -- (instrument, strike, expiry) --
of the ACTIVE version's own definition. ADD is refused if the slot already exists; REMOVE and RESIZE are refused
unless the slot already exists in the active definition. The resulting definition is built with
``dataclasses.replace`` on the active definition, so every added leg is merged into that same strategy object: there
is no function in this module that can hand back a leg not attached to a ``StrategyDefinition``, so a leg can never
be constructed as a standalone, unrelated trade.

Strategy Guard (W-026, REQ-036 AC-5, ADR-002): ``propose_modification`` runs the record's own guard on the same
engine Before/After it shows, bound to (strategy id, active version, hash of the active and proposed definitions).
``prepare_confirmed_modification`` refuses unless the guard checked exactly this proposal and, when the risk profile
changes, the caller hands back that decision's own acknowledgement; ``execute_confirmed_modification`` consumes it.
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
from ofo.execution.alternatives import gate_inputs_from_record
from ofo.execution.context import ExecutionAction, ExecutionContext
from ofo.execution.safety import SafetyResult, check_pre_execution
from ofo.instruments import Catalogue, EligibilityRegistry
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.guard import GuardBinding, GuardDecision, proposal_hash
from ofo.strategy.versions import ExecutionOutcome, ExecutionResult, StrategyRecord, Version

_ZERO = Decimal("0.00")

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
    guard: GuardDecision  # REQ-036 AC-5: message + consequences + (when flagged) the acknowledgement token


def propose_modification(
    record: StrategyRecord,
    changes: tuple[LegChange, ...],
    *,
    strategy_id: str,
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
    before_strategy = Strategy(_engine_legs(active_def, entry_prices, ltps))
    after_strategy = Strategy(_engine_legs(new_def, entry_prices, ltps))
    before = _side_metrics(before_strategy, margin_planner, charges_model)
    after = _side_metrics(after_strategy, margin_planner, charges_model)
    binding = _guard_binding(strategy_id, active, new_def)
    decision = record.guard._issue(binding, before_strategy, after_strategy, before.margin, after.margin)
    return ModificationComparison(active.number, description, before, after, decision)


def _definition_rows(definition: StrategyDefinition) -> list[list[str]]:
    return sorted(
        [d.action.value, d.instrument.value, "" if d.strike is None else format(d.strike.normalize(), "f"),
         d.expiry.isoformat(), str(d.quantity)]
        for d in definition.legs
    )


def _guard_binding(strategy_id: object, active: Version, proposed: StrategyDefinition) -> GuardBinding:
    """The Strategy Guard binding of a modification: this strategy, its active version, this exact change."""
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ModificationError(f"strategy_id must be a non-empty string, got {strategy_id!r}")
    payload = {"strategy_id": strategy_id, "active_version": active.number, "underlying": proposed.underlying,
               "active": _definition_rows(active.definition), "proposed": _definition_rows(proposed)}
    return GuardBinding(strategy_id, f"v{active.number}", proposal_hash(payload))


def _pending_binding(record: StrategyRecord, strategy_id: str) -> GuardBinding:
    active, proposed = record.active_version, record.proposed_version
    if active is None or proposed is None:
        raise ModificationError("no active version with a pending proposal to check")
    return _guard_binding(strategy_id, active, proposed.definition)


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


def _gate_legs(definition: StrategyDefinition) -> tuple[Leg, ...]:
    """Legs for the REQ-059 gate: option premiums excluded (0.00), matching ``gate_inputs_from_record``'s own
    convention (rule 5 excludes premiums from every adjustment check). Futures are out of scope for this module."""
    legs = []
    for d in definition.legs:
        if d.instrument is Instrument.FUT:
            raise ModificationError("a futures leg's gate entry price is not supported by this module yet")
        legs.append(Leg(d.action, d.instrument, d.strike, d.expiry, d.quantity, _ZERO))
    return tuple(legs)


def prepare_confirmed_modification(
    record: StrategyRecord,
    version_number: int,
    *,
    strategy_id: str,
    context: ExecutionContext,
    catalogue: Catalogue,
    eligibility: EligibilityRegistry,
    acknowledgement: str | None = None,
) -> SafetyResult:
    """Run the REQ-059 gate on THIS record's own pending proposal (AC-4). The ONLY way to learn whether an
    adjustment may execute: there is no public function in this module that accepts a caller-supplied verdict.

    ``context`` supplies the outside facts the gate needs (market/broker/session/margin/etc., ``action`` must be
    ``ADJUSTMENT`` and ``version_id`` must name ``version_number``); the active-version identity fields
    (``active_legs``, ``active_version_id``, ``active_legs_hash``, ``active_futures_entry_known``) and
    ``strategy_id`` are always computed HERE from ``record`` itself (``gate_inputs_from_record``) and overwrite
    whatever ``context`` carries, so a forged identity cannot be injected through it either.
    """
    if not isinstance(record, StrategyRecord):
        raise ModificationError(f"record must be a StrategyRecord, got {record!r}")
    proposed = record.proposed_version
    if proposed is None or proposed.number != version_number:
        raise ModificationError(f"version {version_number!r} is not the pending proposed version of this record")
    if not isinstance(context, ExecutionContext):
        raise ModificationError(f"context must be an ExecutionContext, got {context!r}")
    if context.action is not ExecutionAction.ADJUSTMENT:
        raise ModificationError("a modification proposal executes as an ExecutionAction.ADJUSTMENT")
    if context.version_id != f"v{proposed.number}":
        raise ModificationError(f"context.version_id must be 'v{proposed.number}' for this proposal")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ModificationError(f"strategy_id must be a non-empty string, got {strategy_id!r}")
    # REQ-036 AC-5: the record's own guard must have checked THIS proposal; a flagged one needs its own token.
    record.guard.check(_pending_binding(record, strategy_id), acknowledgement)
    identity = gate_inputs_from_record(record, strategy_id=strategy_id)
    grounded_context = dataclasses.replace(context, strategy_id=strategy_id, **identity)
    strategy = Strategy(_gate_legs(proposed.definition))
    return check_pre_execution(strategy, grounded_context, catalogue, eligibility, strategy_id=strategy_id)


def execute_confirmed_modification(
    record: StrategyRecord,
    version_number: int,
    *,
    strategy_id: str,
    context: ExecutionContext,
    catalogue: Catalogue,
    eligibility: EligibilityRegistry,
    result: ExecutionResult,
    acknowledgement: str | None = None,
) -> ExecutionOutcome:
    """Apply a broker execution result for the confirmed proposal, ONLY when the REQ-059 gate -- run HERE, on this
    record's own pending proposal -- passes (AC-4). The gate runs exactly once per call, via
    ``prepare_confirmed_modification``; there is no parameter through which a caller can hand in a verdict instead
    of letting this function compute one, and no way to name a different strategy or version than the one this
    record actually has pending.

    A blocked gate is refused before ``StrategyRecord.apply_result`` is ever called: no order is treated as
    prepared, and the active version (v1, or whichever version is currently active) is left exactly as it was.

    A result for an attempt that is not the record's live one (a late message of an earlier attempt, W-041 round 5)
    is handed straight to the record, which records it as STALE and changes nothing; it neither runs the gate nor
    spends the acknowledgement.
    """
    if not isinstance(record, StrategyRecord):
        raise ModificationError(f"record must be a StrategyRecord, got {record!r}")
    if isinstance(result, ExecutionResult) and result.attempt != record.live_attempt:
        return record.apply_result(result)
    safety = prepare_confirmed_modification(
        record, version_number, strategy_id=strategy_id, context=context, catalogue=catalogue, eligibility=eligibility,
        acknowledgement=acknowledgement,
    )
    if safety.blocked:
        reasons = "; ".join(f.reason for f in safety.failures)
        raise ModificationError(
            f"execution is blocked by the pre-execution gate; no order has been prepared and the active version is "
            f"unchanged: {reasons}"
        )
    record.guard.redeem(_pending_binding(record, strategy_id), acknowledgement)  # single use (REQ-036 AC-5)
    return record.apply_result(result)
