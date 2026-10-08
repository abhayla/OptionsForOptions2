"""The Kite Connect login adapter port (W-058, REQ-015 AC-6, AC-9).

Spec basis: REQ-015 AC-6 ("The platform never asks for the user's Zerodha password, PIN or OTP; Zerodha authentication
happens on Zerodha's side and is separate from platform login."). The user logs in on Zerodha's own page; we only
build the link to it and exchange the request token Kite redirects back with.

Formats from the Kite Connect v3 docs (https://kite.trade/docs/connect/v3/user/): the login URL is
``https://kite.zerodha.com/connect/login?v=3&api_key=<key>``; an optional ``redirect_params`` value (a URL-encoded
query string) comes back unchanged on the redirect; the checksum is SHA-256 hex of api_key + request_token +
api_secret (proven live 2026-10-07 by docs/research/kite-proof-2026-10-07/kite_core_proof.py).

Copy from: legacy-reuse row 9 (algochanakya app/api/routes/auth.py:60-175, REFERENCE: the flow only).
"""

from __future__ import annotations

import hashlib
from typing import Protocol
from urllib.parse import urlencode

KITE_LOGIN_BASE = "https://kite.zerodha.com/connect/login"


def login_url(api_key: str, state: str) -> str:
    """Zerodha's own login page for our app, carrying ``state`` back to the callback through ``redirect_params``."""
    if not api_key or not state:
        raise ValueError("api_key and state are required")
    return KITE_LOGIN_BASE + "?" + urlencode(
        {"v": "3", "api_key": api_key, "redirect_params": urlencode({"state": state})})


def checksum(api_key: str, request_token: str, api_secret: str) -> str:
    """SHA-256 hex of api_key + request_token + api_secret (Kite's session token exchange)."""
    if not api_key or not request_token or not api_secret:
        raise ValueError("api_key, request_token and api_secret are required")
    return hashlib.sha256((api_key + request_token + api_secret).encode("utf-8")).hexdigest()


class KiteAuthPort(Protocol):
    """Exchanges a request token for an access token (POST /session/token). The app implements it; the api key and
    secret come from one credentials source behind the implementation (Q210 open; ADR-051 V1 uses the platform app)."""

    async def exchange(self, request_token: str) -> str: ...
