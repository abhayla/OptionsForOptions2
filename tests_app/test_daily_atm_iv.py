"""ADR-277 (4): the app's own ATM IV, once per underlying per trading day (migration 0047, ``daily_atm_iv_store``).

- one row per underlying per day: a second record the same day returns False and keeps the first value;
- the insert-only guard refuses UPDATE / DELETE / TRUNCATE, even for the table owner;
- a bad underlying, a float, zero, a non-date is refused before the database;
- read_since: ascending from ``since``; none -> []; a non-Decimal -> unreadable;
- migration round trip (allow-list post check passing both ways) and the downgrade refused while rows exist.
Every database test rolls back.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from _migration_replay import recorded, round_trip_sql
from ofo_app import daily_atm_iv_store as store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

DAY = datetime.date(2026, 11, 9)
EXPIRY = datetime.date(2026, 11, 11)
MIGRATION = "0047_daily_atm_iv.py"
GUARD_TEXT = "a daily ATM IV is written once and never changed"


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


@pytest.fixture
async def owner(admin_engine):
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_one_row_per_underlying_per_day_first_value_kept(db):
    assert await store.record(db, "NIFTY", DAY, EXPIRY, D("0.1432")) is True
    assert await store.record(db, "NIFTY", DAY, EXPIRY, D("0.2000")) is False
    assert await store.record(db, "SENSEX", DAY, EXPIRY, D("0.1500")) is True  # the other underlying is its own row
    assert await store.read_since(db, "NIFTY", DAY) == [(DAY, D("0.1432"))]
    assert await store.read_since(db, "SENSEX", DAY) == [(DAY, D("0.1500"))]


async def test_read_since_is_ascending_from_since_and_empty_when_none(db):
    days = [DAY + datetime.timedelta(days=n) for n in (2, 0, 1)]
    for n, day in enumerate(days):
        await store.record(db, "NIFTY", day, EXPIRY, D("0.10") + D(n) / 100)
    got = await store.read_since(db, "NIFTY", DAY + datetime.timedelta(days=1))
    assert got == [(DAY + datetime.timedelta(days=1), D("0.12")), (DAY + datetime.timedelta(days=2), D("0.10"))]
    assert all(isinstance(iv, D) for _, iv in got)
    assert await store.read_since(db, "SENSEX", DAY) == []


@pytest.mark.parametrize("sql", [
    "UPDATE public.daily_atm_iv SET atm_iv = 0.3",
    "DELETE FROM public.daily_atm_iv",
    "TRUNCATE public.daily_atm_iv",
], ids=["update", "delete", "truncate"])
async def test_the_guard_refuses_update_delete_truncate(db, owner, sql):
    await store.record(owner, "NIFTY", DAY, EXPIRY, D("0.1432"))
    with pytest.raises(DBAPIError, match=GUARD_TEXT):  # the owner: no privilege stops it, only the guard
        async with owner.begin_nested():
            await owner.execute(text(sql))
    # SENSEX: the owner's uncommitted NIFTY row would block a same-key insert from this other transaction
    await store.record(db, "SENSEX", DAY, EXPIRY, D("0.1432"))
    with pytest.raises(DBAPIError):  # the app role: refused too (no privilege, and the guard behind it)
        async with db.begin_nested():
            await db.execute(text(sql))
    assert await store.read_since(owner, "NIFTY", DAY) == [(DAY, D("0.1432"))]


@pytest.mark.parametrize(("underlying", "day", "expiry", "iv"), [
    ("BANKNIFTY", DAY, EXPIRY, D("0.14")),
    ("NIFTY", DAY, EXPIRY, 0.14),
    ("NIFTY", DAY, EXPIRY, D(0)),
    ("NIFTY", DAY, EXPIRY, D("-0.1")),
    ("NIFTY", DAY, EXPIRY, D("NaN")),
    ("NIFTY", DAY, EXPIRY, D("Infinity")),
    ("NIFTY", "2026-11-09", EXPIRY, D("0.14")),
    ("NIFTY", DAY, datetime.datetime(2026, 11, 11, tzinfo=datetime.UTC), D("0.14")),
], ids=["underlying", "float", "zero", "negative", "nan", "inf", "day-str", "expiry-datetime"])
async def test_bad_values_are_refused_before_the_database(underlying, day, expiry, iv):
    class _NoDb:
        async def execute(self, *_a, **_k):
            raise AssertionError("reached the database")

    with pytest.raises(ValueError):
        await store.record(_NoDb(), underlying, day, expiry, iv)


async def test_the_table_refuses_a_non_positive_iv_and_an_unknown_underlying(db):
    for sql in ("INSERT INTO public.daily_atm_iv (underlying, trading_day, expiry, atm_iv) "
                "VALUES ('NIFTY', '2026-11-09', '2026-11-11', 0)",
                "INSERT INTO public.daily_atm_iv (underlying, trading_day, expiry, atm_iv) "
                "VALUES ('BANKNIFTY', '2026-11-09', '2026-11-11', 0.1)"):
        with pytest.raises(DBAPIError, match="check"):
            async with db.begin_nested():
                await db.execute(text(sql))


async def test_read_since_unreadable_on_a_failed_read_or_a_non_decimal():
    class _Fails:
        async def execute(self, *_a, **_k):
            raise RuntimeError("down")

    class _Float:
        async def execute(self, *_a, **_k):
            return SimpleNamespace(all=lambda: [SimpleNamespace(trading_day=DAY, atm_iv=0.14)])

    with pytest.raises(store.DailyAtmIvUnreadable, match="RuntimeError"):
        await store.read_since(_Fails(), "NIFTY", DAY)
    with pytest.raises(store.DailyAtmIvUnreadable, match="not an exact Decimal"):
        await store.read_since(_Float(), "NIFTY", DAY)


async def test_round_trip_drops_and_restores_the_table_with_the_allowlist_passing(owner):
    own_down, own_up, down, up = round_trip_sql(MIGRATION)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    exists = text("SELECT to_regclass('public.daily_atm_iv') IS NOT NULL")
    assert (await owner.execute(exists)).scalar() is True
    for sql in down:  # ends with the allow-list post check against 0046's chain (no block 33)
        await owner.execute(text(sql))
    assert (await owner.execute(exists)).scalar() is False
    for sql in up:  # ends with the post check including block 33
        await owner.execute(text(sql))
    assert (await owner.execute(exists)).scalar() is True


async def test_allowlist_post_check_fails_when_the_app_role_may_update_daily_atm_iv(owner, app_engine):
    role = app_engine.url.username
    check = text(f"SELECT public.ofo_assert_app_role_allowlist('{role}', 'post')")
    await owner.execute(check)  # passes on the migrated database
    await owner.execute(text(f'GRANT UPDATE (atm_iv) ON public.daily_atm_iv TO "{role}"'))
    with pytest.raises(DBAPIError, match=r"has UPDATE on daily_atm_iv column atm_iv"):
        async with owner.begin_nested():
            await owner.execute(check)


async def test_downgrade_is_refused_with_a_count_while_rows_exist(owner):
    await store.record(owner, "NIFTY", DAY, EXPIRY, D("0.1432"))
    with pytest.raises(DBAPIError, match=r"refusing to downgrade 0047_daily_atm_iv: 1 stored daily ATM IVs"):
        async with owner.begin_nested():
            for sql in recorded(MIGRATION, "downgrade"):
                await owner.execute(text(sql))
