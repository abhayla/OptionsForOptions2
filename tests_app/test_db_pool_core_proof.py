"""GC-6 POOL-BUDGET core proof: two API processes under load never exceed the ofo_app role's connection limit.

Core: every API process sizes its DB pool from the role's limit (ADR-048: CONNECTION LIMIT 5 in CI).
Proof: this is a DATABASE test (the app_engine / admin_engine fixtures skip it locally without TEST_DATABASE_URL
and TEST_ADMIN_DATABASE_URL; CI runs it against its own PostgreSQL). It builds the app's engine TWICE the way
``db.get_engine`` does, with the DEFAULT settings (= two API processes), drives concurrent load through the real
connection paths (the charge-rates load with an expired cache, ``access_token_for`` on a fresh connection, the strategy
list read) from many tasks, and samples ``pg_stat_activity`` for the role through the OWNER connection (so the sampler
takes no slot from the role). The second case uses the OLD defaults (pool 5, overflow 10) and must hit
TooManyConnectionsError: that is what shows the first case can fail.
"""
from __future__ import annotations

import asyncio
import contextvars
import os
import types

from ofo_app import broker_token_store as tokens
from ofo_app import db, strategy_store
from ofo_app.broker_crypto import TokenCipher
from ofo_app.config import Settings
from ofo_app.routes import outcome
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROLE_LIMIT = 5  # the CI role: CONNECTION LIMIT 5 (the workflow creates it; test_db_pool_startup pins the number)
API_PROCESSES = 2
TASKS_PER_PROCESS = 24
RUN_SECONDS = 30.0  # the default settings, held under load this long
OLD_RUN_SECONDS = 20.0  # the old defaults: ends at the first refusal, this is only the ceiling
SAMPLE_EVERY = 0.05
OLD_POOL, OLD_OVERFLOW = 5, 10  # the settings before GC-6
PATHS = ("rates", "token", "list")

_process: contextvars.ContextVar[int] = contextvars.ContextVar("process")


def _is_too_many(exc: BaseException | None) -> bool:
    while exc is not None:
        if "TooManyConnections" in type(exc).__name__ or "too many connections" in str(exc).lower():
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _settings(url, pool: int, overflow: int):
    return types.SimpleNamespace(DATABASE_URL=url, DB_POOL_SIZE=pool, DB_MAX_OVERFLOW=overflow)


async def _one_call(engine, how: str, user: str, cipher: TokenCipher) -> None:
    """One call down a real connection path of the app."""
    if how == "rates":
        outcome._rates_cache.update(until=0.0, flight=None)  # an expired cache: this call loads
        await outcome.load_charge_rates()
    elif how == "token":
        async with engine.connect() as conn:  # a fresh connection, as live_market opens it
            assert await tokens.access_token_for(conn, user, cipher) == "ACtok_fake_pool_proof"
    else:
        async with engine.connect() as conn:
            await strategy_store.list_strategies(conn, user)


async def _drive(monkeypatch, app_engine, admin_engine, pool: int, overflow: int, seconds: float, *, stop_on_refusal):
    """Two engines built by the app's own ``db.get_engine`` code; returns (peak role connections, errors)."""
    url = app_engine.url
    monkeypatch.setattr(db, "get_settings", lambda: _settings(url, pool, overflow))
    engines = [db.get_engine.__wrapped__() for _ in range(API_PROCESSES)]
    makers = [async_sessionmaker(e, class_=AsyncSession, expire_on_commit=False) for e in engines]
    monkeypatch.setattr(db, "get_sessionmaker", lambda: makers[_process.get()])
    async with app_engine.connect() as conn:
        role = (await conn.execute(text("SELECT current_user"))).scalar_one()
    cipher, user = TokenCipher(os.urandom(32)), "pool-proof-" + os.urandom(6).hex()
    async with app_engine.begin() as conn:
        await tokens.store_session(conn, user, "ACtok_fake_pool_proof", cipher)

    stop, peak, errors = asyncio.Event(), [0], []
    loop = asyncio.get_running_loop()
    loop.call_later(seconds, stop.set)

    async def sampler():
        async with admin_engine.connect() as conn:
            while not stop.is_set():
                n = (await conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE usename = :r"),
                                        {"r": role})).scalar_one()
                peak[0] = max(peak[0], n)
                await asyncio.sleep(SAMPLE_EVERY)

    async def worker(idx: int):
        _process.set(idx % API_PROCESSES)
        engine, turn = engines[idx % API_PROCESSES], idx
        while not stop.is_set():
            turn += 1
            try:
                await _one_call(engine, PATHS[turn % len(PATHS)], user, cipher)
            except Exception as exc:  # noqa: BLE001 - every failure is the evidence
                errors.append(exc)
                if stop_on_refusal and _is_too_many(exc):
                    stop.set()

    monkeypatch.setattr(outcome, "_rates_cache", {"until": 0.0, "value": None, "flight": None})
    sampling = asyncio.create_task(sampler())
    workers = [asyncio.create_task(worker(i)) for i in range(TASKS_PER_PROCESS * API_PROCESSES)]
    try:
        await asyncio.gather(*workers)
        await sampling
    finally:
        for e in engines:
            await e.dispose()
    return peak[0], errors


async def test_two_processes_with_the_default_settings_never_exceed_the_role_limit(monkeypatch, app_engine,
                                                                                  admin_engine):
    defaults = Settings.model_fields
    pool, overflow = defaults["DB_POOL_SIZE"].default, defaults["DB_MAX_OVERFLOW"].default
    assert API_PROCESSES * (pool + overflow) <= ROLE_LIMIT  # the budget on paper
    peak, errors = await _drive(monkeypatch, app_engine, admin_engine, pool, overflow, RUN_SECONDS,
                                stop_on_refusal=False)
    assert errors == [], [repr(e) for e in errors[:3]]  # no TooManyConnectionsError, no other failure
    assert 0 < peak <= ROLE_LIMIT  # the load really held connections, and never above the limit


async def test_the_old_defaults_do_hit_the_limit(monkeypatch, app_engine, admin_engine):
    """The discriminating case: pool 5 + overflow 10 per process, two processes, the same load -> the role refuses."""
    _peak, errors = await _drive(monkeypatch, app_engine, admin_engine, OLD_POOL, OLD_OVERFLOW, OLD_RUN_SECONDS,
                                 stop_on_refusal=True)
    assert any(_is_too_many(e) for e in errors), [repr(e) for e in errors[:3]]
