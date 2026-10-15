"""W-060 AC-1, database part: the NIFTY 50 and SENSEX index rows are storable through the real store code (migration 0006).

Spec basis: REQ-072 AC-1 ("The platform's segment list gains NSE_INDEX and BSE_INDEX for the two index rows only
(NIFTY 50, SENSEX); their identity is (segment, exchange token)..."); findings F-10 (NSE exchange token 1001 is both
NIFTY 50 and the cash row 94SFL28-YL).

Rows are real Zerodha rows already in the repo: NIFTY 50 from tests_app/fixtures (2026-10-02), SENSEX from
tests/fixtures/kite_ws (2026-10-08), the NSE cash row from tests/instruments/test_index_segments.py (F-10).
Database tests run as the application role in a rolled-back transaction; CI requires them (OFO_REQUIRE_DB_TESTS=1) and
is where the mutation below is proven:

Mutation (CI only; no PostgreSQL on the laptop): drop `broker_segment = 'INDICES'` from the lot_size CHECK in
0006_index_segments.py -> test_a_zero_lot_or_tick_option_row_is_refused_by_the_lot_and_tick_checks goes red, because a lot-0 option row would then
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
SEGMENT = "catalogue_contracts_exchange_segment_check"
SUPPORTED = "catalogue_contracts_supported_underlying"
TYPE = "catalogue_contracts_instrument_type_check"
IDENTITY = "catalogue_contracts_index_identity"
TABLE = "public.catalogue_contracts"
BROKER = "public.broker_instruments"


def _contract(segment: str, token: int, name: str, kind: str, expiry: str = "NULL", strike: int = 0) -> str:
    return (f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, instrument_type) "
            f"VALUES ('{segment}', {token}, '{name}', {expiry}, {strike}, '{kind}')")


def _broker(contract_id: int, broker_segment: str, lot: int, tick: str) -> str:
    return (f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, broker_segment, lot_size, "
            f"tick_size) VALUES ({contract_id}, 'zerodha', 'T-{contract_id}', 'X', '{broker_segment}', {lot}, {tick})")


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


async def _expect_refused(conn, sql: str, constraint: str | None = None) -> None:
    """The statement must fail with SQLSTATE 23514 and, when given, ON that CHECK (its name is in the error)."""
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql))
    except DBAPIError as exc:
        assert _sqlstate(exc) == CHECK_VIOLATION, f"refused with {_sqlstate(exc)}: {exc}"
        if constraint is not None:
            assert f'"{constraint}"' in str(exc), f"refused, but not by {constraint}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


def test_the_migration_names_exactly_the_domains_index_rows() -> None:
    import importlib.util

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0006_index_segments.py"
    spec = importlib.util.spec_from_file_location("ofo_migration_0006_index_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)  # type: ignore[union-attr]
    assert {(name, segment) for (segment, _), (name, _) in INDEX_ROWS.items()} == set(migration.INDEX_PAIRS)
    assert {(name, segment, token) for (segment, token), (name, _) in INDEX_ROWS.items()} == set(migration.INDEX_IDENTITY)
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
            # (PostgreSQL reports the first failing CHECK in name order, so each case names the one that comes first)
            await _expect_refused(conn, _contract("NSE_INDEX", 1002, "94SFL28-YL", "INDEX"), IDENTITY)
            await _expect_refused(conn, _contract("NSE_FO", 1001, "NIFTY 50", "INDEX"), TYPE)
        finally:
            await trans.rollback()


async def test_a_zero_lot_or_tick_option_row_is_refused_by_the_lot_and_tick_checks(app_engine: AsyncEngine) -> None:
    """A contract with NO Zerodha row yet, so the refusal is the CHECK (23514) and not a duplicate (23505)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(_contract("NSE_FO", 99999, "NIFTY", "CE", expiry="'2027-12-28'", strike=25000)))
            cid = await conn.scalar(text(f"SELECT id FROM {TABLE} WHERE exchange_token = 99999"))
            assert await conn.scalar(text(f"SELECT count(*) FROM {BROKER} WHERE contract_id = {cid}")) == 0
            for lot, tick, name in ((0, "0.05", "broker_instruments_lot_size_check"),
                                    (65, "0", "broker_instruments_tick_size_check"),
                                    (-1, "0.05", "broker_instruments_lot_size_check")):
                await _expect_refused(conn, _broker(cid, "NFO-OPT", lot, tick), name)
            await conn.execute(text(_broker(cid, "NFO-OPT", 65, "0.05")))  # the same row with real terms is stored
        finally:
            await trans.rollback()


