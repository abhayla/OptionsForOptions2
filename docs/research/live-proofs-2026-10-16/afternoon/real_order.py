"""Real 1-lot test order (ADR-097). READ-ONLY toward Kite: this script never places, modifies or cancels an order.

fetch  (run with MAIN's backend: no egress gate): snapshot holdings, pick a cheap OTM NIFTY CE (nearest weekly, best
       ask 2-6 covering one lot), read funds and Zerodha's basket margin for exactly that order; save to fetch.json.
build  (run in the W-080 worktree, offline): build the plan, run freeze_check and the margin gate (ADR-094 top-up by
       hand) on the saved replies, build the basket with W-080's build_basket, write basket.html whose ONE button posts
       the basket form to Kite's basket page. The owner reviews there and presses Execute.
after  (MAIN's backend): snapshot holdings / orders / trades / positions / funds; holdings must equal the fetch snapshot.
Outputs: D:/Abhay/Ventures/ofo-kite-ticks/<day>/real-order/ (outside the repo: account data)."""
import asyncio
import csv
import datetime as dt
import html
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from decimal import Decimal

assert os.environ["DATABASE_URL"].rstrip("/").endswith("/ofo_dev"), "ofo_dev only"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
OUT = os.path.join("D:/Abhay/Ventures/ofo-kite-ticks", NOW.date().isoformat(), "real-order")
os.makedirs(OUT, exist_ok=True)
FETCH = os.path.join(OUT, "fetch.json")
MAX_PREMIUM, MIN_PREMIUM = Decimal("6.00"), Decimal("2.00")
READ_PATHS = ("/portfolio/", "/instruments/", "/quote", "/user/margins", "/orders", "/trades")


def kite(key, tok, method, path, body=None, raw=False):
    ok = (method == "GET" and path.startswith(READ_PATHS)) or (method == "POST" and path.startswith("/margins/basket"))
    if not ok:
        raise SystemExit(f"REFUSED {method} {path}: read-only script")  # never an order call (ADR-097)
    req = urllib.request.Request("https://api.kite.trade" + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Kite-Version": "3", "Authorization": f"token {key}:{tok}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        data = r.read()
    return data.decode() if raw else json.loads(data, parse_float=Decimal)


def session():
    from ofo_app.broker_config import load_broker_config
    from ofo_app.broker_crypto import TokenCipher
    from ofo_app.broker_token_store import access_token_for
    from ofo_app.db import close_db, get_engine

    async def go():
        cfg = load_broker_config()
        try:
            async with get_engine().connect() as conn:
                return cfg.api_key, await access_token_for(conn, "owner", TokenCipher(cfg.token_key), engine=get_engine())
        finally:
            await close_db()
    key, tok = asyncio.run(go())
    assert tok, "no stored Kite session"
    return key, tok


def holdings(key, tok):
    return {f"{h['exchange']}:{h['tradingsymbol']}": {"quantity": str(h["quantity"]), "t1": str(h.get("t1_quantity")),
                                                      "collateral": str(h.get("collateral_quantity"))}
            for h in kite(key, tok, "GET", "/portfolio/holdings")["data"]}


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)


def fetch():
    key, tok = session()
    hold = holdings(key, tok)
    dump(os.path.join(OUT, f"holdings-before-{NOW:%H%M%S}.json"), hold)
    print("holdings before:", len(hold), "symbols")
    rows = list(csv.DictReader(io.StringIO(kite(key, tok, "GET", "/instruments/NFO", raw=True))))
    nifty = [r for r in rows if r["name"] == "NIFTY" and r["instrument_type"] == "CE"]
    expiry = min(r["expiry"] for r in nifty if r["expiry"] >= NOW.date().isoformat())
    spot = kite(key, tok, "GET", "/quote/ltp?i=" + urllib.parse.quote("NSE:NIFTY 50"))["data"]["NSE:NIFTY 50"]["last_price"]
    cands = sorted((r for r in nifty if r["expiry"] == expiry and Decimal(r["strike"]) > spot),
                   key=lambda r: Decimal(r["strike"]))[:30]
    q = kite(key, tok, "GET", "/quote?" + "&".join("i=" + urllib.parse.quote("NFO:" + r["tradingsymbol"]) for r in cands))
    pick = ask = None
    for r in cands:
        d = q["data"].get("NFO:" + r["tradingsymbol"])
        sells = [x for x in d["depth"]["sell"] if x["quantity"] > 0] if d else []
        if sells and MIN_PREMIUM <= Decimal(str(sells[0]["price"])) <= MAX_PREMIUM \
                and sells[0]["quantity"] >= int(r["lot_size"]):
            pick, ask = r, Decimal(str(sells[0]["price"]))
            break
    assert pick, "no CE with a best ask between 2 and 6 covering one lot"
    assert pick["exchange"] == "NFO" and pick["instrument_type"] == "CE"  # ADR-097 (1)
    order = {"exchange": "NFO", "tradingsymbol": pick["tradingsymbol"], "transaction_type": "BUY", "variety": "regular",
             "product": "NRML", "order_type": "LIMIT", "quantity": int(pick["lot_size"]), "price": float(ask)}
    margin_raw = kite(key, tok, "POST", "/margins/basket?consider_positions=true", [order], raw=True)
    margin = json.loads(margin_raw, parse_float=Decimal)
    funds = kite(key, tok, "GET", "/user/margins")["data"]["equity"]["net"]
    dump(FETCH, {"at": NOW.isoformat(), "spot": spot, "expiry": expiry, "row": pick, "ask": ask, "order": order,
                 "margin_raw": margin_raw, "funds": funds, "quote": q["data"]["NFO:" + pick["tradingsymbol"]]})
    print("spot", spot, "expiry", expiry, "pick", pick["tradingsymbol"], "ask", ask, "lot", pick["lot_size"],
          "| kite margin", margin["data"]["final"]["total"], "| funds", funds)


