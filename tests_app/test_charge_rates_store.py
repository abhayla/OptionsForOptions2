"""AC-6: the dated charge rate store (W-074, ADR-082 part 1; migration 0012).

Spec basis: ADR-082 ("The rates are admin settings with the date they were read; every amount is exact Decimal; STT
and stamp duty are not rounded at order level"); ADR-023 (the database clock); ADR-048 (the limited application role).

Database tests run as the application role inside a transaction that is rolled back (the table is append-only, so a
test never leaves a row). Expected values: the seed is F-35's rate text of 2026-10-15; a later set is built here.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from ofo_app import charge_rates_store
from ofo_app.charge_rates_store import ChargeRatesError, add_rate_set, rates_in_force

D = Decimal
VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
SEED_DAY = date(2026, 10, 15)


def _migration():
    spec = importlib.util.spec_from_file_location("ofo_0012_for_test", VERSIONS / "0012_charge_rates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_components_equal_the_migrations():
    """AC-6: the store's component names are the migration's (a rename in one place only is refused)."""
    assert charge_rates_store.COMPONENTS == _migration().COMPONENTS


async def _tx(engine: AsyncEngine):
    conn = await engine.connect()
    trans = await conn.begin()
    return conn, trans


async def test_the_seed_is_the_published_rates(app_engine):
    """AC-6: the 2026-10-15 seed equals F-35's text (brokerage 20, STT 0.15%, NSE 0.03553%, BSE 0.0325%, SEBI Rs 10 per
    crore = 0.000001, stamp 0.003%, GST 18%)."""
    conn, trans = await _tx(app_engine)
    try:
        r = await rates_in_force(conn, SEED_DAY)
        assert r.brokerage_per_order == D("20")
        assert r.stt_sell_rate == D("0.0015") and r.stt_exercise_rate == D("0.0015")
        assert dict(r.transaction_rates) == {"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}
        assert r.sebi_rate == D("0.000001") and r.stamp_buy_rate == D("0.00003") and r.gst_rate == D("0.18")
        assert r.read_on == SEED_DAY and r.source_url.startswith("https://zerodha.com/charges")
    finally:
        await trans.rollback()
        await conn.close()


async def test_no_rate_set_before_the_first_is_an_error(app_engine):
    """AC-6: a day before the first set (2026-10-14) has no rate: error, no default."""
    conn, trans = await _tx(app_engine)
    try:
        with pytest.raises(ChargeRatesError, match="no complete charge rate set in force"):
            await rates_in_force(conn, date(2026, 10, 14))
    finally:
        await trans.rollback()
        await conn.close()


async def test_newest_set_in_force_wins_and_a_future_set_is_not_in_force(app_engine):
    """AC-6: a set dated 2026-11-01 (brokerage 25) wins from that day; on 2026-10-31 the seed is still in force."""
    conn, trans = await _tx(app_engine)
    try:
        seed = await rates_in_force(conn, SEED_DAY)
        later = replace(seed, brokerage_per_order=D("25"), read_on=date(2026, 11, 1), source_url="https://example/later")
        await add_rate_set(conn, later, note="test")
        assert (await rates_in_force(conn, date(2026, 10, 31))).brokerage_per_order == D("20")
        on_day = await rates_in_force(conn, date(2026, 11, 1))
        assert on_day.brokerage_per_order == D("25") and on_day.read_on == date(2026, 11, 1)
        assert on_day.source_url == "https://example/later"
        assert on_day.gst_rate == D("0.18")
    finally:
        await trans.rollback()
        await conn.close()


async def test_default_day_is_the_database_today(app_engine):
    """AC-6: with no day given the database's own IST date is used (today is after the 2026-10-15 seed)."""
    conn, trans = await _tx(app_engine)
    try:
        today = (await conn.execute(text("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date"))).scalar_one()
        assert (await rates_in_force(conn)).read_on == (await rates_in_force(conn, today)).read_on
    finally:
        await trans.rollback()
        await conn.close()


async def test_a_second_set_on_the_same_date_is_refused(app_engine):
    """AC-6: append-only: the seed date already holds a set."""
    conn, trans = await _tx(app_engine)
    try:
        seed = await rates_in_force(conn, SEED_DAY)
        with pytest.raises(ChargeRatesError, match="already exists"):
            await add_rate_set(conn, seed)
    finally:
        await trans.rollback()
        await conn.close()


async def test_a_rate_is_never_updated_or_deleted_by_the_application_role(app_engine):
    """AC-6: the application role holds no UPDATE or DELETE grant (privilege error), history is append-only."""
    for sql in ("UPDATE public.charge_rates SET value = 0 WHERE component = 'gst_rate'",
                "DELETE FROM public.charge_rates"):
        conn, trans = await _tx(app_engine)
        try:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(sql))
        finally:
            await trans.rollback()
            await conn.close()


async def test_the_guard_refuses_an_update_even_for_the_owner(admin_engine):
    """AC-6: the guard trigger (OF012) refuses an owner's update and delete; killing test for the guard."""
    for sql in ("UPDATE public.charge_rates SET value = 0 WHERE component = 'gst_rate'",
                "DELETE FROM public.charge_rates"):
        conn, trans = await _tx(admin_engine)
        try:
            with pytest.raises(DBAPIError, match="insert-only") as excinfo:
                await conn.execute(text(sql))
            assert getattr(excinfo.value.orig, "sqlstate", None) == "OF012"
        finally:
            await trans.rollback()
            await conn.close()


