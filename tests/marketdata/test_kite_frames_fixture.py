"""W-059 core: the real Kite frames recorded 2026-10-08 09:20:00-09:20:10 IST parse into the values in the work item.

Expected values are the ones written in work/W-059.md `proof` (read by an independent parser from the same bytes),
not values produced by running this code.
"""
import datetime
import gzip
import pathlib
from decimal import Decimal

import pytest

from ofo.marketdata.kite_frames import RawTick, iter_recording, parse_frame

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "kite_ws"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# Zerodha instrument_token for each name in the proof (from instruments-2026-10-08-subscribed.csv).
NIFTY_50 = 256265
SENSEX = 265
NIFTY_CE = 11421186  # the NIFTY 22550 call of 2026-10-13, NFO exchange token 44614
NIFTY_PE = 11421442  # the NIFTY 22550 put of 2026-10-13, NFO exchange token 44615
SENSEX_CE = 227668741  # SENSEX26O0872500CE, BFO exchange token 889331


@pytest.fixture(scope="module")
def replay():
    frames = heartbeats = unknown = unsupported = malformed = 0
    ticks: list[RawTick] = []
    with gzip.open(FIXTURES / "frames-2026-10-08-092000-10s.bin.gz") as f:
        for _recv_ns, frame in iter_recording(f):
            r = parse_frame(frame)
            frames += 1
            heartbeats += r.heartbeat
            unknown += r.unknown_packets
            unsupported += r.unsupported_segment
            malformed += r.malformed
            ticks.extend(r.ticks)
    last = {}
    for t in ticks:
        last[t.token] = t
    return {"frames": frames, "heartbeats": heartbeats, "ticks": ticks, "last": last,
            "bad": (unknown, unsupported, malformed)}


def test_counts_match_the_work_item(replay):
    assert replay["frames"] == 43
    assert replay["heartbeats"] == 3
    assert len(replay["ticks"]) == 7301
    assert len(replay["last"]) == 983
    assert replay["bad"] == (0, 0, 0)  # nothing in a real session is unknown, unsupported or cut short


def test_index_values(replay):
    assert replay["last"][NIFTY_50].ltp == Decimal("22533.25")
    assert replay["last"][SENSEX].ltp == Decimal("72443.48")
    assert replay["last"][NIFTY_50].kind == "index"


def test_option_values(replay):
    ce = replay["last"][NIFTY_CE]
    assert (ce.ltp, ce.bid, ce.ask, ce.oi) == (Decimal("124.95"), Decimal("124.20"), Decimal("124.35"), 2_679_040)
    pe = replay["last"][NIFTY_PE]
    assert (pe.ltp, pe.bid, pe.ask) == (Decimal("145.10"), Decimal("145.35"), Decimal("145.75"))
    sx = replay["last"][SENSEX_CE]
    assert (sx.ltp, sx.bid, sx.ask) == (Decimal("144.35"), Decimal("144.15"), Decimal("144.45"))


def test_exchange_time_is_09_20_09_ist(replay):
    ts = replay["last"][NIFTY_CE].exchange_ts
    assert datetime.datetime.fromtimestamp(ts, IST) == datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)


def test_prices_are_exact_decimals(replay):
    for t in replay["last"].values():
        assert type(t.ltp) is Decimal
        for p in (t.bid, t.ask):
            assert p is None or (type(p) is Decimal and p > 0)  # 0 in depth means absent, never a Rs 0 price


def test_bad_bytes_are_counted_not_raised():
    assert parse_frame(b"\x00").heartbeat is True
    assert parse_frame(b"").malformed == 1
    one_packet_cut = (1).to_bytes(2, "big") + (44).to_bytes(2, "big") + b"\x00" * 10
    assert parse_frame(one_packet_cut).malformed == 1
    odd_length = (1).to_bytes(2, "big") + (12).to_bytes(2, "big") + (11421186).to_bytes(4, "big") + b"\x00" * 8
    assert parse_frame(odd_length).unknown_packets == 1
    foreign_segment = (1).to_bytes(2, "big") + (8).to_bytes(2, "big") + (0x00010003).to_bytes(4, "big") + b"\x00" * 4
    assert parse_frame(foreign_segment).unsupported_segment == 1
