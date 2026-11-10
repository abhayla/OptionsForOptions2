"""GC-ICSAFE (ADR-286, REQ-115 AC-6): the Notifier client, proven against a FAKE transport only.

The real send to the shared Notifier is NOT proven here: this app is not registered with it yet.
"""
from __future__ import annotations

import json
import logging
import urllib.error

import pytest

from ofo_app import notifier

KEY = "k-secret-0123456789"
URL = "https://notifier.example.test:8443"


def _env(monkeypatch, url=URL, project="ofo", key=KEY) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u@127.0.0.1:5432/placeholder")  # Settings needs one; no connect
    for name, value in (("NOTIFIER_URL", url), ("NOTIFIER_PROJECT", project), ("NOTIFIER_KEY", key)):
        monkeypatch.setenv(name, value)
    notifier.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_settings():
    yield
    notifier.get_settings.cache_clear()


class Fake:
    def __init__(self, status=200, error=None):
        self.status, self.error, self.calls = status, error, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if self.error is not None:
            raise self.error
        return self.status


async def _send(fake):
    return await notifier.notify("critical", "T", "B", type="worker-stopped", dedupe_key="worker-stopped-2026-11-10",
                                 transport=fake)


async def test_sent_one_post_with_key_header_and_the_six_body_keys(monkeypatch):
    _env(monkeypatch)
    fake = Fake(200)
    assert await _send(fake) == notifier.SENT
    [(method, url, headers, body, timeout)] = fake.calls
    assert (method, url, timeout) == ("POST", URL + "/notify", 5)
    assert headers["X-Api-Key"] == KEY
    assert json.loads(body) == {"project": "ofo", "severity": "critical", "title": "T", "body": "B",
                                "type": "worker-stopped", "dedupeKey": "worker-stopped-2026-11-10"}


@pytest.mark.parametrize("name", ["NOTIFIER_URL", "NOTIFIER_PROJECT", "NOTIFIER_KEY"])
async def test_any_empty_setting_sends_nothing(monkeypatch, name):
    _env(monkeypatch)
    monkeypatch.setenv(name, "")
    notifier.get_settings.cache_clear()
    fake = Fake()
    assert await _send(fake) == notifier.NOT_CONFIGURED
    assert fake.calls == []


@pytest.mark.parametrize("status, state", [(401, notifier.REFUSED), (400, notifier.REFUSED),
                                           (500, notifier.SERVER_ERROR), (503, notifier.SERVER_ERROR)])
async def test_error_statuses_are_named(monkeypatch, status, state):
    _env(monkeypatch)
    assert await _send(Fake(status)) == state


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionRefusedError(), urllib.error.URLError("x"),
                                   RuntimeError("anything")])
async def test_timeout_and_connection_errors_never_raise(monkeypatch, error):
    _env(monkeypatch)
    assert await _send(Fake(error=error)) == notifier.UNREACHABLE


@pytest.mark.parametrize("url", ["http://notifier.example.test", "ftp://x", "notifier.example.test",
                                 "http://10.0.0.5:3300"])
async def test_a_url_that_is_neither_https_nor_loopback_is_refused_at_build(monkeypatch, url):
    _env(monkeypatch, url=url)
    fake = Fake()
    assert await _send(fake) == notifier.BAD_URL
    assert fake.calls == []


@pytest.mark.parametrize("url", ["http://127.0.0.1:3300", "http://localhost:3300", "http://[::1]:3300"])
async def test_loopback_http_is_allowed(monkeypatch, url):
    _env(monkeypatch, url=url)
    fake = Fake()
    assert await _send(fake) == notifier.SENT
    assert fake.calls[0][1] == url + "/notify"


async def test_the_log_names_state_and_exception_type_never_the_key(monkeypatch, caplog):
    _env(monkeypatch)
    caplog.set_level(logging.DEBUG)
    await _send(Fake(error=RuntimeError(f"boom {KEY}")))
    await _send(Fake(401))
    await _send(Fake(500))
    assert "RuntimeError" in caplog.text and "refused" in caplog.text
    assert KEY not in caplog.text
