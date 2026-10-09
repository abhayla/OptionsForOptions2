"""Throwaway core proof for master plan 4a step 7 (history recording; REQ-051 AC-3/AC-4, ADR-066). Data only.

Question: can 1-minute bars built from our own recorded Kite WebSocket ticks match Kite's own 1-minute historical
candles? If they do, the recorder can build the aggregated-intraday tier from the live feed (REQ-051 AC-4), and
Kite's candles are a fair backfill source for gaps (ADR-066).

Method:
- Reads the two raw recordings of 2026-10-08 (outside the repo) and parses every frame with the proven parser.
- Index rows: one bar per exchange-timestamp minute, OHLC of the index value.
- Option rows: a TRADE is a tick whose cumulative volume rose; it is bucketed by its last-trade time (ltt). Bar OHLC
  = trade prices; bar volume = rise of the cumulative volume inside the minute; OI = last OI seen in the minute.
- Fetches Kite's 1-minute candles (with OI) for the same instruments with the day's cached session (one login a day).
- Compares only minutes fully inside a recording window (the first and last minute of each file are partial).
Writes history-bars-2026-10-08.json next to this file: counts and mismatches only, no personal data, no token.
"""
import datetime as dt, gzip, json, os, struct, sys, urllib.parse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kite_core_proof import TICKS, call, load_env, session_token  # noqa: E402
from kite_live_checks import parse_frame  # noqa: E402

DAY = "2026-10-08"
RAW = os.path.join(TICKS, DAY)
FILES = ["frames-083808.bin.gz", "frames-144102.bin.gz"]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
INDEX = {256265: "NIFTY 50", 265: "SENSEX"}


def minute(epoch_s):
    return dt.datetime.fromtimestamp(epoch_s, IST).replace(second=0).strftime("%H:%M")


def read(path, bars, windows):
    first = last = None
    cum = {}  # token -> last cumulative volume
    with gzip.open(path, "rb") as f:
        while True:
            h = f.read(12)
            if len(h) < 12:
                break
            rx_ns, ln = struct.unpack(">qI", h)
            b = f.read(ln)
            if len(b) < ln:
                break
            rx = rx_ns / 1e9
            first = first if first is not None else rx
            last = rx
            for t in parse_frame(b):
                tok = t["token"]
                if t["kind"] == "index" and tok in INDEX and "exch_ts" in t:
                    m, px, vol_add = minute(t["exch_ts"]), t["ltp"], 0
                elif t["kind"] == "full":
                    prev = cum.get(tok)
                    cum[tok] = t["volume"]
                    if prev is None or t["volume"] <= prev:
                        if prev is None:
                            continue
                        # no new trade: still record OI for the minute of the exchange timestamp
                        bar = bars[tok].get(minute(t["exch_ts"]))
                        if bar:
                            bar["oi"] = t["oi"]
                        continue
                    m, px, vol_add = minute(t["ltt"]), t["ltp"], t["volume"] - prev
                else:
                    continue
                bar = bars[tok].get(m)
                if bar is None:
                    bars[tok][m] = bar = {"o": px, "h": px, "l": px, "c": px, "v": 0, "oi": t.get("oi")}
                bar["h"], bar["l"], bar["c"] = max(bar["h"], px), min(bar["l"], px), px
                bar["v"] += vol_add
                if t.get("oi") is not None:
                    bar["oi"] = t["oi"]
    windows.append((minute(first), minute(last)))


def main():
    bars, windows = defaultdict(dict), []
    for fn in FILES:
        read(os.path.join(RAW, fn), bars, windows)
        print("read", fn, "window", windows[-1], flush=True)
    # full minutes only: strictly after the first and before the last minute of each window, and in market hours
    full = set()
    for a, b in windows:
        t = dt.datetime.strptime(a, "%H:%M") + dt.timedelta(minutes=1)
        end = dt.datetime.strptime(b, "%H:%M")
        while t < end:
            s = t.strftime("%H:%M")
            if "09:15" <= s <= "15:29":
                full.add(s)
            t += dt.timedelta(minutes=1)
    opts = sorted((tok for tok in bars if tok not in INDEX), key=lambda k: -len(bars[k]))
    chosen = list(INDEX) + opts[:6] + opts[len(opts) // 2:len(opts) // 2 + 2]
    env = load_env()
    tok = session_token(env)
    key = env["KITE_API_KEY"]
    out = {"day": DAY, "windows": windows, "full_minutes": len(full), "instruments": []}
    for itok in chosen:
        q = urllib.parse.urlencode({"from": f"{DAY} 09:15:00", "to": f"{DAY} 15:30:00", "oi": 1})
        st, raw = call("GET", f"/instruments/historical/{itok}/minute?{q}", tok, key)
        candles = json.loads(raw)["data"]["candles"] if st == 200 else []
        kite = {c[0][11:16]: c for c in candles}
        mins = sorted(m for m in full if m in kite)
        ours = bars[itok]
        res = {"token": itok, "name": INDEX.get(itok, "option"), "http": st, "kite_candles": len(candles),
               "compared_minutes": len(mins), "missing_in_ours": 0, "ohlc_exact": 0, "close_exact": 0,
               "volume_exact": 0, "oi_exact": 0, "max_abs_diff": {"o": 0.0, "h": 0.0, "l": 0.0, "c": 0.0},
               "examples": []}
        for m in mins:
            k, o = kite[m], ours.get(m)
            if o is None:
                res["missing_in_ours"] += 1 if k[5] or itok in INDEX else 0
                continue
            mine = [o["o"] / 100, o["h"] / 100, o["l"] / 100, o["c"] / 100]
            diffs = [abs(round(x - y, 2)) for x, y in zip(mine, k[1:5])]
            for name, d in zip("ohlc", diffs):
                res["max_abs_diff"][name] = max(res["max_abs_diff"][name], d)
            res["ohlc_exact"] += all(d == 0 for d in diffs)
            res["close_exact"] += diffs[3] == 0
            if itok not in INDEX:
                res["volume_exact"] += o["v"] == k[5]
                res["oi_exact"] += o["oi"] == k[6]
            if any(diffs) and len(res["examples"]) < 3:
                res["examples"].append({"minute": m, "ours": mine + [o["v"], o["oi"]], "kite": k[1:]})
        out["instruments"].append(res)
        print(json.dumps({k: v for k, v in res.items() if k != "examples"}), flush=True)
    with open(os.path.join(HERE, f"history-bars-{DAY}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
