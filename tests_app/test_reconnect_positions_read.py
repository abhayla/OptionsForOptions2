# ruff: noqa: PLC0415, PLR2004, S106, S107
"""REQ-015 AC-5 (W-130): after the socket RE-connects, ONE positions read runs, off the receive loop, never an order.

Part 1 drives the real ``KiteSocket`` against a fake Kite server (first connection dropped, second one ticks).
Part 2 drives ``LiveMarket._read_positions_once`` through the real ``KiteReads`` with a fake transport, for every answer
state (OK, empty, Kite error, timeout, 429, token refused). No network, no database, no real Kite.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time

import pytest
from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import broker_sync, live_market
from ofo_app.kite_ws import KiteSocket
from test_kite_ws_resubscribe import FIXTURES, SPOT_ID, _ltp_frame, _until
from websockets.asyncio.server import serve

NOW = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)
FAST = 0.01


class DropFirst:
    """Kite's side: connection 1 is closed at once; later connections tick every subscribed token."""

    def __init__(self) -> None:
        self.connections = 0
        self.subscribed: set[int] = set()
        self.sent = 0

    async def handler(self, ws) -> None:
        self.connections += 1
        if self.connections == 1:
            await ws.close()
            return

        async def read():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["a"] == "subscribe":
                    self.subscribed |= set(msg["v"])

        reader = asyncio.ensure_future(read())
        try:
            while not reader.done():
                if self.subscribed:
                    self.sent += 1
                    await ws.send(_ltp_frame([(t, 2298245 + self.sent) for t in sorted(self.subscribed)]))
                await asyncio.sleep(0.02)
        finally:
            reader.cancel()


async def _fast_sleep(_seconds: float) -> None:
    await asyncio.sleep(FAST)


def _provider() -> KiteProvider:
    listed = list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv"))
    provider = KiteProvider(listed, clock=lambda: NOW)
    provider.subscribe([SPOT_ID])
    return provider


async def _run_socket(on_reconnect, until):
    provider = _provider()
    kite = DropFirst()
    async with serve(kite.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key="KEY-abc123", access_token="TOK-xyz789", clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=_fast_sleep, on_reconnect=on_reconnect)
        task = asyncio.create_task(sock.run())
        try:
            await _until(lambda: until(kite, provider), 10)
        finally:
            sock.stop()
            await asyncio.wait_for(task, 10)
    return kite, provider, sock


async def test_the_read_runs_once_after_the_reconnect_and_not_on_the_first_connect():
    calls: list[int] = []

    async def read():
        calls.append(kite_holder[0].connections)  # the server's connection count when the read ran

    provider = _provider()
    kite = DropFirst()
    kite_holder: list = [kite]
    async with serve(kite.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key="KEY-abc123", access_token="TOK-xyz789", clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=_fast_sleep, on_reconnect=read)
        task = asyncio.create_task(sock.run())
        try:
            await _until(lambda: kite.sent >= 5, 10)
            await asyncio.sleep(0.2)  # a duplicate would show here
        finally:
            sock.stop()
            await asyncio.wait_for(task, 10)
    assert sock.connections == 2  # the dropped first one and the reconnect
    assert calls == [2]  # exactly one read, made on the second connection - none on the first


async def test_ticks_keep_flowing_while_the_read_is_still_running():
    """Standing item (a): the read is its own task. It blocks until ticks have kept arriving; if it ran on the receive
    loop the ticks could never arrive and the wait below would time out."""
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow_read():
        started.set()
        await release.wait()

    provider = _provider()
    kite = DropFirst()
    async with serve(kite.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key="KEY-abc123", access_token="TOK-xyz789", clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=_fast_sleep, on_reconnect=slow_read)
        task = asyncio.create_task(sock.run())
        try:
            await asyncio.wait_for(started.wait(), 10)
            before = kite.sent
            await _until(lambda: kite.sent >= before + 5, 10)  # five more ticks while the read is blocked
            assert not release.is_set()
            first = provider.book.get(SPOT_ID, NOW)
            assert first is not None
        finally:
            release.set()
            sock.stop()
            await asyncio.wait_for(task, 10)


async def test_a_failing_read_never_ends_the_socket():
    async def boom():
        raise RuntimeError("zerodha said no")

    kite, _, sock = await _run_socket(boom, lambda k, p: k.sent >= 5)
    assert sock.connections == 2 and kite.sent >= 5


async def test_no_callback_means_no_read_and_the_socket_runs_as_before():
    _, _, sock = await _run_socket(None, lambda k, p: k.sent >= 3)
    assert sock.connections == 2


