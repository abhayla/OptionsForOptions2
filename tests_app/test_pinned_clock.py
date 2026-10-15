"""#237: the TEST-ONLY catalogue date pin (TEST_CATALOGUE_DATE) and the CI seed of the recorded fixture.

Spec basis: ADR-023 (the trusted database clock judges expiry everywhere outside APP_ENV=test); ADR-058/059 (the guarded
catalogue update, which the seed uses unchanged); REQ-035 AC-8 (the picker offers only live, not-expired contracts).
Expected counts come from reading the fixture CSV directly with the csv module, not from the code under test.
Every database test rolls back, so public.catalogue_contracts stays empty.
"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ofo_app import pinned_clock, seed_test_catalogue
from ofo_app.catalogue_picker import database_today
from ofo_app.config import Settings
from ofo_app.main import create_app
from ofo_app.pinned_clock import PinRefused

DB = "postgresql+asyncpg://example@127.0.0.1:5432/x"
PIN = datetime.date(2026, 10, 8)
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
SETTINGS = Settings(DATABASE_URL=DB, _env_file=None)
OUTSIDE_TEST = ["production", "development", "staging", "Test", ""]


def _fixture_counts(name: str) -> dict[str, int]:
    """Option/future rows per expiry for ``name`` in the fixture, counted by hand from the CSV."""
    counts: dict[str, int] = {}
    with FIXTURE.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["name"] == name and r["expiry"]:
                counts[r["expiry"]] = counts.get(r["expiry"], 0) + 1
    return counts


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(pinned_clock.ENV_NAME, PIN.isoformat())


# ---- the guards: each one has a test that goes red without it --------------------------------------------------------


@pytest.mark.parametrize("env", OUTSIDE_TEST)
def test_settings_refuse_the_pin_outside_test(env):
    """Kills: the validator line in config.Settings."""
    with pytest.raises(ValueError, match="test-only"):
        Settings(DATABASE_URL=DB, APP_ENV=env, TEST_CATALOGUE_DATE="2026-10-08", _env_file=None)


def test_settings_default_has_no_pin_and_test_env_accepts_it():
    assert Settings(DATABASE_URL=DB, _env_file=None).TEST_CATALOGUE_DATE is None
    assert Settings(DATABASE_URL=DB, APP_ENV="test", TEST_CATALOGUE_DATE="2026-10-08",
                    _env_file=None).TEST_CATALOGUE_DATE == "2026-10-08"


@pytest.mark.parametrize("env", ["production", "development", ""])
def test_create_app_refuses_the_pin_outside_test(monkeypatch, env):
    """Kills: the start-up guard in main.create_app (the app must not start)."""
    monkeypatch.setenv(pinned_clock.ENV_NAME, "2026-10-08")
    monkeypatch.setenv("APP_ENV", env)
    with pytest.raises(PinRefused, match="test-only"):
        create_app()


def test_create_app_refuses_an_unnamed_environment(monkeypatch):
    """APP_ENV unset (not even 'development') is refused too: the allow-list is exactly 'test'."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(pinned_clock.ENV_NAME, "2026-10-08")
    monkeypatch.setattr("ofo_app.main.app_env", lambda: None)
    with pytest.raises(PinRefused):
        create_app()


@pytest.mark.parametrize("env", ["production", "development", ""])
async def test_the_seam_refuses_to_answer_outside_test(monkeypatch, env):
    """Kills: the require_test_env call inside pinned_today (the seam itself never trusts the start-up check)."""
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv(pinned_clock.ENV_NAME, "2026-10-08")
    with pytest.raises(PinRefused):
        await database_today(None)


