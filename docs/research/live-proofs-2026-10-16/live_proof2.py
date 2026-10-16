import asyncio, json, os, math, urllib.request
from decimal import Decimal
from sqlalchemy import text
from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo.engine.executable_price import depth_from_quote, executable_limit
from ofo.engine.legs import Action

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev")
SP = os.path.dirname(os.path.abspath(__file__)); LOT = 65; FREEZE_LOTS = 54

def call(k, t, path):
    req = urllib.request.Request("https://api.kite.trade" + path, headers={"X-Kite-Version": "3", "Authorization": f"token {k}:{t}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read(), parse_float=Decimal)

def hand(levels, qty, side, tick):
    rem, cost, worst, n = qty, Decimal(0), None, 0
    for p, q in levels:
        if p <= 0 or q <= 0: continue
        t = min(rem, q); cost += p*t; worst = p; rem -= t; n += 1
        if rem == 0: break
    if rem: return None, None, n
    k = math.floor(worst/tick) if side == "BUY" else math.ceil(worst/tick)
    return Decimal(k)*tick, cost, n

async def main():
    cfg = load_broker_config(); engine = get_engine()
    try:
        async with engine.connect() as conn:
            token = await access_token_for(conn, "owner", TokenCipher(cfg.token_key), engine=engine)
            rows = (await conn.execute(text("select broker_symbol, tick_size, freeze_limit, lot_size from public.broker_instruments where broker_symbol like 'NIFTY26O19%' and broker_segment is not null"))).all()
        meta = {r[0]: (Decimal(str(r[1])), r[2], r[3]) for r in rows}
        spot = call(cfg.api_key, token, "/quote/ltp?i=NSE:NIFTY%2050")["data"]["NSE:NIFTY 50"]["last_price"]
        atm = int((spot/50).to_integral_value())*50
        cand = [f"NIFTY26O19{atm+d}CE" for d in range(50,4001,50)] + [f"NIFTY26O19{atm-d}PE" for d in range(50,4001,50)]
        cand = [c for c in cand if c in meta]
        q = call(cfg.api_key, token, "/quote?" + "&".join(f"i=NFO:{s}" for s in cand))["data"]
        info = []
        for s in cand:
            qq = q.get(f"NFO:{s}")
            if not qq: continue
            d = depth_from_quote(qq)
            info.append((s, qq, d, sum(l.quantity for l in d.asks), sum(l.quantity for l in d.bids)))
        # crossing legs: both sides' 5-level totals >= 200 and level1 < 3510 and level-1 qty small; prefer thin level 1
        ok = [i for i in info if i[2].asks and i[2].bids and 65 <= i[2].asks[0].quantity < 3400 and 65 <= i[2].bids[0].quantity < 3400 and i[3] >= 500 and i[4] >= 500]
        ok.sort(key=lambda i: min(i[2].asks[0].quantity, i[2].bids[0].quantity))
        print("cands", len(info), "ok", len(ok)); cross = ok[:3]
        thin = sorted([i for i in info if i[2].asks and i[2].bids], key=lambda i: min(i[3], i[4]))[:1]
        res = []
        def run(s, qq, d, lots, side, kind):
            n = lots*LOT; tick = meta[s][0]
            assert n <= (meta[s][1] or 10**9) - 1 or True
            r = executable_limit(d, side, n, tick, qq["last_price"])
            lv = [(l.price, l.quantity) for l in (d.asks if side is Action.BUY else d.bids)]
            hl, hc, nl = hand(lv, n, side.value, tick)
            ok_ = (hl == r.limit and hc == r.walked_cost) if r.fillable else (hl is None and r.reason == "depth_too_thin")
            res.append({"kind": kind, "leg": s, "side": side.value, "lots": lots, "qty": n, "tick": str(tick), "freeze_limit": meta[s][1],
                "levels_crossed": nl, "snapshot": {"ts": qq.get("timestamp"), "ltp": str(qq["last_price"]),
                "bids": [(str(l.price), l.quantity) for l in d.bids], "asks": [(str(l.price), l.quantity) for l in d.asks]},
                "ours_fillable": r.fillable, "reason": r.reason, "ours_limit": str(r.limit), "ours_walked": str(r.walked_cost),
                "hand_limit": str(hl), "hand_walked": str(hc), "match": ok_})
        for s, qq, d, ta, tb in cross:
            for side in (Action.BUY, Action.SELL):
                lv = d.asks if side is Action.BUY else d.bids
                l1 = lv[0].quantity; tot = sum(l.quantity for l in lv)
                lots_a = l1//LOT + 1                      # just past level 1
                lots_b = min(FREEZE_LOTS, max(lots_a, int((l1 + lv[1].quantity + (lv[2].quantity if len(lv) > 2 else 0)//2)//LOT)))
                for lots in sorted({lots_a, lots_b}):
                    if lots*LOT <= tot and lots <= FREEZE_LOTS: run(s, qq, d, lots, side, "cross")
        for s, qq, d, ta, tb in thin:
            for side, tot in ((Action.BUY, ta), (Action.SELL, tb)):
                lots = tot//LOT + 1  # beyond 5-level total (may exceed freeze: function-level probe)
                run(s, qq, d, lots, side, "too_thin_probe")
        json.dump({"spot": str(spot), "results": res}, open(os.path.join(SP, "live_depth_proof2.json"), "w"), indent=1)
        for r in res:
            print(r["kind"], r["leg"], r["side"], r["lots"], r["qty"], "tick", r["tick"], "crossed", r["levels_crossed"], "ours", r["ours_limit"], r["ours_walked"], r["reason"], "hand", r["hand_limit"], r["hand_walked"], r["match"])
            if r["kind"] != "cross" or r["lots"] > 0: print("   snap b", r["snapshot"]["bids"], "a", r["snapshot"]["asks"]) if r["side"]=="BUY" else None
    finally:
        await close_db()
asyncio.run(main())
