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


# -- round 6: the check is in the class; nothing on the instance removes it (round-5 bypass 5 and its class) --------

ORDER = ROOT + "/orders/regular"


def test_b5_emptied_hooks_and_a_swapped_transport_still_refuse_with_zero_requests() -> None:
    seen: list[httpx.Request] = []
    swapped: list[httpx.Request] = []
    c = kite_http.kite_client(transport=_transport(seen))
    c.event_hooks = {}                          # round-5 bypass 5
    c._transport = _transport(swapped)          # and the wire swapped underneath
    with pytest.raises(kite_http.KiteCallRefused):
        c.post(ORDER, data={"x": "1"})
    with pytest.raises(kite_http.KiteCallRefused):
        c.request("POST", ORDER)
    with pytest.raises(kite_http.KiteCallRefused):
        with c.stream("POST", ORDER):
            pass
    c.close()
    assert seen == [] and swapped == []


@pytest.mark.asyncio
async def test_b5_async_emptied_hooks_and_swapped_transport_still_refuse() -> None:
    seen: list[httpx.Request] = []
    async with kite_http.kite_async_client(transport=_transport(seen)) as c:
        c.event_hooks = {}
        c._transport = _transport(seen)
        with pytest.raises(kite_http.KiteCallRefused):
            await c.post(ORDER)
        with pytest.raises(kite_http.KiteCallRefused):
            async with c.stream("POST", ORDER):
                pass
    assert seen == []


def test_a_request_hook_that_rewrites_the_url_after_send_is_caught_at_the_last_hop() -> None:
    seen: list[httpx.Request] = []

    def rewrite(request: httpx.Request) -> None:
        request.url = httpx.URL(ORDER)
        request.method = "POST"

    with kite_http.kite_client(transport=_transport(seen), event_hooks={"request": [rewrite]}) as c:
        with pytest.raises(kite_http.KiteCallRefused):
            c.get(ROOT + "/instruments")       # passes send(); the hook turns it into an order before the wire
    assert seen == []


@pytest.mark.asyncio
async def test_async_request_hook_that_rewrites_the_url_is_caught_at_the_last_hop() -> None:
    seen: list[httpx.Request] = []

    async def rewrite(request: httpx.Request) -> None:
        request.url = httpx.URL(ORDER)
        request.method = "POST"

    async with kite_http.kite_async_client(transport=_transport(seen), event_hooks={"request": [rewrite]}) as c:
        with pytest.raises(kite_http.KiteCallRefused):
            await c.get(ROOT + "/instruments")  # passes send(); the hook turns it into an order before the wire
    assert seen == []


def test_a_redirect_to_an_order_path_is_caught_at_the_last_hop() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(307, headers={"location": ORDER})

    with kite_http.kite_client(transport=httpx.MockTransport(handler), follow_redirects=True) as c:
        with pytest.raises(kite_http.KiteCallRefused):
            c.post(ROOT + "/session/token", data={"a": "b"})
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/session/token")]  # the redirect never left


@pytest.mark.parametrize("attr", ["send", "_send_single_request"])
def test_the_checking_methods_cannot_be_replaced_on_an_instance(attr: str) -> None:
    seen: list[httpx.Request] = []
    with kite_http.kite_client(transport=_transport(seen)) as c:
        with pytest.raises(AttributeError):
            setattr(c, attr, lambda *a, **k: None)
        with pytest.raises(AttributeError):
            object.__setattr__(c, attr, lambda *a, **k: None)
        vars(c)[attr] = lambda *a, **k: None    # forced into the instance namespace: never looked up
        assert kite_http.is_guarded(c)
        with pytest.raises(kite_http.KiteCallRefused):
            c.post(ORDER)
    assert seen == []


def test_a_swapped_class_is_no_longer_guarded() -> None:
    with kite_http.kite_client() as c:
        c.__class__ = httpx.Client
        assert not kite_http.is_guarded(c)


def test_is_guarded_accepts_only_untouched_door_clients() -> None:
    with kite_http.kite_client() as guarded, httpx.Client() as raw:
        assert kite_http.is_guarded(guarded) and not kite_http.is_guarded(raw)
        guarded.event_hooks = {"request": [], "response": []}
        assert kite_http.is_guarded(guarded)    # hooks are not the guard any more

    class Sub(kite_http.KiteClient):
        def send(self, request, **kwargs):      # a subclass without the check
            return httpx.Client.send(self, request, **kwargs)

    with Sub() as sub:
        assert not kite_http.is_guarded(sub)


def test_a_class_patched_after_import_is_no_longer_guarded(monkeypatch) -> None:
    with kite_http.kite_client() as c:
        monkeypatch.setattr(kite_http.KiteClient, "send", httpx.Client.send)
        assert not kite_http.is_guarded(c)


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


def test_the_login_exchange_refuses_a_client_that_did_not_come_from_the_door() -> None:
    with pytest.raises(TypeError):
        HttpKiteAuth("k", "s", httpx.AsyncClient())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_login_exchange_checks_the_client_on_every_call() -> None:
    seen: list[httpx.Request] = []
    async with kite_http.kite_async_client(transport=_transport(seen)) as client:
        auth = HttpKiteAuth("k", "s", client)
        client.__class__ = httpx.AsyncClient   # tampered after construction
        with pytest.raises(TypeError):
            await auth.exchange("rt")
    assert seen == []


@pytest.mark.asyncio
async def test_the_login_exchange_works_with_a_door_client() -> None:
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


@pytest.mark.parametrize("host", ["api.kite%2Etrade", "api%2ekite%2etrade", "user@api.kite.trade"])
def test_clients_refuse_percent_escaped_or_userinfo_hosts(host: str) -> None:
    seen: list[httpx.Request] = []
    with kite_http.kite_client(transport=_transport(seen)) as client:
        with pytest.raises(kite_http.KiteCallRefused):
            client.request("POST", f"https://{host}/orders/regular")
    assert seen == []
