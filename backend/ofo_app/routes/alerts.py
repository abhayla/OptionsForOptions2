"""ADR-330 (3), (4): the Alerts page's Active and History lists and the user's answer (exit / continue).

- GET /api/alerts/active: the unanswered actionable alerts of the user's visible strategies; ``count`` is the length of
  the SAME list (one query, ``actionable_alerts.unanswered``), so the bell cannot differ from the rows.
- POST /api/alerts/{id}/answer {"answer"}: 200 the answered row; 404 suggestion_not_found (another user's id, a deleted
  strategy's, a missing id); 409 suggestion_not_open (already answered); 422 alert_answer_refused (empty or not one of
  the kind's answers). Nothing is written on a refusal. An answer never places an order (ADR-003): "Exit the position"
  only records the call; the exit itself is the usual confirmation.
- GET /api/alerts/history: answered, system-closed and informational rows, newest first.

Answer states: stated -> row leaves Active; absent -> stays; not found / not open / refused -> the three errors above.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from ofo.alerts import CLOSED_BY_SYSTEM
from ofo.errors import render
from ofo.errors.explanations import ALERT_ANSWER_LABEL_TEXT, render_explanation
from ofo.timeutil import IST
from pydantic import BaseModel

from ofo_app import actionable_alerts as aa
from ofo_app import playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.adjustment_opportunities import ID_MAX, condition_text
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused
from ofo_app.strategy_store import StrategyStoreError

router = APIRouter(route_class=ClosedRoute)
_STATUS = {store.SUGGESTION_NOT_FOUND: Failure.NOT_FOUND, store.SUGGESTION_NOT_OPEN: Failure.CONFLICT}
_HM = "%H:%M"


class AnswerIn(BaseModel):
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
    fired_at: Identifier | str
    fired_at_hm: str
    no_longer_true_since: str | None
    no_longer_true_since_hm: str | None
    answers: list[AnswerChoice]


class ActiveOut(ApiModel):
    count: int
    alerts: list[ActiveAlert]


class AnsweredOut(ApiModel):
    id: int
    answer: Identifier
    answer_label: CatalogueText
    answered_at: str
    answered_at_hm: str


class HistoryItem(ApiModel):
    id: int
    strategy_id: int
    strategy_name: CatalogueText
    kind: Identifier
    text: CatalogueText
    fired_at: Identifier | str
    fired_at_hm: str
    answer: Identifier | None
    answer_label: CatalogueText | None
    answered_at: str | None
    answered_at_hm: str | None
    closed_reason: CatalogueText | None


class HistoryOut(ApiModel):
    items: list[HistoryItem]


def _kind(a: aa.Alert) -> str:
    return a.kind or "adjustment_rule"  # a record written before migration 0054 is an adjustment rule


def _words(a: aa.Alert, by_id: dict[int, store.Suggestion]) -> Any:
    """The words the inbox already shows for the record (Active says what today's record says); an informational note
    carries its own text; a record the inbox cannot word falls back to its stage-less rule label, never a raw id."""
    if a.text is not None:
        return a.text
    found = by_id.get(a.id)
    shown = None if found is None else condition_text(found)
    return shown if shown is not None else render_explanation("adjust_condition_line_id", label=a.strategy_name)


def _iso(at: Any) -> str | None:
    return None if at is None else at.astimezone(IST).isoformat()


def _hm(at: Any) -> str | None:
    return None if at is None else at.astimezone(IST).strftime(_HM)


def _reason(a: aa.Alert) -> Any:
    """History's line for a system close (owner Q2b: 'Closed by system: the trade closed at HH:MM')."""
    if a.answer != CLOSED_BY_SYSTEM or a.closed_reason is None:
        return None
    if a.closed_reason == store.LAPSE_STRATEGY_CLOSED and a.answered_at is not None:
        return render_explanation("alert_closed_trade_closed", time=a.answered_at)
    return render_explanation("suggestion_lapsed_" + a.closed_reason)


async def _texts(db: Any, user_ref: str) -> dict[int, store.Suggestion]:
    return {r.suggestion.id: r.suggestion for r in await store.inbox(db, user_ref)}


@router.get("/api/alerts/active", response_model=ActiveOut)
async def active_alerts(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> ActiveOut:
    rows = await aa.unanswered(db, user_ref)  # ONE query: the count below is len() of these rows
    by_id = await _texts(db, user_ref)
    from ofo.alerts import allowed_answers  # noqa: PLC0415 - stdlib table
    alerts = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": a.strategy_name, "kind": _kind(a),
               "text": _words(a, by_id), "fired_at": _iso(a.fired_at), "fired_at_hm": _hm(a.fired_at),
               "no_longer_true_since": _iso(a.no_longer_true_since),
               "no_longer_true_since_hm": _hm(a.no_longer_true_since),
               "answers": [{"code": c, "label": ALERT_ANSWER_LABEL_TEXT[c]}
                           for c in (allowed_answers(a.kind) if a.kind else ("exit", "continue"))]} for a in rows]
    return ActiveOut.model_validate({"count": len(rows), "alerts": alerts})


@router.post("/api/alerts/{alert_id}/answer", response_model=AnsweredOut)
async def answer_alert(alert_id: int, body: AnswerIn, db: Annotated[Any, Depends(get_db)],
                       user_ref: Annotated[str, Depends(current_user_ref)]) -> AnsweredOut:
    from datetime import UTC, datetime  # noqa: PLC0415
    try:
        if not 1 <= alert_id <= ID_MAX:
            raise StrategyStoreError(store.SUGGESTION_NOT_FOUND, f"suggestion {alert_id}")
        done = await aa.answer(db, user_ref, alert_id, body.answer, datetime.now(UTC))
        await db.commit()
    except aa.AlertAnswerRefused:
        await db.rollback()
        raise StrategyRefused(aa.ALERT_ANSWER_REFUSED, Failure.UNPROCESSABLE,
                              message=render(aa.ALERT_ANSWER_REFUSED)) from None
    except StrategyStoreError as exc:
        await db.rollback()
        if exc.code not in _STATUS:
            raise
        raise StrategyRefused(exc.code, _STATUS[exc.code], message=render(exc.code)) from None
    except Exception:
        await db.rollback()
        raise
    return AnsweredOut.model_validate({
        "id": done.id, "answer": done.answer, "answer_label": ALERT_ANSWER_LABEL_TEXT[done.answer or ""],
        "answered_at": _iso(done.answered_at), "answered_at_hm": _hm(done.answered_at)})


@router.get("/api/alerts/history", response_model=HistoryOut)
async def alert_history(db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> HistoryOut:
    by_id = await _texts(db, user_ref)
    items = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": a.strategy_name, "kind": _kind(a),
              "text": _words(a, by_id), "fired_at": _iso(a.fired_at), "fired_at_hm": _hm(a.fired_at),
              "answer": a.answer, "answer_label": ALERT_ANSWER_LABEL_TEXT.get(a.answer or ""),
              "answered_at": _iso(a.answered_at), "answered_at_hm": _hm(a.answered_at),
              "closed_reason": _reason(a)} for a in await aa.history(db, user_ref)]
    return HistoryOut.model_validate({"items": items})
