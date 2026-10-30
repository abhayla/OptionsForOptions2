"""Paper tracking of a saved strategy: the paper entry, paper P&L and the detection inputs (W-122; REQ-109, REQ-045).

Spec basis: REQ-109 AC-1 (the paper entry stores "the entry price used (the leg's price at that moment on the same price
basis as live P&L, REQ-033), with the time and price health"); AC-2 ("Paper P&L is computed by the one engine (ADR-008)
from the paper entry prices and current prices, exact Decimal"); AC-5 (a stale or missing leg price pauses paper P&L).

Price basis: live P&L is ``(LTP - Entry) x Qty`` (ofo.engine.legs.live_pnl), so a leg's price here is its LTP, used only
when the quote's health is AVAILABLE and the LTP is a live price (above 0, ADR-020 Q185). Never the mid, a last-known
value or zero.

Answer states of the market snapshot (standing item d), per leg and for the index:
- live: AVAILABLE health and a positive LTP -> the price is used;
- stale: a quote whose health is not AVAILABLE -> no price; its quote time is kept for "as of";
- missing: no quote, an unknown/expired/other-underlying contract, or no positive LTP -> no price;
- the provider not running is the caller's state (no snapshot at all) and never reaches here.

Answer states of the catalogue (the caller's, ofo_app.tracked_contracts): a leg whose stored contract is not live -
retired, delisted, its token reassigned to another contract, or missing - is never priced, whatever the snapshot holds
under its old feed key (a reused token quotes ANOTHER contract). Such a leg carries its reason as its state, pauses the
view with that reason and stops every detection (the strategy priced is no longer the one tracked).

Paper exit (REQ-109 AC-4; ADR-201 (2)): an exited leg keeps the price it was exited at, and its P&L is BOOKED - the same
engine function (paper_pnl) with the exit price as that leg's "current" price, so it never moves again. The open legs'
P&L at live prices is UNBOOKED; total = booked + unbooked, only when unbooked is known (every open leg live). An exited
leg is never priced, and its contract state no longer pauses the view (its figure is frozen).

An exit with any leg not live is refused (PricesNotLive): a guessed price is never stored. The view pauses paper P&L
when an open leg is not live, and computes no detection when the index is not live. A multi-expiry strategy has no exact
breakevens (MultiExpiryError): paper P&L and the short-strike condition still run, the breakeven condition does not.
Standard library only; no clock is read here.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.adjustment.detection import Detection, detect_near_levels, short_strikes
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.marketdata.quote import NormalizedQuote, is_live_price, planning_price_usable
from ofo.money import PAISE
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth

PriceState = Literal["live", "stale", "missing"]
ContractReason = Literal["contract_retired", "contract_delisted", "token_reassigned", "contract_missing"]
ExitedState = Literal["exited"]
LegState = PriceState | ContractReason | ExitedState
EXITED: ExitedState = "exited"
PauseReason = Literal["prices_not_live"] | ContractReason
LIVE: PriceState = "live"
PRICES_NOT_LIVE: PauseReason = "prices_not_live"


@dataclass(frozen=True)
class Price:
    """One input's price answer: ``price`` is set only when ``state`` is live; ``at`` is the quote time when known."""

    instrument_id: str
    state: LegState
    price: Decimal | None
    at: datetime.datetime | None


@dataclass(frozen=True)
class TrackedLeg:
    """A leg of the saved strategy with its paper entry price (what the store keeps per leg)."""

    instrument_id: str
    action: Action
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    quantity: int
    entry_price: Decimal
    price_at: datetime.datetime


def is_live(price: Price) -> bool:
    """The ONE predicate every paper decision uses (entry, exit, unbooked, total, pause): the answer's STATE is live.
    Never "a price is present": a stale answer may one day carry its last price for display, and that price must never
    be computed with (REQ-109 AC-5; GC-BP step 8 review M1)."""
    return price.state == LIVE


