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

from ofo.instruments.models import ZERODHA
from ofo.timeutil import IST
from sqlalchemy import text

from ofo_app.pinned_clock import pinned_today
from ofo_app.sql_time import IST_SQL_ZONE

CONTRACTS = "public.catalogue_contracts"
BROKER_ROWS = "public.broker_instruments"

_TODAY = text(f"SELECT (now() {IST_SQL_ZONE})::date")
#: The latest load's time: the newest moment a load saw a live Zerodha row (the database stamps last_seen_at).
LOADED_AT = text(f"SELECT max(last_seen_at) FROM {BROKER_ROWS} WHERE broker = :broker AND NOT retired")  # noqa: S608 constant table name


_NOW = text("SELECT clock_timestamp()")
_PUBLISH_TIME = datetime.time(8, 0)  # Zerodha's list for a session is published by 08:00 IST (this product's own rule)
_SATURDAY = 5  # datetime.weekday(): Monday is 0


async def database_now(conn: Any) -> datetime.datetime:
    """The database's own clock (``clock_timestamp()``, ADR-023): the clock that stamps grants and list loads."""
    return (await conn.execute(_NOW)).scalar_one()


def session_start(now: datetime.datetime) -> datetime.datetime:
    """08:00 IST of the most recent trading-session day at ``now``: today when today is a weekday and the time is at or
    past 08:00, otherwise the previous weekday. There is no exchange holiday calendar in this project yet, so a weekday
    holiday counts as a session day (the list is then the same as the previous one, which is harmless)."""
    local = now.astimezone(IST)
    day = local.date() if local.time() >= _PUBLISH_TIME else local.date() - datetime.timedelta(days=1)
    while day.weekday() >= _SATURDAY:
        day -= datetime.timedelta(days=1)
    return datetime.datetime.combine(day, _PUBLISH_TIME, tzinfo=IST)


def loaded_before(loaded_at: datetime.datetime | None, now: datetime.datetime) -> bool:
    """True when the list was never loaded or its latest load is before the current session's publish time (W-133,
    REQ-053 AC-3, finding daily-load-misses-intraday-additions): such a list is unconfirmed, never trusted. A list
    loaded Friday 09:00 is current on Saturday 11:00 and on Monday 07:30. ``now`` and ``loaded_at`` are database times."""
    return loaded_at is None or loaded_at < session_start(now)


_MID_SESSION = datetime.time(12, 0)


async def judging_instant(conn: Any, today: datetime.date) -> datetime.datetime:
    """The instant a staleness judgement is made: the database clock when ``today`` is its India date (always so in
    production, where ``today`` is ``database_today``); a date that is not (the TEST-ONLY pin, ``pinned_clock``, or a
    caller's explicit date) carries no time of day, so it is judged at mid-session of that date."""
    now = await database_now(conn)
    if now.astimezone(IST).date() == today:
        return now
    return datetime.datetime.combine(today, _MID_SESSION, tzinfo=IST)


async def list_is_current(conn: Any, today: datetime.date) -> bool:
    """Whether the latest successful load is at or after the current session's publish time (database clock)."""
    loaded_at = (await conn.execute(LOADED_AT, {"broker": ZERODHA})).scalar_one()
    return not loaded_before(loaded_at, await judging_instant(conn, today))


_PICKABLE = (
    f"FROM {CONTRACTS} AS c JOIN {BROKER_ROWS} AS b ON b.contract_id = c.id AND b.broker = :broker "
    f"WHERE c.name = :underlying AND NOT c.retired AND NOT c.delisted AND c.currently_listed "
    f"AND c.expiry IS NOT NULL AND c.expiry >= :today"
)
_EXPIRIES = text(f"SELECT DISTINCT c.expiry {_PICKABLE} ORDER BY c.expiry")
_CONTRACTS = text(
    f"SELECT c.id AS contract_id, c.exchange_segment, c.exchange_token, c.instrument_type, c.expiry, c.strike, b.lot_size, b.broker_symbol "
    f"{_PICKABLE} AND (CAST(:expiry AS DATE) IS NULL OR c.expiry = CAST(:expiry AS DATE)) "
    f"ORDER BY c.expiry, c.strike, c.instrument_type, c.exchange_token"
)


@dataclass(frozen=True)
class PickableContract:
    contract_id: int  # the catalogue's internal id (ADR-057: what a saved strategy leg links to)
    instrument_id: str  # "<exchange_segment>:<exchange_token>", the id the outcome route takes
    exchange_segment: str
    exchange_token: int
    instrument_type: str  # CE / PE / FUT
    expiry: datetime.date
    strike: Decimal | None  # None for a future
    lot_size: int
    symbol: str  # Zerodha's trading symbol


async def database_today(conn: Any) -> datetime.date:
    """Today's date in India on the DATABASE clock (the one clock every expiry judgement uses). The single exception is the
    TEST-ONLY pin (``TEST_CATALOGUE_DATE`` under APP_ENV=test, ofo_app.pinned_clock, issue #237)."""
    pinned = pinned_today()
    if pinned is not None:
        return pinned
    return (await conn.execute(_TODAY)).scalar_one()


async def pickable_expiries(conn: Any, underlying: str, today: datetime.date) -> list[datetime.date]:
    """Expiry dates (ascending) that hold at least one pickable contract of ``underlying``; none from a list that was
    not loaded today (unconfirmed)."""
    if not await list_is_current(conn, today):
        return []
    rows = await conn.execute(_EXPIRIES, {"broker": ZERODHA, "underlying": underlying, "today": today})
    return [r.expiry for r in rows.all()]


async def pickable_contracts(conn: Any, underlying: str, today: datetime.date,
                             expiry: datetime.date | None = None) -> list[PickableContract]:
    """Pickable contracts of ``underlying`` ordered by expiry, strike, type; one expiry when ``expiry`` is given
    (a past or unknown expiry gives an empty list); none from a list that was not loaded today (unconfirmed)."""
    if not await list_is_current(conn, today):
        return []
    rows = await conn.execute(_CONTRACTS, {"broker": ZERODHA, "underlying": underlying, "today": today,
                                           "expiry": expiry})
    out = []
    for r in rows.all():
        is_future = r.instrument_type == "FUT"
        out.append(PickableContract(
            contract_id=int(r.contract_id), instrument_id=f"{r.exchange_segment}:{r.exchange_token}", exchange_segment=r.exchange_segment,
            exchange_token=int(r.exchange_token), instrument_type=r.instrument_type, expiry=r.expiry,
            strike=None if is_future else r.strike, lot_size=int(r.lot_size), symbol=r.broker_symbol))
    return out
