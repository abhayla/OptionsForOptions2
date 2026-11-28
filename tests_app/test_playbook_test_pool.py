"""Lane H item 5 (REQ-049 AC-4; Lane R's finding pool-held-across-market-wait):
POST /api/playbooks/test reads every tracked strategy's market and REST price. While those reads wait on the broker
the request must not hold its pooled connection (the role has 10 connections, DB_POOL_SIZE 4 on the PC)."""
from __future__ import annotations

import asyncio
import dataclasses

from httpx import ASGITransport, AsyncClient
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo_app import db as app_db
from ofo_app import playbook_store
from ofo_app.adjustment_readers import read_market
from ofo_app.routes.adjustment import get_market_reader, get_rest_spot_reader
from test_adjustment_check import (
    _reset_engine,
    _seeded,
    app_db_url,  # noqa: F401 - the fixture of the check tests
)

STALL_S = 2.0


async def test_playbook_test_holds_no_connection_while_the_rest_read_waits(app_db_url, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    _reset_engine()
    await _seeded(app_db_url, monkeypatch, "ADJ-01")
    async with app_db_url.begin() as conn:
        system = await playbook_store.active_for(conn, "owner", "ic")
    from ofo_app.main import create_app  # noqa: PLC0415 - the env must be set first
    app = create_app()
    reads: list[str] = []

    async def stalled(name):
        reads.append(name)
        await asyncio.sleep(STALL_S)
        raise TimeoutError

    async def no_tick(tracked, ctx):  # ADR-330 (39): the quote is asked only when the feed holds no usable index tick
        market = await read_market(tracked, ctx)
        return dataclasses.replace(market, feed=SourceReading(SourceState.ABSENT), feed_quote=None)

    app.dependency_overrides[get_market_reader] = lambda: no_tick
    app.dependency_overrides[get_rest_spot_reader] = lambda: stalled
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        body = (await ac.get(f"/api/playbooks/{system.id}")).json()["body"]
        task = asyncio.create_task(ac.post("/api/playbooks/test", json={"type": "ic", "body": body}))
        await asyncio.sleep(0.5)
        held = app_db.get_engine().pool.checkedout()
        await task
    await app_db.close_db()
    assert reads, "the REST reader was not reached: the test proves nothing"
    assert held == 0, f"{held} pooled connection(s) held while the REST read waits"
