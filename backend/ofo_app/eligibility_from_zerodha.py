"""Eligibility filled from Zerodha's own data, read from the catalogue store (W-092; ADR-104; REQ-053 AC-1..AC-4).

Spec basis: REQ-053 AC-3 ("Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are
currently unavailable; the check repeats just before execution."); AC-2 (catalogue stored apart from eligibility);
AC-4 (no platform RMS rule); ADR-104 (what "Zerodha data" means: the current instrument list as the product's own load
left it, the expiry date on the database clock, and the basket-margin reply's per-leg refusals).

Read-only: every query here is a SELECT; nothing writes the catalogue or stores eligibility. "Today" is the DATABASE
clock's India date (``catalogue_picker.database_today``, which honours only the test-only pin), never the app clock.

- ``leg_statuses(conn, contract_ids, today)``: the add-time check (Save Draft / edit), one status per leg by the
  catalogue's internal contract id; ``None`` when the catalogue has never been loaded (fail closed: refused).
- ``fresh_registry(conn, ...)``: the just-before-execution check. It builds a NEW registry from the store at that
  moment, optionally narrowed by the basket-margin reply's refusals. Its caller is the GC-2c Execute route, which
  passes the result straight to ``ofo.execution.safety.check_pre_execution``. It takes no registry and no status
  from its caller: a refusal can only make a contract NOT tradable (finding caller-supplied-verdict-trusted).

Known limit (ADR-104, finding daily-load-misses-intraday-additions / F-33): a contract Zerodha lists during the day,
after the latest load, is not eligible until a later load lists it. An intraday refresh is a follow-up.

Copy from: none - the eligibility registry and the picker are this project's own; no algochanakya row covers
eligibility.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from ofo.instruments.eligibility import (
    EligibilityRegistry,
    EligibilityStatus,
    ListState,
    registry_from_list,
    status_from_list,
)
from ofo.instruments.models import ZERODHA, InstrumentId
from sqlalchemy import text

from ofo_app.catalogue_picker import BROKER_ROWS, CONTRACTS, database_today

_STATE_COLUMNS = (
    "SELECT c.id, c.exchange_segment, c.exchange_token, c.instrument_type, c.expiry, c.currently_listed, c.retired, "  # noqa: S608 constant table name
    "c.delisted, (b.contract_id IS NOT NULL AND NOT b.retired) AS has_zerodha_row "
    f"FROM {CONTRACTS} AS c LEFT JOIN {BROKER_ROWS} AS b ON b.contract_id = c.id AND b.broker = :broker"
)
_BY_IDS = text(_STATE_COLUMNS + " WHERE c.id = ANY(CAST(:ids AS BIGINT[]))")
_LIVE = text(_STATE_COLUMNS + " WHERE NOT c.retired AND NOT c.delisted "
                              "AND (CAST(:underlying AS TEXT) IS NULL OR c.name = CAST(:underlying AS TEXT))")
#: The latest load's time: the newest moment the load saw a live Zerodha row (the database stamps last_seen_at).
_LOADED_AT = text(f"SELECT max(last_seen_at) FROM {BROKER_ROWS} WHERE broker = :broker AND NOT retired")  # noqa: S608 constant table name
_NOW = text("SELECT clock_timestamp()")


def _state(row: Any) -> ListState:
    return ListState(
        instrument_id=InstrumentId(row.exchange_segment, int(row.exchange_token)),
        instrument_type=row.instrument_type, expiry=row.expiry, listed=bool(row.currently_listed),
        retired=bool(row.retired), delisted=bool(row.delisted), has_zerodha_row=bool(row.has_zerodha_row))


async def _loaded_at(conn: Any) -> datetime.datetime | None:
    return (await conn.execute(_LOADED_AT, {"broker": ZERODHA})).scalar_one()


async def leg_statuses(conn: Any, contract_ids: Sequence[int],
                       today: datetime.date) -> list[EligibilityStatus | None]:
    """ADR-104 (a) for each leg, in order. ``None`` for a leg whose contract has no row or when no load ever ran (the
    caller refuses it as unconfirmed). Keyed by internal id, so a retired contract never shadows a live one that
    reuses its token."""
    loaded_at = await _loaded_at(conn)
    wanted = sorted(set(contract_ids))
    if loaded_at is None or not wanted:
        return [None] * len(contract_ids)
    rows = (await conn.execute(_BY_IDS, {"broker": ZERODHA, "ids": wanted})).all()
    by_id = {int(r.id): status_from_list(_state(r), today=today, loaded_at=loaded_at) for r in rows}
    return [by_id.get(contract_id) for contract_id in contract_ids]


async def fresh_registry(conn: Any, *, underlying: str | None = None,
                         margin_refusals: Mapping[InstrumentId, str] | None = None) -> EligibilityRegistry:
    """The just-before-execution registry (ADR-104 (a) + (b)), built NOW from the store. Caller: the GC-2c Execute
    route, straight into ``check_pre_execution``. ``margin_refusals`` = instrument -> Zerodha's error text for each
    leg the basket-margin reply refused; stamped with the database clock. Every live contract gets a status; with no
    load ever, the registry is empty and the gate refuses every leg as unconfirmed."""
    today = await database_today(conn)
    loaded_at = await _loaded_at(conn)
    if loaded_at is None:
        return EligibilityRegistry()
    rows = (await conn.execute(_LIVE, {"broker": ZERODHA, "underlying": underlying})).all()
    refused_at = (await conn.execute(_NOW)).scalar_one() if margin_refusals else None
    return registry_from_list((_state(r) for r in rows), today=today, loaded_at=loaded_at,
                              refusals=margin_refusals, refused_at=refused_at)


TodayReader = Callable[[Any], Awaitable[datetime.date]]


def get_eligibility_today() -> TodayReader:
    """The route's clock seam (a FastAPI dependency that returns the reader, so no query runs before the body is
    checked): the database clock's India date. Tests override it with a fixed date for recorded catalogue rows."""
    return database_today
