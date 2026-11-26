"""ADR-330 (3), (4): the Alerts page's Active and History lists and the user's answer (exit / continue).

- GET /api/alerts/active: the unanswered actionable alerts of the user's visible strategies; ``count`` is the length of
  the SAME list (one query, ``actionable_alerts.unanswered``), so the bell cannot differ from the rows.
- POST /api/alerts/{id}/answer {"answer"}: 200 the answered row; 404 suggestion_not_found (another user's id, a deleted
  strategy's, a missing id); 409 suggestion_not_open (already answered); 422 alert_answer_refused (empty or not one of
  the kind's answers). Nothing is written on a refusal. An answer never places an order (ADR-003): "Exit the position"
  only records the call; the exit itself is the usual confirmation.
- GET /api/alerts/answered: answered, system-closed and informational rows, newest first.

Answer states: stated -> row leaves Active; absent -> stays; not found / not open / refused -> the three errors above.
"""
from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from ofo.alerts import CLOSED_BY_SYSTEM
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.strategy.stored_form import shown_name
from pydantic import BaseModel, ConfigDict

from ofo_app import actionable_alerts as aa
from ofo_app import playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.adjustment_opportunities import ID_MAX, condition_text
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_STATUS = {store.SUGGESTION_NOT_FOUND: Failure.NOT_FOUND, store.SUGGESTION_NOT_OPEN: Failure.CONFLICT}


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a closed body: an unnamed field is refused (422)

    answer: str = ""


class AnswerChoice(ApiModel):
    code: Identifier
    label: CatalogueText


class ActiveAlert(ApiModel):
    id: int
    strategy_id: int
    strategy_name: CatalogueText
    kind: Identifier
    text: CatalogueText
    fired_at: datetime.datetime
    fired_line: CatalogueText
    no_longer_true_since: datetime.datetime | None
    no_longer_true_line: CatalogueText | None
    escalated_at: datetime.datetime | None
    worse_line: CatalogueText | None
    answers: list[AnswerChoice]


class ActiveOut(ApiModel):
    count: int
    alerts: list[ActiveAlert]


class AnsweredOut(ApiModel):
    id: int
    answer: Identifier
    answer_label: CatalogueText
    answered_at: datetime.datetime


class HistoryItem(ApiModel):
    id: int
    strategy_id: int
    strategy_name: CatalogueText
    kind: Identifier
    text: CatalogueText
    fired_at: datetime.datetime
    fired_line: CatalogueText
    escalated_at: datetime.datetime | None
    worse_line: CatalogueText | None
    answer: Identifier | None
    answer_label: CatalogueText | None
    answered_at: datetime.datetime | None
    closed_reason: CatalogueText | None


class HistoryOut(ApiModel):
    items: list[HistoryItem]


def _kind(a: aa.Alert) -> str:
    return a.kind or "adjustment_rule"  # a record written before migration 0054 is an adjustment rule


def _words(a: aa.Alert, by_id: dict[int, store.Suggestion]) -> Any:
    """The words the inbox already shows for the record (Active says what today's record says); an informational note
    is rendered from the catalogue id and values stored with it; a record the inbox cannot word falls back to its
    stage-less rule label, never a raw id."""
    if a.note is not None:
        template_id, values = a.note
        return render_explanation(template_id, **values)
    found = by_id.get(a.id)
    shown = None if found is None else condition_text(found)
    return shown if shown is not None else render_explanation("adjust_condition_line_id", label=a.strategy_name)


def _fired(a: aa.Alert) -> Any:
    return render_explanation("alert_fired_at", time=a.fired_at)


def _stopped(a: aa.Alert) -> Any:
    at = a.no_longer_true_since
    return None if at is None else render_explanation("alert_no_longer_true_since", time=at)


def _worse(a: aa.Alert) -> Any:
    """REQ-170 AC-3: a later, worse reading of the same rule updated this open alert; None if it never was."""
    if a.escalated_at is None or a.value is None or a.fired_value is None:
        return None
    now, fired = format(a.value, "f"), format(a.fired_value, "f")
    try:
        return render_explanation("alert_worse_than_fired", value=now, unit=a.unit, fired=fired)
    except (TypeError, ValueError):  # no stored unit, or one the catalogue does not take: the line without it
        return render_explanation("alert_worse_than_fired_plain", value=now, fired=fired)


def _label(code: str | None) -> Any:
    return None if code is None else render_explanation("alert_answer_" + code)


def _reason(a: aa.Alert) -> Any:
    """History's line for a system close (owner Q2b: 'Closed by system: the trade closed at HH:MM')."""
    if a.answer != CLOSED_BY_SYSTEM or a.closed_reason is None:
        return None
    if a.closed_reason == store.LAPSE_STRATEGY_CLOSED and a.answered_at is not None:
        return render_explanation("alert_closed_trade_closed", time=a.answered_at)
    return render_explanation("suggestion_lapsed_" + a.closed_reason)