async def test_the_instrument_type_check_keeps_index_and_derivative_types_apart(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _expect_refused(conn, _contract("NSE_FO", 99998, "NIFTY", "INDEX", expiry="'2027-12-28'"), TYPE)
            await _expect_refused(conn, _contract("NSE_INDEX", 1001, "NIFTY 50", "CE"), TYPE)
            await _expect_refused(conn, _contract("BSE_INDEX", 1, "SENSEX", "FUT"), TYPE)
            await conn.execute(text(_contract("NSE_INDEX", 1001, "NIFTY 50", "INDEX")))  # the right type is stored
        finally:
            await trans.rollback()


async def test_the_database_pins_each_index_to_its_own_token_and_no_expiry_or_strike(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for segment, token, name in (("NSE_INDEX", 1002, "NIFTY 50"), ("NSE_INDEX", 1, "NIFTY 50"),
                                         ("BSE_INDEX", 1001, "SENSEX"), ("BSE_INDEX", 2, "SENSEX")):
                await _expect_refused(conn, _contract(segment, token, name, "INDEX"), IDENTITY)
            await _expect_refused(conn, _contract("NSE_INDEX", 1001, "NIFTY 50", "INDEX", expiry="'2027-12-28'"), IDENTITY)
            await _expect_refused(conn, _contract("BSE_INDEX", 1, "SENSEX", "INDEX", strike=25000), IDENTITY)
            await _expect_refused(conn, _contract("NSE_INDEX", 1001, "SENSEX", "INDEX"), IDENTITY)  # the other's name
            # the name/segment pairs still refuse an underlying outside the two
            await _expect_refused(conn, _contract("NSE_FO", 99997, "BANKNIFTY", "CE", expiry="'2027-12-28'"), SUPPORTED)
            for segment, token, name in (("NSE_INDEX", 1001, "NIFTY 50"), ("BSE_INDEX", 1, "SENSEX")):
                await conn.execute(text(_contract(segment, token, name, "INDEX")))
        finally:
            await trans.rollback()


def _run_migration(module_name: str):
    """The migration's statements, in order, as recorded from upgrade() / downgrade() (what alembic would execute)."""
    import importlib.util
    from types import SimpleNamespace

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0006_index_segments.py"
    found = importlib.util.spec_from_file_location(module_name, path)
    migration = importlib.util.module_from_spec(found)
    found.loader.exec_module(migration)  # type: ignore[union-attr]
    recorded: list[str] = []
    migration.op = SimpleNamespace(execute=lambda sql, *a, **k: recorded.append(str(sql)))
    migration._BASE._app_role = lambda: "ofo_app"
    return migration, recorded


async def test_downgrade_then_upgrade_round_trips_and_downgrade_refuses_with_an_index_row(admin_engine: AsyncEngine) -> None:
    down_m, down = _run_migration("ofo_migration_0006_down_test")
    down_m.downgrade()
    up_m, up = _run_migration("ofo_migration_0006_up_test")
    up_m.upgrade()
    assert "'pre'" in down[0] and "'post'" in down[-1]  # the allowlist is checked at both ends, as in upgrade
    async with admin_engine.connect() as conn:
        trans = await conn.begin()  # DDL is transactional: everything below is rolled back
        try:
            for sql in down:  # empty catalogue: the downgrade runs to the end
                await conn.execute(text(sql))
            await _expect_refused(conn, _contract("NSE_INDEX", 1001, "NIFTY 50", "INDEX"), SEGMENT)
            for sql in up:  # and the upgrade restores everything
                await conn.execute(text(sql))
            await conn.execute(text(_contract("NSE_INDEX", 1001, "NIFTY 50", "INDEX")))
            with pytest.raises(DBAPIError, match="refusing to downgrade 0006_index_segments"):
                async with conn.begin_nested():
                    for sql in down:  # with an index row stored, the same downgrade refuses
                        await conn.execute(text(sql))
            assert await conn.scalar(text(f"SELECT count(*) FROM {TABLE} WHERE exchange_segment = 'NSE_INDEX'")) == 1
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


def test_every_statement_of_the_upgrade_and_downgrade_parses_in_postgresql_own_parser() -> None:
    """No database needed: libpg_query parses each statement, so a quoting mistake (round 1: the downgrade's nested
    quotes) fails here and not first in CI. A DO block's body is parsed too."""
    pglast = pytest.importorskip("pglast")
    for name, call in (("up", "upgrade"), ("down", "downgrade")):
        migration, recorded = _run_migration(f"ofo_migration_0006_parse_{name}")
        getattr(migration, call)()
        assert len(recorded) > 5
        for sql in recorded:
            pglast.parse_sql(sql)
            if sql.lstrip().startswith("DO"):
                body = sql.split("$down$" if "$down$" in sql else "$drop$")[1]
                pglast.parse_plpgsql(f"CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $x$ {body} $x$")
