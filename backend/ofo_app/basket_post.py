"""W-095: the one closed response value that carries a Kite basket to the browser (REQ-073 AC-1, AC-2).

Spec basis: REQ-073 AC-1 ("one Kite basket of LIMIT orders marked read-only, in the plan's order; the user cannot
change a price, quantity or contract on Kite's page"); AC-2 (every order carries our own tag).

The browser must POST exactly ``KiteBasket.form_fields(api_key)`` to ``KITE_BASKET_URL``: a client that rebuilt the
JSON could drop ``readonly`` or a tag. So the response carries the exact ``data`` string, and the API door
(``api_models``) writes it only from this type, which:
- is made only by ``BasketPost.of(basket, api_key)`` from a real ``KiteBasket`` (``type(basket) is KiteBasket``; the
  constructor refuses any other caller);
- re-parses its own ``data`` and refuses unless it is exactly the basket's orders, each LIMIT and ``readonly`` true,
  each tag the basket's own tag, so a text that would let Kite's page edit an order can never be emitted.
Its URL is the module constant, never a value passed in.
"""
from __future__ import annotations

import json
from decimal import Decimal

from ofo.execution.basket import KITE_BASKET_URL, KiteBasket

_TOKEN = object()
_FIELDS = ("variety", "tradingsymbol", "exchange", "transaction_type", "order_type", "product", "price", "quantity",
           "readonly", "tag")


class BasketPostRefused(ValueError):
    """The basket's form text does not parse back to its own read-only orders (never emitted)."""


def _expected(basket: KiteBasket) -> list[dict[str, object]]:
    return [{"variety": o.variety, "tradingsymbol": o.tradingsymbol, "exchange": o.exchange,
             "transaction_type": o.transaction_type, "order_type": "LIMIT", "product": o.product,
             "price": o.price, "quantity": o.quantity, "readonly": True, "tag": o.tag} for o in basket.orders]


def _check(data: str, basket: KiteBasket) -> None:
    try:
        parsed = json.loads(data, parse_float=Decimal)
    except ValueError as exc:
        raise BasketPostRefused("the basket text is not JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(o, dict) and tuple(o) == _FIELDS for o in parsed):
        raise BasketPostRefused("the basket text is not a list of Kite orders with exactly the basket fields")
    if any(o["readonly"] is not True or o["order_type"] != "LIMIT" for o in parsed):
        raise BasketPostRefused("every order must be a read-only LIMIT order")
    if [{**o, "price": Decimal(o["price"])} for o in parsed] != _expected(basket):
        raise BasketPostRefused("the basket text does not equal the basket's own orders")


class BasketPost:
    """``{"url", "api_key", "data"}`` for the browser's form POST; built only by ``of``."""

    __slots__ = ("api_key", "data", "tags")

    def __init__(self, api_key: str, data: str, tags: tuple[str, ...], *, _token: object = None) -> None:
        if _token is not _TOKEN:
            raise TypeError("a BasketPost is made only by BasketPost.of(basket, api_key)")
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "tags", tags)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a BasketPost is read-only")

    @classmethod
    def of(cls, basket: KiteBasket, api_key: str) -> BasketPost:
        if type(basket) is not KiteBasket:
            raise TypeError(f"a BasketPost is made from a KiteBasket, got {type(basket).__name__}")
        fields = basket.form_fields(api_key)
        _check(fields["data"], basket)
        return cls(fields["api_key"], fields["data"], tuple(o.tag for o in basket.orders), _token=_TOKEN)

    @classmethod
    def __get_pydantic_core_schema__(cls, source: object, handler: object) -> object:
        """Validation accepts only an existing BasketPost (no text is ever parsed into one); the documented shape is
        the three form strings the door writes."""
        from pydantic_core import core_schema  # noqa: PLC0415

        text_field = core_schema.typed_dict_field(core_schema.str_schema())
        return core_schema.json_or_python_schema(
            json_schema=core_schema.typed_dict_schema({"url": text_field, "api_key": text_field, "data": text_field}),
            python_schema=core_schema.is_instance_schema(cls),
            serialization=core_schema.plain_serializer_function_ser_schema(lambda v: v.as_form()))

    def as_form(self) -> dict[str, str]:
        """What the door writes: the fixed URL and exactly the two hidden fields."""
        return {"url": KITE_BASKET_URL, "api_key": self.api_key, "data": self.data}


__all__ = ["BasketPost", "BasketPostRefused"]
