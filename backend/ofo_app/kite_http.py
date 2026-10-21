"""The only place an httpx client for Kite is built (REQ-073 AC-4, ADR-054; W-080 rounds 7-9).

``KiteClient`` / ``KiteAsyncClient`` take PLAIN DATA only (W-080 round 9): ``request`` / ``get`` / ``post`` / ``put`` /
``delete`` accept a method from a fixed set, a ``str`` URL, and params / form data / JSON / bytes / headers built from
plain ``str`` / ``int`` / ``float`` / ``Decimal`` / ``bool`` / ``None`` / ``dict`` / ``list`` values, checked by exact
type before anything is sent. No ``extensions`` (an httpx trace callback), ``auth``, ``event_hooks``, ``cookies``,
``transport``, body iterator or ``**kwargs`` is accepted (a TypeError); ``send``, ``stream`` and ``build_request`` are
closed. The constructor takes only ``caller``, ``base_url``, ``timeout`` and ``headers``.

Each client is built for ONE calling module (``caller``: its ``kite_endpoints.CALLER_*`` constant, #353) and may make
only that module's calls. At the LAST hop (``_send_single_request``: after redirects, to the absolute URL httpx merged
with ``base_url``) the door applies ``ofo.broker.kite_http.check_call`` for that caller, reads the body, refuses any
request extension but a plain timeout,
and builds a FRESH request from plain bytes. Only then does it open the egress gate's door permission
(``ofo.broker.egress``), around the transport call alone: cookies, logging and the response wrapping run after it.
The permission holds only for the door's own call chain (its thread, task and frame, through trusted libraries), so
caller code that still ran inside it gets nothing. Outside it the gate refuses every non-loopback connect.

The transport is built here with keep-alive 0 (every request a fresh connect), no proxies (``trust_env`` off) and, for
the async client, a network backend that connects in the door's own task (anyio's happy-eyeballs connect would run it
in a child task, which the gate refuses). Tests pass a mock transport as ``_test_transport``, refused outside the test
suites.
"""
from __future__ import annotations

import json as _json
import logging as _logging
import socket as _socket
import time as _time
from collections.abc import Coroutine as _Coroutine
from collections.abc import Mapping as _Mapping
from decimal import Decimal as _Decimal

import anyio as _anyio
import anyio.abc as _anyio_abc
import h11 as _h11
import httpcore as _httpcore
import httpx as _httpx

try:  # newer anyio no longer depends on sniffio (CI's app environment lacks it); trust its frames only if installed
    import sniffio as _sniffio
except ImportError:  # pragma: no cover - depends on the installed anyio
    _sniffio = None
from httpcore._backends.anyio import AnyIOStream as _AnyIOStream
from httpx._client import BoundAsyncStream as _BoundAsyncStream
from httpx._client import BoundSyncStream as _BoundSyncStream
from ofo.broker import egress as _egress
from ofo.broker.kite_endpoints import ALLOWED_CALLS as _ALLOWED_CALLS
from ofo.broker.kite_http import KiteCallRefused
from ofo.broker.kite_http import check_call as _check_call
from ofo.broker.kite_http import plain_headers as _plain_headers
from ofo.broker.kite_http import plain_method as _plain_method
from ofo.broker.kite_http import plain_str as _plain_str
from ofo.broker.kite_http import plain_timeout as _plain_timeout

HTTPError = _httpx.HTTPError  # the one httpx name a consumer needs, so a consumer imports no network module

_TIMEOUT = 20.0
_httpx_log = _logging.getLogger("httpx")
_SCALARS = (str, int, float, bool, _Decimal, type(None))
_MAX_NESTING = 20
_TIMEOUT_KEYS = frozenset({"connect", "read", "write", "pool"})

_egress._trust_modules(*(m for m in (_anyio, _h11, _httpcore, _httpx, _sniffio) if m is not None), __file__)
_egress.install()  # W-080 integration: importing a Kite door installs the gate (idempotent with create_app's)


def _limits() -> _httpx.Limits:
    return _httpx.Limits(max_keepalive_connections=0)  # every request a fresh connect, inside its own door


