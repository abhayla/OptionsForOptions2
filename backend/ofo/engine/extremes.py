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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, breakevens_with_shift, strategy_metrics
from ofo.engine.orderbook import BookView, NetPosition, PaperOrder, net_positions
from ofo.engine.strategy import Strategy

ExtremesReason = Literal["prices_not_live", "multi_expiry"]
PRICES_NOT_LIVE: ExtremesReason = "prices_not_live"
MULTI_EXPIRY: ExtremesReason = "multi_expiry"
Figure = Decimal | object  # a Decimal, or the engine's UNLIMITED sentinel (its class is private to metrics.py)

__all__ = ["MULTI_EXPIRY", "PRICES_NOT_LIVE", "UNLIMITED", "BookBreakevens", "BookExtremes", "ContractTerms",
           "ExitRisk", "ExtremesReason", "book_breakevens", "book_extremes", "exit_risk"]


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


def book_pnl_at_zero(view: BookView, terms: Mapping[str, ContractTerms]) -> Decimal | None:
    """ADR-330 (55): the book's P&L at expiry with the index at 0 (the booked cash plus every open contract's payoff
    at level 0, the same definition as Max Loss); None when it cannot be said (nothing open, two expiries, a leg the
    engine will not value). The warning prints "worst case: <index> at zero" only when this equals the Max Loss."""
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if not open_ or len({terms[p.instrument_id].expiry for p in open_}) > 1:
        return None
    try:
        strategy = _strategy(open_, terms, {p.instrument_id: Decimal(0) for p in open_})
        return view.cash + strategy.expiry_pnl_at(Decimal(0))
    except (ValueError, KeyError, MultiExpiryError):
        return None


ExitState = Literal["yes", "no", "cannot_tell"]


@dataclass(frozen=True)
class ExitRisk:
    """ADR-256: the answer to "does this basket leave the legs open with less protection?" in THREE states; ``no`` only
    when proven. The figures (book Max Loss before / after) show only when the answer is yes and they read worse."""
    state: ExitState
    max_loss_before: Figure | None
    max_loss_after: Figure | None
    exposed: tuple[str, ...]  # the sold legs left open with less cover (instrument ids)


def _naked(view: BookView, terms: Mapping[str, ContractTerms]) -> dict[Instrument, int] | None:
    """Sold units with no bought unit of the same option type covering them, per type; a bought leg covers a sold leg
    with the same or a later expiry. None when it cannot be counted (a future leg)."""
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if any(terms[p.instrument_id].instrument not in (Instrument.CE, Instrument.PE) for p in open_):
        return None
    out = {}
    for kind in (Instrument.CE, Instrument.PE):
        legs = [(terms[p.instrument_id].expiry, p.net_quantity) for p in open_
                if terms[p.instrument_id].instrument is kind]
        cover = [[e, q] for e, q in legs if q > 0]
        naked = 0
        for expiry, sold in sorted(((e, -q) for e, q in legs if q < 0), reverse=True):  # latest sold expiry first
            left = sold
            for bought in cover:
                take = min(left, bought[1]) if bought[0] >= expiry else 0
                bought[1] -= take
                left -= take
            naked += left
        out[kind] = naked
    return out


def _worse(after: Figure | None, before: Figure | None) -> bool:
    """ADR-256 amendment: Max Loss after unlimited, or more than double the Max Loss before (a loss is negative)."""
    if after is None or before is None or before is UNLIMITED:
        return False
    return after is UNLIMITED or (after < 0 and after < 2 * before)


