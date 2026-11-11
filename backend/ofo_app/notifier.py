"""The shared Notifier client (ADR-286, REQ-115 AC-6, ADR-285 (1)): operational alerts for the platform owner only.

One POST to ``<NOTIFIER_URL>/notify`` with the key in ``X-Api-Key``. Never a user's data, an account figure, a position,
a symbol list or a token: callers pass fixed texts. The egress gate allows exactly this one address
(``ofo_app/__init__.py``). ``notify`` never raises: every answer state is a named result, every result but ``sent`` is
logged once with its state and reason, and the log carries the state and the exception type only, never the key.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import urllib.request
from collections.abc import Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit

from ofo_app.config import get_settings

log = logging.getLogger("ofo_app.notifier")

NOT_CONFIGURED, SENT, REFUSED, SERVER_ERROR, UNREACHABLE, BAD_URL = (
    "not configured", "sent", "refused", "server error", "unreachable", "bad url")
TIMEOUT_S = 5

Transport = Callable[[str, str, dict[str, str], bytes, float], int]  # method, url, headers, body, timeout -> status


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would be followed as a GET with the key header to an address the guard never saw: any 3xx is an
    answer, not a road."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes, timeout: float) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - scheme checked by notify
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def warn_if_guard_mismatch() -> None:
    """The outbound guard reads NOTIFIER_URL from the process environment at import; the settings may also read a
    ``.env`` file. A https address the guard does not hold would be refused on every send: say so once, at start."""
    url = get_settings().NOTIFIER_URL.strip()
    if url and not (urlsplit(url).scheme == "http" and _loopback(urlsplit(url).hostname or "")) \
            and os.environ.get("NOTIFIER_URL", "").strip() != url:
        log.warning("NOTIFIER_URL is set in the settings but not in the process environment (or is not https): the "
                    "outbound guard will refuse every alert")


def _not_sent(state: str, reason: str) -> str:
    log.warning("alert not sent: %s (%s)", state, reason)
    return state


def _type_name(exc: BaseException) -> str:
    return type(exc).__name__  # a helper because notify() has a parameter called type


async def notify(severity: str, title: str, body: str, *, type: str, dedupe_key: str,  # noqa: PLR0913 - the Notifier's field names
                 transport: Transport = _urllib_transport) -> str:
    """Send one alert; the returned state is one of the module constants. A 3xx is not a 2xx: it is ``refused``."""
    cfg = get_settings()
    key = cfg.NOTIFIER_KEY.get_secret_value()
    empty = [n for n, v in (("NOTIFIER_URL", cfg.NOTIFIER_URL), ("NOTIFIER_PROJECT", cfg.NOTIFIER_PROJECT),
                            ("NOTIFIER_KEY", key)) if not v]
    if empty:
        return _not_sent(NOT_CONFIGURED, "empty: " + ", ".join(empty))
    parts = urlsplit(cfg.NOTIFIER_URL)
    if not (parts.scheme == "https" or (parts.scheme == "http" and _loopback(parts.hostname or ""))):
        return _not_sent(BAD_URL, "not https and not loopback")
    payload = json.dumps({"project": cfg.NOTIFIER_PROJECT, "severity": severity, "title": title, "body": body,
                          "type": type, "dedupeKey": dedupe_key}).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Api-Key": key}
    try:
        status = await asyncio.to_thread(transport, "POST", cfg.NOTIFIER_URL.rstrip("/") + "/notify", headers,
                                         payload, TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - never raises to the caller; the type only, the message may carry the URL
        return _not_sent(UNREACHABLE, _type_name(exc))
    if 200 <= status < 300:  # noqa: PLR2004
        return SENT
    return _not_sent(SERVER_ERROR if status >= 500 else REFUSED, f"HTTP {status}")  # noqa: PLR2004
