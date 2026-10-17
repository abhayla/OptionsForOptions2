"""W-080 round 3 (REQ-073 AC-4): every httpx client the backend uses for Kite comes from ``ofo_app.kite_http`` and
refuses, BEFORE sending, any request that is not in ALLOWED_CALLS. httpx.MockTransport (the door's test seam, refused
outside the test suites): no network. Round 7: the check is at the last hop only; whatever skips it has no door
context, so the egress gate refuses its connect (tests_app/test_egress_gate_doors.py)."""
from __future__ import annotations

import httpx
import pytest
from ofo_app import kite_http
from ofo_app.kite_client import HttpKiteAuth

ROOT = "https://api.kite.trade"
ORDER = ROOT + "/orders/regular"


def _transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": {}})

    return httpx.MockTransport(handler)


def _client(seen: list[httpx.Request], **kwargs) -> kite_http.KiteClient:
    return kite_http.KiteClient(_test_transport=_transport(seen), **kwargs)


def _async_client(seen: list[httpx.Request], **kwargs) -> kite_http.KiteAsyncClient:
    return kite_http.KiteAsyncClient(_test_transport=_transport(seen), **kwargs)


REFUSED = [
    ("POST", ROOT + "/orders/regular"), ("PUT", ROOT + "/orders/regular/123"),
    ("DELETE", ROOT + "/orders/regular/123"), ("POST", ROOT + "/gtt/triggers"),
    ("PATCH", ROOT + "/orders/regular/123"), ("GET", ROOT + "/orders/123"),  # W-093: only exact GET /orders is allowed
]


@pytest.mark.parametrize("method,url", REFUSED)
def test_sync_client_refuses_before_sending(method: str, url: str) -> None:
    seen: list[httpx.Request] = []
    with _client(seen) as client, pytest.raises(kite_http.KiteCallRefused):
        client.request(method, url)
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("method,url", REFUSED)
async def test_async_client_refuses_before_sending(method: str, url: str) -> None:
    seen: list[httpx.Request] = []
    async with _async_client(seen) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            await client.request(method, url)
    assert seen == []


@pytest.mark.parametrize("path", ["orders/regular", "/orders/regular", "gtt/triggers"])
def test_base_url_client_refuses_relative_paths(path: str) -> None:
    seen: list[httpx.Request] = []
    with _client(seen, base_url=ROOT) as client, pytest.raises(kite_http.KiteCallRefused):
        client.post(path)
    assert seen == []


@pytest.mark.asyncio
async def test_async_base_url_client_refuses_relative_path() -> None:
    seen: list[httpx.Request] = []
    async with _async_client(seen, base_url=ROOT) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            await client.post("orders/regular")
    assert seen == []


def test_allowed_calls_pass_and_are_sent() -> None:
    seen: list[httpx.Request] = []
    with _client(seen, base_url=ROOT) as client:
        assert client.get("instruments").status_code == 200  # noqa: PLR2004
        assert client.post("/session/token", data={"a": "b"}).status_code == 200  # noqa: PLR2004
        assert client.get("/instruments/historical/9/minute", params={"from": "x"}).status_code == 200  # noqa: PLR2004
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/instruments"), ("POST", "/session/token"), ("GET", "/instruments/historical/9/minute")]


def test_a_swapped_transport_and_every_entry_point_still_refuse_with_zero_requests() -> None:
    seen: list[httpx.Request] = []
    swapped: list[httpx.Request] = []
    c = _client(seen)
    c._transport = _transport(swapped)  # the wire swapped underneath: the last hop still checks first
    with pytest.raises(kite_http.KiteCallRefused):
        c.post(ORDER, data={"x": "1"})
    with pytest.raises(kite_http.KiteCallRefused):
        c.request("POST", ORDER)
    with pytest.raises(TypeError):  # W-080 r9: stream / send / build_request are closed (plain data only)
        c.stream("POST", ORDER)
    with pytest.raises(kite_http.KiteCallRefused):  # the unbound httpx send still meets the last hop
        httpx.Client.send(c, httpx.Request("POST", ORDER))
    c.close()
    assert seen == [] and swapped == []


@pytest.mark.asyncio
async def test_async_entry_points_still_refuse() -> None:
    seen: list[httpx.Request] = []
    async with _async_client(seen) as c:
        with pytest.raises(kite_http.KiteCallRefused):
            await c.post(ORDER)
        with pytest.raises(TypeError):  # W-080 r9: stream is closed
            c.stream("POST", ORDER)
        with pytest.raises(kite_http.KiteCallRefused):
            await httpx.AsyncClient.send(c, httpx.Request("POST", ORDER))
    assert seen == []


def test_a_redirect_to_an_order_path_is_caught_at_the_last_hop() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(307, headers={"location": ORDER})

    client = kite_http.KiteClient(_test_transport=httpx.MockTransport(handler))
    with client as c, pytest.raises(kite_http.KiteCallRefused):
        # the door's own API never follows a redirect (W-080 r9); the unbound httpx send with follow_redirects meets the
        # last-hop check on every hop
        httpx.Client.send(c, httpx.Request("POST", ROOT + "/session/token", data={"a": "b"}), follow_redirects=True)
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/session/token")]  # the redirect never left


def test_httpx_still_sends_through_the_last_hop_method() -> None:
    """The last-hop check relies on httpx calling ``_send_single_request``; if a new httpx stops, this fails."""
    assert "_send_single_request" in vars(httpx.Client) and "_send_single_request" in vars(httpx.AsyncClient)
    calls: list[str] = []

    class Probe(httpx.Client):
        def _send_single_request(self, request):
            calls.append(str(request.url))
            return super()._send_single_request(request)

    with Probe(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as p:
        p.get("https://example.com/x")
    assert calls == ["https://example.com/x"]


@pytest.mark.asyncio
async def test_the_login_exchange_works_with_a_door_client() -> None:
    seen: list[httpx.Request] = []
    async with _async_client(seen) as client:
        auth = HttpKiteAuth("k", "s", client)
        with pytest.raises(Exception):  # the mock answer has no access_token: the exchange fails, but it was SENT  # noqa: B017
            await auth.exchange("rt")
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/session/token")]


def test_clients_refuse_non_ascii_host_before_sending() -> None:
    # U+3002 ideographic full stop: other layers fold it to "." and would reach api.kite.trade
    url = "https://api。kite。trade/orders/regular"
    seen: list[httpx.Request] = []
    with _client(seen) as client, pytest.raises((kite_http.KiteCallRefused, httpx.InvalidURL)):
        client.request("POST", url)
    assert seen == []


@pytest.mark.parametrize("host", ["api.kite%2Etrade", "api%2ekite%2etrade", "user@api.kite.trade"])
def test_clients_refuse_percent_escaped_or_userinfo_hosts(host: str) -> None:
    seen: list[httpx.Request] = []
    with _client(seen) as client, pytest.raises(kite_http.KiteCallRefused):
        client.request("POST", f"https://{host}/orders/regular")
    assert seen == []
