"""W-080 round 3 (REQ-073 AC-4): every httpx client the backend uses for Kite comes from ``ofo_app.kite_http`` and
refuses, BEFORE sending, any request that is not in ALLOWED_CALLS. httpx.MockTransport: no network."""
from __future__ import annotations

import httpx
import pytest

from ofo_app import kite_http
from ofo_app.kite_client import HttpKiteAuth

ROOT = "https://api.kite.trade"


def _transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": {}})

    return httpx.MockTransport(handler)


REFUSED = [
    ("POST", ROOT + "/orders/regular"), ("PUT", ROOT + "/orders/regular/123"),
    ("DELETE", ROOT + "/orders/regular/123"), ("POST", ROOT + "/gtt/triggers"),
    ("PATCH", ROOT + "/orders/regular/123"), ("GET", ROOT + "/orders"),
]


@pytest.mark.parametrize("method,url", REFUSED)
def test_sync_client_refuses_before_sending(method: str, url: str) -> None:
    seen: list[httpx.Request] = []
    with kite_http.kite_client(transport=_transport(seen)) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            client.request(method, url)
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method,url", REFUSED)
async def test_async_client_refuses_before_sending(method: str, url: str) -> None:
    seen: list[httpx.Request] = []
    async with kite_http.kite_async_client(transport=_transport(seen)) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            await client.request(method, url)
    assert seen == []


@pytest.mark.parametrize("path", ["orders/regular", "/orders/regular", "gtt/triggers"])
def test_base_url_client_refuses_relative_paths(path: str) -> None:
    seen: list[httpx.Request] = []
    with kite_http.kite_client(base_url=ROOT, transport=_transport(seen)) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            client.post(path)
    assert seen == []


@pytest.mark.asyncio
async def test_async_base_url_client_refuses_relative_path() -> None:
    seen: list[httpx.Request] = []
    async with kite_http.kite_async_client(base_url=ROOT, transport=_transport(seen)) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            await client.post("orders/regular")
    assert seen == []


def test_allowed_calls_pass_and_are_sent() -> None:
    seen: list[httpx.Request] = []
    with kite_http.kite_client(base_url=ROOT, transport=_transport(seen)) as client:
        assert client.get("instruments").status_code == 200
        assert client.post("/session/token", data={"a": "b"}).status_code == 200
        assert client.get("/instruments/historical/9/minute", params={"from": "x"}).status_code == 200
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/instruments"), ("POST", "/session/token"), ("GET", "/instruments/historical/9/minute")]


def test_the_guard_cannot_be_replaced_by_the_caller() -> None:
    with pytest.raises(TypeError):
        kite_http.kite_client(event_hooks={"request": []})
    with pytest.raises(TypeError):
        kite_http.kite_async_client(event_hooks={"request": []})


def test_client_hooks_are_not_removable_through_the_factory_client_marker() -> None:
    with kite_http.kite_client() as guarded, httpx.Client() as raw:
        assert kite_http.is_guarded(guarded) and not kite_http.is_guarded(raw)
        guarded.event_hooks = {"request": [], "response": []}
        assert not kite_http.is_guarded(guarded)  # a stripped client is no longer accepted


def test_the_login_exchange_refuses_a_client_that_did_not_come_from_the_factory() -> None:
    with pytest.raises(TypeError):
        HttpKiteAuth("k", "s", httpx.AsyncClient())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_login_exchange_works_with_a_factory_client() -> None:
    seen: list[httpx.Request] = []
    async with kite_http.kite_async_client(transport=_transport(seen)) as client:
        auth = HttpKiteAuth("k", "s", client)
        with pytest.raises(Exception):  # the mock answer has no access_token: the exchange fails, but it was SENT
            await auth.exchange("rt")
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/session/token")]


def test_clients_refuse_non_ascii_host_before_sending() -> None:
    # U+3002 ideographic full stop: other layers fold it to "." and would reach api.kite.trade
    url = "https://api\u3002kite\u3002trade/orders/regular"
    seen: list[httpx.Request] = []
    with kite_http.kite_client(transport=_transport(seen)) as client:
        with pytest.raises((kite_http.KiteCallRefused, httpx.InvalidURL)):
            client.request("POST", url)
    assert seen == []
