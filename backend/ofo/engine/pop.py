"""W-125 (REQ-082 AC-2..AC-5; ADR-156 (1), ADR-063, ADR-082, ADR-008): the probability of profit at expiry.

The probability that the underlying at the strategy's expiry lies where the expiry P&L, INCLUDING the round-trip charges
(ADR-082), is above zero. Under the engine's own pricing model (``black_scholes.probability_below``: lognormal about the
expiry's parity forward with the expiry's ATM implied volatility). The loss regions come from the same region logic as the
outcome's "where do I start losing" (``metrics._loss_regions``), computed on the net-of-charges P&L; they are NEVER
inferred from breakevens alone (finding loss-region-inferred-from-breakevens: a strategy can lose between two zeros).

Held (REQ-082 AC-1): the caller shows the figure only when ``probability_of_profit`` is on; the figure is never used to
sort, rank or pick strategies (AC-6), and nothing in this module is imported by a ranking path (a repo test checks).

Answer states (standing item d): single expiry + forward + vol -> a figure; mixed expiries -> ``MultiExpiryError``; no
forward / no volatility / no spot -> the caller passes None and gets ``Unavailable`` with the reason.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum

from ofo.engine.black_scholes import probability_below
from ofo.engine.metrics import MultiExpiryError, loss_regions_after_charges
from ofo.engine.strategy import Strategy

__all__ = ["MultiExpiryError", "Unavailable", "Why", "probability_of_profit", "whole_percent"]
_HUNDRED = Decimal(100)


class Why(Enum):
    """The closed reasons the figure shows "-" (REQ-082 AC-5)."""

    MIXED_EXPIRIES = "different_expiries"
    NO_VOLATILITY = "no_volatility"
    NO_FORWARD = "no_forward"
    SPOT_STALE_OR_MISSING = "spot_stale_or_missing"


class Unavailable(Exception):
    def __init__(self, why: Why) -> None:
        super().__init__(why.value)
        self.why = why


def probability_of_profit(strategy: Strategy, *, forward: Decimal | None, years: Decimal | None, vol: Decimal | None,
                          charges: Decimal = Decimal(0)) -> Decimal:
    """P(expiry P&L - ``charges`` > 0) as a fraction in [0, 1] (1e-9 precision). Raises ``Unavailable``."""
    if not strategy.is_single_expiry:
        raise Unavailable(Why.MIXED_EXPIRIES)
    if vol is None or vol <= 0 or years is None or years <= 0:
        raise Unavailable(Why.NO_VOLATILITY)
    if forward is None or forward <= 0:
        raise Unavailable(Why.NO_FORWARD)
    regions = loss_regions_after_charges(strategy, charges)
    lose = Decimal(0)
    for region in regions:
        lower, upper = region[0], region[1]
        below_upper = Decimal(1) if upper is None else probability_below(upper, forward, years, vol)
        below_lower = Decimal(0) if lower is None else probability_below(lower, forward, years, vol)
        lose += below_upper - below_lower
    return min(Decimal(1), max(Decimal(0), Decimal(1) - lose))


def whole_percent(probability: Decimal) -> int:
    """A whole percent, half-even (REQ-082 AC-3). A probability strictly between 0 and 1 never shows as 0 or 100: the
    model is an estimate, and "100%" would read as a promise (ADR-003)."""
    percent = int((probability * _HUNDRED).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    if Decimal(0) < probability < Decimal(1):
        return min(99, max(1, percent))
    return percent
