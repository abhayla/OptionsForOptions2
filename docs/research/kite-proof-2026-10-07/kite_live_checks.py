"""Throwaway live market-hours checks (master plan Stage 4a step 2; ADR-030 Phase-0; ADR-056 item 4). Data only.

Extends kite_core_proof.py (same login helpers). One owner login, then:
1. Subscribes NIFTY 50, SENSEX, INDIA VIX and every NIFTY (NFO) + SENSEX (BFO) option of the nearest 2 expiries, full
   mode, on one Kite WebSocket; records ticks for --minutes after the 09:15 IST anchor.
2. Forces one disconnect at anchor + --reconnect-at minutes, reconnects, measures the gap.
3. Flags stale data: the feed (no data frame for FEED_STALE_S) and each instrument (no tick for INST_STALE_S).
4. Persists every raw frame (receive time + bytes, gzip) outside the repo, for the later fan-out replay, and reads the
   file back at the end to prove it is complete.
5. Every 5 min: rebuilds both chains from ticks and checks our engine's IV/Greeks for internal consistency
   (Kite exposes no Greeks or IV, so there is nothing of Kite's to compare against).
6. Afterwards keeps the token in memory only and probes it until it stops working (next-morning expiry).
Writes summary.json (no personal data, no secrets) next to this file under live-<date>/.
No order endpoint is called anywhere in this file. The access token is never printed or written.
"""
import argparse, asyncio, csv, datetime as dt, gzip, hashlib, io, json, math, os, statistics, struct, sys, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "backend"))
from kite_core_proof import API, call, load_env, wait_for_request_token  # noqa: E402
from decimal import Decimal  # noqa: E402
from ofo.engine.black_scholes import (IST, NoImpliedVolatilityError, bs_greeks, bs_price,  # noqa: E402
                                      implied_volatility, year_fraction)
from ofo.engine.legs import Instrument  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

RATE = Decimal("0.065")  # Q248
FEED_STALE_S = 3.0
INST_STALE_S = 60.0
BUCKETS = [1, 2, 5, 10, 30, 60, 120, 300, 10**9]


def now_ist():
    return dt.datetime.now(IST)


def log(*a):
    print(now_ist().strftime("%H:%M:%S"), *a, flush=True)


# ---------- packet parsing (Kite WebSocket binary format) ----------
def parse_frame(b):
    if len(b) < 2:
        return []
    n = int.from_bytes(b[0:2], "big")
    off, out = 2, []
    for _ in range(n):
        ln = int.from_bytes(b[off:off + 2], "big")
        p = b[off + 2:off + 2 + ln]
        off += 2 + ln
        t = parse_packet(p)
        if t:
            out.append(t)
    return out


def parse_packet(p):
    ln = len(p)
    if ln < 8:
        return None
    token = struct.unpack(">I", p[0:4])[0]
    if ln in (28, 32):  # index
        f = struct.unpack(">iiiiii", p[4:28])
        t = {"token": token, "ltp": f[0], "high": f[1], "low": f[2], "open": f[3], "close": f[4], "kind": "index"}
        if ln == 32:
            t["exch_ts"] = struct.unpack(">i", p[28:32])[0]
        return t
    if ln == 8:
        return {"token": token, "ltp": struct.unpack(">i", p[4:8])[0], "kind": "ltp"}
    if ln >= 44:
        f = struct.unpack(">10i", p[4:44])
        t = {"token": token, "ltp": f[0], "last_qty": f[1], "avg": f[2], "volume": f[3], "buy_qty": f[4],
             "sell_qty": f[5], "open": f[6], "high": f[7], "low": f[8], "close": f[9], "kind": "quote"}
        if ln >= 184:
            g = struct.unpack(">5i", p[44:64])
            t.update(kind="full", ltt=g[0], oi=g[1], oi_high=g[2], oi_low=g[3], exch_ts=g[4])
            depth = [struct.unpack(">iih2x", p[64 + 12 * i:76 + 12 * i]) for i in range(10)]
            t["bid"] = depth[0][1] if depth[0][1] > 0 else 0
            t["ask"] = depth[5][1] if depth[5][1] > 0 else 0
        return t
    return None


