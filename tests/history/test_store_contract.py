"""W-062 round 3: the shared history-store contract. Every store implementation runs every rule through EVERY public
write method, because the three rules live in one private writer, not in each method (finding
store-rule-enforced-per-call-site). The PostgreSQL store must be added to STORES when it exists.
"""
import datetime
from decimal import Decimal

import pytest
from _history_fixture import DAY, at

from ofo.history.bars import BarSource, MinuteBar, session_gaps
from ofo.history.store import DayStatus, InMemoryHistoryStore

STORES = [InMemoryHistoryStore]  # add the PostgreSQL store here when it exists
GAP = (at(10, 0, 5), at(10, 2, 59))  # a 174 s outage inside the session: minutes 10:00, 10:01, 10:02
IN_GAP, OUT = at(10, 1), at(11, 0)


@pytest.fixture(params=STORES, ids=lambda c: c.__name__)
def store(request):
    return request.param()


def bar(minute, source=BarSource.LIVE, close="1", iid="X:1"):
    c = Decimal(close)
    return MinuteBar(iid, minute, c, c, c, c, 1, 1, source)


def sources(store, iid="X:1"):
    return {b.minute: b.source for b in store.bars(iid, DAY)}


# ---- rule 1: no LIVE bar inside a recorded gap, through every write method ---------------------------------------------
def test_put_bars_refuses_a_live_bar_inside_a_gap(store):
    store.record_gaps([GAP])
    store.put_bars([bar(IN_GAP), bar(OUT)])
    assert sources(store) == {OUT: BarSource.LIVE}


def test_replace_day_bars_refuses_a_live_bar_inside_a_gap(store):  # finding A
    store.record_gaps([GAP])
    store.replace_day_bars(DAY, [bar(at(10, 0)), bar(IN_GAP), bar(OUT)])
    assert sources(store) == {OUT: BarSource.LIVE}


def test_record_gaps_removes_a_live_bar_stored_before_the_gap_was_known(store):
    store.put_bars([bar(IN_GAP), bar(OUT)])
    store.record_gaps([GAP])
    assert sources(store) == {OUT: BarSource.LIVE}
    assert store.gap_minutes_missing(DAY) == 1


def test_apply_candles_marks_a_gap_minute_backfilled_and_others_kite(store):
    store.record_gaps([GAP])
    store.apply_candles(DAY, [bar(IN_GAP, BarSource.KITE), bar(OUT, BarSource.KITE)])
    assert sources(store) == {IN_GAP: BarSource.BACKFILLED, OUT: BarSource.KITE}


# ---- rule 2: a source is never lowered, through every write method -----------------------------------------------------
@pytest.mark.parametrize("low", [BarSource.LIVE, BarSource.BACKFILLED])
def test_put_bars_never_lowers_a_kite_bar(store, low):
    store.put_bars([bar(OUT, BarSource.KITE, "2")])
    store.put_bars([bar(OUT, low, "9")])
    assert store.bars("X:1", DAY)[0].close == Decimal("2") and sources(store) == {OUT: BarSource.KITE}


def test_replace_day_bars_never_lowers_a_kite_bar_and_never_removes_it(store):  # finding B
    store.put_bars([bar(OUT, BarSource.KITE, "2"), bar(at(12, 0), BarSource.KITE)])
    store.replace_day_bars(DAY, [bar(OUT, BarSource.LIVE, "9")])
    assert sources(store) == {OUT: BarSource.KITE, at(12, 0): BarSource.KITE}
    assert store.bars("X:1", DAY)[0].close == Decimal("2")


def test_replace_day_bars_removes_only_live_bars_the_batch_does_not_carry(store):
    store.put_bars([bar(at(12, 0)), bar(at(12, 1), BarSource.BACKFILLED)])
    store.replace_day_bars(DAY, [bar(OUT)])
    assert sources(store) == {at(12, 1): BarSource.BACKFILLED, OUT: BarSource.LIVE}


def test_apply_candles_never_lowers_a_kite_bar(store):
    store.put_bars([bar(IN_GAP, BarSource.KITE, "2")])
    store.record_gaps([GAP])
    store.apply_candles(DAY, [bar(IN_GAP, BarSource.KITE, "9")])  # a gap candle is BACKFILLED: lower than KITE
    assert sources(store) == {IN_GAP: BarSource.KITE} and store.bars("X:1", DAY)[0].close == Decimal("2")


def test_a_live_bar_replaces_a_live_bar_but_a_kite_candle_replaces_a_live_bar(store):
    store.put_bars([bar(OUT, close="1")])
    store.put_bars([bar(OUT, close="2")])
    store.apply_candles(DAY, [bar(OUT, BarSource.KITE, "3")])
    assert store.bars("X:1", DAY)[0].close == Decimal("3") and sources(store) == {OUT: BarSource.KITE}


