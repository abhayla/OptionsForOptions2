"""GC-MU step 4b: the feed's wanted set is the union of the API's snapshot and the background role's own."""
from __future__ import annotations

import asyncio
import datetime
import json

import pytest
from ofo_app import feed_bus
from redis.exceptions import ConnectionError as RedisConnectionError

USER = "ua"
T0 = datetime.datetime(2026, 11, 2, 9, 30, tzinfo=datetime.UTC)


class FakeRedis:
    """Just set / mget; an expired or absent key reads None (the real client returns None for both)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.px: dict[str, int] = {}
        self.down = False

    async def set(self, key, value, px=None):
        self.data[key] = value
        self.px[key] = px

    async def mget(self, *keys):
        if self.down:
            raise RedisConnectionError("down")
        return [self.data.get(k) for k in keys]


def _relay() -> feed_bus.FeedRelay:
    return feed_bus.FeedRelay(USER, lambda: T0)


async def _api(client, tokens):
    await client.set(feed_bus.want_key(USER), feed_bus.encode_want(USER, tokens), px=feed_bus.WANT_TTL_MS)


def test_core_only_the_background_key_reaches_the_wanted_set():
    async def go():
        client, relay = FakeRedis(), _relay()
        await feed_bus.write_background_want(client, USER, [101, 102])
        assert client.px[feed_bus.background_want_key(USER)] == feed_bus.WANT_TTL_MS
        assert feed_bus.background_want_key(USER) == feed_bus.want_key(USER) + ":bg"
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [101, 102]
    asyncio.run(go())


def test_only_the_api_key():
    async def go():
        client, relay = FakeRedis(), _relay()
        await _api(client, [1, 2])
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [1, 2]
    asyncio.run(go())


def test_both_keys_are_unioned():
    async def go():
        client, relay = FakeRedis(), _relay()
        await _api(client, [1, 2])
        await feed_bus.write_background_want(client, USER, [2, 3])
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [1, 2, 3]
    asyncio.run(go())


def test_one_key_expired_the_other_still_applies():
    async def go():
        client, relay = FakeRedis(), _relay()
        await _api(client, [1])
        await feed_bus.write_background_want(client, USER, [9])
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [1, 9]
        del client.data[feed_bus.want_key(USER)]  # API key lapsed
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [9]
        del client.data[feed_bus.background_want_key(USER)]
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == []
    asyncio.run(go())


@pytest.mark.parametrize("bad", ["not json", json.dumps({"u": "other", "tokens": [7]}),
                                 json.dumps({"u": USER, "tokens": [True]})])
def test_a_malformed_or_foreign_key_counts_as_nothing_and_never_drops_the_good_one(bad):
    async def go():
        for bad_is_background in (True, False):
            client, relay = FakeRedis(), _relay()
            good_key = feed_bus.want_key(USER) if bad_is_background else feed_bus.background_want_key(USER)
            bad_key = feed_bus.background_want_key(USER) if bad_is_background else feed_bus.want_key(USER)
            client.data[good_key] = feed_bus.encode_want(USER, [5])
            client.data[bad_key] = bad
            await relay.refresh_want(client)
            assert relay.subscribed_tokens() == [5]
            assert relay.counters["bus_malformed"] == 1
    asyncio.run(go())


def test_redis_not_answering_keeps_the_last_wishes_and_counts():
    async def go():
        client, relay = FakeRedis(), _relay()
        await feed_bus.write_background_want(client, USER, [101])
        await relay.refresh_want(client)
        client.down = True
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == [101]
        assert relay.counters["redis_failed"] == 1
    asyncio.run(go())


def test_a_union_above_the_cap_is_refused_whole_like_one_oversize_snapshot(monkeypatch):
    monkeypatch.setattr(feed_bus, "MAX_WANTED_TOKENS", 3)

    async def go():
        client, relay = FakeRedis(), _relay()
        await _api(client, [1, 2])
        await feed_bus.write_background_want(client, USER, [3, 4])  # each within the cap, union is 4
        await relay.refresh_want(client)
        assert relay.subscribed_tokens() == []
        assert relay.counters["bus_malformed"] == 1
        client2, relay2 = FakeRedis(), _relay()
        await _api(client2, [1, 2, 3, 4])  # one oversize snapshot behaves the same
        await relay2.refresh_want(client2)
        assert relay2.subscribed_tokens() == [] and relay2.counters["bus_malformed"] == 1
    asyncio.run(go())