# ---------- instruments ----------
def load_instruments():
    with urllib.request.urlopen(API + "/instruments", timeout=120) as r:
        rows = list(csv.DictReader(io.TextIOWrapper(r, encoding="utf-8")))
    today = dt.date.today()
    idx = {}
    for x in rows:
        if x["segment"] == "INDICES" and (x["exchange"], x["tradingsymbol"]) in (
                ("NSE", "NIFTY 50"), ("BSE", "SENSEX"), ("NSE", "INDIA VIX")):
            idx[x["tradingsymbol"]] = x
    chains = {}
    for name, exch in (("NIFTY", "NFO"), ("SENSEX", "BFO")):
        opts = [x for x in rows if x["name"] == name and x["exchange"] == exch and x["instrument_type"] in ("CE", "PE")
                and x["expiry"] and dt.date.fromisoformat(x["expiry"]) >= today]
        exps = sorted({dt.date.fromisoformat(x["expiry"]) for x in opts})[:2]
        for e in exps:
            chains[(name, e)] = [x for x in opts if x["expiry"] == e.isoformat()]
    return idx, chains


# ---------- state ----------
class State:
    def __init__(self, meta):
        self.meta = meta  # token -> dict
        self.latest = {}
        self.count = {t: 0 for t in meta}
        self.last_rx = {}
        self.hist = {t: [0] * len(BUCKETS) for t in meta}
        self.frames = 0
        self.data_frames = 0
        self.heartbeats = 0
        self.ticks = 0
        self.text_msgs = {}
        self.last_data_rx = None
        self.lag = []  # receive wall time - exchange timestamp (s), sampled
        self.feed_stale = False
        self.events = []
        self.timeline = []
        self.snapshots = []
        self.disconnects = []
        self.reconnect = {}

    def on_tick(self, t, rx_mono, rx_wall):
        tok = t["token"]
        if tok not in self.meta:
            return
        prev = self.last_rx.get(tok)
        if prev is not None:
            d = rx_mono - prev
            for i, edge in enumerate(BUCKETS):
                if d <= edge:
                    self.hist[tok][i] += 1
                    break
        self.last_rx[tok] = rx_mono
        self.count[tok] += 1
        self.ticks += 1
        old = self.latest.get(tok, {})
        old.update(t)
        self.latest[tok] = old
        if "exch_ts" in t and self.ticks % 50 == 0:
            self.lag.append(rx_wall - t["exch_ts"])


def event(st, kind, **kw):
    e = {"at": now_ist().isoformat(timespec="milliseconds"), "event": kind, **kw}
    st.events.append(e)
    log("EVENT", json.dumps(e))


# ---------- engine consistency snapshot ----------
def d2(paise):
    return Decimal(int(paise)) / 100


