"""W-067 AC-3 (REQ-051): the one-minute history tier lives in PostgreSQL and behaves exactly like the in-memory store.

Spec basis (quoted): REQ-051 AC-3 "Tiers: real-time, aggregated intraday (1-minute/5-minute), daily, strategy
snapshots"; AC-4 "Aggregated history is built from the live feed where practical and licensed (Q169)"; AC-5
"Historical data and simulation never block live strategy creation, Option Chain, execution or monitoring". ADR-067
(live first, final from Kite's candles), ADR-048 (the real test database and the limited ofo_app role).

Real input: tests/fixtures/kite_history/ - the two recorded 2026-10-08 windows (09:20-09:24, 15:06-15:12; 8 instruments,
the 15:08-15:10 network drop inside the second) replayed through the W-059 provider and the W-062 recorder.

The W-062 store contract (tests/history/test_store_contract.py) is imported and run unchanged against the PostgreSQL
store, each test inside a transaction that is rolled back. The core proof commits (a restart can only be proven by a
second engine, which sees only committed rows), so it empties the four history tables first and last through the owner
role (TRUNCATE: the application role cannot delete, and a final day cannot change). Database tests need
TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL (PostgreSQL 16); they skip locally unless OFO_REQUIRE_DB_TESTS=1.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "history"))

import test_store_contract as contract  # noqa: E402  (the W-062 contract, run here against PostgreSQL)
from _history_fixture import DAY, at, candle_bars, replay_window  # noqa: E402

from ofo.history.bars import BarSource, MinuteBar  # noqa: E402
from ofo.history.candles import InMemoryCandleSource  # noqa: E402
from ofo.history.recorder import Recorder  # noqa: E402
from ofo.history.store import DayStatus, InMemoryHistoryStore  # noqa: E402
from ofo_app.history_finalize import FinalizeRefused, finalize_trading_day  # noqa: E402
from ofo_app.history_store import PostgresHistoryStore  # noqa: E402

TABLES = ("history_minute_bars", "history_day_status", "history_feed_gaps", "history_gap_dropped")
GUARD_SQLSTATE = "OF009"
GAP_MINUTES = {at(15, 8), at(15, 9), at(15, 10)}  # the recorded network drop of the 15:06-15:12 window (F-34)


def _url(name: str) -> str:
    url = os.environ.get(name, "").strip()
    if not url:
        if os.environ.get("OFO_REQUIRE_DB_TESTS") == "1":
            pytest.fail(f"{name} is unset but OFO_REQUIRE_DB_TESTS=1")
        pytest.skip(f"{name} is unset: database tests need real PostgreSQL (ADR-048)")
    return url


def admin_sql(sql: str, params: dict | None = None, *, fetch: bool = False):
    async def run():
        engine = create_async_engine(_url("TEST_ADMIN_DATABASE_URL"), poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text(sql), params or {})
                return [tuple(r) for r in result.all()] if fetch else None
        finally:
            await engine.dispose()

    return asyncio.run(run())


def app_sql(sql: str, params: dict | None = None):
    """Run one statement as ofo_app in a transaction that is always rolled back; returns rows or raises."""
    async def run():
        engine = create_async_engine(_url("TEST_DATABASE_URL"), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                trans = await conn.begin()
                try:
                    result = await conn.execute(text(sql), params or {})
                    return [tuple(r) for r in result.all()] if result.returns_rows else result.rowcount
                finally:
                    await trans.rollback()
        finally:
            await engine.dispose()

    return asyncio.run(run())


def empty_tables() -> None:
    admin_sql("TRUNCATE " + ", ".join(f"public.{t}" for t in TABLES))


# ---- the W-062 contract, unchanged, against PostgreSQL ---------------------------------------------------------------
@pytest.fixture
def store():
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    pg.begin_isolated()
    try:
        yield pg
    finally:
        pg.rollback_isolated()
        pg.close()


for _name, _obj in list(vars(contract).items()):
    if _name.startswith("test_") or _name == "final":
        globals()[_name] = _obj  # collected here; `store` above replaces the contract's in-memory parameter


# ---- replay helpers ---------------------------------------------------------------------------------------------------
def replay_into(stores, windows) -> None:
    for window in windows:
        recorders: list[Recorder] = []

        def wire(fan, ids):
            fan.subscribe(lambda q: None, ids)  # the feed already carries the ids (the recorder never subscribes)
            for s in stores:
                r = Recorder(s)
                assert r.attach(fan, ids) == ids
                recorders.append(r)

        _, _, last = replay_window(window, wire)
        for r in recorders:
            r.flush(last + datetime.timedelta(minutes=1))
        assert all(r.counters["errors"] == 0 and r.counters["bars_lost"] == 0 for r in recorders)


def all_kite_candles() -> list[MinuteBar]:
    return [k for wins in candle_bars().values() for ks in wins.values() for k in ks]


@pytest.fixture
def committed_day():
    """A clean slate for the tests that commit (core proof, finalize); emptied again afterwards."""
    _url("TEST_ADMIN_DATABASE_URL")
    empty_tables()
    try:
        yield
    finally:
        empty_tables()


def test_core_recorded_frames_survive_an_engine_restart_and_equal_the_in_memory_store(committed_day):
    """CORE. The real 2026-10-08 frames -> recorder -> PostgreSQL as ofo_app; dispose the engine; a NEW engine reads
    every bar back exactly (Decimal, OI, source), and bar by bar it equals the in-memory store fed the same frames."""
    url = _url("TEST_DATABASE_URL")
    pg, mem = PostgresHistoryStore(url), InMemoryHistoryStore()
    replay_into([pg, mem], ["0920-0924", "1506-1512"])
    written = mem.bars_for_day(DAY)
    assert len(written) > 50 and {b.source for b in written} == {BarSource.LIVE}
    pg.close()  # the restart: the first engine and its connections are gone

    reborn = PostgresHistoryStore(url)
    try:
        read = reborn.bars_for_day(DAY)
        assert read == written  # dataclass equality: Decimal prices, volume, oi, source, minute (timezone-aware)
        assert all(isinstance(b.open, Decimal) for b in read)
        assert any(b.volume is None and b.oi is None for b in read)  # the two index rows carry neither
        assert reborn.gaps(DAY) == mem.gaps(DAY) and reborn.gaps(DAY) != []
        assert reborn.gap_minutes_missing(DAY) == mem.gap_minutes_missing(DAY)
        assert reborn.day_status(DAY) is DayStatus.PROVISIONAL
        for iid in candle_bars():
            assert reborn.bars(iid, DAY) == mem.bars(iid, DAY)
    finally:
        reborn.close()


def test_columns_are_exact_decimal_and_whole_numbers_never_float():
    rows = admin_sql("SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
                     "FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ANY(:t)",
                     {"t": list(TABLES)}, fetch=True)
    by = {(t, c): (d, p, s) for t, c, d, p, s in rows}
    for c in ("open", "high", "low", "close"):
        assert by[("history_minute_bars", c)] == ("numeric", 14, 2)
    assert by[("history_minute_bars", "volume")][0] == "bigint" and by[("history_minute_bars", "oi")][0] == "bigint"
    assert not [k for k, v in by.items() if v[0] in ("double precision", "real")]


def test_a_price_finer_than_a_paisa_is_refused_not_silently_rounded(store):
    fine = MinuteBar("X:1", at(11, 0), Decimal("1.005"), Decimal("1.005"), Decimal("1.005"), Decimal("1.005"), 1, 1,
                     BarSource.LIVE)
    with pytest.raises(ValueError, match="paisa"):
        store.put_bars([fine])
    assert store.bars_for_day(DAY) == []
    with pytest.raises(ValueError):  # and a float never gets as far as the store (MinuteBar refuses it)
        MinuteBar("X:1", at(11, 0), 1.5, 1.5, 1.5, 1.5, 1, 1, BarSource.LIVE)


# ---- the finalize job on Kite's real candles --------------------------------------------------------------------------
def test_finalize_makes_every_minute_kites_candle_and_a_second_run_changes_nothing(committed_day):
    url = _url("TEST_DATABASE_URL")
    pg, mem = PostgresHistoryStore(url), InMemoryHistoryStore()
    replay_into([pg, mem], ["0920-0924", "1506-1512"])
    kite = all_kite_candles()
    source, ids = InMemoryCandleSource(kite), list(candle_bars())

    result = finalize_trading_day(pg, DAY, source, ids, now=at(15, 45))
    finalize_trading_day(mem, DAY, InMemoryCandleSource(kite), ids, now=at(15, 45))
    assert result.status is DayStatus.FINAL and pg.day_status(DAY) is DayStatus.FINAL
    by = {(b.instrument_id, b.minute): b for b in pg.bars_for_day(DAY)}
    for k in kite:  # expected values are Kite's recorded candles, parsed from the fixture text
        got = by[(k.instrument_id, k.minute)]
        assert (got.open, got.high, got.low, got.close, got.volume, got.oi) == \
               (k.open, k.high, k.low, k.close, k.volume, k.oi)
        assert got.source is (BarSource.BACKFILLED if k.minute in GAP_MINUTES else BarSource.KITE)
    assert {k.instrument_id for k in kite if k.minute == at(15, 9)} == set(ids)  # the 15:09 gap minute, all 8, from Kite
    assert pg.bars_for_day(DAY) == mem.bars_for_day(DAY)  # the same results the in-memory store gives
    assert pg.gap_minutes_missing(DAY) == mem.gap_minutes_missing(DAY)

    marks = "SELECT instrument_id, minute, xmin::text FROM public.history_minute_bars ORDER BY 1, 2"
    before, calls = admin_sql(marks, fetch=True), source.calls
    again = finalize_trading_day(pg, DAY, source, ids, now=at(16, 5))
    assert again.status is DayStatus.FINAL and again.counts is None
    assert admin_sql(marks, fetch=True) == before  # 0 rows changed: not one row version was rewritten
    assert source.calls == calls  # and Kite was not asked again
    pg.close()


def test_finalize_refuses_before_the_session_has_closed(committed_day):
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    source = InMemoryCandleSource(all_kite_candles())
    try:
        for now in (at(11, 0), at(15, 29, 59), at(15, 30)):
            with pytest.raises(FinalizeRefused):
                finalize_trading_day(pg, DAY, source, list(candle_bars()), now=now)
        assert source.calls == 0 and pg.day_status(DAY) is DayStatus.PROVISIONAL
        with pytest.raises(FinalizeRefused):  # a day that has not started yet
            finalize_trading_day(pg, DAY + datetime.timedelta(days=1), source, [], now=at(15, 45))
    finally:
        pg.close()


# ---- the database itself refuses what the store would never do --------------------------------------------------------
def test_the_database_refuses_any_change_to_a_final_day_as_the_application_role(committed_day):
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    replay_into([pg], ["1506-1512"])
    finalize_trading_day(pg, DAY, InMemoryCandleSource(all_kite_candles()), list(candle_bars()), now=at(15, 45))
    pg.close()
    iid, minute = admin_sql("SELECT instrument_id, minute FROM public.history_minute_bars LIMIT 1", fetch=True)[0]
    refused = [
        "UPDATE public.history_minute_bars SET close = high WHERE instrument_id = :i AND minute = :m",
        "UPDATE public.history_minute_bars SET removed = TRUE WHERE instrument_id = :i AND minute = :m",
        "INSERT INTO public.history_minute_bars (instrument_id, minute, trade_date, open, high, low, close, volume, "
        "oi, source, removed) VALUES ('Z:9', :m, '2026-10-08', 1, 1, 1, 1, 1, 1, 'live', FALSE)",
        "UPDATE public.history_day_status SET status = 'provisional' WHERE trade_date = '2026-10-08'",
        "INSERT INTO public.history_feed_gaps (gap_start, gap_end, trade_date) VALUES (:m, :m + interval '9 seconds', "
        "'2026-10-08')",
    ]
    for sql in refused:
        with pytest.raises(DBAPIError) as err:
            app_sql(sql, {"i": iid, "m": minute})
        assert GUARD_SQLSTATE in repr(err.value.orig), sql
    for sql in ("DELETE FROM public.history_minute_bars", "TRUNCATE public.history_minute_bars",
                "DELETE FROM public.history_day_status", "DELETE FROM public.history_feed_gaps"):
        with pytest.raises(DBAPIError, match="permission denied"):
            app_sql(sql)


def test_the_database_never_lowers_a_bars_source_even_on_a_provisional_day(committed_day):
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    k = MinuteBar("X:1", at(12, 0), Decimal("2"), Decimal("2"), Decimal("2"), Decimal("2"), 1, 1, BarSource.KITE)
    pg.put_bars([k])
    pg.close()
    with pytest.raises(DBAPIError) as err:
        app_sql("UPDATE public.history_minute_bars SET source = 'live' WHERE instrument_id = 'X:1'")
    assert GUARD_SQLSTATE in repr(err.value.orig)


def test_grants_the_application_role_holds_on_the_history_tables():
    for table in TABLES:
        rows = app_sql("SELECT has_table_privilege(current_user, :t, p) FROM unnest(ARRAY['DELETE','TRUNCATE',"
                       "'REFERENCES','TRIGGER']) AS p", {"t": f"public.{table}"})
        assert [r[0] for r in rows] == [False] * 4, table
    update = app_sql("SELECT attname FROM pg_attribute WHERE attrelid = 'public.history_minute_bars'::regclass "
                     "AND attnum > 0 AND NOT attisdropped AND has_column_privilege(current_user, "
                     "'public.history_minute_bars', attname, 'UPDATE') ORDER BY 1")
    assert [r[0] for r in update] == ["close", "high", "low", "oi", "open", "removed", "source", "volume"]


# ---- AC-5: a failing store never reaches the feed ---------------------------------------------------------------------
def test_a_store_that_cannot_reach_the_database_never_disturbs_the_feed():
    user = "nobody"
    dead = PostgresHistoryStore(f"postgresql+asyncpg://{user}@127.0.0.1:1/none")  # connection refused
    delivered_with, delivered_without = [], []
    holder = {}

    def wire(fan, ids):
        fan.subscribe(delivered_with.append, ids)
        holder["rec"] = Recorder(dead)
        holder["rec"].attach(fan, ids)

    _, fan, last = replay_window("1506-1512", wire)
    holder["rec"].flush(last + datetime.timedelta(minutes=1))
    replay_window("1506-1512", lambda fan, ids: fan.subscribe(delivered_without.append, ids))
    dead.close()
    assert len(delivered_with) == len(delivered_without) > 1000
    assert holder["rec"].counters["errors"] > 0 and holder["rec"].counters["bars_lost"] > 0
    assert fan.listener_errors == 0


# ---- the migration ----------------------------------------------------------------------------------------------------
def _recorded(phase: str, tag: str) -> list[str]:
    import importlib.util
    from types import SimpleNamespace

    path = ROOT / "backend" / "ofo_app" / "alembic" / "versions" / "0009_minute_history.py"
    found = importlib.util.spec_from_file_location(f"ofo_migration_0009_{tag}", path)
    migration = importlib.util.module_from_spec(found)
    found.loader.exec_module(migration)  # type: ignore[union-attr]
    out: list[str] = []
    migration.op = SimpleNamespace(execute=lambda sql, *a, **k: out.append(str(sql)))
    migration._BASE._app_role = lambda: "ofo_app"
    getattr(migration, phase)()
    return out


def test_downgrade_then_upgrade_round_trips_and_downgrade_refuses_while_bars_exist():
    admin_url = _url("TEST_ADMIN_DATABASE_URL")
    down, up = _recorded("downgrade", "down"), _recorded("upgrade", "up")
    assert "'pre'" in up[0] and "'post'" in up[-1] and "'post'" in down[-1]

    async def run():
        engine = create_async_engine(admin_url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                trans = await conn.begin()  # DDL is transactional: everything below is rolled back
                try:
                    await conn.execute(text("TRUNCATE " + ", ".join(f"public.{t}" for t in TABLES)))
                    for sql in down:
                        await conn.execute(text(sql))
                    gone = await conn.scalar(text("SELECT count(*) FROM pg_class WHERE relname = ANY(:t)"),
                                             {"t": list(TABLES)})
                    assert gone == 0
                    for sql in up:
                        await conn.execute(text(sql))
                    back = await conn.scalar(text("SELECT count(*) FROM pg_class WHERE relname = ANY(:t) "
                                                  "AND relkind = 'r'"), {"t": list(TABLES)})
                    assert back == 4
                    await conn.execute(text(
                        "INSERT INTO public.history_minute_bars (instrument_id, minute, trade_date, open, high, "
                        "low, close, volume, oi, source, removed) VALUES ('X:1', '2026-10-08 10:00+05:30', "
                        "'2026-10-08', 1, 1, 1, 1, 1, 1, 'live', FALSE)"))
                    with pytest.raises(DBAPIError, match="refusing to downgrade 0009_minute_history"):
                        async with conn.begin_nested():
                            for sql in down:
                                await conn.execute(text(sql))
                finally:
                    await trans.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())
