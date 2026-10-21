"""Live proof of today's merged code on main (READ-ONLY toward Kite: quotes, /margins/basket, /user/margins).
ADR-094: margin_verdict / fetch_basket_margin on fresh BUY-above-live baskets (NIFTY + SENSEX), required = Zerodha's
final.total + sum max(0, qty x limit - option_premium), recomputed here from the same raw reply.
ADR-095: protected_limits on the live depth of a NIFTY iron condor, Rs 300 tolerance; fills_within per leg.
Run via dev_run.py from the main checkout. Writes D:/Abhay/Ventures/ofo-kite-ticks/<day>/live-proof-pm.json."""
import asyncio
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from decimal import Decimal

from ofo.engine import Action
from ofo.engine.executable_price import depth_from_quote
from ofo.engine import price_protection as pp
from ofo_app.broker_config import load_broker_config
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import access_token_for
from ofo_app.db import close_db, get_engine
from ofo_app.kite_margin import BasketOrder, KiteMargin, margin_verdict

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
OUT = os.path.join("D:/Abhay/Ventures/ofo-kite-ticks", NOW.date().isoformat(), "live-proof-pm.json")
TICK = Decimal("0.05")


async def session():
    cfg = load_broker_config()
    try:
        async with get_engine().connect() as conn:
            return cfg.api_key, await access_token_for(conn, "owner", TokenCipher(cfg.token_key))
    finally:
        await close_db()


def get(key, tok, path):
    assert path.startswith(("/quote", "/instruments/")), path
    req = urllib.request.Request("https://api.kite.trade" + path,
                                 headers={"X-Kite-Version": "3", "Authorization": f"token {key}:{tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return r.read().decode()


def chain(key, tok, exch, name, step, spot_key):
    import csv
    import io
    rows = [r for r in csv.DictReader(io.StringIO(get(key, tok, f"/instruments/{exch}")))
            if r["name"] == name and r["instrument_type"] in ("CE", "PE")]
    expiry = min(r["expiry"] for r in rows if r["expiry"] >= NOW.date().isoformat())
    spot = Decimal(str(json.loads(get(key, tok, "/quote/ltp?i=" + urllib.parse.quote(spot_key)),
                                  parse_float=Decimal)["data"][spot_key]["last_price"]))
    atm = (spot / step).quantize(Decimal(1)) * step
    by = {(r["instrument_type"], Decimal(r["strike"])): r for r in rows if r["expiry"] == expiry}
    return spot, atm, by, expiry


def quotes(key, tok, exch, syms):
    q = "&".join("i=" + urllib.parse.quote(f"{exch}:{s}") for s in syms)
    return json.loads(get(key, tok, "/quote?" + q), parse_float=Decimal)["data"]


def main():
    key, tok = asyncio.run(session())
    client = KiteMargin(api_key=key, access_token=tok)
    out = {"at": NOW.isoformat(timespec="seconds"), "adr094": [], "adr095": None}
    for exch, name, step, spot_key in (("NFO", "NIFTY", 50, "NSE:NIFTY 50"), ("BFO", "SENSEX", 100, "BSE:SENSEX")):
        spot, atm, by, expiry = chain(key, tok, exch, name, Decimal(step), spot_key)
        legs = [by[("CE", atm + 3 * step)], by[("PE", atm - 3 * step)]]
        q = quotes(key, tok, exch, [r["tradingsymbol"] for r in legs])
        orders = [BasketOrder(exch, r["tradingsymbol"], "BUY", "NRML", "LIMIT", int(r["lot_size"]),
                              Decimal(str(q[f"{exch}:{r['tradingsymbol']}"]["last_price"])) + Decimal(5))
                  for r in legs]
        bm = client.fetch_basket_margin(orders)
        verdict = margin_verdict(client, orders)
        row = {"exch": exch, "expiry": expiry, "orders": [(o.tradingsymbol, o.quantity, str(o.price)) for o in orders],
               "zerodha_total": str(bm.zerodha_total), "required_total": str(bm.required_total),
               "per_order_kite": [(m.tradingsymbol, str(m.total)) for m in bm.orders],
               "verdict_allowed": verdict.allowed, "verdict_available": str(verdict.available),
               "verdict_required": str(verdict.required)}
        out["adr094"].append(row)
        print("ADR-094", exch, "zerodha", bm.zerodha_total, "required", bm.required_total,
              "topup", bm.required_total - bm.zerodha_total, "| funds", verdict.available, "allowed", verdict.allowed)
    spot, atm, by, expiry = chain(key, tok, "NFO", "NIFTY", Decimal(50), "NSE:NIFTY 50")
    shape = [("PE", -6, Action.BUY), ("PE", -3, Action.SELL), ("CE", 3, Action.SELL), ("CE", 6, Action.BUY)]
    rows = [(by[(t, atm + k * 50)], side) for t, k, side in shape]
    q = quotes(key, tok, "NFO", [r["tradingsymbol"] for r, _ in rows])
    inputs = []
    for r, side in rows:
        qq = q["NFO:" + r["tradingsymbol"]]
        inputs.append((r["tradingsymbol"], side, int(r["lot_size"]), Decimal(str(qq["last_price"])), depth_from_quote(qq)))
    out["adr095_inputs"] = [(s, side.value, n, str(p)) for s, side, n, p, _ in inputs]
    out["adr095_quotes"] = {k: {"last_price": str(v["last_price"]), "depth": v["depth"]} for k, v in q.items()}
    res = pp.protected_limits([pp.PlannedLeg(side, n, p, d) for _, side, n, p, d in inputs], Decimal("300"), TICK)
    out["adr095"] = {"tolerance": "300", "total_adverse": str(res.total_adverse),
                     "legs": [{"symbol": s, "side": lg.side.value, "planned": str(lg.planned_price),
                               "share": str(lg.share), "limit": str(lg.limit), "adverse": str(lg.adverse),
                               "fills_within": lg.fills_within, "executable_limit": str(lg.executable_limit)}
                              for (s, *_), lg in zip(inputs, res.legs, strict=True)]}
    for leg in out["adr095"]["legs"]:
        print("ADR-095", leg)
    print("ADR-095 total adverse", res.total_adverse, "<= 300:", res.total_adverse <= Decimal(300))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print("WROTE", OUT)
    return inputs


if __name__ == "__main__":
    main()
