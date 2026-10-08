"""REQ-048 AC-2: the provider interface offers live quote stream, option-chain snapshot, instrument master,
underlying quote, futures quote, optional historical data, health/status and source metadata. Kite frames normalise
per F-29 on the real recording."""
import datetime
from decimal import Decimal

import pytest
from _kite_fixture import NIFTY_CE_ID, NIFTY_PE_ID, SENSEX_CE_ID, all_instrument_ids, new_provider, replay

from ofo.engine.legs import Instrument
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.marketdata.provider import MarketDataProvider, NotSupported
from ofo.rules.inputs import DataHealth

OPERATIONS = ("live_quote_stream", "option_chain_snapshot", "instrument_master", "underlying_quote", "futures_quote",
              "historical", "status", "source_metadata", "subscribe", "unsubscribe")


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    seen = []
    provider.live_quote_stream(seen.append)
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider, seen, items


def test_interface_lists_every_ac2_operation():
    for op in OPERATIONS:
        assert op in MarketDataProvider.__abstractmethods__
    assert issubclass(KiteProvider, MarketDataProvider)


def test_stream_delivers_normalised_quotes_in_arrival_order(replayed):
    provider, seen, _ = replayed
    assert len(seen) == 7281 == provider.counters["ticks"]
    assert provider.counters["frames"] == 43 and provider.counters["heartbeats"] == 3
    assert provider.counters["unmapped_token"] == 20  # INDIA VIX's ticks: not in REQ-072 AC-1 (W-060)


def test_option_quote_fields_follow_f29(replayed):
    provider, _, _ = replayed
    now = datetime.datetime(2026, 10, 8, 9, 20, 10, tzinfo=IST)
    ce = provider.book.get(NIFTY_CE_ID, now)
    assert (ce.ltp, ce.bid, ce.ask, ce.oi) == (Decimal("124.95"), Decimal("124.20"), Decimal("124.35"), 2_679_040)
    assert ce.instrument_type is Instrument.CE and ce.underlying == "NIFTY" and ce.strike == Decimal("22550")
    assert ce.oi_change is None and ce.iv is None and ce.delta is None  # Kite has none of these
    assert ce.timestamp == datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST) and ce.timestamp.utcoffset() is not None
    assert type(ce.ltp) is Decimal and type(ce.bid) is Decimal and type(ce.ask) is Decimal
    pe = provider.book.get(NIFTY_PE_ID, now)
    assert (pe.ltp, pe.bid, pe.ask) == (Decimal("145.10"), Decimal("145.35"), Decimal("145.75"))
    sx = provider.book.get(SENSEX_CE_ID, now)
    assert (sx.ltp, sx.bid, sx.ask) == (Decimal("144.35"), Decimal("144.15"), Decimal("144.45"))
    assert sx.exchange == "BSE" and sx.segment == "BSE_FO"
    assert ce.source.provider == "zerodha-kite"


def test_underlying_and_chain_snapshot(replayed):
    provider, _, _ = replayed
    assert provider.underlying_quote("NIFTY").ltp == Decimal("22533.25")
    assert provider.underlying_quote("SENSEX").ltp == Decimal("72443.48")
    assert provider.underlying_quote("NIFTY").instrument_type is None
    chain = provider.option_chain_snapshot("NIFTY", datetime.date(2026, 10, 13))
    assert chain and {q.instrument_type for q in chain} == {Instrument.CE, Instrument.PE}
    assert all(q.underlying == "NIFTY" and q.expiry == datetime.date(2026, 10, 13) for q in chain)


def test_master_status_and_metadata(replayed):
    provider, _, items = replayed
    assert len(provider.instrument_master()) == len(items) == 1090  # 1,091 rows less INDIA VIX (NIFTY 50 / SENSEX are NSE_INDEX / BSE_INDEX rows, W-060)
    assert provider.status().health in (DataHealth.AVAILABLE, DataHealth.STALE)
    assert provider.status().connected is True
    assert provider.source_metadata().provider == "zerodha-kite"


def test_unsupported_operations_raise_not_supported(replayed):
    provider, _, _ = replayed
    with pytest.raises(NotSupported):
        provider.futures_quote("NIFTY", datetime.date(2026, 10, 27))
    with pytest.raises(NotSupported):
        provider.historical(NIFTY_CE_ID, datetime.datetime(2026, 10, 8, tzinfo=IST), datetime.datetime(2026, 10, 8, tzinfo=IST))


def test_every_socket_answer_state_has_a_counted_behaviour():
    provider, clock, _ = new_provider()
    now = clock.now
    provider.on_frame(b"\x00", now)  # heartbeat
    provider.on_frame((1).to_bytes(2, "big") + (12).to_bytes(2, "big") + (11421186).to_bytes(4, "big") + b"\x00" * 8, now)
    provider.on_frame((1).to_bytes(2, "big") + (8).to_bytes(2, "big") + (7).to_bytes(4, "big") + b"\x00" * 4, now)
    provider.on_text('{"type": "order", "data": {"order_id": "1", "tradingsymbol": "X"}}')
    provider.on_text('{"type": "error", "data": "bad"}')
    provider.on_text("not json")
    assert provider.counters["heartbeats"] == 1
    assert provider.counters["unknown_packets"] == 1
    assert provider.counters["unsupported_segment"] == 1
    assert provider.counters["text:order"] == 1 and provider.counters["text:error"] == 1
    assert provider.counters["text:unparsed"] == 1
    assert not any("order_id" in k or "tradingsymbol" in k for k in provider.counters)  # nothing personal stored
