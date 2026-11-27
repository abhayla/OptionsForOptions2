"""Migration 0059 and the stored last close (Lane N A1 / AF-02; ADR-330 (36), ADR-008, ADR-048).

Real PostgreSQL only (skips without TEST_DATABASE_URL); every test rolls back, so no row of the test database changes.
Core proof (first test): the limited application role upserts a close and reads the newest trade date per instrument
with the module's own SQL; a price finer than a paisa is refused by the CHECK (SQLSTATE 23514), never rounded; the role
cannot DELETE. Then: the downgrade drops the table and the upgrade brings it back (the chain replayed to head).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from _migration_replay import round_trip_sql
from ofo_app import last_close_store as lcs
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

MIGRATION = "0059_last_close.py"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MON, TUE = datetime.date(2026, 11, 30), datetime.date(2026, 12, 1)
CHECK_VIOLATION = "23514"
_ROWS = (("T59:A", MON), ("T59:A", TUE), ("T59:B", MON))


def _cols(rows):
    return {"instrument_id": [r[0] for r in rows], "trade_date": [r[1] for r in rows], "price": [r[2] for r in rows],
            "price_at": [r[3] for r in rows], "source": [r[4] for r in rows]}


def _row(iid, day, price, hh=15, mm=29):
    return (iid, day, Decimal(price), datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST), "feed_book")


async def test_core_the_app_role_upserts_and_reads_the_newest_close_per_instrument(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(lcs._UPSERT, _cols([_row("T59:A", MON, "99.75"), _row("T59:A", TUE, "100.10"),
                                                   _row("T59:B", MON, "5.00")]))
            await conn.execute(lcs._UPSERT, _cols([_row("T59:A", TUE, "101.25", 15, 30)]))  # same key: replaced
            sql = lcs._LATEST.format(where="WHERE instrument_id = ANY(CAST(:ids AS text[]))")
            got = {r[0]: (r[1], r[3]) for r in (await conn.execute(text(sql), {"ids": ["T59:A", "T59:B"]})).all()}
            assert got == {"T59:A": (Decimal("101.25"), TUE), "T59:B": (Decimal("5.00"), MON)}
            n = (await conn.execute(text("SELECT count(*) FROM public.last_close WHERE instrument_id LIKE 'T59:%'"))
                 ).scalar_one()
            assert n == len(_ROWS)  # one row per instrument per trade date
        finally:
            await trans.rollback()


@pytest.mark.parametrize("price", ["99.755", "-1.00", "1000000000000.00", "NaN"])
async def test_a_sub_paisa_negative_or_huge_price_is_refused_by_the_check(app_engine, price):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            with pytest.raises(DBAPIError) as err:
                await conn.execute(text("INSERT INTO public.last_close (instrument_id, trade_date, price, price_at, "
                                        "source) VALUES ('T59:X', :d, CAST(:p AS numeric), now(), 'feed_book')"),
                                   {"d": TUE, "p": price})
            assert getattr(err.value.orig, "sqlstate", None) == CHECK_VIOLATION
        finally:
            await trans.rollback()


async def test_the_app_role_cannot_delete_or_truncate(app_engine):
    for sql in ("DELETE FROM public.last_close", "TRUNCATE public.last_close"):
        async with app_engine.connect() as conn:
            trans = await conn.begin()
            try:
                with pytest.raises(ProgrammingError, match="permission denied"):
                    await conn.execute(text(sql))
            finally:
                await trans.rollback()


async def test_the_downgrade_drops_the_table_and_the_upgrade_brings_it_back(admin_engine):
    _, _, down, up = round_trip_sql(MIGRATION)
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            assert (await conn.execute(text("SELECT to_regclass('public.last_close')"))).scalar_one() is None
            for sql in up:
                await conn.execute(text(sql))
            assert (await conn.execute(text("SELECT to_regclass('public.last_close')"))).scalar_one() is not None
            for sql in down:  # and once more: re-upgrade after a downgrade is clean
                await conn.execute(text(sql))
            for sql in up:
                await conn.execute(text(sql))
        finally:
            await trans.rollback()
