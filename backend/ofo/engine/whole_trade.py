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

import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from ofo.engine.black_scholes import bs_price, forward_price, year_fraction
from ofo.engine.legs import Instrument, expiry_pnl, position_pnl, require_price
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
from ofo.timeutil import EXPIRY_CLOSE

__all__ = ["FarLegNoIV", "MultiExpiryError", "NearExpiryAfter", "WholeTradeAfter", "WholeTradeFigures",
           "near_expiry_after", "near_pnl_at", "whole_pnl_at", "whole_trade_after"]


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


def whole_pnl_at(strategy: Strategy | None, after: WholeTradeAfter, level: Decimal) -> Decimal:
    """REQ-156: the whole-trade at-expiry P&L after every charge line at ``level``: the open legs' expiry P&L
    (``Strategy.expiry_pnl_at``; None = nothing open) plus the booked P&L less the total charges, the same flat shift
    :func:`whole_trade_after` applies to its figures (no second formula). ``level`` is a price: at most 2 decimals
    (finding interpolated-level-finer-than-paise-refused: the caller rounds a derived level once)."""
    require_price(level, "level")
    open_pnl = strategy.expiry_pnl_at(level) if strategy is not None else Decimal(0)
    return open_pnl + after.booked_pnl - after.total_charges


# ---- legs on two or more expiries: valued at the NEARER expiry close (REQ-148, C12 / GC-ICGUIDE g13) ----------------

class FarLegNoIV(ValueError):
    """A leg on a later expiry has no implied volatility, so it cannot be valued at the nearer expiry close."""

    def __init__(self, index: int) -> None:
        super().__init__(index)  # the leg index only: the caller words it from the catalogue
        self.index = index


@dataclass(frozen=True)
class NearExpiryAfter:
    """The whole trade of a strategy whose legs span expiries, valued at the nearer expiry's close: the nearer legs at
    their expiry value, every later leg at its Black-Scholes price at that moment (its own IV, time left to its own
    close, q = 0), through the one sign convention (``legs.position_pnl``). An ESTIMATE, never an exact at-expiry
    figure: no single maximum loss, maximum profit or breakeven exists (ADR-143, REQ-148 AC-4), so none is given.
    shortcut: q = 0 for the later legs (the spot fallback of ADR-061); pass each expiry's parity q when the Compare
    reads it."""

    strategy: Strategy
    near: datetime.date
    rate: Decimal
    ivs: tuple[Decimal | None, ...]  # one per leg; required for every option leg after ``near``
    booked_pnl: Decimal
    paid_charges: Decimal
    adjustment_charges: Decimal
    open_exit_charges: Decimal
    total_charges: Decimal


def near_expiry_after(strategy: Strategy, *, booked_pnl: Decimal, paid_charges: Decimal,  # noqa: PLR0913
                      adjustment_charges: Decimal, open_exit_charges: Decimal, rate: Decimal,
                      ivs: tuple[Decimal | None, ...]) -> NearExpiryAfter:
    """The :class:`NearExpiryAfter` of ``strategy`` (legs on 2+ expiries; a single expiry -> ValueError, use
    :func:`whole_trade_after`). A later option leg without an IV -> :class:`FarLegNoIV` naming the leg's index."""
    if strategy.is_single_expiry:
        raise ValueError("a single-expiry strategy has an exact After: use whole_trade_after")
    if len(ivs) != len(strategy.legs):
        raise ValueError("ivs needs one entry per leg")
    if not isinstance(rate, Decimal) or not rate.is_finite():
        raise ValueError(f"rate must be a finite decimal.Decimal, got {rate!r}")
    near = min(x.expiry for x in strategy.legs)
    for i, (leg, iv) in enumerate(zip(strategy.legs, ivs, strict=True)):
        if leg.expiry > near and leg.instrument is not Instrument.FUT and iv is None:
            raise FarLegNoIV(i)
    booked = _signed_paise(booked_pnl, "booked_pnl")
    paid = require_price(paid_charges, "paid_charges")
    adjustment = require_price(adjustment_charges, "adjustment_charges")
    exits = require_price(open_exit_charges, "open_exit_charges")
    return NearExpiryAfter(strategy, near, rate, tuple(ivs), booked, paid, adjustment, exits, paid + adjustment + exits)


def near_pnl_at(after: NearExpiryAfter, level: Decimal) -> Decimal:
    """The estimated whole-trade P&L after every charge line if the index is at ``level`` at the nearer expiry close:
    the open legs as :class:`NearExpiryAfter` values them, plus the booked P&L less the total charges (the same flat
    shift as :func:`whole_pnl_at`), rounded half-even to the paisa once."""
    require_price(level, "level", allow_zero=False)
    at = datetime.datetime.combine(after.near, EXPIRY_CLOSE)
    total = Decimal(0)
    for leg, iv in zip(after.strategy.legs, after.ivs, strict=True):
        if leg.expiry == after.near:
            total += expiry_pnl(leg, level)
            continue
        years = year_fraction(at, leg.expiry)
        mark = (forward_price(level, years, after.rate) if leg.instrument is Instrument.FUT
                else bs_price(leg.instrument, level, leg.strike, years, after.rate, iv))  # type: ignore[arg-type]
        total += position_pnl(leg, mark)
    return (total + after.booked_pnl - after.total_charges).quantize(PAISE, rounding=ROUND_HALF_EVEN)
