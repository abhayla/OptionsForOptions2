"""A-23 delta-neutral helper: figures only, no trade (GC-IC1 step 4a; ADR-003 decision support, ADR-008 exact Decimal).

Spec basis: brief GC-IC1 4a "the position's net delta now (engine Greeks summed over the legs, as the Greeks total)
and, to bring it to 0, the lots of the nearest-ATM option of the needed type or the lots of the index future (exact
Decimal, rounded to whole lots, the remaining delta after rounding stated)". Sensibull study catalogue-raw line 55
(per-leg delta and a Total).

The per-unit deltas come from the caller, read from the ONE engine (``ofo.engine.model`` Greeks, the same per-option
figures the chain rows carry); nothing here prices an option. Net delta = sum over legs of (+1 BUY / -1 SELL) x lots x
lot size x the leg's per-unit delta, in index points per point (the Greeks total's unit).

Answer states: every leg has a delta -> the figures; a leg with no delta (no IV) -> ``NotKnown`` naming that leg (never
0); the ATM option's delta not known or 0 -> the option figure is None and the future figure still given; a lot size
below 1 -> ValueError. Lots are SIGNED: positive = held long, negative = held short (a figure, never an instruction).
Rounding: to the nearest whole lot, halves away from zero (``ROUND_HALF_UP`` on the magnitude).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_SIGN = {"BUY": Decimal(1), "SELL": Decimal(-1)}
FUTURE_DELTA = Decimal(1)  # an index future moves one point per index point


@dataclass(frozen=True)
class LegDelta:
    ref: str  # the leg as shown ("SELL 23500 CE"), named in a NotKnown
    side: str  # BUY / SELL
    lots: int
    delta: Decimal | None  # per unit, from the engine; None = no IV for this leg


@dataclass(frozen=True)
class NotKnown:
    leg: str


@dataclass(frozen=True)
class Hedge:
    lots: int  # signed: + long, - short
    remaining: Decimal  # the net delta left after these lots


@dataclass(frozen=True)
class Figures:
    net_delta: Decimal
    option_type: str  # CE when the position needs delta added, PE when it needs delta taken away
    option: Hedge | None  # None: the ATM option's delta is not known (or 0)
    future: Hedge


def _lots(need: Decimal, per_lot: Decimal) -> int:
    raw = need / per_lot
    whole = abs(raw).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(whole if raw >= 0 else -whole)


def figures(legs: Sequence[LegDelta], lot: int, atm_ce_delta: Decimal | None,
            atm_pe_delta: Decimal | None) -> Figures | NotKnown:
    """The A-23 figures of a position (module docstring)."""
    if lot < 1:
        raise ValueError(f"a lot size must be at least 1, not {lot}")
    net = Decimal(0)
    for leg in legs:
        if leg.delta is None:
            return NotKnown(leg.ref)
        net += _SIGN[leg.side] * leg.lots * lot * leg.delta
    need = -net
    option_type = "CE" if need >= 0 else "PE"
    unit = atm_ce_delta if option_type == "CE" else atm_pe_delta
    option = None
    if unit is not None and unit != 0:
        n = _lots(need, unit * lot)
        option = Hedge(n, net + n * lot * unit)
    f = _lots(need, FUTURE_DELTA * lot)
    return Figures(net, option_type, option, Hedge(f, net + f * lot * FUTURE_DELTA))
