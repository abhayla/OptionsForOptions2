"""The original Max Profit / Max Loss of a paper book, net of the round-trip charges (F-94, ADR-082 (2), ADR-008).

``book_extremes`` gives the figures before charges. The builder and Compare show them net of the strategy's round-trip
charges (``outcome.service._summary``: max profit - charges, max loss + charges magnitude). The paper book uses the SAME
calculator (``charges.calculator``, the formula ``round_trip_charges`` uses) over its open contracts at their exact
average price, so there is one charges formula; nothing is re-derived here. The average can have more than two
decimals (a contract filled at two prices): it is priced as it is, never rounded to a price nobody traded at.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, charges_for_orders
from ofo.charges.round_trip import ChargesNotComputable, charge_segment, to_paise_up
from ofo.engine.extremes import UNLIMITED, BookExtremes, ContractTerms, Figure, book_extremes
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import BookView

__all__ = ["AfterSplit", "BookAfterCharges", "after_split", "book_after_charges", "expiry_hold", "max_after_charges",
           "open_exit_charges", "open_round_trip_charges", "review_charge_lines", "sum_after_charges",
           "sum_booked_after", "with_charges"]

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


def sum_booked_after(rows: Sequence[tuple[Decimal | None, str | None]]) -> tuple[Decimal | None, str | None]:
    """ADR-311 (4), the all-strategies row: the exact sum of every book's Booked after (figure, reason) - or (None, the
    first absent book's reason) when any book has none or fell back to before charges. Never a sum over some books,
    never a mix of bases; a reason is never blank."""
    absent = next((r for r in rows if r[0] is None), None)
    if absent is not None:
        return None, absent[1] or RATES_UNAVAILABLE
    return sum((value for value, _ in rows if value is not None), Decimal(0)), None


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


def open_round_trip_charges(  # noqa: PLR0911, PLR0913 - each refusal names its own absent input
        view: BookView, terms: Mapping[str, ContractTerms], underlying: str,
        rates: ChargeRates | None, paid_exact: Decimal | None = None,
        live: Mapping[str, Decimal] | None = None) -> Decimal | None:
    """The charges inside Max profit / Max loss, rounded UP once; None when nothing is open, no rates are set, or a
    contract cannot be priced (a futures leg): the figures then stay before charges and say so.

    Without ``paid_exact`` (a trade not yet placed, the builder): the ESTIMATE, a round trip of the open contracts at
    their average price. With it (a PLACED book, ADR-263): the charges really paid on every filled order (exact,
    ``paper_charges(...).total``) plus the estimated cost to close the open contracts NOW, at their LIVE price: the same
    exit orders :func:`open_exit_charges` prices for Total after (D-14: one exit cost, not one at the average price
    for the extremes and another at the live price for the total). A placed book with an open contract that has no
    live price gives None (the figures stay before charges and say so; never the average price in its place)."""
    open_ = [p for p in view.positions if p.net_quantity != 0 and p.average is not None]
    if rates is None:
        return None
    if not open_:  # a fully closed placed book: what was paid, nothing left to close (ADR-263, ADR-306 (5))
        return None if paid_exact is None or any(p.net_quantity for p in view.positions) else to_paise_up(paid_exact)
    if any(terms[p.instrument_id].instrument is Instrument.FUT or p.average <= 0 for p in open_):  # type: ignore[operator]
        return None
    try:
        segment = charge_segment(underlying)
    except ChargesNotComputable:
        return None
    if paid_exact is not None and any((live or {}).get(p.instrument_id) is None for p in open_):
        return None  # the cost to close now needs every open contract's live price
    orders = []
    for p in open_:  # ChargeOrder takes any price above 0; only the strategy ``Leg`` demands two decimals
        side, other = ("BUY", "SELL") if p.net_quantity > 0 else ("SELL", "BUY")
        if paid_exact is None:
            orders.append(ChargeOrder(segment, side, abs(p.net_quantity), p.average))  # type: ignore[arg-type]
            orders.append(ChargeOrder(segment, other, abs(p.net_quantity), p.average))  # type: ignore[arg-type]
        else:
            orders.append(ChargeOrder(segment, other, abs(p.net_quantity), live[p.instrument_id]))  # type: ignore[index]
    try:
        return to_paise_up((paid_exact or Decimal(0)) + charges_for_orders(orders, rates).total)
    except ValueError:  # the calculator refusing a price (a live 0) -> no after figure, never a guess
        return None


def review_charge_lines(paid: Decimal, paid_exact: Decimal | None, own: Sequence[ChargeOrder],
                        closing: Sequence[ChargeOrder], rates: ChargeRates) -> tuple[Decimal, Decimal]:
    """The adjustment review's two charge lines beside ``paid``: (the approach's own orders, the closing of what stays
    open), each rounded up. With the exact paid total the three lines add up to the exact sum rounded UP ONCE, the
    figure :func:`open_round_trip_charges` gives the trade page: the exit line takes the rounding remainder.
    Raises ``ValueError`` when the calculator refuses an order (the caller then shows the figures before charges)."""
    zero = Decimal(0)
    adjustment = to_paise_up(charges_for_orders(list(own), rates).total) if own else zero
    exits = to_paise_up(charges_for_orders(list(closing), rates).total) if closing else zero
    if paid_exact is not None and closing and to_paise_up(paid_exact) == paid:
        exact = paid_exact + (charges_for_orders(list(own), rates).total if own else zero)
        exits = max(to_paise_up(exact + charges_for_orders(list(closing), rates).total) - paid - adjustment, zero)
    return adjustment, exits


def with_charges(got: BookExtremes, charges: Decimal | None) -> BookExtremes:
    """``got`` with the charges inside Max Profit and Max Loss (both move down by them); Profit left / Loss left are the
    open position's own range from the live price and stay as they are."""
    if charges is None:
        return got

    def net(value: object) -> object:
        return value if value is None or value is UNLIMITED else value - charges  # type: ignore[operator]

    return replace(got, max_profit=net(got.max_profit), max_loss=net(got.max_loss))


