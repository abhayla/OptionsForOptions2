"""W-080 round 7 (REQ-073 AC-4): the egress gate against the httpx and websocket routes, with planted REAL calls.

Verifier END CONDITION: "A fresh module in ordinary Python, using any import route, any client, or any public or private attribute with a literal name, that opens a non-loopback connection or reaches POST /orders* is refused at runtime, or flagged by the scan. Out of scope, and noted only: ctypes/cffi, computed-name reflection (getattr(x, '_'+s), gc), changing the hook's state, and native-code event loops."

Each planted bypass aims at TEST-NET 192.0.2.1 (never routed, never Kite) and expects ``EgressRefused`` before any
packet leaves; with the gate disabled each would try the network instead. No database is needed.
"""  # noqa: E501
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from ofo.broker import egress
from ofo.broker.egress import EgressRefused
from ofo_app import kite_client, kite_http, kite_ws

TEST_NET = "192.0.2.1"
KITE = "https://api.kite.trade"


# -- planted bypasses ------------------------------------------------------------------------------------------------

def test_r2_a_passed_in_raw_httpx_client() -> None:
    def place(client: httpx.Client) -> None:  # "any client": the caller hands in a plain one
        client.post(f"https://{TEST_NET}/orders/regular", data={"x": "1"})

    with httpx.Client(timeout=2) as raw, pytest.raises(EgressRefused):
        place(raw)


def _refused(exc: BaseException) -> bool:
    """EgressRefused itself, or inside the exception group anyio's happy-eyeballs connect wraps it in."""
    if isinstance(exc, EgressRefused):
        return True
    return isinstance(exc, BaseExceptionGroup) and any(_refused(e) for e in exc.exceptions)


async def test_r2_the_login_adapter_with_a_raw_client(monkeypatch) -> None:
    monkeypatch.setattr(kite_client, "KITE_API_ROOT", f"https://{TEST_NET}")
    async with httpx.AsyncClient(timeout=2) as raw:
        auth = kite_client.HttpKiteAuth("key", "secret", raw)  # no is_guarded any more: the gate refuses the connect
        with pytest.raises(BaseException) as caught:
            await auth.exchange("request-token")
    assert _refused(caught.value), repr(caught.value)


def test_r3_unicode_dot_host_from_a_non_door_module() -> None:
    with httpx.Client(timeout=2) as raw, pytest.raises(EgressRefused):
        raw.post("https://192。0。2。1/orders/regular")  # httpx folds U+3002 to "."


def test_r6_the_door_no_longer_exports_httpx() -> None:
    with pytest.raises(ImportError):
        exec("from ofo_app.kite_http import httpx", {})  # noqa: S102 - the import route itself is what is tested


@pytest.mark.parametrize("door", [kite_http, kite_ws])
def test_each_doors_public_names_equal_all(door) -> None:
    public = {n for n in vars(door) if not n.startswith("_")} - {"annotations"}
    imported_modules = {n for n in public if type(vars(door)[n]).__name__ == "module"}
    assert public - imported_modules == set(door.__all__), door.__name__


def test_r6_a_guarded_clients_transport_and_super_last_hop() -> None:
    request = httpx.Request("POST", f"https://{TEST_NET}/orders/regular")
    with kite_http.kite_client(timeout=2) as client:
        with pytest.raises(EgressRefused):
            client._transport.handle_request(request)
        with pytest.raises(EgressRefused):
            super(kite_http.KiteClient, client)._send_single_request(request)
        with pytest.raises(EgressRefused):
            httpx.Client._send_single_request(client, request)


def test_closed_constructor_arguments() -> None:
    """No caller code can be handed to a door client to run inside door context."""
    for kwargs in ({"transport": httpx.MockTransport(lambda r: httpx.Response(200))},
                   {"event_hooks": {"request": [print]}}, {"auth": ("a", "b")}, {"mounts": {}},
                   {"follow_redirects": True}, {"verify": False}):
        with pytest.raises(TypeError):
            kite_http.KiteClient(**kwargs)
        with pytest.raises(TypeError):
            kite_http.kite_async_client(**kwargs)


