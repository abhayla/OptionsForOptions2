"""Throwaway capture (2026-10-15, market hours) of the real Kite replies 4b needs for the owner's planned first order:
BUY 1 lot of a far out-of-the-money NIFTY option on the nearest weekly expiry, LIMIT, premium about Rs 5 or less
(master plan 4b note, 2026-10-15). Data only: no order endpoint is called. Saves to rest-<date>-order/ next to this
file: the chosen contracts' instrument rows, full quotes with depth, order margin, basket margin and charges for the
planned BUY (and the exit SELL), for a CE and a PE candidate. The token is never printed."""
import csv, datetime as dt, io, json, os, sys, urllib.parse, urllib.request
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kite_core_proof import API, call, load_env, session_token  # noqa: E402

OUT = os.path.join(HERE, f"rest-{dt.date.today().isoformat()}-order")
MAX_PREMIUM = Decimal("5")


def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)


def main():
    os.makedirs(OUT, exist_ok=True)
    env = load_env()
    key = env["KITE_API_KEY"]
    tok = session_token(env)
    with urllib.request.urlopen(API + "/instruments/NFO", timeout=120) as r:
        rows = [x for x in csv.DictReader(io.TextIOWrapper(r, encoding="utf-8")) if x["name"] == "NIFTY"
                and x["instrument_type"] in ("CE", "PE")]
    today = dt.date.today()
    exp = min(dt.date.fromisoformat(x["expiry"]) for x in rows if dt.date.fromisoformat(x["expiry"]) > today)
    chain = [x for x in rows if x["expiry"] == exp.isoformat()]
    s, raw = call("GET", "/quote/ltp?" + urllib.parse.urlencode([("i", "NSE:NIFTY 50")]), tok, key)
    spot = Decimal(str(json.loads(raw)["data"]["NSE:NIFTY 50"]["last_price"]))
    picks = {}
    for typ in ("CE", "PE"):
        side = sorted((x for x in chain if x["instrument_type"] == typ),
                      key=lambda x: Decimal(x["strike"]), reverse=(typ == "PE"))
        side = [x for x in side if (Decimal(x["strike"]) > spot if typ == "CE" else Decimal(x["strike"]) < spot)]
        keys = [f"NFO:{x['tradingsymbol']}" for x in side]
        ltp = {}
        for i in range(0, len(keys), 400):
            s, raw = call("GET", "/quote/ltp?" + urllib.parse.urlencode([("i", k) for k in keys[i:i + 400]]), tok, key)
            ltp.update({k: Decimal(str(v["last_price"])) for k, v in json.loads(raw)["data"].items()})
        # nearest-to-spot OTM contract whose premium is at most MAX_PREMIUM and still trades (LTP > 0)
        for x in side:
            p = ltp.get(f"NFO:{x['tradingsymbol']}", Decimal(0))
            if Decimal("0") < p <= MAX_PREMIUM:
                picks[typ] = (x, p)
                break
    log = {"spot": str(spot), "expiry": exp.isoformat(), "picks": {}}
    for typ, (x, p) in picks.items():
        sym = x["tradingsymbol"]
        lot = int(x["lot_size"])
        s, raw = call("GET", "/quote?" + urllib.parse.urlencode([("i", f"NFO:{sym}")]), tok, key)
        save(f"quote_{typ}.json", json.loads(raw))
        buy = {"exchange": "NFO", "tradingsymbol": sym, "transaction_type": "BUY", "variety": "regular",
               "product": "NRML", "order_type": "LIMIT", "quantity": lot, "price": float(p)}
        sell = dict(buy, transaction_type="SELL")
        s1, r1 = call("POST", "/margins/orders", tok, key, body=[buy])
        s2, r2 = call("POST", "/margins/basket?consider_positions=true", tok, key, body=[buy])
        ch = [dict(order_id="t1", exchange="NFO", tradingsymbol=sym, transaction_type="BUY", variety="regular",
                   product="NRML", order_type="LIMIT", quantity=lot, average_price=float(p)),
              dict(order_id="t2", exchange="NFO", tradingsymbol=sym, transaction_type="SELL", variety="regular",
                   product="NRML", order_type="LIMIT", quantity=lot, average_price=float(p))]
        s3, r3 = call("POST", "/charges/orders", tok, key, body=ch)
        save(f"order_margin_{typ}.json", {"request": buy, "reply": json.loads(r1)})
        save(f"basket_margin_{typ}.json", {"request": [buy], "reply": json.loads(r2)})
        save(f"charges_{typ}.json", {"request": ch, "reply": json.loads(r3)})
        save(f"instrument_{typ}.json", x)
        log["picks"][typ] = {"symbol": sym, "strike": x["strike"], "lot": lot, "tick_size": x["tick_size"],
                             "ltp": str(p), "premium_for_1_lot": str(p * lot),
                             "http": {"quote": s, "order_margin": s1, "basket_margin": s2, "charges": s3}}
    log["captured_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    save("capture_log.json", log)
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
