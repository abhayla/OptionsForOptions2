"""The one door for error text at the API boundary (W-024 round 9 part 6; REQ-065 AC-1/AC-2, ADR-003 Q226).

Every error response body the API sends is built here, and only from a `render()` result:

- an `ofo.errors.UserFacing` exception carrying a `render()` message -> that message's parts (`as_dict()`), at the
  HTTP status of its error class (`STATUS_BY_CLASS`);
- a request the API cannot read (`RequestValidationError`) -> `user_input_request_invalid` (422);
- an HTTP error raised by the framework or a route: 401 -> `entitlement_access_sign_in_required`; 503 ->
  `internal_system_service_unavailable`; any other 4xx -> `user_input_request_not_available`; any other 5xx -> the
  internal message. The status is kept, and so are only the `Allow` (405) and `WWW-Authenticate` (401) headers; its
  `detail` is never shown or logged;
- ANY other exception -> `internal_system_request_failed` (500) with a fresh reference id; the exception goes only to
  the log, beside that reference; every log record of the process is redacted (ofo_app/redaction.py, round 10).

Logging (review MAJOR-3): never a request value. A validation error logs only each problem's `loc` and `type` (never
`input`, `ctx` or `msg`); every record of every logger is redacted where it is built (held values, keyed values, shapes).
Starlette's outermost middleware re-raises an exception after its handler ran ("allows servers to log the error"),
which would hand the raw traceback to the server's logger: `_Boundary`, an inner middleware, answers the exception
itself and never re-raises.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ofo.errors import CATALOGUE, ErrorClass, UserFacingError, render, user_message_of
from ofo_app.api_models import ApiModel
from ofo_app.redaction import install_redaction, keep_public_codes

keep_public_codes(frozenset(t.code for t in CATALOGUE.values()))  # codes are public: never redacted as a token shape

#: Zerodha's login page (Kite Connect v3), the only place a redirect may leave this site for. Equal to
#: ofo.broker.kite_auth.KITE_LOGIN_BASE (asserted by a test; this module does not import the Kite adapter).
KITE_LOGIN_PAGE = "https://kite.zerodha.com/connect/login"

log = logging.getLogger("ofo_app.main")

#: HTTP status per REQ-065 AC-1 class. Exhaustive (tests_app/test_error_boundary.py).
STATUS_BY_CLASS: dict[ErrorClass, int] = {
    ErrorClass.USER_INPUT: 422,
    ErrorClass.STRATEGY_VALIDATION: 422,
    ErrorClass.MARKET_DATA: 503,
    ErrorClass.BROKER_AUTHENTICATION: 401,
    ErrorClass.BROKER_ELIGIBILITY: 403,
    ErrorClass.MARGIN: 422,
    ErrorClass.ORDER_REJECTION: 422,
    ErrorClass.PARTIAL_EXECUTION: 409,
    ErrorClass.RECONCILIATION_MISMATCH: 409,
    ErrorClass.NOTIFICATION: 502,
    ErrorClass.ENTITLEMENT_ACCESS: 403,
    ErrorClass.INTERNAL_SYSTEM: 500,
}

#: Every 401 says how to authenticate (RFC 9110 11.6.1): a fixed scheme, never a secret or a request value.
WWW_AUTHENTICATE = 'Session realm="OptionsForOptions2"'


class Failure(Enum):
    """WHO failed, when it is not our code (W-058 fix round 1): the HTTP status and Retry-After of a user-facing error
    whose cause is our own capacity or an upstream service. Its error class still says what it is to the user; this
    only keeps such a failure from being answered as a 500 ("our bug")."""

    CAPACITY = (429, "60")  # our own cap (e.g. live Zerodha login states) is full
    UPSTREAM_BUSY = (503, "60")  # the upstream answered "too many requests"
    UPSTREAM_BAD_GATEWAY = (502, None)  # the upstream could not be reached, or answered junk
    NOT_FOUND = (404, None)  # W-061: a strategy or history entry that is not there (or is another user's)
    CONFLICT = (409, None)  # W-061: the change is based on a stale revision, or the saved form no longer reads

    def __init__(self, status: int, retry_after: str | None) -> None:
        self.status = status
        self.retry_after = retry_after


#: The only headers of an HTTP error that are passed on: the protocol needs them, and they hold no free text.
KEPT_HEADERS: frozenset[str] = frozenset({"allow", "www-authenticate"})


#: Sent on every error body (W-058 merge): an error answer is never cached, and the page it is shown on never sends
#: its address on (the Zerodha callback's address carries the single-use request token in its query).
NO_LEAK_HEADERS: Mapping[str, str] = MappingProxyType({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def _body(message: UserFacingError, status: int, headers: Mapping[str, str] | None = None) -> JSONResponse:
    extra = {"WWW-Authenticate": WWW_AUTHENTICATE} if status == 401 else {}
    return JSONResponse(status_code=status, content=message.as_dict(),
                        headers={**NO_LEAK_HEADERS, **extra, **(headers or {})})


def typed_response(model: ApiModel, status_code: int) -> JSONResponse:
    """A success body at a non-default status (e.g. /health's 503), built only from a typed `ApiModel`, whose fields
    cannot hold free text (ofo_app/api_models.py). One of the two other places a Response is constructed."""
    if not isinstance(model, ApiModel):
        raise TypeError(f"typed_response needs an ApiModel, got {type(model).__name__}")
    return JSONResponse(status_code=status_code, content=model.model_dump(mode="json"))


#: Characters that would end a Set-Cookie attribute or a header line, or turn a path into a different URL.
_COOKIE_BREAKERS = (";", chr(13), chr(10))
_LOCATION_BREAKERS = (chr(13), chr(10), chr(92))


@dataclass(frozen=True)
class RedirectCookie:
    """A cookie a redirect sets (``value`` given) or clears (``value`` None). Always HttpOnly and SameSite=Lax."""

    name: str
    path: str
    value: str | None = None
    max_age: int | None = None
    secure: bool = False

    def __post_init__(self) -> None:
        for part in (self.name, self.path, self.value or ""):
            if any(c in part for c in _COOKIE_BREAKERS):
                raise ValueError("a cookie name, path or value may not hold ';', CR or LF")


def _clear(response: JSONResponse | RedirectResponse, cookie: RedirectCookie) -> None:
    response.delete_cookie(cookie.name, path=cookie.path, secure=cookie.secure, httponly=True, samesite="lax")


def _is_kite_login_url(location: str) -> bool:
    """True only for the exact shape `login_url` builds: Zerodha's login page, query `v=3`, one `api_key`, and
    `redirect_params` holding one `state`; rebuilt from those parts, it is identical."""
    try:
        api_key, state = _kite_login_parts(location)
    except (KeyError, IndexError, ValueError):
        return False
    rebuilt = KITE_LOGIN_PAGE + "?" + urlencode({"v": "3", "api_key": api_key,
                                                  "redirect_params": urlencode({"state": state})})
    return bool(api_key and state) and rebuilt == location


def _kite_login_parts(location: str) -> tuple[str, str]:
    query = parse_qs(urlsplit(location).query, strict_parsing=True)
    (api_key,), (params,) = query["api_key"], query["redirect_params"]
    (state,) = parse_qs(params, strict_parsing=True)["state"]
    return api_key, state


def _check_location(location: str) -> None:
    if any(c in location for c in _LOCATION_BREAKERS):
        raise ValueError("a redirect location may not hold CR, LF or a backslash")
    if location.startswith("/") and not location.startswith("//"):
        return  # a path on this site
    if not _is_kite_login_url(location):
        raise ValueError("a redirect leaves this site only for the Zerodha login URL")


def typed_redirect(model: ApiModel, location: str, cookie: RedirectCookie | None = None) -> RedirectResponse:
    """A 302 with NO body (W-058: the Zerodha login link and the callback's landing): the route's declared typed
    `ApiModel` names which redirect it is, and the answer carries only the `Location`, the no-leak headers and at most
    one cookie. The other place a Response is constructed outside the error handlers; it holds no text a user reads."""
    if not isinstance(model, ApiModel):
        raise TypeError(f"typed_redirect needs an ApiModel, got {type(model).__name__}")
    _check_location(location)
    response = RedirectResponse(location, status_code=302, headers=dict(NO_LEAK_HEADERS))
    if cookie is not None and cookie.value is None:
        _clear(response, cookie)
    elif cookie is not None:
        response.set_cookie(cookie.name, cookie.value, max_age=cookie.max_age, path=cookie.path, httponly=True,
                            secure=cookie.secure, samesite="lax")
    return response


def _reference() -> str:
    return "ERR-" + secrets.token_hex(4).upper()


def _internal_response(exc: BaseException, request: Request) -> JSONResponse:
    reference = _reference()
    log.error("unhandled error %s on %s %s", reference, request.method, request.url.path, exc_info=exc)
    return _body(render("internal_system_request_failed", reference=reference), 500)


def _validation_problems(exc: RequestValidationError) -> list[tuple[tuple[object, ...], str]]:
    """Each problem's location and type only: `input`, `ctx` and `msg` can hold the request's values."""
    return [(tuple(e.get("loc", ())), str(e.get("type", ""))) for e in exc.errors()]


def _http_response(exc: StarletteHTTPException, request: Request) -> JSONResponse:
    status = exc.status_code
    log.info("http %s on %s %s", status, request.method, request.url.path)  # never `detail`
    headers = {k: v for k, v in (exc.headers or {}).items() if k.lower() in KEPT_HEADERS}
    if status == 401:
        return _body(render("entitlement_access_sign_in_required"), 401, headers)
    if status == 503:
        return _body(render("internal_system_service_unavailable"), 503, headers)
    if 400 <= status < 500:
        return _body(render("user_input_request_not_available"), status, headers)
    reference = _reference()
    log.error("http %s %s on %s %s", status, reference, request.method, request.url.path)
    return _body(render("internal_system_request_failed", reference=reference), status if status >= 500 else 500)


async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    """The single exception handler: registered for every exception type the framework routes to a handler."""
    message = user_message_of(exc)
    if message is not None:
        log.info("user-facing error %s on %s %s", message.code, request.method, request.url.path)
        failure = getattr(exc, "failure", None)
        if isinstance(failure, Failure):
            retry = {"Retry-After": failure.retry_after} if failure.retry_after else {}
            response = _body(message, failure.status, retry)
        else:
            response = _body(message, STATUS_BY_CLASS[message.error_class])
        clear = getattr(exc, "clear_cookie", None)
        if isinstance(clear, RedirectCookie):  # e.g. a refused Zerodha login drops its login-state cookie
            _clear(response, clear)
        return response
    if isinstance(exc, RequestValidationError):
        log.info("request not valid on %s %s: %s", request.method, request.url.path, _validation_problems(exc))
        return _body(render("user_input_request_invalid"), 422)
    if isinstance(exc, StarletteHTTPException):
        return _http_response(exc, request)
    return _internal_response(exc, request)


class _Boundary:
    """Inner ASGI middleware: an exception the framework's own middleware did not answer is answered here, through
    `handle_error`, and NOT re-raised, so no server logger ever receives the raw exception."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            response = await handle_error(Request(scope), exc)
            if not started:
                await response(scope, receive, send)


def install(app: FastAPI) -> None:
    """Route every error through `handle_error`: the framework's own HTTP and validation handlers are replaced too,
    so their default bodies (which echo `detail` and the request's values) never reach a user."""
    install_redaction()
    for exc_type in (Exception, StarletteHTTPException, RequestValidationError):
        app.add_exception_handler(exc_type, handle_error)
    app.add_middleware(_Boundary)
