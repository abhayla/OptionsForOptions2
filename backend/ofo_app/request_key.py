"""Lane FD2 item 2 (issues #869, #871; ADR-017): the order request key ``client_request_id``.

The page makes one UUID per Confirm and sends it with every resend of that Confirm. The server keeps the key for
``KEY_TTL_S`` seconds (longer than the 120 s unknown-outcome window) in the app's short-lived store (Redis); a durable
key store needs a migration (listed for Lane FD). A key goes through three states:

* claimed (``pending``): the first request is placing; any other request with the key is told so and places nothing;
* ``done``: the first request committed; a repeat gets the first result and places nothing;
* freed: the first request was refused (nothing stored); the same key may be used again.

An exception whose outcome is unknown (a failed commit, a failed read after the commit) leaves the key ``pending``
until it expires: a repeat is told "still being placed", never placed twice (fail closed). A request without a key
never touches the store. A key store that cannot be read refuses a keyed request (``request_key_store_unavailable``).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from ofo_app import feed_bus, feed_mode
from ofo_app.errors import Failure
from ofo_app.strategy_refused import StrategyRefused

KEY_TTL_S = 600
PENDING, DONE = "pending", "done"


class KeyStoreDown(Exception):
    """The key store could not be read or written."""


class KeyStore(Protocol):
    async def claim(self, key: str, record: Mapping[str, Any]) -> dict[str, Any] | None:
        """Atomically store ``record`` when ``key`` is free: None. Else the record already there."""

    async def put(self, key: str, record: Mapping[str, Any]) -> None: ...

    async def release(self, key: str) -> None: ...


def new_client(url: str) -> aioredis.Redis:
    return feed_bus.new_client(url)


class RedisKeyStore:
    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._factory = client_factory

    async def claim(self, key: str, record: Mapping[str, Any]) -> dict[str, Any] | None:
        try:
            client = self._factory()
            for _ in range(3):  # a key that expires between the failed SET and the GET is claimed on the next turn
                if await client.set(key, json.dumps(record), nx=True, ex=KEY_TTL_S):
                    return None
                raw = await client.get(key)
                if raw is not None:
                    found = json.loads(raw)
                    if not isinstance(found, dict):
                        raise KeyStoreDown("the stored key record is not an object")
                    return found
            raise KeyStoreDown("the key could be neither claimed nor read")
        except (RedisError, OSError, TimeoutError, ValueError, feed_mode.FeedModeRefused) as exc:
            raise KeyStoreDown(str(exc)) from exc

    async def put(self, key: str, record: Mapping[str, Any]) -> None:
        try:
            await self._factory().set(key, json.dumps(record), ex=KEY_TTL_S)
        except (RedisError, OSError, TimeoutError, feed_mode.FeedModeRefused) as exc:
            raise KeyStoreDown(str(exc)) from exc

    async def release(self, key: str) -> None:
        try:
            await self._factory().delete(key)
        except (RedisError, OSError, TimeoutError, feed_mode.FeedModeRefused) as exc:
            raise KeyStoreDown(str(exc)) from exc


_CLIENT: dict[str, Any] = {}  # one lazy client for the process (the bus address is read on first use)


def _shared_client() -> Any:
    if "client" not in _CLIENT:
        _CLIENT["client"] = new_client(feed_mode.redis_url())
    return _CLIENT["client"]


def get_key_store() -> KeyStore:
    """The dependency the order routes use (tests replace it)."""
    return RedisKeyStore(_shared_client)


def scoped(user_ref: str, key: uuid.UUID | str) -> str:
    return f"ofo:order-key:{user_ref}:{key}"


def fingerprint(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def pending(strategy_id: int, body: Mapping[str, Any]) -> dict[str, Any]:
    return {"state": PENDING, "strategy_id": strategy_id, "fp": fingerprint(body)}


def _refused(template: str, failure: Failure = Failure.CONFLICT) -> StrategyRefused:
    return StrategyRefused(template, failure)


async def begin(store: KeyStore, user_ref: str, key: uuid.UUID, strategy_id: int,
                body: Mapping[str, Any]) -> dict[str, Any] | None:
    """Claim the key. None: this request is the first and places. A ``done`` record: a repeat, answer it with that
    record and place nothing. Every other case is refused by name (nothing is placed)."""
    try:
        found = await store.claim(scoped(user_ref, key), pending(strategy_id, body))
    except KeyStoreDown:
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY) from None
    if found is None:
        return None
    if found.get("strategy_id") != strategy_id:
        raise _refused("request_key_other_strategy")
    if found.get("fp") != fingerprint(body):
        raise _refused("request_key_different_body")
    if found.get("state") != DONE:
        raise _refused("request_key_in_progress")
    return found


def done(strategy_id: int, body: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return pending(strategy_id, body) | {"state": DONE, "result": dict(result)}


async def finish(store: KeyStore, user_ref: str, key: uuid.UUID, record: Mapping[str, Any]) -> None:
    """The first request committed: keep its result (``done``) for a repeat. A store that fails now leaves the key
    pending (a repeat is told "still being placed"), and the first request's own answer is still sent."""
    try:
        await store.put(scoped(user_ref, key), record)
    except KeyStoreDown:
        return


async def free(store: KeyStore, user_ref: str, key: uuid.UUID) -> None:
    """The first request was refused and stored nothing: the key may be used again. A failed release only means the
    key stays claimed until it expires."""
    try:
        await store.release(scoped(user_ref, key))
    except KeyStoreDown:
        return
