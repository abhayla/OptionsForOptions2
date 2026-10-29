"""Profit left / Loss left and the original Max Profit / Max Loss of an open paper book (GC-TP step 3a).

Spec basis: REQ-109 AC-9 "The summary shows "Profit left" and "Loss left" (the open legs' expiry P&L range from their
LTP) first, with the original Max Profit / Max Loss below"; AC-5 (a price not live pauses the live figures); ADR-207
(2) (Drafts Mode, Sensibull catalogue 278-279); ADR-008 (one engine, exact Decimal).

Definitions (each a signed rupee figure at expiry; the payoff maths is ``strategy_metrics``, never re-derived here):

- **Profit left / Loss left**: the highest / lowest at-expiry P&L of the OPEN contracts (net quantity, by side) with
  each contract's current LTP as its entry - what the open position can still make or lose from here. Booked P&L is
  not in it. Any open contract without a live price -> both absent, reason ``prices_not_live`` (AC-5).
- **Max Profit / Max Loss (original)**: booked P&L + the highest / lowest at-expiry P&L of the open contracts at their
  EXACT average price (the order book's fraction, not the paisa-rounded display). Computed as the book's order cash
  (``BookView.cash``, whole paise) + the open contracts' value at expiry (entry 0), which is the same sum exactly and
  needs no non-terminating average. Known whether or not prices are live.
- A side with no bound (a net short call above every strike) is ``UNLIMITED``; the downside always ends at index 0
  (metrics.py conventions), so only the upper tail can be unbounded.
- A fully closed book: profit left = loss left = 0 and max profit = max loss = booked.
- Open contracts on more than one expiry: all four absent, reason ``multi_expiry``. A model-valued version (an
  estimate at the first expiry) is NOT built in this goal.

Max Loss is the signed lowest figure (a loss is negative), not a magnitude: Profit left and Loss left are a range.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, breakevens_with_shift, strategy_metrics
from ofo.engine.orderbook import BookView, NetPosition
from ofo.engine.strategy import Strategy

ExtremesReason = Literal["prices_not_live", "multi_expiry"]
PRICES_NOT_LIVE: ExtremesReason = "prices_not_live"
MULTI_EXPIRY: ExtremesReason = "multi_expiry"
Figure = Decimal | object  # a Decimal, or the engine's UNLIMITED sentinel (its class is private to metrics.py)

__all__ = ["MULTI_EXPIRY", "PRICES_NOT_LIVE", "UNLIMITED", "BookBreakevens", "BookExtremes", "ContractTerms",
           "ExtremesReason", "book_breakevens", "book_extremes"]


@dataclass(frozen=True)
class ContractTerms:
    """What the payoff needs of one contract: its type, strike (None for a future) and expiry."""
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date


@dataclass(frozen=True)
class BookExtremes:
    profit_left: Figure | None
    loss_left: Figure | None
    max_profit: Figure | None
    max_loss: Figure | None
    reason: ExtremesReason | None  # why a figure is absent; None when all four are known


def _strategy(open_: list[NetPosition], terms: Mapping[str, ContractTerms], entry: Mapping[str, Decimal]) -> Strategy:
    legs = []
    for p in open_:
        t = terms[p.instrument_id]
        legs.append(Leg(Action.BUY if p.net_quantity > 0 else Action.SELL, t.instrument, t.strike, t.expiry,
                        abs(p.net_quantity), entry[p.instrument_id]))
    return Strategy(tuple(legs))


def _range(strategy: Strategy, shift: Decimal) -> tuple[Figure, Figure]:
    m = strategy_metrics(strategy)
    high = m.max_profit if m.max_profit is UNLIMITED else m.max_profit + shift
    low = m.min_pnl if m.min_pnl is UNLIMITED else m.min_pnl + shift
    return high, low


def book_extremes(view: BookView, terms: Mapping[str, ContractTerms],
                  live: Mapping[str, Decimal]) -> BookExtremes:
    """The four figures of ``view`` (from ``net_positions``); ``terms`` and ``live`` are keyed by instrument id.

    ``live`` holds only live prices; an open contract absent from it has no live price.
    """
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if not open_:
        return BookExtremes(Decimal(0), Decimal(0), view.booked, view.booked, None)
    if len({terms[p.instrument_id].expiry for p in open_}) > 1:
        return BookExtremes(None, None, None, None, MULTI_EXPIRY)
    try:
        max_profit, max_loss = _range(_strategy(open_, terms, {p.instrument_id: Decimal(0) for p in open_}),
                                      view.cash)
    except MultiExpiryError:  # unreachable after the check above; kept so the engine's own refusal is honoured
        return BookExtremes(None, None, None, None, MULTI_EXPIRY)
    if any(p.instrument_id not in live for p in open_):
        return BookExtremes(None, None, max_profit, max_loss, PRICES_NOT_LIVE)
    profit_left, loss_left = _range(_strategy(open_, terms, live), Decimal(0))
    return BookExtremes(profit_left, loss_left, max_profit, max_loss, None)


@dataclass(frozen=True)
class BookBreakevens:
    """GC-TP R-19b: the book's at-expiry breakevens. ``levels`` is None exactly when ``reason`` is set or nothing open;
    an empty tuple is a real answer (the payoff never crosses zero)."""
    levels: tuple[Decimal, ...] | None
    reason: ExtremesReason | None


def book_breakevens(view: BookView, terms: Mapping[str, ContractTerms]) -> BookBreakevens:
    """The levels where the book's at-expiry P&L is 0: booked + the open contracts' payoff at their exact average (the
    same definition as Max Profit / Max Loss above: ``view.cash`` + the open contracts' value at expiry). Needs no live
    price. Open contracts on more than one expiry: absent, ``multi_expiry`` (no exact breakevens, as Drafts Mode)."""
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if not open_:
        return BookBreakevens(None, None)
    if len({terms[p.instrument_id].expiry for p in open_}) > 1:
        return BookBreakevens(None, MULTI_EXPIRY)
    try:
        strategy = _strategy(open_, terms, {p.instrument_id: Decimal(0) for p in open_})
        return BookBreakevens(breakevens_with_shift(strategy, view.cash), None)
    except MultiExpiryError:
        return BookBreakevens(None, MULTI_EXPIRY)
