"""GC-MU step 4c (REQ-165 AC-2): the background worker writes its strategies' leg tokens (plus the index token) to the
feed bus, so with no screen open the feed still subscribes them. Non-DB: a fake Redis and ADJ-02's fed provider; the
relay's own ``refresh_want`` reads what the worker wrote. Every answer state of the write has its own test."""
from __future__ import annotations

import dataclasses
import datetime
import logging

import pytest
from ofo.instruments.models import ZERODHA
from ofo.settings import calc as settings_calc
from ofo_app import background, chain_push, feed_bus, scenario_mode
from redis.exceptions import ConnectionError as RedisConnectionError

from tests_app.test_background_cycle import DEFAULTS, Calls, FakeGate, Prov, _prefs, _settings, _watched

OWNER = "owner"
LEGS_INDEX_AND_WINDOW = 62  # 4 legs + the index + the chain screen's window (15 strikes each side, CE and PE)
REFRESHED = 2
T0 = datetime.datetime(2026, 11, 2, 9, 30, tzinfo=datetime.UTC)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.sets = 0
        self.down = False

    async def set(self, key, value, px=None):
        if self.down:
            raise RedisConnectionError("down")
        self.sets += 1
        self.data[key] = value

    async def mget(self, *keys):
        return [self.data.get(k) for k in keys]


class IndexedProv(Prov):
    def index_id(self, underlying):
        return self.real.index_id(underlying)

    def subscribe(self, instrument_ids):
        """The worker's own hold (ADR-233 round 1): the real provider takes the instrument ids."""

    def unsubscribe(self, instrument_ids):
        pass


@pytest.fixture(scope="module")
def scn():
    return scenario_mode.load("ADJ-02")


def _window(prov, tracked) -> set[int]:
    """The chain screen's strike window around the spot (``limits.chain_strikes_each_side`` each side) of the first
    leg's expiry: the worker holds it too (finding 2), worked out here from the master, not from the worker."""
    first = tracked.position.legs[0]
    master = [lc for lc in prov.instrument_master()
              if lc.contract.name == tracked.position.underlying and lc.contract.expiry == first.expiry
              and lc.contract.strike is not None]
    grid = sorted({lc.contract.strike for lc in master})
    each = settings_calc.chain_strikes_each_side(DEFAULTS)
    win = set(chain_push.strike_window(grid, chain_push.atm_strike(grid, prov.spot.ltp), each, each))
    return {int(lc.ref(ZERODHA).broker_token) for lc in master if lc.contract.strike in win}


def _expected(prov, tracked) -> set[int]:
    wanted = {(x.expiry, x.strike, x.type) for x in tracked.position.legs}
    out = {int(lc.ref(ZERODHA).broker_token) for lc in prov.instrument_master()
           if lc.contract.name == "NIFTY" and (lc.contract.expiry, lc.contract.strike,
                                               lc.contract.instrument_type) in wanted}
    assert len(out) == len(wanted)
    index = prov.real.index_id("NIFTY")
    out |= {int(lc.ref(ZERODHA).broker_token) for lc in prov.instrument_master()
            if f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" == index}
    return out | _window(prov, tracked)


def _unlisted(w):
    """The same strategy as id 999 with its first leg on a strike the master does not list."""
    legs = list(w.tracked.position.legs)
    legs[0] = dataclasses.replace(legs[0], strike=legs[0].strike + 1)
    pos = dataclasses.replace(w.tracked.position, legs=tuple(legs))
    return background.Watched(OWNER, 999, dataclasses.replace(w.tracked, position=pos), {}, True, OWNER, None, None,
                              resolved=None)


def _worker(prov, watched, now, client):
    async def lister():
        return watched
    return background.Worker(provider_for=lambda _o: prov, lister=lister, clock=lambda: now[0], settings=_settings(),
                             preferences=_prefs, recorder=Calls(), want_client=client, gate_store=FakeGate())


async def _relay_wants(client) -> list[int]:
    relay = feed_bus.FeedRelay(OWNER, lambda: T0)
    await relay.refresh_want(client)
    return relay.subscribed_tokens()


async def test_core_no_snapshot_the_relay_wants_exactly_the_legs_and_the_index(scn):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    prov.closed = True  # no API snapshot, no check: only the write under test
    watched = _watched(scn)
    await _worker(prov, watched, now, client).cycle()
    assert feed_bus.want_key(OWNER) not in client.data
    got = await _relay_wants(client)
    # ADJ-02: 4 legs, the index and the strike window the worker holds for the chain screen
    assert got == sorted(_expected(prov, watched[0].tracked)) and len(got) == LEGS_INDEX_AND_WINDOW


async def test_no_monitored_strategy_writes_an_empty_snapshot_only_for_a_written_owner(scn):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    watched = _watched(scn)
    w = _worker(prov, watched, now, client)
    await w.cycle()
    assert await _relay_wants(client)
    watched.clear()
    w._rebuilt_at = None  # the lister now returns nothing
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert await _relay_wants(client) == []  # the stale wishes lapse at once, not after the TTL
    empty = _worker(prov, [], now, FakeRedis())
    await empty.cycle()
    assert empty._want_client.sets == 0  # an owner never written gets nothing


async def test_a_leg_without_a_token_pauses_that_strategy_and_the_others_are_written(scn, monkeypatch):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    good, bad = _watched(scn, 2)
    bad = _unlisted(bad)
    await _worker(prov, [good, bad], now, client).cycle()
    assert await _relay_wants(client) == sorted(_expected(prov, good.tracked))


async def test_a_leg_without_a_token_shows_paused_with_the_no_price_reason(scn):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    prov.closed = True
    (w0,) = _watched(scn)
    bad = _unlisted(w0)
    w = _worker(prov, [bad], now, client)
    await w.cycle()
    assert w.status[999] is background.MonitoringStatus.PAUSED
    assert w.paused_reason[999] is background.PriceState.LEG_MISSING
    assert await _relay_wants(client) == []


async def test_redis_not_answering_is_counted_and_the_cycle_continues(scn, caplog):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    client.down = True
    w = _worker(prov, _watched(scn), now, client)
    with caplog.at_level(logging.ERROR, logger="ofo_app.background"):
        await w.cycle()
    assert (0, "ConnectionError") in w.errors and "writing the wanted tokens" in caplog.text
    assert w.checks  # the check still ran
    client.down = False
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert await _relay_wants(client)  # retried on the next cycle


async def test_above_the_cap_is_refused_logged_and_counted_never_cut(scn, monkeypatch, caplog):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    monkeypatch.setattr(feed_bus, "MAX_WANTED_TOKENS", 3)
    w = _worker(prov, _watched(scn), now, client)
    with caplog.at_level(logging.ERROR, logger="ofo_app.background"):
        await w.cycle()
    assert (0, "WantTooLarge") in w.errors and "exceed the cap" in caplog.text
    assert client.sets == 0


async def test_rewritten_each_refresh_period_not_every_cycle(scn):
    prov, now, client = IndexedProv(scn), [scn.clock_at], FakeRedis()
    prov.closed = True
    w = _worker(prov, _watched(scn), now, client)
    await w.cycle()
    now[0] += datetime.timedelta(milliseconds=300)
    await w.cycle()
    assert client.sets == 1  # same set, inside WANT_REFRESH_S
    now[0] += datetime.timedelta(seconds=1)
    await w.cycle()
    assert client.sets == REFRESHED  # refreshed before the snapshot's TTL