class _SameTaskBackend(_httpcore.AsyncNetworkBackend):
    """Connects in the CALLING task (one address at a time), so the connect is in the door's own task and stack."""

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
                          local_address: str | None = None, socket_options=None) -> _httpcore.AsyncNetworkStream:
        with _anyio.fail_after(timeout):
            infos = await _anyio.getaddrinfo(host, port, type=_socket.SOCK_STREAM)
            error: OSError | None = None
            for family, kind, proto, _name, address in infos:
                sock = _socket.socket(family, kind, proto)
                try:
                    sock.setblocking(False)
                    for option in socket_options or ():
                        sock.setsockopt(*option)
                    if _connect_started(sock, address):
                        await _anyio.wait_writable(sock)
                    if sock.getsockopt(_socket.SOL_SOCKET, _socket.SO_ERROR):
                        raise OSError("connect failed")
                    stream = await _anyio_abc.SocketStream.from_socket(sock)
                    return _AnyIOStream(stream)
                except OSError as exc:
                    sock.close()
                    error = exc
            raise _httpcore.ConnectError(type(error).__name__ if error else "no address")

    async def connect_unix_socket(self, path: str, timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
                                  socket_options=None):
        raise _httpcore.ConnectError("a Kite door connects over TCP only")

    async def sleep(self, seconds: float) -> None:
        await _anyio.sleep(seconds)


def _connect_started(sock: _socket.socket, address: tuple) -> bool:
    """Start a non-blocking connect HERE (this task's stack); True when it is still in progress."""
    try:
        sock.connect(address)
    except BlockingIOError:
        return True
    return False


