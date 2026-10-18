"""#370: the API's database pool fits the CI role's connection limit (REQ-038 AC-5 list stays readable).

RCA: the e2e job runs three API processes as role ofo_app (CONNECTION LIMIT 5, ADR-048), each with SQLAlchemy's default
pool (5 + 10 overflow). Under two parallel Playwright workers the role ran out, GET /strategies answered 500 and
the saved list rendered empty (runs 39033719880, 39034787611: "too many connections for role ofo_app").
Class: any set of API processes on one limited role whose pools can add up to more than the limit.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from ofo_app import config, db

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "app-tests.yml"
ROLE_LIMIT = 5  # ADR-048
API_PROCESSES = 3
NO_PASSWORD_URL = "postgresql+asyncpg://example@localhost:5432/example"


@pytest.fixture
def fresh(monkeypatch):
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    monkeypatch.setenv("DATABASE_URL", NO_PASSWORD_URL)
    yield monkeypatch
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()


def test_pool_defaults_are_unchanged(fresh):
    """AC-5: with nothing set the engine keeps SQLAlchemy's own 5 + 10."""
    fresh.delenv("DB_POOL_SIZE", raising=False)
    fresh.delenv("DB_MAX_OVERFLOW", raising=False)
    pool = db.get_engine().pool
    assert (pool.size(), pool._max_overflow) == (5, 10)


def test_pool_follows_the_settings(fresh):
    """AC-5: DB_POOL_SIZE / DB_MAX_OVERFLOW reach the engine."""
    fresh.setenv("DB_POOL_SIZE", "1")
    fresh.setenv("DB_MAX_OVERFLOW", "0")
    pool = db.get_engine().pool
    assert (pool.size(), pool._max_overflow) == (1, 0)


def test_invalid_pool_size_is_refused(fresh):
    """AC-5: fail closed on a zero pool."""
    fresh.setenv("DB_POOL_SIZE", "0")
    with pytest.raises(ValueError):
        config.Settings()  # type: ignore[call-arg]


@pytest.mark.repo_scan
def test_e2e_api_processes_fit_the_role_limit():
    """AC-5: each e2e API start (ports 8000/8001/8002) declares a pool, and together they stay under the role limit."""
    steps = re.split(r"\n      - name: ", WORKFLOW.read_text(encoding="utf-8"))
    e2e = [s for s in steps if re.search(r"--port 800[012] >", s)]
    assert len(e2e) == API_PROCESSES
    total = 0
    for step in e2e:
        size = re.search(r"DB_POOL_SIZE: '?(\d+)'?", step)
        overflow = re.search(r"DB_MAX_OVERFLOW: '?(\d+)'?", step)
        assert size and overflow, step.splitlines()[0]
        total += int(size.group(1)) + int(overflow.group(1))
    assert total < ROLE_LIMIT