class PricesNotLive(ValueError):
    """A paper entry was asked for while a leg's price is stale or missing (REQ-109 AC-5): nothing is stored."""

    def __init__(self, prices: Sequence[Price]) -> None:
        self.prices = tuple(prices)
        super().__init__(tuple((p.instrument_id, p.state) for p in self.prices))


def price_of(quote: NormalizedQuote | None, instrument_id: str) -> Price:
    """The live-P&L price basis of one quote (module docstring), never a guess."""
    if quote is None or not is_live_price(quote.ltp):
        return Price(instrument_id, "missing", None, None if quote is None else quote.timestamp)
    if quote.health is not DataHealth.AVAILABLE:
        return Price(instrument_id, "stale", None, quote.timestamp)
    if quote.ltp != quote.ltp.quantize(PAISE):
        raise ValueError(f"{instrument_id}: a price finer than a paisa cannot be stored exactly: {quote.ltp}")
    return Price(instrument_id, LIVE, quote.ltp, quote.timestamp)


def leg_price(snapshot: MarketSnapshot, instrument_id: str) -> Price:
    market = snapshot.legs.get(instrument_id)
    if market is None or market.problem is not None:
        return Price(instrument_id, "missing", None, snapshot.ended_times.get(instrument_id))
    found = price_of(market.quote, instrument_id)
    if found.at is None:
        return Price(instrument_id, found.state, None, snapshot.ended_times.get(instrument_id))
    return found


def display_price(snapshot: MarketSnapshot, instrument_id: str) -> Price:
    """ADR-212: the price a paper DISPLAY figure (LTP, unbooked, totals, decay, Greeks) is computed from. Market hours:
    exactly ``leg_price``. Market closed (``snapshot.market_closed``, ADR-119 calendar): also the last close the feed
    holds (``planning_price_usable``, ADR-200), returned with its own time; no held close stays unpriced (ADR-200 (4)).
    NEVER used for a fill: entry, exit, stops, triggers and settlement keep ``leg_price`` / ``is_live``."""
    found = leg_price(snapshot, instrument_id)
    if is_live(found) or not snapshot.market_closed:
        return found
    market = snapshot.legs.get(instrument_id)
    quote = None if market is None or market.problem is not None else market.quote
    if (quote is None or not is_live_price(quote.ltp) or quote.ltp != quote.ltp.quantize(PAISE)
            or not planning_price_usable(quote, market_closed=True)):
        return found
    return Price(instrument_id, LIVE, quote.ltp, quote.timestamp)


def paused_as_of(open_prices: Iterable[Price]) -> datetime.datetime | None:
    """REQ-109 AC-5: the oldest known quote time of an open input that is not live; None when none has a known time.
    The one rule behind every paused "as of" (tracking and the paper books), never computed a second way."""
    known = [p.at for p in open_prices if not is_live(p) and p.at is not None]
    return min(known) if known else None


def index_price(snapshot: MarketSnapshot) -> Price:
    return price_of(snapshot.spot, snapshot.underlying)


def _engine_leg(leg: TrackedLeg, current: Decimal | None) -> Leg:
    return Leg(leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, leg.entry_price, current)


def paper_pnl(legs: Sequence[TrackedLeg], current: Sequence[Decimal]) -> Decimal:
    """Paper P&L by the one engine (ADR-008): BUY (current - entry) x qty, SELL (entry - current) x qty, summed."""
    if len(legs) != len(current) or not legs:
        raise ValueError("paper P&L needs one current price per leg")
    return Strategy(tuple(_engine_leg(leg, c) for leg, c in zip(legs, current, strict=True))).live_pnl()


def _subset(legs: Sequence[TrackedLeg], prices: Mapping[int, Decimal]) -> Decimal:
    if any(i < 0 or i >= len(legs) for i in prices):
        raise ValueError(f"no such leg among {len(legs)}: {sorted(prices)}")
    if not prices:
        return Decimal(0)
    order = sorted(prices)
    return paper_pnl([legs[i] for i in order], [prices[i] for i in order])


