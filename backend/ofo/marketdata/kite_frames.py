"""Parse Kite's binary WebSocket frames into raw ticks (W-059, REQ-048; field shapes F-29).

Standard library only, no network, no clock. A frame is: int16 packet count, then per packet an int16 length and
that many bytes (big-endian). A frame of one byte is a heartbeat. Packet lengths: 8 = ltp, 28/32 = index
(32 carries the exchange time), 44 = quote, 184 = full (adds OI and exchange time and ten depth entries of
qty int32, price int32, orders int16, 2 pad bytes). Quote and full packets carry, after the ltp, the last quantity,
average price, volume, buy and sell quantity, the day's open, high, low and previous close (the ten int32 fields at
bytes 4..44); a full packet adds the last trade time (44-48), OI (48-52) and exchange time (60-64). Layout source:
the zerodha-expert skill's websocket-protocol reference (no F-id records the packet layout; F-47 records that the
previous close was not decoded before this change). Prices are integer paise on the V1 segments and become
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

from ofo.marketdata.provider import DayStats

#: Kite instrument_token low byte -> price divisor (paise per rupee). Only the V1 segments; others are skipped.
SEGMENT_DIVISOR: dict[int, int] = {1: 100, 2: 100, 4: 100, 5: 100, 9: 100}  # NSE, NFO, BSE, BFO, indices
SEGMENT_NAMES: dict[int, str] = {1: "NSE", 2: "NFO", 4: "BSE", 5: "BFO", 9: "INDICES"}

PACKET_LTP = 8
PACKET_INDEX = (28, 32)
PACKET_QUOTE = 44
PACKET_FULL = 184

_DEPTH_AT = 64
_BID0 = _DEPTH_AT  # buy[0]
_DEPTH_LEVELS = 5
_ASK0 = _DEPTH_AT + _DEPTH_LEVELS * 12  # sell[0]: ten entries of 12 bytes, buys first


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
    # (price, quantity) per level, best first, price-0 entries dropped. ``None`` = the packet carries no depth (ltp /
    # index / quote); an EMPTY tuple = a full packet whose side is empty. The two never read alike.
    depth_bids: tuple[tuple[Decimal, int], ...] | None = None
    depth_asks: tuple[tuple[Decimal, int], ...] | None = None
    depth_unusable: bool = False  # full packet with a negative depth quantity: depth None, counted by the caller
    # the day's open / high / low / previous close and the last trade time (REQ-080 AC-7). Quote and full packets carry
    # them; ltp / index packets do not (``None``). A price of 0 is absent (F-29), so ``None``, never Rs 0.
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    prev_close: Decimal | None = None  # Kite's ``close`` = previous session's close (F-47)
    last_trade_ts: int | None = None  # full packet only: epoch seconds of the last trade; 0 = none yet -> None


def day_stats_of(tick: RawTick) -> DayStats | None:
    """What the packet says about the day; ``None`` for a packet that carries none of it (ltp / index)."""
    stats = DayStats(tick.day_open, tick.day_high, tick.day_low, tick.prev_close, tick.last_trade_ts)
    return None if stats == DayStats(None, None, None, None, None) else stats


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
        day = {"day_open": _price_or_none(f[6], divisor), "day_high": _price_or_none(f[7], divisor),
               "day_low": _price_or_none(f[8], divisor), "prev_close": _price_or_none(f[9], divisor)}
        if n == PACKET_QUOTE:
            return RawTick(token, "quote", _money(ltp, divisor), volume=volume, **day)
        last_trade = struct.unpack(">i", p[44:48])[0]
        oi, ts = struct.unpack(">i", p[48:52])[0], struct.unpack(">i", p[60:64])[0]
        bid = struct.unpack(">i", p[_BID0 + 4:_BID0 + 8])[0]
        ask = struct.unpack(">i", p[_ASK0 + 4:_ASK0 + 8])[0]
        bids, asks = _levels(p, _BID0, divisor), _levels(p, _ASK0, divisor)
        bad = bids is None or asks is None  # one untrustworthy side: no depth at all (never half a book)
        return RawTick(token, "full", _money(ltp, divisor), volume=volume, oi=oi,
                       bid=_price_or_none(bid, divisor), ask=_price_or_none(ask, divisor), exchange_ts=ts,
                       depth_bids=None if bad else bids, depth_asks=None if bad else asks, depth_unusable=bad,
                       last_trade_ts=last_trade if last_trade > 0 else None, **day)
    return None


def _levels(p: bytes, start: int, divisor: int) -> tuple[tuple[Decimal, int], ...] | None:
    """Five (price, quantity) entries from ``start``, best first; a price-0 entry is absent (F-29), dropped.
    ``None`` when an entry with a price has a negative quantity: the side cannot be trusted, so it is not offered."""
    out = []
    for i in range(_DEPTH_LEVELS):
        qty, paise = struct.unpack(">ii", p[start + 12 * i:start + 12 * i + 8])
        if paise > 0:
            if qty < 0:
                return None
            out.append((_money(paise, divisor), qty))
    return tuple(out)


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