async def _labels(db: Any, rows: list[aa.Alert]) -> dict[int, Any]:
    """ADR-330 (19)(b): strategy id -> "<name> (#<id>, <nearest open-leg expiry as D Mon>)" through THIS one function
    (Active and History share it). Answer states: stated -> with the expiry; no open leg / book unreadable / not found
    -> "(#<id>)" only, never a guessed date."""
    from ofo_app import adjustment_readers as readers  # noqa: PLC0415 - it imports the route modules
    out: dict[int, Any] = {}
    for a in rows:
        if a.strategy_id in out:
            continue
        name = shown_name(a.strategy_name)
        expiry = None
        try:
            async with db.begin_nested():  # a failed statement rolls back to here, the request's session stays usable
                expiry = await readers.nearest_expiry(db, a.strategy_id)
        except Exception:  # noqa: BLE001 - a label must never stop the Active list, History or the bell (ADR-330 (3)(4))
            log.warning("alert label: the expiry of strategy %s could not be read; its number is shown alone",
                        a.strategy_id, exc_info=True)
        out[a.strategy_id] = (
            render_explanation("alert_strategy_label_no_expiry", name=name, number=a.strategy_id) if expiry is None
            else render_explanation("alert_strategy_label", name=name, number=a.strategy_id, day=expiry.day,
                                    month=expiry.strftime("%b")))
    return out


async def _texts(db: Any, user_ref: str) -> dict[int, store.Suggestion]:
    return {r.suggestion.id: r.suggestion for r in await store.inbox(db, user_ref)}


@router.get("/api/alerts/active", response_model=ActiveOut)
async def active_alerts(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> ActiveOut:
    rows = await aa.unanswered(db, user_ref)  # ONE query: the count below is len() of these rows
    by_id = await _texts(db, user_ref)
    labels = await _labels(db, rows)
    from ofo.alerts import allowed_answers  # noqa: PLC0415 - stdlib table
    alerts = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": labels[a.strategy_id], "kind": _kind(a),
               "text": _words(a, by_id), "fired_at": a.fired_at, "fired_line": _fired(a),
               "no_longer_true_since": a.no_longer_true_since, "no_longer_true_line": _stopped(a),
               "escalated_at": a.escalated_at, "worse_line": _worse(a),
               "answers": [{"code": c, "label": _label(c)}
                           for c in (allowed_answers(a.kind) if a.kind else ("exit", "continue"))]} for a in rows]
    return ActiveOut.model_validate({"count": len(rows), "alerts": alerts})


@router.post("/api/alerts/{alert_id}/answer", response_model=AnsweredOut)
async def answer_alert(alert_id: int, body: AnswerIn, db: Annotated[Any, Depends(get_db)],
                       user_ref: Annotated[str, Depends(current_user_ref)]) -> AnsweredOut:
    from datetime import UTC, datetime  # noqa: PLC0415
    try:
        if not 1 <= alert_id <= ID_MAX:
            raise aa.StoreError(store.SUGGESTION_NOT_FOUND, f"suggestion {alert_id}")
        done = await aa.answer(db, user_ref, alert_id, body.answer, datetime.now(UTC))
        await db.commit()
    except aa.AlertAnswerRefused:
        await db.rollback()
        raise StrategyRefused(aa.ALERT_ANSWER_REFUSED, Failure.UNPROCESSABLE,
                              message=render(aa.ALERT_ANSWER_REFUSED)) from None
    except aa.StoreError as exc:
        await db.rollback()
        if exc.code not in _STATUS:
            raise
        raise StrategyRefused(exc.code, _STATUS[exc.code], message=render(exc.code)) from None
    except Exception:
        await db.rollback()
        raise
    return AnsweredOut.model_validate({
        "id": done.id, "answer": done.answer, "answer_label": _label(done.answer),
        "answered_at": done.answered_at})


@router.get("/api/alerts/answered", response_model=HistoryOut)
async def alert_answered(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> HistoryOut:
    by_id = await _texts(db, user_ref)
    history = await aa.history(db, user_ref)
    labels = await _labels(db, history)
    items = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": labels[a.strategy_id], "kind": _kind(a),
              "text": _words(a, by_id), "fired_at": a.fired_at, "fired_line": _fired(a),
              "escalated_at": a.escalated_at, "worse_line": _worse(a),
              "answer": a.answer, "answer_label": _label(a.answer),
              "answered_at": a.answered_at,
              "closed_reason": _reason(a)} for a in history]
    return HistoryOut.model_validate({"items": items})