def max_after_charges(  # noqa: PLR0913 - the book, its terms, live prices, underlying, rates and the exact paid
        view: BookView, terms: Mapping[str, ContractTerms], live: Mapping[str, Decimal], underlying: str,
        rates: ChargeRates | None, paid_exact: Decimal | None = None) -> BookExtremes:
    """THE one function for Max profit / Max loss after charges (ADR-263, ADR-008): the trade page, the practice list
    and Profit left / Loss left (``after_split``) read it; the adjustment review reaches the same figure through
    ``routes.adjustment.price_after``, whose charge lines come from :func:`review_charge_lines` (the same total, rounded
    once) and whose booked figure stays exact."""
    return with_charges(book_extremes(view, terms, live),
                        open_round_trip_charges(view, terms, underlying, rates, paid_exact, live))


@dataclass(frozen=True)
class AfterSplit:
    """ADR-303 / ADR-306: the after-charges parts of a paper book. All None when the book has no after total
    (``BookAfterCharges.reason`` says why); ``recover`` is the loss on screen (minus Total after), else None."""

    booked_after: Decimal | None
    unbooked_after: Decimal | None
    profit_left_after: Figure | None
    loss_left_after: Figure | None
    recover: Decimal | None
    booked_reason: str | None = None  # ADR-311: why booked_after is absent (the charges paid are unknown), else None


def after_split(  # noqa: PLR0913 - the book, its terms, live prices, underlying, rates and the after-charges total
        view: BookView, terms: Mapping[str, ContractTerms], live: Mapping[str, Decimal], underlying: str,
        rates: ChargeRates | None, after: BookAfterCharges, paid_exact: Decimal | None = None) -> AfterSplit:
    """The one place Booked / Unbooked / Profit left / Loss left are put after charges. Booked after = booked - ALL
    charges paid; Unbooked after = open-leg P&L - the estimated charges to close, so the two add up to
    ``after.total_after`` exactly (ADR-303). ADR-306: Profit left after = Max profit after - Total after and Loss left
    after = Max loss after - Total after (so Total + left = the extreme, exactly), NOT capped (ADR-302); a closed book
    has 0 left. ``recover`` = minus Total after when Total after is negative (the loss on screen), else None.
    ADR-311 (4): while the total is missing, Booked after stands alone ONLY when the reason is a missing price (then
    Total and Unbooked show no number at all). For any other reason all three fall back to before charges together.
    The sum rule (booked + unbooked = total after) holds whenever all three are given; a lone Booked is never a total.
    ``booked_reason`` says why Booked after is absent when the charges paid are unknown (no rates / not priced)."""
    if after.total_after is None or view.unbooked is None:
        if after.paid is None:
            return AfterSplit(None, None, None, None, None, RATES_UNAVAILABLE if rates is None else NOT_PRICED)
        alone = view.booked - after.paid if after.reason == PRICES_NOT_LIVE else None
        return AfterSplit(alone, None, None, None, None)
    booked_after = view.booked - after.paid
    unbooked_after = view.unbooked - after.open_exit
    got = book_extremes(view, terms, live)
    if got.profit_left is None or got.loss_left is None:  # multi expiry: no left figure, the extremes reason says so
        return AfterSplit(booked_after, unbooked_after, None, None, None)
    if not any(p.net_quantity for p in view.positions):
        return AfterSplit(booked_after, unbooked_after, got.profit_left, got.loss_left, None)
    if open_round_trip_charges(view, terms, underlying, rates, paid_exact, live) is None:  # ADR-306 (6): one basis
        return AfterSplit(booked_after, unbooked_after, None, None, None)
    net, total = max_after_charges(view, terms, live, underlying, rates, paid_exact), after.total_after

    def left(extreme: Figure | None) -> Figure | None:
        return extreme if extreme is None or extreme is UNLIMITED else extreme - total  # type: ignore[operator]

    return AfterSplit(booked_after, unbooked_after, left(net.max_profit), left(net.max_loss),
                      -total if total < 0 else None)


def expiry_hold(before: BookExtremes, after: BookAfterCharges) -> tuple[Figure, Figure] | None:
    """ADR-320 (2), expiry day only: (Max profit, Profit left) "If held to expiry". Settlement books no exit order, so
    the held Max profit = Max profit before charges - the charges already PAID (``after.paid``, the figure Total after
    deducts); Profit left held = that - Total after (the one Total on screen, ADR-306 (1), (3)). The "If exited now"
    pair is the usual :func:`max_after_charges` / :func:`after_split` figures. None when any input is absent (no
    mixing of bases, ADR-306 (6)). Exercise STT on a long leg settling in the money is not in it: the maximum of a
    defined-risk short book (the condors of the 23 Nov test) has every long leg out of the money.
    Real case C2 157: 484.25 - 97.24 = +387.01, the settlement; the screen read 484.25 - 193.76 = +290.49."""
    top = before.max_profit
    if top is None or after.paid is None or after.total_after is None:
        return None
    if top is UNLIMITED:
        return UNLIMITED, UNLIMITED
    held = top - after.paid  # type: ignore[operator]
    return held, held - after.total_after
