"""The shared Notifier client (ADR-286, REQ-115 AC-6, ADR-285 (1)): operational alerts for the platform owner only.

One POST to ``<NOTIFIER_URL>/notify`` with the key in ``X-Api-Key``. Never a user's data, an account figure, a position,
a symbol list or a token: callers pass fixed texts. The egress gate allows exactly this one address
(``ofo_app/__init__.py``). ``notify`` never raises: every answer state is a named result, and the log carries the state
and the exception type only, never the key.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
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


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes, timeout: float) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)  # noqa: S310 - scheme checked by notify
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status
    except HTTPError as exc:
        return exc.code


async def notify(severity: str, title: str, body: str, *, type: str, dedupe_key: str,  # noqa: PLR0913 - the Notifier's field names
                 transport: Transport = _urllib_transport) -> str:
    """Send one alert; the returned state is one of the module constants. A 3xx is not a 2xx: it is ``refused``."""
    cfg = get_settings()
    if not (cfg.NOTIFIER_URL and cfg.NOTIFIER_PROJECT and cfg.NOTIFIER_KEY):
        return NOT_CONFIGURED
    parts = urlsplit(cfg.NOTIFIER_URL)
    if not (parts.scheme == "https" or (parts.scheme == "http" and _loopback(parts.hostname or ""))):
        log.warning("alert not sent: %s", BAD_URL)
        return BAD_URL
    payload = json.dumps({"project": cfg.NOTIFIER_PROJECT, "severity": severity, "title": title, "body": body,
                          "type": type, "dedupeKey": dedupe_key}).encode("utf-8")
    headers = {"Content-Type": "application/json", "X-Api-Key": cfg.NOTIFIER_KEY}
    try:
        status = await asyncio.to_thread(transport, "POST", cfg.NOTIFIER_URL.rstrip("/") + "/notify", headers,
                                         payload, TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - never raises to the caller; the type only, the message may carry the URL
        log.warning("alert not sent: %s (%s)", UNREACHABLE, exc.__class__.__name__)  # type(): shadowed by the parameter
        return UNREACHABLE
    state = SENT if 200 <= status < 300 else SERVER_ERROR if status >= 500 else REFUSED  # noqa: PLR2004
    if state != SENT:
        log.warning("alert not sent: %s (HTTP %d)", state, status)
    return state