def snapshot(st, idx_tokens, chains_by_key):
    ts = now_ist()
    out = {"at": ts.isoformat(timespec="seconds"), "chains": {}}
    vix_tok = idx_tokens.get("INDIA VIX")
    if vix_tok and vix_tok in st.latest:
        out["india_vix"] = float(d2(st.latest[vix_tok]["ltp"]))
    for (name, exp), toks in chains_by_key.items():
        spot_tok = idx_tokens["NIFTY 50" if name == "NIFTY" else "SENSEX"]
        c = {"contracts": len(toks), "ticked": sum(1 for t in toks if st.count[t] > 0),
             "with_bid_and_ask": sum(1 for t in toks if st.latest.get(t, {}).get("bid") and st.latest[t].get("ask")),
             "with_oi": sum(1 for t in toks if st.latest.get(t, {}).get("oi"))}
        out["chains"][f"{name} {exp}"] = c
        if spot_tok not in st.latest:
            c["iv"] = "no spot tick yet"
            continue
        spot = d2(st.latest[spot_tok]["ltp"])
        try:
            years = year_fraction(ts, exp)
        except ValueError as e:
            c["iv"] = f"skipped: {e}"
            continue
        T, r = float(years), float(RATE)
        by = {}
        for t in toks:
            m = st.meta[t]
            by[(m["strike"], m["type"])] = t
        strikes = sorted({k for k, _ in by})
        atm = min(strikes, key=lambda k: abs(k - spot))
        i = strikes.index(atm)
        near = strikes[max(0, i - 10): i + 11]

        def px(t):
            q = st.latest.get(t)
            if not q:
                return None, None
            if q.get("bid") and q.get("ask"):
                return round((q["bid"] + q["ask"]) / 2), "mid"
            return (q["ltp"], "ltp") if q.get("ltp") else (None, None)

        fwds = []
        rows = []
        for k in near:
            ct, pt = by.get((k, "CE")), by.get((k, "PE"))
            cp, cs = px(ct) if ct else (None, None)
            pp, ps = px(pt) if pt else (None, None)
            rows.append((k, ct, pt, cp, cs, pp, ps))
            if cs == "mid" and ps == "mid":
                fwds.append(float(k) + (cp - pp) / 100 * math.exp(r * T))
        if not fwds:
            c["iv"] = "no strike with bid and ask on both sides"
            continue
        F = statistics.median(fwds)
        s_eff = Decimal(repr(F * math.exp(-r * T))).quantize(Decimal("0.01"))
        c.update(spot=float(spot), parity_forward=round(F, 2), effective_spot=float(s_eff),
                 basis_points=round(float(s_eff - spot), 2), forward_spread=round(max(fwds) - min(fwds), 2),
                 years=float(years), strikes_checked=len(near))
        fails, rt, gap_spot, gap_fwd, ivs, greek_bad, n_ok = [], [], [], [], [], [], 0
        for k, ct, pt, cp, cs, pp, ps in rows:
            pair = {}
            for kind, price in ((Instrument.CE, cp), (Instrument.PE, pp)):
                if not price:
                    fails.append(f"{k}{kind.value}: no price")
                    continue
                P = d2(price)
                try:
                    iv_s = implied_volatility(kind, P, spot, k, years, RATE)
                    iv_f = implied_volatility(kind, P, s_eff, k, years, RATE)
                except (NoImpliedVolatilityError, ValueError) as e:
                    fails.append(f"{k}{kind.value} @{P}: {str(e)[:60]}")
                    continue
                n_ok += 1
                rt.append(abs(bs_price(kind, s_eff, k, years, RATE, iv_f) - P))
                g = bs_greeks(kind, s_eff, k, years, RATE, iv_f)
                ok = g.gamma >= 0 and g.vega >= 0 and (0 <= g.delta <= 1 if kind is Instrument.CE else -1 <= g.delta <= 0)
                if not ok:
                    greek_bad.append(f"{k}{kind.value} {g}")
                ivs.append(float(iv_f))
                pair[kind] = (float(iv_s), float(iv_f), g)
                if k == atm:
                    c[f"atm_{kind.value}"] = {"price": float(P), "iv_on_spot": float(iv_s), "iv_on_forward": float(iv_f),
                                              "delta": float(g.delta), "gamma": float(g.gamma),
                                              "theta_per_day": float(g.theta), "vega": float(g.vega)}
            if len(pair) == 2:
                gap_spot.append(abs(pair[Instrument.CE][0] - pair[Instrument.PE][0]))
                gap_fwd.append(abs(pair[Instrument.CE][1] - pair[Instrument.PE][1]))
        c.update(iv_solved=n_ok, iv_failed=len(fails), iv_fail_samples=fails[:6],
                 iv_min=min(ivs) if ivs else None, iv_max=max(ivs) if ivs else None,
                 roundtrip_max_rupees=float(max(rt)) if rt else None,
                 ce_pe_iv_gap_median_on_spot=round(statistics.median(gap_spot), 4) if gap_spot else None,
                 ce_pe_iv_gap_median_on_forward=round(statistics.median(gap_fwd), 4) if gap_fwd else None,
                 greek_sign_violations=greek_bad[:6])
    return out


