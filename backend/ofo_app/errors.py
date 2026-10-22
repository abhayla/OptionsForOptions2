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

import contextlib
import json

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ofo.errors import CATALOGUE, ErrorClass, UserFacingError, render, user_message_of
from ofo_app.api_models import ApiModel, DoorRefused, Emitted, emit, emit_message
from ofo_app.broker_config import validate_frontend_origin
from ofo_app.redaction import install_redaction, keep_public_codes
from ofo_app.underlying import refusal_of

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


#: The seal: `ClosedResponse` (and the sealed redirect) stamp a `_SEAL` record of the exact messages they send into the
#: request scope, in their own send path (#200 N5); `_Boundary` lets a response start only when its messages are those.
#: Nothing else in the app has it, so a raw Response, a mounted app or a framework default fails closed (W-069, #148).
DOOR_KEY = "ofo.door"


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
        try:
            _check_location(location)
            headers.append((b"location", location.encode("ascii")))
        except ValueError:
            raise DoorRefused("a door Location is a site path from the allow-list or the Zerodha login URL") from None
    return headers


def _door_status_ok(status: object) -> bool:
    """An answer with a body: 2xx-5xx, never a redirect, 204 or 304 (those carry no body, or point elsewhere)."""
    return type(status) is int and 200 <= status <= 599 and not (300 <= status < 400) and status != 204


_NO_SOURCE = object()


def _freeze(response: Response, source: object = _NO_SOURCE, exclude_unset: bool = False) -> None:
    """Record (status, headers, body, source, exclude_unset). The source is the model (or message) the body was minted
    from; a re-freeze without one keeps the source already recorded, so a body can be re-frozen but never re-sourced."""
    if source is _NO_SOURCE:
        old = getattr(response, "_frozen", None)
        source, exclude_unset = (old[3], old[4]) if type(old) is tuple and len(old) == 5 else (None, False)
    response._frozen = (response.status_code, tuple(response.raw_headers), response.body,  # type: ignore[attr-defined]
                        source, exclude_unset)


def _mint_body(source: object, exclude_unset: bool) -> Emitted:
    """THE only way a door body is made: from a model (`emit`) or a catalogue message (`emit_message`). Used by the
    constructor and again by `_verify`, so the body is a pure function of the stored source."""
    if isinstance(source, ApiModel):
        return emit(source, exclude_unset)
    if type(source) is UserFacingError:
        return emit_message(source)
    raise DoorRefused(f"a door body is made from an ApiModel or a catalogue message, not {type(source).__name__}")


def _verify(response: object) -> None:
    """THE check, a module function (an instance cannot shadow it): the response is exactly the frozen
    (status, headers, body) the door minted at construction, with no background task, and meets its type's rules."""
    kind = type(response)
    if kind not in _DOOR_TYPES:
        raise DoorRefused("not a door response")
    frozen = getattr(response, "_frozen", None)
    if type(frozen) is not tuple or len(frozen) != 5:
        raise DoorRefused("a door response was never frozen")
    status, headers, body, source, exclude_unset = frozen
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
        if type(exclude_unset) is not bool or not (isinstance(source, ApiModel) or type(source) is UserFacingError):
            raise DoorRefused("a door response was not minted from a model or a catalogue message")
        # Mint the body again from the stored source and demand the same bytes, in the frozen copy AND the live body: a
        # body that is not the pure output of `emit` for its source (however it was made or rewritten) cannot pass.
        expected = _mint_body(source, exclude_unset)
        if bytes.__eq__(expected, body) is not True or bytes.__eq__(expected, response.body) is not True:  # type: ignore[attr-defined]
            raise DoorRefused("a door response body is not the one its model emits")
    elif (status != 302 or type(body) is not bytes or body != b"" or b"location" not in dict(headers)
          or source is not None):
        raise DoorRefused("a sealed redirect was changed after it was made")
    _check_record_values(kind, status, headers, body)


class _SEAL:  # noqa: N801 - the door's private seal record; the name is on the CI scan's door-name list
    """The seal (#200 N5): the very start and body MESSAGES the door is sending, with immutable copies of their parts.
    `_Boundary` lets a start through only when it IS the recorded start message and still equals the copy, and then only
    the recorded body message, unchanged. A response called with a send that goes nowhere records messages that never
    reach the boundary, so raw bytes written afterwards carry no seal; a send wrapper that edits or swaps the door's
    message in transit fails the comparison. Not subclassable."""

    __slots__ = ("start", "body", "status", "headers", "payload")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("the seal is not subclassed")

    def __init__(self, status: int, headers: tuple[tuple[bytes, bytes], ...], payload: bytes) -> None:
        self.status, self.headers, self.payload = status, headers, payload
        self.start = {"type": "http.response.start", "status": status, "headers": list(headers)}
        self.body = {"type": "http.response.body", "body": payload}

    def is_start(self, message: object) -> bool:
        return message is self.start and message == {"type": "http.response.start", "status": self.status,
                                                     "headers": list(self.headers)}

    def is_body(self, message: object) -> bool:
        return message is self.body and message == {"type": "http.response.body", "body": self.payload}


