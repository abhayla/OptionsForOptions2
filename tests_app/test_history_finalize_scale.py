"""W-067 round 2, AC-4 (REQ-051): finalize of a full trading day completes within a bounded time.

Spec basis (quoted): REQ-051 AC-4 "Aggregated history is built from the live feed where practical and licensed
(Q169)"; ADR-067 "After the close, each recorded day is made final". Scale (F-33): about 1,603 instruments x 375
session minutes = 601,125 one-minute bars in a day. Round 1 looked each bar up by a named-key list that planned as a
full scan with a nested loop: 240 instruments did not finish in 480 s.

Size and bound come from the environment so the SAME test runs small on a developer PC and at full size in CI:
  OFO_HISTORY_SCALE_INSTRUMENTS  instruments to finalize (default 40; CI sets 1603)
  OFO_HISTORY_SCALE_BOUND_S      seconds the whole finalize may take (default 90; CI: 600, see app-tests.yml)
  OFO_HISTORY_SCALE_BATCH_BOUND_S  seconds ONE batch (50 instruments, one transaction) may take (default 20; CI: 45);
                                 a batch whose cost grows with the table (a scan per lookup) fails this first
This PC's PostgreSQL also serves a production system (owner decision 2026-10-09): never run the full size here.

Real input: none exists at this size (the recordings hold 8 instruments), so the bars are synthetic but valid: every
instrument has a LIVE bar for each of the 375 minutes of 2026-10-08 (09:15-15:29 IST) and Kite's candle for the same
minute differs from it (the worst case: every live bar is replaced). The 8-instrument real-recording behaviour is
proven in test_history_finalize_job.py.
"""
from __future__ import annotations

# ruff: noqa  # DIAG-344 branch only (never merged)
import datetime
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "history"))

from _history_fixture import DAY, at  # noqa: E402
from test_history_pg_store import _url, admin_sql, committed_day  # noqa: E402,F401

from ofo.history.bars import BarSource, MinuteBar  # noqa: E402
from ofo_app.history_finalize import finalize_trading_day  # noqa: E402
from ofo_app.history_store import PostgresHistoryStore  # noqa: E402

N = int(os.environ.get("OFO_HISTORY_SCALE_INSTRUMENTS", "40"))
BOUND_S = float(os.environ.get("OFO_HISTORY_SCALE_BOUND_S", "90"))
BATCH_BOUND_S = float(os.environ.get("OFO_HISTORY_SCALE_BATCH_BOUND_S", "20"))
MINUTES = 375
FIRST = at(9, 15)


def iid(i: int) -> str:
    return f"NSE_FO:{100000 + i}"


class GeneratedCandles:
    """Kite's answer for any instrument: 375 valid candles, built on request (not held in memory for the whole day)."""

    def __init__(self) -> None:
        self.calls = 0

    def minute_candles(self, instrument_id: str, start, end) -> list[MinuteBar]:
        self.calls += 1
        k = int(instrument_id.rsplit(":", 1)[1]) % 50
        return [MinuteBar(instrument_id, FIRST + datetime.timedelta(minutes=m), Decimal(100 + k) + Decimal("0.05"),
                          Decimal(102 + k), Decimal(99 + k), Decimal(101 + k), 7 + m, 3, BarSource.KITE)
                for m in range(MINUTES)]


def seed_live(n: int) -> None:
    admin_sql(
        "INSERT INTO public.history_minute_bars (instrument_id, minute, trade_date, open, high, low, close, volume, "
        "oi, source, removed) SELECT 'NSE_FO:' || (100000 + i), t.ts, '2026-10-08', 100 + (i % 50), 101 + (i % 50), "
        "99 + (i % 50), 100.50 + (i % 50), 5, 3, 'live', FALSE FROM generate_series(1, :n) AS i, "
        "generate_series(0, :m) AS m, LATERAL (SELECT timestamptz '2026-10-08 09:15+05:30' + m * interval '1 minute' "
        "AS ts) AS t", {"n": n, "m": MINUTES - 1})
    # no ANALYZE here on purpose: a day's rows arrive all day and the job runs before statistics catch up


