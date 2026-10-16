"""The ONE production path to a Kite basket: Zerodha's margin decides (W-081 wired into W-080; REQ-055 AC-1/AC-3/AC-4).

`checked_basket` is the only backend code outside ``ofo/execution/basket.py`` that names ``build_basket``
(``tests/test_margin_from_zerodha_only.py`` fails on any other). Its margin check is never a parameter: it is built
here from the caller's `KiteMargin` client, turns the resolved basket orders into Zerodha's basket-margin orders, and
returns ``kite_margin.margin_verdict`` (funds ``equity.net`` vs the basket reply's ``final.total`` plus the ADR-094
top-up, a negative total counted as 0). No platform estimate takes part (AC-3, REQ-053 AC-4). Zerodha unreadable, a
shortfall of one paisa, or an order the margin call cannot express refuses the whole basket with `BasketRefused`; a
shortfall carries Zerodha's available vs required (AC-4).

`zerodha_required_margin` is the same figure for the partial-fill re-check (``BrokerReader.fetch_required_margin``,
#273): the missing orders are resolved through the catalogue's ZERODHA rows, and any failure raises (fail closed).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from ofo.execution.basket import KiteBasket, KiteOrder, MarginVerdict, build_basket, zerodha_exchange
from ofo.execution.freeze import FreezeCheck
from ofo.execution.planned import ExecutionPlan
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA, MissingBrokerRef
from ofo.orders import Order

from ofo_app.kite_margin import BasketOrder, KiteMargin, margin_verdict


def basket_orders(orders: Sequence[KiteOrder]) -> list[BasketOrder]:
    """The resolved basket orders as Zerodha's basket-margin call takes them (same exchange, symbol, side, product,
    order type, quantity and limit price as the orders the user will see). Raises ValueError on a shape it cannot
    send."""
    return [BasketOrder(o.exchange, o.tradingsymbol, o.transaction_type, o.product, o.order_type, o.quantity, o.price,
                        o.variety) for o in orders]


def _zerodha_margin_check(client: KiteMargin) -> Callable[[tuple[KiteOrder, ...]], MarginVerdict]:
    if type(client) is not KiteMargin:
        raise TypeError("checked_basket needs a KiteMargin client (Zerodha's figures), got "
                        f"{type(client).__name__}")

    def check(orders: tuple[KiteOrder, ...]) -> MarginVerdict:
        return margin_verdict(client, basket_orders(orders))

    return check


def checked_basket(plan: ExecutionPlan, catalogue: Catalogue, plan_version: int, *, margin_client: KiteMargin,
                   freeze_check: Callable[[ExecutionPlan], FreezeCheck]) -> KiteBasket:
    """Build the read-only Kite basket for ``plan`` only if Zerodha says the funds cover the margin these exact orders
    need; otherwise raise `BasketRefused` (its ``user_message`` shows available vs required)."""
    return build_basket(plan, catalogue, plan_version, freeze_check=freeze_check,
                        margin_check=_zerodha_margin_check(margin_client))


def zerodha_required_margin(client: KiteMargin, catalogue: Catalogue, orders: Sequence[Order]) -> Decimal:
    """Zerodha's required margin (``required_total``, rounded to the paisa where parsed, ADR-101) for exactly
    ``orders``. A contract without one listed ZERODHA row, an unsendable order or an unreadable reply raises."""
    if type(client) is not KiteMargin:
        raise TypeError(f"zerodha_required_margin needs a KiteMargin client, got {type(client).__name__}")
    wanted = []
    for order in orders:
        entries = catalogue.entries_for_broker_symbol(ZERODHA, order.contract)
        if len(entries) != 1:
            raise MissingBrokerRef(detail=f"{order.contract!r} matches {len(entries)} catalogue rows at {ZERODHA}")
        entry = catalogue.get(entries[0].id)
        wanted.append(BasketOrder(zerodha_exchange(entry.id.exchange_segment), entry.ref(ZERODHA).broker_symbol,
                                  order.side.value, order.product.value, "LIMIT", order.quantity, order.price))
    return client.fetch_basket_margin(wanted).required_total


__all__ = ["basket_orders", "checked_basket", "zerodha_required_margin"]
