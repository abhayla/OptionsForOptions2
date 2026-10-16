"""Gate 4a D-1 through the real KiteSocket: a fake Kite server that keeps Kite's subscription set (messages applied in
the order they arrive) and ticks only what is subscribed. Socket A holds the spot, socket B takes it in the same
change; the spot must keep updating. No network, no real Kite, no order ever sent."""
from __future__ import annotations

import asyncio
import datetime
import json
import pathlib

from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app.kite_ws import KiteSocket
from websockets.asyncio.server import serve

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
NOW = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)
SPOT_ID = "NSE_INDEX:1001"
API_KEY, TOKEN = "KEY-abc123", "TOK-xyz789"


def _ltp_frame(pairs) -> bytes:
    body = b"".join((8).to_bytes(2, "big") + t.to_bytes(4, "big") + p.to_bytes(4, "big") for t, p in pairs)
    return len(pairs).to_bytes(2, "big") + body


class FakeKite:
    """Kite's side: one subscription set, changed by each message in arrival order; ticks every subscribed token."""

    def __init__(self) -> None:
        self.subscribed: set[int] = set()
        self.price = 2298245  # paise; rises by 5 each tick so a frozen price is visible
        self.messages: list[dict] = []

    async def handler(self, ws) -> None:
        async def read():
            async for raw in ws:
                msg = json.loads(raw)
                self.messages.append(msg)
                if msg["a"] == "subscribe":
                    self.subscribed |= set(msg["v"])
                elif msg["a"] == "unsubscribe":
                    self.subscribed -= set(msg["v"])

        reader = asyncio.ensure_future(read())
        try:
            while not reader.done():
                if self.subscribed:
                    self.price += 5
                    await ws.send(_ltp_frame([(t, self.price) for t in sorted(self.subscribed)]))
                await asyncio.sleep(0.02)
        finally:
            reader.cancel()


async def _until(cond, limit_s=5.0):
    end = asyncio.get_running_loop().time() + limit_s
    while not cond():
        assert asyncio.get_running_loop().time() < end, "condition not met in time"
        await asyncio.sleep(0.02)


async def test_spot_released_by_one_socket_and_taken_by_another_keeps_ticking():
    listed = list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv"))
    provider = KiteProvider(listed, clock=lambda: NOW)
    fan = FanOut(provider)
    leg_a, leg_b = (f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed[:2])
    spot = provider._token_of[SPOT_ID]
    kite = FakeKite()
    async with serve(kite.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}")
        task = asyncio.create_task(sock.run())
        try:
            h_a = fan.subscribe(lambda q: None, [leg_a, SPOT_ID])
            await _until(lambda: provider.book.get(SPOT_ID, NOW) is not None)
            fan.unsubscribe(h_a)  # socket A closes and socket B opens in the same event-loop step
            fan.subscribe(lambda q: None, [leg_b, SPOT_ID])
            await _until(lambda: provider._token_of[leg_a] not in kite.subscribed
                         and provider._token_of[leg_b] in kite.subscribed)
            first = provider.book.get(SPOT_ID, NOW)
            await asyncio.sleep(0.3)  # ~15 server ticks
            later = provider.book.get(SPOT_ID, NOW)
        finally:
            sock.stop()
            await asyncio.wait_for(task, 10)
    assert spot in kite.subscribed, f"Kite was told to drop the spot: {kite.messages}"
    assert first is not None and later is not None and later.ltp > first.ltp, "the spot stopped updating"
