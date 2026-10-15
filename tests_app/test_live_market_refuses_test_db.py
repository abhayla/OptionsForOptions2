"""ADR-078 (finding live-work-shares-test-database): a live run never uses the test database.

ADR-078: "the test suites use only ofo_test, which nothing else writes to". The one config path every start passes
through refuses LIVE_MARKET when DATABASE_URL names ofo_test (or the database named by TEST_DATABASE_URL).
"""
from __future__ import annotations

import base64

import pytest

from ofo_app.config import Settings, database_name

BASE = "postgresql+asyncpg://example@127.0.0.1:5432/"


def _s(db: str, **kw):
    return Settings(DATABASE_URL=BASE + db, _env_file=None, **kw)


@pytest.fixture(autouse=True)
def _no_test_url(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)


def test_live_market_on_ofo_test_is_refused_naming_adr_and_dev_url():
    with pytest.raises(ValueError) as e:
        _s("ofo_test", LIVE_MARKET=True)
    assert "ADR-078" in str(e.value) and "DEV_DATABASE_URL" in str(e.value)


def test_live_market_refused_when_query_string_follows_the_name():
    with pytest.raises(ValueError, match="ADR-078"):
        _s("ofo_test?ssl=disable", LIVE_MARKET=True)


def test_live_market_on_ofo_dev_or_other_name_is_allowed():
    assert _s("ofo_dev", LIVE_MARKET=True).LIVE_MARKET is True
    assert _s("ofo_test2", LIVE_MARKET=True).LIVE_MARKET is True
    assert _s("x", LIVE_MARKET=True).LIVE_MARKET is True


def test_live_market_off_on_ofo_test_is_allowed():
    assert _s("ofo_test").LIVE_MARKET is False
    assert _s("ofo_test", APP_ENV="test").DATABASE_URL.endswith("/ofo_test")


def test_live_market_refused_on_the_database_named_by_test_database_url(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", BASE + "custom_test_db")
    with pytest.raises(ValueError, match="ADR-078"):
        _s("custom_test_db", LIVE_MARKET=True)
    assert _s("ofo_dev", LIVE_MARKET=True).LIVE_MARKET is True


def test_database_name_parsing():
    assert database_name(BASE + "ofo_test") == "ofo_test"
    assert database_name(BASE + "ofo_test?x=1") == "ofo_test"
    assert database_name("") is None
    assert database_name("postgresql://example:5432") is None


def _create_app(monkeypatch, url: str):
    from ofo_app import main

    monkeypatch.setenv("LIVE_MARKET", "1")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", url)
    for k, v in (("KITE_API_KEY", "k"), ("KITE_API_SECRET", "s"), ("KITE_REDIRECT_URL", "http://127.0.0.1:8000/kite/callback"),
                 ("KITE_EXPECTED_USER_ID", "ZZ0000"), ("BROKER_TOKEN_KEY", base64.urlsafe_b64encode(bytes(32)).decode())):
        monkeypatch.setenv(k, v)
    return main.create_app()


def test_create_app_raises_for_live_market_on_ofo_test(monkeypatch):
    with pytest.raises(ValueError, match="ADR-078"):
        _create_app(monkeypatch, BASE + "ofo_test")


def test_create_app_raises_for_live_market_with_an_unnamed_database(monkeypatch):
    with pytest.raises(ValueError, match="ADR-078"):
        _create_app(monkeypatch, BASE)


def test_create_app_builds_for_live_market_on_ofo_dev(monkeypatch):
    assert _create_app(monkeypatch, BASE + "ofo_dev") is not None


def test_empty_or_missing_name_refused_under_live_market():
    for url in ("postgresql+asyncpg://example@127.0.0.1:5432/", "postgresql+asyncpg://example@127.0.0.1:5432"):
        with pytest.raises(ValueError, match="ADR-078"):
            Settings(DATABASE_URL=url, LIVE_MARKET=True, _env_file=None)
    assert Settings(DATABASE_URL=BASE, _env_file=None).LIVE_MARKET is False
