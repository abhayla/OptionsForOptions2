"""Throwaway proof (W-097 core): latest full frame for token 12080386 at or before 15:07:20 IST vs Zerodha's REST depth.

Run from the repo root: python docs/research/depth-proof-2026-10-17/proof.py [cut-frame-output-path]
"""
import gzip
import json
import struct
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, "backend")
from ofo.marketdata.kite_frames import iter_recording  # noqa: E402

REC = "D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/frames-120730.bin.gz"
FETCH = "D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json"
TOKEN = 12080386
IST = timezone(timedelta(hours=5, minutes=30))
CUT = int(datetime(2026, 10, 16, 15, 7, 20, tzinfo=IST).timestamp())

best = None
n = 0
with gzip.open(REC, "rb") as fh:
    for idx, (recv_ns, frame) in enumerate(iter_recording(fh)):
        n += 1
        if len(frame) < 2:
            continue
        count, off = int.from_bytes(frame[:2], "big"), 2
        for _ in range(count):
            ln = int.from_bytes(frame[off:off + 2], "big")
            pk = frame[off + 2:off + 2 + ln]
            off += 2 + ln
            if ln == 184 and int.from_bytes(pk[:4], "big") == TOKEN:
                ts = struct.unpack(">i", pk[60:64])[0]
                if ts <= CUT:
                    best = (idx, recv_ns, ts, bytes(pk))
print("frames scanned", n)
idx, recv_ns, ts, pk = best
print("frame index", idx, "recv_ns", recv_ns, "exchange_ts", ts, datetime.fromtimestamp(ts, IST).isoformat())
levels = []
for i in range(10):
    q, p, o = struct.unpack(">iih", pk[64 + 12 * i:64 + 12 * i + 10])
    levels.append((q, Decimal(p) / 100, o))
bids, asks = levels[:5], levels[5:]
rest = json.load(open(FETCH), parse_float=Decimal)["quote"]["depth"]
for side, mine, key in (("BID", bids, "buy"), ("ASK", asks, "sell")):
    for i, (q, p, o) in enumerate(mine):
        r = rest[key][i]
        same = (Decimal(str(r["price"])), r["quantity"]) == (p, q)
        print(side, i, "frame", p, q, o, "| rest", r["price"], r["quantity"], r["orders"], "MATCH" if same else "DIFF")
if len(sys.argv) > 1:
    with open(sys.argv[1], "wb") as out:
        out.write((1).to_bytes(2, "big") + (184).to_bytes(2, "big") + pk)
    print("cut frame written", sys.argv[1], len(pk) + 4, "bytes")
