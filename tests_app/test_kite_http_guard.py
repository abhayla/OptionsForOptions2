"""W-080 round 3 (REQ-073 AC-4): every httpx client the backend uses for Kite comes from ``ofo_app.kite_http`` and
refuses, BEFORE sending, any request that is not in ALLOWED_CALLS. httpx.MockTransport (the door's test seam, refused
outside the test suites): no network. Round 7: the check is at the last hop only; whatever skips it has no door
context, so the egress gate refuses its connect (tests_app/test_egress_gate_doors.py)."""
from __future__ import annotations

import httpx
import pytest
from ofo.broker.kite_endpoints import (
    CALLER_DOWNLOADER,
    CALLER_KITE_CLIENT,
    CALLER_KITE_HISTORY,
    CALLER_KITE_MARGIN,
    CALLER_KITE_READS,
)
from ofo_app import kite_http
from ofo_app.kite_client import HttpKiteAuth

ROOT = "https://api.kite.trade"
ORDER = ROOT + "/orders/regular"


def _transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "success", "data": {}})

    return httpx.MockTransport(handler)


def _client(seen: list[httpx.Request], caller: str = CALLER_KITE_READS, **kwargs) -> kite_http.KiteClient:
    return kite_http.KiteClient(caller=caller, _test_transport=_transport(seen), **kwargs)


def _async_client(seen: list[httpx.Request], caller: str = CALLER_KITE_READS,
                  **kwargs) -> kite_http.KiteAsyncClient:
    return kite_http.KiteAsyncClient(caller=caller, _test_transport=_transport(seen), **kwargs)


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
    with _client(seen, CALLER_DOWNLOADER, base_url=ROOT) as client:
        assert client.get("instruments").status_code == 200  # noqa: PLR2004
    with _client(seen, CALLER_KITE_CLIENT, base_url=ROOT) as client:
        assert client.post("/session/token", data={"a": "b"}).status_code == 200  # noqa: PLR2004
    with _client(seen, CALLER_KITE_HISTORY, base_url=ROOT) as client:
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

    client = kite_http.KiteClient(caller=CALLER_KITE_CLIENT, _test_transport=httpx.MockTransport(handler))
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
    async with _async_client(seen, CALLER_KITE_CLIENT) as client:
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


# -- #353: each client module may make only its own listed calls ----------------------------------------------------

def test_353_the_margin_transport_cannot_read_orders_and_nothing_is_sent(monkeypatch) -> None:
    """REQ-073 AC-4 (#353, the issue's example): ``kite_margin``'s own transport sending GET /orders is refused
    before the opener (kite_margin_refused)."""
    from ofo.broker import kite_http as broker_http  # noqa: PLC0415
    from ofo_app.kite_margin import KiteMarginError, margin_transport  # noqa: PLC0415

    opened: list[object] = []
    monkeypatch.setattr(broker_http._OPENER, "open", lambda *a, **k: opened.append(a))
    for path in ("/orders", "/portfolio/positions", "/instruments"):
        with pytest.raises(KiteMarginError) as raised:
            margin_transport("GET", ROOT + path, {}, None)
        assert raised.value.code == "kite_margin_refused"
    assert opened == []


def test_353_kite_reads_cannot_read_margins_and_its_transport_is_never_called() -> None:
    """REQ-073 AC-4 (#353): KiteReads checks as its own module, so a margin call is refused before the transport."""
    from ofo_app.kite_reads import KiteReadError, KiteReads  # noqa: PLC0415

    sent: list[object] = []
    reads = KiteReads(api_key="k", access_token="t", transport=lambda *a: sent.append(a) or (200, "{}"))  # noqa: S106
    with pytest.raises(KiteReadError) as raised:
        reads._data("GET", "/user/margins")
    assert raised.value.code == "kite_read_refused" and sent == []


def test_353_the_reads_transport_cannot_send_a_margin_basket(monkeypatch) -> None:
    """REQ-073 AC-4 (#353): ``kite_reads.reads_transport`` refuses POST /margins/basket before the opener."""
    from ofo.broker import kite_http as broker_http  # noqa: PLC0415
    from ofo_app.kite_margin import KiteMarginError  # noqa: PLC0415
    from ofo_app.kite_reads import reads_transport  # noqa: PLC0415

    opened: list[object] = []
    monkeypatch.setattr(broker_http._OPENER, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(KiteMarginError):
        reads_transport("POST", ROOT + "/margins/basket?consider_positions=true", {}, "[]")
    assert opened == []


@pytest.mark.parametrize(("caller", "path"), [(CALLER_KITE_CLIENT, "/orders"), (CALLER_DOWNLOADER, "/session/token"),
                                              (CALLER_KITE_MARGIN, "/orders"), (CALLER_KITE_HISTORY, "/instruments")])
def test_353_an_httpx_client_built_for_one_module_refuses_another_modules_call(caller: str, path: str) -> None:
    """REQ-073 AC-4 (#353): the httpx door client carries its module; another module's call never reaches the wire."""
    seen: list[httpx.Request] = []
    with _client(seen, caller) as client, pytest.raises(kite_http.KiteCallRefused):
        client.get(ROOT + path)
    assert seen == []


@pytest.mark.parametrize("caller", [None, "", "ofo_app/routes/broker.py", 3])
def test_353_an_httpx_client_for_an_unlisted_module_cannot_be_built(caller: object) -> None:
    """REQ-073 AC-4 (#353, fail closed): no client exists for a module not in ALLOWED_CALLS."""
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.KiteClient(caller=caller)  # type: ignore[arg-type]
    with pytest.raises(kite_http.KiteCallRefused):
        kite_http.KiteAsyncClient(caller=caller)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        kite_http.KiteClient()  # type: ignore[call-arg]


async def test_353_the_session_client_is_built_as_kite_client() -> None:
    """REQ-073 AC-4 (#353): ``kite_client.session_client`` may post /session/token and nothing else."""
    from ofo_app.kite_client import session_client  # noqa: PLC0415

    async with session_client() as client:
        assert client._kite_caller == CALLER_KITE_CLIENT
        with pytest.raises(kite_http.KiteCallRefused):
            await client.get(ROOT + "/orders")
