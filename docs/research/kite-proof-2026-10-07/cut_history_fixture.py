"""Cuts the real fixture for W-062 (one-minute history, ADR-067) from the 2026-10-08 recordings. Data only.

Writes into tests/fixtures/kite_history/:
- frames-2026-10-08-0920-0924-8tok.bin.gz and frames-2026-10-08-1506-1512-8tok.bin.gz: the recorded frames of two
  windows, re-packed with only the 8 chosen instruments' packets (same binary format: 12-byte header + Kite frame).
  The second window holds the 15:08:13-15:10:08 laptop network outage of F-32/F-34.
- candles-2026-10-08.json: Kite's own one-minute candles (oi=1) for the same 8 instruments and minutes, kept as the
  exact HTTP body text per instrument so prices can be parsed as Decimal from their text (F-33).
No personal data, no token.
"""
import datetime as dt, gzip, json, os, struct, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kite_core_proof import call, load_env, session_token  # noqa: E402

RAW = r"D:\Abhay\Ventures\ofo-kite-ticks\2026-10-08"
OUT = os.path.join(HERE, "..", "..", "..", "tests", "fixtures", "kite_history")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TOKENS = [256265, 265, 11421186, 11421442, 227668741, 227622405, 227781893, 227673349]
WINDOWS = [("frames-083808.bin.gz", "09:19:50", "09:24:10", "0920-0924"),
           ("frames-144102.bin.gz", "15:05:50", "15:12:10", "1506-1512")]


def at(hms):
    h, m, s = map(int, hms.split(":"))
    return dt.datetime(2026, 10, 8, h, m, s, tzinfo=IST).timestamp()


def cut(src, start, end, tag):
    keep = set(TOKENS)
    frames = packets = 0
    dst = os.path.join(OUT, f"frames-2026-10-08-{tag}-8tok.bin.gz")
    with gzip.open(os.path.join(RAW, src), "rb") as f, gzip.open(dst, "wb") as g:
        while True:
            h = f.read(12)
            if len(h) < 12:
                break
            ns, ln = struct.unpack(">qI", h)
            b = f.read(ln)
            if len(b) < ln:
                break
            if not (at(start) <= ns / 1e9 <= at(end)):
                continue
            if len(b) < 2:  # heartbeat: keep it, it is part of the feed's timing
                g.write(h + b)
                frames += 1
                continue
            n, off, out = int.from_bytes(b[0:2], "big"), 2, []
            for _ in range(n):
                pl = int.from_bytes(b[off:off + 2], "big")
                p = b[off + 2:off + 2 + pl]
                off += 2 + pl
                if len(p) >= 4 and struct.unpack(">I", p[0:4])[0] in keep:
                    out.append(len(p).to_bytes(2, "big") + p)
            if out:
                body = len(out).to_bytes(2, "big") + b"".join(out)
                g.write(struct.pack(">qI", ns, len(body)) + body)
                frames += 1
                packets += len(out)
    return {"file": os.path.basename(dst), "from": start, "to": end, "frames": frames, "packets": packets}


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {"tokens": TOKENS, "windows": [cut(*w) for w in WINDOWS], "candles": {}}
    env = load_env()
    tok = session_token(env)
    bodies = {}
    for itok in TOKENS:
        bodies[str(itok)] = {}
        for _, start, end, tag in WINDOWS:
            q = urllib.parse.urlencode({"from": f"2026-10-08 {start[:5]}:00", "to": f"2026-10-08 {end[:5]}:00",
                                        "oi": 1})
            st, raw = call("GET", f"/instruments/historical/{itok}/minute?{q}", tok, env["KITE_API_KEY"])
            body = raw.decode() if isinstance(raw, bytes) else raw
            assert st == 200, (itok, st)
            bodies[str(itok)][tag] = body
            summary["candles"][f"{itok}/{tag}"] = len(json.loads(body)["data"]["candles"])
    with open(os.path.join(OUT, "candles-2026-10-08.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "Kite /instruments/historical/<token>/minute?oi=1, owner's account, fetched 2026-10-08",
                   "bodies": bodies}, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
