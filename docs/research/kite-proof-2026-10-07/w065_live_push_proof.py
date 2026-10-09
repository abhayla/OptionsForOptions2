"""W-065 live proof: real Kite ticks reach a platform-WebSocket client as recomputed strategy numbers, at most 1/s.

Run by the orchestrator with the owner, AFTER 09:15 IST on a trading day, after one login through the app's own login
link (W-058), against the real API started with LIVE_MARKET on (see work/W-065.md `proof`):

    python docs/research/kite-proof-2026-10-07/w065_live_push_proof.py [API_BASE_URL]      (default http://127.0.0.1:8765)

Needs: the repo's Python env (sqlalchemy, asyncpg, websockets) and DATABASE_URL in the environment (the same database
the API uses; read-only: it only LOADS the catalogue to name the contracts). It never sees the Kite access token and
prints no token or personal data: counts only.

Steps: (1) load the catalogue and pick the nearest live NIFTY expiry; (2) open WS /api/strategies/live, send a one-leg
probe to learn the live spot from the push (the push subscribes the leg and the NIFTY index); (3) send the NIFTY iron
condor (sell CE/PE at spot rounded to 50, +-200; buy wings +-400; 1 lot) and record 60 s of pushes; (4) print and write
the summary. Exit 0 only when: pushes >= 30, min gap >= 1.0 s, some leg's LTP changed, Unrealized P&L changed, and every
leg's data health was 'available' in every push.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import pathlib
import sys
import time
from decimal import Decimal

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

RECORD_SECONDS = 60
MIN_PUSHES = 30
MIN_GAP = 1.0
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
SUMMARY = HERE / "w065_live_push_proof_summary.json"


async def load_nifty_options() -> dict:
    """{expiry: {(strike, 'CE'|'PE'): instrument_id}} for the live NIFTY options in the catalogue."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from ofo_app.catalogue_store import load_catalogue

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as conn:
            catalogue = await load_catalogue(conn)
    finally:
        await engine.dispose()
    out: dict = {}
    for e in catalogue.all_entries():
        c = e.contract
        if c.name == "NIFTY" and e.currently_listed and c.instrument_type in ("CE", "PE") and c.expiry:
            out.setdefault(c.expiry, {})[(c.strike, c.instrument_type)] = f"{c.exchange_segment}:{c.exchange_token}"
    return out


def nearest(strikes, target: Decimal, kind: str):
    have = sorted(s for s, k in strikes if k == kind)
    return min(have, key=lambda s: abs(s - target))


def leg(instrument_id: str, action: str, entry: str, now: datetime.datetime) -> dict:
    return {"instrument_id": instrument_id, "action": action, "lots": 1, "planned_entry": entry,
            "captured_at": now.isoformat()}


def total_pnl(push: dict):
    for row in (push.get("table") or {}).get("rows", []):
        if row["row_id"] == "TOTAL":
            return (row["cells"].get("unrealized_pnl") or {}).get("value")
    return None


async def main(base: str) -> int:
    from websockets.asyncio.client import connect

    today = datetime.datetime.now(IST).date()
    options = await load_nifty_options()
    expiries = sorted(d for d in options if d >= today)
    if not expiries:
        print("FAIL: no live NIFTY expiry in the catalogue")
        return 2
    expiry = expiries[0]
    chain = options[expiry]
    mid = sorted(s for s, k in chain if k == "CE")[len(chain) // 4]
    url = base.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + "/api/strategies/live"
    now = datetime.datetime.now(IST)
    summary: dict = {"expiry": expiry.isoformat(), "base": base, "pushes": 0}

    async with connect(url, open_timeout=15) as ws:
        # 1. probe: one leg, to learn the live spot from the push (the push subscribes the NIFTY index too)
        await ws.send(json.dumps({"underlying": "NIFTY", "legs": [leg(chain[(mid, "CE")], "BUY", "1.00", now)]}))
        spot, msg = None, {}
        deadline = time.monotonic() + 45
        while spot is None and time.monotonic() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                continue
            spot = msg.get("spot_level")
        if spot is None:
            print("FAIL: no live NIFTY spot reached the push within 45 s (state seen: %s)" % msg.get("state"))
            return 3
        atm = (Decimal(spot) / 50).quantize(Decimal(1)) * 50
        picks = [("SELL", nearest(chain, atm + 200, "CE"), "CE"), ("BUY", nearest(chain, atm + 400, "CE"), "CE"),
                 ("SELL", nearest(chain, atm - 200, "PE"), "PE"), ("BUY", nearest(chain, atm - 400, "PE"), "PE")]
        legs = [leg(chain[(s, k)], a, "1.00", now) for a, s, k in picks]
        ids = [x["instrument_id"] for x in legs]
        summary["strikes"] = [f"{a} {k} {s}" for a, s, k in picks]
        # 2. the condor: record 60 s of pushes that carry all four legs
        await ws.send(json.dumps({"underlying": "NIFTY", "legs": legs}))
        times: list[float] = []
        ltps: dict[str, set] = {i: set() for i in ids}
        pnls: set = set()
        health: set = set()
        end = None
        while end is None or time.monotonic() < end:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                if end is None:
                    continue
                break
            got = msg.get("legs") or []
            if [g.get("instrument_id") for g in got] != ids:
                continue  # still the probe's answer
            at = time.monotonic()
            if end is None:
                end = at + RECORD_SECONDS
            times.append(at)
            for g in got:
                ltps[g["instrument_id"]].add(g.get("ltp"))
                health.add(g.get("health"))
            pnls.add(total_pnl(msg))

    gaps = [b - a for a, b in zip(times, times[1:])]
    summary.update({
        "pushes": len(times),
        "min_gap_s": round(min(gaps), 3) if gaps else None,
        "distinct_ltp_per_leg": [len(ltps[i] - {None}) for i in ids],
        "distinct_unrealized_pnl": len(pnls - {None}),
        "health_states": sorted(str(h) for h in health),
    })
    checks = {
        "pushes>=30": len(times) >= MIN_PUSHES,
        "min_gap>=1.0": bool(gaps) and min(gaps) >= MIN_GAP,
        "ltp_changed": any(n > 1 for n in summary["distinct_ltp_per_leg"]),
        "pnl_changed": summary["distinct_unrealized_pnl"] > 1,
        "health_live": health == {"available"},
    }
    summary["checks"] = checks
    summary["passed"] = all(checks.values())
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765")))
