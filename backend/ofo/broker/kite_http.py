"""The door every Kite HTTP request goes through (REQ-073 AC-4, ADR-054; run-discipline B8).

``check_call(method, url)`` refuses, BEFORE anything is sent, a request to Kite's API host whose (method, path) is not in
``ALLOWED_CALLS`` (path templates such as ``/instruments/historical/{token}/minute`` match as templates; nothing is
allowed by default). Every other host is refused too (loopback only in the egress test mode): the backend calls only ``api.kite.trade``.

Two doors apply it: ``open_url`` here (stdlib ``urllib``, used by the instrument downloader and the history reader)
and the httpx client classes in ``ofo_app.kite_http`` (at their last hop). Only after the check passes does a door
open the runtime egress gate's door context (``ofo.broker.egress``), around the send alone; outside it every
non-loopback connect is refused. ``check_ws_url`` is the same rule
for the websocket door ``ofo_app.kite_ws``. This module is standard library only (the domain layer imports no HTTP
package); the hosts come from ``kite_endpoints`` (one constant per host).
"""  # noqa: E501
from __future__ import annotations

import ipaddress
import re
import urllib.request as _urllib_request
from collections.abc import Mapping as _Mapping
from typing import Final as _Final
from urllib.parse import unquote as _unquote
from urllib.parse import urlsplit as _urlsplit

from ofo.broker import egress as _egress
from ofo.broker.kite_endpoints import ALLOWED_CALLS as _ALLOWED_CALLS
from ofo.broker.kite_endpoints import KITE_API_HOST, KITE_WS_HOST

# W-080 round 9: the library frames a door's send runs through (urllib, http.client, ssl), trusted by the egress gate
_egress._trust_modules(_urllib_request, _urllib_request.http.client, _urllib_request.ssl, _egress)
# W-080 integration: any process that can reach Kite imports a door, so importing a door installs the gate (idempotent
# with create_app's install); a tool process that loads no door is not gated.
_egress.install()

_PLAIN_NETLOC: _Final = re.compile(r"[A-Za-z0-9.-]+(:443)?", re.ASCII)
#: One instrument as Kite's quote takes it: ``EXCHANGE:TRADINGSYMBOL``, plain ASCII only (W-099).
QUOTE_INSTRUMENT: _Final = r"[A-Z0-9_-]+:[A-Z0-9_-]+"
_BARE_TARGETS: _Final = frozenset({"/portfolio/holdings"})  # calls sent with no query, no fragment (W-106)
_QUOTE_TARGET: _Final = re.compile(rf"/quote(\?i={QUOTE_INSTRUMENT}(&i={QUOTE_INSTRUMENT})*)?", re.ASCII)
_PLAIN_WS_NETLOC: _Final = re.compile(r"[A-Za-z0-9.-]+(:[0-9]{1,5})?", re.ASCII)  # a local test fake carries a port


class KiteCallRefused(Exception):
    """A request to Kite that is not in the allow-list; it was not sent."""


def _template_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]*\})", template)
    return re.compile("".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts))


_ALLOWED: _Final = tuple((method, _template_regex(path))
                        for calls in _ALLOWED_CALLS.values() for method, path in sorted(calls))


def check_call(method: str, url: str) -> None:
    """Raise ``KiteCallRefused`` unless ``method url`` is allow-listed on Kite's API host (loopback only in test mode)."""
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
        if _loopback_test_host(host):
            return
        raise KiteCallRefused(f"{method} {host}: only {KITE_API_HOST} is called, and only allow-listed paths; "
                              "nothing was sent")
    path =_unquote(parts.path)
    segments = path.split("/")[1:]
    if "" in segments or ".." in segments or "." in segments or not path.startswith("/"):
        raise KiteCallRefused(f"{method} {path!r}: not a plain path")
    verb = str(method).upper()
    if not any(m == verb and rx.fullmatch(path) for m, rx in _ALLOWED):
        raise KiteCallRefused(f"{verb} {path} is not an allow-listed Kite call; nothing was sent")
    if path in _BARE_TARGETS and str(url).partition("//")[2][len(parts.netloc):] != path:
        raise KiteCallRefused(f"{verb} {path}: no query or fragment is sent on this call; nothing was sent")
    if path == "/quote":  # the one call with a query: the repeated ``i=`` and nothing else, judged on the RAW text
        target = str(url).partition("//")[2][len(parts.netloc):]
        if not _QUOTE_TARGET.fullmatch(target):
            raise KiteCallRefused(f"{verb} /quote: only repeated i=EXCHANGE:SYMBOL queries are sent; nothing was sent")


