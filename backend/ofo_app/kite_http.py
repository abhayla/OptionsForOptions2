"""The only place an httpx client for Kite is built (REQ-073 AC-4, ADR-054; run-discipline B8).

``KiteClient`` / ``KiteAsyncClient`` are httpx clients that apply ``ofo.broker.kite_http.check_call`` BEFORE anything is
sent, to the absolute URL httpx has already merged with ``base_url`` (so a relative ``"orders/regular"`` is caught
too). The check is in the CLASS, not in removable configuration, at two points:

- ``send``: every ``get`` / ``post`` / ``request`` / ``stream`` call ends there;
- ``_send_single_request``: the last step before the transport, after request hooks, auth flows and redirects (any of
  which could rewrite the URL after ``send`` looked at it). httpx 0.28 names it so; a test fails if a future httpx
  stops calling it.

Both are read-only class properties (data descriptors), so an instance cannot shadow them: ``client.send = f`` raises,
and a value forced into the instance namespace is never looked up. Emptying ``event_hooks`` or swapping the transport
changes nothing. ``is_guarded(client)`` (exact class, both properties the originals captured at import) is what a
consumer checks before EVERY call, so a patched class or a swapped class is refused too.
"""
from __future__ import annotations

from types import MethodType

import httpx

from ofo.broker.kite_http import KiteCallRefused, check_call

HTTPError = httpx.HTTPError  # the one httpx name a consumer needs, so a consumer imports no network module


def _check(request: httpx.Request) -> None:
    check_call(request.method, str(request.url))


def _sync_send(self: httpx.Client, request: httpx.Request, **kwargs: object) -> httpx.Response:
    _check(request)
    return httpx.Client.send(self, request, **kwargs)  # type: ignore[arg-type]


def _sync_last_hop(self: httpx.Client, request: httpx.Request) -> httpx.Response:
    _check(request)
    return httpx.Client._send_single_request(self, request)


async def _async_send(self: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
    _check(request)
    return await httpx.AsyncClient.send(self, request, **kwargs)  # type: ignore[arg-type]


async def _async_last_hop(self: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    _check(request)
    return await httpx.AsyncClient._send_single_request(self, request)


def _bound(fn):  # a read-only property returning ``fn`` bound to the instance; ``fn`` is fixed when the class is made
    return property(lambda self, _fn=fn: MethodType(_fn, self))


class KiteClient(httpx.Client):
    send = _bound(_sync_send)  # type: ignore[assignment]
    _send_single_request = _bound(_sync_last_hop)  # type: ignore[assignment]


class KiteAsyncClient(httpx.AsyncClient):
    send = _bound(_async_send)  # type: ignore[assignment]
    _send_single_request = _bound(_async_last_hop)  # type: ignore[assignment]


#: the class properties as made at import: a class patched later is no longer guarded.
_ORIGINAL = {KiteClient: (KiteClient.send, KiteClient._send_single_request),
             KiteAsyncClient: (KiteAsyncClient.send, KiteAsyncClient._send_single_request)}


def kite_client(**kwargs: object) -> KiteClient:
    return KiteClient(**kwargs)  # type: ignore[arg-type]


def kite_async_client(**kwargs: object) -> KiteAsyncClient:
    return KiteAsyncClient(**kwargs)  # type: ignore[arg-type]


def is_guarded(client: object) -> bool:
    """True only for a client of exactly one of the two classes whose checking properties are untouched."""
    cls = type(client)  # exact type: a subclass could override send without the check
    original = _ORIGINAL.get(cls)
    return original is not None and (cls.send, cls._send_single_request) == original  # type: ignore[attr-defined]


__all__ = ["HTTPError", "KiteAsyncClient", "KiteCallRefused", "KiteClient", "is_guarded", "kite_async_client",
           "kite_client"]
