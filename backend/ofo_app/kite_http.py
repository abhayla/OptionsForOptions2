"""The only place an httpx client for Kite is built (REQ-073 AC-4, ADR-054; W-080 round 7).

``KiteClient`` / ``KiteAsyncClient`` apply ``ofo.broker.kite_http.check_call`` at the LAST hop
(``_send_single_request``: after redirects, to the absolute URL httpx merged with ``base_url``) and only then open the
door context of the runtime egress gate (``ofo.broker.egress``) around that one send. Outside it, the gate refuses
every non-loopback connect, so a raw httpx client, a client's ``_transport``, or a bypassed ``send`` cannot reach the
network at all.

Nothing caller-supplied runs inside door context: the constructor takes only ``base_url``, ``timeout`` and
``headers`` (no transport, event hooks, auth, mounts, proxies or redirects), the transport is built here with
keep-alive 0 (every request is a fresh connect, so no pooled connection outlives its door), and the request body is
read before the door opens (a caller's body generator never runs inside it). Auth flows and response hooks run in
``send``, outside the door. Tests pass a mock transport as ``_test_transport``, which is refused outside the test suites.
"""
from __future__ import annotations

from collections.abc import Mapping

import httpx as _httpx

from ofo.broker import egress as _egress
from ofo.broker.kite_http import KiteCallRefused
from ofo.broker.kite_http import check_call as _check_call

HTTPError = _httpx.HTTPError  # the one httpx name a consumer needs, so a consumer imports no network module

_TIMEOUT = 20.0


def _limits() -> _httpx.Limits:
    return _httpx.Limits(max_keepalive_connections=0)  # every request a fresh connect, inside its own door


def _transport(cls_transport, test_transport):
    if test_transport is None:
        return cls_transport(limits=_limits())
    if not _egress._test_mode():  # the test seam: refused outside the test suites
        raise _egress.EgressRefused("a Kite client takes a test transport only inside the test suites")
    return test_transport


class KiteClient(_httpx.Client):
    def __init__(self, *, base_url: str = "", timeout: float = _TIMEOUT, headers: Mapping[str, str] | None = None,
                 _test_transport: _httpx.BaseTransport | None = None) -> None:
        super().__init__(base_url=base_url, timeout=timeout, headers=headers, follow_redirects=False,
                         transport=_transport(_httpx.HTTPTransport, _test_transport))

    def _send_single_request(self, request: _httpx.Request) -> _httpx.Response:
        _check_call(request.method, str(request.url))
        request.read()  # a caller's body generator runs HERE, outside door context, never inside it
        with _egress._door():
            return super()._send_single_request(request)


class KiteAsyncClient(_httpx.AsyncClient):
    def __init__(self, *, base_url: str = "", timeout: float = _TIMEOUT, headers: Mapping[str, str] | None = None,
                 _test_transport: _httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(base_url=base_url, timeout=timeout, headers=headers, follow_redirects=False,
                         transport=_transport(_httpx.AsyncHTTPTransport, _test_transport))

    async def _send_single_request(self, request: _httpx.Request) -> _httpx.Response:
        _check_call(request.method, str(request.url))
        await request.aread()  # a caller's body generator runs HERE, outside door context, never inside it
        with _egress._door():
            return await super()._send_single_request(request)


def kite_client(*, base_url: str = "", timeout: float = _TIMEOUT,
                headers: Mapping[str, str] | None = None) -> KiteClient:
    return KiteClient(base_url=base_url, timeout=timeout, headers=headers)


def kite_async_client(*, base_url: str = "", timeout: float = _TIMEOUT,
                      headers: Mapping[str, str] | None = None) -> KiteAsyncClient:
    return KiteAsyncClient(base_url=base_url, timeout=timeout, headers=headers)


__all__ = ["HTTPError", "KiteAsyncClient", "KiteCallRefused", "KiteClient", "kite_async_client", "kite_client"]
