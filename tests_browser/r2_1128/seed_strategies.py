"""Lane TC set-up: paper strategies through the real HTTP routes of the app (the throwaway database only).
Prints one line per call so a refusal is visible. Entry prices are typed (paper)."""
import json
import subprocess
import sys

import httpx

import os

BASE = os.environ["TC_API_BASE"]
PSQL = ["psql", "-Atc"]  # connection comes from the PG* environment variables
ENV = {**os.environ}


def cid(token: int) -> int:
    out = subprocess.run(PSQL + [f"select id from catalogue_contracts where exchange_token={token} and exchange_segment='NSE_FO'"],
                         capture_output=True, text=True, env=ENV).stdout.strip()
    return int(out)


LOT = 65


def make(name, legs):
    body = {"underlying": "NIFTY", "name": name,
            "legs": [{"contract_id": cid(t), "action": a, "quantity": LOT} for t, a, _ in legs]}
    r = httpx.post(BASE + "/strategies", json=body, timeout=30)
    print("create", name, r.status_code, r.text[:200])
    sid = r.json().get("id") if r.status_code == 201 else None
    return sid


def orders(sid, legs, kind="open", confirmed=True):
    body = {"orders": [{"contract_id": cid(t), "side": a, "quantity": LOT, "price": p, "kind": kind} for t, a, p in legs],
            "prices_not_live_confirmed": confirmed}
    r = httpx.post(f"{BASE}/paper/strategies/{sid}/orders", json=body, timeout=30)
    print("orders", sid, kind, r.status_code, r.text[:260])
    return r.status_code


IC = [(44732, "SELL", "88.00"), (44746, "BUY", "45.00"), (44721, "SELL", "70.00"), (44715, "BUY", "38.00")]
STR = [(44730, "SELL", "64.00"), (44727, "SELL", "66.00")]
UNP = [(44740, "SELL", "55.00"), (44745, "SELL", "57.00")]
DONE = [(44728, "SELL", "98.00")]
LONGNAME = [(44720, "SELL", "150.00"), (44739, "SELL", "30.00")]
if __name__ == "__main__":
    for name, legs in [("TC Condor Running 1", IC), ("TC Strangle Open", STR), ("TC Unpriced Trade", UNP),
                       ("TC Completed Trade", DONE), ("Wide Iron Condor 20x", LONGNAME)]:
        sid = make(name, legs)
        if sid:
            orders(sid, legs)
            if name == "TC Completed Trade":
                orders(sid, [(44728, "BUY", "90.00")], kind="exit")
