"""AC-3 (W-077; REQ-039 AC-3, ADR-088): an answer in each non-normal Builder state carries the moment the server produced
it. The four states: not connected and refused (the outcome route's own answers: `answered_at`), unpriced (the
planned-entry answer the leg came from: `answered_at`) and error (the server's HTTP `Date` header, set by the real server
on every answer, error bodies included). The clock is injected: no assertion reads the wall clock. No database is needed."""
from __future__ import annotations

import asyncio
import datetime
import email.utils
import pathlib
import sys

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.marketdata.kite_provider import IST  # noqa: E402

ANSWER = datetime.datetime(2026, 10, 16, 3, 50, 5, tzinfo=datetime.timezone.utc)  # 09:20:05 IST
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
LEG = "NSE_FO:44624"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _outcome_body(provider, fallback=False):
    price = f"{provider.book.get(LEG, VALUATION).ltp:f}"
    return {"underlying": "NIFTY", "fallback": fallback,
            "legs": [{"instrument_id": LEG, "action": "SELL", "lots": 1, "planned_entry": price,
                      "captured_at": VALUATION.isoformat()}]}


def _app(provider=None):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context

    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: ANSWER)
    if provider is not None:
        app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, __import__(
            "decimal").Decimal("0.065"))
    return app


async def _post(app, path, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(path, json=body)


def _is_time(value, expected) -> bool:
    parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and parsed == expected


def _is_answer_time(value) -> bool:
    return _is_time(value, ANSWER)


async def test_not_connected_answer_carries_the_server_time(replayed):
    """AC-3: not connected (no provider)."""
    out = (await _post(_app(), "/api/strategies/outcome", _outcome_body(replayed))).json()
    assert out["state"] == "NOT_CONNECTED"
    assert _is_answer_time(out["answered_at"])


async def test_refused_answer_carries_the_server_time(replayed):
    """AC-3: refused (a leg the market does not know). With a provider the answer time is the context clock's reading
    (the one the snapshot was read at), so a live push and the REST answer of one snapshot stay equal."""
    body = _outcome_body(replayed)
    body["legs"][0]["instrument_id"] = "NSE_FO:99999999"
    out = (await _post(_app(replayed), "/api/strategies/outcome", body)).json()
    assert out["state"] == "REFUSED"
    assert _is_time(out["answered_at"], VALUATION)


async def test_computed_answer_carries_the_server_time(replayed):
    """AC-3: every outcome answer carries the one field (the stale state keeps its own text)."""
    out = (await _post(_app(replayed), "/api/strategies/outcome", _outcome_body(replayed))).json()
    assert out["state"] == "COMPUTED"
    assert _is_time(out["answered_at"], VALUATION)


async def test_unpriced_answer_carries_the_server_time():
    """AC-3: unpriced (the planned-entry answer that gave the leg no price)."""
    body = {"underlying": "NIFTY", "instrument_ids": [LEG]}
    out = (await _post(_app(), "/api/strategies/planned-entry", body)).json()
    assert out["entries"][0]["planned_entry"] is None
    assert _is_answer_time(out["answered_at"])


async def test_error_answer_carries_the_server_date_header():
    """AC-3: error. Real uvicorn, a request the route refuses (422): the server's own `Date` header is on the answer."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(_app(), host="127.0.0.1", port=0, log_config=None, lifespan="off"))
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.02)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]
        async with httpx.AsyncClient() as ac:
            res = await ac.post(f"http://127.0.0.1:{port}/api/strategies/outcome", json={"underlying": "NIFTY"})
        assert res.status_code == 422
        stamped = email.utils.parsedate_to_datetime(res.headers["date"])
        assert stamped.tzinfo is not None
    finally:
        server.should_exit = True
        await task
