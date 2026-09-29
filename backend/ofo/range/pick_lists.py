"""Pick lists for the expected market range input (REQ-026).

AC-3: both lists start at the current market level; the platform never pre-fills an assumed range.
AC-5: two pick lists in 100-point steps — the lower list holds the current level and everything
below, the upper list the current level and everything above. Input is by pick list only. Each
list runs from the current level to the furthest listed strike of the chosen expiry in that
direction (instrument master), capped per index by an Admin setting (defaults NIFTY 3,000 points,
SENSEX 9,000 points — ADR-042 / REQ-026 AC-5).
AC-6: the lower value can never exceed the current level and the upper value can never be below it
(enforced structurally: every list value is built by stepping AWAY from the current level).
AC-7: the chosen range feeds strategy and risk evaluation and is labelled an input, never a
prediction.

Fix round 1 finding: an unaligned current level (e.g. SENSEX 81,422) produced list values that were
not real strikes (81,322, 81,222, ...), and a strike-bound list could stop short of the furthest
listed strike (NIFTY 2026-10-06 lower list stopped at 20,837 instead of the real furthest strike,
20,800). Every value after the first must be a strike the catalogue actually lists.

Orchestrator defaults (not settled by the spec text; decided here in this module):
(a) AC-3 ("Both levels start at the current market level") and AC-5 ("100-point steps ... runs
    from the current level to the furthest listed strike ... capped", and the REQ-026 note that
    "every value is a real strike") together give this rule: the FIRST value is the exact current
    level (AC-3), appearing once even when it is already a multiple of 100. Every value after that
    is a 100-multiple STRICTLY beyond the current level, moving away from it (floor(current/100)*100
    then -100 per step for the lower list; ceil(current/100)*100 then +100 per step for the upper
    list) — and, per the REQ-026 note, only values the catalogue actually lists for that expiry are
    included; a 100-multiple missing from the real listing is skipped (real far-OTM chains can have
    gaps — see the NIFTY 2026-09-29 fixture, e.g. 20,300..20,700 are not listed). The list is capped
    at whichever bound binds first: the per-index Admin cap (current ± cap) or the furthest listed
    strike of `expiry` in that direction. When the furthest listed strike is the binding bound and
    is not itself a 100-multiple, it is appended as the final value regardless, so the list truly
    reaches it (AC-5's "runs ... to the furthest listed strike").
(b) the Admin cap is a distance measured FROM the current level, not from a rounded value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ofo.instruments.catalogue import Catalogue

STEP = Decimal("100")

# ADR-042 / REQ-026 AC-5 defaults. Admin-configurable; no Admin UI is built in this item.
DEFAULT_CAPS: dict[str, Decimal] = {
    "NIFTY": Decimal("3000"),
    "SENSEX": Decimal("9000"),
}


@dataclass(frozen=True)
class RangeCaps:
    """Per-index range extent caps (ADR-042). A stand-in for the Admin setting; no UI here."""

    caps: dict[str, Decimal] = field(default_factory=lambda: dict(DEFAULT_CAPS))

    @classmethod
    def defaults(cls) -> "RangeCaps":
        return cls(dict(DEFAULT_CAPS))

    def for_index(self, name: str) -> Decimal:
        try:
            cap = self.caps[name]
        except KeyError as exc:
            raise ValueError(f"no configured range cap for {name!r}") from exc
        if cap <= 0:
            raise ValueError(f"range cap for {name!r} must be positive, got {cap}")
        return cap


def _require_decimal(value: object, label: str) -> Decimal:
    """Fail closed on anything that is not exactly a `Decimal` (never a float, never a bool)."""
    if isinstance(value, bool) or not isinstance(value, Decimal):
        raise ValueError(f"{label} must be a decimal.Decimal, got {type(value).__name__}: {value!r}")
    return value


def _listed_strikes(catalogue: Catalogue, name: str, expiry: date) -> set[Decimal]:
    """Every option strike the catalogue lists for this underlying + expiry.

    Raises ValueError for an unknown or empty expiry — never guesses a range.
    """
    options = catalogue.contracts_for(name, expiry, instrument_types=frozenset({"CE", "PE"}))
    if not options:
        raise ValueError(
            f"no option contracts found for {name} expiry {expiry}: cannot build pick lists "
            "(unknown or empty expiry)"
        )
    return {c.strike for c in options}


def _snap_floor_100(value: Decimal) -> Decimal:
    """The largest 100-multiple <= value."""
    return (value // STEP) * STEP


def _snap_ceil_100(value: Decimal) -> Decimal:
    """The smallest 100-multiple >= value."""
    floor = _snap_floor_100(value)
    return floor if floor == value else floor + STEP


def build_pick_list(
    catalogue: Catalogue,
    name: str,
    expiry: date,
    current_level: Decimal,
    caps: RangeCaps,
    *,
    direction: str,
) -> list[Decimal]:
    """Build one pick list ("lower" or "upper") starting at `current_level`.

    AC-3: the first value is the exact current level, appearing once even when it is itself a
    100-multiple.
    AC-5 (fix round 1): every value after the first is a 100-multiple strictly beyond the current
    level, moving away from it, snapped to the index's strike grid — a candidate 100-multiple that
    the catalogue does not actually list for this expiry is skipped (real far-OTM chains widen out
    and can have gaps). The list stops at whichever bound binds first: the per-index Admin cap
    (current ± cap) or the furthest listed strike of `expiry` in that direction. When the furthest
    listed strike binds and is not itself a 100-multiple, it is appended as the final value anyway,
    so the list genuinely reaches it.
    AC-6: a lower list never contains a value above `current_level`; an upper list never contains
    one below it — guaranteed by construction (every step moves away from current_level).
    """
    current_level = _require_decimal(current_level, "current_level")
    if direction not in ("lower", "upper"):
        raise ValueError(f"direction must be 'lower' or 'upper', got {direction!r}")
    if not name or not name.strip():
        raise ValueError("name must be a non-empty underlying symbol")

    cap = caps.for_index(name)
    listed_strikes = _listed_strikes(catalogue, name, expiry)
    min_strike, max_strike = min(listed_strikes), max(listed_strikes)

    values: list[Decimal] = [current_level]

    if direction == "lower":
        # Whichever limiter is reached FIRST while stepping down (nearer to current_level) wins:
        # the strike floor if strikes run out before the cap, else the cap.
        bound = max(min_strike, current_level - cap)
        strike_bound = bound == min_strike
        start = _snap_floor_100(current_level)
        if start == current_level:
            start -= STEP
        value = start
        while value >= bound:
            if value in listed_strikes:
                values.append(value)
            # else: this 100-multiple is not a strike the catalogue lists for this expiry (a real
            # gap in a far-OTM chain) — skip it rather than offer an unreal value.
            value -= STEP
    else:
        bound = min(max_strike, current_level + cap)
        strike_bound = bound == max_strike
        start = _snap_ceil_100(current_level)
        if start == current_level:
            start += STEP
        value = start
        while value <= bound:
            if value in listed_strikes:
                values.append(value)
            value += STEP

    if strike_bound and values[-1] != bound:
        values.append(bound)

    return values


@dataclass(frozen=True)
class ExpectedRange:
    """AC-7: the user's chosen expected range — an input to strategy/risk evaluation, never a
    prediction. Immutable; `label` is always "user input"."""

    name: str
    expiry: date
    lower: Decimal
    upper: Decimal
    label: str = "user input"

    def __post_init__(self) -> None:
        if self.label != "user input":
            raise ValueError("ExpectedRange.label must be 'user input' — never a prediction (AC-7)")
        if self.lower > self.upper:
            raise ValueError(f"lower ({self.lower}) must not exceed upper ({self.upper})")


def choose_range(
    catalogue: Catalogue,
    name: str,
    expiry: date,
    current_level: Decimal,
    caps: RangeCaps,
    lower_choice: Decimal,
    upper_choice: Decimal,
) -> ExpectedRange:
    """Validate a user's picks against the built pick lists and return an immutable ExpectedRange.

    AC-6: a `lower_choice` above the current level (or an `upper_choice` below it) can never be a
    member of the corresponding list, so it is refused here as "not offered".
    """
    lower_list = build_pick_list(catalogue, name, expiry, current_level, caps, direction="lower")
    upper_list = build_pick_list(catalogue, name, expiry, current_level, caps, direction="upper")

    lower_choice = _require_decimal(lower_choice, "lower_choice")
    upper_choice = _require_decimal(upper_choice, "upper_choice")

    if lower_choice not in lower_list:
        raise ValueError(f"{lower_choice} is not an offered lower pick-list value for {name} {expiry}")
    if upper_choice not in upper_list:
        raise ValueError(f"{upper_choice} is not an offered upper pick-list value for {name} {expiry}")

    return ExpectedRange(name=name, expiry=expiry, lower=lower_choice, upper=upper_choice)