def test_the_test_seam_is_refused_outside_test_mode(monkeypatch) -> None:
    monkeypatch.setitem(egress._state, "test", False)
    with pytest.raises(EgressRefused):
        kite_http.KiteClient(_test_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(EgressRefused):
        kite_ws.KiteSocket(_provider(), api_key="k", access_token="t", clock=lambda: None,  # noqa: S106
                           connect=lambda *a, **k: None)


def _connect_test_net() -> None:
    socket.create_connection((TEST_NET, 443), timeout=2)


def test_a_callback_never_runs_inside_door_context() -> None:
    """A per-request auth flow and a streamed body are the caller code httpx still accepts: both run outside."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    class Auth(httpx.Auth):
        def auth_flow(self, request):
            _connect_test_net()
            yield request

    def body():
        _connect_test_net()
        yield b"x"

    with kite_http.KiteClient(_test_transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EgressRefused):
            client.get(KITE + "/instruments", auth=Auth())
        with pytest.raises(EgressRefused):
            client.post(KITE + "/margins/basket", content=body())


class _Ok(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:
        pass


def test_no_pooled_connection_outlives_its_door() -> None:
    """Keep-alive 0: after a door request, no open connection is left for caller code to reuse outside the door."""
    server = HTTPServer(("127.0.0.1", 0), _Ok)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:  # the door's own transport, on a loopback server (a Kite URL with a port is refused by check_call)
        with kite_http.kite_client(timeout=5) as client:
            response = client._transport.handle_request(httpx.Request("GET", f"http://127.0.0.1:{server.server_port}/"))
            assert response.read() == b"ok"
            response.close()
            assert client._transport._pool.connections == []
    finally:
        server.shutdown()
        server.server_close()


# -- the doors still work --------------------------------------------------------------------------------------------

def test_the_http_door_reaches_an_allowed_path_inside_door_context_only() -> None:
    seen: list[tuple[str, bool]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, egress._in_door()))
        return httpx.Response(200, json={})

    with kite_http.KiteClient(_test_transport=httpx.MockTransport(handler)) as client:
        assert client.get(KITE + "/instruments").status_code == 200  # noqa: PLR2004
        with pytest.raises(kite_http.KiteCallRefused):
            client.post(KITE + "/orders/regular", data={"x": "1"})
    assert seen == [("/instruments", True)] and not egress._in_door()


async def test_the_async_http_door_reaches_an_allowed_path_inside_door_context_only() -> None:
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(egress._in_door())
        return httpx.Response(200, json={})

    async with kite_http.KiteAsyncClient(_test_transport=httpx.MockTransport(handler)) as client:
        assert (await client.post(KITE + "/session/token", data={"a": "b"})).status_code == 200  # noqa: PLR2004
    assert seen == [True] and not egress._in_door()


class _Provider:  # the calls KiteSocket makes on a connect that fails
    def on_disconnected(self, when) -> None:
        pass


def _provider() -> _Provider:
    return _Provider()


async def test_the_socket_door_opens_door_context_only_for_the_real_connect(monkeypatch) -> None:
    seen: list[bool] = []

    class _Cm:
        async def __aenter__(self):
            seen.append(egress._in_door())
            raise ConnectionError("stop here")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(kite_ws, "_ws_connect", lambda url, **k: _Cm())  # stands in for the real websockets connect
    sock = kite_ws.KiteSocket(_provider(), api_key="k", access_token="t", clock=lambda: None)  # noqa: S106

    async def stop_after_first(_seconds: float) -> None:
        sock.stop()

    sock._sleep = stop_after_first
    await sock.run()
    sock = kite_ws.KiteSocket(_provider(), api_key="k", access_token="t", clock=lambda: None,  # noqa: S106
                              connect=lambda url, **k: _Cm(), sleep=stop_after_first)  # an injected connect (tests only)  # noqa: E501
    await sock.run()
    assert seen == [True, False] and not egress._in_door()
