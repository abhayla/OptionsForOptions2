"""W-062 AC-4 (REQ-051, ADR-067): a day is made final from Kite's candles, a feed gap is filled and marked backfilled."""
import datetime
from decimal import Decimal

import pytest
from _history_fixture import DAY, at, candle_bars
from test_minute_bars_replay import NIFTY_CE, build

from ofo.history.bars import BarSource, MinuteBar
from ofo.history.candles import CandleError, InMemoryCandleSource, parse_candles
from ofo.history.finalize import FinalizeCounts, daily_bar, fill_gaps, finalize_day, finalize_into, five_minute
from ofo.history.store import DayStatus, InMemoryHistoryStore

W = "1506-1512"


def kite_all(window: str) -> list[MinuteBar]:
    return [k for wins in candle_bars().values() for k in wins[window]]


def test_finalize_makes_every_minute_kites_candle_exactly_with_source_kite():
    for window in ("0920-0924", W):
        _, live = build(window)
        kite = kite_all(window)
        final, counts = finalize_day(live, kite)
        by = {(b.instrument_id, b.minute): b for b in final}
        for k in kite:
            got = by[(k.instrument_id, k.minute)]
            assert (got.open, got.high, got.low, got.close, got.volume, got.oi) == \
                   (k.open, k.high, k.low, k.close, k.volume, k.oi)
            assert got.source is BarSource.KITE
        assert counts.replaced + counts.kite_only == len(kite)
        assert counts.replaced > 0 and counts.replaced + counts.kept_live + counts.kite_only == len(final)


def test_a_minute_only_the_live_feed_has_stays_live():
    live = [MinuteBar("X:1", at(9, 20), Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), 5, 7, BarSource.LIVE)]
    final, counts = finalize_day(live, [])
    assert [b.source for b in final] == [BarSource.LIVE] and counts == FinalizeCounts(0, 1, 0)


def test_gap_fill_marks_the_lost_minutes_backfilled_and_replaces_the_stale_one():
    builder, live = build(W)
    kite = kite_all(W)
    live_1508 = {b.instrument_id: b for b in live if b.minute == at(15, 8)}
    assert live_1508[NIFTY_CE].close != Decimal("38.35")  # the stale close of F-34: Kite's 15:08 close is 38.35
    filled = fill_gaps(live, kite, builder.gaps)
    by = {(b.instrument_id, b.minute): b for b in filled}
    kite_by = {(k.instrument_id, k.minute): k for k in kite}
    for iid in candle_bars():
        for minute in (at(15, 8), at(15, 9), at(15, 10)):
            got, k = by[(iid, minute)], kite_by[(iid, minute)]
            assert got.source is BarSource.BACKFILLED
            assert (got.open, got.high, got.low, got.close, got.volume, got.oi) == \
                   (k.open, k.high, k.low, k.close, k.volume, k.oi)
        # a minute outside the gap is untouched and still provisional
        assert by[(iid, at(15, 7))].source is BarSource.LIVE
    nifty_1509 = by[(NIFTY_CE, at(15, 9))]
    assert (nifty_1509.close, nifty_1509.volume, nifty_1509.oi) == (Decimal("38.3"), 132925, 5721170)
    assert not any(b.source is BarSource.LIVE and b.minute in (at(15, 8), at(15, 9)) for b in filled)


def test_gap_minute_kite_lacks_is_dropped_not_kept_as_live():
    live = [MinuteBar("X:1", at(15, 8), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1, 1, BarSource.LIVE)]
    assert fill_gaps(live, [], [(at(15, 8, 14), at(15, 10, 8))]) == []


def test_five_minute_and_daily_are_derived_on_demand_from_one_minute_bars():
    def bar(m, o, h, l, c, v, oi, src=BarSource.KITE):
        return MinuteBar("X:1", at(9, m), Decimal(o), Decimal(h), Decimal(l), Decimal(c), v, oi, src)

    bars = [bar(15, "10", "12", "9", "11", 100, 1000), bar(16, "11", "15", "10", "14", 50, 1010),
            bar(19, "14", "14", "8", "9", 25, 1020), bar(20, "9", "9.5", "9", "9.5", 10, 1030, BarSource.LIVE)]
    five = five_minute(bars)
    assert [(p.start, p.minutes) for p in five] == [(at(9, 15), 3), (at(9, 20), 1)]
    first = five[0]
    assert (first.open, first.high, first.low, first.close, first.volume, first.oi) == \
           (Decimal("10"), Decimal("15"), Decimal("8"), Decimal("9"), 175, 1020)
    assert first.source is BarSource.KITE and five[1].source is BarSource.LIVE
    day = daily_bar(bars)
    assert (day.open, day.high, day.low, day.close, day.volume, day.oi) == \
           (Decimal("10"), Decimal("15"), Decimal("8"), Decimal("9.5"), 185, 1030)
    assert day.source is BarSource.LIVE  # one provisional minute keeps the whole day provisional


