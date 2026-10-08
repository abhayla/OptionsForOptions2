"""W-060 AC-1, database part: the NIFTY 50 and SENSEX index rows are storable through the real store code (migration 0006).

Spec basis: REQ-072 AC-1 ("The platform's segment list gains NSE_INDEX and BSE_INDEX for the two index rows only
(NIFTY 50, SENSEX); their identity is (segment, exchange token)..."); findings F-10 (NSE exchange token 1001 is both
NIFTY 50 and the cash row 94SFL28-YL).

Rows are real Zerodha rows already in the repo: NIFTY 50 from tests_app/fixtures (2026-10-02), SENSEX from
tests/fixtures/kite_ws (2026-10-08), the NSE cash row from tests/instruments/test_index_segments.py (F-10).
Database tests run as the application role in a rolled-back transaction; CI requires them (OFO_REQUIRE_DB_TESTS=1) and
is where the mutation below is proven:

Mutation (CI only; no PostgreSQL on the laptop): drop `broker_segment = 'INDICES'` from the lot_size CHECK in
0006_index_segments.py -> test_a_zero_lot_option_row_is_still_refused goes red, because a lot-0 option row would then
store; drop `lot_size = 0` from it -> test_index_rows_are_stored_and_read_back goes red.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from ofo.instruments import InstrumentId
from ofo.instruments.models import INDEX_ROWS
from ofo.instruments.parser import parse_instruments_rows
from ofo_app.catalogue_store import apply_update, load_catalogue

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 2, 10, 0, tzinfo=IST)
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests_app" / "fixtures" / "zerodha_instruments_nifty_sensex_2026-10-02.csv"
HEADER = "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange\n"
NIFTY_50_ROW = "256265,1001,NIFTY 50,NIFTY 50,0,,0,0,0,EQ,INDICES,NSE\n"  # last row of the fixture above
SENSEX_ROW = "265,1,SENSEX,SENSEX,0,,0,0,0,EQ,INDICES,BSE\n"  # tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv
CASH_1001_ROW = "256266,1001,94SFL28-YL,94SFL28,0,,0,0.01,1,EQ,NSE,NSE\n"  # F-10: same exchange token, a cash row
CHECK_VIOLATION = "23514"
TABLE = "public.catalogue_contracts"
BROKER = "public.broker_instruments"


def _rows(raw: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(HEADER + raw)))


def _fixture_derivatives():
    text_ = "".join(l for l in FIXTURE.read_text(encoding="utf-8").splitlines(True) if not l.startswith("#"))
    return list(parse_instruments_rows(csv.DictReader(io.StringIO(text_))))


def _all_rows():
    """The fixture (22 derivatives + the real NIFTY 50 row) plus the real SENSEX row: 24 storable contracts."""
    return _fixture_derivatives() + list(parse_instruments_rows(_rows(SENSEX_ROW)))


def _index_listed():
    return list(parse_instruments_rows(_rows(NIFTY_50_ROW + SENSEX_ROW + CASH_1001_ROW)))


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


async def _expect_refused(conn, sql: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql))
    except DBAPIError as exc:
        assert _sqlstate(exc) == CHECK_VIOLATION, f"refused with {_sqlstate(exc)}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


def test_the_migration_names_exactly_the_domains_index_rows() -> None:
    import importlib.util

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0006_index_segments.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0006_index_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)  # type: ignore[union-attr]
    assert {(name, segment) for (segment, _), (name, _) in INDEX_ROWS.items()} == set(migration.INDEX_PAIRS)
    assert {s for s, _ in INDEX_ROWS} == set(migration.INDEX_SEGMENTS)


def test_the_parser_takes_nifty_50_and_sensex_and_leaves_the_cash_row_out() -> None:
    listed = _index_listed()
    assert [(c.contract.exchange_segment, c.contract.exchange_token, c.contract.name) for c in listed] == [
        ("NSE_INDEX", 1001, "NIFTY 50"), ("BSE_INDEX", 1, "SENSEX")]  # the NSE cash row 94SFL28-YL is not here


async def test_index_rows_are_stored_and_read_back(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            result = await apply_update(conn, _all_rows(), as_of=AS_OF)
            assert result.added == 22 + 2
            raw = (await conn.execute(text(
                f"SELECT c.exchange_segment, c.exchange_token, c.name, c.instrument_type, c.expiry, b.broker_token, "
                f"b.broker_segment, b.lot_size, b.tick_size::text FROM {TABLE} AS c JOIN {BROKER} AS b "
                f"ON b.contract_id = c.id WHERE c.instrument_type = 'INDEX' ORDER BY c.exchange_segment"))).all()
            assert [tuple(r) for r in raw] == [
                ("BSE_INDEX", 1, "SENSEX", "INDEX", None, "265", "INDICES", 0, "0.0000"),
                ("NSE_INDEX", 1001, "NIFTY 50", "INDEX", None, "256265", "INDICES", 0, "0.0000"),
            ]
            catalogue = await load_catalogue(conn)
            nifty = catalogue.get(InstrumentId("NSE_INDEX", 1001))
            assert (nifty.contract.name, nifty.contract.instrument_type) == ("NIFTY 50", "INDEX")
            assert nifty.ref("zerodha").broker_token == "256265" and nifty.currently_listed
            assert catalogue.get(InstrumentId("BSE_INDEX", 1)).contract.name == "SENSEX"
        finally:
            await trans.rollback()


async def test_the_nse_cash_row_sharing_token_1001_is_not_nifty_50(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _all_rows(), as_of=AS_OF)
            rows = (await conn.execute(text(f"SELECT exchange_segment, name FROM {TABLE} WHERE exchange_token = 1001"))).all()
            assert [tuple(r) for r in rows] == [("NSE_INDEX", "NIFTY 50")]  # the cash row was never stored
            catalogue = await load_catalogue(conn)
            assert InstrumentId("NSE_INDEX", 1001) in {e.id for e in catalogue.all_entries()}
            assert InstrumentId("NSE_FO", 1001) not in {e.id for e in catalogue.all_entries()}
            # the cash row cannot be stored as an index row or as a derivative either
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, strike, "
                                        "instrument_type) VALUES ('NSE_INDEX', 1002, '94SFL28-YL', 0, 'INDEX')")
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, strike, "
                                        "instrument_type) VALUES ('NSE_FO', 1001, 'NIFTY 50', 0, 'INDEX')")
        finally:
            await trans.rollback()


async def test_a_zero_lot_option_row_is_still_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _all_rows(), as_of=AS_OF)
            cid = await conn.scalar(text(f"SELECT min(id) FROM {TABLE} WHERE exchange_segment = 'NSE_FO'"))
            for column in ("lot_size", "tick_size"):
                lot, tick = ("0", "0.05") if column == "lot_size" else ("65", "0")
                await _expect_refused(
                    conn, f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, broker_segment, "
                          f"lot_size, tick_size) VALUES ({cid}, 'zerodha', 'ZERO-{column}', 'X', 'NFO-OPT', {lot}, {tick})")
            # a negative lot is refused whatever the segment
            await _expect_refused(
                conn, f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, broker_segment, "
                      f"lot_size, tick_size) VALUES ({cid}, 'zerodha', 'ZERO-NEG', 'X', 'NFO-OPT', -1, 0.05)")
        finally:
            await trans.rollback()


async def test_planning_stores_index_rows_without_an_expiry_and_never_retires_them_without_a_database() -> None:
    """The store plans the two index rows as inserts (no expiry is not an error for an index) with no database."""
    from tests_app.test_catalogue_store import _FakeConn

    conn = _FakeConn()
    result = await apply_update(conn, _all_rows(), as_of=AS_OF)
    assert (result.added, result.retired) == (24, 0)
    contracts, brokers = conn.writes[0][1], conn.writes[1][1]
    assert sorted((p["exchange_segment"], p["exchange_token"], p["expiry"]) for p in contracts
                  if p["instrument_type"] == "INDEX") == [("BSE_INDEX", 1, None), ("NSE_INDEX", 1001, None)]
    assert sorted((p["broker_token"], p["broker_segment"], p["lot_size"]) for p in brokers
                  if p["broker_segment"] == "INDICES") == [("256265", "INDICES", 0), ("265", "INDICES", 0)]
