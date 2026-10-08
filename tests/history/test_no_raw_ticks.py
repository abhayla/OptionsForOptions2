"""W-062 AC-2 (REQ-051): no raw tick or quote is kept - the store takes only MinuteBars and holds at most one per minute."""
import datetime
from decimal import Decimal

import pytest
from _history_fixture import replay_window
from test_minute_bars_replay import NIFTY_CE

from ofo.history.bars import BarSource, MinuteBar
from ofo.history.recorder import Recorder
from ofo.history.store import InMemoryHistoryStore
from ofo.marketdata.kite_frames import RawTick
from ofo.marketdata.quote import NormalizedQuote


def _hold_anything_raw(obj, seen=None) -> bool:
    """True if a NormalizedQuote or RawTick is reachable from obj's attributes / containers."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return False
    seen.add(id(obj))
    if isinstance(obj, (NormalizedQuote, RawTick)):
        return True
    if isinstance(obj, dict):
        children = [*obj.keys(), *obj.values()]
    elif isinstance(obj, (list, tuple, set, frozenset)):
        children = list(obj)
    elif hasattr(obj, "__dict__"):
        children = list(vars(obj).values())
    elif hasattr(obj, "__slots__"):
        children = [getattr(obj, s, None) for s in obj.__slots__]
    else:
        return False
    return any(_hold_anything_raw(c, seen) for c in children)


def test_after_a_replay_store_and_recorder_hold_only_minute_bars_one_per_minute():
    store = InMemoryHistoryStore()
    holder = {}

    def wire(fan, ids):
        fan.subscribe(lambda q: None, ids)
        holder["rec"] = Recorder(store)
        holder["rec"].attach(fan, ids)

    _, _, last = replay_window("1506-1512", wire)
    holder["rec"].flush(last + datetime.timedelta(minutes=1))
    stored = store.all_stored()
    assert len(stored) > 40 and all(type(b) is MinuteBar for b in stored)
    assert len({(b.instrument_id, b.minute) for b in stored}) == len(stored)  # at most one per instrument-minute
    holder["rec"].detach()  # the fan-out (and through it the provider's own quote book) is the feed's, not the recorder's
    assert not _hold_anything_raw(store) and not _hold_anything_raw(holder["rec"])
    # a minute holds far fewer bars than the ~1 s ticks that built it (the replay carried 3,041 ticks into 56 bars)
    assert len(stored) < 100


def test_the_store_refuses_a_quote_or_a_tick_and_stores_nothing_of_a_mixed_batch():
    store = InMemoryHistoryStore()
    quotes = []

    def wire(fan, ids):
        fan.subscribe(quotes.append, ids)

    replay_window("0920-0924", wire)
    good = MinuteBar(NIFTY_CE, quotes[0].timestamp.replace(second=0, microsecond=0), Decimal("1"), Decimal("1"),
                     Decimal("1"), Decimal("1"), 1, 1, BarSource.LIVE)
    for raw in (quotes[0], RawTick.__new__(RawTick), {"ltp": "1"}, 5):
        with pytest.raises(TypeError):
            store.put_bars([good, raw])
    assert store.all_stored() == []


def test_the_bar_type_has_no_field_that_could_carry_a_tick():
    fields = set(MinuteBar.__dataclass_fields__)
    assert fields == {"instrument_id", "minute", "open", "high", "low", "close", "volume", "oi", "source"}
