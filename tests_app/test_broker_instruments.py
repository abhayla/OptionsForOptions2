"""W-056: Zerodha's ids live only in public.broker_instruments, keyed to (exchange_segment, exchange_token).

Spec basis: REQ-054 AC-3 "Each broker's own token, trading symbol and segment code for a contract are stored in a
per-broker table keyed to the contract's identity (exchange segment, exchange token), with one broker code
vocabulary; a contract with no row for a broker cannot be traded at that broker - no symbol is guessed or derived.";
AC-4 "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them.";
REQ-054 "Exchange segment vocabulary" (NSE_FO, BSE_FO; Zerodha NFO -> NSE_FO, BFO -> BSE_FO); findings F-10.

Expected values come from Zerodha's public list and the spec, never from running the code:
- NIFTY 20050 CE (expiry 2026-10-06): exchange token 40559, instrument_token 10383106, NIFTY26O0620050CE.
- SENSEX 75000 CE (expiry 2026-10-08): exchange token 888931 on BFO.
- NSE / 1001 is both "NIFTY 50" (INDICES) and "94SFL28-YL" (NSE cash) on the 2026-10-02 list (F-10).
Fixture rows (tests_app/fixtures, 2026-10-02): 12468226,48704,NIFTY26OCTFUT,...,65,FUT,NFO-FUT,NFO.
Database tests run as the application role inside a rolled-back transaction; CI requires them (OFO_REQUIRE_DB_TESTS=1).
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ofo.instruments import InstrumentId, MissingBrokerRef
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ListedContract
from ofo_app.catalogue_store import CatalogueStoreError, apply_update, load_catalogue, parse_rows_naming_the_row, with_terms

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 2, 10, 0, tzinfo=IST)
ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests_app" / "fixtures" / "zerodha_instruments_nifty_sensex_2026-10-02.csv"
TABLE = "public.catalogue_contracts"
BROKER = "public.broker_instruments"
HISTORY = "public.catalogue_term_changes"
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
CATALOGUE_SQLSTATE = "OF006"


def _fixture():
    raw = "".join(line for line in FIXTURE.read_text(encoding="utf-8").splitlines(True) if not line.startswith("#"))
    return parse_rows_naming_the_row(io.StringIO(raw))


def _sqlstate(exc: DBAPIError) -> str | None:
    for obj in (exc.orig, getattr(exc.orig, "__cause__", None)):
        code = getattr(obj, "sqlstate", None) or getattr(obj, "pgcode", None)
        if code:
            return str(code)
    return None


async def _expect_refused(conn: AsyncConnection, sql: str, expected: str) -> None:
    try:
        async with conn.begin_nested():
            await conn.execute(text(sql))
    except DBAPIError as exc:
        got = _sqlstate(exc)
        assert got == expected, f"refused with SQLSTATE {got}, expected {expected}: {exc}"
        return
    raise AssertionError(f"not refused: {sql}")


async def _scalar(conn: AsyncConnection, sql: str, params: dict | None = None):
    return (await conn.execute(text(sql), params or {})).scalar_one()


# ---------------------------------------------------------------------------------------------------------------
# AC-3: the schema holds Zerodha's ids only in broker_instruments
# ---------------------------------------------------------------------------------------------------------------


async def test_ac3_no_table_but_broker_instruments_has_a_zerodha_id_column(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' "
            "AND column_name IN ('instrument_token', 'tradingsymbol', 'broker_token', 'broker_symbol') "
            "ORDER BY 1, 2"))).all()
    assert [tuple(r) for r in rows] == [("broker_instruments", "broker_symbol"), ("broker_instruments", "broker_token")]


async def test_ac3_every_stored_contract_has_exactly_one_zerodha_row_keyed_to_its_identity(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            result = await apply_update(conn, _fixture(), as_of=AS_OF)
            assert result.added == 22
            assert await _scalar(conn, f"SELECT count(*) FROM {TABLE}") == 22
            assert await _scalar(conn, f"SELECT count(*) FROM {BROKER} WHERE broker = 'zerodha'") == 22
            row = (await conn.execute(text(
                f"SELECT c.exchange_segment, c.exchange_token, b.broker, b.broker_token, b.broker_symbol, "
                f"b.broker_segment, b.lot_size, b.tick_size::text FROM {TABLE} AS c JOIN {BROKER} AS b "
                f"ON b.contract_id = c.id WHERE c.exchange_segment = 'NSE_FO' AND c.exchange_token = 48704"))).one()
            assert tuple(row) == ("NSE_FO", 48704, "zerodha", "12468226", "NIFTY26OCTFUT", "NFO-FUT", 65, "0.1000")
        finally:
            await trans.rollback()


async def test_ac3_a_contract_with_no_zerodha_row_cannot_be_loaded_or_traded(admin_engine: AsyncEngine) -> None:
    """The owner inserts a contract without a broker row (the app path never can): the reload refuses, naming it."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await conn.execute(text(f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, "
                                    "instrument_type) VALUES ('NSE_FO', 99999, 'NIFTY', '2026-10-27', 25000, 'CE')"))
            with pytest.raises(CatalogueStoreError, match=r"NSE_FO:99999: has no zerodha row"):
                await load_catalogue(conn)
        finally:
            await trans.rollback()