async def _send_frozen(response: Response, scope: Scope, send: Send) -> None:
    """Verify, seal, and send the FROZEN copy from here: not Starlette's `__call__`, which reads the live attributes at
    send time and runs `background`. The seal records the exact messages handed to `send` (#200 N5), set here in the
    send path, so it vouches only for the response that is really sent."""
    _verify(response)
    if scope["type"] != "http":
        raise DoorRefused("a door response is sent over http only")
    status, headers, body = response._frozen[:3]  # type: ignore[attr-defined]
    seal = _SEAL(status, tuple(headers), bytes(body))
    scope[DOOR_KEY] = seal
    await send(seal.start)
    await send(seal.body)


class ClosedResponse(Response):
    """A JSON response whose body the door MINTS from its SOURCE (round 6): an `ApiModel` (written by `emit`) or a
    catalogue `UserFacingError` (written by `emit_message`). The constructor takes no bytes at all, so there is no
    ready-made body to forge; it keeps the source, and `_verify` re-emits from it and demands the same bytes. It seals
    the request when it is sent. Not subclassable. Its status, every header (name AND value, from `_mint_headers`),
    body and source are frozen; `_verify` runs at the route wrapper and at the seal and the frozen copy is what is
    sent. No caller headers: a `Retry-After`, an `Allow` or a cookie is a typed argument."""

    media_type = "application/json"

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ClosedResponse is not subclassed")

    def __init__(self, source: ApiModel | UserFacingError, status_code: int = 200, *, exclude_unset: bool = False,
                 retry_after: str | None = None, allow: tuple[str, ...] | None = None,
                 cookie: RedirectCookie | None = None) -> None:
        if isinstance(source, (bytes, bytearray, memoryview)):
            raise TypeError("a ClosedResponse is made from a model or a message, never from a ready-made body")
        if not _door_status_ok(status_code):
            raise DoorRefused("a ClosedResponse carries a body: 2xx-5xx, not a redirect, 204 or 304")
        if type(exclude_unset) is not bool:
            raise TypeError("exclude_unset is a bool")
        body = _mint_body(source, exclude_unset)
        super().__init__(content=body, status_code=status_code)
        self.raw_headers[:] = _mint_headers(body_length=len(body), content_type=True, status=status_code,
                                            retry_after=retry_after, allow=allow, cookie=cookie)
        _freeze(self, source, exclude_unset)

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
    return ClosedResponse(message, status, retry_after=retry_after, allow=allow, cookie=cookie)


def respond(model: ApiModel, status_code: int) -> ClosedResponse:
    """A success body at a non-default status (e.g. /health's 503), written by the door from a typed `ApiModel`."""
    return ClosedResponse(model, status_code)


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
            return ClosedResponse(result, route.status_code or 200,  # type: ignore[arg-type]
                                  exclude_unset=route.response_model_exclude_unset)
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


def add_socket_route(app: FastAPI, route: ClosedWebSocketRoute) -> None:
    """Adds a door socket route to the app's own table, exactly as built (``include_router`` would rebuild it as a plain
    APIWebSocketRoute, off the door). Anything but a ClosedWebSocketRoute is refused."""
    if type(route) is not ClosedWebSocketRoute:
        raise DoorRefused("a socket route is a ClosedWebSocketRoute")
    app.router.routes.append(route)


# --- the socket door (W-065): a WebSocket route whose every message is minted by `emit` ---------------------------------

#: The largest client message a door socket reads; a bigger one is answered as a request the API cannot read.
SOCKET_MAX_MESSAGE = 65536


class SocketClosed(Exception):
    """The client's WebSocket connection ended."""


class _Unreadable:
    """A client message the socket could not read (not text, not JSON, too long): the endpoint answers it as invalid."""


UNREADABLE = _Unreadable()


def socket_body(source: object, message_models: tuple[type, ...]) -> Emitted:
    """THE only way a door socket message is made: an instance of EXACTLY one of the route's declared message models,
    written by `emit` (exclude_unset, like the REST routes), or a catalogue `UserFacingError` written by `emit_message`.
    Anything else (a dict, a subclass, free text, bytes) raises `DoorRefused`."""
    if type(source) is UserFacingError:
        return emit_message(source)
    if type(source) in message_models and isinstance(source, ApiModel):
        return emit(source, True)
    raise DoorRefused(f"a door socket message is one of its declared models or a catalogue message, "
                      f"not {type(source).__name__}")


