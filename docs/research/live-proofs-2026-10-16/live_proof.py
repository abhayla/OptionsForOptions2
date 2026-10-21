import asyncio, json, os, urllib.request, datetime
from decimal import Decimal
from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo_app.charge_rates_store import rates_in_force
from ofo.engine.executable_price import depth_from_quote, executable_limit
from ofo.engine.legs import Action
from ofo.charges.calculator import ChargeOrder, charges_for_order

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
SP = os.path.dirname(os.path.abspath(__file__))
LOT, TICK = 65, Decimal("0.05")

def call(k, t, method, path, body=None):
    req = urllib.request.Request("https://api.kite.trade" + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"X-Kite-Version": "3", "Authorization": f"token {k}:{t}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read(), parse_float=Decimal)

def hand(levels, qty, side):  # independent walk over (price, qty) list
    rem, cost, worst = qty, Decimal(0), None
    for p, q in levels:
        if p <= 0 or q <= 0: continue
        t = min(rem, q); cost += p*t; worst = p; rem -= t
        if rem == 0: break
    if rem: return None, None
    steps = int(worst / TICK) if worst % TICK == 0 else None
    import math
    n = worst / TICK
    k = math.floor(n) if side == "BUY" else math.ceil(n)
    return Decimal(k)*TICK, cost

async def main():
    cfg = load_broker_config(); engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key))
            rates = await rates_in_force(conn)
        spot = call(cfg.api_key, token, "GET", "/quote/ltp?i=NSE:NIFTY%2050")["data"]["NSE:NIFTY 50"]["last_price"]
        atm = int((spot / 50).to_integral_value()) * 50
        legs = [f"NIFTY26O19{atm}CE", f"NIFTY26O19{atm}PE", f"NIFTY26O19{atm+200}CE"]
        q = call(cfg.api_key, token, "GET", "/quote?" + "&".join(f"i=NFO:{s}" for s in legs))["data"]
        now = datetime.datetime.now().isoformat()
        depth_res, orders = [], []
        for s in legs:
            qq = q[f"NFO:{s}"]
            d = depth_from_quote(qq); ltp = qq["last_price"]
            snap = {"ts": qq.get("timestamp"), "ltp": str(ltp),
                    "bids": [(str(l["price"]), l["quantity"]) for l in qq["depth"]["buy"]],
                    "asks": [(str(l["price"]), l["quantity"]) for l in qq["depth"]["sell"]]}
            for lots in (1, 2):
                for side in (Action.BUY, Action.SELL):
                    n = lots*LOT
                    r = executable_limit(d, side, n, TICK, ltp)
                    lv = snap["asks"] if side is Action.BUY else snap["bids"]
                    hl, hc = hand([(Decimal(p), qt) for p, qt in lv], n, side.value)
                    ok = (hl == r.limit and hc == r.walked_cost) if r.fillable else hl is None
                    depth_res.append({"leg": s, "lots": lots, "side": side.value, "qty": n, "snapshot": snap,
                        "ours_limit": str(r.limit), "ours_walked": str(r.walked_cost), "ours_fillable": r.fillable, "reason": r.reason,
                        "hand_limit": str(hl), "hand_walked": str(hc), "match": ok})
                    if r.fillable:
                        orders.append((s, side.value, n, r.limit))
        json.dump({"at": now, "spot": str(spot), "tick_assumed": str(TICK), "results": depth_res}, open(os.path.join(SP, "live_depth_proof.json"), "w"), indent=1)
        body = [{"order_id": f"o{i}", "exchange": "NFO", "tradingsymbol": s, "transaction_type": sd, "variety": "regular",
                 "product": "NRML", "order_type": "LIMIT", "quantity": n, "average_price": float(p)} for i, (s, sd, n, p) in enumerate(orders)]
        rep = call(cfg.api_key, token, "POST", "/charges/orders", body)["data"]
        out = []
        for (s, sd, n, p), k in zip(orders, rep):
            c = k["charges"]
            o = charges_for_order(ChargeOrder("NSE_FO", sd, n, p), rates)
            kite = {"brokerage": c["brokerage"], "stt": c["transaction_tax"], "exchange_transaction": c["exchange_turnover_charge"],
                    "sebi": c["sebi_turnover_charge"], "stamp": c["stamp_duty"], "gst": c["gst"]["total"], "total": c["total"]}
            ours = {f: getattr(o, f) for f in kite}
            diff = {f: str(ours[f] - kite[f]) for f in kite}
            out.append({"order": [s, sd, n, str(p)], "ours": {f: str(v) for f, v in ours.items()},
                        "kite": {f: str(v) for f, v in kite.items()}, "diff": diff,
                        "ok_4dp_except_stamp": all(abs(ours[f]-kite[f]) < Decimal("0.00005") for f in kite if f not in ("stamp", "total"))})
        json.dump({"rates_read_on": str(rates.read_on), "source": rates.source_url, "orders": out}, open(os.path.join(SP, "live_charges_proof.json"), "w"), indent=1)
        print("rates", rates.read_on, "spot", spot, "legs", legs)
        for r in depth_res:
            print(r["leg"], r["lots"], r["side"], "ours", r["ours_limit"], r["ours_walked"], "hand", r["hand_limit"], r["hand_walked"], r["match"], r["reason"])
        for o in out: print(o["order"], o["ok_4dp_except_stamp"], o["diff"])
    finally:
        await close_db()
asyncio.run(main())