async def test_the_table_refuses_a_bad_value_component_and_blank_source(admin_engine):
    """AC-6: CHECKs: negative or NaN value, an unknown component, a blank source URL are refused by the table."""
    bad = (
        ("gst_rate", "-1", "https://x"),
        ("gst_rate", "NaN", "https://x"),
        ("nse_special", "1", "https://x"),
        ("gst_rate", "1", "  "),
        ("stt_sell_rate", "0.15", "https://x"),  # a percentage typed as a fraction (0.15% is 0.0015)
        ("transaction_rate_nse_fo", "0.03553", "https://x"),
        ("gst_rate", "18", "https://x"),
    )
    for component, value, source in bad:
        conn, trans = await _tx(admin_engine)
        try:
            with pytest.raises(DBAPIError, match="check constraint"):
                await conn.execute(
                    text("INSERT INTO public.charge_rates (component, read_on, value, source_url) "
                         "VALUES (:c, DATE '2030-01-01', CAST(:v AS numeric), :s)"),
                    {"c": component, "v": value, "s": source})
        finally:
            await trans.rollback()
            await conn.close()


async def test_an_incomplete_later_date_is_ignored_the_complete_seed_answers(admin_engine):
    """AC-6: a lone gst_rate row dated 2030-01-01 is not a set: the answer is the complete seed (never a mix)."""
    conn, trans = await _tx(admin_engine)
    try:
        await conn.execute(
            text("INSERT INTO public.charge_rates (component, read_on, value, source_url) "
                 "VALUES ('gst_rate', DATE '2030-01-01', 0.19, 'https://x')"))
        got = await rates_in_force(conn, date(2030, 1, 1))
        assert got.gst_rate == D("0.18") and got.read_on == SEED_DAY
    finally:
        await trans.rollback()
        await conn.close()


async def test_a_back_dated_set_is_refused(app_engine):
    """AC-6: a set dated 2026-10-01 is older than the stored 2026-10-15 set: refused."""
    conn, trans = await _tx(app_engine)
    try:
        seed = await rates_in_force(conn, SEED_DAY)
        with pytest.raises(ChargeRatesError, match="back-dating"):
            await add_rate_set(conn, replace(seed, read_on=date(2026, 10, 1)))
    finally:
        await trans.rollback()
        await conn.close()


async def test_a_same_date_race_is_a_store_error():
    """AC-6: an IntegrityError on insert (a concurrent writer of the same date) becomes ChargeRatesError."""
    from sqlalchemy.exc import IntegrityError

    class Racing:
        async def execute(self, stmt, params=None):
            sql = str(stmt)
            if "INSERT" in sql:
                raise IntegrityError("insert", {}, Exception("duplicate key"))
            if "max(read_on)" in sql:
                return _Scalar(None)
            return _Scalar(None)

    class _Scalar:
        def __init__(self, v):
            self.v = v

        def first(self):
            return self.v

        def scalar_one(self):
            return self.v

    rates = ChargeRates_for_unit()
    with pytest.raises(ChargeRatesError, match="already exists"):
        await add_rate_set(Racing(), rates)  # type: ignore[arg-type]


def ChargeRates_for_unit():
    from ofo.charges import ChargeRates

    return ChargeRates(brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
                       transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
                       stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=date(2026, 11, 1),
                       source_url="https://x")


def test_a_non_date_day_is_refused():
    """AC-6: a datetime or string day raises before any query (no database needed)."""
    import asyncio

    for bad in ("2026-10-15", 20261015):
        with pytest.raises(ChargeRatesError, match="date"):
            asyncio.run(rates_in_force(None, bad))  # type: ignore[arg-type]


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _row(component: str):
    from types import SimpleNamespace

    return SimpleNamespace(component=component, read_on=SEED_DAY, value=D("1"), source_url="https://x")


async def test_a_component_with_no_row_is_an_error_not_a_default():
    """AC-6: seven of the eight components stored -> the answer is an error naming the missing one."""
    rows = [_row(c) for c in charge_rates_store.COMPONENTS if c != "sebi_rate"]
    with pytest.raises(ChargeRatesError, match="sebi_rate"):
        await rates_in_force(_FakeSession(rows), SEED_DAY)


async def test_a_value_that_is_not_a_decimal_is_refused():
    """AC-6: a stored rate that came back as a float is refused (never silently converted)."""
    rows = [_row(c) for c in charge_rates_store.COMPONENTS]
    rows[0].value = 20.0
    with pytest.raises(ChargeRatesError, match="Decimal"):
        await rates_in_force(_FakeSession(rows), SEED_DAY)


async def test_a_set_that_mixes_dates_is_refused():
    """AC-6: rows of one answer carrying two dates (cannot come from the query; the reader still refuses)."""
    rows = [_row(c) for c in charge_rates_store.COMPONENTS]
    rows[3].read_on = date(2026, 10, 16)
    with pytest.raises(ChargeRatesError, match="mixes"):
        await rates_in_force(_FakeSession(rows), SEED_DAY)
