"""REQ-113 AC-2 core proof: the market-data process holds the Kite price socket; restarting the API process does not
reconnect it, and fresh frames reach the restarted API.

A looping fake Kite websocket server on loopback (port 0) replays the REAL recorded frames
(tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz) in a loop. The feed process (the REAL
``KiteSocket``) and the API process start as OS subprocesses through the test-only launcher (``feed_launcher.py``);
the API is killed (a hard kill on Windows and Ubuntu alike) and started again. Readiness is polled, never slept.
"""
from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

import pytest
import redis.asyncio as aioredis
from ofo.marketdata.kite_frames import iter_recording
from ofo_app import feed_bus
from websockets.asyncio.server import serve

HERE = pathlib.Path(__file__).resolve().parent
LAUNCHER = HERE / "feed_launcher.py"
FRAMES = HERE.parent / "tests" / "fixtures" / "kite_ws" / "frames-2026-10-08-092000-10s.bin.gz"
TOKEN = "TOK-core-proof-not-a-real-token"  # noqa: S105 - a fixture value, not a credential
WAIT_S = 60.0


def _recorded() -> list[bytes]:
    with gzip.open(FRAMES) as f:
        return [frame for _, frame in iter_recording(f)]


class LoopingKite:
    """A fake Kite: replays the recorded frames forever on every connection and counts the connections it accepted."""

    def __init__(self) -> None:
        self.accepted = 0
        self.frames = _recorded()

    async def handler(self, ws) -> None:
        self.accepted += 1
        reader = asyncio.ensure_future(self._drain(ws))
        try:
            while True:
                for frame in self.frames:
                    await ws.send(frame)
                    await asyncio.sleep(0.02)
        finally:
            reader.cancel()

    @staticmethod
    async def _drain(ws) -> None:
        with contextlib.suppress(Exception):
            async for _ in ws:
                pass


async def until(predicate, what: str, children, limit: float = WAIT_S):
    """Poll ``predicate`` (an async callable returning a truthy value) until it holds; fail with the exit codes."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        value = await predicate()
        if value:
            return value
        dead = {name: p.returncode for name, p in children.items() if p.poll() is not None}
        if dead:
            logs = {name: _tail(pathlib.Path(children[name].args[-1]).with_name(f"{name}.log")) for name in dead}
            pytest.fail(f"a process exited while waiting for {what}: {dead} {logs}")
        await asyncio.sleep(0.1)
    pytest.fail(f"timed out waiting for {what}")


def _tail(path: pathlib.Path) -> str:
    try:
        return path.read_text(errors="replace")[-1500:]
    except OSError:
        return ""


def _start(role: str, cfg_path: pathlib.Path, env: dict) -> subprocess.Popen:
    log = open(cfg_path.with_name(f"{role}.log"), "ab")  # noqa: SIM115 - handed to the child process
    return subprocess.Popen([sys.executable, str(LAUNCHER), role, str(cfg_path)], env=env,  # noqa: S603
                            stdout=log, stderr=log)


async def test_api_restart_does_not_reconnect_the_feed_and_fresh_frames_reach_the_new_api(redis_url, tmp_path):
    """AC-2: across a real API process restart the feed's Kite connection count stays 1 (and the server accepted exactly
    one), the feed process keeps running, and frames received by the NEW API are newer than the restart."""
    user = f"core{uuid.uuid4().hex[:12]}"
    kite = LoopingKite()
    server = await serve(kite.handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    cfg = {"user": user, "redis_url": redis_url, "ws_url": f"ws://127.0.0.1:{port}",
           "state_file": str(tmp_path / "api.json")}
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    env = {**os.environ, "OFO_TEST_KITE_TOKEN": TOKEN}
    bus = aioredis.Redis.from_url(redis_url)
    children: dict[str, subprocess.Popen] = {}
    seen_connections: list[int] = []

    async def status() -> dict | None:
        raw = await bus.get(feed_bus.status_key(user))
        body = None if raw is None else feed_bus.decode_status(user, raw)
        if body is not None and body["connected"]:  # before the first connect the count is 0 by definition
            seen_connections.append(body["connections"])
        return body

    async def api_state() -> dict | None:
        try:
            return json.loads(pathlib.Path(cfg["state_file"]).read_text())  # noqa: ASYNC240 - a tiny local file
        except (OSError, ValueError):
            return None

    try:
        children["feed"] = _start("feed", cfg_path, env)
        await until(lambda: _is(status, lambda s: s["connected"] and s["connections"] == 1),
                    "the feed connected", children)
        children["api"] = _start("api", cfg_path, env)
        first = await until(lambda: _is(api_state, lambda s: s["ticks"] > 0),
                            "the first API to receive price ticks", children)
        # kill the API (a hard kill); the feed must not notice
        children["api"].kill()
        children["api"].wait(timeout=30)
        pathlib.Path(cfg["state_file"]).unlink()  # noqa: ASYNC240 - a tiny local file
        restart_us = feed_bus.to_micros(feed_bus.from_micros(int(time.time() * 1_000_000)))
        children["api"] = _start("api", cfg_path, env)
        second = await until(lambda: _is(api_state, lambda s: s["ticks"] > 0 and s["last_frame_us"] is not None),
                             "the restarted API to receive price ticks", children)
        await until(lambda: _is(status, lambda s: s["last_frame_us"] is not None and s["last_frame_us"] > restart_us),
                    "the feed to keep receiving frames after the restart", children)
        assert second["pid"] != first["pid"]
        assert second["last_frame_us"] > restart_us, "a frame the new API holds is older than the restart"
        assert second["phase"] in {"healthy", "waiting"}
        assert children["feed"].poll() is None, "the feed process stopped"
        assert kite.accepted == 1, f"Kite saw {kite.accepted} connections; an API restart must not reconnect"
        assert seen_connections
        assert set(seen_connections) == {1}, f"the feed's own connection count moved: {seen_connections}"
    finally:
        for child in children.values():
            if child.poll() is None:
                child.kill()
        for child in children.values():
            child.wait(timeout=30)
        server.close()
        await server.wait_closed()
        await bus.aclose()


async def _is(read, ok):
    value = await read()
    return value if value is not None and ok(value) else None