# ---- rule 3: a FINAL day never changes, through every write method -----------------------------------------------------
@pytest.fixture
def final(store):
    store.put_bars([bar(OUT), bar(at(12, 0), BarSource.KITE), bar(at(12, 30))])  # 12:30 stays LIVE (Kite lacks it)
    store.apply_candles(DAY, [bar(OUT, BarSource.KITE)])
    store.set_day_status(DAY, DayStatus.FINAL)
    return store, {b.minute: (b.source, b.close) for b in store.bars_for_day(DAY)}


def snapshot(store):
    return {b.minute: (b.source, b.close) for b in store.bars_for_day(DAY)}


def test_put_bars_is_refused_on_a_final_day(final):
    store, before = final
    store.put_bars([bar(at(13, 0)), bar(OUT, BarSource.KITE, "9")])
    assert snapshot(store) == before


def test_replace_day_bars_is_refused_on_a_final_day(final):
    store, before = final
    store.replace_day_bars(DAY, [bar(at(13, 0))])  # would also delete the kept LIVE 12:30 bar
    assert snapshot(store) == before
    store.replace_day_bars(DAY, [])
    assert snapshot(store) == before


def test_apply_candles_is_refused_on_a_final_day(final):
    store, before = final
    store.apply_candles(DAY, [bar(at(13, 0), BarSource.KITE)])
    assert snapshot(store) == before


def test_record_gaps_after_final_deletes_nothing_and_the_day_stays_final(final):  # finding C
    store, before = final
    store.record_gaps([(at(11, 59), at(12, 5)), (at(10, 59), at(11, 5))])
    assert snapshot(store) == before and store.day_status(DAY) is DayStatus.FINAL and store.gaps(DAY) == []


def test_a_final_day_cannot_go_back_to_provisional_and_finalizing_again_is_idempotent(final):
    store, before = final
    store.set_day_status(DAY, DayStatus.PROVISIONAL)
    assert store.day_status(DAY) is DayStatus.FINAL
    store.set_day_status(DAY, DayStatus.FINAL)
    assert store.day_status(DAY) is DayStatus.FINAL and snapshot(store) == before


def test_another_day_is_not_affected_by_a_final_day(final):
    store, _ = final
    next_day = datetime.date(2026, 10, 9)
    store.put_bars([bar(datetime.datetime(2026, 10, 9, 10, 0, tzinfo=OUT.tzinfo))])
    assert len(store.bars("X:1", next_day)) == 1 and store.day_status(next_day) is DayStatus.PROVISIONAL


# ---- only MinuteBars; a bad batch changes nothing -------------------------------------------------------------------
@pytest.mark.parametrize("method", ["put_bars", "replace_day_bars", "apply_candles"])
def test_every_bar_taking_method_refuses_a_non_bar_and_changes_nothing(store, method):
    args = (DAY,) if method != "put_bars" else ()
    with pytest.raises(TypeError):
        getattr(store, method)(*args, [bar(OUT, BarSource.KITE), {"ltp": 1}])
    assert store.bars_for_day(DAY) == []


# ---- gaps are session gaps ---------------------------------------------------------------------------------------------
def test_an_overnight_quiet_spell_is_not_a_gap_and_closed_market_minutes_are_not_clipped_in(store):
    d1_close, d2_open = at(15, 29, 59), datetime.datetime(2026, 10, 9, 9, 15, tzinfo=at(9, 0).tzinfo)
    assert session_gaps(d1_close, d2_open) == []
    store.record_gaps([(d1_close, d2_open)])
    store.put_bars([bar(at(15, 29)), bar(datetime.datetime(2026, 10, 9, 9, 15, tzinfo=d2_open.tzinfo))])
    assert store.gaps(DAY) == [] and store.gaps(datetime.date(2026, 10, 9)) == []
    assert len(store.bars("X:1", DAY)) == 1 and len(store.bars("X:1", datetime.date(2026, 10, 9))) == 1


def test_an_outage_inside_the_session_is_still_a_gap_and_post_close_minutes_are_not(store):
    assert session_gaps(at(10, 0, 0), at(10, 1, 54)) == [(at(10, 0, 0), at(10, 1, 54))]  # 114 s at 10:00
    assert session_gaps(at(15, 29, 0), at(15, 45, 0)) == [(at(15, 29, 0), at(15, 30, 0))]  # clipped at the close
    store.record_gaps([(at(15, 29, 0), at(15, 45, 0))])
    store.put_bars([bar(at(15, 35)), bar(at(15, 39))])  # expiring SENSEX options traded until 15:39 (F-33)
    assert sources(store) == {at(15, 35): BarSource.LIVE, at(15, 39): BarSource.LIVE}
    store.apply_candles(DAY, [bar(at(15, 35), BarSource.KITE)])
    assert sources(store)[at(15, 35)] is BarSource.KITE