@pytest.mark.parametrize("bad", ["2026-13-01", "tomorrow", "08/10/2026", "2026-10-08T00:00:00", "20261008x"])
def test_a_malformed_pin_is_refused(monkeypatch, bad):
    """Kills: strict parse in pin_requested/parse_pin (a bad value never silently means 'no pin')."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(pinned_clock.ENV_NAME, bad)
    with pytest.raises(PinRefused, match="YYYY-MM-DD"):
        create_app()


# ---- behaviour -------------------------------------------------------------------------------------------------------


async def test_with_the_pin_the_date_is_the_pin_and_no_database_is_read(pinned):
    assert await database_today(None) == PIN  # None as the connection: the pin never touches the database


async def test_without_the_pin_the_date_is_the_database_clock(app_engine: AsyncEngine, monkeypatch):
    """Behaviour unchanged when the variable is absent."""
    monkeypatch.delenv(pinned_clock.ENV_NAME, raising=False)
    async with app_engine.connect() as conn:
        expected = (await conn.execute(text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date"))).scalar_one()
        assert await database_today(conn) == expected


async def _client(session: AsyncSession) -> AsyncClient:
    from ofo_app.db import get_db

    app = create_app()  # NO get_today override: the real seam decides "today"

    async def db():
        yield session

    app.dependency_overrides[get_db] = db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_seed_then_routes_offer_the_fixture_only_under_the_pin(app_engine: AsyncEngine, pinned, monkeypatch):
    """Core: the fixture, seeded through the normal loader, is pickable with the pin and NOT pickable without it."""
    expected = _fixture_counts("NIFTY")
    assert set(expected) == {"2026-10-13", "2026-10-19"}  # read from the CSV, not from the code under test
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert (await conn.execute(text("SELECT count(*) FROM public.catalogue_contracts"))).scalar_one() == 0
            assert await seed_test_catalogue.seed(conn, SETTINGS, "test") == 0
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                async with await _client(session) as ac:
                    got = (await ac.get("/api/catalogue/NIFTY/expiries")).json()
                    assert got == {"underlying": "NIFTY", "expiries": ["2026-10-13", "2026-10-19"]}
                    for expiry, n in expected.items():
                        body = (await ac.get("/api/catalogue/NIFTY/contracts", params={"expiry": expiry})).json()
                        assert len(body["contracts"]) == n
                    sensex = (await ac.get("/api/catalogue/SENSEX/expiries")).json()["expiries"]
                    assert sensex == ["2026-10-08", "2026-10-15"]
                    # the same database, pin removed: expiry is judged on the database clock again
                    monkeypatch.delenv(pinned_clock.ENV_NAME)
                    async with await _client(session) as plain:
                        real_today = await database_today(conn)
                        assert real_today > PIN
                        # no pin: ONLY expiries on or after the database's own today (counted from the CSV)
                        assert (await plain.get("/api/catalogue/NIFTY/expiries")).json()["expiries"] == sorted(
                            e for e in expected if e >= real_today.isoformat())
                        # the recording day itself is past on any real clock, so it is never offered unpinned
                        assert "2026-10-08" not in (await plain.get("/api/catalogue/SENSEX/expiries")).json()["expiries"]
        finally:
            await trans.rollback()


async def test_a_fixture_contract_picked_under_the_pin_can_be_saved(app_engine: AsyncEngine, pinned):
    """The save path reads the stored retired/delisted flags, not a clock: the seeded contract builds and saves."""
    from ofo.strategy import stored_form as sf
    from ofo_app import strategy_store
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await seed_test_catalogue.seed(conn, SETTINGS, "test")
            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                async with await _client(session) as ac:
                    rows = (await ac.get("/api/catalogue/NIFTY/contracts", params={"expiry": "2026-10-13"})).json()
                    pick = next(c for c in rows["contracts"] if c["instrument_type"] == "CE")
            choice = sf.LegChoice(contract_id=pick["contract_id"], action=sf.Action.SELL, quantity=pick["lot_size"])
            saved = await strategy_store.build_definition(conn, "NIFTY", [choice], rules_ref="t237")
            stored = await strategy_store.save_draft(conn, "u237", saved)
            assert stored.id > 0
        finally:
            await trans.rollback()


# ---- the seed's own guards ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("env", OUTSIDE_TEST)
def test_seed_refused_outside_test(monkeypatch, env):
    """Kills: require_test_env in seed_as_of."""
    monkeypatch.setenv("APP_ENV", "test")  # the process says test, so only the caller's stated environment can refuse
    monkeypatch.setenv(pinned_clock.ENV_NAME, "2026-10-08")
    with pytest.raises(PinRefused):
        seed_test_catalogue.seed_as_of(env)


def test_seed_refused_without_a_pin(monkeypatch):
    """Kills: the 'pin must be set' check in seed_as_of."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv(pinned_clock.ENV_NAME, raising=False)
    with pytest.raises(seed_test_catalogue.SeedRefused, match="must be set"):
        seed_test_catalogue.seed_as_of("test")


def test_seed_as_of_is_ten_am_ist_on_the_pinned_day(pinned):
    got = seed_test_catalogue.seed_as_of("test")
    assert got.isoformat() == "2026-10-08T10:00:00+05:30"


async def test_seed_refused_on_a_catalogue_that_already_holds_rows(app_engine: AsyncEngine, pinned):
    """Kills: the non-empty refusal in seed (never seed the shared database after other runs)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert await seed_test_catalogue.seed(conn, SETTINGS, "test") == 0
            with pytest.raises(seed_test_catalogue.SeedRefused, match="already holds"):
                await seed_test_catalogue.seed(conn, SETTINGS, "test")
        finally:
            await trans.rollback()
