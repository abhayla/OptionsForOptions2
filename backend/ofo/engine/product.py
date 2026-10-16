"""Order product (W-078, ADR-080): a closed value. Every entry and adjustment order is NRML (carry forward); MIS
exists only as a value read from a Zerodha position, so an exit can carry the product of the position it reduces."""
from __future__ import annotations

from enum import Enum


class Product(Enum):
    NRML = "NRML"
    MIS = "MIS"  # only ever read from a Zerodha position; never chosen for a new order
