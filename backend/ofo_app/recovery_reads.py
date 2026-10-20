"""#380-3 item 1: Zerodha's two raw reads -> the recovery domain's ``ZerodhaRead`` (ofo/execution/recovery.py).

The route reads the order book (``fetch_orders``) and the positions (``fetch_positions``, parsed by the ONE
reconciler, ``route_reconciliation.reconcile_account``), then stamps ``read_at`` with the route clock read AFTER both
replies came back, never the request-start clock (finding freshness-judged-on-request-start-clock).

Answer states (standing item (d)) and what each does here:
- stated: every order row parses -> ``orders``; position lines -> ``net`` per Zerodha tradingsymbol.
- empty: ``[]`` orders / no position lines -> ``()`` / ``{}`` (stated "nothing"; the domain reads it as flat).
- failed: the order reply is not a list, or any row does not parse -> ``orders`` None (every action
  ``READ_FAILED``);
  positions unread (``None``) -> ``net`` None (every close refused ``READ_FAILED``).
- ambiguous: two position lines for one contract are summed (Zerodha's own net of day and overnight rows), never
  picked between; the domain refuses a tag seen twice.
"""
from __future__ import annotations

import datetime
from collections.abc import Sequence

from ofo.engine import Action
from ofo.execution.recovery import ZerodhaOrder, ZerodhaRead

from ofo_app.kite_replies import KiteReplyError, PositionsRead, orders_from_reply


def _orders(rows: object) -> tuple[ZerodhaOrder, ...] | None:
    try:
        parsed = orders_from_reply(rows)
        return tuple(ZerodhaOrder(o.tradingsymbol, Action(o.side), o.status, o.quantity, o.filled_quantity, o.tag)
                     for o in parsed)
    except (KiteReplyError, ValueError):
        return None  # one unreadable row makes the whole book unread: never decide on part of it


def _net(positions: PositionsRead | None) -> dict[str, int] | None:
    if positions is None:
        return None
    net: dict[str, int] = {}
    for line in positions.lines:
        net[line.contract] = net.get(line.contract, 0) + line.net_quantity
    return {c: units for c, units in net.items() if units != 0}


def zerodha_read(order_rows: Sequence[object] | object, positions: PositionsRead | None,
                 read_at: datetime.datetime) -> ZerodhaRead:
    """The domain's view of Zerodha's two replies, stamped with the clock read after them (timezone-aware)."""
    if read_at.utcoffset() is None:
        raise ValueError("read_at must be timezone-aware")
    return ZerodhaRead(_orders(order_rows), _net(positions), read_at)


__all__ = ["zerodha_read"]
