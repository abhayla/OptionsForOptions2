"""Zerodha (Kite Connect) login link and callback (W-058, REQ-015 AC-6, AC-9).

Spec basis: REQ-015 AC-6 ("The platform never asks for the user's Zerodha password, PIN or OTP; Zerodha authentication
happens on Zerodha's side and is separate from platform login."): neither route takes a password, PIN or OTP field;
the user logs in on Zerodha's own page. REQ-015 AC-9: the token is stored only as ciphertext (broker_token_store).

- ``GET /broker/zerodha/login``: 302 to Kite's login page, carrying a random single-use state (10-minute life, kept
  server-side, bound to the user).
- ``GET <path of KITE_REDIRECT_URL>`` (``/kite/callback``): consumes the state, checks Kite's answer, exchanges the
  request token, stores the access token encrypted, then 302 to a fixed frontend path with no token and no query.
  Every refusal is a fixed message keyed by a code (W-024's catalogue wires them later); nothing is stored.
- The state is bound to the browser that started the login: a short-lived HttpOnly, SameSite=Lax cookie (Secure when
  the redirect URL is https) set on the login route, required and matched on the callback (login CSRF).
- Kite's user_id must equal KITE_EXPECTED_USER_ID, else refused with nothing stored and the active session untouched
  (no account swap).
- At most MAX_LIVE_STATES unexpired states are held; over the cap the login is refused, never silently evicted.
- The query string of ANY access-log line whose query carries request_token, state or access_token is dropped
  (``CallbackQueryFilter``, key-based, any path).
- Stated limitation: the login must start on the same host as KITE_REDIRECT_URL (localhost vs 127.0.0.1 drops
  the cookie; the callback then fails closed).
- Stated limitation: states live in this process's memory, so with several workers (or after a restart) a callback
  that lands on another worker fails closed as "expired or already used". V1 runs one worker (ADR-051).

Copy from: legacy-reuse row 9 (algochanakya app/api/routes/auth.py:60-175, REFERENCE: the flow only; the legacy
stored the token in plaintext and echoed it to the frontend in the redirect URL).
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from urllib.parse import parse_qsl

from ofo.broker.kite_auth import KiteAuthPort, login_url
from ofo_app.broker_config import BrokerConfig
from ofo_app.broker_crypto import TokenCipher
from ofo_app.broker_token_store import store_session
from ofo_app.db import get_db
from ofo_app.kite_client import HttpKiteAuth, KiteExchangeError

log = logging.getLogger(__name__)

LOGIN_PATH = "/broker/zerodha/login"
#: Where the browser lands after a successful login: fixed, no token, no query.
CONNECTED_FRONTEND_PATH = "/broker/connected"
STATE_TTL_SECONDS = 600
#: Live login states held at once (the login route is anonymous); over it the login is refused.
MAX_LIVE_STATES = 20
STATE_COOKIE = "ofo_kite_login"
#: Query keys whose presence makes an access-log line drop its whole query string.
SECRET_QUERY_KEYS = frozenset({"request_token", "state", "access_token"})
#: ADR-051 V1 is single-user: the owner. Platform login replaces this dependency later.
V1_OWNER_REF = "owner"

#: Fixed refusal messages keyed by code (W-024's catalogue wires them later). Never echo Kite's text.
MESSAGES = {
    "broker_login_not_completed": "Zerodha login was not completed",
    "broker_state_invalid": "This Zerodha login link has expired or was already used. Start the login again.",
    "broker_login_busy": "Too many Zerodha logins are in progress. Wait a few minutes and start the login again.",
    "broker_user_mismatch": "This Zerodha account is not the one connected to this platform. Nothing was changed.",
    "kite_no_user_id": "Zerodha did not return a session. Start the login again.",
    "kite_token_exception": "Zerodha did not accept this login. Start the login again.",
    "kite_input_exception": "Zerodha did not accept this login. Start the login again.",
    "kite_no_access_token": "Zerodha did not return a session. Start the login again.",
    "kite_refused": "Zerodha did not accept this login. Start the login again.",
    "kite_unavailable": "Zerodha could not be reached. Nothing was saved; start the login again.",
    "broker_store_failed": "The Zerodha session could not be saved. Start the login again.",
}
_STATUS = {"kite_unavailable": 502, "broker_store_failed": 500, "broker_login_busy": 429, "broker_user_mismatch": 403}
_NO_LEAK_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class StateCapReached(Exception):
    """MAX_LIVE_STATES unexpired login states are already held."""


@dataclass
class StateStore:
    """Login states: random, single use, ``ttl`` seconds of life, at most ``cap`` live, kept in this process
    (ADR-051 V1, one worker). Each state is bound to a browser nonce (the login cookie). Keyed by state, in issue
    order, so purging expired states only looks at the oldest ones: ``ops`` counts the entries examined."""

    ttl: float = STATE_TTL_SECONDS
    cap: int = MAX_LIVE_STATES
    clock: Callable[[], float] = time.monotonic
    ops: int = 0
    _states: OrderedDict[str, tuple[str, float, str]] = field(default_factory=OrderedDict)

    def _purge(self, now: float) -> None:
        while self._states:
            self.ops += 1
            oldest = next(iter(self._states))
            if now - self._states[oldest][1] < self.ttl:
                return
            self._states.popitem(last=False)

    def issue(self, user_ref: str) -> tuple[str, str]:
        """Returns (state, browser nonce). Raises StateCapReached when ``cap`` live states are held."""
        now = self.clock()
        self._purge(now)
        if len(self._states) >= self.cap:
            raise StateCapReached()
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._states[state] = (user_ref, now, nonce)
        return state, nonce

    def consume(self, state: str | None, nonce: str | None) -> str | None:
        if not state:
            return None
        found = self._states.pop(state, None)  # single use: gone whatever happens next
        if found is None:
            return None
        user_ref, at, expected = found
        if not nonce or not secrets.compare_digest(nonce, expected):
            return None
        return user_ref if self.clock() - at < self.ttl else None


@dataclass
class BrokerRuntime:
    config: BrokerConfig
    cipher: TokenCipher
    states: StateStore


def runtime(request: Request) -> BrokerRuntime:
    return request.app.state.broker


def current_user_ref() -> str:
    return V1_OWNER_REF


async def get_kite_auth(request: Request) -> AsyncIterator[KiteAuthPort]:
    rt = runtime(request)
    async with httpx.AsyncClient() as client:
        yield HttpKiteAuth(rt.config.api_key, rt.config.api_secret.get_secret_value(), client)


def _refuse(code: str) -> JSONResponse:
    log.info("zerodha login refused: %s", code)  # the code only, never a token, checksum or Kite body
    return JSONResponse(status_code=_STATUS.get(code, 400), content={"code": code, "message": MESSAGES[code]},
                        headers=_NO_LEAK_HEADERS)


router = APIRouter()


@router.get(LOGIN_PATH)
async def zerodha_login(request: Request, user_ref: str = Depends(current_user_ref)) -> Response:
    rt = runtime(request)
    try:
        state, nonce = rt.states.issue(user_ref)
    except StateCapReached:
        return _refuse("broker_login_busy")
    response = RedirectResponse(login_url(rt.config.api_key, state), status_code=302, headers=_NO_LEAK_HEADERS)
    response.set_cookie(STATE_COOKIE, nonce, max_age=STATE_TTL_SECONDS, path=rt.config.callback_path, httponly=True,
                        secure=rt.config.redirect_url.startswith("https://"), samesite="lax")
    return response


async def kite_callback(
    request: Request,
    status: str | None = Query(default=None),
    request_token: str | None = Query(default=None),
    state: str | None = Query(default=None),
    kite: KiteAuthPort = Depends(get_kite_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    rt = runtime(request)
    user_ref = rt.states.consume(state, request.cookies.get(STATE_COOKIE))
    if user_ref is None:
        return _refuse("broker_state_invalid")
    if status != "success" or not request_token:
        return _refuse("broker_login_not_completed")
    try:
        session = await kite.exchange(request_token)
    except KiteExchangeError as exc:
        return _refuse(exc.code if exc.code in MESSAGES else "kite_refused")
    except Exception:  # noqa: BLE001 - fail closed, and never let an exception text near a log or the browser
        return _refuse("kite_unavailable")
    if not secrets.compare_digest(session.user_id, rt.config.expected_user_id):
        return _refuse("broker_user_mismatch")  # nothing stored; the active session is not replaced
    try:
        async with db.begin():
            await store_session(db, user_ref, session.access_token, rt.cipher)
    except Exception:  # noqa: BLE001 - any error between exchange and commit stores nothing
        return _refuse("broker_store_failed")
    finally:
        del session
    response = RedirectResponse(CONNECTED_FRONTEND_PATH, status_code=302, headers=_NO_LEAK_HEADERS)
    response.delete_cookie(STATE_COOKIE, path=rt.config.callback_path)
    return response


class CallbackQueryFilter(logging.Filter):
    """Drops the query string of any uvicorn access record whose query carries request_token, state or access_token,
    on any path (uvicorn logs ``'%s - "%s %s HTTP/%s" %d'`` with args (client, method, path-with-query, http version,
    status)). Key-based, so a trailing slash or a root_path prefix cannot route around it."""

    def __init__(self, paths: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.paths = paths  # kept for the record; matching is by query key, not by path

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            cleaned = tuple(self._strip(a) for a in args)
            if cleaned != args:
                record.args = cleaned
        return True

    def _strip(self, value: object) -> object:
        if isinstance(value, str) and "?" in value:
            path, query = value.split("?", 1)
            keys = {k.lower() for k, _ in parse_qsl(query, keep_blank_values=True)}
            if keys & SECRET_QUERY_KEYS or any(k in query.lower() for k in SECRET_QUERY_KEYS):
                return path
        return value


def install_access_log_filter(paths: tuple[str, ...]) -> CallbackQueryFilter:
    access = logging.getLogger("uvicorn.access")
    for existing in [f for f in access.filters if isinstance(f, CallbackQueryFilter)]:
        access.removeFilter(existing)
    flt = CallbackQueryFilter(paths)
    access.addFilter(flt)
    return flt


def mount(app: FastAPI, config: BrokerConfig) -> None:
    app.state.broker = BrokerRuntime(config=config, cipher=TokenCipher(config.token_key), states=StateStore())
    app.include_router(router)
    app.add_api_route(config.callback_path, kite_callback, methods=["GET"], include_in_schema=True)
    install_access_log_filter((config.callback_path,))
