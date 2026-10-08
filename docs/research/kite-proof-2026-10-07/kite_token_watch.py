"""Throwaway: measure when the cached Kite token stops working (next-morning expiry). Data only.

Uses the encrypted cache of kite_core_proof.session_token without ever logging in (exits if there is no cached token).
Probes /quote/ltp every 15 minutes, every minute from 04:00 to 09:00 IST. A network error is recorded as
"network" and the watch continues; only an HTTP refusal from Kite ends it. Results go to token-watch-<date>.json.
"""
import base64, datetime as dt, json, os, sys, time, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kite_core_proof import CACHE, API, load_env  # noqa: E402
import urllib.request  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OUT = os.path.join(HERE, f"token-watch-{dt.date.today().isoformat()}.json")


def main():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    env = load_env()
    key = env["KITE_API_KEY"]
    blob = json.load(open(CACHE, encoding="utf-8"))
    tok = AESGCM(base64.urlsafe_b64decode(env["KITE_TOKEN_CACHE_KEY"])).decrypt(
        base64.b64decode(blob["nonce"]), base64.b64decode(blob["ct"]), key.encode()).decode()
    rec = {"started": dt.datetime.now(IST).isoformat(timespec="seconds"), "probes": 0, "network_errors": 0,
           "last_ok": None, "first_fail": None}
    stop = dt.datetime.combine(dt.date.today() + dt.timedelta(days=1), dt.time(10, 0), IST)
    while dt.datetime.now(IST) < stop:
        now = dt.datetime.now(IST).isoformat(timespec="seconds")
        req = urllib.request.Request(API + "/quote/ltp?i=NSE:NIFTY+50",
                                     headers={"X-Kite-Version": "3", "Authorization": f"token {key}:{tok}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
            rec["last_ok"] = now
        except urllib.error.HTTPError as e:
            try:
                et = json.loads(e.read()).get("error_type")
            except ValueError:
                et = "unparsed"
            rec.update(first_fail=now, http=e.code, error_type=et)
            json.dump(rec, open(OUT, "w"), indent=1)
            print("TOKEN expired", now, e.code, et, flush=True)
            return
        except Exception as e:  # DNS, timeout, Wi-Fi drop, sleep: not an expiry
            rec["network_errors"] += 1
            rec["last_network_error"] = f"{now} {type(e).__name__}"
        rec["probes"] += 1
        json.dump(rec, open(OUT, "w"), indent=1)
        h = dt.datetime.now(IST).hour
        time.sleep(60 if 4 <= h < 9 else 900)
    rec["note"] = "still valid at stop time"
    json.dump(rec, open(OUT, "w"), indent=1)


if __name__ == "__main__":
    main()
