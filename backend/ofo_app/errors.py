"""The one door for error text at the API boundary (W-024 round 9 part 6; REQ-065 AC-1/AC-2, ADR-003 Q226).

Every error response body the API sends is built here, and only from a `render()` result:

- an `ofo.errors.UserFacing` exception carrying a `render()` message -> that message's parts (`as_dict()`), at the
  HTTP status of its error class (`STATUS_BY_CLASS`);
- a request the API cannot read (`RequestValidationError`) -> `user_input_request_invalid` (422);
- an HTTP error raised by the framework or a route: 401 -> `entitlement_access_sign_in_required`; 503 ->
  `internal_system_service_unavailable`; any other 4xx -> `user_input_request_not_available`; any other 5xx -> the
  internal message. The status is kept (a 4xx/5xx), and the exception's headers are NEVER copied: `Allow` (405) is
  re-minted from the method tokens it names, `WWW-Authenticate` (401) is the constant; its `detail` is never shown or
  logged;
- ANY other exception -> `internal_system_request_failed` (500) with a fresh reference id; the exception goes only to
  the log, beside that reference; every log record of the process is redacted (ofo_app/redaction.py, round 10).

Logging (review MAJOR-3): never a request value. A validation error logs only each problem's `loc` and `type` (never
`input`, `ctx` or `msg`); every record of every logger is redacted where it is built (held values, keyed values, shapes).
Starlette's outermost middleware re-raises an exception after its handler ran ("allows servers to log the error"),
which would hand the raw traceback to the server's logger: `_Boundary`, an inner middleware, answers the exception
itself and never re-raises.
"""

from __future__ import annotations

import functools
import inspect
import logging
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ofo.errors import CATALOGUE, ErrorClass, UserFacingError, render, user_message_of
from ofo_app.api_models import ApiModel, DoorRefused, Emitted, emit, emit_message
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


