"""REQ-080 AC-7: the day's open / high / low / previous close and the last trade time decoded from a full-mode frame.

The input is the ONE real full packet in ``tests/fixtures/kite_ws/full-frame-12080386-150720.bin`` (the NIFTY 23650 call
of 2026-10-19, token 12080386, 2026-10-16 15:07:20 IST). Expected values are read straight off the raw bytes with
``struct`` (the layout of Kite's websocket-protocol reference: ten int32 fields at bytes 4..44, last trade
time at 44..48), not from the decoder:
open 3.30 (330 paise), high 7.35, low 2.05, previous close 3.00, last trade time 1792143439.
A quote-only and an ltp-only packet are cut from the same real packet; a zero price is dropped (F-29).
"""
from __future__ import annotations

import pathlib
import struct
from decimal import Decimal

from ofo.marketdata.kite_frames import parse_frame

FRAME = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "kite_ws" / "full-frame-12080386-150720.bin"
D = Decimal
FULL_PACKET_LEN, LAST_TRADE_TS, FULL_OI = 184, 1792143439, 2562430


def _packet() -> bytes:
    return FRAME.read_bytes()[4:]  # one-packet frame: int16 count, int16 length, then the 184 bytes


def _frame(packet: bytes) -> bytes:
    return (1).to_bytes(2, "big") + len(packet).to_bytes(2, "big") + packet


def test_ac_7_full_frame_carries_the_days_open_high_low_previous_close_and_last_trade_time():
    """AC-7: the five values of the real packet, as read off its bytes."""
    packet = _packet()
    assert len(packet) == FULL_PACKET_LEN
    fields = struct.unpack(">11i", packet[4:48])  # ltp, last qty, avg, volume, buy qty, sell qty, o, h, l, c, ltt
    assert fields[6:] == (330, 735, 205, 300, LAST_TRADE_TS)
    tick = parse_frame(_frame(packet)).ticks[0]
    assert (tick.day_open, tick.day_high, tick.day_low, tick.prev_close) == (D("3.3"), D("7.35"), D("2.05"), D("3"))
    assert tick.last_trade_ts == LAST_TRADE_TS
    assert tick.ltp == D("3.35") and tick.oi == FULL_OI  # the fields decoded before are unchanged


def test_ac_7_a_zero_price_is_absent_never_rupees_zero():
    """AC-7 (attack 4): a zero open or previous close is None; a zero last trade time is None."""
    packet = bytearray(_packet())
    packet[28:32] = (0).to_bytes(4, "big")  # open
    packet[40:44] = (0).to_bytes(4, "big")  # close
    packet[44:48] = (0).to_bytes(4, "big")  # last trade time
    tick = parse_frame(_frame(bytes(packet))).ticks[0]
    assert tick.day_open is None and tick.prev_close is None and tick.last_trade_ts is None
    assert (tick.day_high, tick.day_low) == (D("7.35"), D("2.05"))


def test_ac_7_a_zero_priced_depth_level_is_dropped_and_the_rest_keep_their_order():
    """AC-7 (attack 4): a level whose price is 0 is not shown; the other four stay best first."""
    packet = bytearray(_packet())
    before = parse_frame(_frame(bytes(packet))).ticks[0].depth_bids
    packet[64 + 12 + 4:64 + 12 + 8] = (0).to_bytes(4, "big")  # buy[1] price -> 0
    after = parse_frame(_frame(bytes(packet))).ticks[0].depth_bids
    assert before is not None and after == (before[0], *before[2:])


def test_ac_8_a_quote_only_packet_has_the_day_values_but_no_depth_and_no_trade_time():
    """AC-8 (attack 4): the 44-byte quote packet carries OHLC but depth is None ('not read'), never an empty book."""
    quote = _packet()[:44]
    tick = parse_frame(_frame(quote)).ticks[0]
    assert tick.kind == "quote" and tick.depth_bids is None and tick.depth_asks is None
    assert (tick.day_open, tick.day_high, tick.day_low, tick.prev_close) == (D("3.3"), D("7.35"), D("2.05"), D("3"))
    assert tick.last_trade_ts is None


def test_ac_7_an_ltp_only_packet_carries_no_day_values():
    """AC-7: an 8-byte ltp packet has no open/high/low/close: all None."""
    tick = parse_frame(_frame(_packet()[:8])).ticks[0]
    assert tick.kind == "ltp"
    assert (tick.day_open, tick.day_high, tick.day_low, tick.prev_close, tick.last_trade_ts) == (None,) * 5
