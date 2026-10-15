"""Charges (W-074, ADR-082 part 1): Zerodha's published F&O options rates and the calculator that applies them.

Standard library only (domain layer). Every amount is an exact ``Decimal``; STT and stamp duty are not rounded at order
level (ADR-082). The rates are data (``ChargeRates``, stored as dated admin settings by the app layer), never defaults.
"""

from ofo.charges.calculator import (
    ChargeOrder,
    OrderCharges,
    StrategyCharges,
    charges_for_order,
    charges_for_orders,
    exercise_stt,
)
from ofo.charges.rates import SEGMENTS, ChargeRates

__all__ = [
    "SEGMENTS",
    "ChargeOrder",
    "ChargeRates",
    "OrderCharges",
    "StrategyCharges",
    "charges_for_order",
    "charges_for_orders",
    "exercise_stt",
]
