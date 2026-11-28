"""Lane FD2 item 2 (issues #869, #871; ADR-017): the order request key ``client_request_id``.

The page makes one UUID per Confirm and sends it with every resend of that Confirm. The server keeps the key for
``KEY_TTL_S`` seconds (longer than the 120 s unknown-outcome window) in the app's short-lived store (Redis), the fast
path. FD3 item 2 (migration 0061): the record of truth is ``public.order_request_keys``, claimed in the SAME transaction
as the orders (see the end of this module); a repeat after a Redis flush or expiry still finds it. A key goes through
three states:

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
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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


# ---- the durable record (Lane FD3 item 2, migration 0061): public.order_request_keys ---------------------------------
# The record of truth. The claim is written in the SAME transaction as the orders (or the sealed plan), so a crash can
# neither store the orders without the key nor the key without the orders; a repeat reads the row. Redis stays the fast
# path for "the first request is still running" (582). A table that cannot be read or written refuses the keyed
# request by name (583) and stores nothing.

_DB_CLAIM = text(
    "INSERT INTO public.order_request_keys (user_ref, request_key, strategy_id, body_sha256, door, state) "
    "VALUES (:u, :k, :s, :h, :d, 'pending') ON CONFLICT (user_ref, request_key) DO NOTHING RETURNING request_key")
_DB_READ = text("SELECT strategy_id, body_sha256, door, state, result FROM public.order_request_keys "
                "WHERE user_ref = :u AND request_key = :k")
_DB_DONE = text("UPDATE public.order_request_keys SET state = 'done', result = CAST(:r AS jsonb), "
                "finished_at = clock_timestamp() WHERE user_ref = :u AND request_key = :k AND state = 'pending'")
DOORS = ("paper", "real")


class Repeated(Exception):  # a signal, not a failure: the key was already used and committed
    """The key is already recorded by a request that committed: ``result`` is what that request stored."""

    def __init__(self, result: Mapping[str, Any]) -> None:
        super().__init__("request key already used")
        self.result: dict[str, Any] = dict(result)


async def _read(db: Any, user_ref: str, key: uuid.UUID) -> Any:
    try:
        return (await db.execute(_DB_READ, {"u": user_ref, "k": key})).first()
    except (SQLAlchemyError, OSError, TimeoutError):
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY) from None


def _judge(row: Any, strategy_id: int, body: Mapping[str, Any]) -> dict[str, Any]:
    """The rules for a key that is already recorded: other strategy 580, other orders 581, still pending 582, else the
    stored result of the request that committed."""
    if int(row.strategy_id) != strategy_id:
        raise _refused("request_key_other_strategy")
    if row.body_sha256 != fingerprint(body):
        raise _refused("request_key_different_body")
    if row.state != DONE:
        raise _refused("request_key_in_progress")
    return dict(row.result or {})


async def lookup(db: Any, user_ref: str, key: uuid.UUID, strategy_id: int, body: Mapping[str, Any]
                 ) -> dict[str, Any] | None:
    """None: the key is not recorded (this request is the first). Else the stored result of the request that committed
    (a repeat; place nothing). Refused by name for another strategy, other orders, a pending row, an unreadable table.
    """
    row = await _read(db, user_ref, key)
    return None if row is None else _judge(row, strategy_id, body)


async def claim_in_transaction(db: Any, user_ref: str, key: uuid.UUID, strategy_id: int,  # noqa: PLR0913
                               body: Mapping[str, Any], door: str) -> None:
    """Write the claim in the caller's transaction (it commits or rolls back with the orders). When another request
    committed the key first (this INSERT waits for it), raises ``Repeated`` with that request's result; the caller rolls
    back and answers it. A table that cannot be written refuses the request (nothing stored)."""
    if door not in DOORS:
        raise ValueError(door)
    try:
        inserted = (await db.execute(_DB_CLAIM, {"u": user_ref, "k": key, "s": strategy_id, "h": fingerprint(body),
                                                 "d": door})).first()
    except (SQLAlchemyError, OSError, TimeoutError):
        await db.rollback()
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY) from None
    if inserted is not None:
        return
    row = await _read(db, user_ref, key)
    if row is None:  # the other request rolled back between our INSERT and this read: nothing is recorded, refuse
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY)
    raise Repeated(_judge(row, strategy_id, body))


async def finish_in_transaction(db: Any, user_ref: str, key: uuid.UUID, result: Mapping[str, Any]) -> None:
    """Mark the claim ``done`` with the result, in the same transaction, right before the commit."""
    try:
        done = await db.execute(_DB_DONE, {"u": user_ref, "k": key, "r": json.dumps(result, default=str)})
        done_rows = done.rowcount
    except (SQLAlchemyError, OSError, TimeoutError):
        await db.rollback()
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY) from None
    if done_rows != 1:  # the claim is gone (a rollback since): never commit orders without it
        await db.rollback()
        raise _refused("request_key_store_unavailable", Failure.UPSTREAM_BUSY)
