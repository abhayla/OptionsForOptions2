"""REQ-155 AC-2, AC-3 (F-74, ADR-214, ADR-008): the whole-trade After of an adjustment, at expiry.

The After is the whole trade, not the open legs alone: the open legs' exact at-expiry P&L PLUS the booked P&L (legs
closed earlier and legs this adjustment closes), LESS the charges. Booked P&L and charges are flat amounts (they do not
depend on where the index ends), so each enters as a flat shift of the open legs' payoff, through the engine's one
zero-finding path (``metrics.breakevens_with_shift``, ``metrics.loss_regions_after_charges``, both on
``metrics._breakevens``); there is no second formula here. Every level is rounded at its one producer
(``metrics._to_decimal``, half-even to 0.01 points, REQ-155 AC-4).

Charges convention (consistent with ``ofo.outcome.service``: ``_charges_breakdown`` prices a ROUND TRIP of every leg,
its entry order and its exit order, via ``charges.round_trip.round_trip_breakdown``; ``_summary`` takes that total off
max profit and adds it to max loss once, ADR-082 (2); STT on exercise is NOT in that total, only its rate is shown):

- ``paid_charges``: charges already paid on earlier orders (the original entries, earlier adjustments).
- ``adjustment_charges``: this adjustment's own orders, its closing orders plus its opening orders (AC-3: its own line).
- ``open_exit_charges``: the exit orders of the legs still open After, priced as the outcome prices the exit half of
  its round trip (the open legs' entries are already in one of the two lines above, so they are never counted twice).
  Required, never defaulted: a caller that leaves exit charges out passes 0 on purpose. STT on exercise is excluded,
  as in the outcome (it depends on the settlement level).

Each of the three is kept as its own line on the answer and subtracted exactly once from the whole-trade figures.
Example (ADJ-13): open legs credit 4,179.50 + booked 962 -> gross max profit 5,141.50, max loss 20,858.50,
breakevens 22,860.45 / 23,489.55 (the open legs alone would give max loss 21,820.50).

POP of the whole trade (REQ-155 AC-2, AC-4): ``ofo.engine.pop.probability_of_profit`` on the open legs with
``charges = total_charges - booked_pnl``. That function takes a flat amount off every level of the open legs' expiry
P&L, so this is P(open legs + booked - every charge line > 0): the after-charges whole trade, booked P&L included,
through the one POP path (no second formula). Its levels are the after-charges levels above, rounded at their one
producer. Answer: ``pop`` a fraction in [0, 1] with ``pop_unavailable`` None, or ``pop`` None with
``pop_unavailable`` the named reason (``pop.Why``: no volatility, no forward, ...); never an exception, never both
None. The words shown ("POP not available") are the route's job.

Answer states: single expiry -> figures; legs on more than one expiry -> ``MultiExpiryError`` (no exact at-expiry
payoff, nothing made up); a non-Decimal, non-finite or not-whole-paise amount, or a negative charge -> ``ValueError``
naming the argument.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ofo.engine.legs import require_price
from ofo.engine.metrics import (
    UNLIMITED,
    LossRegion,
    MultiExpiryError,
    _Unlimited,
    breakevens_with_shift,
    loss_regions_after_charges,
    strategy_metrics,
)
from ofo.engine.pop import Unavailable, Why, probability_of_profit
from ofo.engine.strategy import Strategy
from ofo.money import PAISE

__all__ = ["MultiExpiryError", "WholeTradeAfter", "WholeTradeFigures", "whole_trade_after"]


@dataclass(frozen=True)
class WholeTradeFigures:
    """Whole-trade at-expiry figures for one flat shift. ``max_profit`` is signed (negative when the booked loss is
    larger than the open legs can make); ``max_loss`` is the loss magnitude, 0 when the trade cannot end below zero."""

    max_profit: Decimal | _Unlimited
    max_loss: Decimal | _Unlimited
    breakevens: tuple[Decimal, ...]
    loss_regions: tuple[LossRegion, ...]


@dataclass(frozen=True)
class WholeTradeAfter:
    """The After of the whole trade: ``gross`` (open legs + booked P&L, before any charges) and ``after_charges``
    (gross less every charge line once), with each charge line kept apart (REQ-155 AC-3)."""

    gross: WholeTradeFigures
    after_charges: WholeTradeFigures
    booked_pnl: Decimal
    paid_charges: Decimal
    adjustment_charges: Decimal
    open_exit_charges: Decimal
    total_charges: Decimal
    #: P(after-charges whole-trade P&L > 0), or None when ``pop_unavailable`` names why (exactly one is set).
    pop: Decimal | None
    pop_unavailable: Why | None


def _figures(strategy: Strategy, shift: Decimal) -> WholeTradeFigures:
    metrics = strategy_metrics(strategy)
    top, low = metrics.max_profit, metrics.min_pnl
    max_profit: Decimal | _Unlimited = top + shift if isinstance(top, Decimal) else UNLIMITED
    if not isinstance(low, Decimal):
        max_loss: Decimal | _Unlimited = UNLIMITED
    else:
        low += shift
        max_loss = -low if low < 0 else Decimal(0)
    # a flat shift of +s is a charge of -s: the same region walk as the outcome's net-of-charges P&L
    return WholeTradeFigures(max_profit, max_loss, breakevens_with_shift(strategy, shift),
                             loss_regions_after_charges(strategy, -shift))


def _flat(amount: Decimal) -> WholeTradeFigures:
    """No open leg: the trade's P&L is ``amount`` at every level. Max profit is that amount (signed), max loss its
    magnitude when below zero; no breakeven; a loss everywhere when below zero, nowhere otherwise."""
    loss: tuple[LossRegion, ...] = ((None, None),) if amount < 0 else ()  # type: ignore[assignment]
    return WholeTradeFigures(amount, -amount if amount < 0 else Decimal(0), (), loss)


def _signed_paise(value: object, name: str) -> Decimal:
    """A signed rupee amount (booked P&L can be a loss): a finite Decimal of whole paise, else ValueError by name."""
    if not isinstance(value, Decimal) or not value.is_finite() or value.quantize(PAISE) != value:
        raise ValueError(f"{name} must be a finite decimal.Decimal of whole paise, got {value!r}")
    return value


def whole_trade_after(strategy: Strategy | None, *, booked_pnl: Decimal, paid_charges: Decimal,  # noqa: PLR0913
                      adjustment_charges: Decimal, open_exit_charges: Decimal, forward: Decimal | None = None,
                      years: Decimal | None = None, vol: Decimal | None = None) -> WholeTradeAfter:
    """The whole-trade After of ``strategy`` (the legs open after the adjustment). See the module docstring for which
    order each charge line covers and how POP is taken; ``forward`` / ``years`` / ``vol`` are POP's inputs (None ->
    the named reason). Raises ``MultiExpiryError`` for legs on more than one expiry.

    ``strategy`` None = no leg is open After (an exit of every leg, A-31): the whole trade is the booked P&L less the
    charges at every level, so the figures are flat (``_flat``) and POP is 1 when that amount is above 0, else 0 (no
    model input is needed: nothing is left to the market)."""
    if strategy is None:
        b = _signed_paise(booked_pnl, "booked_pnl")
        p, a, e = (require_price(paid_charges, "paid_charges"), require_price(adjustment_charges, "adjustment_charges"),
                   require_price(open_exit_charges, "open_exit_charges"))
        total = p + a + e
        return WholeTradeAfter(gross=_flat(b), after_charges=_flat(b - total), booked_pnl=b, paid_charges=p,
                               adjustment_charges=a, open_exit_charges=e, total_charges=total,
                               pop=Decimal(1) if b - total > 0 else Decimal(0), pop_unavailable=None)
    if not strategy.is_single_expiry:
        raise MultiExpiryError("the whole-trade After needs every open leg on one expiry")
    booked = _signed_paise(booked_pnl, "booked_pnl")
    paid = require_price(paid_charges, "paid_charges")
    adjustment = require_price(adjustment_charges, "adjustment_charges")
    exits = require_price(open_exit_charges, "open_exit_charges")
    total = paid + adjustment + exits
    pop: Decimal | None = None
    why: Why | None = None
    try:
        pop = probability_of_profit(strategy, forward=forward, years=years, vol=vol, charges=total - booked)
    except Unavailable as missing:
        why = missing.why
    return WholeTradeAfter(gross=_figures(strategy, booked), after_charges=_figures(strategy, booked - total),
                           booked_pnl=booked, paid_charges=paid, adjustment_charges=adjustment,
                           open_exit_charges=exits, total_charges=total, pop=pop, pop_unavailable=why)
