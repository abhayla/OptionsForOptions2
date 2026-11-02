"""The original Max Profit / Max Loss of a paper book, net of the round-trip charges (F-94, ADR-082 (2), ADR-008).

``book_extremes`` gives the figures before charges. The builder and Compare show them net of the strategy's round-trip
charges (``outcome.service._summary``: max profit - charges, max loss + charges magnitude). The paper book uses the SAME
function for the charges (``charges.round_trip.round_trip_charges``) over its open contracts at their exact average
price, so there is one charges formula; nothing is re-derived here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.charges.round_trip import ChargesNotComputable, round_trip_charges
from ofo.engine.extremes import UNLIMITED, BookExtremes, ContractTerms
from ofo.engine.legs import Action, Leg
from ofo.engine.orderbook import BookView

__all__ = ["open_round_trip_charges", "with_charges"]


def open_round_trip_charges(view: BookView, terms: Mapping[str, ContractTerms], underlying: str,
                            rates: ChargeRates | None) -> Decimal | None:
    """Round-trip charges of the open contracts at their average price; None when nothing is open, no rates are set,
    or a contract cannot be priced (a futures leg): the figures then stay before charges and say so."""
    open_ = [p for p in view.positions if p.net_quantity != 0 and p.average is not None]
    if rates is None or not open_:
        return None
    legs = [Leg(Action.BUY if p.net_quantity > 0 else Action.SELL, terms[p.instrument_id].instrument,
                terms[p.instrument_id].strike, terms[p.instrument_id].expiry, abs(p.net_quantity), p.average)
            for p in open_]
    try:
        return round_trip_charges(legs, underlying, rates)
    except ChargesNotComputable:
        return None


def with_charges(got: BookExtremes, charges: Decimal | None) -> BookExtremes:
    """``got`` with the charges inside Max Profit and Max Loss (both move down by them); Profit left / Loss left are the
    open position's own range from the live price and stay as they are."""
    if charges is None:
        return got

    def net(value: object) -> object:
        return value if value is None or value is UNLIMITED else value - charges  # type: ignore[operator]

    return replace(got, max_profit=net(got.max_profit), max_loss=net(got.max_loss))
