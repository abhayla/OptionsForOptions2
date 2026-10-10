"""W-067 round 3, AC-4 (REQ-051, ADR-067): a successful after-close fetch makes the day final; a minute Kite has no candle
for keeps its live bar. There is no day-level completeness refusal.

Basis (quoted): ADR-067 decision "a minute Kite has no candle for keeps the live bar"; consequence "A day that could not
be made final (no session, Kite error) stays provisional and is named as such". Round 2 refused the whole day when
Kite's candles did not reach an instrument's last live minute, so one thin strike held the day provisional forever.
"""
import datetime
from decimal import Decimal

from _history_fixture import DAY, at

from ofo.history.bars import BarSource, MinuteBar
from ofo.history.candles import InMemoryCandleSource
from ofo.history.finalize import finalize_into
from ofo.history.store import DayStatus, InMemoryHistoryStore

OPEN, LAST = at(9, 15), at(15, 29)
START, END = at(9, 15), at(15, 59)


def bar(iid, minute, source, close="11"):
    return MinuteBar(iid, minute, Decimal("10"), Decimal("12"), Decimal("9"), Decimal(close), 5, 3, source)


def minutes(first, last):
    out, m = [], first
    while m <= last:
        out.append(m)
        m += datetime.timedelta(minutes=1)
    return out


def seeded(ids, until=LAST):
    store = InMemoryHistoryStore()
    store.put_bars([bar(i, m, BarSource.LIVE) for i in ids for m in minutes(OPEN, until)])
    return store


def run(store, kite, ids):
    return finalize_into(store, DAY, ids, InMemoryCandleSource(kite), start=START, end=END)


def test_a_thin_strike_whose_live_bar_is_one_minute_after_kites_last_candle_ends_final_with_the_live_bar_kept():
    ids = ["NSE_FO:1"]
    store = seeded(ids)  # live to 15:29; Kite's last candle is 15:28
    result = run(store, [bar("NSE_FO:1", m, BarSource.KITE, "12") for m in minutes(OPEN, at(15, 28))], ids)
    assert result.status is DayStatus.FINAL and store.day_status(DAY) is DayStatus.FINAL and result.errors == {}
    last = store.bars("NSE_FO:1", DAY)[-1]
    assert last.minute == at(15, 29) and last.source is BarSource.LIVE and last.close == Decimal("11")
    assert result.counts.kept_live == 1


def test_an_instrument_recorded_live_but_missing_from_the_instrument_list_keeps_its_live_bars_and_the_day_is_final():
    store = seeded(["NSE_FO:1", "NSE_FO:2"])
    result = run(store, [bar("NSE_FO:1", m, BarSource.KITE) for m in minutes(OPEN, LAST)], ["NSE_FO:1"])
    assert result.status is DayStatus.FINAL and result.errors == {}
    assert {b.source for b in store.bars("NSE_FO:2", DAY)} == {BarSource.LIVE}
    assert len(store.bars("NSE_FO:2", DAY)) == 375


def test_an_empty_kite_answer_for_an_instrument_with_live_bars_is_final_and_the_live_bars_stay():
    ids = ["NSE_FO:1"]
    store = seeded(ids)
    result = run(store, [], ids)
    assert result.status is DayStatus.FINAL and result.errors == {}
    assert {b.source for b in store.bars("NSE_FO:1", DAY)} == {BarSource.LIVE} and result.counts.kept_live == 375


class Raising:
    def minute_candles(self, instrument_id, start, end):
        raise TimeoutError("t")


def test_a_fetch_error_still_keeps_the_day_provisional_and_named():
    ids = ["NSE_FO:1"]
    store = seeded(ids)
    result = finalize_into(store, DAY, ids, Raising(), start=START, end=END)
    assert result.status is DayStatus.PROVISIONAL and result.errors == {"fetch_failed": 1}


def test_chunk_size_changes_nothing_about_the_result_only_the_number_of_batches():
    ids = ["NSE_FO:1", "NSE_FO:2", "NSE_FO:3"]
    results = {}
    for chunk in (1, 2, 50):
        store = seeded(ids)
        kite = [bar(i, m, BarSource.KITE) for i in ids for m in minutes(OPEN, LAST)]
        r = finalize_into(store, DAY, ids, InMemoryCandleSource(kite), start=START, end=END, chunk=chunk)
        results[chunk] = (r.status, r.counts, store.bars_for_day(DAY))
        assert len(r.batch_seconds) == -(-len(ids) // chunk)
    assert results[1] == results[2] == results[50] and results[1][1].replaced == 3 * 375
