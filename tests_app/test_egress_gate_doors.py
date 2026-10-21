"""W-080 round 7 (REQ-073 AC-4): the egress gate against the httpx and websocket routes, with planted REAL calls.

Verifier END CONDITION: "A fresh module in ordinary Python, using any import route, any client, or any public or private attribute with a literal name, that opens a non-loopback connection or reaches POST /orders* is refused at runtime, or flagged by the scan. Out of scope, and noted only: ctypes/cffi, computed-name reflection (getattr(x, '_'+s), gc), changing the hook's state, and native-code event loops."

Each planted bypass aims at TEST-NET 192.0.2.1 (never routed, never Kite) and expects ``EgressRefused`` before any
packet leaves; with the gate disabled each would try the network instead. No database is needed.
"""  # noqa: E501
from __future__ import annotations

import asyncio
import contextvars
import logging
import logging.handlers
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from ofo.broker import egress
from ofo.broker import kite_http as broker_http
from ofo.broker.egress import EgressRefused
from ofo.broker.kite_endpoints import CALLER_DOWNLOADER, CALLER_KITE_CLIENT, CALLER_KITE_READS
from ofo_app import kite_client, kite_http, kite_ws
from websockets.asyncio.server import serve

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
    with kite_http.kite_client(caller=CALLER_KITE_READS, timeout=2) as client:
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
            kite_http.KiteClient(caller=CALLER_KITE_READS, **kwargs)
        with pytest.raises(TypeError):
            kite_http.kite_async_client(caller=CALLER_KITE_READS, **kwargs)


def test_the_test_seam_is_refused_outside_test_mode(monkeypatch) -> None:
    monkeypatch.setitem(egress._state, "test", False)
    with pytest.raises(EgressRefused):
        kite_http.KiteClient(caller=CALLER_KITE_READS,
                             _test_transport=httpx.MockTransport(lambda r: httpx.Response(200)))
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

    with kite_http.KiteClient(caller=CALLER_DOWNLOADER, _test_transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TypeError):  # W-080 r9: the door API takes no auth and no body iterator at all
            client.get(KITE + "/instruments", auth=Auth())
        with pytest.raises(TypeError):
            client.post(KITE + "/margins/basket", content=body())
        with pytest.raises(EgressRefused):  # the unbound httpx send: the auth flow still runs outside the door
            httpx.Client.send(client, httpx.Request("GET", KITE + "/instruments"), auth=Auth())
        with pytest.raises(EgressRefused):  # and the body generator is read before it
            # #353: this client is the downloader, so its own GET carries the body generator
            httpx.Client.send(client, httpx.Request("GET", KITE + "/instruments", content=body()))


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
        with kite_http.kite_client(caller=CALLER_KITE_READS, timeout=5) as client:
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

    with kite_http.KiteClient(caller=CALLER_DOWNLOADER, _test_transport=httpx.MockTransport(handler)) as client:
        assert client.get(KITE + "/instruments").status_code == 200  # noqa: PLR2004
        with pytest.raises(kite_http.KiteCallRefused):
            client.post(KITE + "/orders/regular", data={"x": "1"})
    assert seen == [("/instruments", True)] and not egress._in_door()


async def test_the_async_http_door_reaches_an_allowed_path_inside_door_context_only() -> None:
    seen: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(egress._in_door())
        return httpx.Response(200, json={})

    async with kite_http.KiteAsyncClient(caller=CALLER_KITE_CLIENT,
                                         _test_transport=httpx.MockTransport(handler)) as client:
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
                              connect=lambda url, **k: _Cm(), sleep=stop_after_first)  # injected connect, tests only
    await sock.run()
    assert seen == [True, False] and not egress._in_door()


# -- W-080 round 8: the public door APIs refuse a non-Kite host with zero door entries ----------------------------------

@pytest.fixture
def door_entries(monkeypatch) -> list[int]:
    import contextlib
    entries: list[int] = []

    @contextlib.contextmanager
    def counting():
        entries.append(1)
        yield

    monkeypatch.setattr(egress, "_door", counting)
    return entries