def test_kite_body_parses_from_text_as_decimal_and_malformed_bodies_are_refused():
    body = '{"status":"success","data":{"candles":[["2026-10-08T09:20:00+0530",1.95,2,1.9,2.0,478640,1966980]]}}'
    (bar,) = parse_candles(body, "X:1")
    assert bar.open == Decimal("1.95") and bar.close == Decimal("2.0") and isinstance(bar.close, Decimal)
    assert bar.minute == at(9, 20) and bar.source is BarSource.KITE and (bar.volume, bar.oi) == (478640, 1966980)
    for bad in ("not json", '{"status":"error"}', '{"status":"success","data":{}}',
                '{"status":"success","data":{"candles":[["2026-10-08T09:20:00+0530",1,2]]}}',
                '{"status":"success","data":{"candles":[["2026-10-08T09:20:00+0530","x",2,1,2,1,1]]}}'):
        with pytest.raises(CandleError):
            parse_candles(bad, "X:1")


# ---- every answer state of the candle fetch (standing item d) --------------------------------------------------------
class Raising:
    def __init__(self, exc):
        self.exc = exc

    def minute_candles(self, instrument_id, start, end):
        raise self.exc


def _seeded_store():
    _, live = build(W)
    store = InMemoryHistoryStore()
    store.put_bars(live)
    return store


START, END = at(15, 5), at(15, 12)


def assert_kite_up_to_1511(store):
    # Kite's fixture ends at 15:11; the live 15:12 bar has no candle to replace it and stays provisional
    bars = store.bars(NIFTY_CE, DAY)
    assert all(b.source is BarSource.KITE for b in bars if b.minute <= at(15, 11))
    assert [b.source for b in bars if b.minute > at(15, 11)] == [BarSource.LIVE]


def test_candles_returned_makes_the_day_final():
    store = _seeded_store()
    source = InMemoryCandleSource(kite_all(W))
    result = finalize_into(store, DAY, list(candle_bars()), source, start=START, end=END)
    assert result.status is DayStatus.FINAL and store.day_status(DAY) is DayStatus.FINAL
    assert_kite_up_to_1511(store)
    assert result.errors == {}


def test_empty_list_for_an_instrument_with_no_live_bars_is_final_but_not_for_one_the_feed_traded():
    """W-067 r2: an empty answer means "no trades" only where the feed saw none; an instrument whose live bars exist
    must have candles reaching them, or the answer is incomplete and the day stays provisional (retryable)."""
    store = InMemoryHistoryStore()
    result = finalize_into(store, DAY, list(candle_bars()), InMemoryCandleSource([]), start=START, end=END)
    assert result.status is DayStatus.FINAL and result.counts.replaced == 0 and result.errors == {}
    store = _seeded_store()
    result = finalize_into(store, DAY, list(candle_bars()), InMemoryCandleSource([]), start=START, end=END)
    assert result.status is DayStatus.PROVISIONAL and result.errors == {"incomplete": 8}
    assert result.counts.replaced == 0 and result.counts.kept_live > 0
    assert all(b.source is BarSource.LIVE for b in store.bars(NIFTY_CE, DAY))


@pytest.mark.parametrize("exc,key", [(TimeoutError("t"), "fetch_failed"), (RuntimeError("http 500"), "fetch_failed"),
                                      (CandleError("bad"), "malformed")])
def test_error_timeout_or_malformed_body_keeps_the_day_provisional_without_raising(exc, key):
    store = _seeded_store()
    result = finalize_into(store, DAY, list(candle_bars()), Raising(exc), start=START, end=END)
    assert result.status is DayStatus.PROVISIONAL and store.day_status(DAY) is DayStatus.PROVISIONAL
    assert result.errors[key] == 8
    assert all(b.source is BarSource.LIVE for b in store.bars(NIFTY_CE, DAY))


def test_a_candle_outside_the_requested_range_is_ignored_and_counted():
    store = _seeded_store()
    late = MinuteBar(NIFTY_CE, at(15, 40), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1, 1, BarSource.KITE)

    class Loose:
        def minute_candles(self, instrument_id, start, end):
            return [late]
    result = finalize_into(store, DAY, [NIFTY_CE], Loose(), start=START, end=END)
    assert result.errors["out_of_range"] == 1  # (the 7 instruments not asked for also leave the day incomplete)
    assert not any(b.minute == at(15, 40) for b in store.bars(NIFTY_CE, DAY))


def test_a_final_bar_is_never_overwritten_by_a_late_live_bar():
    store = _seeded_store()
    finalize_into(store, DAY, list(candle_bars()), InMemoryCandleSource(kite_all(W)), start=START, end=END)
    _, live = build(W)
    store.put_bars(live)
    assert_kite_up_to_1511(store)
    assert datetime.date(2026, 10, 9) not in {b.minute.date() for b in store.bars(NIFTY_CE, DAY)}