class ClosedSocket:
    """The only object a door socket endpoint holds: `receive()` gives one parsed JSON client message (or `UNREADABLE`)
    and raises `SocketClosed` when the connection ends; `send()` writes a door-minted body. The raw WebSocket, its URL
    and its query string are never handed to the endpoint."""

    __slots__ = ("_ws", "_models")

    def __init__(self, websocket: WebSocket, message_models: tuple[type, ...]) -> None:
        self._ws = websocket
        self._models = message_models

    async def receive(self) -> object:
        message = await self._ws.receive()
        if message["type"] == "websocket.disconnect":
            raise SocketClosed()
        text = message.get("text")
        if type(text) is not str or len(text) > SOCKET_MAX_MESSAGE:
            return UNREADABLE
        try:
            return json.loads(text)
        except ValueError:
            return UNREADABLE

    async def send(self, source: object) -> None:
        body = socket_body(source, self._models)
        try:
            await self._ws.send_text(bytes(body).decode("utf-8"))
        except (WebSocketDisconnect, RuntimeError):  # the client went away mid-send
            raise SocketClosed() from None


class ClosedWebSocketRoute(APIWebSocketRoute):
    """The only WebSocket route class of the API. Its endpoint is ``async def endpoint(socket: ClosedSocket)``; the door
    accepts the connection, hands the endpoint a `ClosedSocket` limited to ``message_models`` (closed `ApiModel`s), and
    closes the connection when the endpoint returns. An exception inside the endpoint is logged by class name only and
    the connection closes with 1011; no exception text ever reaches the client."""

    def __init__(self, path: str, endpoint: Callable[..., object], *, message_models: tuple[type, ...],
                 **kwargs: object) -> None:
        if not message_models or not all(isinstance(m, type) and issubclass(m, ApiModel) for m in message_models):
            raise TypeError("a door socket declares its message models, each a closed ApiModel")
        self.message_models = tuple(message_models)
        models = self.message_models

        async def door(websocket: WebSocket) -> None:
            await websocket.accept()
            code = 1000
            try:
                await endpoint(ClosedSocket(websocket, models))
            except SocketClosed:
                return
            except Exception as exc:  # never the message: it could hold a request value
                log.error("socket door: %s on %s", type(exc).__name__, path)
                code = 1011
            with contextlib.suppress(Exception):
                await websocket.close(code)

        door.__name__ = getattr(endpoint, "__name__", "socket")
        door.ofo_door = True  # type: ignore[attr-defined]
        door.ofo_endpoint = endpoint  # type: ignore[attr-defined]
        super().__init__(path, door, **kwargs)  # type: ignore[arg-type]


#: The one allow-list for a path Location (W-070 round 5): a single leading `/` (never `//`), then RFC 3986 unreserved
#: and reserved characters, or `%XX` escapes that do not decode to a slash, a backslash, a C0 control or DEL. No space,
#: tab, control character, backslash or non-ASCII byte can match, so the text is the same on every parser.
_PATH_LOCATION = re.compile(
    r"/(?!/)(?:[A-Za-z0-9._~!$&'()*+,;=:@/?#\[\]-]|%(?!2[Ff]|5[Cc]|[01][0-9A-Fa-f]|7[Ff])[0-9A-Fa-f]{2})*")

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


_EXPIRES = re.compile(rb"; expires=[A-Za-z]{3}, [0-9]{2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT")
_COOKIE_PARTS = re.compile(rb'(?P<name>[A-Za-z0-9_.-]{1,64})=(?P<value>""|[A-Za-z0-9_.~-]{0,128})')


def _cookie_from_header(raw: bytes) -> RedirectCookie:
    """A candidate `RedirectCookie` read back from a Set-Cookie value. It is only a candidate: the caller re-mints the
    header from it and demands the same bytes, so anything the cookie builder would not write is refused there."""
    first, _, rest = raw.partition(b";")
    match = _COOKIE_PARTS.fullmatch(first)
    path = re.search(rb"; Path=([^;]*)", raw)
    age = re.search(rb"; Max-Age=([0-9]{1,9})(?=;|$)", raw)
    if match is None or path is None:
        raise DoorRefused("a door cookie is not one the cookie builder writes")
    value = match["value"]
    try:
        return RedirectCookie(match["name"].decode("ascii"), path[1].decode("ascii"),
                              value=None if value == b'""' else value.decode("ascii"),
                              max_age=int(age[1]) if age else None, secure=raw.endswith(b"; Secure"))
    except (ValueError, UnicodeDecodeError):
        raise DoorRefused("a door cookie is not one the cookie builder writes") from None