class _AsyncTransport(_httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__(limits=_limits(), trust_env=False)
        self._pool = _httpcore.AsyncConnectionPool(ssl_context=self._pool._ssl_context, max_keepalive_connections=0,
                                                   network_backend=_SameTaskBackend())


def _transport(make, test_transport):
    if test_transport is None:
        return make()
    if not _egress._test_mode():  # the test seam: refused outside the test suites
        raise _egress.EgressRefused("a Kite client takes a test transport only inside the test suites")
    return test_transport


def _plain_value(value: object, what: str, depth: int = 0) -> object:
    """A JSON / form value built from plain types only (exact types; Decimal becomes its str)."""
    kind = type(value)
    if depth > _MAX_NESTING:
        raise TypeError(f"a Kite door takes {what} nested at most 20 deep; nothing was sent")
    if kind is _Decimal:
        return str(value)
    if kind in _SCALARS:
        return value
    if kind is list:
        return [_plain_value(v, what, depth + 1) for v in value]  # type: ignore[attr-defined]
    if kind is dict:
        return {_plain_str(k, f"a key of {what}"): _plain_value(v, what, depth + 1)
                for k, v in value.items()}  # type: ignore[attr-defined]
    raise TypeError(f"a Kite door takes {what} as plain str/int/float/Decimal/bool/None/dict/list; nothing was sent")


def _plain_form(value: object, what: str) -> dict | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise TypeError(f"a Kite door takes {what} as a plain dict; nothing was sent")
    plain = _plain_value(value, what)
    if any(type(v) in (dict, list) for v in plain.values()):  # type: ignore[union-attr]
        raise TypeError(f"a Kite door takes {what} with scalar values only; nothing was sent")
    return {k: "" if v is None else str(v) for k, v in plain.items()}  # type: ignore[union-attr]


def _plain_args(method: object, url: object, *, params: object, data: object, json: object, content: object,  # noqa: PLR0913 - one plain-data check per httpx keyword
                headers: object, timeout: object) -> dict:
    """Every argument checked by exact type and converted to plain data (strings and bytes) BEFORE any send."""
    args: dict = {"method": _plain_method(method), "url": _plain_str(url, "the URL"),
                  "headers": _plain_headers(headers), "params": _plain_form(params, "params"),
                  "data": _plain_form(data, "form data")}
    if json is not None:
        args["content"] = _json.dumps(_plain_value(json, "the JSON body")).encode("utf-8")
        args["headers"].setdefault("Content-Type", "application/json")
    if content is not None:
        if json is not None or type(content) not in (bytes, str):
            raise TypeError("a Kite door takes content as plain bytes or str, without json; nothing was sent")
        args["content"] = content.encode("utf-8") if type(content) is str else content
    if timeout is not None:
        args["timeout"] = _plain_timeout(timeout)
    return args


def _known_caller(caller: object) -> str:
    """``caller`` as a key of ``ALLOWED_CALLS`` (exact ``str``), checked when the client is built (#353)."""
    if type(caller) is not str or caller not in _ALLOWED_CALLS:
        raise KiteCallRefused("a Kite client is built only for a module listed in ALLOWED_CALLS; nothing was sent")
    return caller


def _plain_request(request: _httpx.Request, caller: str) -> _httpx.Request:
    """A fresh request from plain bytes: nothing of the caller's request object (a subclass, its extensions, its
    stream) is reachable inside the door. Called after the body was read, before the door opens."""
    method = _plain_method(str(request.method))
    url = str(request.url)
    _check_call(method, url, caller=caller)
    content = request.content
    if type(content) is not bytes:
        raise KiteCallRefused(f"{method}: the body is not plain bytes; nothing was sent")
    extensions = dict(request.extensions)
    timeout = extensions.pop("timeout", None)
    if extensions:  # a trace callback, an sni_hostname, anything else: caller-supplied, refused
        raise KiteCallRefused(f"{method}: request extensions {sorted(map(str, extensions))} are refused; nothing was "
                              "sent")
    plain_timeout: dict = {}
    if timeout is not None:
        if type(timeout) is not dict or not set(timeout) <= _TIMEOUT_KEYS \
                or any(type(v) not in (int, float, type(None)) for v in timeout.values()):
            raise KiteCallRefused(f"{method}: the timeout is not plain numbers; nothing was sent")
        plain_timeout = {"timeout": dict(timeout)}
    headers = [(bytes(k), bytes(v)) for k, v in request.headers.raw]
    return _httpx.Request(method, url, headers=headers, content=bytes(content), extensions=plain_timeout)


def _log_sent(request: _httpx.Request, response: _httpx.Response) -> None:
    """httpx's own request log line, written AFTER the door closed (a log handler is caller code)."""
    _httpx_log.info('HTTP Request: %s %s "%s %d %s"', request.method, request.url, response.http_version,
                    response.status_code, response.reason_phrase)


class _Closed:
    def send(self, *args, **kwargs):
        raise TypeError("a Kite door takes plain data through request/get/post/put/delete only; send is closed")

    stream = build_request = send


class KiteClient(_httpx.Client):
    def __init__(self, *, caller: str, base_url: str = "", timeout: float = _TIMEOUT,
                 headers: _Mapping[str, str] | None = None,
                 _test_transport: _httpx.BaseTransport | None = None) -> None:
        self._kite_caller = _known_caller(caller)
        super().__init__(base_url=_plain_str(base_url, "the base URL"), timeout=_plain_timeout(timeout),
                         headers=_plain_headers(None if headers is None else dict(headers)), follow_redirects=False,
                         trust_env=False,
                         transport=_transport(lambda: _httpx.HTTPTransport(limits=_limits(), trust_env=False),
                                              _test_transport))

    send = _Closed.send
    stream = _Closed.stream
    build_request = _Closed.build_request

    def request(self, method: str, url: str, *, params: dict | None = None, data: dict | None = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
                json: object = None, content: bytes | str | None = None, headers: dict | None = None,
                timeout: float | None = None) -> _httpx.Response:
        args = _plain_args(method, url, params=params, data=data, json=json, content=content, headers=headers,
                           timeout=timeout)
        timeout_arg = args.pop("timeout", _httpx.USE_CLIENT_DEFAULT)
        req = _httpx.Client.build_request(self, **args, timeout=timeout_arg)
        return _httpx.Client.send(self, req, auth=None, follow_redirects=False)

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            timeout: float | None = None) -> _httpx.Response:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(self, url: str, *, params: dict | None = None, data: dict | None = None, json: object = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
             content: bytes | str | None = None, headers: dict | None = None,
             timeout: float | None = None) -> _httpx.Response:
        return self.request("POST", url, params=params, data=data, json=json, content=content, headers=headers,
                            timeout=timeout)

    def put(self, url: str, *, params: dict | None = None, data: dict | None = None, json: object = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
            content: bytes | str | None = None, headers: dict | None = None,
            timeout: float | None = None) -> _httpx.Response:
        return self.request("PUT", url, params=params, data=data, json=json, content=content, headers=headers,
                            timeout=timeout)

    def delete(self, url: str, *, params: dict | None = None, headers: dict | None = None,
               timeout: float | None = None) -> _httpx.Response:
        return self.request("DELETE", url, params=params, headers=headers, timeout=timeout)

    def _send_single_request(self, request: _httpx.Request) -> _httpx.Response:
        _check_call(request.method, str(request.url), caller=self._kite_caller)
        request.read()  # a caller's body generator runs HERE, outside the door, never inside it
        fresh = _plain_request(request, self._kite_caller)
        transport = self._transport
        start = _time.perf_counter()
        with _egress._door():
            response = transport.handle_request(fresh)
        if not isinstance(response.stream, _httpx.SyncByteStream):
            raise KiteCallRefused("the transport returned a stream that is not a sync byte stream")
        response.request = fresh
        response.stream = _BoundSyncStream(response.stream, response=response, start=start)
        self.cookies.extract_cookies(response)
        response.default_encoding = self._default_encoding
        _log_sent(fresh, response)
        return response


