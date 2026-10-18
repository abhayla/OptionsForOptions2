"""The freeze-limit check on the order review (ADR-081, REQ-054 AC-4, findings F-36).

Basis, ADR-081: "A leg whose quantity is above the contract's freeze limit is blocked on the order review with the
reason and the limit, never split." and "While no freeze limit is stored for a contract, the review warns that Zerodha
may reject a large order." F-36: ``MaxTradQty`` is the limit and the largest allowed order is ``MaxTradQty - 1``, so a
leg is allowed exactly when its units are BELOW the stored limit.

``limits`` maps a contract's broker trading symbol (the plan's ``contract``) to the stored limit. A symbol with no
entry gets the warning, never a silent pass and never a block. This module never splits a leg.

ADR-092: "Complete, Retry and exit orders follow it too." and "The fixed 1,755-unit placeholder used for slicing is
removed; the stored limit (ADR-081, ADR-091) is the only freeze figure." ``require_within_freeze`` is the ONE check every
order-preparing path calls (Complete, Retry, exit, the reconciliation closing proposal, the rule-action proposal); the
review's ``freeze_check`` uses the same ``exceeded_message``. Allow-list: an order is allowed only when a stored limit
is present, is a ``StoredFreeze``, the units are a positive whole number of its lots and below the limit; anything else
is refused. In those paths a missing limit BLOCKS (fail closed, issue 255): nothing is prepared without a known limit.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from ofo.errors import UserFacingError, render
from ofo.errors.user_facing import UserFacing
from ofo.execution.planned import ExecutionPlan
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA, InstrumentId

STALE_AFTER_DAYS: Final = 8  # issue 257, ADR-091: the review warns when the file date is MORE than 8 days before it


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


def largest_allowed_units(stored: StoredFreeze) -> int:
    """The largest whole-lot order below the limit (NIFTY: 3,511 and lot 65 -> 3,510 = 54 lots)."""
    return (stored.limit - 1) // stored.lot * stored.lot


def exceeded_message(contract: str, units: int, stored: StoredFreeze) -> UserFacingError | None:
    """The block message when ``units`` is not below ``stored.limit`` (with the largest allowed order), else None.
    ``units`` must be a positive whole number of ``stored.lot`` (ValueError otherwise: a programmer or data error)."""
    if not isinstance(stored, StoredFreeze):
        raise ValueError(f"a freeze limit must be a StoredFreeze, got {stored!r}")
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError(f"{contract}: units must be a positive integer, got {units!r}")
    if units % stored.lot != 0:
        raise ValueError(f"{contract}: {units} units is not a whole number of lots of {stored.lot}")
    if units < stored.limit:
        return None
    top = largest_allowed_units(stored)
    return render("freeze_limit_exceeded", contract=contract, units=units, lots=units // stored.lot,
                  max_units=top, max_lots=top // stored.lot, limit=stored.limit)


class FreezeRefused(UserFacing, ValueError):
    """An order not prepared because of the freeze limit (above it, or no stored limit). ``str(error)`` is the
    developer detail; ``message`` is the catalogue message a user is shown."""

    def __init__(self, *, detail: str, message: UserFacingError) -> None:
        if type(message) is not UserFacingError:
            raise TypeError(f"FreezeRefused needs a UserFacingError from render(), got {type(message).__name__}")
        super().__init__(detail)
        self.message = message


@dataclass(frozen=True)
class ContractFreeze:
    """A stored limit with the exchange trading symbol it was stored for (for builders that key orders by contract
    terms, not by symbol)."""

    symbol: str
    stored: StoredFreeze


def require_within_freeze(contract: str | None, units: int, stored: StoredFreeze | None) -> None:
    """THE order check (ADR-092): return only when ``units`` may go as ONE order; raise ``FreezeRefused`` otherwise.
    ``contract`` is the trading symbol, or None when the caller has no symbol (only possible with no stored limit)."""
    if stored is None:
        message = (render("freeze_limit_missing", contract=contract) if contract is not None
                   else render("freeze_limit_missing_unnamed"))
        raise FreezeRefused(detail=f"{contract}: no stored freeze limit; nothing prepared", message=message)
    if contract is None:
        raise ValueError("a stored freeze limit needs the trading symbol it was stored for")
    message = exceeded_message(contract, units, stored)
    if message is not None:
        raise FreezeRefused(detail=f"{contract}: {units} units is not below the freeze limit {stored.limit}",
                            message=message)


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
        exceeded = exceeded_message(planned.contract, units, stored)
        if exceeded is not None:
            blocks.append(FreezeFinding(planned.leg_ref, planned.contract, exceeded))
        age = (today - stored.file_date).days
        if age > STALE_AFTER_DAYS:
            warnings.append(FreezeFinding(planned.leg_ref, planned.contract, render(
                "freeze_limit_stale", contract=planned.contract, file_date=stored.file_date, days=age)))
    return FreezeCheck(tuple(blocks), tuple(warnings))


__all__ = ["STALE_AFTER_DAYS", "ContractFreeze", "FreezeCheck", "FreezeFinding", "FreezeRefused", "StoredFreeze",
           "exceeded_message", "freeze_check", "freeze_limits_for_plan", "largest_allowed_units",
           "require_within_freeze"]
