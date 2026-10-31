"""The compare's two cost-side rows and the cost breakdown (ADR-230 (3), GC-MU A2). All arithmetic is the engine's
(``ofo.engine.adjust_money``, ADR-008); this module chooses the figure, or the dash and its reason, and words it.

- "Cost as % of premium left": the approach's cost (the compare's cost row) / its premium left x 100. Premium left zero
  or below, or either input a dash -> "-" with that reason (no division error). Lower is the leader.
- "Change in max profit": the After's max profit minus the Before's, both after charges. Unlimited on either side, or
  either side not worked out -> "-" with the reason. Higher is the leader.
- Charge breakdown: the calculator's own components for the approach's trades (brokerage, STT, exchange transaction
  charges, GST, stamp duty, SEBI turnover fee: SEBI is a separate component of the calculator, so it is shown as one),
  each to the paisa, then the charges total the cost uses and the bid-ask cost, so the lines add up to the cost row.
  The components are approximate (the total rounds up once, as everywhere).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from ofo.charges import ChargeRates
from ofo.charges.calculator import ChargeOrder, OrderCharges, charges_for_orders
from ofo.engine import adjust_money
from ofo.engine.metrics import UNLIMITED
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.money import PAISE

#: (shown id, the calculator's component) in the shown order, after Sensibull's charges panel (bundle-findings 2.5)
COMPONENTS: tuple[tuple[str, Callable[[OrderCharges], Decimal]], ...] = (
    ("brokerage", lambda o: o.brokerage), ("stt", lambda o: o.stt), ("exchange", lambda o: o.exchange_transaction),
    ("gst", lambda o: o.gst), ("stamp", lambda o: o.stamp), ("sebi", lambda o: o.sebi),
)
TOTAL_ID, SPREAD_ID = "charges_total", "bid_ask"


@dataclass(frozen=True)
class Figure:
    """What one new cell shows: ``text`` and ``value`` (None for a dash, with ``reason``), ``rank`` for the leader."""

    text: ExplanationText
    value: Decimal | None = None
    reason: ExplanationText | None = None
    rank: Decimal | None = None


def _dash(reason: ExplanationText | None) -> Figure:
    return Figure(render_explanation("adjust_cmp_dash"), None, reason, None)


def cost_pct_of_premium_left(cost: Decimal | None, cost_reason: ExplanationText | None, left: Decimal | None,
                             left_reason: ExplanationText | None) -> Figure:
    """The cost cell's and the premium-left cell's own figures (value, reason) -> the percent cell."""
    if cost is None:
        return _dash(cost_reason)
    if left is None:
        return _dash(left_reason)
    pct = adjust_money.cost_pct_of_premium_left(cost, left)
    if pct is None:
        return _dash(render_explanation("adjust_cmp_no_premium_left"))
    return Figure(render_explanation("adjust_cmp_percent", value=pct), pct, None, pct)


def max_profit_change(after: object, before: object, reason: ExplanationText | None, before_known: bool) -> Figure:
    """``after`` / ``before``: the whole-trade max profit after charges (a Decimal or ``UNLIMITED``);
    ``reason``: why the
    After has none (None when it has); ``before_known``: whether the Before's figure could be worked out."""
    if reason is not None:
        return _dash(reason)
    if not before_known:
        return _dash(render_explanation("adjust_cmp_before_max_profit_unknown"))
    if after is UNLIMITED or before is UNLIMITED:
        return _dash(render_explanation("adjust_cmp_max_profit_unlimited"))
    change = adjust_money.max_profit_change(after, before)  # type: ignore[arg-type]
    return Figure(render_explanation("adjust_cmp_rupees", amount=change), change, None, change)


def charge_breakdown(orders: Sequence[ChargeOrder], rates: ChargeRates | None, charges_total: Decimal,
                     cost: Decimal) -> tuple[tuple[str, Decimal], ...] | None:
    """(component id, amount) lines under the cost row, or None when no charge can be itemised (no trade, rates not
    known, or a rate the calculator cannot price)."""
    if rates is None or not orders:
        return None
    try:
        per_order = charges_for_orders(list(orders), rates).orders
    except ValueError:
        return None
    lines = [(cid, adjust_money.sum_amounts(pick(o) for o in per_order).quantize(PAISE, ROUND_HALF_EVEN))
             for cid, pick in COMPONENTS]
    spread = adjust_money.sum_amounts((cost, -charges_total))
    return (*lines, (TOTAL_ID, charges_total), (SPREAD_ID, spread.quantize(PAISE, ROUND_HALF_EVEN)))


def breakdown_lines(lines: tuple[tuple[str, Decimal], ...]) -> list[dict[str, str]]:
    """The breakdown as the reply carries it: id, shown label and shown amount (catalogue words)."""
    return [{"id": cid, "label": render_explanation(f"adjust_cmp_charge_{cid}"),
             "text": render_explanation("adjust_cmp_rupees", amount=amount)} for cid, amount in lines]