class _Diag:  # DIAG-344 (temporary, branch diag/scale-flake only)
    def __init__(self) -> None:
        import collections
        import threading
        self.threading = threading
        self.events = collections.Counter()
        self.ev_by_thread = collections.Counter()
        self.on = False
        self.stop = threading.Event()
        self.db: list = []
        self.stacks = collections.Counter()
        self.t0 = time.perf_counter()
        sys.addaudithook(self._hook)

    def _hook(self, event, args):
        if self.on:
            self.events[event] += 1
            self.ev_by_thread[self.threading.current_thread().name] += 1

    def _db(self):
        import asyncpg
        url = _url("TEST_ADMIN_DATABASE_URL").replace("postgresql+asyncpg", "postgresql")

        async def run():
            conn = await asyncpg.connect(url)
            try:
                while not self.stop.is_set():
                    t = round(time.perf_counter() - self.t0, 1)
                    act = await conn.fetch(
                        "SELECT pid, backend_type, state, wait_event_type, wait_event, "
                        "round(extract(epoch FROM now() - query_start)::numeric, 1) AS age, left(query, 60) AS q "
                        "FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND (state IS DISTINCT FROM 'idle')")
                    vac = await conn.fetch("SELECT pid, relid::regclass::text, phase, heap_blks_scanned, "
                                           "heap_blks_total FROM pg_stat_progress_vacuum")
                    locks = await conn.fetch("SELECT pid, locktype, mode, objid FROM pg_locks WHERE NOT granted")
                    st = await conn.fetch(
                        "SELECT s.n_live_tup, s.n_dead_tup, s.n_mod_since_analyze, s.last_autoanalyze IS NOT NULL, "
                        "s.autoanalyze_count, s.autovacuum_count, c.reltuples, c.relpages, "
                        "(SELECT count(*) FROM pg_stats WHERE tablename = 'history_minute_bars') "
                        "FROM pg_stat_user_tables s JOIN pg_class c ON c.oid = s.relid "
                        "WHERE s.relname = 'history_minute_bars'")
                    act = [*act, ("STATS", *tuple(st[0]))] if st else act
                    if int(t) % 3 == 0:
                        for name, sql in (
                            ("SLICE", "SELECT b.instrument_id FROM unnest(CAST($1 AS text[]), CAST($2 AS timestamptz[])) "
                                      "AS k(i, m) JOIN public.history_minute_bars AS b ON b.instrument_id = k.i "
                                      "AND b.minute = k.m WHERE NOT b.removed"),
                            ("KEPT", "SELECT count(*) FROM public.history_minute_bars WHERE trade_date = $1 "
                                     "AND source = 'live' AND NOT removed")):
                            try:
                                plan = await conn.fetch(f"EXPLAIN (GENERIC_PLAN) {sql}")
                                act = [*act, (f"GENERIC-{name}", " | ".join(r[0].strip()[:90] for r in plan[:4]))]
                            except Exception as exc:  # noqa: BLE001
                                act = [*act, (f"GENERIC-{name}", repr(exc)[:120])]
                    load = open("/proc/loadavg").read().strip() if os.path.exists("/proc/loadavg") else "-"
                    self.db.append((t, [tuple(r) for r in act], [tuple(r) for r in vac],
                                    [tuple(r) for r in locks], load, self._threads_cpu()))
                    await asyncio.sleep(1.0)
            finally:
                await conn.close()

        import asyncio
        try:
            asyncio.run(run())
        except Exception as exc:  # noqa: BLE001
            self.db.append(("watch error", repr(exc)))

    def _threads_cpu(self):
        out = {}
        for th in self.threading.enumerate():
            try:
                out[th.name[:28]] = round(time.clock_gettime(time.pthread_getcpuclockid(th.ident)), 2)
            except Exception:  # noqa: BLE001
                out[th.name[:28]] = None
        return out

    def _sampler(self):
        main = self.threading.main_thread().ident
        while not self.stop.wait(0.05):
            frames = sys._current_frames()
            for th in self.threading.enumerate():
                if th.ident in (self.threading.get_ident(),):
                    continue
                f = frames.get(th.ident)
                if f is None:
                    continue
                parts = []
                while f is not None and len(parts) < 3:
                    parts.append(f"{os.path.basename(f.f_code.co_filename)}:{f.f_code.co_name}:{f.f_lineno}")
                    f = f.f_back
                tag = "MAIN" if th.ident == main else th.name[:20]
                self.stacks[(tag, " < ".join(parts))] += 1

    def start(self):
        self.on = True
        for target in (self._db, self._sampler):
            self.threading.Thread(target=target, daemon=True, name=f"diag-{target.__name__}").start()

    def dump(self, line):
        self.stop.set()
        time.sleep(1.5)
        self.on = False
        out = [f"DIAG344 {line}", f"DIAG344 threads={[t.name for t in self.threading.enumerate()]}",
               f"DIAG344 events_total={sum(self.events.values())} top={self.events.most_common(25)}",
               f"DIAG344 events_by_thread={self.ev_by_thread.most_common(15)}"]
        for row in self.db:
            out.append(f"DIAG344 db {row}")
        for (tag, st), n in self.stacks.most_common(60):
            out.append(f"DIAG344 stack {n:5d} {tag} {st}")
        print("\n" + "\n".join(out), flush=True)


