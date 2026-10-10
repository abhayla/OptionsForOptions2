"""W-067 AC-4 (REQ-051, ADR-067): the after-close job makes a day final from Kite's own candles, once.

Spec basis (quoted): REQ-051 AC-4 "Aggregated history is built from the live feed where practical and licensed (Q169)";
ADR-067 "After the close, each recorded day is made final" and "A day that could not be made final (no session, Kite
error) stays provisional and is named as such, never silently treated as final." ADR-066: Kite's candles are internal
use only.

Real input: the recorded 2026-10-08 frames replayed through the recorder into PostgreSQL, and Kite's recorded candles
(tests/fixtures/kite_history/candles-2026-10-08.json) parsed as Decimal from the body text. Expected values are those
candles, never the output of the code under test. Helpers and the clean-slate fixture come from test_history_pg_store.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "history"))

from _history_fixture import DAY, at, candle_bars
from test_history_pg_store import (GAP_MINUTES, _url, admin_sql, all_kite_candles, committed_day,  # noqa: F401
                                   replay_into)

from ofo.history.bars import BarSource
from ofo.history.candles import InMemoryCandleSource
from ofo.history.store import DayStatus, InMemoryHistoryStore
from ofo_app.history_finalize import FinalizeRefused, finalize_trading_day, main
from ofo_app.history_store import PostgresHistoryStore


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


def test_the_command_line_entry_refuses_before_the_close_with_exit_2(monkeypatch, capsys):
    for name, value in (("KITE_API_KEY", "example-key"), ("KITE_ACCESS_TOKEN", "example-token"),
                        ("DATABASE_URL", "postgresql+asyncpg://example@127.0.0.1:1/none")):
        monkeypatch.setenv(name, value)
    csv = ROOT / "tests" / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
    code = main(["--day", "2026-10-08", "--instruments-csv", str(csv)], now=at(11, 0))
    assert code == 2 and "refused" in capsys.readouterr().out