async def test_ac3_lookup_for_a_broker_with_no_row_is_refused(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            entry = (await load_catalogue(conn)).get(InstrumentId("NSE_FO", 48704))
            assert entry.ref("zerodha").broker_symbol == "NIFTY26OCTFUT"
            for broker in ("upstox", "dhan", "Zerodha"):
                with pytest.raises(MissingBrokerRef):
                    entry.ref(broker)
        finally:
            await trans.rollback()


async def test_ac3_unknown_broker_and_segment_codes_are_refused_by_the_database(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            cid = await _scalar(conn, f"SELECT min(id) FROM {TABLE}")
            await _expect_refused(conn, f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, "
                                        f"broker_segment, lot_size, tick_size) VALUES ({cid}, 'upstox', 'X', 'X', "
                                        "'NSE_FO', 65, 0.05)", CHECK_VIOLATION)
            # mutation test (3): an exchange segment outside the list
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, strike, "
                                        "instrument_type) VALUES ('NFO', 1, 'NIFTY', 0, 'FUT')", CHECK_VIOLATION)
            await _expect_refused(conn, f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, strike, "
                                        "instrument_type) VALUES ('NSE', 1001, 'NIFTY', 0, 'FUT')", CHECK_VIOLATION)
        finally:
            await trans.rollback()


async def test_ac3_app_role_cannot_delete_or_rewrite_broker_rows(app_engine: AsyncEngine) -> None:
    """Mutation test (2): a DELETE on broker_instruments as the app role is refused; so are identity rewrites."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            await _expect_refused(conn, f"DELETE FROM {BROKER}", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET broker_token = '1'", INSUFFICIENT_PRIVILEGE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET contract_id = contract_id", INSUFFICIENT_PRIVILEGE)
            assert await _scalar(conn, f"SELECT count(*) FROM {BROKER}") == 22
        finally:
            await trans.rollback()


async def test_ac3_owner_cannot_delete_or_change_a_broker_rows_identity(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            where = "WHERE broker_symbol = 'NIFTY26OCTFUT'"
            await _expect_refused(conn, f"DELETE FROM {BROKER} {where}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET broker_token = '1' {where}", CATALOGUE_SQLSTATE)
            await _expect_refused(conn, f"UPDATE {BROKER} SET broker_segment = 'NFO-OPT' {where}", CATALOGUE_SQLSTATE)
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# AC-4: lot/tick/freeze per broker, dated
# ---------------------------------------------------------------------------------------------------------------


async def test_ac4_a_zerodha_lot_revision_is_dated_and_writes_one_history_row_naming_the_broker(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            today_ist = await _scalar(conn, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date")
            first = (await conn.execute(text(f"SELECT seen_on, first_seen_at FROM {BROKER} "
                                             "WHERE broker_token = '12468226'"))).one()
            assert first.seen_on == today_ist
            revised = [with_terms(c, lot_size=75) if c.ref("zerodha").broker_token == "12468226" else c
                       for c in _fixture()]
            result = await apply_update(conn, revised, as_of=AS_OF)
            assert (result.added, result.revised) == (0, 1)
            row = (await conn.execute(text(f"SELECT lot_size, seen_on, first_seen_at FROM {BROKER} "
                                           "WHERE broker_token = '12468226'"))).one()
            assert (row.lot_size, row.seen_on, row.first_seen_at) == (75, today_ist, first.first_seen_at)
            history = (await conn.execute(text(
                f"SELECT c.exchange_segment, c.exchange_token, h.broker, h.field, h.old_value, h.new_value "
                f"FROM {HISTORY} AS h JOIN {TABLE} AS c ON c.id = h.contract_id"))).all()
            assert [tuple(h) for h in history] == [("NSE_FO", 48704, "zerodha", "lot_size", "65", "75")]
            with capsys.disabled():
                print(f"\nW-056 PROOF revise zerodha 12468226 lot 65->75 seen_on={row.seen_on} "
                      f"history={[tuple(h) for h in history]}")
        finally:
            await trans.rollback()


async def test_ac4_a_tick_and_freeze_revision_each_write_a_history_row(app_engine: AsyncEngine) -> None:
    from decimal import Decimal

    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            revised = [with_terms(c, tick_size=Decimal("0.05"), freeze_limit=1800)
                       if c.ref("zerodha").broker_token == "12468226" else c for c in _fixture()]
            await apply_update(conn, revised, as_of=AS_OF)
            history = (await conn.execute(text(
                f"SELECT broker, field, old_value, new_value FROM {HISTORY} ORDER BY field"))).all()
            assert [tuple(h) for h in history] == [("zerodha", "freeze_limit", None, "1800"),
                                                   ("zerodha", "tick_size", "0.1000", "0.0500")]
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# Core proof on the real file (network; CI)
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.network
async def test_real_file_counts_named_contracts_and_f10_collisions(
    app_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    import csv

    from ofo.instruments.downloader import download_instruments_csv

    raw = download_instruments_csv()
    rows = parse_rows_naming_the_row(io.StringIO(raw))
    scoped = [r for r in rows if Catalogue._in_scope(r.contract)]
    collisions = [r for r in csv.DictReader(io.StringIO(raw)) if r["exchange"] == "NSE" and r["exchange_token"] == "1001"]
    assert {r["tradingsymbol"] for r in collisions} >= {"NIFTY 50"}, collisions
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await _scalar(conn, f"SELECT count(*) FROM {TABLE}") == 0, "tables must be empty (tests roll back)"
            as_of = await _scalar(conn, "SELECT clock_timestamp()")
            await apply_update(conn, rows, as_of=as_of)
            contracts = await _scalar(conn, f"SELECT count(*) FROM {TABLE}")
            broker_rows = await _scalar(conn, f"SELECT count(*) FROM {BROKER} WHERE broker = 'zerodha'")
            load_day = as_of.astimezone(IST).date()
            live_rows = [r for r in scoped if r.contract.expiry >= load_day]  # ADR-059: stale rows are skipped
            assert len(live_rows) == contracts == broker_rows

            # W-057 fix: the named contracts are chosen relative to the load date (the live file changes daily): the
            # lowest-token CE of the nearest unexpired NIFTY and SENSEX expiry, compared with the file's own row
            def nearest_ce(name: str) -> ListedContract:
                pool = [r for r in live_rows if r.contract.name == name and r.contract.instrument_type == "CE"]
                first = min(r.contract.expiry for r in pool)
                return min((r for r in pool if r.contract.expiry == first), key=lambda r: r.contract.exchange_token)

            want_nifty, want_sensex = nearest_ce("NIFTY"), nearest_ce("SENSEX")
            nifty = (await conn.execute(text(
                f"SELECT c.exchange_segment, c.exchange_token, b.broker, b.broker_token, b.broker_symbol FROM {TABLE} "
                f"AS c JOIN {BROKER} AS b ON b.contract_id = c.id WHERE c.exchange_segment = 'NSE_FO' "
                f"AND c.exchange_token = :t"), {"t": want_nifty.contract.exchange_token})).one()
            ref = want_nifty.ref("zerodha")
            assert tuple(nifty) == ("NSE_FO", want_nifty.contract.exchange_token, "zerodha", ref.broker_token,
                                    ref.broker_symbol)
            sensex = (await conn.execute(text(
                f"SELECT exchange_segment, exchange_token FROM {TABLE} WHERE exchange_segment = 'BSE_FO' "
                f"AND exchange_token = :t"), {"t": want_sensex.contract.exchange_token})).one()
            assert tuple(sensex) == ("BSE_FO", want_sensex.contract.exchange_token)
            stray = await _scalar(conn, f"SELECT count(*) FROM {TABLE} WHERE exchange_token = 1001")
            assert stray == 0
            entry = (await load_catalogue(conn)).get(want_nifty.id)
            with pytest.raises(MissingBrokerRef):
                entry.ref("upstox")
            with capsys.disabled():
                print(f"\nW-056 PROOF file rows={len(rows)} skipped_outside_v1={rows.skipped_outside_v1} "
                      f"in_scope={len(scoped)} catalogue={contracts} zerodha_rows={broker_rows}"
                      f"\nW-056 PROOF NIFTY 20050 CE -> {tuple(nifty)}"
                      f"\nW-056 PROOF SENSEX 75000 CE -> {tuple(sensex)}"
                      f"\nW-056 PROOF NSE/1001 file rows={[r['tradingsymbol'] for r in collisions]} stored={stray}"
                      f"\nW-056 PROOF missing broker row refused: upstox lookup raised MissingBrokerRef")
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------------------------------------------
# W-056 fix round 1: review items M1, M4, m1, m2
# ---------------------------------------------------------------------------------------------------------------


def _migration_0004():
    import importlib.util

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0004_broker_instruments.py"
    loader_spec = importlib.util.spec_from_file_location("ofo_migration_0004_broker_test", path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def test_m1_upgrade_refusal_statement_refuses_a_non_empty_catalogue(app_engine: AsyncEngine) -> None:
    """M1: 0004 moves no 0003 data; its first change refuses while the catalogue holds a row. The harness cannot stage
    a 0003 database (CI migrates to head once), so the migration's own refusal statement is run against the head
    tables: refused with rows, accepted when empty."""
    sql = _migration_0004().refuse_if_rows_sql()
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            async with conn.begin_nested():
                await conn.execute(text(sql))  # empty: no refusal
            await apply_update(conn, _fixture(), as_of=AS_OF)
            with pytest.raises(DBAPIError, match="refusing to upgrade to 0004_broker_instruments"):
                async with conn.begin_nested():
                    await conn.execute(text(sql))
        finally:
            await trans.rollback()


async def test_m4_a_zerodha_load_never_clears_a_stored_freeze_limit(app_engine: AsyncEngine) -> None:
    """REQ-054 "Per-broker values and their date": Zerodha's list has no freeze limit, so a daily load keeps 1800 and
    writes no 1800 -> NULL history row."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            with_freeze = [with_terms(c, freeze_limit=1800) if c.ref("zerodha").broker_token == "12468226" else c
                           for c in _fixture()]
            await apply_update(conn, with_freeze, as_of=AS_OF)
            assert await _scalar(conn, f"SELECT freeze_limit FROM {BROKER} WHERE broker_token = '12468226'") == 1800
            result = await apply_update(conn, _fixture(), as_of=AS_OF)  # the plain Zerodha list: no freeze value
            assert result.revised == 0
            assert await _scalar(conn, f"SELECT freeze_limit FROM {BROKER} WHERE broker_token = '12468226'") == 1800
            assert await _scalar(conn, f"SELECT count(*) FROM {HISTORY}") == 0
            entry = (await load_catalogue(conn)).get(InstrumentId("NSE_FO", 48704))
            assert entry.ref("zerodha").freeze_limit == 1800
        finally:
            await trans.rollback()


