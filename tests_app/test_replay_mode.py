"""W-064 step 1: the outcome route's replay mode exists only under APP_ENV=test; production settings refuse it."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ofo_app.config import Settings
from ofo_app.main import create_app
from ofo_app.replay_mode import ReplayRefused

DB = "postgresql+asyncpg://example@127.0.0.1:5432/x"
BODY = {"underlying": "NIFTY", "legs": [
    {"instrument_id": "NSE_FO:44624", "action": "SELL", "lots": 1, "planned_entry": "100.00",
     "captured_at": "2026-10-08T09:20:09+05:30"}]}


@pytest.mark.parametrize("env", ["production", "development", "staging", "Test", ""])
def test_settings_refuse_replay_outside_test(env):
    with pytest.raises(ValueError, match="test-only"):
        Settings(DATABASE_URL=DB, APP_ENV=env, OUTCOME_REPLAY=True, _env_file=None)


def test_settings_default_has_no_replay_and_test_env_accepts_it():
    assert Settings(DATABASE_URL=DB, _env_file=None).OUTCOME_REPLAY is False
    assert Settings(DATABASE_URL=DB, APP_ENV="test", OUTCOME_REPLAY=True, _env_file=None).OUTCOME_REPLAY is True


@pytest.mark.parametrize("env", ["production", "development"])
def test_create_app_refuses_replay_outside_test(monkeypatch, env):
    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    monkeypatch.setenv("APP_ENV", env)
    with pytest.raises(ReplayRefused):
        create_app()


async def test_replay_in_test_env_serves_the_recorded_numbers(monkeypatch):
    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    monkeypatch.setenv("APP_ENV", "test")
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        out = (await ac.post("/api/strategies/outcome", json=BODY)).json()
    assert out["state"] == "COMPUTED" and out["spot_level"] == "22533.25"


async def test_no_replay_env_means_not_connected(monkeypatch):
    monkeypatch.delenv("OUTCOME_REPLAY", raising=False)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        assert (await ac.post("/api/strategies/outcome", json=BODY)).json()["state"] == "NOT_CONNECTED"
