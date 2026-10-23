"""REQ-114 (W-139): a Kite socket that stays OPEN but sends nothing is closed and reconnected (AC-1, AC-2), its quotes
read stale until a fresh tick after the reconnect (AC-4), with capped, jittered back-off (AC-3). The REAL ``KiteSocket``
runs on an injected clock against a fake connection that plays the recorded frames (2026-10-08 09:20) and then goes
silent.

Kite's socket answer states and what each does (standing item d):
- data frame (>1 byte)        -> provider.on_frame; counts as a frame of any kind; resets the back-off
- heartbeat (1 byte)          -> provider.on_frame; counts as a frame of any kind (the link is alive); no back-off reset
- text frame, order update    -> provider.on_text; session untouched
- text frame, token error     -> session ended, no retry (tests_app/test_kite_ws.py)
- text frame, other error     -> counted, session untouched (tests_app/test_kite_ws.py)
- close / network error       -> drop, back off, reconnect (tests_app/test_kite_ws.py)
- 403 at connect              -> session ended, no retry (tests_app/test_kite_ws.py)
- connect refused             -> back off 1, 2, 4 ... 30 (tests_app/test_kite_ws.py)
- silence                     -> THIS FILE: 60 s on the connection -> close, stale, reconnect
"""
from __future__ import annotations

import datetime
import itertools
import types
from datetime import timedelta

from _fake_kite_ws import API_KEY, START, TOKEN, FakeConnect, NoJitter, SimClock, Sleeper, new_provider, recorded_frames
from ofo.rules.inputs import DataHealth
from ofo_app.kite_ws import STOPPED, KiteSocket

HEARTBEAT = b"\x00"
SILENT = 60  # REQ-114 AC-2
MIN_FIRST_WAIT, FIRST_WAIT = 0.5, 1  # the first back-off 1 s, less up to 50% jitter
SECOND_BACKOFF = 2


def _build(scripts, *, step=0.5, **extra):
    clock = SimClock()
    provider = new_provider(clock)
    connect = FakeConnect(clock, scripts, step=step)
    sleeper = Sleeper(clock)
    sock = KiteSocket(provider, api_key=API_KEY, access_token=TOKEN, clock=clock, base_url="ws://127.0.0.1:9",
                      connect=connect, sleep=sleeper, **extra)
    connect.on_end = sock.stop
    return types.SimpleNamespace(clock=clock, provider=provider, connect=connect, sleeper=sleeper, sock=sock)


def _healths(provider, clock):
    quotes = provider.book.quotes(clock.now)
    assert quotes, "no quote is held: the probe would prove nothing"
    return {q.health for q in quotes}


async def test_core_silent_open_socket_is_closed_at_60s_and_reconnected_with_stale_quotes_until_a_fresh_tick():
    """Core: recorded frames, then silence on an OPEN socket. At 60 s it is closed; the wait is jittered (0.5-1 s);
    the subscriptions are re-sent; quotes read stale from the silence until the first replayed frame."""
    frames = recorded_frames(3)
    seen: dict[str, set] = {}
    holder: dict = {}

    def probe(name):
        return lambda: seen.__setitem__(name, _healths(holder["provider"], holder["clock"]))

    conn1 = [("bytes", f) for f in frames] + [("call", probe("after_frames")), ("silence", 300)]
    conn2 = [("call", probe("after_reconnect_before_tick")), ("bytes", frames[0]), ("call", probe("after_tick")),
             ("silence", 1)]
    rig = _build([conn1, conn2])
    holder.update(provider=rig.provider, clock=rig.clock)
    rig.sleeper.on_sleep = probe("during_backoff")

    assert await rig.sock.run() == STOPPED

    first, second = rig.connect.sockets
    assert first.closed_at - START == timedelta(seconds=SILENT)  # closed at exactly 60.0 s of silence
    assert rig.sock.connections == 2  # noqa: PLR2004
    # the first back-off is 1 s, less up to 50% jitter
    assert len(rig.sleeper.sleeps) == 1 and MIN_FIRST_WAIT <= rig.sleeper.sleeps[0] <= FIRST_WAIT
    wanted = rig.provider.subscribed_tokens()
    assert second.sent == [{"a": "subscribe", "v": wanted}, {"a": "mode", "v": ["full", wanted]}]  # re-sent
    assert seen["after_frames"] == {DataHealth.AVAILABLE}  # the feed was healthy while frames flowed
    assert seen["during_backoff"] == {DataHealth.STALE}  # stale from the close
    assert seen["after_reconnect_before_tick"] == {DataHealth.STALE}  # reconnect alone never makes quotes available
    assert seen["after_tick"] == {DataHealth.AVAILABLE}  # the first fresh tick does


