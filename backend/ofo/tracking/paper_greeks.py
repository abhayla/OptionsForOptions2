"""Net Greeks of a paper book's open contracts (GC-TP R-19b; Sensibull Drafts Mode screen 090, the Greeks action).

Spec basis: ADR-008 (one engine owns every number: this module only signs and sums the engine's per-unit
``leg_greeks_unrounded``, the table's own signing and rounding); REQ-109 AC-5 (a figure that needs a price that is not
live is absent with the reason, never a partial sum); ADR-207 ("a saved plan can never differ silently from the paper
position").

A contract's Greeks are computed exactly as the P&L table computes a leg (ofo.table.model): per-unit Black-Scholes
Greeks at the IV solved from the leg's quote (the same solve as ``paper_decay``), x quantity x sign (BUY +1, SELL -1;
here the signed net quantity). A futures contract has delta 1 per unit and no other Greek (the table's rule). Each
leg's value and the NET are rounded ONCE, to 4 dp, from the UNROUNDED position values (a displayed leg can differ from
the displayed net by up to 0.0001 per leg: the table's own boundary behaviour).

Answer states, each an absent figure with a closed reason: an option with no solvable IV (``no_iv``); the model
refusing the spot or a forward (``model_refused``). No open contract: no figure (the caller says the book is exited).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from ofo.engine.black_scholes import Greeks
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import SpotRefused, leg_greeks_unrounded, model_inputs
from ofo.marketdata.forward import ForwardUnavailable
from ofo.outcome.snapshot import MarketSnapshot
from ofo.scenario.spot import spot_reading
from ofo.table.model import FUTURES_PER_UNIT_GREEKS, position_greeks, round_greek
from ofo.tracking.paper_decay import OpenContract, solved_iv

GreeksReason = Literal["no_iv", "model_refused"]
NO_IV: GreeksReason = "no_iv"
MODEL_REFUSED: GreeksReason = "model_refused"


@dataclass(frozen=True)
class BookGreeks:
    """``legs`` (in the callers' order, rounded once) and ``net``; both None exactly when ``reason`` is set."""
    legs: tuple[Greeks, ...] | None
    net: Greeks | None
    reason: GreeksReason | None


def _rounded(g: Greeks) -> Greeks:
    return Greeks(round_greek(g.delta), round_greek(g.gamma), round_greek(g.theta), round_greek(g.vega))


def book_greeks(snapshot: MarketSnapshot, underlying: str, contracts: Sequence[OpenContract]) -> BookGreeks:
    """Each open contract's position Greeks and their net, from the one snapshot the book was priced from."""
    legs: list[LegInput] = []
    for c in contracts:
        iv = None
        if c.instrument is not Instrument.FUT:
            iv = solved_iv(snapshot, underlying, c)
            if iv is None:
                return BookGreeks(None, None, NO_IV)
        action = Action.BUY if c.net_quantity > 0 else Action.SELL
        legs.append(LegInput(underlying, c.key, action, c.instrument, c.strike, c.expiry, abs(c.net_quantity), c.ltp,
                             c.ltp, iv))
    try:
        model = model_inputs(StrategyInput(underlying, spot_reading(snapshot.spot), snapshot.valuation, snapshot.rate,
                                           tuple(legs)), snapshot.forwards)
    except (SpotRefused, ForwardUnavailable):
        return BookGreeks(None, None, MODEL_REFUSED)
    try:
        positions = [position_greeks(FUTURES_PER_UNIT_GREEKS if leg.instrument is Instrument.FUT
                                     else leg_greeks_unrounded(model, leg), leg.action, leg.quantity) for leg in legs]
    except (ValueError, ArithmeticError):  # the model refusing a leg's inputs: no figure, never a partial net
        return BookGreeks(None, None, MODEL_REFUSED)
    zero = Decimal(0)
    net = Greeks(sum((g.delta for g in positions), zero), sum((g.gamma for g in positions), zero),
                 sum((g.theta for g in positions), zero), sum((g.vega for g in positions), zero))
    return BookGreeks(tuple(_rounded(g) for g in positions), _rounded(net), None)
