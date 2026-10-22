"""The one Zerodha implementation of ``BrokerReader`` (W-131, REQ-054 AC-1 and AC-2; Zerodha is the authority, ADR-016).

It is glue and nothing else: every call goes through the existing doors (``KiteReads`` and ``KiteMargin``, both behind
``check_call``), and every reply is turned into a domain value by the existing converters in ``ofo_app.kite_replies``
and ``ofo_app.checked_basket``. No header, host, JSON parse or HTTP-error helper is repeated here. There is no retry:
a failed read raises the door's error (``KiteReadError`` / ``KiteMarginError`` / ``KiteReplyError``) and the caller
treats it as "could not re-read" (the ``BrokerReader`` contract). No call here can place, change or cancel an order.

Only Zerodha is implemented (REQ-054 AC-2); ``tests/test_one_broker_only.py`` keeps it that way.
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from decimal import Decimal

from ofo.execution.basket import parse_tag
from ofo.execution.partial import BrokerOrderStatus
from ofo.instruments.catalogue import Catalogue
from ofo.orders import Order
from ofo.reconciliation.positions import BrokerPositionLine
from ofo.timeutil import IST

from ofo_app.checked_basket import zerodha_required_margin
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import AccountProfile, KiteReadError, KiteReads
from ofo_app.kite_replies import ContractIndex, order_status_from_row, positions_from_reply


def _ist_now() -> datetime.datetime:
    return datetime.datetime.now(IST)


class KiteBrokerReader:
    """``BrokerReader`` over the owner's own Kite connection. Fresh read on every call; nothing is cached."""

    def __init__(self, reads: KiteReads, margin: KiteMargin, catalogue: Catalogue,
                 now: Callable[[], datetime.datetime] = _ist_now) -> None:
        if type(reads) is not KiteReads or type(margin) is not KiteMargin:
            raise TypeError("KiteBrokerReader needs the KiteReads and KiteMargin doors, nothing else")
        self._reads, self._margin, self._catalogue, self._now = reads, margin, catalogue, now

    def __repr__(self) -> str:
        return "KiteBrokerReader()"

    def _read_at(self) -> datetime.datetime:
        stamp = self._now()
        if stamp.utcoffset() is None:
            raise ValueError("the read time must be timezone-aware")
        return stamp

    def fetch_account(self) -> AccountProfile:
        """REQ-054 AC-1 "fetch account": the five kept profile keys (no name, email or avatar)."""
        return self._reads.fetch_profile()

    def fetch_positions(self, strategy_id: str) -> tuple[Sequence[BrokerPositionLine], datetime.datetime]:
        """The platform's net position lines (Kite does not tag positions by strategy: the caller groups them) and
        the time of the read. Rows the platform can never own are skipped by ``positions_from_reply``."""
        read = positions_from_reply(self._reads.fetch_positions(), ContractIndex.from_catalogue(self._catalogue))
        return read.lines, self._read_at()

    def fetch_order_statuses(self, strategy_id: str) -> tuple[Sequence[BrokerOrderStatus], datetime.datetime]:
        """Every order of today carrying this strategy's tag (ONE ``GET /orders``), each as the broker's status.

        An order with no tag, or a tag that is not ours, is another system's and is left out. A tagged row whose
        status cannot be read raises (``KiteReplyError``): a status is never guessed."""
        wanted = _strategy_number(strategy_id)
        found = []
        for row in self._reads.fetch_orders():
            tag = row.get("tag")  # type: ignore[attr-defined]  # fetch_orders returned only objects
            if not isinstance(tag, str) or _tag_strategy(tag) != wanted:
                continue
            found.append(order_status_from_row(row))  # type: ignore[arg-type]
        return tuple(found), self._read_at()

    def fetch_order_status_by_id(self, order_ids: Sequence[str]) -> dict[str, BrokerOrderStatus | None]:
        """Each asked broker order id -> its status, or ``None`` (explicit not-found) when Zerodha's one orders list
        has no such id. REQ-054 AC-1 "fetch order status"."""
        rows = self._reads.fetch_order_statuses(order_ids)
        return {i: None if row is None else order_status_from_row(row) for i, row in rows.items()}

    def fetch_available_margin(self) -> Decimal:
        return self._margin.fetch_available_funds()

    def fetch_required_margin(self, orders: Sequence[Order]) -> Decimal:
        return zerodha_required_margin(self._margin, self._catalogue, orders)


def _strategy_number(strategy_id: object) -> int:
    if not isinstance(strategy_id, str) or not strategy_id.isascii() or not strategy_id.isdigit():
        raise KiteReadError("kite_read_refused")  # a strategy id that cannot be a tag's number matches nothing
    return int(strategy_id)


def _tag_strategy(tag: str) -> int | None:
    try:
        return parse_tag(tag).strategy_id
    except ValueError:
        return None


__all__ = ["KiteBrokerReader"]
