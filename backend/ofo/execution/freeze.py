"""The freeze-limit check on the order review (ADR-081, REQ-054 AC-4, findings F-36).

Basis, ADR-081: "A leg whose quantity is above the contract's freeze limit is blocked on the order review with the
reason and the limit, never split." and "While no freeze limit is stored for a contract, the review warns that Zerodha
may reject a large order." F-36: ``MaxTradQty`` is the limit and the largest allowed order is ``MaxTradQty - 1``, so a
leg is allowed exactly when its units are BELOW the stored limit.

``limits`` maps a contract's broker trading symbol (the plan's ``contract``) to the stored limit. A symbol with no
entry gets the warning, never a silent pass and never a block. This module never splits a leg.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from ofo.errors import UserFacingError, render
from ofo.execution.planned import ExecutionPlan
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.freeze_limits import StoredFreeze, largest_allowed_units
from ofo.instruments.models import ZERODHA, InstrumentId

STALE_AFTER_DAYS: Final = 8  # issue 257, ADR-091: the review warns when the file date is MORE than 8 days before it


@dataclass(frozen=True)
class FreezeFinding:
    leg_ref: str
    contract: str
    message: UserFacingError


@dataclass(frozen=True)
class FreezeCheck:
    blocks: tuple[FreezeFinding, ...]
    warnings: tuple[FreezeFinding, ...]


def freeze_limits_for_plan(plan: ExecutionPlan, catalogue: Catalogue,
                           stored: Mapping[InstrumentId, tuple[int, date]]) -> dict[str, StoredFreeze]:
    """The review's input, built from the store: for each plan contract, the catalogue entry that carries that Zerodha
    trading symbol (exactly one; none or several = no entry, so the warning), its stored (limit, file date) by
    ``InstrumentId``, and the LOT from the catalogue contract, never from the caller."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"freeze_limits_for_plan needs an ExecutionPlan, got {plan!r}")
    out: dict[str, StoredFreeze] = {}
    for planned in plan.legs:
        entries = catalogue.entries_for_broker_symbol(ZERODHA, planned.contract)
        if len(entries) != 1 or entries[0].id not in stored:
            continue
        limit, file_date = stored[entries[0].id]
        out[planned.contract] = StoredFreeze(limit, entries[0].contract.lot_size, file_date)
    return out


def freeze_check(plan: ExecutionPlan, limits: Mapping[str, StoredFreeze] | None, *, today: date) -> FreezeCheck:
    """Block each leg whose units are not below its stored limit; warn for each leg with no stored limit, and for a
    stored limit whose file date is more than ``STALE_AFTER_DAYS`` before ``today`` (the stale limit still blocks).
    ``today`` is required (no default, so the age check cannot be skipped by omission)."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"freeze_check needs an ExecutionPlan, got {plan!r}")
    stored_limits = {} if limits is None else limits
    blocks: list[FreezeFinding] = []
    warnings: list[FreezeFinding] = []
    for planned in plan.legs:
        units = planned.leg.quantity
        stored = stored_limits.get(planned.contract)
        if stored is None:
            warnings.append(FreezeFinding(planned.leg_ref, planned.contract,
                                          render("freeze_limit_unknown", contract=planned.contract)))
            continue
        if units % stored.lot != 0:
            raise ValueError(f"{planned.contract}: {units} units is not a whole number of lots of {stored.lot}")
        if not units < stored.limit:
            top = largest_allowed_units(stored)
            blocks.append(FreezeFinding(planned.leg_ref, planned.contract, render(
                "freeze_limit_exceeded", contract=planned.contract, units=units, lots=units // stored.lot,
                max_units=top, max_lots=top // stored.lot, limit=stored.limit)))
        age = (today - stored.file_date).days
        if age > STALE_AFTER_DAYS:
            warnings.append(FreezeFinding(planned.leg_ref, planned.contract, render(
                "freeze_limit_stale", contract=planned.contract, file_date=stored.file_date, days=age)))
    return FreezeCheck(tuple(blocks), tuple(warnings))


__all__ = ["STALE_AFTER_DAYS", "FreezeCheck", "FreezeFinding", "StoredFreeze", "freeze_check", "freeze_limits_for_plan", "largest_allowed_units"]
