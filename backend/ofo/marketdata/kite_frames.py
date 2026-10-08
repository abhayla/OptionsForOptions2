"""Parse Kite's binary WebSocket frames into raw ticks (W-059, REQ-048; field shapes F-29).

Standard library only, no network, no clock. A frame is: int16 packet count, then per packet an int16 length and
that many bytes (big-endian). A frame of one byte is a heartbeat. Packet lengths: 8 = ltp, 28/32 = index
(32 carries the exchange time), 44 = quote, 184 = full (adds OI and exchange time and ten depth entries of
qty int32, price int32, orders int16, 2 pad bytes). Prices are integer paise on the V1 segments and become
``Decimal`` rupees (paise / 100); a segment whose divisor is not known here is counted and skipped, never guessed.

Every answer state is counted, never raised: unknown packet length, unsupported segment, truncated frame.
Depth price 0 means "absent" (F-29), so bid / ask are ``None`` then, never a Rs 0 price.

``iter_recording`` reads the recorder's file format (gzip of repeated ``>qI`` receive-time-ns and length, then the
frame) so a recorded session can be replayed through the same code the live socket uses.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import BinaryIO, Iterator

#: Kite instrument_token low byte -> price divisor (paise per rupee). Only the V1 segments; others are skipped.
SEGMENT_DIVISOR: dict[int, int] = {1: 100, 2: 100, 4: 100, 5: 100, 9: 100}  # NSE, NFO, BSE, BFO, indices
SEGMENT_NAMES: dict[int, str] = {1: "NSE", 2: "NFO", 4: "BSE", 5: "BFO", 9: "INDICES"}

PACKET_LTP = 8
PACKET_INDEX = (28, 32)
PACKET_QUOTE = 44
PACKET_FULL = 184

_DEPTH_AT = 64
_BID0 = _DEPTH_AT  # buy[0]
_ASK0 = _DEPTH_AT + 5 * 12  # sell[0]: ten entries of 12 bytes, buys first


@dataclass(frozen=True)
class RawTick:
    """One packet, decoded. Fields a packet type does not carry are ``None``."""

    token: int
    kind: str  # "ltp" | "index" | "quote" | "full"
    ltp: Decimal
    volume: int | None = None
    oi: int | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    exchange_ts: int | None = None  # epoch seconds, as Kite sends it


@dataclass(frozen=True)
class FrameResult:
    ticks: tuple[RawTick, ...]
    heartbeat: bool = False
    unknown_packets: int = 0  # packet length not in the format table
    unsupported_segment: int = 0  # token's segment has no known price divisor
    malformed: int = 0  # frame or packet cut short


def _money(paise: int, divisor: int) -> Decimal:
    return Decimal(paise) / Decimal(divisor)


def _price_or_none(paise: int, divisor: int) -> Decimal | None:
    return _money(paise, divisor) if paise > 0 else None


def _decode(p: bytes, divisor: int, token: int) -> RawTick | None:
    n = len(p)
    if n == PACKET_LTP:
        return RawTick(token, "ltp", _money(struct.unpack(">i", p[4:8])[0], divisor))
    if n in PACKET_INDEX:
        ltp = struct.unpack(">i", p[4:8])[0]
        ts = struct.unpack(">i", p[28:32])[0] if n == 32 else None
        return RawTick(token, "index", _money(ltp, divisor), exchange_ts=ts)
    if n == PACKET_QUOTE or n == PACKET_FULL:
        f = struct.unpack(">10i", p[4:44])
        ltp, volume = f[0], f[3]
        if n == PACKET_QUOTE:
            return RawTick(token, "quote", _money(ltp, divisor), volume=volume)
        oi, ts = struct.unpack(">i", p[48:52])[0], struct.unpack(">i", p[60:64])[0]
        bid = struct.unpack(">i", p[_BID0 + 4:_BID0 + 8])[0]
        ask = struct.unpack(">i", p[_ASK0 + 4:_ASK0 + 8])[0]
        return RawTick(token, "full", _money(ltp, divisor), volume=volume, oi=oi,
                       bid=_price_or_none(bid, divisor), ask=_price_or_none(ask, divisor), exchange_ts=ts)
    return None


def parse_frame(data: bytes) -> FrameResult:
    """Decode one WebSocket binary message. Never raises on bad bytes: it counts them."""
    if len(data) == 1:
        return FrameResult((), heartbeat=True)
    if len(data) < 2:
        return FrameResult((), malformed=1)
    count = int.from_bytes(data[0:2], "big")
    off = 2
    ticks: list[RawTick] = []
    unknown = unsupported = malformed = 0
    for _ in range(count):
        if off + 2 > len(data):
            malformed += 1
            break
        length = int.from_bytes(data[off:off + 2], "big")
        packet = data[off + 2:off + 2 + length]
        off += 2 + length
        if len(packet) < length or length < 8:
            malformed += 1
            break
        token = int.from_bytes(packet[0:4], "big")
        divisor = SEGMENT_DIVISOR.get(token & 0xFF)
        if divisor is None:
            unsupported += 1
            continue
        tick = _decode(packet, divisor, token)
        if tick is None:
            unknown += 1
        else:
            ticks.append(tick)
    return FrameResult(tuple(ticks), unknown_packets=unknown, unsupported_segment=unsupported, malformed=malformed)


def iter_recording(stream: BinaryIO) -> Iterator[tuple[int, bytes]]:
    """Yield ``(receive_time_ns, frame_bytes)`` from an opened (already decompressed) recording."""
    while True:
        head = stream.read(12)
        if len(head) < 12:
            return
        recv_ns, length = struct.unpack(">qI", head)
        frame = stream.read(length)
        if len(frame) < length:
            return
        yield recv_ns, frame
