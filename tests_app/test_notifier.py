"""GC-ICSAFE (ADR-286, REQ-115 AC-6): the Notifier client, proven against a FAKE transport, and its real urllib sender
against a loopback HTTP server started inside the test (the outbound guard allows loopback).

The real send to the shared Notifier is NOT proven here: this app is not registered with it yet.
"""
from __future__ import annotations

import http.server
import json
import logging
import socket
import threading
import urllib.error

import pytest
from ofo_app import notifier

KEY = "k-secret-0123456789"
URL = "https://notifier.example.test:8443"


def _env(monkeypatch, url=URL, project="ofo", key=KEY) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u@127.0.0.1:5432/x")  # Settings needs one; no connect
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


async def _send(fake=None):
    kwargs = {} if fake is None else {"transport": fake}
    return await notifier.notify("critical", "T", "B", type="worker-stopped", dedupe_key="worker-stopped-2026-11-10-1",
                                 **kwargs)


async def test_sent_one_post_with_key_header_and_the_six_body_keys(monkeypatch):
    _env(monkeypatch)
    fake = Fake(200)
    assert await _send(fake) == notifier.SENT
    [(method, url, headers, body, timeout)] = fake.calls
    assert (method, url, timeout) == ("POST", URL + "/notify", 5)
    assert headers["X-Api-Key"] == KEY
    assert json.loads(body) == {"project": "ofo", "severity": "critical", "title": "T", "body": "B",
                                "type": "worker-stopped", "dedupeKey": "worker-stopped-2026-11-10-1"}


@pytest.mark.parametrize("name", ["NOTIFIER_URL", "NOTIFIER_PROJECT", "NOTIFIER_KEY"])
async def test_any_empty_setting_sends_nothing_and_the_log_names_which(monkeypatch, name, caplog):
    _env(monkeypatch)
    monkeypatch.setenv(name, "")
    notifier.get_settings.cache_clear()
    caplog.set_level(logging.WARNING)
    fake = Fake()
    assert await _send(fake) == notifier.NOT_CONFIGURED
    assert fake.calls == []
    assert f"alert not sent: not configured (empty: {name})" in caplog.text
    assert KEY not in caplog.text


@pytest.mark.parametrize("status, state", [(401, notifier.REFUSED), (400, notifier.REFUSED),
                                           (302, notifier.REFUSED), (500, notifier.SERVER_ERROR),
                                           (503, notifier.SERVER_ERROR)])
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
async def test_a_url_that_is_neither_https_nor_loopback_is_refused_at_build(monkeypatch, url, caplog):
    _env(monkeypatch, url=url)
    caplog.set_level(logging.WARNING)
    fake = Fake()
    assert await _send(fake) == notifier.BAD_URL
    assert fake.calls == []
    assert "alert not sent: bad url" in caplog.text


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


def test_the_key_is_a_secret_in_the_settings_text(monkeypatch):
    _env(monkeypatch)
    cfg = notifier.get_settings()
    assert KEY not in repr(cfg) and KEY not in str(cfg)
    assert cfg.NOTIFIER_KEY.get_secret_value() == KEY


def _guard_holds(monkeypatch, settings_url, env_url) -> None:
    """The settings hold ``settings_url`` (read once); the process environment the guard read holds ``env_url``."""
    _env(monkeypatch, url=settings_url)
    notifier.get_settings()
    monkeypatch.setenv("NOTIFIER_URL", env_url)


def test_a_https_address_the_guard_does_not_hold_is_named_once_at_start(monkeypatch, caplog):
    _guard_holds(monkeypatch, URL, "")
    caplog.set_level(logging.WARNING)
    notifier.warn_if_guard_mismatch()
    assert caplog.text.count("NOTIFIER_URL is set in the settings but not in the process environment") == 1
    assert URL not in caplog.text


@pytest.mark.parametrize("settings_url, env_url", [(URL, URL), ("", ""), ("http://127.0.0.1:3300", "")])
def test_no_mismatch_line_when_the_guard_holds_it_nothing_is_set_or_it_is_loopback(monkeypatch, caplog, settings_url,
                                                                                     env_url):
    _guard_holds(monkeypatch, settings_url, env_url)
    caplog.set_level(logging.WARNING)
    notifier.warn_if_guard_mismatch()
    assert caplog.text == ""


class _Server:
    """A loopback HTTP server: ``mode`` picks the answer to POST /notify; ``paths`` lists every request it saw."""

    def __init__(self) -> None:
        self.mode, self.paths, self.keys = 200, [], []
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - the stdlib's name
                owner.paths.append(self.path)
                owner.keys.append(self.headers.get("X-Api-Key"))
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path == "/notify" and owner.mode == 302:  # noqa: PLR2004
                    self.send_response(302)
                    self.send_header("Location", "/elsewhere")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(owner.mode if self.path == "/notify" else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST  # noqa: N815 - a followed redirect would arrive as a GET

            def log_message(self, *_args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    srv = _Server()
    yield srv
    srv.close()


@pytest.mark.parametrize("mode, state", [(200, notifier.SENT), (500, notifier.SERVER_ERROR)])
async def test_the_real_sender_answers_200_and_500(monkeypatch, server, mode, state):
    server.mode = mode
    _env(monkeypatch, url=server.url)
    assert await _send() == state
    assert server.paths == ["/notify"] and server.keys == [KEY]


async def test_the_real_sender_never_follows_a_redirect_and_the_key_goes_nowhere_else(monkeypatch, server):
    server.mode = 302
    _env(monkeypatch, url=server.url)
    assert await _send() == notifier.REFUSED
    assert server.paths == ["/notify"]  # /elsewhere was never requested
    assert server.keys == [KEY]


async def test_the_real_sender_on_a_closed_port_is_unreachable(monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    _env(monkeypatch, url=f"http://127.0.0.1:{port}")
    assert await _send() == notifier.UNREACHABLE