class KiteAsyncClient(_httpx.AsyncClient):
    def __init__(self, *, caller: str, base_url: str = "", timeout: float = _TIMEOUT,
                 headers: _Mapping[str, str] | None = None,
                 _test_transport: _httpx.AsyncBaseTransport | None = None) -> None:
        self._kite_caller = _known_caller(caller)
        super().__init__(base_url=_plain_str(base_url, "the base URL"), timeout=_plain_timeout(timeout),
                         headers=_plain_headers(None if headers is None else dict(headers)), follow_redirects=False,
                         trust_env=False, transport=_transport(_AsyncTransport, _test_transport))

    send = _Closed.send
    stream = _Closed.stream
    build_request = _Closed.build_request

    # Plain functions returning the send's coroutine (``await client.post(...)`` as with httpx): the arguments are
    # checked, by exact type, at the CALL, before any coroutine exists.
    def request(self, method: str, url: str, *, params: dict | None = None, data: dict | None = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
                json: object = None, content: bytes | str | None = None, headers: dict | None = None,
                timeout: float | None = None) -> _Coroutine[object, object, _httpx.Response]:
        args = _plain_args(method, url, params=params, data=data, json=json, content=content, headers=headers,
                           timeout=timeout)
        timeout_arg = args.pop("timeout", _httpx.USE_CLIENT_DEFAULT)
        req = _httpx.AsyncClient.build_request(self, **args, timeout=timeout_arg)
        return _httpx.AsyncClient.send(self, req, auth=None, follow_redirects=False)

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
            timeout: float | None = None) -> _Coroutine[object, object, _httpx.Response]:
        return self.request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(self, url: str, *, params: dict | None = None, data: dict | None = None, json: object = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
             content: bytes | str | None = None, headers: dict | None = None,
             timeout: float | None = None) -> _Coroutine[object, object, _httpx.Response]:
        return self.request("POST", url, params=params, data=data, json=json, content=content, headers=headers,
                            timeout=timeout)

    def put(self, url: str, *, params: dict | None = None, data: dict | None = None, json: object = None,  # noqa: PLR0913 - httpx's own keyword names, plain data only
            content: bytes | str | None = None, headers: dict | None = None,
            timeout: float | None = None) -> _Coroutine[object, object, _httpx.Response]:
        return self.request("PUT", url, params=params, data=data, json=json, content=content, headers=headers,
                            timeout=timeout)

    def delete(self, url: str, *, params: dict | None = None, headers: dict | None = None,
               timeout: float | None = None) -> _Coroutine[object, object, _httpx.Response]:
        return self.request("DELETE", url, params=params, headers=headers, timeout=timeout)

    async def _send_single_request(self, request: _httpx.Request) -> _httpx.Response:
        _check_call(request.method, str(request.url), caller=self._kite_caller)
        await request.aread()  # a caller's body generator runs HERE, outside the door, never inside it
        fresh = _plain_request(request, self._kite_caller)
        transport = self._transport
        start = _time.perf_counter()
        with _egress._door():
            response = await transport.handle_async_request(fresh)
        if not isinstance(response.stream, _httpx.AsyncByteStream):
            raise KiteCallRefused("the transport returned a stream that is not an async byte stream")
        response.request = fresh
        response.stream = _BoundAsyncStream(response.stream, response=response, start=start)
        self.cookies.extract_cookies(response)
        response.default_encoding = self._default_encoding
        _log_sent(fresh, response)
        return response


def kite_client(*, caller: str, base_url: str = "", timeout: float = _TIMEOUT,
                headers: _Mapping[str, str] | None = None) -> KiteClient:
    return KiteClient(caller=caller, base_url=base_url, timeout=timeout, headers=headers)


def kite_async_client(*, caller: str, base_url: str = "", timeout: float = _TIMEOUT,
                      headers: _Mapping[str, str] | None = None) -> KiteAsyncClient:
    return KiteAsyncClient(caller=caller, base_url=base_url, timeout=timeout, headers=headers)


__all__ = ["HTTPError", "KiteAsyncClient", "KiteCallRefused", "KiteClient", "kite_async_client", "kite_client"]
