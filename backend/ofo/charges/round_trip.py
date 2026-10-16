"""Round-trip charges of a strategy at its planned prices, and STT on exercise at an expiry level (W-075, ADR-082 (2)).

Round trip (W-075 decision (a)): each leg's entry order plus the OPPOSITE-side exit order of the same quantity, both at the
leg's planned price. Exercise STT (ADR-082): a BOUGHT option that finishes in the money adds ``exercise_stt`` at that
level's intrinsic value; a sold option or an out-of-the-money bought option adds nothing.

Only options on the NSE/BSE index contracts have a published rate here. A futures leg, an index with no known exchange
segment, or a price the calculator refuses is :class:`ChargesNotComputable`: the caller keeps ADR-071's honest phrase
rather than show a made-up figure.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ofo.charges.calculator import ChargeOrder, charges_for_orders, exercise_stt
from ofo.charges.rates import ChargeRates
from ofo.engine.legs import Action, Instrument, Leg

#: The index -> exchange segment map (NIFTY options trade on NSE, SENSEX options on BSE).
SEGMENT_BY_UNDERLYING = {"NIFTY": "NSE_FO", "SENSEX": "BSE_FO"}


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
        return charges_for_orders(orders, rates).total
    except ValueError as exc:
        raise ChargesNotComputable(str(exc)) from exc


def is_bought_option(leg: Leg) -> bool:
    """A bought option leg (CE or PE): the only kind that can be exercised, so the only kind that can owe exercise STT."""
    return leg.action is Action.BUY and leg.is_option


def holds_bought_option(legs: Sequence[Leg]) -> bool:
    return any(is_bought_option(leg) for leg in legs)


def exercise_stt_at(legs: Sequence[Leg], level: Decimal, rates: ChargeRates) -> Decimal:
    """STT on exercise at underlying ``level``: bought options with intrinsic value above 0 only."""
    total = Decimal("0")
    for leg in legs:
        if not is_bought_option(leg):
            continue
        intrinsic = max(level - leg.strike, Decimal(0)) if leg.instrument is Instrument.CE else max(leg.strike - level, Decimal(0))
        if intrinsic > 0:
            total += exercise_stt(intrinsic, leg.quantity, rates)
    return total