async def test_m1_owner_cannot_backdate_a_broker_rows_stamps(admin_engine: AsyncEngine) -> None:
    """m1: the database stamps seen_on / first_seen_at / last_seen_at on insert and update, whatever is supplied."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            today_ist = await _scalar(conn, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date")
            await conn.execute(text(f"INSERT INTO {TABLE} (exchange_segment, exchange_token, name, expiry, strike, "
                                    "instrument_type) VALUES ('NSE_FO', 99998, 'NIFTY', '2026-10-27', 25000, 'PE')"))
            cid = await _scalar(conn, f"SELECT id FROM {TABLE} WHERE exchange_token = 99998")
            await conn.execute(text(
                f"INSERT INTO {BROKER} (contract_id, broker, broker_token, broker_symbol, broker_segment, lot_size, "
                f"tick_size, seen_on, first_seen_at, last_seen_at) VALUES ({cid}, 'zerodha', '99998', 'X', 'NFO-OPT', "
                "65, 0.05, '2000-01-01', '2000-01-01', '2000-01-01')"))
            row = (await conn.execute(text(f"SELECT seen_on, first_seen_at, last_seen_at FROM {BROKER} "
                                           f"WHERE contract_id = {cid}"))).one()
            assert row.seen_on == today_ist and row.first_seen_at.year > 2000 and row.last_seen_at.year > 2000
            await conn.execute(text(f"UPDATE {BROKER} SET seen_on = '2000-01-01', first_seen_at = '2000-01-01', "
                                    f"last_seen_at = '2000-01-01' WHERE contract_id = {cid}"))
            again = (await conn.execute(text(f"SELECT seen_on, first_seen_at, last_seen_at FROM {BROKER} "
                                             f"WHERE contract_id = {cid}"))).one()
            assert again.seen_on == today_ist and again.first_seen_at == row.first_seen_at
            assert again.last_seen_at >= row.last_seen_at
        finally:
            await trans.rollback()


async def test_m2_a_revised_broker_symbol_writes_one_dated_history_row(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await apply_update(conn, _fixture(), as_of=AS_OF)
            today_ist = await _scalar(conn, "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date")
            revised = [with_terms(c, broker_symbol="NIFTY26OCTFUTX") if c.ref("zerodha").broker_token == "12468226"
                       else c for c in _fixture()]
            result = await apply_update(conn, revised, as_of=AS_OF)
            assert result.revised == 1
            history = (await conn.execute(text(
                f"SELECT broker, field, old_value, new_value, (changed_at AT TIME ZONE 'Asia/Kolkata')::date AS day "
                f"FROM {HISTORY}"))).all()
            assert [tuple(h) for h in history] == [("zerodha", "broker_symbol", "NIFTY26OCTFUT", "NIFTY26OCTFUTX",
                                                    today_ist)]
            assert await _scalar(conn, f"SELECT broker_symbol FROM {BROKER} WHERE broker_token = '12468226'") == \
                "NIFTY26OCTFUTX"
        finally:
            await trans.rollback()