#: Sent on every error body (W-058 merge): an error answer is never cached, and the page it is shown on never sends
#: its address on (the Zerodha callback's address carries the single-use request token in its query).
NO_LEAK_HEADERS: Mapping[str, str] = MappingProxyType({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


#: The seal: `ClosedResponse` (and the sealed redirect) stamp it into the request scope when they are sent; `_Boundary`
#: lets a response start only when it is there. Nothing else in the app has it, so a raw Response, a mounted app or a
#: framework default fails closed (W-069, issue #148).
DOOR_KEY = "ofo.door"
_SEAL = object()


#: Headers a door response may carry: the body's own two, the no-leak pair, and the protocol ones an error keeps.
_DOOR_HEADERS = frozenset({"content-length", "content-type", "cache-control", "referrer-policy", "www-authenticate",
                           "retry-after", "allow", "set-cookie", "location"})
_REDIRECT_MINT = object()

#: The HTTP methods an `Allow` header may name (RFC 9110): the only words an exception's `Allow` can contribute.
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_DIGITS = re.compile(r"[0-9]{1,6}")


def _mint_headers(*, body_length: int, content_type: bool, status: int, retry_after: str | None = None,
                  allow: tuple[str, ...] | None = None, cookie: RedirectCookie | None = None,
                  location: str | None = None) -> list[tuple[bytes, bytes]]:
    """THE closed header table (W-070). Every header a door response carries is written here from a constant, a number
    the door computed, a closed token set or a `RedirectCookie`; no caller value is copied. Raises `DoorRefused`."""
    headers = [(b"content-length", str(body_length).encode("ascii"))]
    if content_type:
        headers.append((b"content-type", b"application/json"))
    headers += [(name.lower().encode("ascii"), value.encode("ascii")) for name, value in NO_LEAK_HEADERS.items()]
    if status == 401:
        headers.append((b"www-authenticate", WWW_AUTHENTICATE.encode("latin-1")))
    if retry_after is not None:
        if type(retry_after) is not str or _DIGITS.fullmatch(retry_after) is None:
            raise DoorRefused("a door Retry-After is digits only")
        headers.append((b"retry-after", retry_after.encode("ascii")))
    if allow:
        if not all(type(m) is str and m in _METHODS for m in allow):
            raise DoorRefused("a door Allow names only HTTP methods")
        headers.append((b"allow", ", ".join(sorted(set(allow))).encode("ascii")))
    if cookie is not None:
        if type(cookie) is not RedirectCookie:
            raise DoorRefused("a door cookie is a RedirectCookie")
        headers.append((b"set-cookie", _cookie_header(cookie)))
    if location is not None:
        headers.append((b"location", location.encode("latin-1")))
    return headers


def _door_status_ok(status: object) -> bool:
    """An answer with a body: 2xx-5xx, never a redirect, 204 or 304 (those carry no body, or point elsewhere)."""
    return type(status) is int and 200 <= status <= 599 and not (300 <= status < 400) and status != 204


def _freeze(response: Response) -> None:
    response._frozen = (response.status_code, tuple(response.raw_headers), response.body)  # type: ignore[attr-defined]


def _verify(response: object) -> None:
    """THE check, a module function (an instance cannot shadow it): the response is exactly the frozen
    (status, headers, body) the door minted at construction, with no background task, and meets its type's rules."""
    kind = type(response)
    if kind not in _DOOR_TYPES:
        raise DoorRefused("not a door response")
    frozen = getattr(response, "_frozen", None)
    if type(frozen) is not tuple or len(frozen) != 3:
        raise DoorRefused("a door response was never frozen")
    status, headers, body = frozen
    raw = response.raw_headers  # type: ignore[attr-defined]
    if type(raw) is not list or not all(type(p) is tuple and len(p) == 2 and type(p[0]) is bytes and type(p[1]) is bytes
                                        for p in raw):
        raise DoorRefused("a door response header list was replaced")
    if (response.status_code != status or type(response.status_code) is not int  # type: ignore[attr-defined]
            or tuple(raw) != headers or response.body is not body  # type: ignore[attr-defined]
            or response.background is not None):  # type: ignore[attr-defined]
        raise DoorRefused("a door response was changed after it was made")
    names = {k.decode("latin-1") for k, _ in headers}
    if not names <= _DOOR_HEADERS:
        raise DoorRefused("a door response carries a header the door does not write")
    if kind is ClosedResponse:
        if type(body) is not Emitted or not _door_status_ok(status) or "location" in names:
            raise DoorRefused("a door response is not a body-carrying answer written by emit")
        return
    values = dict(headers)
    if status != 302 or type(body) is not bytes or body != b"" or b"location" not in values:
        raise DoorRefused("a sealed redirect was changed after it was made")
    try:
        _check_location(values[b"location"].decode("latin-1"))
    except ValueError:
        raise DoorRefused("a sealed redirect points outside this site and the Zerodha login page") from None


async def _send_frozen(response: Response, scope: Scope, send: Send) -> None:
    """Verify, seal, and send the FROZEN copy from here: not Starlette's `__call__`, which reads the live attributes at
    send time and runs `background`."""
    _verify(response)
    if scope["type"] != "http":
        raise DoorRefused("a door response is sent over http only")
    status, headers, body = response._frozen  # type: ignore[attr-defined]
    scope[DOOR_KEY] = _SEAL
    await send({"type": "http.response.start", "status": status, "headers": list(headers)})
    await send({"type": "http.response.body", "body": bytes(body)})


class ClosedResponse(Response):
    """A JSON response whose body is `Emitted` bytes (made only by `ofo_app.api_models.emit`) and which seals the request
    when it is sent. The one response type the API writes a body with. Not subclassable. Its status, every header (name
    AND value, from `_mint_headers`) and body are minted here and frozen; `_verify` runs at the route wrapper and at
    the seal and the frozen copy is what is sent, so nothing set afterwards (or at construction, by a caller) reaches
    the wire. No caller headers: a `Retry-After`, an `Allow` or a cookie is a typed argument."""

    media_type = "application/json"

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ClosedResponse is not subclassed")

    def __init__(self, body: Emitted, status_code: int = 200, *, retry_after: str | None = None,
                 allow: tuple[str, ...] | None = None, cookie: RedirectCookie | None = None) -> None:
        if type(body) is not Emitted:
            raise TypeError(f"a ClosedResponse body is made by emit(), not {type(body).__name__}")
        if not _door_status_ok(status_code):
            raise DoorRefused("a ClosedResponse carries a body: 2xx-5xx, not a redirect, 204 or 304")
        super().__init__(content=body, status_code=status_code)
        self.raw_headers[:] = _mint_headers(body_length=len(body), content_type=True, status=status_code,
                                            retry_after=retry_after, allow=allow, cookie=cookie)
        _freeze(self)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await _send_frozen(self, scope, send)


class SealedRedirect(RedirectResponse):
    """A body-less 302 that seals the request when it is sent. Made only by `typed_redirect` (a mint token, so no
    route can point one at an outside host); its Location is checked again when it is verified and sent. Its headers,
    cookie included, are minted in the constructor and frozen like `ClosedResponse`'s."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("SealedRedirect is not subclassed")

    def __init__(self, location: str, cookie: RedirectCookie | None = None, *, _mint: object = None) -> None:
        if _mint is not _REDIRECT_MINT:
            raise TypeError("a SealedRedirect is made only by typed_redirect")
        super().__init__(location, status_code=302)
        self.raw_headers[:] = _mint_headers(body_length=0, content_type=False, status=302, cookie=cookie,
                                            location=self.headers["location"])
        _freeze(self)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await _send_frozen(self, scope, send)


_DOOR_TYPES = (ClosedResponse, SealedRedirect)


def _body(message: UserFacingError, status: int, *, retry_after: str | None = None,
          allow: tuple[str, ...] | None = None, cookie: RedirectCookie | None = None) -> ClosedResponse:
    return ClosedResponse(emit_message(message), status, retry_after=retry_after, allow=allow, cookie=cookie)


def respond(model: ApiModel, status_code: int) -> ClosedResponse:
    """A success body at a non-default status (e.g. /health's 503), written by the door from a typed `ApiModel`."""
    return ClosedResponse(emit(model), status_code)


def _through_the_door(endpoint: Callable[..., object], holder: list[ClosedRoute]) -> Callable[..., object]:
    """The endpoint, wrapped so its result is a sealed door response: an instance of EXACTLY the route's response model
    is written by `emit`; a sealed door response passes; anything else (a dict, a raw Response, a subclass) is refused.
    Async exactly when the endpoint is: FastAPI decides how to call it from the unwrapped function."""

    def convert(result: object) -> object:
        route = holder[0]
        if type(result) in _DOOR_TYPES:
            _verify(result)
            return result
        if route.response_model is not None and type(result) is route.response_model:
            return ClosedResponse(emit(result, exclude_unset=route.response_model_exclude_unset),  # type: ignore[arg-type]
                                  route.status_code or 200)
        raise DoorRefused(f"{route.path}: the route returned {type(result).__name__}, not exactly its response model")

    if inspect.iscoroutinefunction(endpoint):
        @functools.wraps(endpoint)
        async def wrapper(*args: object, **kwargs: object) -> object:
            return convert(await endpoint(*args, **kwargs))
    else:
        @functools.wraps(endpoint)
        def wrapper(*args: object, **kwargs: object) -> object:  # type: ignore[misc]
            return convert(endpoint(*args, **kwargs))
    wrapper.ofo_door = True  # type: ignore[attr-defined]
    return wrapper


class ClosedRoute(APIRoute):
    """The only route class of the API: its endpoint's result goes through `emit` (see `_through_the_door`)."""

    def __init__(self, path: str, endpoint: Callable[..., object], **kwargs: object) -> None:
        holder: list[ClosedRoute] = []
        super().__init__(path, _through_the_door(endpoint, holder), **kwargs)  # type: ignore[arg-type]
        holder.append(self)


_LOCATION_BREAKERS = (chr(13), chr(10), chr(92))

#: A cookie is built only from token-shaped parts (RFC 6265): the nonce is urlsafe base64, the path a URL path.
_COOKIE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_COOKIE_VALUE = re.compile(r"[A-Za-z0-9_.~-]{0,128}")
_COOKIE_PATH = re.compile(r"/[A-Za-z0-9/_.~-]{0,128}")


@dataclass(frozen=True)
class RedirectCookie:
    """A cookie a door response sets (``value`` given) or clears (``value`` None). Always HttpOnly and SameSite=Lax. Name,
    value and path match a token pattern, so none can hold ';', CR, LF, a space or a sentence."""

    name: str
    path: str
    value: str | None = None
    max_age: int | None = None
    secure: bool = False

    def __post_init__(self) -> None:
        if not (type(self.name) is str and _COOKIE_NAME.fullmatch(self.name)
                and type(self.path) is str and _COOKIE_PATH.fullmatch(self.path)
                and (self.value is None or (type(self.value) is str and _COOKIE_VALUE.fullmatch(self.value)))):
            raise ValueError("a cookie name, path and value must match the token patterns")
        if self.max_age is not None and (type(self.max_age) is not int or self.max_age < 0):
            raise ValueError("a cookie max_age is a non-negative integer")
        if type(self.secure) is not bool:
            raise ValueError("a cookie secure flag is a bool")


def _cookie_header(cookie: RedirectCookie) -> bytes:
    """The Set-Cookie value, written by Starlette's own formatter on a scratch response (so it is byte-for-byte what
    `set_cookie`/`delete_cookie` wrote before W-070) and read back; the scratch response is never sent."""
    scratch = Response()
    if cookie.value is None:
        scratch.delete_cookie(cookie.name, path=cookie.path, secure=cookie.secure, httponly=True, samesite="lax")
    else:
        scratch.set_cookie(cookie.name, cookie.value, max_age=cookie.max_age, path=cookie.path, httponly=True,
                           secure=cookie.secure, samesite="lax")
    return next(value for name, value in scratch.raw_headers if name == b"set-cookie")


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


def typed_redirect(model: ApiModel, location: str, cookie: RedirectCookie | None = None) -> SealedRedirect:
    """A 302 with NO body (W-058: the Zerodha login link and the callback's landing): the route's declared typed
    `ApiModel` names which redirect it is, and the answer carries only the `Location`, the no-leak headers and at most
    one cookie. The other place a Response is constructed outside the error handlers; it holds no text a user reads."""
    if not isinstance(model, ApiModel):
        raise TypeError(f"typed_redirect needs an ApiModel, got {type(model).__name__}")
    _check_location(location)
    return SealedRedirect(location, cookie, _mint=_REDIRECT_MINT)  # the cookie goes into the constructor, not after


def _reference() -> str:
    return "ERR-" + secrets.token_hex(4).upper()


def _internal_response(exc: BaseException, request: Request) -> ClosedResponse:
    reference = _reference()
    log.error("unhandled error %s on %s %s", reference, request.method, request.url.path, exc_info=exc)
    return _body(render("internal_system_request_failed", reference=reference), 500)


def _validation_problems(exc: RequestValidationError) -> list[tuple[tuple[object, ...], str]]:
    """Each problem's location and type only: `input`, `ctx` and `msg` can hold the request's values."""
    return [(tuple(e.get("loc", ())), str(e.get("type", ""))) for e in exc.errors()]


def _http_response(exc: StarletteHTTPException, request: Request) -> ClosedResponse:
    status = exc.status_code
    log.info("http %s on %s %s", status, request.method, request.url.path)  # never `detail`
    if status == 401:  # the WWW-Authenticate value is the constant, minted by the door; the exception's is discarded
        return _body(render("entitlement_access_sign_in_required"), 401)
    if status == 503:
        return _body(render("internal_system_service_unavailable"), 503)
    if 400 <= status < 500:
        allow = _allowed_methods(exc) if status == 405 else None
        return _body(render("user_input_request_not_available"), status, allow=allow)
    reference = _reference()
    log.error("http %s %s on %s %s", status, reference, request.method, request.url.path)
    return _body(render("internal_system_request_failed", reference=reference), status if 500 <= status <= 599 else 500)


def _allowed_methods(exc: StarletteHTTPException) -> tuple[str, ...] | None:
    """The method tokens (from the closed method set) the exception's `Allow` names; any other word is dropped, so a
    sentence there contributes nothing and the header is left out."""
    given = next((v for k, v in (exc.headers or {}).items() if k.lower() == "allow"), "")
    tokens = tuple(t for t in (p.strip() for p in given.split(",")) if t in _METHODS) if type(given) is str else ()
    return tokens or None


async def handle_error(request: Request, exc: Exception) -> ClosedResponse:
    """The single exception handler: registered for every exception type the framework routes to a handler."""
    message = user_message_of(exc)
    if message is not None:
        log.info("user-facing error %s on %s %s", message.code, request.method, request.url.path)
        failure = getattr(exc, "failure", None)
        clear = getattr(exc, "clear_cookie", None)  # e.g. a refused Zerodha login drops its login-state cookie
        cookie = replace(clear, value=None, max_age=None) if isinstance(clear, RedirectCookie) else None
        if isinstance(failure, Failure):
            return _body(message, failure.status, retry_after=failure.retry_after, cookie=cookie)
        return _body(message, STATUS_BY_CLASS[message.error_class], cookie=cookie)
    if isinstance(exc, RequestValidationError):
        log.info("request not valid on %s %s: %s", request.method, request.url.path, _validation_problems(exc))
        return _body(render("user_input_request_invalid"), 422)
    if isinstance(exc, StarletteHTTPException):
        return _http_response(exc, request)
    return _internal_response(exc, request)


#: The outcome route predates the door (plain `str` fields built in the domain, instrument ids with ':'): exempt by exact
#: method and path until W-066 (issue #172) moves it onto the door and deletes this entry. Nothing else is exempt but
#: the framework docs pages, and those only where `main.create_app` mounts them (ADR-073).
OUTCOME_EXEMPTION = ("POST", "/api/strategies/outcome")


class _Boundary:
    """Inner ASGI middleware: an exception the framework's own middleware did not answer is answered here, through
    `handle_error`, and NOT re-raised, so no server logger ever receives the raw exception.

    It is also the door's last guard (W-069): a response may start only if the request was sealed by a `ClosedResponse`
    or a sealed redirect; anything else (a raw Response, a mounted app, a framework default) is dropped, whole, and
    answered with the internal-system message. `exempt` is a set of exact (method, path) pairs."""

    def __init__(self, app: ASGIApp, exempt: frozenset[tuple[str, str]] = frozenset()) -> None:
        self.app = app
        self.exempt = exempt

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        exempt = (scope["method"], scope["path"]) in self.exempt
        started = False
        refused = False

        async def tracking_send(message: Message) -> None:
            nonlocal started, refused
            if refused:
                return
            if message["type"] == "http.response.start":
                if not exempt and scope.get(DOOR_KEY) is not _SEAL:
                    refused = True
                    log.error("response door: an unsealed response was dropped on %s %s", scope["method"], scope["path"])
                    return
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            response = await handle_error(Request(scope), exc)
            if not started:
                await response(scope, receive, send)
            return
        if refused:
            response = _internal_response(DoorRefused("an unsealed response left the app"), Request(scope))
            await response(scope, receive, send)


def install(app: FastAPI) -> None:
    """Route every error through `handle_error`: the framework's own HTTP and validation handlers are replaced too,
    so their default bodies (which echo `detail` and the request's values) never reach a user."""
    install_redaction()
    for exc_type in (Exception, StarletteHTTPException, RequestValidationError):
        app.add_exception_handler(exc_type, handle_error)
    docs = {("GET", url) for url in (app.docs_url, app.redoc_url, app.openapi_url,
                                      app.swagger_ui_oauth2_redirect_url if app.docs_url else None) if url}
    app.add_middleware(_Boundary, exempt=frozenset(docs | {OUTCOME_EXEMPTION}))
