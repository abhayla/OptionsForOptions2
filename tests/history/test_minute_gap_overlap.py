"""W-062 round 4: a minute is inside a gap iff its 60 seconds overlap the half-open gap [start, end)."""
import pytest
from _history_fixture import DAY, at

from ofo.history.bars import BarSource, MinuteBar, minute_in_gap
from ofo.history.store import InMemoryHistoryStore
from decimal import Decimal


def bar(minute):
    c = Decimal("1")
    return MinuteBar("X:1", minute, c, c, c, c, 1, 1, BarSource.LIVE)


@pytest.mark.parametrize("gap,inside,outside", [
    ((at(15, 29, 50), at(15, 30, 20)), [at(15, 29), at(15, 30)], [at(15, 31)]),
    ((at(10, 0, 0), at(10, 1, 0)), [at(10, 0)], [at(10, 1), at(9, 59)]),
    ((at(10, 0, 30), at(10, 0, 40)), [at(10, 0)], [at(10, 1)]),
    ((at(9, 15, 30), at(9, 16, 0)), [at(9, 15)], [at(9, 16)]),
])
def test_minute_in_gap_is_half_open_overlap(gap, inside, outside):
    assert all(minute_in_gap(m, gap) for m in inside) and not any(minute_in_gap(m, gap) for m in outside)


def test_the_1530_minute_survives_a_gap_that_ends_at_the_close():
    store = InMemoryHistoryStore()
    store.record_gaps([(at(15, 29, 50), at(15, 30, 20))])  # clipped to end at 15:30:00
    store.put_bars([bar(at(15, 29)), bar(at(15, 30)), bar(at(15, 31))])
    assert [b.minute for b in store.bars_for_day(DAY)] == [at(15, 30), at(15, 31)] and store.dropped_in_gap == 1


def test_a_longer_gap_to_the_close_drops_only_minutes_it_overlaps():
    store = InMemoryHistoryStore()
    store.put_bars([bar(at(15, 29)), bar(at(15, 30)), bar(at(15, 31))])
    store.record_gaps([(at(15, 25, 0), at(15, 30, 20))])
    assert [b.minute for b in store.bars_for_day(DAY)] == [at(15, 30), at(15, 31)]
