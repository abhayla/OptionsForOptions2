"""The only place an httpx client for Kite is built (REQ-073 AC-4, ADR-054; run-discipline B8).

Every client carries a request hook that applies ``ofo.broker.kite_http.check_call`` BEFORE the request is sent, to the
absolute URL httpx has already merged with ``base_url`` (so a relative ``"orders/regular"`` is caught too). The caller
cannot pass its own ``event_hooks``; ``is_guarded`` lets a consumer (``HttpKiteAuth``) refuse a client that did not
come from here or had its hook removed.
"""
from __future__ import annotations

import httpx

from ofo.broker.kite_http import KiteCallRefused, check_call


def _hook(request: httpx.Request) -> None:
    check_call(request.method, str(request.url))


async def _ahook(request: httpx.Request) -> None:
    check_call(request.method, str(request.url))


def kite_client(**kwargs: object) -> httpx.Client:
    if "event_hooks" in kwargs:
        raise TypeError("event_hooks are set by the Kite client factory")
    return httpx.Client(event_hooks={"request": [_hook]}, **kwargs)  # type: ignore[arg-type]


def kite_async_client(**kwargs: object) -> httpx.AsyncClient:
    if "event_hooks" in kwargs:
        raise TypeError("event_hooks are set by the Kite client factory")
    return httpx.AsyncClient(event_hooks={"request": [_ahook]}, **kwargs)  # type: ignore[arg-type]


def is_guarded(client: object) -> bool:
    hooks = getattr(client, "event_hooks", None)
    if not isinstance(hooks, dict):
        return False
    wanted = _ahook if isinstance(client, httpx.AsyncClient) else _hook
    return isinstance(client, (httpx.Client, httpx.AsyncClient)) and wanted in hooks.get("request", [])


__all__ = ["KiteCallRefused", "is_guarded", "kite_async_client", "kite_client"]
