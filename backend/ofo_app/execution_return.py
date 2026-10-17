"""W-096: the parts of the return from Kite that need no database (REQ-073 AC-3, ADR-105, design review 3/5/6).

Spec basis: REQ-073 AC-3 ("When the user returns from Kite, the platform reads the actual order states and positions
from Zerodha and reconciles them (REQ-057, REQ-060); a basket the user closed or only partly placed is handled as a
partial execution (REQ-058), never retried automatically."); REQ-057 AC-2 (a submitted order changes nothing until the
broker confirms execution); REQ-058 AC-2 (the four choices, in order) and AC-6 (never resubmitted); REQ-060 AC-7 (units
in no strategy block no strategy; a shortfall or the wrong side blocks this one); ADR-050 item 4(d) (external orders
recorded, never dropped).

- ``read_book``: today's orders and trades -> THIS strategy's rows only (``parse_tag`` decodes exactly to its id).
  A tag in a stored plan is ours; a tag for this strategy in no stored plan is EXTERNAL (kept, never dropped). Trades
  are taken for our orders only and de-duplicated by (order id, trade id): the same key twice with other content is a
  conflict (that order cannot be trusted), never a second fill.
- ``classify``: one open plan against the book. The status word is kept as read and only asked "terminal?" against
  ``execute_plan.TERMINAL_ORDER_STATUSES`` (an allow-list; any other or unknown word is still working, finding
  trust-broker-status-word); quantities come from ``filled_quantity``, which must equal the sum of today's trades for
  that order, else the plan stays open and needs reconciliation (never pick one).
- ``drifted``: a CLOSED plan whose tags show, in today's book, a filled quantity other than the one stored at close (an
  order that appeared or filled after the close) needs reconciliation (design review finding 5).
- ``reconcile``: per contract the strategy traded, Zerodha's net minus the units every OTHER stored strategy holds is
  this strategy's share; ``execute_plan.strategy_blocked`` decides the block (one copy of REQ-060 AC-7). Units beyond
  the strategy are unexplained: listed, blocking nothing.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ofo.execution.basket import parse_tag
from ofo.orders.model import FillEvent, realised_pnl

from ofo_app import execute_plan as ep
from ofo_app.execution_plan_store import PlanOrder, StoredPlan
from ofo_app.kite_replies import BrokerOrderRow, fill_from_trade_row, order_from_row

WAITING = "waiting"
FILLED = "filled"
EXITED = "exited"
NOTHING_PLACED = "nothing_placed"
PARTIAL = "partial"
RECONCILE = "reconciliation_required"
#: REQ-058 AC-2, in its order: "Complete Strategy, Retry Failed Leg, Review Manually, Close Partial Strategy."
PARTIAL_CHOICES = ("complete_strategy", "retry_failed_leg", "review_manually", "close_partial_strategy")
#: Mismatch kinds, named by their catalogue template (ofo.reconciliation.compare's ids; the screen renders the text).
MISSING, SIDE, QUANTITY = "recon_missing_platform_position", "recon_side_mismatch", "recon_quantity_mismatch"


@dataclass(frozen=True)
class TodaysBook:
    ours: Mapping[str, tuple[BrokerOrderRow, ...]]  # stored tag -> its rows (a basket posted twice -> two rows)
    external: tuple[Mapping[str, object], ...]  # rows tagged for this strategy with no stored plan, as read
    traded: Mapping[str, int]  # order id -> today's traded units (de-duplicated)
    fills: tuple[FillEvent, ...]  # our orders' fills, each (order id, trade id) once
    conflicting: frozenset[str]  # order ids whose trades repeat a key with other content


def _ours(row: Mapping[str, object], strategy_id: int) -> bool:
    try:
        return parse_tag(row.get("tag")).strategy_id == strategy_id
    except ValueError:
        return False  # no tag, or not a basket tag of ours


def _split_orders(order_rows: Sequence[Mapping[str, object]], strategy_id: int,
                  stored_tags: frozenset[str]) -> tuple[dict[str, tuple[BrokerOrderRow, ...]], list]:
    ours: dict[str, tuple[BrokerOrderRow, ...]] = {}
    external = []
    for row in order_rows:
        if not isinstance(row, Mapping):
            raise ValueError("an order row must be a mapping")  # an unreadable book never passes
        if not _ours(row, strategy_id):
            continue
        if row["tag"] in stored_tags:
            ours[row["tag"]] = (*ours.get(row["tag"], ()), order_from_row(row))
        else:
            order_from_row(row)  # an external row is read as strictly as ours (fail closed), then kept as read
            external.append(row)
    return ours, external


def _fills(trade_rows: Sequence[Mapping[str, object]], order_ids: frozenset[str]):
    seen: dict[tuple[str, str], FillEvent] = {}
    conflicting = set()
    for row in trade_rows:
        if not isinstance(row, Mapping):
            raise ValueError("a trade row must be a mapping")
        if row.get("order_id") not in order_ids:
            continue
        fill = fill_from_trade_row(row)
        key = (fill.broker_order_id, fill.trade_id)
        if key in seen and seen[key] != fill:
            conflicting.add(fill.broker_order_id)
        seen.setdefault(key, fill)
    traded: dict[str, int] = {}
    for fill in seen.values():
        traded[fill.broker_order_id] = traded.get(fill.broker_order_id, 0) + fill.quantity
    return tuple(seen.values()), traded, frozenset(conflicting)


def read_book(order_rows: Sequence[Mapping[str, object]], trade_rows: Sequence[Mapping[str, object]],
              strategy_id: int, stored_tags: frozenset[str]) -> TodaysBook:
    ours, external = _split_orders(order_rows, strategy_id, stored_tags)
    order_ids = frozenset(r.order_id for rows in ours.values() for r in rows)
    fills, traded, conflicting = _fills(trade_rows, order_ids)
    return TodaysBook(ours, tuple(external), traded, fills, conflicting)


@dataclass(frozen=True)
class PlanAnswer:
    state: str  # WAITING | RECONCILE (plan stays open) or FILLED | NOTHING_PLACED | PARTIAL (a close reason)
    filled: Mapping[str, int]  # tag -> Zerodha's filled quantity (empty while the plan stays open)


def _agrees(order: PlanOrder, row: BrokerOrderRow, book: TodaysBook) -> bool:
    """The row is the planned order (same contract, same side) and Zerodha's fill count equals its trades."""
    return (row.tradingsymbol == order.tradingsymbol and row.side.value == order.transaction_type
            and row.order_id not in book.conflicting and book.traded.get(row.order_id, 0) == row.filled_quantity)


