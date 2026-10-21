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

A start with any leg not live is refused (PricesNotLive): a guessed price is never stored. The view pauses paper P&L
when any leg is not live, and computes no detection when the index is not live. A multi-expiry strategy has no exact
breakevens (MultiExpiryError): paper P&L and the short-strike condition still run, the breakeven condition does not.
Standard library only; no clock is read here.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Sequence

from ofo.adjustment.detection import Detection, detect_near_levels, short_strikes
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import MultiExpiryError, strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.marketdata.quote import NormalizedQuote, is_live_price
from ofo.money import PAISE
from ofo.outcome.snapshot import MarketSnapshot
from ofo.rules.inputs import DataHealth

PriceState = Literal["live", "stale", "missing"]
LIVE: PriceState = "live"


@dataclass(frozen=True)
class Price:
    """One input's price answer: ``price`` is set only when ``state`` is live; ``at`` is the quote time when known."""

    instrument_id: str
    state: PriceState
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


class PricesNotLive(ValueError):
    """A paper entry was asked for while a leg's price is stale or missing (REQ-109 AC-5): nothing is stored."""

    def __init__(self, prices: Sequence[Price]) -> None:
        self.prices = tuple(prices)
        super().__init__("prices are not live for " + ", ".join(f"{p.instrument_id} ({p.state})" for p in prices))


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


def index_price(snapshot: MarketSnapshot) -> Price:
    return price_of(snapshot.spot, snapshot.underlying)


def capture_entry(snapshot: MarketSnapshot, legs: Sequence[TrackedLeg]) -> tuple[TrackedLeg, ...]:
    """The paper entry: each leg's live price now. ``legs`` carry the definition (their entry_price is ignored and
    replaced); any leg not live refuses the whole entry (PricesNotLive)."""
    if not legs:
        raise ValueError("a paper entry needs at least one leg")
    prices = [leg_price(snapshot, leg.instrument_id) for leg in legs]
    not_live = [p for p in prices if p.state != LIVE]
    if not_live:
        raise PricesNotLive(not_live)
    return tuple(TrackedLeg(leg.instrument_id, leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity,
                            p.price, p.at) for leg, p in zip(legs, prices, strict=True))


def _engine_leg(leg: TrackedLeg, current: Decimal | None) -> Leg:
    return Leg(leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, leg.entry_price, current)


def paper_pnl(legs: Sequence[TrackedLeg], current: Sequence[Decimal]) -> Decimal:
    """Paper P&L by the one engine (ADR-008): BUY (current - entry) x qty, SELL (entry - current) x qty, summed."""
    if len(legs) != len(current) or not legs:
        raise ValueError("paper P&L needs one current price per leg")
    return Strategy(tuple(_engine_leg(leg, c) for leg, c in zip(legs, current, strict=True))).live_pnl()


def entry_breakevens(legs: Sequence[TrackedLeg]) -> tuple[Decimal, ...] | None:
    """The strategy's at-expiry breakevens on the paper entry prices; None for a multi-expiry strategy (no exact ones)."""
    try:
        return strategy_metrics(Strategy(tuple(_engine_leg(leg, None) for leg in legs))).breakevens
    except MultiExpiryError:
        return None


@dataclass(frozen=True)
class TrackingView:
    paused: bool
    paper_pnl: Decimal | None  # None when paused (REQ-109 AC-5)
    as_of: datetime.datetime | None  # paused: the oldest known quote time of a leg not live
    legs: tuple[Price, ...]
    index: Price
    breakevens: tuple[Decimal, ...] | None  # None: multi-expiry, no exact breakevens
    detections: tuple[Detection, ...]  # empty when the index is not live (index.state says why)


def tracking_view(snapshot: MarketSnapshot, legs: Sequence[TrackedLeg], threshold_percent: Decimal) -> TrackingView:
    prices = tuple(leg_price(snapshot, leg.instrument_id) for leg in legs)
    paused = any(p.state != LIVE for p in prices)
    pnl = None if paused else paper_pnl(legs, [p.price for p in prices])
    known = [p.at for p in prices if p.state != LIVE and p.at is not None]
    index = index_price(snapshot)
    breakevens = entry_breakevens(legs)
    detections: tuple[Detection, ...] = ()
    if index.state == LIVE:
        detections = detect_near_levels(short_strike_levels=short_strikes(legs), breakevens=breakevens or (),
                                        index_level=index.price, threshold_percent=threshold_percent)
    return TrackingView(paused, pnl, min(known) if paused and known else None, prices, index, breakevens, detections)
