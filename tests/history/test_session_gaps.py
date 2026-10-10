"""W-062 round 3: the builder's gaps are session gaps - a closed market is not a feed gap (ADR-067, F-33)."""
import datetime
from decimal import Decimal

from _history_fixture import at

from ofo.history.bars import IST, MinuteBarBuilder
from ofo.history.recorder import Recorder
from ofo.history.store import InMemoryHistoryStore
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

SRC = SourceMetadata(provider="t", feed_id="t")
D2 = datetime.date(2026, 10, 9)


def index_quote(ts, ltp="100"):
    return NormalizedQuote(instrument_id="NSE_INDEX:1001", underlying="NIFTY", exchange="NSE", segment="NSE_INDEX",
                           instrument_type=None, expiry=None, strike=None, ltp=Decimal(ltp), bid=None, ask=None,
                           volume=None, oi=None, oi_change=None, iv=None, delta=None, gamma=None, theta=None,
                           vega=None, timestamp=ts, source=SRC, health=DataHealth.AVAILABLE)


def test_overnight_quiet_spell_records_no_gap_and_keeps_both_days_bars_live():
    store = InMemoryHistoryStore()
    rec = Recorder(store)
    d2_open = datetime.datetime(2026, 10, 9, 9, 15, tzinfo=IST)
    for ts in (at(15, 29, 58), at(15, 29, 59), *(d2_open + datetime.timedelta(seconds=i) for i in range(0, 63, 2))):
        rec.on_quote(index_quote(ts))
    assert rec.drain(10)  # the writer thread owns the store calls
    assert rec.builder.gaps == [] and store.gaps(DAY := at(9, 0).date()) == [] and store.gaps(D2) == []
    stored = {b.minute: b.source.value for b in store.all_stored()}
    assert stored == {at(15, 29): "live", d2_open: "live"}  # 15:29 and the 09:15 bar both survive as LIVE


def test_a_114_second_quiet_spell_at_10_is_still_a_gap():
    store = InMemoryHistoryStore()
    rec = Recorder(store)
    for ts in (at(9, 59, 59), at(10, 0, 0), at(10, 1, 54), at(10, 1, 55)):
        rec.on_quote(index_quote(ts))
    assert rec.drain(10)
    assert rec.builder.gaps == [(at(10, 0, 0), at(10, 1, 54))]
    assert store.gaps(at(9, 0).date()) == [(at(10, 0, 0), at(10, 1, 54))]
    assert not any(at(10, 0) <= b.minute <= at(10, 1) for b in store.all_stored())  # the suspect minutes are not LIVE


def test_the_builder_clip_matters_for_a_quiet_spell_after_the_close():
    builder = MinuteBarBuilder()
    builder.on_quote(index_quote(at(15, 30, 0)))
    builder.on_quote(index_quote(at(15, 39, 0)))  # expiring options traded until 15:39: nothing in 15:30+ is a gap
    assert builder.gaps == []
