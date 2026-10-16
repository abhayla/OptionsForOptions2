"""Record read-only Kite REST replies for the weekend: /margins/basket for many shapes (incl. BUY limits above live,
ADR-094), /charges/orders for the same shapes, /user/margins, /quote (depth) for the shape legs. Every N minutes until
--end. NO order is placed: margins/basket and charges/orders are calculations. Run via dev_run.py from the main checkout.
Writes one JSON per round to D:/Abhay/Ventures/ofo-kite-ticks/<day>/rest/."""
import argparse
import asyncio
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
DAY = dt.date.today().isoformat()
TICKS = os.path.join("D:/Abhay/Ventures/ofo-kite-ticks", DAY)
OUT = os.path.join(TICKS, "rest")
FORBIDDEN = ("/orders", "/gtt")  # never: placement endpoints (ADR-054/097); charges/orders is the one read-only POST


def call(key, tok, method, path, body=None):
    if any(path.startswith(p) for p in FORBIDDEN):
        raise SystemExit(f"REFUSED placement path {path}")
    req = urllib.request.Request("https://api.kite.trade" + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Kite-Version": "3", "Authorization": f"token {key}:{tok}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed Kite host
            return {"status": r.status, "body": json.loads(r.read(), parse_float=Decimal)}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", "replace")[:2000]}


def chain(meta, group):
    return {(m["type"], Decimal(m["strike"])): (m["symbol"], m["lot"]) for m in meta.values() if m["group"] == group}


def shapes(spot, ch, step, exch, lot):
    atm = (Decimal(spot) / step).quantize(Decimal("1")) * step
    s = lambda t, k: ch.get((t, atm + k * step))  # noqa: E731
    out = {}
    def leg(t, k, side, lots=1):
        x = s(t, k)
        return None if x is None else {"exchange": exch, "tradingsymbol": x[0], "transaction_type": side,
                                       "variety": "regular", "product": "NRML", "order_type": "LIMIT",
                                       "quantity": x[1] * lots}
    defs = {
        "buy_ce_otm": [leg("CE", 4, "BUY")], "buy_pe_otm": [leg("PE", -4, "BUY")],
        "sell_ce_otm": [leg("CE", 4, "SELL")], "sell_pe_otm": [leg("PE", -4, "SELL")],
        "buy_ce_atm_2lots": [leg("CE", 0, "BUY", 2)],
        "bull_call_spread": [leg("CE", 0, "BUY"), leg("CE", 2, "SELL")],
        "bear_put_spread": [leg("PE", 0, "BUY"), leg("PE", -2, "SELL")],
        "short_straddle": [leg("CE", 0, "SELL"), leg("PE", 0, "SELL")],
        "long_strangle": [leg("CE", 3, "BUY"), leg("PE", -3, "BUY")],
        "iron_condor": [leg("PE", -6, "BUY"), leg("PE", -3, "SELL"), leg("CE", 3, "SELL"), leg("CE", 6, "BUY")],
    }
    for name, legs in defs.items():
        if all(legs):
            out[name] = legs
    return out


def price_legs(legs, ltp, bump):
    res = []
    for o in legs:
        p = Decimal(str(ltp[f"{o['exchange']}:{o['tradingsymbol']}"]["last_price"]))
        lim = max(Decimal("0.05"), p + bump if o["transaction_type"] == "BUY" else p - bump)
        res.append({**o, "price": float(lim.quantize(Decimal("0.05")))})
    return res


async def token():
    cfg = load_broker_config()
    try:
        async with get_engine().connect() as conn:
            return cfg.api_key, await access_token_for(conn, "owner", TokenCipher(cfg.token_key), engine=get_engine())
    finally:
        await close_db()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="15:31")
    ap.add_argument("--every", type=int, default=20)
    a = ap.parse_args()
    key, tok = asyncio.run(token())
    assert tok, "no stored session"
    os.makedirs(OUT, exist_ok=True)
    meta = json.load(open(os.path.join(TICKS, "instruments.json"), encoding="utf-8"))
    groups = sorted({m["group"] for m in meta.values() if m["group"] != "INDEX"})
    nifty_g = next(g for g in groups if g.startswith("NIFTY"))
    sensex_g = next(g for g in groups if g.startswith("SENSEX"))
    hh, mm = map(int, a.end.split(":"))
    end = dt.datetime.now(IST).replace(hour=hh, minute=mm, second=0, microsecond=0)
    n = 0
    while dt.datetime.now(IST) < end:
        t0 = dt.datetime.now(IST)
        rec = {"at": t0.isoformat(timespec="seconds"), "groups": [nifty_g, sensex_g], "calls": []}
        idx = call(key, tok, "GET", "/quote/ltp?i=NSE:NIFTY%2050&i=BSE:SENSEX")["body"]["data"]
        for g, spot_key, step, exch in ((nifty_g, "NSE:NIFTY 50", 50, "NFO"), (sensex_g, "BSE:SENSEX", 100, "BFO")):
            spot = idx[spot_key]["last_price"]
            sh = shapes(spot, chain(meta, g), step, exch, None)
            syms = sorted({f"{o['exchange']}:{o['tradingsymbol']}" for legs in sh.values() for o in legs})
            q = "&".join("i=" + urllib.parse.quote(s) for s in syms)
            quote = call(key, tok, "GET", "/quote?" + q)
            rec["calls"].append({"what": f"quote {g}", "spot": spot, "reply": quote})
            ltp = quote["body"]["data"] if quote["status"] == 200 else {}
            for name, legs in sh.items():
                for bump in (Decimal("0"), Decimal("2"), Decimal("5")):
                    if bump and not any(o["transaction_type"] == "BUY" for o in legs):
                        continue
                    orders = price_legs(legs, ltp, bump)
                    for cp in ("true", "false") if bump == 0 else ("true",):
                        r = call(key, tok, "POST", f"/margins/basket?consider_positions={cp}", orders)
                        rec["calls"].append({"what": f"margins/basket {g} {name} bump={bump} cp={cp}",
                                             "request": orders, "reply": r})
                        time.sleep(0.4)
                    if bump == 0:
                        ch = call(key, tok, "POST", "/charges/orders",
                                  [{**o, "order_id": f"r{i}", "average_price": o["price"]} for i, o in enumerate(orders)])
                        rec["calls"].append({"what": f"charges/orders {g} {name}", "request": orders, "reply": ch})
                        time.sleep(0.4)
        rec["calls"].append({"what": "user/margins", "reply": call(key, tok, "GET", "/user/margins")})
        rec["calls"].append({"what": "portfolio/positions", "reply": call(key, tok, "GET", "/portfolio/positions")})
        path = os.path.join(OUT, f"rest-{t0:%H%M%S}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1, default=str)
        bad = sum(1 for c in rec["calls"] if c["reply"]["status"] != 200)
        n += 1
        print(f"{t0:%H:%M:%S} ROUND {n} calls {len(rec['calls'])} non200 {bad} -> {path}", flush=True)
        nxt = t0 + dt.timedelta(minutes=a.every)
        while dt.datetime.now(IST) < min(nxt, end):
            time.sleep(5)
    print("REST DONE rounds", n, flush=True)


main()
