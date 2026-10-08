"""The one door for error text at the API boundary (W-024 round 9 part 6; REQ-065 AC-1/AC-2, ADR-003 Q226).

Every error response body the API sends is built here, and only from a `render()` result:

- an `ofo.errors.UserFacing` exception carrying a `render()` message -> that message's parts (`as_dict()`), at the
  HTTP status of its error class (`STATUS_BY_CLASS`);
- a request the API cannot read (`RequestValidationError`) -> `user_input_request_invalid` (422);
- an HTTP 4xx raised by the framework or a route (an unknown address, a wrong method) -> `user_input_request_not_available`
  at its own status; its `detail` is never shown;
- ANY other exception -> `internal_system_request_failed` (500) with a fresh reference id; the exception's own text goes
  only to the log, beside that reference, so support can find it.

No route builds an error body itself: tests_app/test_error_boundary_scan.py fails on `str(exc)`, an f-string or a
sentence in a response built anywhere in backend/ofo_app outside this file.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ofo.errors import ErrorClass, UserFacingError, render, user_message_of

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


def _body(message: UserFacingError, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content=message.as_dict())


def _reference() -> str:
    return "ERR-" + secrets.token_hex(4).upper()


def _internal_response(exc: BaseException, request: Request) -> JSONResponse:
    reference = _reference()
    log.error("unhandled error %s on %s %s", reference, request.method, request.url.path, exc_info=exc)
    return _body(render("internal_system_request_failed", reference=reference), 500)


async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    """The single exception handler: registered for every exception type the framework routes to a handler."""
    message = user_message_of(exc)
    if message is not None:
        log.info("user-facing error %s on %s %s: %s", message.code, request.method, request.url.path, exc)
        return _body(message, STATUS_BY_CLASS[message.error_class])
    if isinstance(exc, RequestValidationError):
        log.info("request not valid on %s %s: %s", request.method, request.url.path, exc.errors())
        return _body(render("user_input_request_invalid"), 422)
    if isinstance(exc, StarletteHTTPException) and 400 <= exc.status_code < 500:
        log.info("http %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail)
        return _body(render("user_input_request_not_available"), exc.status_code)
    return _internal_response(exc, request)


def install(app: FastAPI) -> None:
    """Route every error through `handle_error`: the framework's own HTTP and validation handlers are replaced too,
    so their default bodies (which echo `detail` and the request's values) never reach a user."""
    for exc_type in (Exception, StarletteHTTPException, RequestValidationError):
        app.add_exception_handler(exc_type, handle_error)
