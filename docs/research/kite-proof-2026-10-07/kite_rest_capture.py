"""Throwaway capture of Kite REST replies during market hours (2026-10-08 afternoon). Data only - no order is placed.

Saves market replies (quote, ltp, ohlc, basket margin, charges, historical candles) to rest-<date>/ next to this
file. For personal endpoints (profile, funds, positions, holdings, orders, trades) it saves ONLY the key structure
and value types, never a value. The access token stays in memory and is never printed or written.
"""
import csv, datetime as dt, hashlib, io, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kite_core_proof import API, call, load_env, session_token  # noqa: E402

OUT = os.path.join(HERE, f"rest-{dt.date.today().isoformat()}")


def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)


def shape(v):
    if isinstance(v, dict):
        return {k: shape(x) for k, x in v.items()}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    return type(v).__name__


def main():
    os.makedirs(OUT, exist_ok=True)
    env = load_env()
    key = env["KITE_API_KEY"]
    tok = session_token(env)
    log = {}

    with urllib.request.urlopen(API + "/instruments", timeout=120) as r:
        rows = list(csv.DictReader(io.TextIOWrapper(r, encoding="utf-8")))
    today = dt.date.today()

    def legs(name, exch):
        o = [x for x in rows if x["name"] == name and x["exchange"] == exch and x["instrument_type"] in ("CE", "PE")
             and dt.date.fromisoformat(x["expiry"]) >= today]
        e = min(dt.date.fromisoformat(x["expiry"]) for x in o if dt.date.fromisoformat(x["expiry"]) > today)
        return e, {(float(x["strike"]), x["instrument_type"]): x for x in o if x["expiry"] == e.isoformat()}

    s, raw = call("GET", "/quote/ltp?" + urllib.parse.urlencode([("i", "NSE:NIFTY 50"), ("i", "BSE:SENSEX")]), tok, key)
    spot = json.loads(raw)["data"]
    n = spot["NSE:NIFTY 50"]["last_price"]
    atm = round(n / 50) * 50
    exp, by = legs("NIFTY", "NFO")
    picks = [by[(float(atm + d), t)] for d in (-200, -100, 0, 100, 200) for t in ("CE", "PE") if (float(atm + d), t) in by]
    ks = [f"NFO:{x['tradingsymbol']}" for x in picks] + ["NSE:NIFTY 50", "BSE:SENSEX"]
    for ep in ("quote", "quote/ltp", "quote/ohlc"):
        s, raw = call("GET", f"/{ep}?" + urllib.parse.urlencode([("i", k) for k in ks]), tok, key)
        save(ep.replace("/", "_") + ".json", json.loads(raw))
        log[ep] = s
    ic = [(by[(float(atm + 200), "CE")], "SELL"), (by[(float(atm + 400), "CE")], "BUY"),
          (by[(float(atm - 200), "PE")], "SELL"), (by[(float(atm - 400), "PE")], "BUY")]
    basket = [{"exchange": "NFO", "tradingsymbol": x["tradingsymbol"], "transaction_type": side, "variety": "regular",
               "product": "NRML", "order_type": "LIMIT", "quantity": int(x["lot_size"]), "price": 0} for x, side in ic]
    q = json.loads(open(os.path.join(OUT, "quote.json")).read()).get("data", {})
    s2, rawq = call("GET", "/quote?" + urllib.parse.urlencode([("i", f"NFO:{x['tradingsymbol']}") for x, _ in ic]), tok, key)
    qq = json.loads(rawq).get("data", {})
    for b in basket:
        b["price"] = qq.get(f"NFO:{b['tradingsymbol']}", {}).get("last_price", 0)
    s, raw = call("POST", "/margins/basket?consider_positions=false", tok, key, body=basket)
    save("margins_basket.json", {"request": basket, "reply": json.loads(raw)})
    log["margins/basket"] = s
    s, raw = call("POST", "/margins/orders", tok, key, body=basket)
    save("margins_orders.json", {"request": basket, "reply": json.loads(raw)})
    log["margins/orders"] = s
    charges = [dict(order_id=f"t{i}", exchange="NFO", tradingsymbol=b["tradingsymbol"], transaction_type=b["transaction_type"],
                    variety="regular", product="NRML", order_type="LIMIT", quantity=b["quantity"],
                    average_price=b["price"]) for i, b in enumerate(basket)]
    s, raw = call("POST", "/charges/orders", tok, key, body=charges)
    save("charges_orders.json", {"request": charges, "reply": json.loads(raw)})
    log["charges/orders"] = s
    fr = dt.datetime.now().strftime("%Y-%m-%d 09:15:00")
    to = dt.datetime.now().strftime("%Y-%m-%d %H:%M:00")
    for label, token, interval in (("nifty50_minute", 256265, "minute"), ("nifty50_day", 256265, "day"),
                                   ("option_minute", int(picks[4]["instrument_token"]), "minute")):
        frm = fr if interval == "minute" else (today - dt.timedelta(days=30)).isoformat() + " 00:00:00"
        s, raw = call("GET", f"/instruments/historical/{token}/{interval}?" + urllib.parse.urlencode(
            {"from": frm, "to": to, "oi": 1}), tok, key)
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"unparsed": raw[:200].decode(errors="replace")}
        candles = (body.get("data") or {}).get("candles", [])
        save(f"historical_{label}.json", {"http": s, "status": body.get("status"), "error_type": body.get("error_type"),
                                          "count": len(candles), "first": candles[:3], "last": candles[-3:]})
        log[f"historical {label}"] = (s, len(candles))
    for ep in ("user/profile", "user/margins", "portfolio/positions", "portfolio/holdings", "orders", "trades"):
        s, raw = call("GET", "/" + ep, tok, key)
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        save("shape_" + ep.replace("/", "_") + ".json", {"http": s, "shape": shape(body.get("data"))})
        log[ep] = s
    save("capture_log.json", {"at": dt.datetime.now().isoformat(timespec="seconds"), "http": log, "atm": atm,
                              "expiry": exp.isoformat()})
    print("DONE", json.dumps(log), flush=True)


if __name__ == "__main__":
    main()
