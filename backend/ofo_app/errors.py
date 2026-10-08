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
  the log, beside that reference, through the redaction filter (ofo_app/redaction.py).

Logging (review MAJOR-3): never a request value. A validation error logs only each problem's `loc` and `type` (never
`input`, `ctx` or `msg`); every record on the boundary's loggers is redacted (secret-keyed values, token-shaped runs).
Starlette's outermost middleware re-raises an exception after its handler ran ("allows servers to log the error"),
which would hand the raw traceback to the server's logger: `_Boundary`, an inner middleware, answers the exception
itself and never re-raises.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ofo.errors import ErrorClass, UserFacingError, render, user_message_of
from ofo_app.redaction import install_redaction

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

#: The only headers of an HTTP error that are passed on: the protocol needs them, and they hold no free text.
KEPT_HEADERS: frozenset[str] = frozenset({"allow", "www-authenticate"})


def _body(message: UserFacingError, status: int, headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=message.as_dict(), headers=dict(headers or {}))


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
        return _body(message, STATUS_BY_CLASS[message.error_class])
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
