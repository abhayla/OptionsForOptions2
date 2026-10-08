"""The Kite Connect token exchange over HTTP (W-058): implements ofo.broker.kite_auth.KiteAuthPort.

POST https://api.kite.trade/session/token with form fields api_key, request_token, checksum and header
``X-Kite-Version: 3`` (Kite Connect v3 docs, https://kite.trade/docs/connect/v3/user/; proven live 2026-10-07 by
docs/research/kite-proof-2026-10-07/kite_core_proof.py). Success: HTTP 200, ``{"status": "success", "data":
{"access_token": ...}}``. Errors: ``{"status": "error", "error_type": "TokenException" | "InputException" | ...}``.

Every answer state maps to one code (run-discipline B4 d); nothing about the answer body is ever logged or raised:
- 200 with data.access_token          -> the token
- 200 without an access token         -> KiteExchangeError("kite_no_access_token")
- 200 without a user_id               -> KiteExchangeError("kite_no_user_id")
- 429 (Kite rate limit)               -> KiteExchangeError("kite_busy")     (never "did not accept this login")
- 403 / TokenException                -> KiteExchangeError("kite_token_exception")   (expired or used request token)
- 400 / InputException                -> KiteExchangeError("kite_input_exception")   (bad checksum or input)
- any other 4xx                       -> KiteExchangeError("kite_refused")
- 5xx, timeout, network error, junk   -> KiteExchangeError("kite_unavailable")
No automatic retry: a request token is single use (ADR-016 spirit; no silent re-submission).
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from ofo.broker.kite_auth import KiteSession, checksum

log = logging.getLogger(__name__)

KITE_API_ROOT = "https://api.kite.trade"
SESSION_TOKEN_PATH = "/session/token"
EXCHANGE_TIMEOUT_SECONDS = 10.0


class KiteExchangeError(Exception):
    """A refused or failed exchange. Carries only a code; never the request token, checksum or response body."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class KiteTokenException(Exception):
    """Kite answered TokenException on an authenticated call: the access token no longer works."""


class _JsonAnswer(Protocol):
    """Kite's HTTP answer, as far as reading its error type needs (structural: any object with ``json()``)."""

    def json(self) -> object: ...


def _error_type(response: _JsonAnswer) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error_type") if isinstance(body, dict) else None


class HttpKiteAuth:
    def __init__(self, api_key: str, api_secret: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = client

    def __repr__(self) -> str:
        return f"HttpKiteAuth(api_key={self._api_key!r})"

    async def exchange(self, request_token: str) -> KiteSession:
        form = {"api_key": self._api_key, "request_token": request_token,
                "checksum": checksum(self._api_key, request_token, self._api_secret)}
        try:
            response = await self._client.post(KITE_API_ROOT + SESSION_TOKEN_PATH, data=form,
                                               headers={"X-Kite-Version": "3"}, timeout=EXCHANGE_TIMEOUT_SECONDS)
        except httpx.HTTPError:
            raise KiteExchangeError("kite_unavailable") from None
        finally:
            form.clear()
        status = response.status_code
        if status == 200:
            try:
                body = response.json()
            except ValueError:
                raise KiteExchangeError("kite_unavailable") from None
            data = body.get("data") if isinstance(body, dict) else None
            token = data.get("access_token") if isinstance(data, dict) else None
            if not isinstance(token, str) or not token or body.get("status") != "success":
                raise KiteExchangeError("kite_no_access_token")
            user_id = data.get("user_id")
            if not isinstance(user_id, str) or not user_id:
                raise KiteExchangeError("kite_no_user_id")
            return KiteSession(access_token=token, user_id=user_id)
        if status >= 500:
            raise KiteExchangeError("kite_unavailable")
        if status == 429:
            raise KiteExchangeError("kite_busy")
        error_type = _error_type(response)
        if status == 403 or error_type == "TokenException":
            raise KiteExchangeError("kite_token_exception")
        if status == 400 or error_type == "InputException":
            raise KiteExchangeError("kite_input_exception")
        raise KiteExchangeError("kite_refused")
