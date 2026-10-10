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


def test_finalize_of_a_full_day_is_set_based_and_finishes_within_the_bound(committed_day, capsys):
    seed_live(N)
    ids = [iid(i) for i in range(1, N + 1)]
    pg, source = PostgresHistoryStore(_url("TEST_DATABASE_URL")), GeneratedCandles()
    try:
        started = time.perf_counter()
        result = finalize_trading_day(pg, DAY, source, ids, now=at(16, 5))
        elapsed = time.perf_counter() - started
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
