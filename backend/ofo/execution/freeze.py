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
review's ``freeze_check`` uses the same ``_assess``. Only a USABLE known limit (a ``StoredFreeze`` that allows at
least one whole lot) the units are not below blocks, with the limit and the largest allowed order. A limit that is
missing, None, or allows no whole lot (bad stored data, e.g. 64 for NIFTY lot 65) never blocks
on any path: every path gets the review's ``freeze_limit_unknown`` warning (ADR-081 "the review warns"; ADR-037). A
usable limit whose exchange file is more than ``STALE_AFTER_DAYS`` old also warns on every path (the limit still
applies).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
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
        try:
            found = StoredFreeze(limit, entries[0].contract.lot_size, file_date)
        except ValueError:  # bad stored data (zero, negative, not a whole number): no entry, so the review warns
            continue
        out[planned.contract] = found
    return out


def _require_stored_type(stored: object) -> None:
    """Allow-list for every entry that takes ``stored``: exactly a ``StoredFreeze`` or None (None = limit unknown).
    Any other type is a programmer error (a raw int, a str, a duck object), never "limit unknown": TypeError."""
    if stored is not None and not isinstance(stored, StoredFreeze):
        raise TypeError(f"a stored freeze limit must be a StoredFreeze or None, got {type(stored).__name__}")


def largest_allowed_units(stored: StoredFreeze) -> int:
    """The largest whole-lot order below the limit (NIFTY: 3,511 and lot 65 -> 3,510 = 54 lots)."""
    if not isinstance(stored, StoredFreeze):
        raise TypeError(f"a stored freeze limit must be a StoredFreeze, got {type(stored).__name__}")
    return (stored.limit - 1) // stored.lot * stored.lot


def exceeded_message(contract: str, units: int, stored: StoredFreeze) -> UserFacingError | None:
    """The block message when ``units`` is not below ``stored.limit`` (with the largest allowed order), else None.
    ``units`` must be a positive whole number of ``stored.lot`` (ValueError otherwise: a programmer or data error)."""
    if not isinstance(stored, StoredFreeze):
        raise TypeError(f"a freeze limit must be a StoredFreeze, got {type(stored).__name__}")
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
    """A contract's exchange trading symbol and its stored limit, None while none is stored (for builders that key
    orders by contract terms, not by symbol). Every contract of a proposal must have one: the symbol names the
    warning or the block."""

    symbol: str
    stored: StoredFreeze | None

    def __post_init__(self) -> None:
        _require_stored_type(self.stored)


def usable(stored: object) -> StoredFreeze | None:
    """``stored`` when it is a ``StoredFreeze`` that allows at least one whole lot below its limit, else None (bad
    stored data such as 64 for NIFTY lot 65 would block even a 1-lot exit: it is treated as no limit, so it warns).
    None is "limit unknown"; any other non-``StoredFreeze`` is a programmer error: TypeError."""
    _require_stored_type(stored)
    if stored is None or largest_allowed_units(stored) < stored.lot:
        return None
    return stored


def terms_symbol(*parts: object) -> str:
    """A contract named from its terms, for a warning when the caller gave no trading symbol: the parts joined by
    ``-`` in capitals (``NIFTY-CE-23600-20261027``); a strike's decimal point is written ``-`` (the slot allows no ``.``)."""
    text = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, date):
            text.append(part.strftime("%Y%m%d"))
        elif isinstance(part, Enum):  # an Instrument
            text.append(str(part.value))
        elif isinstance(part, Decimal):
            text.append(format(part.normalize(), "f").replace(".", "-"))
        else:
            text.append(str(part))
    return "-".join(text).upper()[:40]


def _assess(contract: str, units: int, stored: object, today: date,
            ) -> tuple[UserFacingError | None, tuple[UserFacingError, ...]]:
    """(the block message or None, the warnings) for ``units`` of ``contract`` as ONE order: the shared rule of the
    review and every order-preparing path."""
    _require_stored_type(stored)
    if not isinstance(today, date) or isinstance(today, datetime):
        raise ValueError(f"today must be a date, got {today!r}")
    known = usable(stored)
    if known is None:
        return None, (render("freeze_limit_unknown", contract=contract),)
    block = exceeded_message(contract, units, known)
    age = (today - known.file_date).days
    if age > STALE_AFTER_DAYS:
        return block, (render("freeze_limit_stale", contract=contract, file_date=known.file_date, days=age),)
    return block, ()


def require_within_freeze(contract: str, units: int, stored: object, *, today: date) -> tuple[UserFacingError, ...]:
    """THE order check (ADR-092): ``units`` of ``contract`` (its trading symbol) go as ONE order. A USABLE known stored
    limit the units are not below raises ``FreezeRefused`` (with the limit and the largest allowed order). Returns the
    warnings: no usable stored limit (ADR-081 "the review warns that Zerodha may reject a large order"; ADR-037: never
    stop a user getting out of risk), or a stale one (file more than ``STALE_AFTER_DAYS`` before ``today``)."""
    block, warnings = _assess(contract, units, stored, today)
    if block is not None:
        limit = stored.limit if isinstance(stored, StoredFreeze) else None
        raise FreezeRefused(detail=f"{contract}: {units} units is not below the freeze limit {limit}",
                            message=block)
    return warnings


def freeze_check(plan: ExecutionPlan, limits: Mapping[str, StoredFreeze] | None, *, today: date) -> FreezeCheck:
    """Block each leg whose units are not below its usable stored limit; warn for each leg with no usable stored
    limit (``usable``), and for a stored limit whose file date is more than ``STALE_AFTER_DAYS`` before ``today`` (the stale limit still blocks).
    ``today`` is required (no default, so the age check cannot be skipped by omission)."""
    if not isinstance(plan, ExecutionPlan):
        raise ValueError(f"freeze_check needs an ExecutionPlan, got {plan!r}")
    stored_limits = {} if limits is None else limits
    blocks: list[FreezeFinding] = []
    warnings: list[FreezeFinding] = []
    for planned in plan.legs:
        block, found = _assess(planned.contract, planned.leg.quantity, stored_limits.get(planned.contract), today)
        if block is not None:
            blocks.append(FreezeFinding(planned.leg_ref, planned.contract, block))
        warnings.extend(FreezeFinding(planned.leg_ref, planned.contract, w) for w in found)
    return FreezeCheck(tuple(blocks), tuple(warnings))


__all__ = ["STALE_AFTER_DAYS", "ContractFreeze", "FreezeCheck", "FreezeFinding", "FreezeRefused", "StoredFreeze",
           "exceeded_message", "freeze_check", "freeze_limits_for_plan", "largest_allowed_units",
           "require_within_freeze", "terms_symbol", "usable"]
