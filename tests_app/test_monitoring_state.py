"""Lane J2 (27 Nov), item 3: a trade the worker cannot price is visible as NOT WATCHED, with its reason and since when.

Real case 27 Nov: the worker silently skipped trades it could not price; the after-close sweep saw no
"Monitoring paused" and no "Health unknown" on Live Strategies cards while every price was missing (the state lived
in the worker's memory).
Spec basis: REQ-115 AC-4 ("the strategy shows Monitoring paused" while its inputs are stale or the feed is
disconnected; no rule fires, no alert claims a trigger) and AC-6 (no heartbeat for 2 minutes: every affected strategy
shows Monitoring paused rather than its last colour); REQ-049 line 38 (badge and grey "Health unknown" dot);
domain-model.md line 71 (a lost feed leaves the strategy Active; its monitoring status shows paused); ADR-330 (58).
No Redis, no Kite: a dict-backed client. The module carries codes only; the wording is the screens'.
"""
from __future__ import annotations

import datetime
import json
import logging
from decimal import Decimal

from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import background, feed_bus, monitoring_state
from ofo_app.monitoring_state import ACTIVE, PAUSED, Entry
from test_background_cycle import Calls, Prov, _watched, _worker, scn  # noqa: F401 - the fixture is used by name
from test_spot_either_source import _Reader

SID = 100
T0 = datetime.datetime(2026, 11, 27, 10, 0, 0, tzinfo=datetime.UTC)
SEC = datetime.timedelta(seconds=1)
TWO_WRITES = 2


class _Client:
    """A dict-backed stand-in for the bus client (set / get)."""

    def __init__(self, boom: bool = False) -> None:
        self.data: dict[str, str] = {}
        self.sets = 0
        self.boom = boom

    async def set(self, k, v, **_kw):
        if self.boom:
            raise OSError("down")
        self.sets += 1
        self.data[k] = v

    async def get(self, k):
        if self.boom:
            raise OSError("down")
        return self.data.get(k)


class _Status:
    def __init__(self, name):
        self.name = name


PAUSED_S, ACTIVE_S = _Status("PAUSED"), _Status("ACTIVE")


async def _fresh(_client, _now):
    return feed_bus.FRESH


async def _stale(_client, _now):
    return feed_bus.STALE


async def test_a_paused_trade_is_stored_with_its_reason_why_and_since():
    client = _Client()
    pub = monitoring_state.Publisher(client)
    wrote = await pub.publish({SID: PAUSED_S}, {SID: _Status("LEG_MISSING")}, {SID: "rest_stale"}, T0)
    assert wrote is True
    got = await monitoring_state.read_states(client, [SID], T0 + 3 * SEC, heartbeat=_fresh)
    assert got == {SID: Entry(SID, PAUSED, "leg_missing", "rest_stale", T0)}


async def _monitor_reports(client, at):  # item (a): no report = not watched; a live monitor's empty report is set-up
    await monitoring_state.ExitsPublisher(client, "m").publish([], {}, at)


async def test_since_is_kept_while_status_and_reason_stay_and_restarts_when_either_changes():
    client = _Client()
    await _monitor_reports(client, T0)
    pub = monitoring_state.Publisher(client)
    await pub.publish({SID: PAUSED_S}, {SID: _Status("STALE")}, {}, T0)
    await pub.publish({SID: PAUSED_S}, {SID: _Status("STALE")}, {}, T0 + 40 * SEC)
    same = await monitoring_state.read_states(client, [SID], T0 + 41 * SEC, heartbeat=_fresh)
    assert same[SID].since == T0
    await pub.publish({SID: PAUSED_S}, {SID: _Status("DISCONNECTED")}, {}, T0 + 50 * SEC)
    changed = await monitoring_state.read_states(client, [SID], T0 + 51 * SEC, heartbeat=_fresh)
    assert changed[SID].since == T0 + 50 * SEC and changed[SID].reason == "disconnected"
    await pub.publish({SID: ACTIVE_S}, {}, {}, T0 + 60 * SEC)
    back = await monitoring_state.read_states(client, [SID], T0 + 61 * SEC, heartbeat=_fresh)
    assert back[SID] == Entry(SID, ACTIVE, "", "", T0 + 60 * SEC)


async def test_an_unchanged_snapshot_is_not_rewritten_each_cycle_but_is_refreshed():
    client = _Client()
    pub = monitoring_state.Publisher(client)
    assert await pub.publish({SID: ACTIVE_S}, {}, {}, T0) is True
    assert await pub.publish({SID: ACTIVE_S}, {}, {}, T0 + 3 * SEC) is False
    assert client.sets == 1
    assert await pub.publish({SID: ACTIVE_S}, {}, {}, T0 + monitoring_state.REFRESH_S * SEC) is True
    assert client.sets == TWO_WRITES  # refreshed: a living worker's snapshot never ages out