def build():
    from ofo.engine import Action, Instrument, Leg
    from ofo.execution.basket import KITE_BASKET_URL, build_basket
    from ofo.execution.freeze import StoredFreeze, freeze_check
    from ofo.execution.margin_gate import check_margin, required_from_basket_reply
    from ofo.execution.planned import ExecutionPlan, PlannedLeg
    from ofo.instruments.catalogue import Catalogue
    from ofo.instruments.models import ZERODHA
    from ofo.instruments.parser import parse_instruments_rows
    from ofo_app.broker_config import load_broker_config

    f = json.load(open(FETCH, encoding="utf-8"), parse_float=Decimal)
    age = (NOW - dt.datetime.fromisoformat(f["at"])).total_seconds()
    assert age < 600, f"fetch.json is {age:.0f}s old; run fetch again"
    row, ask = f["row"], Decimal(str(f["ask"]))
    sym, lot = row["tradingsymbol"], int(row["lot_size"])
    cat = Catalogue()
    cat.load(parse_instruments_rows([row]))
    (entry,) = cat.entries_for_broker_symbol(ZERODHA, sym)
    c = entry.contract
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", sym, Leg(Action.BUY, Instrument(c.instrument_type), c.strike,
                                                            c.expiry, lot, ask)),))
    rep, funds = json.loads(f["margin_raw"], parse_float=Decimal)["data"], Decimal(str(f["funds"]))
    seen = {}

    def margin_gate(orders):
        assert [(o.tradingsymbol, o.quantity, o.price) for o in orders] == [(sym, lot, ask)], "orders differ from fetch"
        kite_total = required_from_basket_reply(rep)
        topup = sum((max(Decimal(0), Decimal(o.quantity) * o.price - ro["option_premium"])
                     for o, ro in zip(orders, rep["orders"], strict=True) if o.transaction_type == "BUY"), Decimal(0))
        seen.update(kite_total=kite_total, topup=topup)
        return check_margin(funds, kite_total + topup)  # ADR-094 by hand until its builder lands

    freeze = StoredFreeze(limit=3511, lot=65, file_date=dt.date(2026, 10, 15))  # F-36, NSE file of 15 Oct 2026
    basket = build_basket(plan, cat, 1, freeze_check=lambda p: freeze_check(p, {sym: freeze}, today=NOW.date()),
                          margin_check=margin_gate)
    o = basket.orders[0]
    assert (o.exchange, o.product, o.order_type, o.transaction_type, o.quantity) == ("NFO", "NRML", "LIMIT", "BUY", lot)
    fields = basket.form_fields(load_broker_config().api_key)
    dump(os.path.join(OUT, f"basket-{NOW:%H%M%S}.json"), {"data": fields["data"], **seen, "funds": funds})
    page = f"""<!doctype html><meta charset="utf-8"><title>Real test order</title>
<style>body{{font:16px system-ui;margin:24px;max-width:760px}}td,th{{border:1px solid #999;padding:6px}}
button{{font-size:18px;padding:10px 18px}}</style>
<h2>Real test order, 1 lot (ADR-097), prepared {NOW:%H:%M:%S} IST</h2>
<table><tr><th>Contract</th><th>Exch</th><th>Side</th><th>Qty</th><th>Price</th><th>Product</th></tr>
<tr><td>{html.escape(sym)}</td><td>NFO</td><td>BUY</td><td>{lot} (1 lot)</td><td>LIMIT {ask}</td><td>NRML</td></tr></table>
<p>Premium Rs {Decimal(lot) * ask} plus charges. Zerodha margin {seen['kite_total']} + top-up {seen['topup']}; funds {funds}.</p>
<p>The button opens Kite's basket page. Nothing is placed until YOU press Execute on Kite.</p>
<form method="post" action="{KITE_BASKET_URL}">
<input type="hidden" name="api_key" value="{html.escape(fields['api_key'])}">
<input type="hidden" name="data" value="{html.escape(fields['data'])}">
<button type="submit">Open this basket on Kite</button></form>"""
    p = os.path.join(OUT, "basket.html")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(page)
    print("basket:", fields["data"])
    print("margin: kite", seen["kite_total"], "topup", seen["topup"], "funds", funds, "-> allowed")
    print("PAGE", p)


def after():
    key, tok = session()
    first = sorted(x for x in os.listdir(OUT) if x.startswith("holdings-before-"))[0]
    before = json.load(open(os.path.join(OUT, first), encoding="utf-8"))
    now = holdings(key, tok)
    dump(os.path.join(OUT, f"holdings-after-{NOW:%H%M%S}.json"), now)
    for name, path in (("orders", "/orders"), ("trades", "/trades"), ("positions", "/portfolio/positions"),
                       ("margins", "/user/margins")):
        dump(os.path.join(OUT, f"{name}-{NOW:%H%M%S}.json"), kite(key, tok, "GET", path))
    diff = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
    print("holdings unchanged:", not diff, "| changed:", diff)


{"fetch": fetch, "build": build, "after": after}[sys.argv[1]]()