async def test_quiet_contracts_with_heartbeats_never_reconnect():
    """Attack 1 (F-32): a quiet feed that still sends the 1-byte heartbeat every second is healthy, for 10 minutes."""
    script = [("bytes", recorded_frames(1)[0])]
    for _ in range(600):
        script += [("silence", 1), ("bytes", HEARTBEAT)]
    rig = _build([script])
    assert await rig.sock.run() == STOPPED
    assert rig.sock.connections == 1 and rig.sleeper.sleeps == []
    assert rig.provider.counters["heartbeats"] == 600  # noqa: PLR2004


async def test_59_9_seconds_of_silence_keeps_the_socket_and_60_0_closes_it():
    """Attack 2: the boundary on the injected clock, in 0.1 s steps."""
    beat = [("bytes", recorded_frames(1)[0]), ("silence", 59.9), ("bytes", HEARTBEAT), ("silence", 5)]
    rig = _build([beat], step=0.1)
    assert await rig.sock.run() == STOPPED
    assert rig.sock.connections == 1 and rig.sleeper.sleeps == []  # 59.9 s then a heartbeat: still the same connection

    rig = _build([[("bytes", recorded_frames(1)[0]), ("silence", 120)], []], step=0.1)
    assert await rig.sock.run() == STOPPED
    assert rig.connect.sockets[0].closed_at - START == timedelta(seconds=SILENT)  # not 59.9, not 60.1


async def test_the_silence_check_runs_at_least_every_15_seconds():
    """AC-1: the connection's last-frame time is checked every 15 s (and at the 60 s mark). Observed through the
    socket's check observer on the injected clock; heartbeats in between do not stop the checks."""
    times: list[datetime.datetime] = []
    script = [("bytes", recorded_frames(1)[0]), ("silence", 50), ("bytes", HEARTBEAT), ("silence", 50)]
    rig = _build([script], on_check=times.append)
    await rig.sock.run()
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
    assert len(times) >= 6 and max(gaps) <= 15 and min(gaps) > 0  # noqa: PLR2004


async def test_a_drop_before_the_first_data_frame_does_not_reset_the_backoff():
    """Attack 4: connections that only ever send heartbeats (no data frame) and then go silent back off 1, 2, 4 s;
    a connection that delivers a data frame resets the next wait to 1 s."""
    data = recorded_frames(1)[0]
    hb_only = [("bytes", HEARTBEAT), ("silence", 300)]
    with_data = [("bytes", data), ("silence", 300)]
    rig = _build([hb_only, hb_only, hb_only, with_data, hb_only, []], rng=NoJitter())
    assert await rig.sock.run() == STOPPED
    assert rig.sleeper.sleeps[:3] == [1, 2, 4]
    assert rig.sleeper.sleeps[3] == 1  # the data frame of connection 4 reset the nominal wait to 1
    assert rig.sleeper.sleeps[4] == SECOND_BACKOFF  # and the climb starts again from there (1, then 2)


async def test_a_connection_that_never_sent_anything_is_closed_60s_after_it_opened():
    """A fresh connection starts the 'something must arrive' clock at connect (no frame of any kind yet)."""
    rig = _build([[("silence", 300)], []], rng=NoJitter())
    assert await rig.sock.run() == STOPPED
    first = rig.connect.sockets[0]
    assert first.closed_at - first.opened_at == timedelta(seconds=SILENT)


async def test_market_closed_silence_reconnects_at_most_once_per_5_minutes():
    """AC-7 through the socket: on a Saturday the silent socket is closed at 60 s; the next connect waits >= 300 s."""
    saturday = datetime.datetime(2026, 10, 10, 11, 0, 0, tzinfo=START.tzinfo)
    rig = _build([[("silence", 300)], []], rng=NoJitter())
    rig.clock.now = saturday
    assert await rig.sock.run() == STOPPED
    assert rig.sleeper.sleeps == [300]
