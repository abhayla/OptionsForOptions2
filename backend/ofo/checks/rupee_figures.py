"""ADR-330 (5): the plan's two figures for one level, percent and rupees, worked out in ONE place (ADR-008: the browser
computes nothing). Rupees are the whole trade before charges (owner Q3); the per-lot figure is shown beside it.
Pure, Decimal only. An unusable base (absent, not finite, not positive, unlimited) -> None figures, never a guess."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from ofo.engine import adjust_money
from ofo.money import PAISE

_MAX_PERCENT: Final = Decimal(100)


@dataclass(frozen=True)
class Figures:
    percent: Decimal | None
    rupees: Decimal | None
    per_lot: Decimal | None


NONE: Final = Figures(None, None, None)


def _base_ok(base: object) -> bool:
    return isinstance(base, Decimal) and base.is_finite() and base > 0


def _per_lot(rupees: Decimal, lots: int | None) -> Decimal | None:
    if type(lots) is not int or lots <= 0:
        return None
    return (rupees / lots).quantize(PAISE, rounding=ROUND_HALF_UP)


def from_percent(percent: Decimal, base: Decimal | None, lots: int | None) -> Figures:
    """A percent of ``base`` (max profit for a target, max loss for a stop) in rupees to the paisa, half up."""
    if not _base_ok(base) or not percent.is_finite() or not 0 < percent <= _MAX_PERCENT:
        return Figures(percent if percent.is_finite() and 0 < percent <= _MAX_PERCENT else None, None, None)
    rupees = adjust_money.stop_at_pct(base, percent)  # type: ignore[arg-type]  # the engine's one % -> rupees
    return Figures(percent, rupees, _per_lot(rupees, lots))


def from_rupees(rupees: Decimal, base: Decimal | None, lots: int | None) -> Figures:
    """Rupees as a percent of ``base`` to two decimals (half up); a level above the base has no percent (> 100)."""
    if not rupees.is_finite() or rupees <= 0:
        return NONE
    rupees = rupees.quantize(PAISE, rounding=ROUND_HALF_UP)
    per = _per_lot(rupees, lots)
    if not _base_ok(base):
        return Figures(None, rupees, per)
    pct = adjust_money.level_as_pct(rupees, base)  # type: ignore[arg-type]  # the engine's one rupees -> %
    return Figures(pct if pct <= _MAX_PERCENT else None, rupees, per)


def agree(percent: Decimal, rupees: Decimal, base: Decimal | None, lots: int | None) -> bool:
    """True when a typed percent and a typed rupee amount are the same level (the percent's rupee figure, to the paisa,
    equals the rupees, or the rupees' percent, to two decimals, equals the percent). An unusable base -> False."""
    if not _base_ok(base):
        return False
    return from_percent(percent, base, lots).rupees == rupees or from_rupees(rupees, base, lots).percent == percent
