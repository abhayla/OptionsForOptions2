"""W-065 core proof, in-process: real Kite ticks become recomputed strategy numbers through the live market context and
StrategyPush (1 s gate, changed-input check). No websocket route is registered (orchestrator decision 2026-10-09: no
W-024 exemption; the route follows issue #151), so the proof drives StrategyPush directly through a collecting sink.

Run by the orchestrator AFTER 09:15 IST on a trading day, after the owner has logged in through the app's login link:

    python docs/research/kite-proof-2026-10-07/w065_live_push_proof.py [--env-file PATH] [--seconds 60]

Reads settings from the project .env (DATABASE_URL, else TEST_DATABASE_URL; the Kite and token-key settings), opens the
DB engine as the app does, builds the live market context exactly as ofo_app.live_market does in the lifespan (the
owner's stored session via access_token_for), starts KiteSocket, waits for the NIFTY spot, builds the NIFTY iron condor
on the nearest live expiry (sell +-200 from spot rounded to 50, buy wings +-400, 1 lot), drives StrategyPush for the
recording time, stops the socket and prints COUNTS ONLY. The token is never printed or written.

Exit 0 only when: pushes >= 30, min gap >= 1.0 s, some leg's LTP changed, Unrealized P&L changed, every push's data
health was 'available'. Exit 2: no active Kite session (owner login needed) or no live NIFTY expiry. Exit 3: no spot.
The summary is also written to w065-live-proof-<date>.json next to this file.

The old HTTP/WebSocket client mode is not kept: the route does not exist yet (phase 2, after issue #151).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import pathlib
import sys
import time
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

RECORD_SECONDS = 60
MIN_PUSHES = 30
MIN_GAP = 1.0
SPOT_WAIT_SECONDS = 45
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class CollectingChannel:
    """The two-method channel StrategyPush expects. The first receive() hands over the strategy request; the next
    receive() waits until close(). Every push is recorded with the monotonic time it was sent."""

    def __init__(self, request: dict, monotonic: Callable[[], float]) -> None:
        self._request, self._mono = request, monotonic
        self._queue: asyncio.Queue = asyncio.Queue()
        self._queue.put_nowait(request)
        self.sent: list[tuple[float, dict]] = []

    async def receive(self):
        from ofo_app.live_push import ChannelClosed

        item = await self._queue.get()
        if item is None:
            raise ChannelClosed()
        return item

    async def send(self, body: dict) -> None:
        self.sent.append((self._mono(), body))

    def close(self) -> None:
        self._queue.put_nowait(None)


def total_pnl(push: dict):
    for row in (push.get("table") or {}).get("rows", []):
        if row["row_id"] == "TOTAL":
            return (row["cells"].get("unrealized_pnl") or {}).get("value")
    return None


def summarise(sent: list[tuple[float, dict]], ids: list[str], min_pushes: int) -> dict:
    """Counts only. Pushes before all legs are present (an error body) are ignored."""
    rows = [(t, b) for t, b in sent if [g.get("instrument_id") for g in (b.get("legs") or [])] == ids]
    times = [t for t, _ in rows]
    gaps = [b - a for a, b in zip(times, times[1:])]
    ltps: dict[str, set] = {i: set() for i in ids}
    health: set = set()
    pnls: set = set()
    for _, body in rows:
        for g in body["legs"]:
            ltps[g["instrument_id"]].add(g.get("ltp"))
            health.add(g.get("health"))
        pnls.add(total_pnl(body))
    out = {
        "pushes": len(rows),
        "min_gap_s": round(min(gaps), 3) if gaps else None,
        "distinct_ltp_per_leg": [len(ltps[i] - {None}) for i in ids],
        "distinct_unrealized_pnl": len(pnls - {None}),
        "health_states": sorted(str(h) for h in health),
    }
    checks = {
        f"pushes>={min_pushes}": len(rows) >= min_pushes,
        "min_gap>=1.0": bool(gaps) and min(gaps) >= MIN_GAP,
        "ltp_changed": any(n > 1 for n in out["distinct_ltp_per_leg"]),
        "pnl_changed": out["distinct_unrealized_pnl"] > 1,
        "health_live": health == {"available"},
    }
    out["checks"], out["passed"] = checks, all(checks.values())
    return out


async def run_core(feed, make_request: Callable[[Decimal], dict], *, monotonic: Callable[[], float],
                   sleep: Callable[[float], Awaitable[None]], seconds: float = RECORD_SECONDS,
                   spot_wait: float = SPOT_WAIT_SECONDS, min_pushes: int = MIN_PUSHES, poll: Optional[float] = None
                   ) -> dict:
    """The in-process core: subscribe the NIFTY index on the shared fan-out, wait for its spot, build the strategy
    request from it, run StrategyPush into a collecting sink for ``seconds`` of ``monotonic``, return the summary
    (counts only). ``feed`` is a LiveFeed (live: LiveMarket.feed; CI: the W-064 replay provider on a fake clock)."""
    from ofo_app.live_push import POLL_SECONDS, StrategyPush

    provider = feed.ctx.provider
    index_id = provider.index_id("NIFTY")
    if index_id is None:
        return {"error": "no NIFTY index in the catalogue", "passed": False, "exit": 3}
    handle = feed.fanout.subscribe(lambda _q: None, [index_id])  # the spot source; also asks Kite for the index
    spot = None
    try:
        deadline = monotonic() + spot_wait
        while monotonic() < deadline:
            quote = provider.underlying_quote("NIFTY")
            if quote is not None and quote.ltp is not None:
                spot = Decimal(str(quote.ltp))
                break
            await sleep(0.25)
        if spot is None:
            return {"error": "no live NIFTY spot within %d s" % spot_wait, "passed": False, "exit": 3}
        request = make_request(spot)
        ids = [leg["instrument_id"] for leg in request["legs"]]
        channel = CollectingChannel(request, monotonic)
        push = StrategyPush(channel, feed, monotonic=monotonic, poll=POLL_SECONDS if poll is None else poll)
        task = asyncio.ensure_future(push.run())
        try:
            end = monotonic() + seconds
            while monotonic() < end and not task.done():
                await sleep(0.25)
        finally:
            channel.close()
            await asyncio.wait({task}, timeout=5)
            if not task.done():
                task.cancel()
    finally:
        feed.fanout.unsubscribe(handle)  # held to the end, so the spot is never dropped and re-asked mid-run
    out = summarise(channel.sent, ids, min_pushes)
    out["spot_known"] = True
    return out


# ---- live-only parts ---------------------------------------------------------------------------------------------
def load_env(path: pathlib.Path) -> None:
    """KEY=VALUE lines into os.environ (existing variables win). Values are never printed."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def nearest(strikes, target: Decimal, kind: str):
    have = sorted(s for s, k in strikes if k == kind)
    return min(have, key=lambda s: abs(s - target))


