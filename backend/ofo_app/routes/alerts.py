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
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from ofo.alerts import CLOSED_BY_SYSTEM, SIDE_CLOSED
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from pydantic import BaseModel, ConfigDict

from ofo_app import actionable_alerts as aa
from ofo_app import alert_title, side_closed
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
    position_kind: Identifier  # ADR-330 (64): paper | real | none | unknown (the stored fact, never the name)
    position_kind_text: CatalogueText | None  # the real / unknown row's one line; None for paper


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


_SIDE_CLOSED_TEXT = {"call": "alert_side_closed_text_call", "put": "alert_side_closed_text_put"}


def _words(a: aa.Alert, by_id: dict[int, store.Suggestion]) -> Any:
    """The words the inbox already shows for the record (Active says what today's record says); an informational note
    is rendered from the catalogue id and values stored with it; a record the inbox cannot word falls back to its
    stage-less rule label, never a raw id."""
    side = _closed_side(a)
    shape = None if side is None else side_closed.remaining_shape_name(side)
    # ADR-330 (2) (b): the side_closed row says the side closed, the shape that remains (the template's own name,
    # TemplateText refuses any other string), and asks; an unknown side or shape keeps the row's earlier words
    if side in _SIDE_CLOSED_TEXT and shape is not None:
        return render_explanation(_SIDE_CLOSED_TEXT[side], shape=shape)
    if a.note is not None:
        template_id, values = a.note
        return render_explanation(template_id, **values)
    found = by_id.get(a.id)
    shown = None if found is None else condition_text(found)
    return shown if shown is not None else _rule_in_words(a)


#: the rule's kind in words, for a record the inbox cannot word (item 2: never the trade's name as the reason)
_KIND_WORDS = {"plan_loss_stop": "Plan loss stop", "plan_profit_target": "Plan profit target",
               "plan_rupee_loss": "Plan loss stop", "plan_rupee_profit": "Plan rupee target",
               "plan_time_exit": "Plan time exit"}
_TRIGGER_ID = re.compile(r"T-\d{2}[a-z]?")


def _rule_in_words(a: aa.Alert) -> Any:
    """The rule of a record with no worded condition: its kind (or its trigger id) and, when the record holds them, its
    value and threshold. Every answer state: kind known / trigger only / neither (the generic words); figures present
    or absent. Server-built; the page prints it."""
    label = _KIND_WORDS.get(_kind(a))
    if label is None:
        label = f"Adjustment rule {a.trigger_id}" if a.trigger_id and _TRIGGER_ID.fullmatch(a.trigger_id) \
            else "Adjustment rule"
    if a.value is not None and a.threshold is not None:
        try:
            return render_explanation("alert_rule_fallback_valued", label=label, value=format(a.value, "f"),
                                      threshold=format(a.threshold, "f"))
        except (TypeError, ValueError):
            pass
    return render_explanation("adjust_condition_line_id", label=label)


def _closed_side(a: aa.Alert) -> str | None:
    """"call" / "put" for a side_closed row (its rule id is ``side.closed.<side>``), else None."""
    prefix = side_closed.RULE_PREFIX
    side = a.rule_id.removeprefix(prefix)
    if a.kind != SIDE_CLOSED or not a.rule_id.startswith(prefix) or side not in ("call", "put"):
        return None
    return side


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


def offered(codes: tuple[str, ...], position_kind: str) -> tuple[str, ...]:
    """ADR-330 (64): "Exit the position" is offered for a PAPER position only; real, none and unknown never get it."""
    return codes if position_kind == "paper" else tuple(c for c in codes if c != "exit")


def _label(code: str | None) -> Any:
    return None if code is None else render_explanation("alert_answer_" + code)


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
    titles = await alert_title.labels(db, [(a.strategy_id, a.strategy_name) for a in rows])  # ADR-330 (19)(b)
    from ofo.alerts import allowed_answers  # noqa: PLC0415 - stdlib table
    from ofo_app import position_kind, strategy_store  # noqa: PLC0415 - late: it reaches the order modules
    kinds = await strategy_store.kinds_of(db, [a.strategy_id for a in rows])
    alerts = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": titles[a.strategy_id], "kind": _kind(a),
               "text": _words(a, by_id), "fired_at": a.fired_at, "fired_line": _fired(a),
               "no_longer_true_since": a.no_longer_true_since, "no_longer_true_line": _stopped(a),
               "escalated_at": a.escalated_at, "worse_line": _worse(a),
               "answers": [{"code": c, "label": _label(c)}
                           for c in offered(allowed_answers(a.kind) if a.kind else ("exit", "continue"),
                                            kinds.get(a.strategy_id, "unknown"))],
               "position_kind": kinds.get(a.strategy_id, "unknown"),
               "position_kind_text": position_kind.line_of(kinds.get(a.strategy_id, "unknown"))} for a in rows]
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
async def alert_answered(db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
                        after: Annotated[int | None, Query(ge=0, le=ID_MAX)] = None) -> HistoryOut:
    """``after``: only the rows with an id above it (the header's pop-up reader asks for what is new since the last
    row it saw; the page History asks without it)."""
    by_id = await _texts(db, user_ref)
    rows = [a for a in await aa.history(db, user_ref) if after is None or a.id > after]
    titles = await alert_title.labels(db, [(a.strategy_id, a.strategy_name) for a in rows])  # ADR-330 (19)(b)
    items = [{"id": a.id, "strategy_id": a.strategy_id, "strategy_name": titles[a.strategy_id], "kind": _kind(a),
              "text": _words(a, by_id), "fired_at": a.fired_at, "fired_line": _fired(a),
              "escalated_at": a.escalated_at, "worse_line": _worse(a),
              "answer": a.answer, "answer_label": _label(a.answer),
              "answered_at": a.answered_at,
              "closed_reason": _reason(a)} for a in rows]
    return HistoryOut.model_validate({"items": items})
