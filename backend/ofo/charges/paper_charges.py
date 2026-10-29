"""Charges of a paper strategy's recorded orders (GC-TP step 8a; REQ-109 AC-10, ADR-207 (7), ADR-082).

Spec basis: REQ-109 AC-10 "Each paper strategy shows a Charges figure beside its P&L (not subtracted from it ...), the
sum of the charges engine's figure for every paper order"; ADR-082 (the rates, exercise STT); Sensibull study 050.

Per order kind:

- ``open`` / ``add`` / ``exit`` / ``stop``: a normal executed order at its recorded price: :func:`charges_for_order`
  (brokerage, STT on a sell, exchange transaction, SEBI, stamp on a buy, GST), exact.
- ``settle`` (an open leg settled on its expiry day at its intrinsic value, ADR-207 (6)): no order reaches the exchange,
  so no brokerage, transaction, SEBI, stamp or GST. A SELL settle closes a BOUGHT option: in the money (price above 0,
  the price IS the intrinsic value per unit) it pays STT on exercise, :func:`exercise_stt` on intrinsic x quantity
  (ADR-082: "a BOUGHT option that finishes in the money adds exercise_stt"). A BUY settle closes a SOLD option: STT on
  exercise is levied on the holder who exercises, not on the writer, so it adds 0 (the same rule as
  ``round_trip.exercise_stt_at``). An out-of-the-money settle (price 0) is not exercised and adds 0.

The figures are exact Decimals (F-35: no rounding per order); :func:`to_paise_up` rounds the strategy total UP to the
paisa ONCE for display, never understated. A futures order, an index with no known exchange segment or a price the
calculator refuses is :class:`ChargesNotComputable`: the caller shows the Charges as absent with a reason, never 0 and
never an estimate. The figure is beside P&L: nothing here touches a P&L number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from ofo.charges.calculator import ChargeOrder, charges_for_order, exercise_stt
from ofo.charges.rates import ChargeRates
from ofo.charges.round_trip import SEGMENT_BY_UNDERLYING, ChargesNotComputable, to_paise_up
from ofo.engine.legs import Action

SETTLE: Final = "settle"
ORDER_KINDS: Final = frozenset({"open", "add", "exit", "stop", SETTLE})
_ZERO: Final = Decimal(0)


@dataclass(frozen=True)
class PaperFill:
    """One recorded paper order: kind, side (BUY / SELL), quantity in units, price per unit, and whether its contract
    is an option (the rate table covers options only)."""

    kind: str
    side: str
    quantity: int
    price: Decimal
    is_option: bool


@dataclass(frozen=True)
class PaperCharges:
    """``per_order`` parallel to the fills, exact; ``total`` exact; ``shown`` the total rounded UP to the paisa once."""

    per_order: tuple[Decimal, ...]
    total: Decimal
    shown: Decimal


def _settle_charge(fill: PaperFill, rates: ChargeRates) -> Decimal:
    if fill.side == Action.SELL.value and fill.price > 0:  # a bought option settled in the money: exercised
        return exercise_stt(fill.price, fill.quantity, rates)
    return _ZERO  # a sold option settled (STT on exercise is the holder's), or out of the money (not exercised)


def _one(fill: PaperFill, segment: str, rates: ChargeRates) -> Decimal:
    if fill.kind not in ORDER_KINDS:
        raise ChargesNotComputable(f"unknown paper order kind {fill.kind!r}: no charge rule, none is assumed")
    if not fill.is_option:
        raise ChargesNotComputable("the rate table covers options only; a futures order has no rate here")
    if fill.kind == SETTLE:
        return _settle_charge(fill, rates)
    return charges_for_order(ChargeOrder(segment, fill.side, fill.quantity, fill.price), rates).total


def paper_charges(fills: Sequence[PaperFill], underlying: str, rates: ChargeRates) -> PaperCharges:
    """The charges of every recorded paper order of one strategy and their sum (see the module text for each kind)."""
    if not fills:
        raise ChargesNotComputable("a paper strategy needs at least one order")
    try:
        segment = SEGMENT_BY_UNDERLYING[underlying]
    except KeyError:
        raise ChargesNotComputable(f"no exchange segment is known for {underlying!r}") from None
    try:
        per_order = tuple(_one(f, segment, rates) for f in fills)
    except ChargesNotComputable:
        raise
    except ValueError as exc:  # the calculator refused a price or quantity
        raise ChargesNotComputable(str(exc)) from exc
    total = sum(per_order, _ZERO)
    return PaperCharges(per_order, total, to_paise_up(total))


def charges_sum(shown: Sequence[Decimal | None]) -> Decimal | None:
    """The Paper totals' Charges: the sum of every strategy's shown figure, or None (never a partial sum) as soon as one
    strategy's is absent. No strategies: 0."""
    if any(s is None for s in shown):
        return None
    return sum((s for s in shown if s is not None), _ZERO)