def test_r8_kite_client_refuses_a_non_kite_base_url(door_entries: list[int]) -> None:
    from ofo.broker.kite_http import KiteCallRefused
    with kite_http.kite_client(caller=CALLER_KITE_READS,
                               base_url=f"http://{TEST_NET}", timeout=2) as client, pytest.raises(KiteCallRefused):
        client.post("/x")
    assert door_entries == []


async def test_r8_kite_async_client_refuses_a_non_kite_base_url(door_entries: list[int]) -> None:
    from ofo.broker.kite_http import KiteCallRefused
    async with kite_http.kite_async_client(caller=CALLER_KITE_READS,
                                           base_url=f"http://{TEST_NET}", timeout=2) as client:
        with pytest.raises(KiteCallRefused):
            await client.get("/x")
    assert door_entries == []


def test_r8_kite_socket_refuses_a_non_kite_ws_url(door_entries: list[int]) -> None:
    from ofo.broker.kite_http import KiteCallRefused
    with pytest.raises(KiteCallRefused):
        kite_ws.KiteSocket(_provider(), api_key="k", access_token="t", clock=lambda: None,  # noqa: S106
                           base_url=f"ws://{TEST_NET}:80")
    assert door_entries == []


# -- W-080 round 9: caller code run while a door's permission is active gets nothing -----------------------------------
# Each attack aims at TEST-NET; on the round-8 head each one reached socket.connect (a timeout, not EgressRefused).

def _trace_attack(seen: list[str]):
    def inside(name, info):
        seen.append(name)
        _connect_test_net()
    return inside


def test_r9_a_trace_extension_is_refused_at_the_door_signature() -> None:
    seen: list[str] = []
    with kite_http.kite_client(caller=CALLER_KITE_READS, timeout=2) as client, pytest.raises(TypeError):
        client.get(KITE + "/user/margins", extensions={"trace": _trace_attack(seen)})
    assert seen == []


