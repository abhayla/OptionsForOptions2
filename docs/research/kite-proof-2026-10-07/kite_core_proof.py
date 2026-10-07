"""Throwaway core proof (master plan Stage 4a step 1; ADR-051): owner's own Kite account, data only, no orders.

1. Prints the Kite login URL; the owner logs in on Zerodha's own page.
2. Catches the redirect on http://127.0.0.1:8765/kite/callback, exchanges request_token for an access token
   (kept in memory only - never printed, never written to disk).
3. Reads the public instrument list, picks real contracts, fetches quotes (NIFTY 50, SENSEX, 3 NIFTY + 3 SENSEX
   options) and the basket margin of one 4-leg NIFTY iron condor.
4. Writes the raw JSON replies (no personal data) to the scratchpad `proof/` folder and prints a short summary.
No order endpoint is called anywhere in this file.
"""
import csv, hashlib, http.server, io, json, os, re, sys, threading, time, urllib.parse, urllib.request, datetime as dt

ENV = r"D:\Abhay\Ventures\OptionsForOptions2\.env"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proof")
API = "https://api.kite.trade"


def load_env():
    vals = {}
    for line in open(ENV, encoding="utf-8"):
        m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if m:
            vals[m.group(1)] = m.group(2)
    return vals


def call(method, path, token=None, key=None, form=None, body=None):
    headers = {"X-Kite-Version": "3"}
    data = None
    if token:
        headers["Authorization"] = f"token {key}:{token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def wait_for_request_token(timeout_s=600):
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["status"] = (q.get("status") or [""])[0]
            got["request_token"] = (q.get("request_token") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Login received. You can close this tab and go back to Claude.".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8765), H)
    srv.timeout = 2
    end = time.time() + timeout_s
    while "request_token" not in got and time.time() < end:
        srv.handle_request()
    srv.server_close()
    return got


def main():
    os.makedirs(OUT, exist_ok=True)
    env = load_env()
    key, secret = env.get("KITE_API_KEY", ""), env.get("KITE_API_SECRET", "")
    if not key or not secret:
        sys.exit("KITE_API_KEY / KITE_API_SECRET missing in .env")
    print("LOGIN_URL https://kite.zerodha.com/connect/login?v=3&api_key=" + key, flush=True)
    got = wait_for_request_token()
    if got.get("status") != "success" or not got.get("request_token"):
        sys.exit(f"login not completed (status={got.get('status')!r})")
    checksum = hashlib.sha256((key + got["request_token"] + secret).encode()).hexdigest()
    st, raw = call("POST", "/session/token", form={"api_key": key, "request_token": got["request_token"],
                                                    "checksum": checksum})
    sess = json.loads(raw)
    if st != 200:
        sys.exit(f"session failed HTTP {st}: {sess.get('error_type')} {sess.get('message')}")
    token = sess["data"]["access_token"]
    print("SESSION ok (token held in memory only)", flush=True)

    # Instruments (public file) - pick real contracts.
    with urllib.request.urlopen(API + "/instruments", timeout=60) as r:
        rows = list(csv.DictReader(io.TextIOWrapper(r, encoding="utf-8")))
    today = dt.date.today()

    def chain(name, exch):
        opts = [x for x in rows if x["name"] == name and x["exchange"] == exch and x["instrument_type"] in ("CE", "PE")
                and x["expiry"] and dt.date.fromisoformat(x["expiry"]) >= today]
        exp = min(dt.date.fromisoformat(x["expiry"]) for x in opts)
        return exp, [x for x in opts if x["expiry"] == exp.isoformat()]

    st, raw = call("GET", "/quote?" + urllib.parse.urlencode([("i", "NSE:NIFTY 50"), ("i", "BSE:SENSEX")]), token, key)
    idx = json.loads(raw)
    open(os.path.join(OUT, "quote_index.json"), "w").write(json.dumps(idx, indent=1))
    spot = {"NIFTY": idx["data"]["NSE:NIFTY 50"]["last_price"], "SENSEX": idx["data"]["BSE:SENSEX"]["last_price"]}
    print("SPOT", spot, flush=True)

    picks, ic = [], None
    for name, exch, step in (("NIFTY", "NFO", 50), ("SENSEX", "BFO", 100)):
        exp, legs = chain(name, exch)
        atm = round(spot[name] / step) * step
        by = {(float(x["strike"]), x["instrument_type"]): x for x in legs}
        for k in (atm - step, atm, atm + step):
            if (k, "CE") in by:
                picks.append(by[(k, "CE")])
        if name == "NIFTY":
            def g(k, t):
                return by.get((float(k), t))
            ic = [(g(atm + 200, "CE"), "SELL"), (g(atm + 400, "CE"), "BUY"),
                  (g(atm - 200, "PE"), "SELL"), (g(atm - 400, "PE"), "BUY")]
        print(f"CHAIN {name} expiry {exp} contracts {len(legs)} atm {atm}", flush=True)

    keys = [f"{x['exchange']}:{x['tradingsymbol']}" for x in picks]
    st, raw = call("GET", "/quote?" + urllib.parse.urlencode([("i", k) for k in keys]), token, key)
    q = json.loads(raw)
    open(os.path.join(OUT, "quote_options.json"), "w").write(json.dumps(q, indent=1))
    for x in picks:
        d = q.get("data", {}).get(f"{x['exchange']}:{x['tradingsymbol']}", {})
        print(f"QUOTE {x['tradingsymbol']} exch_token {x['exchange_token']} ltp {d.get('last_price')} "
              f"oi {d.get('oi')} lot {x['lot_size']} ts {d.get('timestamp')}", flush=True)

    basket = [{"exchange": leg["exchange"], "tradingsymbol": leg["tradingsymbol"], "transaction_type": side,
               "variety": "regular", "product": "NRML", "order_type": "MARKET", "quantity": int(leg["lot_size"]),
               "price": 0} for leg, side in ic if leg]
    st, raw = call("POST", "/margins/basket?consider_positions=false", token, key, body=basket)
    m = json.loads(raw)
    open(os.path.join(OUT, "margin_basket.json"), "w").write(json.dumps({"request": basket, "reply": m}, indent=1))
    if st == 200:
        init = m["data"]["initial"]["total"]
        final = m["data"]["final"]["total"]
        print(f"MARGIN iron condor {[b['tradingsymbol'] + ' ' + b['transaction_type'] for b in basket]} "
              f"initial {init} final {final}", flush=True)
    else:
        print(f"MARGIN failed HTTP {st}: {m.get('error_type')} {m.get('message')}", flush=True)
    print("DONE files in", OUT, flush=True)


if __name__ == "__main__":
    main()
