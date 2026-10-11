"""Read-only catalogue queries for the Builder's leg picker (W-068; REQ-035 AC-8, ADR-068 item 4).

Spec basis: REQ-035 AC-8 ("The Builder adds and edits legs from a picker that offers only listed, not-expired contracts
of the chosen underlying"); ADR-068 item 4; ADR-057/058 (live = neither retired nor delisted); REQ-053 AC-2 (the
catalogue is stored apart from eligibility, so Zerodha's own per-user check is not made here - that comes with orders).

A contract is offered only if it is live (NOT retired AND NOT delisted), currently listed, has an expiry on or after
``today`` and belongs to the asked underlying. ``today`` is a parameter: the route passes the DATABASE clock's date in
Asia/Kolkata (``database_today``), never the application's clock. Nothing here writes.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from ofo.instruments.models import ZERODHA

CONTRACTS = "public.catalogue_contracts"
BROKER_ROWS = "public.broker_instruments"

_TODAY = text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date")

_PICKABLE = (
    f"FROM {CONTRACTS} AS c JOIN {BROKER_ROWS} AS b ON b.contract_id = c.id AND b.broker = :broker "
    f"WHERE c.name = :underlying AND NOT c.retired AND NOT c.delisted AND c.currently_listed "
    f"AND c.expiry IS NOT NULL AND c.expiry >= :today"
)
_EXPIRIES = text(f"SELECT DISTINCT c.expiry {_PICKABLE} ORDER BY c.expiry")
_CONTRACTS = text(
    f"SELECT c.exchange_segment, c.exchange_token, c.instrument_type, c.expiry, c.strike, b.lot_size, b.broker_symbol "
    f"{_PICKABLE} AND (CAST(:expiry AS DATE) IS NULL OR c.expiry = CAST(:expiry AS DATE)) "
    f"ORDER BY c.expiry, c.strike, c.instrument_type, c.exchange_token"
)


@dataclass(frozen=True)
class PickableContract:
    instrument_id: str  # "<exchange_segment>:<exchange_token>", the id the outcome route takes
    exchange_segment: str
    exchange_token: int
    instrument_type: str  # CE / PE / FUT
    expiry: datetime.date
    strike: Decimal | None  # None for a future
    lot_size: int
    symbol: str  # Zerodha's trading symbol


async def database_today(conn: Any) -> datetime.date:
    """Today's date in India on the DATABASE clock (the one clock every expiry judgement uses)."""
    return (await conn.execute(_TODAY)).scalar_one()


async def pickable_expiries(conn: Any, underlying: str, today: datetime.date) -> list[datetime.date]:
    """Expiry dates (ascending) that hold at least one pickable contract of ``underlying``."""
    rows = await conn.execute(_EXPIRIES, {"broker": ZERODHA, "underlying": underlying, "today": today})
    return [r.expiry for r in rows.all()]


async def pickable_contracts(conn: Any, underlying: str, today: datetime.date,
                             expiry: datetime.date | None = None) -> list[PickableContract]:
    """Pickable contracts of ``underlying`` ordered by expiry, strike, type; one expiry when ``expiry`` is given
    (a past or unknown expiry gives an empty list)."""
    rows = await conn.execute(_CONTRACTS, {"broker": ZERODHA, "underlying": underlying, "today": today,
                                           "expiry": expiry})
    out = []
    for r in rows.all():
        is_future = r.instrument_type == "FUT"
        out.append(PickableContract(
            instrument_id=f"{r.exchange_segment}:{r.exchange_token}", exchange_segment=r.exchange_segment,
            exchange_token=int(r.exchange_token), instrument_type=r.instrument_type, expiry=r.expiry,
            strike=None if is_future else r.strike, lot_size=int(r.lot_size), symbol=r.broker_symbol))
    return out
