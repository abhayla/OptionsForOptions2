"""W-125 (REQ-079 AC-3, AC-6, AC-7, AC-8; ADR-150 (2), ADR-157, ADR-015): strikes placed by a rule.

Held for the Q211 legal answer: the caller (``ofo_app.routes.ready_made``) checks the switch first. This module is the
rule itself, pure and clock-free:

- ATM is the LISTED strike nearest the spot; a tie takes the lower strike (AC-3; ``atm_strike`` rounds a tie up).
- every other strike sits the template's number of strike steps from ATM (``resolve_template`` does the arithmetic on
  the listed ATM, so the formula lives in one place); each strike must be a listed strike of that expiry.
- a stale or missing spot refuses (AC-8); a slot with no expiry refuses (AC-6); nothing is silently replaced.

Answer states (standing item d): spot stated and fresh / stale / missing; expiry present / absent; strike listed / not
listed; distance offered / not offered. Each has one result below.
"""
from __future__ import annotations

import datetime
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ofo.engine.legs import Action, Instrument
from ofo.strategy.model import EXPIRY_SLOTS, Template, resolve_template

#: REQ-079 AC-7 defaults: quick-pick distances in index points per underlying (admin-changeable later; each a
#: multiple of the strike step, checked on use).
QUICK_PICK_DISTANCES: Mapping[str, tuple[int, ...]] = {"NIFTY": (50, 100, 150, 200), "SENSEX": (100, 200, 300, 400)}
#: The entry price handed to ``resolve_template`` (placement places strikes and prices nothing).
_UNPRICED = Decimal("1")


class Refusal(Enum):
    SPOT_MISSING = "spot_missing"
    SPOT_STALE = "spot_stale"
    EXPIRY_MISSING = "expiry_missing"
    STRIKE_NOT_LISTED = "strike_not_listed"
    DISTANCE_NOT_OFFERED = "distance_not_offered"


class PlacementRefused(Exception):
    """Nothing was placed. ``reason`` is the closed cause; the route turns it into a catalogue message."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Market:
    """What the live read gives: the index value (None when missing), whether it is fresh, the strike gap."""

    spot: Decimal | None
    spot_fresh: bool
    strike_gap: Decimal


@dataclass(frozen=True)
class QuickPick:
    """A straddle or strangle request: the user's side and expiry, the distance in points (0 for a straddle)."""

    kind: str
    underlying: str
    distance: int
    side: Action
    expiry: datetime.date


@dataclass(frozen=True)
class PlacedLeg:
    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date


def listed_atm(spot: Decimal, listed: Collection[Decimal]) -> Decimal:
    """The listed strike nearest ``spot``; an exact tie takes the lower strike (REQ-079 AC-3)."""
    if not listed:
        raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
    return min(listed, key=lambda strike: (abs(strike - spot), strike))


def _usable_spot(market: Market) -> Decimal:
    if market.spot is None or market.spot <= 0:
        raise PlacementRefused(Refusal.SPOT_MISSING)
    if not market.spot_fresh:
        raise PlacementRefused(Refusal.SPOT_STALE)
    return market.spot


def expiry_slots(chosen: datetime.date, available: Sequence[datetime.date]) -> dict[str, datetime.date | None]:
    """near = the chosen expiry, next / far = the following listed expiries (None when the file has none: AC-6)."""
    later = sorted(d for d in set(available) if d > chosen)
    return {slot: (chosen if i == 0 else (later[i - 1] if i - 1 < len(later) else None))
            for i, slot in enumerate(EXPIRY_SLOTS)}


def place_template(template: Template, expiries: Mapping[str, datetime.date | None], market: Market,
                   listed_strikes: Mapping[datetime.date, Collection[Decimal]]) -> tuple[PlacedLeg, ...]:
    """The template's legs at the template's own default step counts from the listed ATM of its first expiry.

    ``expiries`` maps each slot to a date or None; ``listed_strikes`` maps an expiry to the strikes the instrument file
    lists for it. Raises ``PlacementRefused`` (spot, expiry, strike) and places nothing.
    """
    live_spot = _usable_spot(market)
    used = {leg.expiry_slot for leg in template.legs}
    near = expiries.get("near")
    if near is None or any(expiries.get(slot) is None for slot in used):
        raise PlacementRefused(Refusal.EXPIRY_MISSING)
    atm = listed_atm(live_spot, listed_strikes.get(near, ()))
    strategy = resolve_template(template, spot=atm, strike_gap=market.strike_gap, expiries=expiries,
                                prices=[_UNPRICED] * len(template.legs))
    placed = tuple(PlacedLeg(leg.action, leg.instrument, leg.strike, leg.expiry) for leg in strategy.legs)
    for leg in placed:
        if leg.strike is not None and leg.strike not in listed_strikes.get(leg.expiry, ()):
            raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
    return placed


def place_quick_pick(pick: QuickPick, market: Market, listed_strikes: Collection[Decimal]) -> tuple[PlacedLeg, ...]:
    """A straddle (both legs at ATM) or a strangle (PE at ATM - distance, CE at ATM + distance), both legs on the side.

    A strangle's distance must be one of the underlying's offered distances and a multiple of the strike step. The user
    picks the side and the lots; the platform never does (AC-7).
    """
    if pick.kind not in ("straddle", "strangle"):
        raise ValueError(f"quick pick kind must be 'straddle' or 'strangle', got {pick.kind!r}")
    live_spot = _usable_spot(market)
    if pick.kind == "strangle" and (pick.distance not in QUICK_PICK_DISTANCES.get(pick.underlying, ())
                                    or Decimal(pick.distance) % market.strike_gap != 0):
        raise PlacementRefused(Refusal.DISTANCE_NOT_OFFERED)
    atm = listed_atm(live_spot, listed_strikes)
    reach = Decimal(pick.distance) if pick.kind == "strangle" else Decimal(0)
    pe, ce = atm - reach, atm + reach
    if pe not in listed_strikes or ce not in listed_strikes:
        raise PlacementRefused(Refusal.STRIKE_NOT_LISTED)
    return (PlacedLeg(pick.side, Instrument.PE, pe, pick.expiry), PlacedLeg(pick.side, Instrument.CE, ce, pick.expiry))
