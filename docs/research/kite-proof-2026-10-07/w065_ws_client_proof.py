"""W-065 core proof through the REAL route: a plain WebSocket client of the RUNNING API receives live strategy numbers.

Run during market hours against an API started with LIVE_MARKET=1 and the owner's stored Kite session:

    python docs/research/kite-proof-2026-10-07/w065_ws_client_proof.py [--base http://127.0.0.1:8766] [--seconds 60]

The client talks ONLY to the API (as a browser would; REQ-048 AC-5: no vendor connection): it reads the nearest NIFTY
expiry and its contracts from the leg-picker routes, opens ws://<base>/api/strategies/live, sends a provisional iron
condor to learn the live spot from the first push's ``spot_level``, then replaces it with the NIFTY iron condor around
the spot (sell +-200 rounded to 50, buy wings +-400, 1 lot) and records ``--seconds`` of pushes. It prints COUNTS ONLY
(no token exists on this path: the socket carries no credential).

Exit 0 only when: pushes >= 30, min gap >= 1.0 s, some leg's LTP changed, Unrealized P&L changed, every leg's health is
'available' in every push after the first tick. The summary is written to w065-ws-proof-<date>.json next to this file.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import pathlib
import sys
import time
import urllib.request
from decimal import Decimal

import websockets

HERE = pathlib.Path(__file__).resolve().parent
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
MIN_PUSHES, MIN_GAP, SPOT_WAIT = 30, 1.0, 45.0


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - a local API address given on the command line
        return json.loads(r.read().decode("utf-8"))


def chain_of(base: str) -> tuple[str, dict]:
    expiries = get_json(f"{base}/api/catalogue/NIFTY/expiries")["expiries"]
    expiry = sorted(expiries)[0]
    rows = get_json(f"{base}/api/catalogue/NIFTY/contracts?expiry={expiry}")["contracts"]
    chain = {(Decimal(r["strike"]), r["instrument_type"]): f"{r['exchange_segment']}:{r['exchange_token']}"
             for r in rows if r["instrument_type"] in ("CE", "PE")}
    return expiry, chain


def nearest(chain: dict, target: Decimal, kind: str) -> Decimal:
    return min((s for s, k in chain if k == kind), key=lambda s: abs(s - target))


def condor(chain: dict, centre: Decimal) -> tuple[dict, list[str]]:
    atm = (centre / 50).quantize(Decimal(1)) * 50
    picks = [("SELL", nearest(chain, atm + 200, "CE"), "CE"), ("BUY", nearest(chain, atm + 400, "CE"), "CE"),
             ("SELL", nearest(chain, atm - 200, "PE"), "PE"), ("BUY", nearest(chain, atm - 400, "PE"), "PE")]
    now = datetime.datetime.now(IST).isoformat()
    legs = [{"instrument_id": chain[(s, k)], "action": a, "lots": 1, "planned_entry": "1.00", "captured_at": now}
            for a, s, k in picks]
    return {"underlying": "NIFTY", "legs": legs}, [f"{a} {k} {s}" for a, s, k in picks]


def total_pnl(push: dict):
    for row in (push.get("table") or {}).get("rows", []):
        if row["row_id"] == "TOTAL":
            return (row["cells"].get("unrealized_pnl") or {}).get("value")
    return None


def summarise(sent: list[tuple[float, dict]], ids: list[str]) -> dict:
    rows = [(t, b) for t, b in sent if [g.get("instrument_id") for g in (b.get("legs") or [])] == ids]
    times = [t for t, _ in rows]
    gaps = [b - a for a, b in zip(times, times[1:])]
    ltps: dict[str, set] = {i: set() for i in ids}
    pnls, health_after_first, states = set(), set(), set()
    for n, (_, body) in enumerate(rows):
        states.add(body.get("state"))
        for g in body["legs"]:
            ltps[g["instrument_id"]].add(g.get("ltp"))
            if n > 0:
                health_after_first.add(g.get("health"))
        pnls.add(total_pnl(body))
    out = {"pushes": len(rows), "messages_total": len(sent), "min_gap_s": round(min(gaps), 3) if gaps else None,
           "distinct_ltp_per_leg": [len(ltps[i] - {None}) for i in ids],
           "distinct_unrealized_pnl": len(pnls - {None}), "states": sorted(str(s) for s in states),
           "health_after_first_tick": sorted(str(h) for h in health_after_first)}
    checks = {f"pushes>={MIN_PUSHES}": len(rows) >= MIN_PUSHES, "min_gap>=1.0": bool(gaps) and min(gaps) >= MIN_GAP,
              "ltp_changed": any(n > 1 for n in out["distinct_ltp_per_leg"]),
              "pnl_changed": out["distinct_unrealized_pnl"] > 1,
              "health_available": health_after_first == {"available"}}
    out["checks"], out["passed"] = checks, all(checks.values())
    return out


async def run(base: str, seconds: float) -> dict:
    expiry, chain = chain_of(base)
    strikes = sorted({s for s, _ in chain})
    provisional, _ = condor(chain, strikes[len(strikes) // 2])
    url = base.replace("http://", "ws://").replace("https://", "wss://") + "/api/strategies/live"
    started = datetime.datetime.now(IST)
    async with websockets.connect(url, max_size=4_000_000) as ws:
        await ws.send(json.dumps(provisional))
        spot = None
        deadline = time.monotonic() + SPOT_WAIT
        while spot is None and time.monotonic() < deadline:
            try:
                body = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic())))
            except asyncio.TimeoutError:
                break
            spot = body.get("spot_level")
        if spot is None:
            return {"error": f"no spot_level within {SPOT_WAIT:.0f} s", "passed": False, "exit": 3}
        request, picked = condor(chain, Decimal(spot))
        ids = [leg["instrument_id"] for leg in request["legs"]]
        await ws.send(json.dumps(request))
        sent: list[tuple[float, dict]] = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.05, end - time.monotonic()))
            except asyncio.TimeoutError:
                break
            sent.append((time.monotonic(), json.loads(raw)))
    out = summarise(sent, ids)
    out.update({"started_ist": started.isoformat(timespec="seconds"),
                "ended_ist": datetime.datetime.now(IST).isoformat(timespec="seconds"),
                "route": "/api/strategies/live", "expiry": expiry, "spot_seen": spot, "strikes": picked,
                "seconds": seconds})
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8766")
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args(argv)
    summary = asyncio.run(run(args.base.rstrip("/"), args.seconds))
    date = datetime.datetime.now(IST).date().isoformat()
    (HERE / f"w065-ws-proof-{date}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return int(summary.get("exit", 0 if summary.get("passed") else 1))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