async def test_a_second_drop_while_the_read_is_still_running_does_not_start_a_second_read():
    release = asyncio.Event()
    calls: list[int] = []

    async def slow():
        calls.append(1)
        await release.wait()

    provider = _provider()
    sock = KiteSocket(provider, api_key="KEY-abc123", access_token="TOK-xyz789", clock=lambda: NOW,
                      base_url="ws://127.0.0.1:1", sleep=_fast_sleep, on_reconnect=slow)
    sock.connections = 2
    sock._start_reconnect_read()
    sock.connections = 3
    sock._start_reconnect_read()
    await asyncio.sleep(0)
    assert calls == [1]
    release.set()
    await asyncio.gather(*sock._reconnect_tasks)


# ---------------------------------------------------------------------------------------------------------------
# Part 2: the one positions read, every answer state
# ---------------------------------------------------------------------------------------------------------------


class _Config:
    api_key = "KEY-abc123"
    token_key = b"k" * 32


class Wire:
    """A fake Kite REST transport: records every call and answers ``reply`` (or raises/blocks)."""

    def __init__(self, reply=None, error: Exception | None = None, block: float = 0.0) -> None:
        self.reply, self.error, self.block = reply, error, block
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, headers, body, *, timeout=20):
        self.calls.append((method, url))
        if self.block:
            time.sleep(self.block)
        if self.error is not None:
            raise self.error
        return self.reply


def _ok(net=(), day=()):
    return 200, json.dumps({"status": "success", "data": {"net": list(net), "day": list(day)}})


@pytest.fixture(autouse=True)
def _clean():
    broker_sync.forget()
    yield
    broker_sync.forget()


def _market(monkeypatch, wire: Wire, token: str | None = "ACtok_fake_reconnect") -> live_market.LiveMarket:
    market = live_market.LiveMarket()
    market._config = _Config()

    async def stored(_config):
        return token

    monkeypatch.setattr(market, "_stored_token", stored)
    monkeypatch.setattr(live_market, "urllib_transport", wire)
    return market


async def test_ok_reply_notes_the_sync_and_calls_only_get_positions(monkeypatch):
    wire = Wire(_ok(net=[{"tradingsymbol": "X", "quantity": 0}]))
    await _market(monkeypatch, wire)._read_positions_once()
    assert broker_sync.last_read() is not None
    assert [m for m, _ in wire.calls] == ["GET"] and wire.calls[0][1].endswith("/portfolio/positions")


async def test_empty_positions_is_a_valid_answer_and_notes_the_sync(monkeypatch):
    wire = Wire(_ok())
    await _market(monkeypatch, wire)._read_positions_once()
    assert broker_sync.last_read() is not None and len(wire.calls) == 1


@pytest.mark.parametrize(("reply", "error"), [
    ((500, "{}"), None),                                                   # Kite error
    ((429, '{"status":"error","error_type":"NetworkException"}'), None),   # 429
    ((403, '{"status":"error","error_type":"TokenException"}'), None),     # token refused
    ((200, "not json"), None),                                             # malformed
    (None, TimeoutError("slow")),                                          # transport timeout
])
async def test_a_failed_read_is_logged_once_never_raised_never_retried_and_notes_no_sync(monkeypatch, reply, error):
    wire = Wire(reply, error)
    await _market(monkeypatch, wire)._read_positions_once()  # must not raise
    assert broker_sync.last_read() is None
    assert len(wire.calls) == 1  # no retry


async def test_a_read_that_overruns_its_timeout_is_abandoned_without_raising(monkeypatch):
    monkeypatch.setattr(live_market, "CALL_TIMEOUT_SECONDS", -4.9)  # the guard waits CALL_TIMEOUT + 5 = 0.1 s
    wire = Wire(_ok(), block=0.4)
    await _market(monkeypatch, wire)._read_positions_once()
    assert broker_sync.last_read() is None
    await asyncio.sleep(0.5)  # let the abandoned worker thread finish before the test ends


async def test_no_stored_token_makes_no_call(monkeypatch):
    wire = Wire(_ok())
    await _market(monkeypatch, wire, token=None)._read_positions_once()
    assert wire.calls == [] and broker_sync.last_read() is None


async def test_the_reconnect_path_reaches_no_order_call_even_if_the_wire_were_asked(monkeypatch):
    """Threat model: the allow-list refuses anything but a read. The one call the path makes is on the list."""
    from ofo.broker.kite_http import check_call
    wire = Wire(_ok())
    await _market(monkeypatch, wire)._read_positions_once()
    for method, url in wire.calls:
        check_call(method, url)  # raises when not an allow-listed read