def _loopback_test_host(host: str) -> bool:
    """Loopback (a local fake) passes only while the egress test mode is on: the one switch, set by the test suites."""
    if not _egress._test_mode():
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_ws_url(url: str) -> None:
    """Raise ``KiteCallRefused`` unless ``url`` is a plain websocket address; it must be exactly
    ``wss://ws.kite.trade`` (port absent or 443, path empty or ``/``); any other host is refused, loopback only in
    test mode. Same raw-netloc character rule as ``check_call``."""
    parts = _urlsplit(str(url))
    if parts.scheme not in ("wss", "ws"):
        raise KiteCallRefused("only ws(s) URLs are opened by the Kite socket; nothing was opened")
    if not _PLAIN_WS_NETLOC.fullmatch(parts.netloc):
        raise KiteCallRefused(f"{parts.netloc!r}: host has characters outside a-z 0-9 . - (or is empty); "
                              "nothing was opened")
    host = (parts.hostname or "").lower().rstrip(".")
    if host != KITE_WS_HOST:
        if _loopback_test_host(host):
            return
        raise KiteCallRefused(f"{host}: only wss://{KITE_WS_HOST} is opened for the Kite socket; nothing was opened")
    if parts.netloc not in (KITE_WS_HOST, KITE_WS_HOST + ":443") or parts.scheme != "wss" \
            or parts.path not in ("", "/"):
        raise KiteCallRefused(f"only wss://{KITE_WS_HOST} is opened for the Kite socket; nothing was opened")


class _NoRedirect(_urllib_request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect is an HTTPError: its target was never checked
        return None


#: this door's own opener (never the process-wide one, which caller code could have replaced), without redirects and
#: without proxies (an environment proxy would be a second host, never checked).
_OPENER: _Final = _urllib_request.build_opener(_NoRedirect, _urllib_request.ProxyHandler({}))
#: the methods a door sends (W-080 round 9: plain data only, checked by exact type before the door opens)
METHODS: _Final = frozenset({"GET", "POST", "PUT", "DELETE"})


def plain_method(method: object) -> str:
    """The method as a plain ``str`` from ``METHODS``: another type (a ``str`` subclass included) is a TypeError,
    another method a ``KiteCallRefused``."""
    if type(method) is not str:
        raise TypeError("a Kite door takes the method as a plain str; nothing was sent")
    if method not in METHODS:
        raise KiteCallRefused(f"{method!r}: a Kite door sends only GET, POST, PUT or DELETE; nothing was sent")
    return method


def plain_str(value: object, what: str) -> str:
    if type(value) is not str:  # exact type: a subclass's methods would be caller code run by the libraries
        raise TypeError(f"a Kite door takes {what} as a plain str; nothing was sent")
    return value


def plain_headers(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    if type(headers) is not dict:
        raise TypeError("a Kite door takes headers as a plain dict of str to str; nothing was sent")
    if any(type(k) is not str or type(v) is not str for k, v in headers.items()):  # exact types, as plain_str
        raise TypeError("a Kite door takes header names and values as plain str; nothing was sent")
    return dict(headers)


def plain_timeout(timeout: object) -> float:
    if type(timeout) not in (int, float):
        raise TypeError("a Kite door takes the timeout as a number of seconds; nothing was sent")
    return float(timeout)  # type: ignore[arg-type]


def open_url(url: str, *, method: str = "GET", data: bytes | None = None,
             headers: _Mapping[str, str] | None = None, timeout: float = 20):
    """``urllib`` request through the door: plain data only (exact types, checked before anything else), then the
    URL check, then sent inside the egress gate's door permission. Nothing the caller passed runs inside it."""
    if type(url) is not str:  # exact type, as plain_str (whose label argument would be a sentence literal here)
        raise TypeError("a Kite door takes the URL as a plain str; nothing was sent")
    method = plain_method(method)
    plain = plain_headers(headers)
    seconds = plain_timeout(timeout)
    if data is not None and type(data) is not bytes:
        raise TypeError(f"{method}: the body must be bytes; nothing was sent")
    check_call(method, url)
    request = _urllib_request.Request(url, data=data, headers=plain, method=method)
    with _egress._door():
        return _OPENER.open(request, timeout=seconds)  # host and path checked above; no redirect is followed


__all__ = ["KITE_API_HOST", "KITE_WS_HOST", "METHODS", "QUOTE_INSTRUMENT", "KiteCallRefused", "check_call",
           "check_ws_url", "open_url", "plain_headers", "plain_method", "plain_str", "plain_timeout"]