def _close_reason(plan: StoredPlan, filled: Mapping[str, int]) -> str:
    if all(filled[o.tag] == o.quantity for o in plan.orders):
        return FILLED
    if all(filled[o.tag] == 0 for o in plan.orders):
        return NOTHING_PLACED  # every order ended unfilled, or the user closed the basket (no tag in the book)
    return PARTIAL


def classify(plan: StoredPlan, book: TodaysBook) -> PlanAnswer:
    """Zerodha's answer for one OPEN plan. Nothing here is resent or retried (REQ-058 AC-6)."""
    rows = {o.tag: book.ours.get(o.tag, ()) for o in plan.orders}
    if any(r.status not in ep.TERMINAL_ORDER_STATUSES for found in rows.values() for r in found):
        return PlanAnswer(WAITING, {})  # REQ-057 AC-2: an order still working changes nothing
    filled = {}
    for order in plan.orders:
        if not all(_agrees(order, r, book) for r in rows[order.tag]):
            return PlanAnswer(RECONCILE, {})
        filled[order.tag] = sum(r.filled_quantity for r in rows[order.tag])
        if filled[order.tag] > order.quantity:
            return PlanAnswer(RECONCILE, {})  # more filled than planned (a basket posted twice)
    return PlanAnswer(_close_reason(plan, filled), filled)


def drifted(history: Sequence[StoredPlan], book: TodaysBook) -> tuple[int, ...]:
    """Closed plans whose orders, in today's book, are not terminal or filled other than stored at close."""
    out = []
    for plan in history:
        if plan.status != "closed":
            continue
        for order in plan.orders:
            found = book.ours.get(order.tag, ())
            if not found:
                continue  # not in today's book (another day): nothing to compare
            moving = any(r.status not in ep.TERMINAL_ORDER_STATUSES for r in found)
            if moving or sum(r.filled_quantity for r in found) != (order.filled_quantity or 0):
                out.append(plan.plan_number)
                break
    return tuple(out)


@dataclass(frozen=True)
class ContractCheck:
    key: tuple
    platform_units: int  # what this strategy holds by its stored fills (BUY +, SELL -)
    zerodha_units: int  # Zerodha's account-wide net
    other_units: int  # what every other stored strategy holds
    kind: str | None  # a blocking mismatch's catalogue id, else None

    @property
    def unexplained(self) -> int:
        """Zerodha's units beyond every stored strategy: listed, blocking nothing (REQ-060 AC-7)."""
        return self.zerodha_units - self.other_units - self.platform_units


def _kind(share: int, units: int) -> str | None:
    if not ep.strategy_blocked({"c": share}, {"c": units}):
        return None
    if share == 0:
        return MISSING
    return SIDE if (share > 0) != (units > 0) else QUANTITY


def reconcile(keys: Sequence[tuple], held: Mapping[tuple, int], others: Mapping[tuple, int],
              broker_net: Mapping[tuple, int]) -> tuple[ContractCheck, ...]:
    """One row per contract the strategy traded (``keys``)."""
    rows = []
    for key in keys:
        units, other, net = held.get(key, 0), others.get(key, 0), broker_net.get(key, 0)
        rows.append(ContractCheck(key, units, net, other, _kind(net - other, units)))
    return tuple(rows)


def exit_is_clean(checks: Sequence[ContractCheck]) -> bool:
    """An EXIT reads ``exited`` only when the strategy holds 0 on every contract AND Zerodha agrees: no mismatch and
    no units left beyond the other strategies (Zerodha still holding them is not an exit)."""
    return all(c.platform_units == 0 and c.kind is None and c.unexplained == 0 for c in checks)


def pnl_or_none(fills: Sequence[FillEvent]):
    """ADR-102 through the one engine: the fills' realised P&L when they leave every contract flat, else None."""
    try:
        return realised_pnl(fills)
    except ValueError:
        return None


__all__ = ["EXITED", "FILLED", "NOTHING_PLACED", "PARTIAL", "PARTIAL_CHOICES", "RECONCILE", "WAITING",
           "ContractCheck", "PlanAnswer", "TodaysBook", "classify", "drifted", "exit_is_clean", "pnl_or_none",
           "read_book", "reconcile"]
