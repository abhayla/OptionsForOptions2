"""GC-UI S5-1 / B1: the composition point of the Strategy Chart's candle read (REQ-091, ADR-012, ADR-029).

The feature module (``ofo_app.strategy_price_history``) and its route never reach the vendor: they receive only an
opener, ``(db) -> (listed contracts -> minute-candle fetch) | None``. This module is the one place that picks the
broker adapter's opener (V1: the one Zerodha adapter, ADR-002), like ``outcome_margin.py`` wires the margin client.
"""
from __future__ import annotations

from typing import Any


def history_opener() -> Any:
    """The production opener: reads the owner's stored session first on the request connection (S5-1)."""
    from ofo_app.kite_history import owner_minute_reader  # noqa: PLC0415 - a vendor door loads only on use
    return owner_minute_reader
