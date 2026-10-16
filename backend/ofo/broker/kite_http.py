"""The door every Kite HTTP request goes through (REQ-073 AC-4, ADR-054; run-discipline B8).

``check_call(method, url)`` refuses, BEFORE anything is sent, a request to Kite's API host whose (method, path) is not in
``ALLOWED_CALLS`` (path templates such as ``/instruments/historical/{token}/minute`` match as templates; nothing is
allowed by default). Any other Kite or Zerodha host is refused too: the backend calls only ``api.kite.trade``.

Two doors apply it: ``open_url`` here (stdlib ``urllib``, used by the instrument downloader and the history reader)
and the httpx client classes in ``ofo_app.kite_http`` (at their last hop). Only after the check passes does a door
open the runtime egress gate's door context (``ofo.broker.egress``), around the send alone; outside it every
non-loopback connect is refused. ``check_ws_url`` is the same rule
for the websocket door ``ofo_app.kite_ws``. This module is standard library only (the domain layer imports no HTTP
package); the hosts come from ``kite_endpoints`` (one constant per host).
"""  # noqa: E501
from __future__ import annotations

import re
import urllib.request as _urllib_request
from collections.abc import Mapping as _Mapping
from typing import Final as _Final
from urllib.parse import unquote as _unquote
from urllib.parse import urlsplit as _urlsplit

from ofo.broker import egress as _egress
from ofo.broker.kite_endpoints import ALLOWED_CALLS as _ALLOWED_CALLS
from ofo.broker.kite_endpoints import KITE_API_HOST, KITE_WS_HOST

_OTHER_KITE_SUFFIXES: _Final = ("kite.trade", "zerodha.com")
_PLAIN_NETLOC: _Final = re.compile(r"[A-Za-z0-9.-]+(:443)?", re.ASCII)
_PLAIN_WS_NETLOC: _Final = re.compile(r"[A-Za-z0-9.-]+(:[0-9]{1,5})?", re.ASCII)  # a local test fake carries a port


class KiteCallRefused(Exception):
    """A request to Kite that is not in the allow-list; it was not sent."""


def _template_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]*\})", template)
    return re.compile("".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts))


_ALLOWED: _Final = tuple((method, _template_regex(path))
                        for calls in _ALLOWED_CALLS.values() for method, path in sorted(calls))


def check_call(method: str, url: str) -> None:
    """Raise ``KiteCallRefused`` unless ``method url`` is allow-listed (or the host is not a Kite host)."""
    parts = _urlsplit(str(url))
    # Fail closed (B8): the address is read by this guard AND by urllib / http.client / httpx / ssl, and they differ on
    # percent-escapes (%2E), non-ASCII dots, userinfo, IPv6 brackets and backslashes. So only a plain netloc is
    # accepted: the RAW text must fully match, before any lowercasing or decoding. Nothing is converted or compared
    # otherwise (owner decisions 2026-10-16: refuse non-ASCII outright, then refuse everything but a-z 0-9 . -).
    if parts.scheme not in ("https", "http"):
        raise KiteCallRefused(f"{method}: only http(s) URLs are allowed; nothing was sent")
    if not _PLAIN_NETLOC.fullmatch(parts.netloc):
        raise KiteCallRefused(f"{method} {parts.netloc!r}: host has characters outside a-z 0-9 . - (or is empty); "
                              "nothing was sent")
    host = (parts.hostname or "").lower().rstrip(".")
    if host != KITE_API_HOST:
        if _is_kite_family(host):
            raise KiteCallRefused(f"{method} {host}: only {KITE_API_HOST} is called, and only allow-listed paths")
        return
    path = _unquote(parts.path)
    segments = path.split("/")[1:]
    if "" in segments or ".." in segments or "." in segments or not path.startswith("/"):
        raise KiteCallRefused(f"{method} {path!r}: not a plain path")
    verb = str(method).upper()
    if not any(m == verb and rx.fullmatch(path) for m, rx in _ALLOWED):
        raise KiteCallRefused(f"{verb} {path} is not an allow-listed Kite call; nothing was sent")


def _is_kite_family(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in _OTHER_KITE_SUFFIXES)


def check_ws_url(url: str) -> None:
    """Raise ``KiteCallRefused`` unless ``url`` is a plain websocket address; for any Kite or Zerodha host it must be
    exactly ``wss://ws.kite.trade`` (port absent or 443, path empty or ``/``). Same raw-netloc character rule as
    ``check_call``; a non-Kite host (a local fake in tests) is not this door's concern, as in ``check_call``."""
    parts = _urlsplit(str(url))
    if parts.scheme not in ("wss", "ws"):
        raise KiteCallRefused("only ws(s) URLs are opened by the Kite socket; nothing was opened")
    if not _PLAIN_WS_NETLOC.fullmatch(parts.netloc):
        raise KiteCallRefused(f"{parts.netloc!r}: host has characters outside a-z 0-9 . - (or is empty); "
                              "nothing was opened")
    host = (parts.hostname or "").lower().rstrip(".")
    if not _is_kite_family(host):
        return
    if parts.netloc not in (KITE_WS_HOST, KITE_WS_HOST + ":443") or parts.scheme != "wss" \
            or parts.path not in ("", "/"):
        raise KiteCallRefused(f"only wss://{KITE_WS_HOST} is opened for the Kite socket; nothing was opened")


class _NoRedirect(_urllib_request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect is an HTTPError: its target was never checked
        return None


#: this door's own opener (never the process-wide one, which caller code could have replaced), without redirects.
_OPENER: _Final = _urllib_request.build_opener(_NoRedirect)


def open_url(url: str, *, method: str = "GET", data: bytes | None = None,
             headers: _Mapping[str, str] | None = None, timeout: float = 20):
    """``urllib`` request through the door: checked first, then sent inside the egress gate's door context."""
    check_call(method, url)
    if not isinstance(data, (bytes, type(None))):
        raise KiteCallRefused(f"{method}: the body must be bytes; nothing was sent")
    request = _urllib_request.Request(url, data=data, headers=dict(headers or {}), method=method)  # noqa: S310
    with _egress._door():
        return _OPENER.open(request, timeout=timeout)  # host and path checked above; no redirect is followed


__all__ = ["KITE_API_HOST", "KITE_WS_HOST", "KiteCallRefused", "check_call", "check_ws_url", "open_url"]