def test_finalize_of_a_full_day_is_set_based_and_finishes_within_the_bound(committed_day, capsys):
    diag = _Diag()
    with capsys.disabled():
        print(f"\nDIAG344 before threads={[t.name for t in diag.threading.enumerate()]} "
              f"load={open('/proc/loadavg').read().strip() if os.path.exists('/proc/loadavg') else '-'} "
              f"cpu={os.times()}", flush=True)
    seed_live(N)
    ids = [iid(i) for i in range(1, N + 1)]
    pg, source = PostgresHistoryStore(_url("TEST_DATABASE_URL")), GeneratedCandles()
    try:
        diag.start()
        cpu0 = os.times()
        started = time.perf_counter()
        result = finalize_trading_day(pg, DAY, source, ids, now=at(16, 5))
        elapsed = time.perf_counter() - started
        cpu1 = os.times()

        async def _prepared():
            from sqlalchemy import text as _t
            out = []
            for _ in range(2):  # pool_size 2: try to see both pooled connections
                async with pg._engine_().connect() as c:
                    rows = await c.execute(_t(
                        "SELECT pg_backend_pid(), generic_plans, custom_plans, left(regexp_replace(statement, "
                        "'\\s+', ' ', 'g'), 70) FROM pg_prepared_statements ORDER BY generic_plans + custom_plans DESC"))
                    out.append([tuple(r) for r in rows][:8])
            return out

        try:
            prepared = pg._run(_prepared())
        except Exception as exc:  # noqa: BLE001
            prepared = repr(exc)
        with capsys.disabled():
            print(f"\nDIAG344 prepared={prepared}", flush=True)
            diag.dump(f"elapsed={elapsed:.1f} batches={[round(s, 2) for s in result.batch_seconds]} "
                      f"errors={result.errors} proc_user={cpu1.user - cpu0.user:.1f} "
                      f"proc_sys={cpu1.system - cpu0.system:.1f}")
        batches = result.batch_seconds
        line = (f"SCALE instruments={N} bars={N * MINUTES} total={elapsed:.1f}s batches={len(batches)} "
                f"per_batch_max={max(batches):.2f}s per_batch_mean={sum(batches) / len(batches):.2f}s")
        with capsys.disabled():  # real stdout: the CI log shows it on a pass too, with or without -s
            print(f"\n{line}", flush=True)
        assert result.status.value == "final" and result.errors == {}
        assert result.counts.replaced == N * MINUTES and result.counts.kept_live == 0
        assert max(batches) < BATCH_BOUND_S, f"{line} - one batch exceeded {BATCH_BOUND_S} s"
        assert elapsed < BOUND_S, f"{line} - total exceeded {BOUND_S} s"
        rows = admin_sql("SELECT source, count(*) FROM public.history_minute_bars GROUP BY 1", fetch=True)
        assert rows == [("kite", N * MINUTES)]
        assert source.calls == N
    finally:
        pg.close()


class FailsAfter(GeneratedCandles):
    """Kite answers the first ``ok`` instruments and then a timeout (a fetch error: the day stays provisional)."""

    def __init__(self, ok: int) -> None:
        super().__init__()
        self.ok = ok

    def minute_candles(self, instrument_id: str, start, end) -> list[MinuteBar]:
        if self.calls >= self.ok:
            self.calls += 1
            raise TimeoutError("t")
        return super().minute_candles(instrument_id, start, end)


