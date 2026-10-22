"""REQ-113: the market-data process. It holds the owner's Kite price socket, so restarting or redeploying the API
process never cuts it (AC-1, AC-2). Run it with ``python -m ofo_app.feed_main`` (FEED_MODE=bus on the API side).

It reuses the REAL ``KiteSocket`` unchanged (a listed broker-adapter file, REQ-063 AC-1); a ``FeedRelay`` stands
where the socket expects its provider, publishes the raw frames to the bus and applies the API's wanted-token
snapshot. It parses nothing (the API owns the one frame parser) and it holds the Kite token only in memory,
loaded from the encrypted token store (REQ-015). The egress gate is
installed BEFORE any Kite call, exactly as ``create_app`` does (REQ-073 AC-4); the database must not be the
test database (ADR-078); the pool is checked against the role's connection limit like the API's.

Not in this part (A1/B/C): login and Disconnect control messages over the bus, the per-user socket map, the
cap refuse-and-log, the 06:00 session end, and the order-update stream.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import sys
from collections.abc import Callable
from typing import Any

from ofo.broker import egress as _egress
from ofo.timeutil import IST_UNNAMED as IST

from ofo_app import event_loop, feed_bus, feed_mode

log = logging.getLogger("ofo_app.feed_main")

EXIT_NO_SESSION = 3


def prepare_process() -> None:
    """The first thing the process does: install the egress gate (idempotent). From here this process connects only to
    loopback, the database and the Kite doors, and starts no process."""
    _egress.install()


def feed_settings():
    """The process settings, built as a LIVE run: refuses the test database or an unnamed one (ADR-078) and the real
    Kite address under APP_ENV=test, exactly like the API."""
    from ofo_app.config import Settings  # noqa: PLC0415

    return Settings(LIVE_MARKET=True)  # type: ignore[call-arg]


def build_socket(relay: feed_bus.FeedRelay, *, api_key: str, access_token: str, ws_url: str,  # noqa: PLR0913
                 clock: Callable[[], datetime.datetime], connect: Callable | None = None):
    """The real ``KiteSocket`` over the relay. Its address check refuses anything but ``wss://ws.kite.trade`` (loopback
    only in the test suites' mode); ``connect`` is a test seam it refuses outside them."""
    from ofo_app.kite_ws import KiteSocket  # noqa: PLC0415

    return KiteSocket(relay, api_key=api_key, access_token=access_token, clock=clock, base_url=ws_url,  # type: ignore[arg-type]
                      connect=connect)


def _now() -> datetime.datetime:
    return datetime.datetime.now(IST)


async def run_feed(*, user_ref: str, api_key: str, access_token: str, ws_url: str,  # noqa: PLR0913
                   redis_url: str | None = None, client: Any = None,
                   clock: Callable[[], datetime.datetime] = _now,
                   connect: Callable | None = None) -> str:
    """Hold the user's Kite socket and relay it to the bus until it is stopped or the session ends. Returns the socket's
    result word. The token is passed in memory and is never put on the bus or in a log line."""
    owned = client is None
    client = client or feed_bus.new_client(redis_url or feed_mode.redis_url())
    relay = feed_bus.FeedRelay(user_ref, clock)
    socket = build_socket(relay, api_key=api_key, access_token=access_token, ws_url=ws_url, clock=clock,
                          connect=connect)
    relay.bind(socket)
    jobs = [asyncio.create_task(job(client), name=name) for name, job in
            (("feed-publish", relay.publish_loop), ("feed-want", relay.want_loop), ("feed-status", relay.status_loop))]
    try:
        result = await socket.run()
        await relay.flush(client)  # the last events (dropped / ended) go out before the status says so
        with contextlib.suppress(Exception):
            await relay.publish_status(client)
        return result
    finally:
        for job in jobs:
            job.cancel()
        for job in jobs:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await job
        if owned:
            with contextlib.suppress(Exception):
                await client.aclose()


async def _main() -> int:
    from ofo_app import live_market  # noqa: PLC0415
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import access_token_for  # noqa: PLC0415
    from ofo_app.config import app_env  # noqa: PLC0415
    from ofo_app.db import close_db, get_engine, verify_pool_budget  # noqa: PLC0415

    prepare_process()
    event_loop.require_selector_loop()  # a loop whose connects the egress gate cannot see is refused (W-080 r7)
    settings = feed_settings()
    live_market.require_safe(app_env() or "", settings.KITE_WS_URL)
    redis_url = feed_mode.redis_url()
    config = load_broker_config()
    await verify_pool_budget()
    try:
        async with get_engine().connect() as conn:
            token = await access_token_for(conn, live_market.OWNER_REF, TokenCipher(config.token_key))
    finally:
        await close_db()
    if token is None:
        log.error("market-data process: no active Kite session; connect through the login first")
        return EXIT_NO_SESSION
    result = await run_feed(user_ref=live_market.OWNER_REF, api_key=config.api_key, access_token=token,
                            ws_url=settings.KITE_WS_URL, redis_url=redis_url)
    log.warning("market-data process ended: %s", result)
    return 0


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    logging.basicConfig(level=logging.INFO)
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