# ---------- websocket run ----------
async def run_ws(key, token, st, tokens, raw_path, anchor, end_at, reconnect_at):
    url = "wss://ws.kite.trade?" + urllib.parse.urlencode({"api_key": key, "access_token": token})
    raw = gzip.open(raw_path, "wb", compresslevel=1)
    forced_done = False
    stop = asyncio.Event()
    idx_tokens = st.idx_tokens
    chains_by_key = st.chains_by_key

    async def sampler():
        next_snap = time.monotonic() + 30
        while not stop.is_set():
            await asyncio.sleep(5)
            m = time.monotonic()
            feed_age = (m - st.last_data_rx) if st.last_data_rx else None
            stale_now = feed_age is None or feed_age > FEED_STALE_S
            if stale_now != st.feed_stale:
                st.feed_stale = stale_now
                event(st, "feed_stale" if stale_now else "feed_live", feed_age_s=round(feed_age or -1, 2))
            ages = [m - st.last_rx[t] for t in st.last_rx]
            row = {"at": now_ist().strftime("%H:%M:%S"), "feed_age_s": round(feed_age, 2) if feed_age else None,
                   "feed_stale": stale_now, "never_ticked": len(tokens) - len(st.last_rx),
                   "inst_stale_gt_60s": sum(a > INST_STALE_S for a in ages) + (len(tokens) - len(st.last_rx)),
                   "age_gt_5s": sum(a > 5 for a in ages), "age_gt_30s": sum(a > 30 for a in ages),
                   "age_gt_120s": sum(a > 120 for a in ages), "ticks": st.ticks}
            st.timeline.append(row)
            if m >= next_snap:
                next_snap = m + 300
                try:
                    s = snapshot(st, idx_tokens, chains_by_key)
                    st.snapshots.append(s)
                    log("SNAPSHOT", json.dumps(s)[:600])
                except Exception as e:  # throwaway proof: record, keep running
                    event(st, "snapshot_error", error=repr(e)[:200])
                write_summary(st)
            if now_ist() >= end_at:
                stop.set()

    samp = asyncio.create_task(sampler())
    attempt = 0
    while not stop.is_set():
        try:
            async with connect(url, max_size=None, open_timeout=15, ping_interval=20) as ws:
                attempt = 0
                t_conn = time.monotonic()
                await ws.send(json.dumps({"a": "subscribe", "v": tokens}))
                await ws.send(json.dumps({"a": "mode", "v": ["full", tokens]}))
                event(st, "connected", subscribed=len(tokens))
                if st.reconnect.get("closed_mono") and "connected_after_s" not in st.reconnect:
                    st.reconnect["connected_after_s"] = round(t_conn - st.reconnect["closed_mono"], 3)
                while not stop.is_set():
                    if not forced_done and now_ist() >= reconnect_at:
                        forced_done = True
                        st.reconnect.update(closed_at=now_ist().isoformat(timespec="milliseconds"),
                                            closed_mono=time.monotonic(),
                                            last_data_before_mono=st.last_data_rx)
                        event(st, "forced_disconnect")
                        await ws.close()
                        if PAUSE_S:
                            event(st, "forced_pause", seconds=PAUSE_S)
                            await asyncio.sleep(PAUSE_S)
                        break
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    rx_m, rx_w = time.monotonic(), time.time()
                    if isinstance(msg, str):
                        try:
                            typ = json.loads(msg).get("type", "?")
                        except ValueError:
                            typ = "unparsed"
                        st.text_msgs[typ] = st.text_msgs.get(typ, 0) + 1
                        continue
                    raw.write(struct.pack(">qI", time.time_ns(), len(msg)) + msg)
                    st.frames += 1
                    if len(msg) < 2:
                        st.heartbeats += 1
                        continue
                    st.data_frames += 1
                    if st.reconnect.get("closed_mono") and "first_data_after_s" not in st.reconnect:
                        st.reconnect["first_data_after_s"] = round(rx_m - st.reconnect["closed_mono"], 3)
                        lb = st.reconnect.get("last_data_before_mono")
                        if lb:
                            st.reconnect["data_gap_s"] = round(rx_m - lb, 3)
                        event(st, "data_resumed", **{k: v for k, v in st.reconnect.items() if not k.endswith("mono")})
                    st.last_data_rx = rx_m
                    for t in parse_frame(msg):
                        st.on_tick(t, rx_m, rx_w)
        except Exception as e:
            st.disconnects.append({"at": now_ist().isoformat(timespec="seconds"), "error": type(e).__name__,
                                   "detail": str(e)[:160].replace(token, "<token>")})
            event(st, "disconnect", error=type(e).__name__)
        if stop.is_set():
            break
        attempt += 1
        await asyncio.sleep(min(30, 1 if forced_done and attempt == 1 else 2 ** min(attempt, 4)))
    await samp
    raw.close()


