"""Total Decay of a paper book's open contracts to the next market open (GC-TP step 4a; REQ-145 AC-2, F-63).

Spec basis: REQ-145 AC-2 / finding F-63 (Decay = the model value at the next market open minus the model value now,
after Theta); ADR-008 (one engine owns every number: this module only signs and sums the engine's per-unit
``leg_decay_unrounded``); REQ-109 AC-5 (a figure that needs a price that is not live is absent with the reason, never a
partial sum).

A contract's decay is computed exactly as the P&L table's Decay column computes a leg (ofo.table.model._decay_cell):
per-unit decay from the engine x quantity x sign (BUY +1, SELL -1), here the signed net quantity. Its IV is solved
like an outcome leg's (``implied_vol`` at ``iv_price`` of the leg's quote, the expiry's parity forward, the live spot).
The sum is UNROUNDED; the caller rounds once at its own boundary (like the table's TOTAL row).

Answer states, each an absent figure with a closed reason: an open contract whose price is not live
(``prices_not_live`` or the contract's own reason, passed in); an option with no solvable IV (``no_iv``); no next
market open in the calendar (``no_next_open``); the model refusing the spot or forward (``model_refused``). A futures
contract decays a true 0. No open contract: 0.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.engine.book_totals import signed_decay
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import SpotRefused, expiry_model, implied_vol, iv_price, leg_decay_unrounded, model_inputs
from ofo.market_calendar import next_open
from ofo.marketdata.forward import ForwardUnavailable
from ofo.outcome.snapshot import MarketSnapshot
from ofo.scenario.spot import spot_reading
from ofo.tracking.paper import PauseReason

DecayReason = Literal["no_iv", "no_next_open", "model_refused"]
NO_IV: DecayReason = "no_iv"
NO_NEXT_OPEN: DecayReason = "no_next_open"
MODEL_REFUSED: DecayReason = "model_refused"


@dataclass(frozen=True)
class OpenContract:
    """One open contract of a book at a LIVE price (the caller drops the book's decay when any open price is not
    live). ``net_quantity`` is signed: above 0 long, below 0 short."""

    key: str  # the snapshot's instrument id
    instrument: Instrument
    strike: Decimal | None
    expiry: datetime.date
    net_quantity: int
    ltp: Decimal


@dataclass(frozen=True)
class Decay:
    value: Decimal | None  # unrounded rupees; None exactly when ``reason`` is set
    reason: DecayReason | PauseReason | None  # a book paused by a price passes its own pause reason


def solved_iv(snapshot: MarketSnapshot, underlying: str, c: OpenContract) -> Decimal | None:
    market = snapshot.legs.get(c.key)
    quote = None if market is None else market.quote
    fwd = snapshot.forwards.get(c.expiry)
    if quote is None or fwd is None or c.strike is None:
        return None
    price = iv_price(quote)
    if price is None:
        return None
    try:
        return implied_vol(expiry_model(spot_reading(snapshot.spot), fwd, underlying=underlying), c.instrument, price,
                           c.strike).iv
    except (ValueError, ArithmeticError):  # SpotRefused / ForwardUnavailable are ValueErrors: no IV
        return None


def book_decay(snapshot: MarketSnapshot | None, underlying: str, contracts: Sequence[OpenContract]) -> Decay:
    """The signed, unrounded sum of every open contract's decay to the next market open after the snapshot."""
    if not contracts:
        return Decay(Decimal(0), None)
    if snapshot is None:
        raise ValueError("open contracts at live prices need the snapshot they were priced from")
    until = next_open(snapshot.valuation)
    if until is None:
        return Decay(None, NO_NEXT_OPEN)
    legs: list[LegInput] = []
    for c in contracts:
        iv = None
        if c.instrument is not Instrument.FUT:
            iv = solved_iv(snapshot, underlying, c)
            if iv is None:
                return Decay(None, NO_IV)
        action = Action.BUY if c.net_quantity > 0 else Action.SELL
        legs.append(LegInput(underlying, c.key, action, c.instrument, c.strike, c.expiry, abs(c.net_quantity), c.ltp,
                             c.ltp, iv))
    try:
        model = model_inputs(StrategyInput(underlying, spot_reading(snapshot.spot), snapshot.valuation, snapshot.rate,
                                           tuple(legs)), snapshot.forwards)
    except (SpotRefused, ForwardUnavailable):
        return Decay(None, MODEL_REFUSED)
    units = [(leg_decay_unrounded(model, leg, until), c.net_quantity) for c, leg in zip(contracts, legs, strict=True)]
    return Decay(signed_decay(units), None)  # per unit x quantity x sign, in the engine