def nifty_options(catalogue) -> dict:
    out: dict = {}
    for e in catalogue.all_entries():
        c = e.contract
        if c.name == "NIFTY" and e.currently_listed and c.instrument_type in ("CE", "PE") and c.expiry:
            out.setdefault(c.expiry, {})[(c.strike, c.instrument_type)] = f"{c.exchange_segment}:{c.exchange_token}"
    return out


def condor_request(chain: dict, spot: Decimal, now: datetime.datetime) -> tuple[dict, list[str]]:
    atm = (spot / 50).quantize(Decimal(1)) * 50
    picks = [("SELL", nearest(chain, atm + 200, "CE"), "CE"), ("BUY", nearest(chain, atm + 400, "CE"), "CE"),
             ("SELL", nearest(chain, atm - 200, "PE"), "PE"), ("BUY", nearest(chain, atm - 400, "PE"), "PE")]
    legs = [{"instrument_id": chain[(s, k)], "action": a, "lots": 1, "planned_entry": "1.00",
             "captured_at": now.isoformat()} for a, s, k in picks]
    return {"underlying": "NIFTY", "legs": legs}, [f"{a} {k} {s}" for a, s, k in picks]


async def live_main(seconds: float) -> int:
    from ofo_app import live_market
    from ofo_app.broker_config import load_broker_config
    from ofo_app.catalogue_store import load_catalogue
    from ofo_app.db import close_db, get_engine

    market = live_market.LiveMarket()
    live_market.set_current(market)
    summary: dict[str, Any] = {"date": datetime.datetime.now(IST).date().isoformat(), "pushes": 0}
    try:
        await market.start(load_broker_config())  # the lifespan's own start: stored session -> provider -> socket
        if market.state != live_market.LIVE:
            print("no active Kite session: owner login needed")
            return 2
        async with get_engine().connect() as conn:
            options = nifty_options(await load_catalogue(conn))
        today = datetime.datetime.now(IST).date()
        expiries = sorted(d for d in options if d >= today)
        if not expiries:
            print("FAIL: no live NIFTY expiry in the catalogue")
            return 2
        chain = options[expiries[0]]
        picked: dict = {}

        def make(spot: Decimal) -> dict:
            req, picked["strikes"] = condor_request(chain, spot, datetime.datetime.now(IST))
            return req

        result = await run_core(market.feed, make, monotonic=time.monotonic, sleep=asyncio.sleep, seconds=seconds)
        summary.update(result)
        summary["expiry"], summary["strikes"] = expiries[0].isoformat(), picked.get("strikes")
        summary["connections"] = getattr(market._socket, "connections", None)
        summary["session_state"] = market.state
        summary["feed_session_ended"] = market.feed.ctx.provider.status().session_ended
    finally:
        await market.stop()
        live_market.set_current(None)
        await close_db()
    path = HERE / f"w065-live-proof-{summary['date']}.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return int(summary.get("exit", 0 if summary.get("passed") else 1))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--seconds", type=float, default=RECORD_SECONDS)
    args = ap.parse_args(argv)
    candidates = [pathlib.Path(args.env_file)] if args.env_file else [ROOT / ".env", ROOT.parent / "OptionsForOptions2" / ".env"]
    for p in candidates:
        if p.is_file():
            load_env(p)
            break
    if "DATABASE_URL" not in os.environ and os.environ.get("TEST_DATABASE_URL"):
        os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ.setdefault("LIVE_MARKET", "1")
    return asyncio.run(live_main(args.seconds))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