def verify_raw(raw_path, expected_frames):
    n, ticks, size = 0, 0, os.path.getsize(raw_path)
    with gzip.open(raw_path, "rb") as f:
        while True:
            h = f.read(12)
            if len(h) < 12:
                break
            _, ln = struct.unpack(">qI", h)
            b = f.read(ln)
            if len(b) < ln:
                break
            n += 1
            ticks += len(parse_frame(b))
    return {"file": raw_path, "bytes_gz": size, "frames_read_back": n, "frames_written": expected_frames,
            "ticks_read_back": ticks, "complete": n == expected_frames}


SUMMARY = None
PAUSE_S = 0.0


def write_summary(st, extra=None):
    hist_all = [0] * len(BUCKETS)
    for h in st.hist.values():
        for i, v in enumerate(h):
            hist_all[i] += v
    per_seg = {}
    for t, m in st.meta.items():
        k = m["group"]
        s = per_seg.setdefault(k, {"contracts": 0, "ticked": 0, "ticks": 0})
        s["contracts"] += 1
        s["ticked"] += st.count[t] > 0
        s["ticks"] += st.count[t]
    lag = sorted(st.lag)
    data = {
        "written_at": now_ist().isoformat(timespec="seconds"),
        "subscribed": len(st.meta), "frames": st.frames, "data_frames": st.data_frames, "heartbeats": st.heartbeats,
        "ticks": st.ticks, "text_messages_by_type": st.text_msgs, "per_group": per_seg,
        "inter_tick_histogram_s": dict(zip([f"<={b}" for b in BUCKETS[:-1]] + [">300"], hist_all)),
        "exchange_lag_s": {"n": len(lag), "p50": lag[len(lag) // 2] if lag else None,
                           "p95": lag[int(len(lag) * .95)] if lag else None},
        "reconnect": {k: v for k, v in st.reconnect.items() if not k.endswith("mono")},
        "unplanned_disconnects": st.disconnects, "events": st.events, "snapshots": st.snapshots,
        "staleness_timeline": st.timeline, "thresholds": {"feed_stale_s": FEED_STALE_S, "inst_stale_s": INST_STALE_S},
        "kite_exposes_greeks_or_iv": False,
    }
    if extra:
        data.update(extra)
    os.makedirs(os.path.dirname(SUMMARY), exist_ok=True)
    tmp = SUMMARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(tmp, SUMMARY)


def probe(key, token):
    s, raw = call("GET", "/quote/ltp?" + urllib.parse.urlencode({"i": "NSE:NIFTY 50"}), token, key)
    if s == 200:
        return s, None
    try:
        return s, json.loads(raw).get("error_type")
    except ValueError:
        return s, "unparsed"


def token_watch(key, token, extra):
    stop_at = dt.datetime.combine(dt.date.today() + dt.timedelta(days=1), dt.time(10, 0), IST)
    extra["token_expiry"] = te = {"probes": 0}
    while now_ist() < stop_at:
        s, err = probe(key, token)
        te["probes"] += 1
        t = now_ist().isoformat(timespec="seconds")
        if s == 200:
            te["last_ok"] = t
        else:
            te.update(first_fail=t, http=s, error_type=err)
            log("TOKEN expired", s, err)
            return
        h = now_ist().hour
        time.sleep(60 if 4 <= h < 9 else 900)
    te["note"] = "still valid at stop time"


def main():
    global SUMMARY, PAUSE_S
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--reconnect-at", type=int, default=15)
    ap.add_argument("--ticks-dir", default=r"D:\Abhay\Ventures\ofo-kite-ticks")
    ap.add_argument("--no-token-watch", action="store_true")
    ap.add_argument("--tag", default="", help="summary folder suffix, e.g. pm")
    ap.add_argument("--pause-s", type=float, default=0.0, help="wait this long after the forced disconnect")
    ap.add_argument("--end", default="", help="HH:MM IST end time; overrides --minutes")
    a = ap.parse_args()
    PAUSE_S = a.pause_s
    day = dt.date.today().isoformat()
    SUMMARY = os.path.join(HERE, f"live-{day}" + (f"-{a.tag}" if a.tag else ""), "summary.json")
    tick_dir = os.path.join(a.ticks_dir, day)
    os.makedirs(tick_dir, exist_ok=True)

    env = load_env()
    key, secret = env.get("KITE_API_KEY", ""), env.get("KITE_API_SECRET", "")
    if not key or not secret:
        sys.exit("KITE_API_KEY / KITE_API_SECRET missing in .env")
    idx, chains = load_instruments()
    meta = {}
    for sym, x in idx.items():
        meta[int(x["instrument_token"])] = {"symbol": sym, "group": "INDEX", "type": "INDEX"}
    chains_by_key = {}
    for (name, exp), legs in chains.items():
        toks = []
        for x in legs:
            t = int(x["instrument_token"])
            meta[t] = {"symbol": x["tradingsymbol"], "group": f"{name} {exp}", "type": x["instrument_type"],
                       "strike": Decimal(x["strike"]).quantize(Decimal("0.01")), "expiry": exp.isoformat(),
                       "lot": int(x["lot_size"])}
            toks.append(t)
        chains_by_key[(name, exp)] = toks
        log(f"CHAIN {name} {exp} contracts {len(toks)}")
    tokens = sorted(meta)
    log(f"SUBSCRIBE {len(tokens)} instruments (limit 3000 per connection)")
    with open(os.path.join(tick_dir, "instruments.json"), "w", encoding="utf-8") as f:
        json.dump({str(t): m for t, m in meta.items()}, f, indent=0, default=str)

    print("LOGIN_URL https://kite.zerodha.com/connect/login?v=3&api_key=" + key, flush=True)
    got = wait_for_request_token(timeout_s=3 * 3600)
    if got.get("status") != "success" or not got.get("request_token"):
        sys.exit(f"login not completed (status={got.get('status')!r})")
    checksum = hashlib.sha256((key + got["request_token"] + secret).encode()).hexdigest()
    s, raw = call("POST", "/session/token", form={"api_key": key, "request_token": got["request_token"],
                                                   "checksum": checksum})
    sess = json.loads(raw)
    if s != 200:
        sys.exit(f"session failed HTTP {s}: {sess.get('error_type')}")
    token = sess["data"]["access_token"]
    del sess, raw
    log("SESSION ok (token held in memory only)")

    n = now_ist()
    anchor = max(n, n.replace(hour=9, minute=15, second=0, microsecond=0))
    end_at = anchor + dt.timedelta(minutes=a.minutes)
    if a.end:
        hh, mm = map(int, a.end.split(":"))
        end_at = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
    reconnect_at = anchor + dt.timedelta(minutes=a.reconnect_at)
    log(f"WINDOW anchor {anchor:%H:%M:%S} reconnect {reconnect_at:%H:%M:%S} end {end_at:%H:%M:%S}")
    st = State(meta)
    st.idx_tokens = {m["symbol"]: t for t, m in meta.items() if m["group"] == "INDEX"}
    st.chains_by_key = chains_by_key
    raw_path = os.path.join(tick_dir, f"frames-{n:%H%M%S}.bin.gz")
    extra = {"window": {"anchor": anchor.isoformat(), "end": end_at.isoformat(), "reconnect_at": reconnect_at.isoformat(),
                        "started": n.isoformat(timespec="seconds")}}
    asyncio.run(run_ws(key, token, st, tokens, raw_path, anchor, end_at, reconnect_at))
    try:
        st.snapshots.append(snapshot(st, st.idx_tokens, chains_by_key))
    except Exception as e:
        event(st, "snapshot_error", error=repr(e)[:200])
    extra["history"] = verify_raw(raw_path, st.frames)
    log("HISTORY", json.dumps(extra["history"]))
    write_summary(st, extra)
    log("TICKS DONE summary", SUMMARY)
    if not a.no_token_watch:
        log("TOKEN WATCH started (probe every 15 min, every 1 min from 04:00 to 09:00 IST)")
        try:
            token_watch(key, token, extra)
        finally:
            write_summary(st, extra)
    log("ALL DONE")


if __name__ == "__main__":
    main()
