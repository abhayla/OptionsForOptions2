"""W-024 round 9 part 6 fix round, review MAJOR-3 and MINOR: the boundary never logs a request value or a secret,
never re-raises to the server's logger, and keeps the protocol headers and statuses of HTTP errors.

Probes are the reviewer's (scratchpad probe/rt.py): a validation error on `access_token` with the value SECRETVAL,
and a RuntimeError carrying `access_token=SECRETTOKEN123`.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

SECRET_INPUT = "SECRETVAL"
SECRET_TOKEN = "SECRETTOKEN123"
KITE_TOKEN = "a1B2c3D4e5F6g7H8i9J0k1L2"  # 24-char token shape, no key name in front of it


class Login(BaseModel):
    api_key: str
    access_token: int


def _app():
    from ofo_app.main import create_app

    app = create_app()

    @app.post("/login")
    def login(b: Login) -> dict:
        return {"ok": True}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(f"kite failed access_token={SECRET_TOKEN} session {KITE_TOKEN}")

    @app.get("/h503")
    def h503() -> None:
        raise HTTPException(503, detail="Leg expired detail")

    @app.get("/h401")
    def h401() -> None:
        raise HTTPException(401, detail="x", headers={"WWW-Authenticate": "Bearer", "X-Leak": "Leg expired"})

    return app


async def _call(method: str, path: str, *, raise_app: bool = False, **kw):
    transport = ASGITransport(app=_app(), raise_app_exceptions=raise_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.request(method, path, **kw)


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(caplog.text.splitlines() + [r.getMessage() + (r.exc_text or "") for r in caplog.records])


async def test_validation_error_logs_loc_and_type_never_the_input(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    response = await _call("POST", "/login", json={"api_key": "K", "access_token": SECRET_INPUT})
    assert response.status_code == 422
    logged = _logged(caplog)
    assert "access_token" in logged and "int_parsing" in logged  # loc and type are kept
    assert SECRET_INPUT not in logged
    assert "Input should be" not in logged  # the `msg` text is not logged either


async def test_exception_log_redacts_keyed_and_token_shaped_secrets(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    response = await _call("GET", "/boom")
    assert response.status_code == 500
    logged = _logged(caplog)
    assert "RuntimeError" in logged and "kite failed" in logged  # the traceback is still useful
    assert SECRET_TOKEN not in logged and KITE_TOKEN not in logged
    assert "[REDACTED]" in logged


async def test_boundary_never_re_raises_to_the_server() -> None:
    """Starlette's outer middleware re-raises after its handler; the boundary middleware answers first."""
    response = await _call("GET", "/boom", raise_app=True)  # a re-raise would fail this call
    assert response.status_code == 500
    assert response.json()["error_class"] == "INTERNAL_SYSTEM"


async def test_405_keeps_allow_and_401_keeps_www_authenticate_only() -> None:
    r405 = await _call("PUT", "/boom")
    assert r405.status_code == 405 and r405.headers.get("allow") == "GET"
    r401 = await _call("GET", "/h401")
    assert r401.status_code == 401 and r401.headers.get("www-authenticate") == "Bearer"
    assert "x-leak" not in r401.headers
    assert r401.json()["error_class"] == "ENTITLEMENT_ACCESS"


async def test_503_stays_503() -> None:
    r = await _call("GET", "/h503")
    assert r.status_code == 503
    assert r.json()["code"] == "INTERNAL_SYSTEM_003"
    assert "Leg expired" not in r.text


def test_redact_unit_cases() -> None:
    from ofo_app.redaction import redact

    assert redact("access_token=abc password: 'hunter2' pin=1234") == \
        "access_token=[REDACTED] password: '[REDACTED]' pin=[REDACTED]"
    assert redact('{"api_secret": "s3cr3t", "otp": "999"}') == '{"api_secret": "[REDACTED]", "otp": "[REDACTED]"}'
    assert redact("checksum " + "0f" * 16) == "checksum [REDACTED]"
    assert redact("wrap_app_handling_exceptions in starlette") == "wrap_app_handling_exceptions in starlette"


async def test_mutant_without_the_filter_leaks(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: put the stock record factory back -> the token reaches the log (so the redaction test is
    load-bearing). Round 10: redaction is the log-record factory, no longer a filter on a list of logger names."""
    from ofo_app import errors

    monkeypatch.setattr(errors, "install_redaction", lambda: None)  # create_app() would re-install it
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    caplog.set_level(logging.INFO)
    await _call("GET", "/boom")
    assert SECRET_TOKEN in _logged(caplog)


async def test_mutant_logging_full_validation_errors_leaks(caplog: pytest.LogCaptureFixture,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: log `exc.errors()` whole -> SECRETVAL reaches the log (a key-based filter alone cannot catch it)."""
    from ofo_app import errors

    monkeypatch.setattr(errors, "_validation_problems", lambda exc: exc.errors())
    caplog.set_level(logging.INFO)
    await _call("POST", "/login", json={"api_key": "K", "access_token": SECRET_INPUT})
    assert SECRET_INPUT in _logged(caplog)
