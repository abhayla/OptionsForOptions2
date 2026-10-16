"""A broker position line and the parser of one Kite position row (neutral: no order-sending dependency).

Moved out of ``ofo.execution.partial`` (W-083 round 3) so that position reading and grouping do not import the
order-sending path (tests/execution/test_strategy_only.py allows only partial.py and send_guard.py to do that);
``partial`` re-imports both names, so every existing caller and test is unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ofo.engine.legs import require_price
from ofo.engine.product import Product


def _ident(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty string without surrounding whitespace, got {value!r}")
    return value


def _int(value: object, name: str, *, signed: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or (not signed and value < 0):
        raise ValueError(f"{name} must be {'an' if signed else 'a non-negative'} integer, got {value!r}")
    return value


@dataclass(frozen=True)
class BrokerPositionLine:
    """One broker position line attributed to the strategy: signed net units (long +, short -)."""

    contract: str
    net_quantity: int
    average_price: Decimal
    ltp: Decimal | None = None
    product: Product | None = None  # as Zerodha reports it; None = not read (an exit of it then BLOCKS)

    def __post_init__(self) -> None:
        _ident(self.contract, "contract")
        if self.product is not None and not isinstance(self.product, Product):
            raise ValueError(f"product must be a Product or None, got {self.product!r}")
        _int(self.net_quantity, "net_quantity", signed=True)
        require_price(self.average_price, "average_price", allow_zero=False)
        if self.ltp is not None:
            require_price(self.ltp, "ltp")


def is_flat_row(row: Mapping[str, object]) -> bool:
    """The ONE flat-row rule (W-091, F-40 gap b): a Kite position row whose ``quantity`` is 0 is "no position".

    Zerodha keeps a closed contract's row for the day with ``quantity 0`` and ``average_price 0`` (real reply
    2026-10-16 15:10:06). It is never a 0-price holding: every reader (grouping's suggestions and the reconcile
    path's broker net map) drops it BEFORE parsing. A boolean ``quantity`` is not 0 here (it is refused later)."""
    quantity = row.get("quantity") if isinstance(row, Mapping) else None
    return quantity == 0 and not isinstance(quantity, bool)


def _kite_price(value: object, name: str) -> Decimal:
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if not isinstance(value, Decimal):
        raise ValueError(f"{name} must be a Decimal or int (floats are refused), got {value!r}")
    return value


def position_line_from_kite_row(row: Mapping[str, object]) -> BrokerPositionLine:
    if not isinstance(row, Mapping):
        raise ValueError(f"a position row must be a mapping, got {row!r}")
    raw_product = row.get("product")
    product = next((p for p in Product if p.value == raw_product), None) if isinstance(raw_product, str) else None
    last = row.get("last_price")
    quantity = row.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValueError(f"quantity must be a whole number, got {quantity!r}")
    contract = row.get("tradingsymbol")
    if not isinstance(contract, str):
        raise ValueError(f"tradingsymbol must be a string, got {contract!r}")
    return BrokerPositionLine(contract, quantity, _kite_price(row.get("average_price"), "average_price"),
                              None if last is None else _kite_price(last, "last_price"), product)
