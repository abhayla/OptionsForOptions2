"""The stored exchange freeze limit in force, read side (W-076, REQ-054 AC-4, ADR-081, REQ-076 AC-5).

Split out of ``freeze_store`` so the leg-edit route can read the limits without its import closure reaching any
``ofo.execution`` module (the order path's plan-side join stays in ``freeze_store``). Imports nothing from the order
path: ``tests_app/test_order_path_switch.py`` walks the closure and fails if that ever changes.
"""

from __future__ import annotations

from datetime import date
from typing import Any, NamedTuple

from ofo.instruments.models import InstrumentId
from sqlalchemy import text

_IN_FORCE = text(
    "SELECT DISTINCT ON (exchange_segment, exchange_token) exchange_segment, exchange_token, file_date, freeze_limit "
    "FROM public.exchange_freeze_limits ORDER BY exchange_segment, exchange_token, file_date DESC")


class StoredLimit(NamedTuple):
    freeze_limit: int
    file_date: date


async def limits_in_force(conn: Any) -> dict[InstrumentId, StoredLimit]:
    """The limit with the newest file date for every stored contract."""
    rows = (await conn.execute(_IN_FORCE)).all()
    return {InstrumentId(r.exchange_segment, r.exchange_token): StoredLimit(r.freeze_limit, r.file_date) for r in rows}
