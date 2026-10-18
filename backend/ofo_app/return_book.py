"""W-096: today's Kite orders and trades -> THIS strategy's book (``execution_return.TodaysBook``).

The one place the return reads Kite's reply rows (through the ``kite_replies`` adapter), so the matching and
classifying logic in ``execution_return`` stays free of any Kite module (REQ-063 AC-1).
Spec basis: REQ-073 AC-3; ADR-050 item 4(d) (external orders recorded, never dropped).

- ``parse_tag`` decodes a row's tag exactly to the strategy id. A tag in a stored plan is ours; a tag for this strategy
  in no stored plan is EXTERNAL (kept as read, never dropped), read as strictly as ours (fail closed).
- Trades are taken for our orders only and de-duplicated by (order id, trade id): the same key twice with other
  content is a conflict (that order cannot be trusted), never a second fill.
- A trade whose order id is in no order row refuses the read (issue 381); the route reads trades first so a real
  Zerodha reply never shows this.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ofo.execution.basket import parse_tag
from ofo.orders.model import FillEvent

from ofo_app.execution_return import TodaysBook
from ofo_app.kite_replies import BrokerOrderRow, fill_from_trade_row, order_from_row


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


def _fills(trade_rows: Sequence[Mapping[str, object]],
           order_ids: frozenset[str]) -> tuple[tuple[FillEvent, ...], dict[str, int], frozenset[str]]:
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


def _require_trade_orders(order_rows: Sequence[Mapping[str, object]], trade_rows: Sequence[Mapping[str, object]]) -> None:
    """Issue 381: a trade whose order is in no order row (any strategy, any tag) means the two reads disagree. Dropping
    it would let a plan close ``nothing_placed`` while Zerodha shows its fill, so the whole read is refused."""
    known = {row.get("order_id") for row in order_rows if isinstance(row, Mapping)}
    for row in trade_rows:
        if isinstance(row, Mapping) and row.get("order_id") not in known:
            raise ValueError("a trade names an order the orders read does not hold")


def read_book(order_rows: Sequence[Mapping[str, object]], trade_rows: Sequence[Mapping[str, object]],
              strategy_id: int, stored_tags: frozenset[str]) -> TodaysBook:
    _require_trade_orders(order_rows, trade_rows)
    ours, external = _split_orders(order_rows, strategy_id, stored_tags)
    order_ids = frozenset(r.order_id for rows in ours.values() for r in rows)
    fills, traded, conflicting = _fills(trade_rows, order_ids)
    return TodaysBook(ours, tuple(external), traded, fills, conflicting)


__all__ = ["read_book"]
