"""Round-trip charges of a strategy at its planned prices, and STT on exercise at an expiry level (W-075, ADR-082 (2)).

Round trip (W-075 decision (a)): each leg's entry order plus the OPPOSITE-side exit order of the same quantity, both at
the leg's planned price. Exercise STT (ADR-082): a BOUGHT option that finishes in the money adds ``exercise_stt`` at that
level's intrinsic value; a sold option or an out-of-the-money bought option adds nothing.

Only options on the NSE/BSE index contracts have a published rate here. A futures leg, an index with no known exchange
segment, or a price the calculator refuses is :class:`ChargesNotComputable`: the caller keeps ADR-071's honest phrase
rather than show a made-up figure.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal

from ofo.charges.calculator import ChargeOrder, charges_for_orders, exercise_stt
from ofo.charges.rates import ChargeRates
from ofo.engine.legs import Action, Instrument, Leg
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS
from ofo.money import PAISE

#: The index -> exchange segment map (NIFTY options trade on NSE, SENSEX options on BSE).
SEGMENT_BY_UNDERLYING = dict(SUPPORTED_UNDERLYINGS)  # the one home (REQ-001 AC-4)


def to_paise_up(amount: Decimal) -> Decimal:
    """A displayed charge rounded UP to the paisa once: never understated (the calculator stays exact, F-35)."""
    return amount.quantize(PAISE, rounding=ROUND_CEILING)


class ChargesNotComputable(ValueError):
    """The strategy has a leg the options rate table cannot price."""


def _segment(underlying: str) -> str:
    try:
        return SEGMENT_BY_UNDERLYING[underlying]
    except KeyError:
        raise ChargesNotComputable(f"no exchange segment is known for {underlying!r}") from None


def _check_options(legs: Sequence[Leg]) -> None:
    for leg in legs:
        if not leg.is_option:
            raise ChargesNotComputable("the rate table covers options only; a futures leg has no rate here")


def round_trip_charges(legs: Sequence[Leg], underlying: str, rates: ChargeRates) -> Decimal:
    """Total charges and taxes of entering and leaving every leg at its planned (entry) price."""
    if not legs:
        raise ChargesNotComputable("a strategy needs at least one leg")
    segment = _segment(underlying)
    _check_options(legs)
    orders: list[ChargeOrder] = []
    try:
        for leg in legs:
            entry = "BUY" if leg.action is Action.BUY else "SELL"
            exit_ = "SELL" if entry == "BUY" else "BUY"
            orders.append(ChargeOrder(segment, entry, leg.quantity, leg.entry_price))
            orders.append(ChargeOrder(segment, exit_, leg.quantity, leg.entry_price))
        return to_paise_up(charges_for_orders(orders, rates).total)
    except ValueError as exc:
        raise ChargesNotComputable(str(exc)) from exc


@dataclass(frozen=True)
class ChargesBreakdown:
    """ADR-167 (2): the round-trip charges shown ONCE, by component (Sensibull screen 022). Each component is the sum
    over the strategy's entry and exit orders rounded half-even to the paisa; ``total`` is :func:`round_trip_charges`
    (rounded UP once), so the parts can differ from the total by a paisa or two. ``read_on`` is the date of the rates.
    Never part of a payoff curve or a scenario value."""

    brokerage: Decimal
    stt: Decimal
    exchange_transaction: Decimal
    gst: Decimal
    stamp: Decimal
    sebi: Decimal
    total: Decimal
    read_on: datetime.date


def round_trip_breakdown(legs: Sequence[Leg], underlying: str, rates: ChargeRates) -> ChargesBreakdown:
    """The charges of :func:`round_trip_charges`, split by component; ChargesNotComputable gives no breakdown at all."""
    # copied from origin/build/W-127-b2-payoff @194cc405 (backend/ofo/charges/round_trip.py), plus read_on
    total = round_trip_charges(legs, underlying, rates)  # raises ChargesNotComputable for what has no rate
    segment = _segment(underlying)
    orders: list[ChargeOrder] = []
    for leg in legs:
        entry = "BUY" if leg.action is Action.BUY else "SELL"
        orders.append(ChargeOrder(segment, entry, leg.quantity, leg.entry_price))
        orders.append(ChargeOrder(segment, "SELL" if entry == "BUY" else "BUY", leg.quantity, leg.entry_price))
    parts = charges_for_orders(orders, rates).orders

    def part(name: str) -> Decimal:
        return sum((getattr(c, name) for c in parts), Decimal("0")).quantize(PAISE, rounding=ROUND_HALF_EVEN)

    return ChargesBreakdown(part("brokerage"), part("stt"), part("exchange_transaction"), part("gst"), part("stamp"),
                            part("sebi"), total, rates.read_on)


def is_bought_option(leg: Leg) -> bool:
    """A bought option leg (CE or PE): the only kind that can be exercised, so the only one owing exercise STT."""
    return leg.action is Action.BUY and leg.is_option


def holds_bought_option(legs: Sequence[Leg]) -> bool:
    return any(is_bought_option(leg) for leg in legs)


def exercise_stt_at(legs: Sequence[Leg], level: Decimal, rates: ChargeRates) -> Decimal:
    """STT on exercise at underlying ``level``: bought options with intrinsic value above 0 only."""
    total = Decimal("0")
    for leg in legs:
        if not is_bought_option(leg):
            continue
        distance = level - leg.strike if leg.instrument is Instrument.CE else leg.strike - level
        intrinsic = max(distance, Decimal(0))
        if intrinsic > 0:
            total += exercise_stt(intrinsic, leg.quantity, rates)
    return to_paise_up(total)
