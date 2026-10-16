"""The door every Kite HTTP request goes through (REQ-073 AC-4, ADR-054; run-discipline B8).

``check_call(method, url)`` refuses, BEFORE anything is sent, a request to Kite's API host whose (method, path) is not in
``ALLOWED_CALLS`` (path templates such as ``/instruments/historical/{token}/minute`` match as templates; nothing is
allowed by default). Any other Kite or Zerodha host is refused too: the backend calls only ``api.kite.trade``.

Two doors apply it: ``open_url`` here (stdlib ``urllib``, used by the instrument downloader and the history reader)
and the httpx client factory ``ofo_app.kite_http`` (every httpx client the backend uses for Kite). This module is
standard library only (the domain layer imports no HTTP package).
"""
from __future__ import annotations

import re
import urllib.request
from collections.abc import Mapping
from typing import Final
from urllib.parse import unquote, urlsplit

from ofo.broker.kite_endpoints import ALLOWED_CALLS

KITE_API_HOST: Final = "api.kite.trade"
_OTHER_KITE_SUFFIXES: Final = ("kite.trade", "zerodha.com")
_PLAIN_NETLOC: Final = re.compile(r"[A-Za-z0-9.-]+(:443)?", re.ASCII)


class KiteCallRefused(Exception):
    """A request to Kite that is not in the allow-list; it was not sent."""


def _template_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]*\})", template)
    return re.compile("".join("[^/]+" if p.startswith("{") else re.escape(p) for p in parts))


_ALLOWED: Final = tuple((method, _template_regex(path))
                        for calls in ALLOWED_CALLS.values() for method, path in sorted(calls))


def check_call(method: str, url: str) -> None:
    """Raise ``KiteCallRefused`` unless ``method url`` is allow-listed (or the host is not a Kite host)."""
    parts = urlsplit(str(url))
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
        if any(host == s or host.endswith("." + s) for s in _OTHER_KITE_SUFFIXES):
            raise KiteCallRefused(f"{method} {host}: only {KITE_API_HOST} is called, and only allow-listed paths")
        return
    path = unquote(parts.path)
    segments = path.split("/")[1:]
    if "" in segments or ".." in segments or "." in segments or not path.startswith("/"):
        raise KiteCallRefused(f"{method} {path!r}: not a plain path")
    verb = str(method).upper()
    if not any(m == verb and rx.fullmatch(path) for m, rx in _ALLOWED):
        raise KiteCallRefused(f"{verb} {path} is not an allow-listed Kite call; nothing was sent")


def open_url(url: str, *, method: str = "GET", data: bytes | None = None,
             headers: Mapping[str, str] | None = None, timeout: float = 20):
    """``urllib`` request through the door: checked first, then ``urllib.request.urlopen``."""
    check_call(method, url)
    request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - host and path checked above


__all__ = ["KITE_API_HOST", "KiteCallRefused", "check_call", "open_url"]
