"""W-068 (REQ-035 AC-8, ADR-068 items 1 and 4): the Builder's leg picker API over the PostgreSQL catalogue.

Spec basis: REQ-035 AC-8 "The Builder adds and edits legs from a picker that offers only listed, not-expired contracts
of the chosen underlying (underlying, expiry, strike, CE/PE/FUT, buy/sell, lots)"; ADR-068 item 1 (planned entry = the
leg's LTP when added, or the mid of bid and ask when no LTP exists); ADR-020 Q185 ("no fake prices"); ADR-003 Q226
(every message from the template catalogue).

Every database test runs in a transaction that is rolled back, so public.catalogue_contracts stays empty.
"""

from __future__ import annotations

import datetime
import io
from datetime import date, datetime as dt, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ofo_app.catalogue_picker import database_today, pickable_contracts, pickable_expiries
from ofo_app.catalogue_store import apply_update, parse_rows_naming_the_row

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / "tests" / "fixtures" / "instruments" / "instruments_slice.csv"
FIRST_LOAD = dt(2026, 9, 28, 10, 0, tzinfo=IST)  # fixed, never the wall clock
SECOND_LOAD = dt(2026, 9, 30, 10, 0, tzinfo=IST)  # retires NIFTY 2026-09-29; the list also drops one SENSEX contract
TODAY = date(2026, 10, 7)
TABLE = "public.catalogue_contracts"


def _slice():
    with SLICE.open(encoding="utf-8") as f:
        return list(parse_rows_naming_the_row(f))


async def _count(conn) -> int:
    return (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one()


async def _load_two_days(conn):
    """The slice loaded on 2026-09-28, then again on 2026-09-30 without one live SENSEX 2026-10-08 call (delisted).
    Returns the instrument id of the dropped contract."""
    rows = _slice()
    await apply_update(conn, rows, as_of=FIRST_LOAD)
    dropped = min((r for r in rows if r.contract.name == "SENSEX" and r.contract.expiry == date(2026, 10, 8)
                   and r.contract.instrument_type == "CE"), key=lambda r: r.contract.exchange_token)
    kept = [r for r in rows if r is not dropped]
    result = await apply_update(conn, kept, as_of=SECOND_LOAD)
    assert result.delisted == 1 and result.retired > 0
    return f"{dropped.contract.exchange_segment}:{dropped.contract.exchange_token}"


# ---------------------------------------------------------------------------------------------------------------
# Step 1: the store functions (deterministic slice, then the real list)
# ---------------------------------------------------------------------------------------------------------------


async def test_only_live_listed_unexpired_contracts_of_the_asked_underlying(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            dropped = await _load_two_days(conn)

            # not-expired is judged on the `today` argument: 2026-10-06 and 2026-10-01 rows are gone on 2026-10-07
            assert await pickable_expiries(conn, "NIFTY", TODAY) == [date(2026, 10, 27), date(2026, 11, 23)]
            assert await pickable_expiries(conn, "SENSEX", TODAY) == [
                date(2026, 10, 8), date(2026, 10, 15), date(2026, 10, 29), date(2026, 11, 26), date(2026, 12, 31)]
            assert await pickable_contracts(conn, "NIFTY", TODAY, date(2026, 10, 6)) == []  # past expiry: empty
            assert await pickable_contracts(conn, "NIFTY", TODAY, date(2031, 1, 1)) == []  # unknown expiry: empty

            sensex = await pickable_contracts(conn, "SENSEX", TODAY, date(2026, 10, 8))
            assert len(sensex) == 2 * 148 - 1
            assert {c.instrument_type for c in sensex} == {"CE", "PE"}
            assert all(c.expiry == date(2026, 10, 8) and c.exchange_segment == "BSE_FO" for c in sensex)
            assert [(c.strike, c.instrument_type) for c in sensex] == sorted((c.strike, c.instrument_type) for c in sensex)
            assert all(isinstance(c.strike, Decimal) and c.lot_size > 0 and c.symbol for c in sensex)
            assert all(c.instrument_id == f"{c.exchange_segment}:{c.exchange_token}" for c in sensex)

            # delisted: the dropped contract is absent although its expiry is ahead
            assert dropped not in {c.instrument_id for c in sensex}
            # retired: NIFTY 2026-09-29 expiry is on/after 2026-09-28 yet its contracts were retired on 2026-09-30
            assert date(2026, 9, 29) not in await pickable_expiries(conn, "NIFTY", date(2026, 9, 28))
            assert await pickable_contracts(conn, "NIFTY", date(2026, 9, 28), date(2026, 9, 29)) == []
            # not yet expired on the earlier day, still live: the 2026-10-01 SENSEX expiry is offered on 2026-09-28
            assert date(2026, 10, 1) in await pickable_expiries(conn, "SENSEX", date(2026, 9, 28))
            # a future has no strike
            futs = [c for c in await pickable_contracts(conn, "NIFTY", TODAY, date(2026, 10, 27))]
            assert [(c.instrument_type, c.strike) for c in futs] == [("FUT", None)]
            # only the asked underlying; out-of-scope names never appear
            everything = await pickable_contracts(conn, "SENSEX", date(2026, 9, 28))
            assert {c.exchange_segment for c in everything} == {"BSE_FO"}
            assert await pickable_expiries(conn, "SENSEX50", TODAY) == []
            assert await pickable_expiries(conn, "BANKEX", TODAY) == []
        finally:
            await trans.rollback()


@pytest.mark.network
async def test_real_list_gives_nifty_expiries_with_ce_and_pe_strikes(app_engine: AsyncEngine) -> None:
    from ofo.instruments.downloader import download_instruments_csv

    rows = parse_rows_naming_the_row(io.StringIO(download_instruments_csv()))
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _count(conn) == 0, "catalogue table must be empty (tests roll back)"
            as_of = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
            await apply_update(conn, rows, as_of=as_of)
            today = await database_today(conn)
            expiries = await pickable_expiries(conn, "NIFTY", today)
            assert expiries and all(e >= today for e in expiries)
            both = []
            for expiry in expiries:
                contracts = await pickable_contracts(conn, "NIFTY", today, expiry)
                ce = {c.strike for c in contracts if c.instrument_type == "CE"}
                pe = {c.strike for c in contracts if c.instrument_type == "PE"}
                if ce and pe:
                    both.append(expiry)
                assert all(c.strike is None for c in contracts if c.instrument_type == "FUT")
            assert both, "no NIFTY expiry offers both CE and PE strikes"
            assert await pickable_contracts(conn, "BANKNIFTY", today) == []
        finally:
            await trans.rollback()