def booked_pnl(legs: Sequence[TrackedLeg], exit_prices: Mapping[int, Decimal]) -> Decimal:
    """REQ-109 AC-4: the exited legs' paper P&L, each frozen at its exit price (leg index -> exit price); 0 if none."""
    return _subset(legs, exit_prices)


def leg_pnl(leg: TrackedLeg, price: Decimal) -> Decimal:
    """GC-UI D-B48: one leg's paper P&L by the same engine call as the total (``paper_pnl`` on that single leg), at its
    live price (open) or its exit price (exited, booked). Exact Decimal, never rounded, so legs add to the total."""
    return paper_pnl([leg], [price])


def leg_pnls(legs: Sequence[TrackedLeg], open_prices: Mapping[int, Decimal],
             exit_prices: Mapping[int, Decimal]) -> tuple[Decimal | None, ...]:
    """Per leg, in order: an exited leg's BOOKED P&L (at its exit price), an open leg's UNBOOKED P&L (at its live price
    in ``open_prices``), or None when the leg is open with no price given (absent, never 0; REQ-109 AC-5). Same refusals
    as ``pnl_split``. When no leg is None the figures sum to ``pnl_split(...).total`` exactly."""
    both = set(open_prices) & set(exit_prices)
    if both:
        raise ValueError(f"a leg is either open or exited, and exits once: {sorted(both)}")
    unknown = [i for i in (*open_prices, *exit_prices) if i < 0 or i >= len(legs)]
    if unknown:
        raise ValueError(f"no such leg among {len(legs)}: {sorted(unknown)}")
    priced = {**open_prices, **exit_prices}
    return tuple(None if i not in priced else leg_pnl(leg, priced[i]) for i, leg in enumerate(legs))


@dataclass(frozen=True)
class PnlSplit:
    booked: Decimal
    unbooked: Decimal | None  # None: an open leg has no live price (REQ-109 AC-5)
    total: Decimal | None  # booked + unbooked, only when unbooked is known


def pnl_split(legs: Sequence[TrackedLeg], open_prices: Mapping[int, Decimal],
              exit_prices: Mapping[int, Decimal]) -> PnlSplit:
    """ADR-201 (2): booked (exited legs at their exit price) + unbooked (open legs at ``open_prices``) = total. An open
    leg missing from ``open_prices`` makes unbooked and total unknown; a leg in both maps is refused."""
    both = set(open_prices) & set(exit_prices)
    if both:
        raise ValueError(f"a leg is either open or exited, and exits once: {sorted(both)}")
    booked = booked_pnl(legs, exit_prices)
    unbooked = _subset(legs, open_prices)  # also refuses an unknown index
    if any(i not in open_prices for i in range(len(legs)) if i not in exit_prices):
        return PnlSplit(booked, None, None)
    return PnlSplit(booked, unbooked, booked + unbooked)


def exit_prices_now(snapshot: MarketSnapshot, legs: Sequence[TrackedLeg]) -> tuple[Price, ...]:
    """REQ-109 AC-4/AC-5: each named leg's live price now, on the same basis as the entry; any leg not live refuses
    the whole exit (PricesNotLive) - a guessed exit price is never stored."""
    if not legs:
        raise ValueError("a paper exit needs at least one leg")
    prices = tuple(leg_price(snapshot, leg.instrument_id) for leg in legs)
    not_live = [p for p in prices if not is_live(p)]
    if not_live:
        raise PricesNotLive(not_live)
    return prices


def entry_breakevens(legs: Sequence[TrackedLeg]) -> tuple[Decimal, ...] | None:
    """The strategy's at-expiry breakevens on the paper entry prices; None for a multi-expiry strategy (no exact
    ones)."""
    try:
        return strategy_metrics(Strategy(tuple(_engine_leg(leg, None) for leg in legs))).breakevens
    except MultiExpiryError:
        return None