def test_finalize_is_resumable_and_a_rerun_rewrites_nothing_already_made_final(committed_day):
    """A run whose fetch fails part-way leaves the day provisional; the next run finishes it and touches only the rows
    still LIVE (not one KITE row version is rewritten)."""
    n = min(N, 12)
    seed_live(n)
    ids = [iid(i) for i in range(1, n + 1)]
    pg = PostgresHistoryStore(_url("TEST_DATABASE_URL"))
    try:
        first = finalize_trading_day(pg, DAY, FailsAfter(n // 2), ids, now=at(16, 5), chunk=3)
        assert first.status.value == "provisional" and first.errors == {"fetch_failed": n - n // 2}
        marks = ("SELECT instrument_id, minute, xmin::text FROM public.history_minute_bars WHERE source = 'kite' "
                 "ORDER BY 1, 2")
        done = admin_sql(marks, fetch=True)
        assert len(done) == (n // 2) * MINUTES
        second = finalize_trading_day(pg, DAY, GeneratedCandles(), ids, now=at(16, 10), chunk=3)
        assert second.status.value == "final"
        after = {(i, m): x for i, m, x in admin_sql(marks, fetch=True)}
        assert len(after) == n * MINUTES
        assert all(after[(i, m)] == x for i, m, x in done)  # the first run's rows are the same row versions
    finally:
        pg.close()


# ---- DIAG-344 deterministic reproduction (temporary) -------------------------------------------------------------
def _seed_with_analyze_during_insert(n: int):
    """The failing runs' state: an ANALYZE that ran while the seed INSERT was still uncommitted (reltuples=0,
    relpages>0, no pg_stats rows)."""
    import asyncio
    import asyncpg
    url = _url("TEST_ADMIN_DATABASE_URL").replace("postgresql+asyncpg", "postgresql")
    sql = ("INSERT INTO public.history_minute_bars (instrument_id, minute, trade_date, open, high, low, close, volume, "
           "oi, source, removed) SELECT 'NSE_FO:' || (100000 + i), t.ts, '2026-10-08', 100 + (i % 50), 101 + (i % 50), "
           "99 + (i % 50), 100.50 + (i % 50), 5, 3, 'live', FALSE FROM generate_series(1, %d) AS i, "
           "generate_series(0, %d) AS m, LATERAL (SELECT timestamptz '2026-10-08 09:15+05:30' + m * interval '1 minute' "
           "AS ts) AS t" % (n, MINUTES - 1))

    async def run():
        a, b = await asyncpg.connect(url), await asyncpg.connect(url)
        try:
            tr = a.transaction()
            await tr.start()
            await a.execute(sql)
            await b.execute("ANALYZE public.history_minute_bars")
            await tr.commit()
            st = await b.fetchrow("SELECT reltuples, relpages, (SELECT count(*) FROM pg_stats WHERE "
                                  "tablename = 'history_minute_bars') FROM pg_class WHERE relname = 'history_minute_bars'")
            await b.execute("PREPARE s344(text[], timestamptz[]) AS SELECT b.instrument_id FROM unnest($1, $2) AS "
                            "k(i, m) JOIN public.history_minute_bars AS b ON b.instrument_id = k.i AND b.minute = k.m "
                            "WHERE NOT b.removed")
            plans = {}
            for mode in ("force_custom_plan", "force_generic_plan"):
                await b.execute(f"SET plan_cache_mode = {mode}")
                rows = await b.fetch("EXPLAIN EXECUTE s344(array_fill('NSE_FO:100001'::text, ARRAY[18750]), "
                                     "array_fill(timestamptz '2026-10-08 09:15+05:30', ARRAY[18750]))")
                plans[mode] = " | ".join(r[0].strip()[:80] for r in rows[:5])
            return tuple(st), plans
        finally:
            await a.close()
            await b.close()

    return asyncio.run(run())


class _CustomPlanStore(PostgresHistoryStore):
    def _engine_(self):
        if self._engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine
            self._engine = create_async_engine(
                self._url, pool_size=2, max_overflow=2, pool_pre_ping=True,
                connect_args={"timeout": 5, "command_timeout": 15,
                              "server_settings": {"jit": "off", "plan_cache_mode": "force_custom_plan"}})
        return self._engine


@pytest.mark.parametrize("store_cls", [PostgresHistoryStore, _CustomPlanStore], ids=["as-is", "force-custom"])
def test_diag344_repro(committed_day, capsys, store_cls):
    state, plans = _seed_with_analyze_during_insert(N)
    ids = [iid(i) for i in range(1, N + 1)]
    pg = store_cls(_url("TEST_DATABASE_URL"))
    try:
        started = time.perf_counter()
        result = finalize_trading_day(pg, DAY, GeneratedCandles(), ids, now=at(16, 5))
        elapsed = time.perf_counter() - started
        with capsys.disabled():
            print(f"\nDIAG344 REPRO {store_cls.__name__} state(reltuples,relpages,pg_stats)={state} "
                  f"elapsed={elapsed:.1f} errors={result.errors} "
                  f"batches={[round(s, 2) for s in result.batch_seconds][:8]}"
                  f"\nDIAG344 REPRO plans={plans}", flush=True)
    finally:
        pg.close()