async def test_workers_down_every_strategy_is_paused_never_its_last_colour():
    client = _Client()
    await monitoring_state.Publisher(client).publish({SID: ACTIVE_S}, {}, {}, T0)
    got = await monitoring_state.read_states(client, [SID, 7], T0 + 5 * SEC, heartbeat=_stale)
    assert got == {SID: Entry(SID, PAUSED, "workers_down", "", None), 7: Entry(7, PAUSED, "workers_down", "", None)}


async def test_a_snapshot_that_is_missing_old_future_corrupt_or_unreadable_is_paused_state_unreadable():
    fresh = encode_at(T0)
    cases = {"missing": None, "old": encode_at(T0 - 130 * SEC), "future": encode_at(T0 + 130 * SEC),
             "not json": "{nope", "wrong shape": json.dumps({"at": T0.isoformat(), "strategies": []}),
             "bad row": json.dumps({"at": T0.isoformat(), "strategies": {"100": {"status": "ok"}}}),
             "naive time": json.dumps({"at": "2026-11-27T10:00:00", "strategies": {}})}
    for name, raw in cases.items():
        client = _Client()
        if raw is not None:
            client.data[monitoring_state.key()] = raw
        got = await monitoring_state.read_states(client, [SID], T0, heartbeat=_fresh)
        assert got == {SID: Entry(SID, PAUSED, "state_unreadable", "", None)}, name
    ok = _Client()
    await _monitor_reports(ok, T0)
    ok.data[monitoring_state.key()] = fresh
    assert (await monitoring_state.read_states(ok, [SID], T0, heartbeat=_fresh))[SID].status == ACTIVE
    down = _Client(boom=True)
    got = await monitoring_state.read_states(down, [SID], T0, heartbeat=_fresh)
    assert got == {SID: Entry(SID, PAUSED, "state_unreadable", "", None)}


def encode_at(at):
    return monitoring_state.encode([Entry(SID, ACTIVE, "", "", at)], at)


async def test_a_strategy_the_snapshot_does_not_name_is_not_listed_never_active():
    client = _Client()
    await _monitor_reports(client, T0)
    await monitoring_state.Publisher(client).publish({SID: ACTIVE_S}, {}, {}, T0)
    got = await monitoring_state.read_states(client, [SID, 55], T0, heartbeat=_fresh)
    assert got[SID].status == ACTIVE and got[55] == Entry(55, PAUSED, "not_listed", "", None)


async def test_a_failing_store_never_stops_the_worker_and_is_logged(caplog):
    pub = monitoring_state.Publisher(_Client(boom=True))
    with caplog.at_level(logging.WARNING):
        assert await pub.publish({SID: PAUSED_S}, {}, {}, T0) is False
    assert any("writing the monitoring state failed" in r.getMessage() for r in caplog.records)
    assert await monitoring_state.Publisher(None).publish({SID: ACTIVE_S}, {}, {}, T0) is False


# ---- the worker's own path (real Worker, real price read) -----------------------------------------------------------

async def _cycle(scn_, rest, feed_spot):
    prov, now, calls = Prov(scn_), [scn_.clock_at], Calls()
    if not feed_spot:
        prov.spot = None
    client = _Client()
    w = _worker(prov, _watched(scn_), now, calls, want_client=client, rest_spot=_Reader(rest))
    await w.cycle()
    return client, now[0], w


async def test_the_worker_publishes_a_trade_it_cannot_price_as_paused_with_the_reason(scn):  # noqa: F811
    client, now, w = await _cycle(scn, SourceReading(SourceState.FAILED), feed_spot=False)
    got = await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh)
    assert got[SID].status == PAUSED and got[SID].reason == "leg_missing" and got[SID].since == now, got
    assert w.paused_reason[SID] is background.PriceState.LEG_MISSING


async def test_the_worker_publishes_a_stale_quote_with_the_quotes_own_reason(scn):  # noqa: F811
    stale = SourceReading(SourceState.STATED, Decimal("23430"), scn.clock_at - datetime.timedelta(minutes=10))
    client, now, _w = await _cycle(scn, stale, feed_spot=False)
    got = await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh)
    assert (got[SID].status, got[SID].reason, got[SID].why) == (PAUSED, "stale", "rest_stale"), got


async def test_the_worker_publishes_a_priced_trade_as_active(scn):  # noqa: F811
    client, now, _w = await _cycle(scn, SourceReading(SourceState.FAILED), feed_spot=True)
    await _monitor_reports(client, now)
    got = await monitoring_state.read_states(client, [SID], now, heartbeat=_fresh)
    assert got[SID] == Entry(SID, ACTIVE, "", "", now)
