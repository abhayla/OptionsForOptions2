"""GC-BM F-19 (ADR-200 (2)): a quote's ``price_at`` is the time its price was MADE: in market hours its own
``timestamp``; outside them the close (15:30 IST) of the session the price belongs to. ``timestamp`` itself never
changes (liveness, bars and the in-hours rules read it).

Live miss (2026-10-28 07:46-07:52 IST, before the open): the banner said "Prices are from 28 Oct 2026, 07:46:17 IST" -
the frame ARRIVAL time of an index packet without an exchange time (kite_provider ``normalise`` falls back to
``received_at``) - and Kite stamps post-close packets 16:22:40 (options) / 17:35:06 (index). None of these is when the
price was made. Packets below are built byte for byte in Kite's documented layout and decoded by the real
``parse_frame``; the in-hours recordings are the real 2026-10-08 09:20 capture and the 15:07:20 full packet.
"""
import datetime
import struct

import pytest

from ofo.marketdata.kite_provider import IST, KiteProvider

from _kite_fixture import FIXTURES, Clock, all_instrument_ids, listed, new_provider, recorded_frames

NIFTY_INDEX_TOKEN = 256265  # NSE_INDEX:1001 in the catalogue fixture
OPTION_TOKEN = 11421186  # NSE_FO:44614, NIFTY 22550 CE
ARRIVED = datetime.datetime(2026, 10, 28, 7, 46, 28, tzinfo=IST)  # Wed, before the open
CLOSE_27 = datetime.datetime(2026, 10, 27, 15, 30, tzinfo=IST)


def _frame(*packets: bytes) -> bytes:
    out = len(packets).to_bytes(2, "big")
    for p in packets:
        out += len(p).to_bytes(2, "big") + p
    return out


def _index_packet(ltp_paise: int, exchange_ts: int | None) -> bytes:
    """28 bytes (no exchange time) or 32 bytes (exchange time at 28-32)."""
    body = struct.pack(">7i", NIFTY_INDEX_TOKEN, ltp_paise, ltp_paise, ltp_paise, ltp_paise, ltp_paise, 0)
    return body if exchange_ts is None else body + struct.pack(">i", exchange_ts)


def _full_packet(exchange_ts: int) -> bytes:
    """184-byte full packet of the option: one bid and one ask level, exchange time at 60-64."""
    head = struct.pack(">11i", OPTION_TOKEN, 1000, 65, 1000, 0, 0, 0, 0, 0, 0, 0)  # 44 bytes
    rest = struct.pack(">5i", 0, 1000, 0, 0, exchange_ts)  # last trade, oi, oi hi, oi lo, exchange time -> 64 bytes
    level = struct.pack(">iihh", 65, 995, 1, 0)  # quantity, price (paise), orders, padding: 12 bytes
    ask = struct.pack(">iihh", 65, 1005, 1, 0)
    empty = b"\x00" * 12
    return head + rest + level + empty * 4 + ask + empty * 4


def _provider() -> KiteProvider:
    return KiteProvider(listed(), clock=Clock(ARRIVED))


def _normalise(packet: bytes, received_at: datetime.datetime = ARRIVED):
    """The real path: ``on_frame`` decodes the frame and normalises its one tick."""
    provider = _provider()
    provider.subscribe(all_instrument_ids(listed()))
    quotes = provider.on_frame(_frame(packet), received_at)
    assert len(quotes) == 1, quotes
    return quotes[0]


@pytest.mark.parametrize("packet,shape", [
    (_index_packet(2585000, None), "28-byte index packet: no exchange time"),
    (_index_packet(2585000, 0), "32-byte index packet: exchange time 0"),
    (_index_packet(2585000, int(ARRIVED.timestamp())), "Kite-stamped 07:46:28"),
])
def test_before_the_open_price_at_is_the_previous_close_and_timestamp_is_unchanged(packet, shape):
    quote = _normalise(packet)
    assert quote.timestamp == ARRIVED, shape  # unchanged: liveness reads it
    assert quote.price_at == CLOSE_27, shape


def test_a_full_option_packet_stamped_before_the_open_is_labelled_with_the_close():
    quote = _normalise(_full_packet(int(ARRIVED.timestamp())))
    assert (quote.timestamp, quote.price_at) == (ARRIVED, CLOSE_27)


@pytest.mark.parametrize("stamped,expected", [
    (datetime.datetime(2026, 10, 27, 17, 35, 6, tzinfo=IST), CLOSE_27),  # Kite's post-close index stamp
    (datetime.datetime(2026, 10, 27, 16, 22, 40, tzinfo=IST), CLOSE_27),  # Kite's post-close option stamp
    (datetime.datetime(2026, 10, 27, 15, 30, tzinfo=IST), CLOSE_27),  # exactly the close
    (datetime.datetime(2026, 10, 21, 7, 46, tzinfo=IST),  # Wed after the Tue 20 Oct Dussehra holiday
     datetime.datetime(2026, 10, 19, 15, 30, tzinfo=IST)),
    (datetime.datetime(2026, 10, 31, 11, 0, tzinfo=IST),  # Saturday
     datetime.datetime(2026, 10, 30, 15, 30, tzinfo=IST)),
    (datetime.datetime(2027, 1, 4, 7, 46, tzinfo=IST), None),  # no calendar data: no time is invented
])
def test_closed_market_stamps_map_to_the_session_close(stamped, expected):
    quote = _normalise(_index_packet(2585000, int(stamped.timestamp())), received_at=stamped)
    assert quote.timestamp == stamped
    assert quote.price_at == expected


def test_replayed_in_hours_recording_price_at_equals_timestamp_on_every_tick():
    """Real 2026-10-08 09:20 recording: no in-hours change."""
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    frames = recorded_frames()
    provider.on_connected(frames[0][0])
    seen = 0
    for at, frame in frames:
        clock.now = at
        for quote in provider.on_frame(frame, at):
            assert quote.price_at == quote.timestamp, quote.instrument_id
            seen += 1
    assert seen > 100


def test_the_real_15_07_20_full_packet_keeps_its_own_time():
    frame = (FIXTURES / "full-frame-12080386-150720.bin").read_bytes()
    at = datetime.datetime.fromtimestamp(1792143440, IST)
    provider = KiteProvider(listed(), clock=Clock(at))
    provider.subscribe(all_instrument_ids(listed()))
    quotes = provider.on_frame(frame, at)
    assert quotes and all(q.price_at == q.timestamp == at for q in quotes)