@dataclass(frozen=True)
class TrackingView:
    paused: bool
    pause_reason: PauseReason | None  # a contract reason (first open leg in order) wins over prices_not_live
    paper_pnl: Decimal | None  # the total; None when paused (REQ-109 AC-5)
    as_of: datetime.datetime | None  # paused: the oldest known quote time of an open leg not live
    legs: tuple[Price, ...]
    index: Price | None  # None only when every leg is exited (no market read)
    breakevens: tuple[Decimal, ...] | None  # None: multi-expiry (no exact breakevens) or nothing open
    detections: tuple[Detection, ...]  # empty when the index is not live (index.state says why)
    booked: Decimal = Decimal(0)  # REQ-109 AC-4: exited legs at their exit prices
    unbooked: Decimal | None = None  # open legs at live prices; None when paused
    exited: bool = False  # every leg exited: paper_pnl == booked, frozen
    leg_pnls: tuple[Decimal | None, ...] = ()  # GC-UI D-B48, per leg in order; None = no figure (paused / not live)


def tracking_view(snapshot: MarketSnapshot | None, legs: Sequence[TrackedLeg],
                  threshold_percent: Decimal, contract_reasons: Sequence[ContractReason | None],
                  exit_prices: Mapping[int, Decimal] | None = None) -> TrackingView:
    """``contract_reasons``: per leg, None when its stored contract is live, else why not (module docstring). Required
    (issue #500): a caller cannot price a leg without having asked the catalogue whether its contract is still live.
    ``exit_prices``: leg index -> its paper exit price; those legs are booked and never priced. ``snapshot`` may be
    None only when every leg is exited."""
    reasons = tuple(contract_reasons)
    if len(reasons) != len(legs):
        raise ValueError("tracking_view needs one contract answer per leg")
    exits = dict(exit_prices or {})
    open_legs = [i for i in range(len(legs)) if i not in exits]
    if snapshot is None and open_legs:
        raise ValueError("an open leg needs a market snapshot")
    prices = tuple(_leg_answer(snapshot, leg, reasons[i], i in exits) for i, leg in enumerate(legs))
    split = pnl_split(legs, {i: prices[i].price for i in open_legs if is_live(prices[i])}, exits)
    if snapshot is None:
        return TrackingView(False, None, split.total, None, prices, None, None, (), split.booked, split.unbooked, True,
                            leg_pnls(legs, {}, exits))
    contract_reason = next((reasons[i] for i in open_legs if reasons[i] is not None), None)
    paused = split.unbooked is None
    index = index_price(snapshot)
    still_open = [legs[i] for i in open_legs]
    breakevens = entry_breakevens(still_open) if still_open else None
    detections: tuple[Detection, ...] = ()
    if is_live(index) and contract_reason is None and still_open:
        detections = detect_near_levels(short_strike_levels=short_strikes(still_open), breakevens=breakevens or (),
                                        index_level=index.price, threshold_percent=threshold_percent)
    reason = contract_reason if contract_reason is not None else (PRICES_NOT_LIVE if paused else None)
    as_of = paused_as_of(prices[i] for i in open_legs) if paused else None
    # D-B48: a paused view (REQ-109 AC-5) shows no open leg's figure, so no half-known set; exited legs stay booked.
    live_open = {} if paused else {i: prices[i].price for i in open_legs}
    return TrackingView(paused, reason, split.total, as_of, prices, index, breakevens, detections, split.booked,
                        split.unbooked, not open_legs, leg_pnls(legs, live_open, exits))


def _leg_answer(snapshot: MarketSnapshot | None, leg: TrackedLeg, reason: ContractReason | None,
                exited: bool) -> Price:
    if exited:
        return Price(leg.instrument_id, EXITED, None, None)
    if reason is not None or snapshot is None:
        return Price(leg.instrument_id, reason or "missing", None, None)
    return leg_price(snapshot, leg.instrument_id)
