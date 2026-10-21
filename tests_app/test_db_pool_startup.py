"""GC-6 POOL-BUDGET (core): the API's pool is sized from the ofo_app role's connection limit (ADR-048).

RCA: one API process could open pool_size + max_overflow (5 + 10) connections against a role limited to 5, plus a
second connection per token read and one session per concurrent rates load -> TooManyConnectionsError on a second
API process / the 13-card Live Strategies page (findings db-role-limit-below-pool-size,
db-role-connection-limit-below-pool-size).
Class: every path that opens an ofo_app connection: pool size per process, nested connections, cache herds.
No database is touched here: fakes only.
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import re

import pytest
from fastapi import FastAPI
from ofo_app import config, db, main

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ("." + "github") / "workflows" / "app-tests.yml").read_text(encoding="utf-8")
API_PROCESSES = 2  # a developer / the live run: two API processes on one role


def _role_limit_in_ci() -> int:
    limits = set(re.findall(r"CONNECTION LIMIT (\d+)", WORKFLOW))
    assert len(limits) == 1, limits
    return int(limits.pop())


@pytest.fixture
def fresh(monkeypatch):
    config.get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example@localhost:5432/example")
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)
    yield monkeypatch
    config.get_settings.cache_clear()


def test_real_settings_budget_fits_the_role_limit_for_two_processes(fresh):
    """The default settings: pool_size + max_overflow per process <= role limit / API processes."""
    assert db.pool_maximum() <= _role_limit_in_ci() // API_PROCESSES


class _Result:
    def __init__(self, value):
        self.value = value

    def one(self):
        """(rolconnlimit, rolsuper): a bare number is a non-superuser's limit."""
        return self.value if isinstance(self.value, tuple) else (self.value, False)


class _Conn:
    def __init__(self, outcome):
        self.outcome, self.sql = outcome, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self.sql.append(str(stmt))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return _Result(self.outcome)


class _Engine:
    def __init__(self, outcome):
        self.conn = _Conn(outcome)

    def connect(self):
        return self.conn


@pytest.mark.parametrize(("pool", "overflow", "limit", "refused"), [
    (5, 10, 5, True),    # the old default against the CI role
    (3, 3, 5, True),     # one over
    (3, 2, 5, False),    # exactly the limit
    (1, 0, 5, False),
    (5, 10, -1, False),  # -1 = unlimited role
    (5, 10, (5, True), False),  # a superuser is not limited by PostgreSQL: skipped
    (5, 10, (5, False), True),  # the same limit for a non-superuser is refused
])
async def test_startup_refuses_a_pool_above_the_role_limit(fresh, pool, overflow, limit, refused):
    fresh.setenv("DB_POOL_SIZE", str(pool))
    fresh.setenv("DB_MAX_OVERFLOW", str(overflow))
    engine = _Engine(limit)
    if refused:
        with pytest.raises(db.PoolBudgetError) as err:
            await db.verify_pool_budget(engine)  # type: ignore[arg-type]
        shown = limit if isinstance(limit, int) else limit[0]
        assert str(pool + overflow) in str(err.value) and str(shown) in str(err.value)  # names both numbers
    else:
        await db.verify_pool_budget(engine)  # type: ignore[arg-type]
    (sql,) = engine.conn.sql
    assert "rolconnlimit" in sql and "rolsuper" in sql and "current_user" in sql  # read once, for the connected role


async def test_a_failed_limit_read_warns_and_starts(fresh, caplog):
    """Fail-open only on the read failure: a pool of 15 against an unreadable limit still starts, with a warning."""
    fresh.setenv("DB_POOL_SIZE", "5")
    fresh.setenv("DB_MAX_OVERFLOW", "10")
    with caplog.at_level(logging.WARNING, logger="ofo_app.db"):
        await db.verify_pool_budget(_Engine(OSError("no database")))  # type: ignore[arg-type]
    assert any("not read" in r.getMessage() and "OSError" in r.getMessage() for r in caplog.records)


class _HangingConn:
    async def __aenter__(self):
        await asyncio.sleep(3600)  # never answers

    async def __aexit__(self, *exc):
        return False


class _HangingEngine:
    def connect(self):
        return _HangingConn()


async def test_a_hanging_limit_read_times_out_warns_and_starts(fresh, caplog):
    """MINOR-1: a database that never answers does not hold start-up: after the timeout it is a read failure."""
    fresh.setattr(db, "ROLE_LIMIT_READ_TIMEOUT_SECONDS", 0.05)
    fresh.setenv("DB_POOL_SIZE", "5")
    fresh.setenv("DB_MAX_OVERFLOW", "10")
    with caplog.at_level(logging.WARNING, logger="ofo_app.db"):
        await asyncio.wait_for(db.verify_pool_budget(_HangingEngine()), timeout=1.0)  # type: ignore[arg-type]
    assert any("not read" in r.getMessage() and "TimeoutError" in r.getMessage() for r in caplog.records)


async def test_the_lifespan_refuses_to_start_when_the_pool_budget_is_refused(fresh):
    """MAJOR-2: main._lifespan awaits verify_pool_budget BEFORE anything else starts (no live market is built)."""
    calls = []

    async def refuse():
        calls.append("verify")
        raise db.PoolBudgetError("pool 15 above role limit 5")

    class _Market:
        def __init__(self):
            calls.append("market built")

    fresh.setattr(main, "verify_pool_budget", refuse)
    fresh.setattr(main.live_market, "live_requested", lambda: True)
    fresh.setattr(main.live_market, "LiveMarket", _Market)
    fresh.setattr(main.event_loop, "require_selector_loop", lambda: None)  # the first two guards are not the subject
    fresh.setattr(main._egress, "installed", lambda: True)
    app = FastAPI()
    with pytest.raises(db.PoolBudgetError):
        async with main._lifespan(app):
            pytest.fail("the app started with a pool above the role limit")
    assert calls == ["verify"]