def _check_record_values(kind: type, status: int, headers: tuple[tuple[bytes, bytes], ...], body: object) -> None:
    """Re-check every header VALUE of a minted record against the closed table, by minting the table again from what the
    record claims (its length, status, optional Retry-After / Allow / cookie / Location) with the SAME `_mint_headers`
    the constructors use, and demanding the very same list. The two can never drift: there is one table. A rewritten
    record (whoever rewrote it, whatever it re-froze) cannot name a value the table would not mint."""
    first: dict[bytes, bytes] = {}
    for name, value in headers:
        first.setdefault(name, value)
    try:
        cookie = _cookie_from_header(first[b"set-cookie"]) if b"set-cookie" in first else None
        allow = tuple(first[b"allow"].decode("ascii").split(", ")) if b"allow" in first else None
        expected = _mint_headers(
            body_length=len(body), content_type=kind is ClosedResponse, status=status,  # type: ignore[arg-type]
            retry_after=first[b"retry-after"].decode("ascii") if b"retry-after" in first else None,
            allow=allow, cookie=cookie,
            location=first[b"location"].decode("latin-1") if b"location" in first else None)
    except (UnicodeDecodeError, ValueError):
        raise DoorRefused("a door response header value is not one the door writes") from None

    def comparable(pairs: object) -> list[tuple[bytes, bytes]]:
        return [(k, _EXPIRES.sub(b"", v) if k == b"set-cookie" else v) for k, v in pairs]  # type: ignore[attr-defined]

    if comparable(headers) != comparable(expected):
        raise DoorRefused("a door response header value is not one the door writes")

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


_frontend_origin = ""  # a plain str, rebound only by `set_frontend_origin`, and only once to a value


def set_frontend_origin(origin: str) -> None:
    """Called by `create_app` with the `FRONTEND_ORIGIN` (scheme://host[:port], no path): the one other site a Location
    may name, followed by a path from the same allow-list (#159). WRITE-ONCE: the value is validated here (so a bad one
    cannot be stored even by a direct call); the first call stores it, a repeat of the same value is a no-op, a
    different value raises. A repo scan (tests/test_door_names_private.py) allows only main.py to name this function."""
    global _frontend_origin  # noqa: PLW0603 - the single write point of the door's origin
    value = validate_frontend_origin(origin)
    if _frontend_origin and _frontend_origin != value:
        raise ValueError("the frontend origin is set once per process")
    _frontend_origin = value


def _check_location(location: str) -> None:
    """THE rule for a Location, shared by the mint (`typed_redirect`, `_mint_headers`) and the re-check, so they cannot
    drift: a path from the allow-list above, that path on the configured frontend origin, or exactly the Zerodha login
    URL. Raises ValueError."""
    if type(location) is not str:
        raise ValueError("a redirect location is text")
    if _PATH_LOCATION.fullmatch(location):
        return  # a path on this site
    origin = _frontend_origin
    if origin and location.startswith(origin) and _PATH_LOCATION.fullmatch(location[len(origin):]):
        return  # a path on the frontend: the remainder starts with exactly one "/", so the host cannot be extended
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
        refused = refusal_of(exc.errors())  # an underlying outside the supported set: its catalogue message (W-129)
        if refused is not None:
            return _body(refused, STATUS_BY_CLASS[refused.error_class])
        log.info("request not valid on %s %s: %s", request.method, request.url.path, _validation_problems(exc))
        return _body(render("user_input_request_invalid"), 422)
    if isinstance(exc, StarletteHTTPException):
        return _http_response(exc, request)
    return _internal_response(exc, request)


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
        finished = False

        async def tracking_send(message: Message) -> None:
            nonlocal started, refused, finished
            if refused or finished:
                return
            if exempt:
                started = started or message["type"] == "http.response.start"
                await send(message)
                return
            seal = scope.get(DOOR_KEY)
            sealed = type(seal) is _SEAL
            if message["type"] == "http.response.start":
                if started or not sealed or not seal.is_start(message):
                    refused = not started
                    log.error("response door: an unsealed response was dropped on %s %s", scope["method"], scope["path"])
                    return
                started = True
            elif not (started and sealed and seal.is_body(message)):  # after a sealed start, only its own body
                refused, finished = not started, started
                log.error("response door: a body the door did not send was dropped on %s %s", scope["method"],
                          scope["path"])
                return
            else:
                finished = True  # the door sends exactly one body message
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
    app.add_middleware(_Boundary, exempt=frozenset(docs))
