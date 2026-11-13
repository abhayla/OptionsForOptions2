"""The original Max Profit / Max Loss of a paper book, net of the round-trip charges (F-94, ADR-082 (2), ADR-008).

``book_extremes`` gives the figures before charges. The builder and Compare show them net of the strategy's round-trip
charges (``outcome.service._summary``: max profit - charges, max loss + charges magnitude). The paper book uses the SAME
function for the charges (``charges.round_trip.round_trip_charges``) over its open contracts at their exact average
price, so there is one charges formula; nothing is re-derived here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import ChargesNotComputable, charge_segment, round_trip_charges, to_paise_up
from ofo.engine.extremes import UNLIMITED, BookExtremes, ContractTerms
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.orderbook import BookView

__all__ = ["BookAfterCharges", "book_after_charges", "open_exit_charges", "open_round_trip_charges",
           "sum_after_charges", "with_charges"]

RATES_UNAVAILABLE = "rates_unavailable"
NOT_PRICED = "not_priced"
PRICES_NOT_LIVE = "prices_not_live"


@dataclass(frozen=True)
class BookAfterCharges:
    """ADR-263: a book's P&L now after charges = total - charges already paid - estimated charges to close what is
    open. ``total_after`` is None (never 0) with ``reason`` when any input is absent; ``total_before`` stays."""

    total_before: Decimal | None
    total_after: Decimal | None
    paid: Decimal | None
    open_exit: Decimal | None
    reason: str | None


def open_exit_charges(view: BookView, terms: Mapping[str, ContractTerms], live: Mapping[str, Decimal],
                      underlying: str, rates: ChargeRates | None) -> tuple[Decimal | None, str | None]:
    """The exit half of the charges for every open contract, one opposite-side order at its LIVE price, rounded up once.
    Nothing open -> 0. Else (None, reason): no rates, a contract the rate table cannot price (a futures leg, an unknown
    index, a price the calculator refuses), or an open contract without a live price. Never a silent 0."""
    open_ = [p for p in view.positions if p.net_quantity != 0]
    if not open_:
        return Decimal(0), None
    if rates is None:
        return None, RATES_UNAVAILABLE
    if any(terms[p.instrument_id].instrument is Instrument.FUT for p in open_):
        return None, NOT_PRICED
    if any(live.get(p.instrument_id) is None for p in open_):
        return None, PRICES_NOT_LIVE
    try:
        segment = charge_segment(underlying)
        orders = [ChargeOrder(segment, "SELL" if p.net_quantity > 0 else "BUY", abs(p.net_quantity),
                              live[p.instrument_id]) for p in open_]
        return to_paise_up(charges_for_orders(orders, rates).total), None
    except ValueError:  # ChargesNotComputable is one; the calculator refusing a price or quantity is the other
        return None, NOT_PRICED


def book_after_charges(view: BookView, paid: Decimal | None, open_exit: Decimal | None,
                       reason: str | None = None) -> BookAfterCharges:
    """The one place the after-charges total is formed. ``reason`` says why ``paid`` / ``open_exit`` is absent (the
    caller knows: rates, not priced); without one an absent input still gives a reason, never a bare None."""
    before = view.total
    if before is None:
        return BookAfterCharges(None, None, paid, open_exit, PRICES_NOT_LIVE)
    if paid is None or open_exit is None:
        return BookAfterCharges(before, None, paid, open_exit, reason or RATES_UNAVAILABLE)
    return BookAfterCharges(before, before - paid - open_exit, paid, open_exit, None)


def sum_after_charges(rows: Sequence[BookAfterCharges]) -> BookAfterCharges:
    """The sum of several books' figures. Never a partial sum: when any row has no after figure the answer has none
    either, carrying that first row's reason."""
    absent = next((r for r in rows if r.total_after is None), None)
    if absent is not None:
        return BookAfterCharges(None, None, None, None, absent.reason or RATES_UNAVAILABLE)
    zero = Decimal(0)

    def total(values: list[Decimal | None]) -> Decimal:
        return sum((v or zero for v in values), zero)

    return BookAfterCharges(total([r.total_before for r in rows]), total([r.total_after for r in rows]),
                            total([r.paid for r in rows]), total([r.open_exit for r in rows]), None)


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
