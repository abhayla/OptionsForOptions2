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

from ofo.errors import UserFacingError, render
from ofo.execution.planned import ExecutionPlan


@dataclass(frozen=True)
class StoredFreeze:
    """A freeze limit in units, the contract's lot size, and the date of the exchange file that showed it."""

    limit: int
    lot: int
    file_date: date

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {self.limit!r}")
        if isinstance(self.lot, bool) or not isinstance(self.lot, int) or self.lot <= 0:
            raise ValueError(f"lot must be a positive integer, got {self.lot!r}")


@dataclass(frozen=True)
class FreezeFinding:
    leg_ref: str
    contract: str
    message: UserFacingError


@dataclass(frozen=True)
class FreezeCheck:
    blocks: tuple[FreezeFinding, ...]
    warnings: tuple[FreezeFinding, ...]


def largest_allowed_units(stored: StoredFreeze) -> int:
    """The largest whole-lot order below the limit (NIFTY: 3,511 and lot 65 -> 3,510 = 54 lots)."""
    return (stored.limit - 1) // stored.lot * stored.lot


def freeze_check(plan: ExecutionPlan, limits: Mapping[str, StoredFreeze] | None) -> FreezeCheck:
    """Block each leg whose units are not below its stored limit; warn for each leg with no stored limit."""
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
        elif not units < stored.limit:
            top = largest_allowed_units(stored)
            blocks.append(FreezeFinding(planned.leg_ref, planned.contract, render(
                "freeze_limit_exceeded", contract=planned.contract, units=units, lots=units // stored.lot,
                max_units=top, max_lots=top // stored.lot, limit=stored.limit)))
    return FreezeCheck(tuple(blocks), tuple(warnings))


__all__ = ["FreezeCheck", "FreezeFinding", "StoredFreeze", "freeze_check", "largest_allowed_units"]