def exit_risk(book: Sequence[PaperOrder], basket: Sequence[PaperOrder], terms: Mapping[str, ContractTerms],
              priced: bool = True) -> ExitRisk:
    """Judge a whole basket (exits and entries together) on the legs after ALL its orders (ADR-008: the one engine).
    yes: naked sold units of an option type grow, or the book Max Loss after is unlimited / more than double while legs
    stay open. no: proven (nothing left open, or both counts and both Max Loss figures known and neither rule fires).
    Anything unproven (a future leg, two expiries, an order the book cannot take) is cannot_tell, never no.
    ``priced`` False = an exit price was not read (the orders carry a stand-in): no Max Loss figure is used or shown
    except "unlimited after", which needs no price; the double rule and the final no become cannot_tell."""
    try:
        before, after = net_positions(list(book), {}), net_positions([*book, *basket], {})
        held = {p.instrument_id: p.net_quantity for p in before.positions}
        for o in basket:  # an exit may only close what is open on the other side (a larger one is not judged)
            if o.kind == "exit":
                held[o.instrument_id] = held.get(o.instrument_id, 0) + (o.quantity if o.side == "BUY" else -o.quantity)
                if held[o.instrument_id] * (1 if o.side == "BUY" else -1) > 0:
                    return ExitRisk("cannot_tell", None, None, ())
        n0, n1 = _naked(before, terms), _naked(after, terms)
        loss0, loss1 = book_extremes(before, terms, {}).max_loss, book_extremes(after, terms, {}).max_loss
    except (ValueError, KeyError):
        return ExitRisk("cannot_tell", None, None, ())
    grew = {k for k in (n1 or {}) if n0 is not None and n1[k] > n0[k]}
    left_open = any(p.net_quantity != 0 for p in after.positions)
    if grew:
        state: ExitState = "yes"
    elif not left_open:
        state = "no"
    elif _worse(loss1, loss0) if priced else (loss1 is UNLIMITED and loss0 is not None and loss0 is not UNLIMITED):
        state = "yes"
    elif not priced or n0 is None or n1 is None or loss0 is None or loss1 is None:
        state = "cannot_tell"
    else:
        state = "no"
    exposed = tuple(p.instrument_id for p in after.positions
                    if p.net_quantity < 0 and terms[p.instrument_id].instrument in grew)
    shown = priced and state == "yes" and loss0 is not None and loss1 is not None and loss0 is not UNLIMITED and (
        loss1 is UNLIMITED or loss1 < loss0)
    return ExitRisk(state, loss0 if shown else None, loss1 if shown else None, exposed)


@dataclass(frozen=True)
class BookBreakevens:
    """GC-TP R-19b: the book's at-expiry breakevens. ``levels`` is None exactly when ``reason`` is set or nothing open;
    an empty tuple is a real answer (the payoff never crosses zero)."""
    levels: tuple[Decimal, ...] | None
    reason: ExtremesReason | None


def book_breakevens(view: BookView, terms: Mapping[str, ContractTerms],
                    charges: Decimal = Decimal(0)) -> BookBreakevens:
    """The levels where the book's at-expiry P&L is 0: booked + the open contracts' payoff at their exact average (the
    same definition as Max Profit / Max Loss above: ``view.cash`` + the open contracts' value at expiry). Needs no
    live price of its own (the charges, when given, come from the caller). D-16 (ADR-263): ``charges`` (the
    round-trip charges Max Profit / Max Loss carry, from ``extremes_charges.open_round_trip_charges``) is a flat
    amount taken off the P&L, so the levels are the ones after charges; 0 is the old answer. The adjustment pages
    reach the same levels through ``whole_trade_after`` (the same
    ``breakevens_with_shift`` kernel, shift = booked - every charge line). Open contracts on more than one expiry:
    absent, ``multi_expiry`` (no exact breakevens, as Drafts Mode)."""
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if not open_:
        return BookBreakevens(None, None)
    if len({terms[p.instrument_id].expiry for p in open_}) > 1:
        return BookBreakevens(None, MULTI_EXPIRY)
    try:
        strategy = _strategy(open_, terms, {p.instrument_id: Decimal(0) for p in open_})
        return BookBreakevens(breakevens_with_shift(strategy, view.cash - charges), None)
    except MultiExpiryError:
        return BookBreakevens(None, MULTI_EXPIRY)
