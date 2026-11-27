"""Hotfix Lane R: every HTTP request writes ONE log line (method, route template, status, ms) from ofo_app.request."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app.db import get_db
from ofo_app.main import create_app
from ofo_app.request_log import RequestLog

HTTP_OK, HTTP_NOT_FOUND, HTTP_ERROR = 200, 404, 500


class _NoDb:
    async def execute(self, *_a: object, **_k: object) -> None:
        return None


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _db() -> AsyncIterator[_NoDb]:
        yield _NoDb()

    app.dependency_overrides[get_db] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "ofo_app.request"]


async def test_health_one_line(api: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ofo_app.request")
    r = await api.get("/health")
    assert r.status_code == HTTP_OK
    recs = _records(caplog)
    assert len(recs) == 1
    method, route, status, ms = recs[0].args
    assert (method, route, status) == ("GET", "/health", HTTP_OK)
    assert isinstance(ms, float) and ms >= 0
    assert recs[0].levelno == logging.INFO
    assert recs[0].getMessage().startswith("request GET /health 200 ")


async def test_path_param_logs_template_not_id(api: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ofo_app.request")
    await api.get("/paper/strategies/SECRET-ID-123?token=abc")
    recs = _records(caplog)
    assert len(recs) == 1
    assert recs[0].args[1] == "/paper/strategies/{strategy_id}"
    text = recs[0].getMessage()
    assert "SECRET-ID-123" not in text and "token" not in text


async def test_unmatched_404_strips_query(api: AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ofo_app.request")
    r = await api.get("/nope/zzz?token=abc")
    assert r.status_code == HTTP_NOT_FOUND
    recs = _records(caplog)
    assert len(recs) == 1
    assert recs[0].args[1:3] == ("/nope/zzz", HTTP_NOT_FOUND)
    assert "token" not in recs[0].getMessage()


async def test_escaping_exception_logs_500_and_reraises(caplog: pytest.LogCaptureFixture) -> None:
    async def boom(scope, receive, send):
        raise RuntimeError("x")

    caplog.set_level(logging.INFO, logger="ofo_app.request")
    scope = {"type": "http", "method": "GET", "path": "/x", "query_string": b"a=1"}
    with pytest.raises(RuntimeError):
        await RequestLog(boom)(scope, None, None)  # type: ignore[arg-type]
    recs = _records(caplog)
    assert len(recs) == 1 and recs[0].args[1:3] == ("/x", HTTP_ERROR)
