"""AC-4 (REQ-054, ADR-081, F-36): the freeze limit from NSE's contract file is stored per exchange contract with the
file's date; the newest file date is in force; the table is append-only and refuses a future-dated file.

Real input: tests/fixtures/exchange/NSE_FO_contract_15102026_sample.csv (real rows; token 47185 = NIFTY 23550 CE of
2026-10-19, lot 65, MaxTradQty 3511). The catalogue rows are built to agree with it (token, expiry, strike, lot), as
Zerodha's list of that day showed. Every test runs in a transaction that is rolled back."""

from __future__ import annotations

import gzip
import io
import pathlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from ofo.instruments.models import NSE_FO, InstrumentId
from ofo.instruments.parser import zerodha_listed
from ofo_app import freeze_store
from ofo_app.catalogue_store import apply_update

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "exchange" / "NSE_FO_contract_15102026_sample.csv"
NSE_NAME = "NSE_FO_contract_15102026.csv.gz"
TABLE = "public.exchange_freeze_limits"


def _listed(token: int, strike: str, kind: str, lot: int = 65):
    return zerodha_listed(
        instrument_token=token * 256 + 9, exchange_token=token, tradingsymbol=f"NIFTY26O19{strike}{kind}", name="NIFTY",
        expiry=date(2026, 10, 19), strike=Decimal(strike), tick_size=Decimal("0.05"), lot_size=lot,
        instrument_type=kind, segment="NFO-OPT", exchange="NFO", seen_on=date(2026, 10, 15))


async def _catalogue(conn, *rows) -> None:
    assert (await conn.execute(text("SELECT count(*) FROM public.catalogue_contracts"))).scalar_one() == 0
    await apply_update(conn, list(rows), as_of=AS_OF, max_delist_percent=Decimal("10"))


async def test_load_stores_the_limit_with_its_file_date_and_cross_checks(app_engine: AsyncEngine, tmp_path) -> None:
    """AC-4: token 47185 is stored with 3511 and 2026-10-15; token 47112 (lot differs from the file) is reported, not
    stored; reloading the same file stores nothing again."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _catalogue(conn, _listed(47185, "23550", "CE"), _listed(47112, "22000", "CE", lot=75))
            result = await freeze_store.load_freeze_file(conn, FIXTURE, nse_name=NSE_NAME)
            assert (result.inserted, result.already_stored, result.not_in_catalogue) == (1, 0, 83)
            assert [(d.exchange_token, d.fields) for d in result.disagreements] == [(47112, ("lot",))]
            inforce = await freeze_store.limits_in_force(conn)
            assert inforce == {InstrumentId(NSE_FO, 47185): freeze_store.StoredLimit(3511, date(2026, 10, 15))}
            again = await freeze_store.load_freeze_file(conn, FIXTURE, nse_name=NSE_NAME)
            assert (again.inserted, again.already_stored) == (0, 1)
            assert "inserted=0 already_stored=1" in freeze_store.format_result(again)
        finally:
            await trans.rollback()


async def test_a_stale_file_never_replaces_a_newer_limit(app_engine: AsyncEngine) -> None:
    """AC-4: a row from an older file date (here 14 Oct, limit 9999) is stored as history but the 15 Oct limit stays in
    force."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _catalogue(conn, _listed(47185, "23550", "CE"))
            await freeze_store.load_freeze_file(conn, FIXTURE, nse_name=NSE_NAME)
            await conn.execute(text(
                f"INSERT INTO {TABLE} (exchange_segment, exchange_token, file_date, freeze_limit, file_name) "
                "VALUES ('NSE_FO', 47185, '2026-10-14', 9999, 'NSE_FO_contract_14102026.csv.gz')"))
            inforce = await freeze_store.limits_in_force(conn)
            assert inforce[InstrumentId(NSE_FO, 47185)] == freeze_store.StoredLimit(3511, date(2026, 10, 15))
        finally:
            await trans.rollback()


async def test_a_file_dated_after_today_is_refused_and_nothing_is_written(app_engine: AsyncEngine, tmp_path) -> None:
    """AC-4: a file named for 1 Jan 2099 is later than the database clock: refused (ADR-023)."""
    future = tmp_path / "NSE_FO_contract_01012099.csv.gz"
    future.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _catalogue(conn, _listed(47185, "23550", "CE"))
            with pytest.raises(ValueError, match="later than today"):
                await freeze_store.load_freeze_file(conn, future)
            assert (await conn.execute(text(f"SELECT count(*) FROM {TABLE}"))).scalar_one() == 0
        finally:
            await trans.rollback()


async def test_command_prints_a_refusal_for_a_bad_name(app_engine: AsyncEngine, tmp_path) -> None:
    """AC-4: a file name that does not parse is refused before any database work."""
    bad = tmp_path / "qtyfreeze.xls"
    bad.write_bytes(b"x")
    async with app_engine.connect() as conn:
        with pytest.raises(ValueError, match="not an NSE F&O contract file name"):
            await freeze_store.load_freeze_file(conn, bad)


async def test_app_role_cannot_update_or_delete(app_engine: AsyncEngine) -> None:
    """AC-4: the application role has SELECT and INSERT only."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(
                f"INSERT INTO {TABLE} (exchange_segment, exchange_token, file_date, freeze_limit, file_name) "
                "VALUES ('NSE_FO', 47185, '2026-10-15', 3511, 'NSE_FO_contract_15102026.csv.gz')"))
            for sql in (f"UPDATE {TABLE} SET freeze_limit = 1", f"DELETE FROM {TABLE}"):
                async with conn.begin_nested():
                    with pytest.raises(DBAPIError, match="permission denied"):
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()


async def test_guard_refuses_update_delete_and_a_future_date_even_for_the_owner(admin_engine: AsyncEngine) -> None:
    """AC-4: the guard trigger (OF013) holds for the owner role too: no UPDATE, no DELETE, no future file date."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            insert = (f"INSERT INTO {TABLE} (exchange_segment, exchange_token, file_date, freeze_limit, file_name) "
                      "VALUES ('NSE_FO', 47185, :d, 3511, 'f.csv')")
            await conn.execute(text(insert), {"d": date(2026, 10, 15)})
            for sql, params in ((f"UPDATE {TABLE} SET freeze_limit = 1", {}), (f"DELETE FROM {TABLE}", {}),
                                (insert, {"d": date(2099, 1, 1)})):
                async with conn.begin_nested():
                    with pytest.raises(DBAPIError, match="freeze limits"):
                        await conn.execute(text(sql), params)
        finally:
            await trans.rollback()


def test_format_result_names_each_disagreement() -> None:
    """AC-4: the command output lists the rows it did not store, by token and field."""
    from ofo.instruments.freeze_file import Disagreement

    out = freeze_store.format_result(freeze_store.FreezeLoadResult(
        date(2026, 10, 15), 1, 0, 83, (Disagreement(47112, ("lot", "strike")),)))
    assert "disagreements=1" in out and "token 47112 differs from the catalogue in lot, strike" in out
    assert isinstance(io.StringIO(), io.StringIO)
