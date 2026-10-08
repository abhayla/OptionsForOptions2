"""W-024 round 9 part 6: the API boundary is the one door for error text (REQ-065 AC-1/AC-2, ADR-003 Q226).

Core: no error text reaches a user except a catalogue message from render(). Any exception that is not a
`ofo.errors.UserFacing` becomes the INTERNAL_SYSTEM template's four parts; the exception's own text goes only to the
log (with the reference id the user sees, so support can find it). A `UserFacing` exception shows its own rendered
four-part message with its code, at the HTTP status of its error class.

Expected texts are the catalogue template `internal_system_request_failed` as written for this round (pinned in
tests/errors/template_pins.json, "pending owner read"), never read back from running the code.
"""

from __future__ import annotations

import logging
import re

import pytest
from httpx import ASGITransport, AsyncClient

LEAK = "leg expired before execution, use strike 22,550"
PARTS = ("what_happened", "impact", "what_is_blocked", "next_action")
INTERNAL_WHAT = re.compile(r"An unexpected server error stopped this request \(reference (ERR-[0-9A-F]{8})\)\.")
INTERNAL_IMPACT = "The action you asked for was not completed."
INTERNAL_BLOCKED = "This request, until the issue is resolved."
INTERNAL_NEXT = "Try again in a few minutes; contact support with the reference if this keeps happening."


def _app_raising(exc: BaseException):
    from ofo_app.main import create_app

    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return app


async def _get(app, path: str = "/boom"):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.get(path)


def _assert_internal(body: dict) -> str:
    assert body["error_class"] == "INTERNAL_SYSTEM"
    assert body["code"] == "INTERNAL_SYSTEM_002"
    match = INTERNAL_WHAT.fullmatch(body["what_happened"])
    assert match, body
    assert body["impact"] == INTERNAL_IMPACT
    assert body["what_is_blocked"] == INTERNAL_BLOCKED
    assert body["next_action"] == INTERNAL_NEXT
    assert body["external_text"] is None
    return match.group(1)


async def test_step1_domain_value_error_shows_internal_system_message_and_logs_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Step 1 (core proof): a plain domain ValueError never shows its own text; the user gets the four parts."""
    caplog.set_level(logging.ERROR, logger="ofo_app.main")
    response = await _get(_app_raising(ValueError(LEAK)))
    assert response.status_code == 500
    assert LEAK not in response.text
    reference = _assert_internal(response.json())
    logged = "\n".join(r.getMessage() + (r.exc_text or "") for r in caplog.records)
    assert LEAK in logged or any(LEAK in str(r.exc_info[1]) for r in caplog.records if r.exc_info)
    assert reference in logged


async def test_runtime_error_with_secret_detail_never_reaches_the_body() -> None:
    secret = "internal detail: host db.internal port 5432"
    response = await _get(_app_raising(RuntimeError(secret)))
    assert response.status_code == 500
    assert secret not in response.text
    _assert_internal(response.json())


async def test_user_facing_exception_shows_its_rendered_message_and_class_status() -> None:
    from ofo.errors import render
    from ofo.execution.send_guard import SendRefused

    message = render("send_choice_unknown")
    response = await _get(_app_raising(SendRefused(message)))
    assert response.status_code == 500  # INTERNAL_SYSTEM class
    body = response.json()
    assert body == message.as_dict()


async def test_user_facing_exception_of_a_user_input_class_is_a_422() -> None:
    from ofo.errors import render
    from ofo.strategy.model import TemplateError

    message = render("user_input_lot_size", entered=0)
    response = await _get(_app_raising(TemplateError("developer detail: lots=0 in row 7", message=message)))
    assert response.status_code == 422
    assert response.json() == message.as_dict()
    assert "developer detail" not in response.text


async def test_user_facing_exception_without_a_message_is_internal() -> None:
    """A UserFacing type whose optional message is absent shows the internal message, never its detail."""
    from ofo.strategy.model import TemplateError

    response = await _get(_app_raising(TemplateError("developer detail: bad yaml at line 3")))
    assert response.status_code == 500
    assert "developer detail" not in response.text
    _assert_internal(response.json())


async def test_unknown_route_and_http_exception_detail_never_echo_text() -> None:
    from fastapi import HTTPException

    response = await _get(_app_raising(HTTPException(status_code=404, detail=LEAK)))
    assert response.status_code == 404
    assert LEAK not in response.text
    for part in PARTS:
        assert response.json()[part]
    missing = await _get(_app_raising(ValueError("x")), "/no-such-route")
    assert missing.status_code == 404
    for part in PARTS:
        assert missing.json()[part]


async def test_request_validation_error_never_echoes_the_input() -> None:
    from ofo_app.main import create_app

    app = create_app()

    @app.get("/lots")
    async def lots(n: int) -> dict:
        return {"n": n}

    response = await _get(app, "/lots?n=" + "leg%20expired%20use%2022550")
    assert response.status_code == 422
    assert "22550" not in response.text and "expired" not in response.text
    assert response.json()["error_class"] == "USER_INPUT"
    for part in PARTS:
        assert response.json()[part]


@pytest.mark.parametrize("error_class", [
    "USER_INPUT", "STRATEGY_VALIDATION", "MARKET_DATA", "BROKER_AUTHENTICATION", "BROKER_ELIGIBILITY", "MARGIN",
    "ORDER_REJECTION", "PARTIAL_EXECUTION", "RECONCILIATION_MISMATCH", "NOTIFICATION", "ENTITLEMENT_ACCESS",
    "INTERNAL_SYSTEM",
])
def test_every_error_class_has_an_http_status(error_class: str) -> None:
    from ofo.errors import ErrorClass
    from ofo_app.errors import STATUS_BY_CLASS

    status = STATUS_BY_CLASS[ErrorClass[error_class]]
    assert 400 <= status <= 599
    assert set(STATUS_BY_CLASS) == set(ErrorClass)


async def test_mutant_handler_returning_str_exc_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: make the boundary return str(exc) -> the step-1 assertion goes red."""
    import ofo_app.errors as boundary
    from fastapi.responses import JSONResponse

    def leaky(exc: BaseException) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    monkeypatch.setattr(boundary, "_internal_response", lambda exc, request: leaky(exc))
    response = await _get(_app_raising(ValueError(LEAK)))
    assert LEAK in response.text  # the mutant leaks: the step-1 test's `LEAK not in response.text` would be red
