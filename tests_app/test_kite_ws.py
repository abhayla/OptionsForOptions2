"""W-059 stage 2: the live Kite socket against a fake WebSocket server. No network, no real Kite, no order ever sent.

Every answer state of the socket: data frame, heartbeat, text message, close, network error, 403 at connect."""
from __future__ import annotations

import asyncio
import datetime
import gzip
import json
import logging
import pathlib
from http import HTTPStatus

import pytest
from websockets.asyncio.server import serve

from ofo.instruments.parser import parse_instruments_csv
from ofo.marketdata.kite_frames import iter_recording
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo.rules.inputs import DataHealth
from ofo_app.kite_ws import SESSION_ENDED, STOPPED, KiteSocket

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
API_KEY, TOKEN = "KEY-abc123", "TOK-xyz789"
NOW = datetime.datetime(2026, 10, 8, 9, 20, 0, tzinfo=IST)


def _provider():
    listed = list(parse_instruments_csv(FIXTURES / "instruments-2026-10-08-subscribed.csv"))
    provider = KiteProvider(listed, clock=lambda: NOW)
    ids = [f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed[:5]] + ["INDEX:NIFTY 50"]
    provider.subscribe(ids)
    return provider


def _frames(n):
    with gzip.open(FIXTURES / "frames-2026-10-08-092000-10s.bin.gz") as f:
        return [frame for _, frame in iter_recording(f)][:n]


class Recorder:
    def __init__(self):
        self.sleeps: list[float] = []

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        await asyncio.sleep(0)


async def test_resubscribes_after_a_drop_and_handles_frames_heartbeats_and_text():
    provider = _provider()
    wanted = provider.subscribed_tokens()
    frames = _frames(3)
    per_connection: list[list[dict]] = []
    second_ready = asyncio.Event()

    async def handler(ws):
        received = []
        per_connection.append(received)
        for _ in range(2):
            received.append(json.loads(await ws.recv()))
        if len(per_connection) == 1:
            for frame in frames:
                await ws.send(frame)
            await ws.send(b"\x00")  # heartbeat
            await ws.send(json.dumps({"type": "order", "data": {"order_id": "1"}}))
            await ws.close()
        else:
            second_ready.set()
            await ws.wait_closed()

    rec = Recorder()
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=rec.sleep)
        task = asyncio.create_task(sock.run())
        await asyncio.wait_for(second_ready.wait(), 10)
        sock.stop()
        assert await asyncio.wait_for(task, 10) == STOPPED

    expected = [{"a": "subscribe", "v": wanted}, {"a": "mode", "v": ["full", wanted]}]
    assert per_connection == [expected, expected]  # the second connection re-subscribed the same tokens
    assert sock.connections == 2 and rec.sleeps == [1]
    assert provider.counters["frames"] == 4 and provider.counters["heartbeats"] == 1
    assert provider.counters["text:order"] == 1
    assert provider.counters["ticks"] > 0


async def test_403_on_connect_ends_the_session_without_retry():
    provider = _provider()

    def refuse(connection, request):
        return connection.respond(HTTPStatus.FORBIDDEN, "no\n")

    rec = Recorder()
    async with serve(lambda ws: None, "127.0.0.1", 0, process_request=refuse) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=rec.sleep)
        assert await asyncio.wait_for(sock.run(), 10) == SESSION_ENDED
    assert rec.sleeps == [] and sock.connections == 0
    assert provider.feed.session_ended is True
    assert provider.feed.health(NOW) is DataHealth.UNAVAILABLE


async def test_network_errors_back_off_1_2_4_up_to_30_and_keep_trying():
    provider = _provider()
    attempts = []
    holder = {}

    class Refused:
        def __init__(self, url, **kwargs):
            attempts.append(url)

        async def __aenter__(self):
            raise OSError(f"cannot reach {attempts[-1]}")  # the message holds the URL: it must not be logged

        async def __aexit__(self, *exc):
            return False

    async def sleep(seconds):
        holder["delays"].append(seconds)
        if len(holder["delays"]) == 7:
            holder["sock"].stop()

    holder["delays"] = []
    sock = holder["sock"] = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                                       connect=Refused, sleep=sleep)
    assert await asyncio.wait_for(sock.run(), 10) == STOPPED
    assert holder["delays"] == [1, 2, 4, 8, 16, 30, 30]
    assert len(attempts) == 7 and provider.feed.connected is False


async def test_url_and_token_never_appear_in_any_log_record(caplog):
    caplog.set_level(logging.DEBUG)  # everything, including the websockets library's own DEBUG request lines
    provider = _provider()
    second_ready = asyncio.Event()
    count = []

    async def handler(ws):
        count.append(1)
        await ws.recv()
        if len(count) == 1:
            await ws.close()
        else:
            second_ready.set()
            await ws.wait_closed()

    rec = Recorder()
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}", sleep=rec.sleep)
        task = asyncio.create_task(sock.run())
        await asyncio.wait_for(second_ready.wait(), 10)
        sock.stop()
        await asyncio.wait_for(task, 10)
    assert any(r.name == "ofo_app.kite_ws" for r in caplog.records)  # we did log something
    # the fake SERVER's own library logs (websockets.server) are the test double, not our client: skip those only
    client_side = [r for r in caplog.records if not r.name.startswith("websockets.server")]
    assert not any(r.name.startswith("websockets.client") for r in client_side)  # the client's wire log is silenced
    for record in client_side:
        text = record.getMessage() + str(record.args) + (record.exc_text or "")
        assert API_KEY not in text and TOKEN not in text and "access_token" not in text, record.name
    # and the Refused case above: an exception whose message holds the URL is logged by class name only
    assert not any("cannot reach" in r.getMessage() for r in caplog.records)


async def test_over_3000_tokens_are_cut_and_counted():
    provider = _provider()
    provider._wanted.update(range(1, 3500))  # more than one connection may carry
    got = []
    ready = asyncio.Event()

    async def handler(ws):
        got.append(json.loads(await ws.recv()))
        ready.set()
        await ws.wait_closed()

    async with serve(handler, "127.0.0.1", 0, max_size=None) as server:
        port = server.sockets[0].getsockname()[1]
        sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=lambda: NOW,
                          base_url=f"ws://127.0.0.1:{port}")
        task = asyncio.create_task(sock.run())
        await asyncio.wait_for(ready.wait(), 10)
        sock.stop()
        await asyncio.wait_for(task, 10)
    assert len(got[0]["v"]) == 3000 and sock.over_limit == len(provider.subscribed_tokens()) - 3000
