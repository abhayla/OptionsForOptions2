# ruff: noqa: PLR2004
"""REQ-113 AC-6 (row 9 part B): Zerodha's caps are configuration with a source and a date, and a request beyond a cap is
REFUSED and logged, never cut to fit and never silently dropped.

Per-connection cap (3000 instruments): the REAL ``KiteSocket`` against a fake Kite; 3001 wanted -> nothing is sent, the
socket says ``capped`` with the count beyond the cap, the log line carries the count, and the status the API reads says
``capped``. Per-key cap (3 connections, F-59): a 4th user on the same key is refused and logged, marked ``capped``, and
starts when a slot frees. Kite's answers: accepted -> subscribed | beyond the cap -> refused (above).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging

import pytest
from ofo.marketdata.kite_provider import IST, KiteProvider
from ofo_app import feed_bus, feed_main
from ofo_app import kite_ws as ws_mod
from ofo_app.kite_ws import KiteSocket
from ofo_app.order_limits_registry import RULES
from test_feed_restart_core import until
from test_feed_user_isolation import FakeClock, Rig, _is_true, new_ref, user_status
from websockets.asyncio.server import serve

NOW = datetime.datetime(2026, 10, 23, 9, 20, tzinfo=IST)
TOKEN = "TOK-caps-not-a-real-token"  # noqa: S105 - a fixture value, not a credential


def test_the_caps_are_registered_with_a_source_and_a_date():
    """AC-6: both caps live in one registry with their Zerodha source and date; the code constants are the registered
    ones (3000 and 3), not retyped."""
    by_name = {r.constant: r for r in RULES}
    per_conn = by_name["ofo_app.kite_ws:MAX_TOKENS_PER_CONNECTION"]
    per_key = by_name["ofo_app.kite_ws:MAX_CONNECTIONS_PER_KEY"]
    assert ws_mod.MAX_TOKENS_PER_CONNECTION == 3000 and ws_mod.MAX_CONNECTIONS_PER_KEY == 3
    for rule in (per_conn, per_key):
        assert "https://kite.trade/docs/connect/v3/websocket/" in rule.source
        assert rule.recorded_on == "2026-10-22" and rule.verified is True
    assert "3 websocket connections" in per_key.source


async def _socket_run(n_tokens: int, caplog):
    provider = KiteProvider([], clock=lambda: NOW)
    provider._wanted.update(range(1, n_tokens + 1))
    got = []
    ready = asyncio.Event()

    async def handler(ws):
        ready.set()
        try:
            async for message in ws:
                got.append(json.loads(message))  # noqa: PERF401
        except Exception:  # noqa: BLE001, S110 - the client went away
            pass

    server = await serve(handler, "127.0.0.1", 0, max_size=None)
    sock = KiteSocket(provider, api_key="KEY-caps", access_token=TOKEN, clock=lambda: NOW,
                      base_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
    task = asyncio.create_task(sock.run())
    await asyncio.wait_for(ready.wait(), 10)
    for _ in range(10):  # let the socket do its first sync
        await asyncio.sleep(0.05)
    return sock, provider, got, task, server


async def test_3001_instruments_are_refused_logged_with_the_count_and_never_truncated(caplog):
    """AC-6 attack 3: 3001 wanted -> NOTHING subscribed (not 3000), ``capped``, ``over_limit`` 1, a warning with the
    count; going back to 3000 wanted subscribes exactly those 3000 and clears ``capped``."""
    caplog.set_level(logging.INFO)
    sock, provider, got, task, server = await _socket_run(3001, caplog)
    try:
        assert got == [], "a request over the cap was cut to fit or partly sent"
        assert sock.capped is True and sock.over_limit == 1
        text = " ".join(r.getMessage() for r in caplog.records if r.name == "ofo_app.kite_ws")
        assert "3001 instruments wanted" in text and "cap is 3000" in text and TOKEN not in text
        provider._wanted.discard(3001)
        for _ in range(60):
            if got:
                break
            await asyncio.sleep(0.05)
        assert len(got) == 2 and got[0]["a"] == "subscribe" and len(got[0]["v"]) == 3000
        assert sock.capped is False and sock.over_limit == 0
    finally:
        sock.stop()
        await asyncio.wait_for(task, 10)
        server.close()
        await server.wait_closed()


async def test_exactly_3000_instruments_are_accepted(caplog):
    """AC-6 boundary: 3000 wanted is within the cap: all 3000 are subscribed, not capped."""
    sock, _provider, got, task, server = await _socket_run(3000, caplog)
    try:
        assert len(got) == 2 and len(got[0]["v"]) == 3000 and sock.capped is False and sock.over_limit == 0
    finally:
        sock.stop()
        await asyncio.wait_for(task, 10)
        server.close()
        await server.wait_closed()


async def test_the_status_the_api_reads_says_capped_when_the_wanted_set_is_over_the_cap(redis_url):
    """AC-6: the feed's own status for the user carries ``capped`` true while 3001 are wanted (the API shows it)."""
    user = new_ref("uc")
    bus = feed_bus.new_client(redis_url)
    kite_seen = []

    async def handler(ws):
        try:
            async for message in ws:
                kite_seen.append(message)  # noqa: PERF401
        except Exception:  # noqa: BLE001, S110
            pass

    server = await serve(handler, "127.0.0.1", 0, max_size=None)
    await bus.set(feed_bus.want_key(user), feed_bus.encode_want(user, list(range(1, 3002))), px=60_000)
    stop = asyncio.Event()
    task = asyncio.ensure_future(feed_main.run_feed(
        user_ref=user, api_key="KEY-caps", access_token=TOKEN, redis_url=redis_url, stop=stop,
        ws_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"))
    try:
        async def capped():
            status = await user_status(bus, user)
            return status if status and status["connected"] and status["capped"] else None

        await until(capped, "the status to say capped", {})
        assert kite_seen == [], "tokens were sent to Kite although the request was over the cap"
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)
        server.close()
        await server.wait_closed()
        await bus.delete(*(k(user) for k in (feed_bus.ticks_key, feed_bus.want_key, feed_bus.status_key)))
        await bus.aclose()


@pytest.fixture
async def rig(redis_url):
    made = Rig(redis_url, FakeClock())
    yield made
    await made.close()


async def test_a_fourth_connection_on_one_key_is_refused_logged_and_marked_capped(rig, caplog):
    """AC-6 attack 4: four users on one API key, the cap is 3: three sockets connect, the fourth user's Kite sees no
    connection, its status says capped (not connected), the log says so, and the three are untouched. When a user's
    session goes, the waiting fourth user gets the freed slot."""
    caplog.set_level(logging.INFO)
    users = [new_ref(f"u{i}") for i in range(4)]
    kites = [await rig.kite(u) for u in users]
    for index, user in enumerate(users):
        rig.store.set(user, f"TOK-cap-{index}")
    rig.start()

    async def three_live_one_capped():
        statuses = [await user_status(rig.bus, u) for u in users]
        live = [s is not None and s["connected"] for s in statuses]
        return (sum(live) == 3 and statuses[3] is not None and statuses[3]["capped"]) or None

    await rig.until(three_live_one_capped, "three live, the fourth capped")
    assert [k.accepted for k in kites] == [1, 1, 1, 0], "the fourth user's socket reached Kite"
    status = await user_status(rig.bus, users[3])
    assert status["connected"] is False and status["phase"] == "stopped" and status["capped"] is True
    assert any("connection cap: 3 sockets already open on this key (cap 3)" in r.getMessage() for r in caplog.records)
    assert not any("TOK-cap" in r.getMessage() for r in caplog.records)
    del rig.store.sessions[users[0]]  # a slot frees

    async def fourth_live():
        return (await rig.live(users[3])) or None

    await rig.until(fourth_live, "the fourth user's socket after a slot frees")
    assert kites[3].accepted == 1 and kites[1].accepted == 1 and kites[2].accepted == 1
    assert _is_true  # the helper is shared with the isolation tests


async def test_the_per_key_cap_counts_only_sockets_of_that_key(rig):
    """AC-6: the cap is per API key: with the cap at 1, a second user on a DIFFERENT key still connects."""
    user_a, user_b = new_ref("ua"), new_ref("ub")
    await rig.kite(user_a)
    await rig.kite(user_b)
    rig.store.set(user_a, "TOK-key-1")
    original = rig.store.read

    async def read(user):
        session = await original(user)
        if session is not None and user == user_b:
            return feed_main.StoredSession("KEY-other", session.access_token, session.fingerprint, session.expires_at)
        return session

    rig.store.read = read
    rig.store.set(user_b, "TOK-key-2")
    rig.start(max_connections=1)

    async def both():
        return ((await rig.live(user_a)) and (await rig.live(user_b))) or None

    await rig.until(both, "one socket per key at cap 1")