def test_r9_a_hand_built_request_with_a_trace_is_refused_at_the_last_hop() -> None:
    seen: list[str] = []
    request = httpx.Request("GET", KITE + "/user/margins", extensions={"trace": _trace_attack(seen)})
    with kite_http.KiteClient(caller=CALLER_KITE_READS,
                              _test_transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client,             pytest.raises(kite_http.KiteCallRefused):
        httpx.Client.send(client, request)
    assert seen == []


async def test_r9_a_hand_built_async_request_with_a_trace_is_refused_at_the_last_hop() -> None:
    seen: list[str] = []
    request = httpx.Request("POST", KITE + "/session/token", extensions={"trace": _trace_attack(seen)})
    async with kite_http.KiteAsyncClient(caller=CALLER_KITE_READS,
                                         _test_transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        with pytest.raises(kite_http.KiteCallRefused):
            await httpx.AsyncClient.send(c, request)
    assert seen == []


def test_r9_plain_data_only_at_the_door_signature() -> None:
    class Sly(str):
        def encode(self, *args, **kwargs):
            _connect_test_net()
            return super().encode(*args, **kwargs)

    with kite_http.kite_client(caller=CALLER_KITE_READS, timeout=2) as client:
        for bad in ({"headers": {"X-Kite-Version": Sly("3")}}, {"params": {"a": object()}}, {"json": {1: "x"}},
                    {"content": iter([b"x"])}):
            with pytest.raises(TypeError):
                client.request("GET", KITE + "/instruments", **bad)
        with pytest.raises(TypeError):
            client.request(Sly("GET"), KITE + "/instruments")
    for bad in ({"headers": {"a": Sly("b")}}, {"data": bytearray(b"x")}, {"timeout": "20"}):
        with pytest.raises(TypeError):
            broker_http.open_url(KITE + "/instruments", caller=CALLER_DOWNLOADER, **bad)
    with pytest.raises(TypeError):
        kite_ws.KiteSocket(_provider(), api_key=Sly("k"), access_token="t", clock=lambda: None)  # noqa: S106 - a placeholder, never a secret


def test_r9_a_copied_context_from_inside_a_door_gets_nothing() -> None:
    with egress._door():
        ctx = contextvars.copy_context()
        with pytest.raises(EgressRefused):  # caller code inside the door: not the door's own frame chain
            ctx.run(_connect_test_net)
    with pytest.raises(EgressRefused):  # after the door: its nonce is dead
        ctx.run(_connect_test_net)


async def test_r9_a_task_or_thread_started_inside_a_door_gets_nothing() -> None:
    async def connect() -> None:
        _connect_test_net()

    errors: list[BaseException] = []

    def in_thread() -> None:
        try:
            _connect_test_net()
        except BaseException as exc:
            errors.append(exc)

    with egress._door():
        task = asyncio.create_task(connect())
        with pytest.raises(EgressRefused):
            await task
        with pytest.raises(EgressRefused):
            await asyncio.to_thread(_connect_test_net)  # to_thread copies the context into the worker thread
        with pytest.raises(EgressRefused):
            await asyncio.get_running_loop().run_in_executor(None, contextvars.copy_context().run, _connect_test_net)
        thread = threading.Thread(target=contextvars.copy_context().run, args=(in_thread,))
        thread.start()
        thread.join(10)
    assert [type(e) for e in errors] == [EgressRefused]


def test_r9_a_log_handler_or_trace_function_inside_a_door_gets_nothing() -> None:
    errors: list[BaseException] = []

    class Handler(logging.Handler):
        def emit(self, record) -> None:
            try:
                _connect_test_net()
            except BaseException as exc:
                errors.append(exc)

    class StdlibSocket(logging.handlers.SocketHandler):
        def handleError(self, record) -> None:
            errors.append(sys.exc_info()[1])

    log = logging.getLogger("ofo_app.test_r9")
    log.propagate = False
    handlers = [Handler(), StdlibSocket(TEST_NET, 9)]
    for h in handlers:
        log.addHandler(h)
    try:
        with egress._door():
            log.warning("inside the door")
    finally:
        for h in handlers:
            log.removeHandler(h)
    assert [type(e) for e in errors] == [EgressRefused, EgressRefused]

    errors.clear()

    def target() -> int:
        return 1

    def tracer(frame, event, arg):
        if event == "call" and frame.f_code is target.__code__:
            try:
                _connect_test_net()
            except BaseException as exc:
                errors.append(exc)

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        with egress._door():
            target()
    finally:
        sys.settrace(previous)
    assert [type(e) for e in errors] == [EgressRefused]


# -- W-080 round 9: with the door as the ONLY permission, every real door transport still connects -------------------

@pytest.fixture
def door_only(monkeypatch):
    """Loopback is no longer allowed by address: a connect passes only through the door's own permission."""
    monkeypatch.setattr(egress, "_address_allowed", lambda family, address: False)
    # the local server has a port, which the URL check refuses; this test is about the egress permission alone
    monkeypatch.setattr(kite_http, "_check_call", lambda method, url, *, caller: None)
    monkeypatch.setattr(broker_http, "check_call", lambda method, url, *, caller: None)
    with pytest.raises(EgressRefused):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


@pytest.fixture
def local_server():
    class Ok(_Ok):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.do_GET()

    server = HTTPServer(("127.0.0.1", 0), Ok)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_r9_the_sync_doors_connect_through_their_own_permission(door_only, local_server) -> None:
    with kite_http.kite_client(caller=CALLER_DOWNLOADER, timeout=5) as client:
        assert client.get(local_server + "/instruments").text == "ok"
    with broker_http.open_url(local_server + "/instruments", caller=CALLER_DOWNLOADER, timeout=5) as response:
        assert response.read() == b"ok"


async def test_r9_the_async_door_connects_in_its_own_task(door_only, local_server) -> None:
    async with kite_http.kite_async_client(caller=CALLER_KITE_CLIENT, timeout=5) as client:
        response = await client.post(local_server + "/session/token", data={"a": "b"})
    assert response.text == "ok"


async def test_r9_the_socket_door_connects_through_its_own_permission(door_only) -> None:
    async def handler(ws) -> None:
        await ws.close()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sock = kite_ws.KiteSocket(_provider(), api_key="k", access_token="t", clock=lambda: None,  # noqa: S106 - a placeholder, never a secret
                                  base_url=f"ws://127.0.0.1:{port}")
        async with sock._opened() as ws:
            assert ws is not None
