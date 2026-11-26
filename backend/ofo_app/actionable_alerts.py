# ruff: noqa: E501
"""The ONE writer of alerts (ADR-330 (3), (4) and the owner's standing instruction).

Spec basis: ADR-330 (3) "Such an alert does not close, lapse or leave the Active list until the user himself
acknowledges it and takes his call: exit the position, or continue with the position. It shows 'Fired at HH:MM'; if its
condition later stops being true it adds 'no longer true since HH:MM' and still stays ... The alert only informs and asks:
it never exits by itself"; (4) "the bell counts the actionable alerts of point (3) that the user has not yet answered,
and that number equals the number of rows in the Active list. Informational messages never count"; standing
instruction: "every 'actionable alert' above is raised through ONE shared module, called with the kind of condition
that was met and its facts; no trigger writes its own alert code". ADR-293 (3): a deleted strategy's alerts leave the list.

Storage: public.adjustment_suggestions (migration 0054 adds kind, answer, answered_at, no_longer_true_since); the SQL
helpers stay in ``playbook_store`` and are called from here. The table guard (0054) is the structural half: a record of a
kind cannot leave 'open' without an answer, nor lapse except as 'closed_by_system'.

Answer states of ``answer`` (every one has a test): stated -> the row leaves ``unanswered`` and History keeps answer and
time; absent -> nothing is called, the row stays; not found (another user's id, a deleted strategy) ->
``SUGGESTION_NOT_FOUND``; failed (a database error) -> raised, the savepoint leaves the row unchanged; empty or
ambiguous (not allowed for the kind) -> ``AlertAnswerRefused``; already answered -> ``SUGGESTION_NOT_OPEN``.
Nothing here places an order: an alert informs and asks (ADR-003).
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ofo import alerts as kinds
from ofo.errors.explanations import render_explanation
from sqlalchemy import text

from ofo_app import playbook_store as pb
from ofo_app import strategy_store

ALERT_ANSWER_REFUSED = "alert_answer_refused"
#: the store error this module raises for a not-found / not-open alert (routes catch it here, never via strategy_store)
StoreError = strategy_store.StrategyStoreError
#: the reasons that still end an alert because the position the question is about is gone (ADR-330 (3))
SYSTEM_REASONS = (pb.LAPSE_STRATEGY_CLOSED, pb.LAPSE_CONTRACT_EXPIRED,
                  pb.LAPSE_NOT_MONITORED)
#: the final outcome each user answer is stored with (Dismiss = continue keeps its old outcome 'dismissed')
_OUTCOME_OF: dict[str, str] = {kinds.EXIT: "acted_on", kinds.ADD_LEGS: "acted_on",
                               kinds.CONTINUE: "dismissed", kinds.CONFIRM_NEW_SHAPE: "dismissed"}
_LESS_IS_WORSE = ("le", "lt")

_COLUMNS = ("g.id, g.strategy_id, s.name, g.rule_id, g.kind, g.trigger_id, g.stage, g.value, g.threshold, g.shown_at, "
            "g.outcome, g.answer, g.answered_at, g.no_longer_true_since, g.dismiss_reason, g.timeline::text, g.escalated_at")
_FROM = ("FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
         "WHERE s.user_ref = :user_ref AND s.deleted_at IS NULL")
_ONE = text(f"SELECT {_COLUMNS} {_FROM} AND g.id = :id")
_OPEN_OF_RULE = text(f"SELECT {_COLUMNS} {_FROM} AND g.strategy_id = :strategy_id AND g.rule_id = :rule_id "
                     "AND g.outcome = 'open'")
_OPEN_OF_STRATEGY = text(f"SELECT {_COLUMNS} {_FROM} AND g.strategy_id = :strategy_id "
                         "AND g.outcome = 'open' ORDER BY g.id")
#: the Active list: open rows of the user's visible strategies of this process (D-29), newest first
_UNANSWERED_SQL = (f"SELECT {_COLUMNS} {_FROM} AND g.outcome = 'open' "  # noqa: S608 constant names
                   f"AND g.kind IS DISTINCT FROM '{kinds.LEVEL_WATCH}' AND {{scope}} "
                   "ORDER BY g.shown_at DESC, g.id DESC")
_HISTORY_SQL = (f"SELECT {_COLUMNS} {_FROM} AND g.outcome <> 'open' AND {{scope}} "
                "ORDER BY COALESCE(g.answered_at, g.shown_at) DESC, g.id DESC")
_UPDATE_FACTS = text(
    "UPDATE public.adjustment_suggestions AS g SET value = CAST(:value AS NUMERIC), "
    "threshold = CAST(:threshold AS NUMERIC), stage = CAST(:stage AS TEXT), "
    "no_longer_true_since = NULL, escalated_at = CAST(:at AS TIMESTAMPTZ), timeline = g.timeline || jsonb_build_array(jsonb_build_object("
    "'at', CAST(:at AS TIMESTAMPTZ), 'event', 'worse', 'value', CAST(:value_text AS TEXT), "
    "'threshold', CAST(:threshold_text AS TEXT))) WHERE g.id = :id AND g.outcome = 'open'")
_SET_STOPPED = text(
    "UPDATE public.adjustment_suggestions AS g SET no_longer_true_since = CAST(:at AS TIMESTAMPTZ), "
    "timeline = g.timeline || jsonb_build_array(jsonb_build_object('at', CAST(:at AS TIMESTAMPTZ), "
    "'event', 'condition_stopped')) WHERE g.id = :id AND g.outcome = 'open' AND g.no_longer_true_since IS NULL")
_CLEAR_STOPPED = text(
    "UPDATE public.adjustment_suggestions AS g SET no_longer_true_since = NULL, "
    "timeline = g.timeline || jsonb_build_array(jsonb_build_object('at', CAST(:at AS TIMESTAMPTZ), "
    "'event', 'condition_true_again')) WHERE g.id = :id AND g.outcome = 'open' "
    "AND g.no_longer_true_since IS NOT NULL")
_INSERT_NOTE = text(
    "INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, kind, outcome, answer, answered_at, shown_at, "
    "timeline) VALUES (:strategy_id, :rule_id, :kind, 'dismissed', 'noted', CAST(:at AS TIMESTAMPTZ), "
    "CAST(:at AS TIMESTAMPTZ), jsonb_build_array(jsonb_build_object('at', CAST(:at AS TIMESTAMPTZ), "
    "'outcome', 'dismissed', 'event', 'info', 'template', CAST(:template AS TEXT), "
    "'values', CAST(:values AS JSONB)))) RETURNING id")


class AlertAnswerRefused(ValueError):
    """The answer is empty, unknown, or not one of the answers of the alert's kind: nothing was written."""

    code = ALERT_ANSWER_REFUSED

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"{ALERT_ANSWER_REFUSED}: {detail}")


@dataclass(frozen=True)
class Alert:
    """One row of the alert table as the Active list and History read it. ``kind`` is None on a record written before
    migration 0054 (an adjustment rule). Money stays Decimal."""

    id: int
    strategy_id: int
    strategy_name: str
    rule_id: str
    kind: str | None
    trigger_id: str | None
    stage: str | None
    value: Decimal | None
    threshold: Decimal | None
    fired_at: datetime
    outcome: str
    answer: str | None
    answered_at: datetime | None
    no_longer_true_since: datetime | None
    dismiss_reason: str | None
    timeline: list = field(default_factory=list)
    #: the last time a WORSE value of the same rule updated this open alert (REQ-170 AC-3); None if never
    escalated_at: datetime | None = None

    @property
    def fired_value(self) -> Decimal | None:
        """The value the alert fired at (kept in its first timeline entry; ``value`` moves with a worse reading)."""
        raw = self.timeline[0].get("fired_value") if self.timeline else None
        return None if raw is None else Decimal(raw)

    @property
    def unit(self) -> str | None:
        return self.timeline[0].get("unit") if self.timeline else None

    @property
    def note(self) -> tuple[str, dict[str, Any]] | None:
        """An informational note's catalogue id and slot values (History only; the route renders them); None for every
        other row. No plain string is ever stored as the words of a note (F4)."""
        first = self.timeline[0] if self.timeline else {}
        if first.get("event") != "info" or "template" not in first:
            return None
        return first["template"], {k: _decode(v) for k, v in first.get("values", {}).items()}

    @property
    def closed_reason(self) -> str | None:
        """Why the system closed it (the lapse reason kept in the timeline); None when a user answered or it is open."""
        if self.answer != kinds.CLOSED_BY_SYSTEM or not self.timeline:
            return None
        return self.timeline[-1].get("reason")

    @property
    def cmp(self) -> str | None:
        return self.timeline[0].get("cmp") if self.timeline else None


def _encode_slot(value: Any) -> Any:
    """A slot value as JSON: Decimal and datetime carry a tag so that read-back gives the exact typed value."""
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": _aware(value).isoformat()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and "$decimal" in value:
        return Decimal(value["$decimal"])
    if isinstance(value, dict) and "$datetime" in value:
        return datetime.fromisoformat(value["$datetime"])
    return value


def _alert(row: Any) -> Alert:
    return Alert(id=row[0], strategy_id=row[1], strategy_name=row[2], rule_id=row[3], kind=row[4], trigger_id=row[5],
                 stage=row[6], value=row[7], threshold=row[8], fired_at=row[9], outcome=row[10], answer=row[11],
                 answered_at=row[12], no_longer_true_since=row[13], dismiss_reason=row[14],
                 timeline=json.loads(row[15]), escalated_at=row[16])


def _not_found(alert_id: object) -> strategy_store.StrategyStoreError:
    return strategy_store.StrategyStoreError(pb.SUGGESTION_NOT_FOUND, f"suggestion {alert_id}")


async def _get(conn: Any, user_ref: str, alert_id: int) -> Alert:
    """One alert of this user on a visible strategy; another user's, a deleted strategy's or a missing id -> not found."""
    if type(alert_id) is not int:
        raise _not_found(alert_id)
    row = (await conn.execute(_ONE, {"id": alert_id, "user_ref": user_ref})).one_or_none()
    if row is None:
        raise _not_found(alert_id)
    return _alert(row)


async def _get_open(conn: Any, user_ref: str, alert_id: int) -> Alert:
    found = await _get(conn, user_ref, alert_id)
    if found.outcome != "open":
        raise strategy_store.StrategyStoreError(pb.SUGGESTION_NOT_OPEN, f"suggestion {alert_id} is {found.outcome}")
    return found


def _aware(at: datetime) -> datetime:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("the event time of an alert must be a timezone-aware datetime")
    return at


def _is_worse(old: Decimal | None, new: Decimal | None, cmp: str | None) -> bool:
    """A worse reading of the same rule: further past the line (a 'le' / 'lt' rule: lower; otherwise higher)."""
    if old is None or new is None:
        return False
    return new < old if cmp in _LESS_IS_WORSE else new > old


async def raise_actionable(conn: Any, user_ref: str, strategy_id: int, rule_id: str, kind: str, *,  # noqa: PLR0913
                           at: datetime, value: Decimal | None, threshold: Decimal | None,
                           trigger_id: str | None = None, stage: str | None = None, **facts: Any) -> Alert:
    """The one way an actionable alert is raised: ``kind`` is the condition that was met, the rest its facts (``facts``
    go to ``playbook_store.open_suggestion``: group, source, cmp, label, unit, approach, ..., target).

    One open row per (strategy, rule): a second call returns the same row; a WORSE value updates value / threshold /
    stage, sets ``escalated_at`` and adds one timeline entry, keeping ``fired_at``; the condition being true again clears
    ``no_longer_true_since`` (one timeline entry); an equal or better value writes nothing. Never closes anything."""
    if kind not in kinds.KINDS or not (kinds.is_actionable(kind) or kind == kinds.LEVEL_WATCH):
        raise ValueError(f"{kind!r} is not an actionable alert kind")
    _aware(at)
    async with conn.begin_nested():
        existing = (await conn.execute(_OPEN_OF_RULE, {"user_ref": user_ref, "strategy_id": strategy_id,
                                                       "rule_id": rule_id})).one_or_none()
        if existing is None:
            created = await pb.open_suggestion(conn, user_ref, strategy_id, rule_id, trigger_id=trigger_id,
                                               stage=stage, value=value, threshold=threshold, kind=kind,
                                               shown_at=at, **facts)
            return await _get(conn, user_ref, created.id)
        current = _alert(existing)
        params = {"id": current.id, "at": at}
        if _is_worse(current.value, value, current.cmp):
            await conn.execute(_UPDATE_FACTS, {
                **params, "value": value, "threshold": threshold, "stage": stage if stage is not None else current.stage,
                "value_text": None if value is None else format(value, "f"),
                "threshold_text": None if threshold is None else format(threshold, "f")})
        elif current.no_longer_true_since is not None:
            await conn.execute(_CLEAR_STOPPED, params)
        return await _get(conn, user_ref, current.id)


async def note_condition(conn: Any, user_ref: str, alert_id: int, *, still_true: bool, at: datetime) -> Alert:
    """The gate's word on the condition. False: ``no_longer_true_since`` is set ONCE (the first time; a repeat changes
    nothing and adds nothing); True after that: it is cleared (one timeline entry). Never closes the alert."""
    _aware(at)
    async with conn.begin_nested():
        await _get_open(conn, user_ref, alert_id)
        await conn.execute(_CLEAR_STOPPED if still_true else _SET_STOPPED, {"id": alert_id, "at": at})
        return await _get(conn, user_ref, alert_id)


async def answer(conn: Any, user_ref: str, alert_id: int, answer: str | None, at: datetime) -> Alert:
    """The user's call on an open alert, stored with its time. The outcome is derived: exit / add_legs -> acted_on,
    continue / confirm_new_shape -> dismissed. Never exits a position: the Exit button opens the usual confirmation."""
    _aware(at)
    async with conn.begin_nested():
        current = await _get_open(conn, user_ref, alert_id)
        allowed = kinds.allowed_answers(current.kind) if current.kind else (kinds.EXIT, kinds.CONTINUE)
        if not isinstance(answer, str) or answer not in allowed:
            raise AlertAnswerRefused(f"{answer!r} is not one of {allowed} for {current.kind or 'this alert'}")
        await pb.close_suggestion(conn, user_ref, alert_id, _OUTCOME_OF[answer], None, answer=answer, answered_at=at)
        return await _get(conn, user_ref, alert_id)


async def dismiss(conn: Any, user_ref: str, alert_id: int, reason: str | None = None) -> Any:
    """The inbox's Dismiss (= "continue with the position"; it stores answer and time). The route goes through here so
    that no module outside the two homes closes an alert-table row."""
    return await pb.dismiss(conn, user_ref, alert_id, reason)


async def act_on(conn: Any, user_ref: str, alert_id: int) -> Any:
    """The inbox's Act on (outcome acted_on, answer continue, as before); see ``dismiss``."""
    return await pb.act_on(conn, user_ref, alert_id)


async def close_by_system(conn: Any, user_ref: str, strategy_id: int, reason: str, *,  # noqa: PLR0913
                          at: datetime | None = None,
                          ids: Iterable[int] | None = None) -> list[Alert]:
    """The position the question is about is gone (``SYSTEM_REASONS``): the open rows of the strategy (or just ``ids``)
    close with answer 'closed_by_system', outcome 'lapsed', the reason kept in the timeline entry. ``condition_stopped``
    and ``superseded_by_worse`` are refused: they no longer end an alert."""
    if reason not in SYSTEM_REASONS:
        raise ValueError(f"{reason!r} is not a reason the system may close an alert for: {SYSTEM_REASONS}")
    chosen = None if ids is None else set(ids)
    at = datetime.now(UTC) if at is None else _aware(at)
    closed: list[Alert] = []
    async with conn.begin_nested():
        rows = (await conn.execute(_OPEN_OF_STRATEGY, {"user_ref": user_ref, "strategy_id": strategy_id})).all()
        for row in rows:
            if chosen is not None and row[0] not in chosen:
                continue
            await pb.lapse(conn, user_ref, row[0], reason, answer=kinds.CLOSED_BY_SYSTEM, answered_at=at)
            closed.append(await _get(conn, user_ref, row[0]))
    return closed


async def close_level_watch(conn: Any, user_ref: str, strategy_id: int, rule_id: str, *, at: datetime) -> Alert | None:
    """ADR-242 (3): the watched level cleared at a candle close, so this episode's record closes (lapsed,
    condition_stopped, no answer); the next crossing opens a new one. Only a level_watch row closes here: any other
    open row of the rule is left alone. None when no such row is open (absent: nothing to close)."""
    _aware(at)
    async with conn.begin_nested():
        row = (await conn.execute(_OPEN_OF_RULE, {"user_ref": user_ref, "strategy_id": strategy_id,
                                                  "rule_id": rule_id})).one_or_none()
        if row is None or row[4] != kinds.LEVEL_WATCH:
            return None
        await pb.lapse(conn, user_ref, row[0], pb.LAPSE_CONDITION_STOPPED)
        return await _get(conn, user_ref, row[0])


async def note_rule_condition(conn: Any, user_ref: str, strategy_id: int, rule_id: str, *, still_true: bool,  # noqa: PLR0913
                              at: datetime) -> Alert | None:
    """The gate's word on one RULE of a strategy (it knows rules, not row ids): ``note_condition`` on the rule's open
    row. None when no row of the rule is open, or when it was answered or closed meanwhile (a race with the user's
    answer is normal: the row is already out of Active, nothing to note)."""
    row = (await conn.execute(_OPEN_OF_RULE, {"user_ref": user_ref, "strategy_id": strategy_id,
                                              "rule_id": rule_id})).one_or_none()
    if row is None:
        return None
    try:
        return await note_condition(conn, user_ref, row[0], still_true=still_true, at=at)
    except strategy_store.StrategyStoreError as gone:
        if gone.code not in (pb.SUGGESTION_NOT_OPEN, pb.SUGGESTION_NOT_FOUND):
            raise
        return None


async def record_held(conn: Any, user_ref: str, strategy_id: int, rule_id: str, **facts: Any) -> Any:
    """A capped or quiet-time crossing (REQ-170 AC-4): a stored row that is never an alert and never counted; written
    here so that no other module writes alert-table rows."""
    return await pb.record_held(conn, user_ref, strategy_id, rule_id, **facts)


async def close_expired(conn: Any, user_ref: str, strategy_id: int, expiry: Any, today: Any, *,  # noqa: PLR0913
                        at: datetime | None = None) -> list[Alert]:
    """D-30: a strategy whose last expiry is before ``today`` closes its open alerts as contract_expired; an unknown
    expiry or day closes nothing (never a guess)."""
    if expiry is None or today is None or not expiry < today:
        return []
    return await close_by_system(conn, user_ref, strategy_id, pb.LAPSE_CONTRACT_EXPIRED, at=at)


async def unanswered(conn: Any, user_ref: str) -> list[Alert]:
    """The Active list: every open alert of the user's visible strategies (ADR-293: a deleted one is hidden)."""
    return [_alert(r) for r in await _rows(conn, _UNANSWERED_SQL, user_ref)]


async def unanswered_count(conn: Any, user_ref: str) -> int:
    """The bell (ADR-330 (4)): the length of the one list, so it cannot differ from the Active rows."""
    return len(await unanswered(conn, user_ref))


async def history(conn: Any, user_ref: str) -> list[Alert]:
    """Answered, system-closed and informational rows, newest first (never counted)."""
    return [_alert(r) for r in await _rows(conn, _HISTORY_SQL, user_ref)]


async def _rows(conn: Any, sql: str, user_ref: str) -> list[Any]:
    statement, params = pb.scoped(sql)
    return list((await conn.execute(statement, {**params, "user_ref": user_ref})).all())


async def inform(conn: Any, user_ref: str, strategy_id: int, kind: str, template_id: str,  # noqa: PLR0913
                 values: dict[str, Any], *, at: datetime) -> int:
    """An informational message (ADR-330 (3b)): a History row, answered at once ('noted'), never open, never counted.
    The words are a catalogue id plus its slot values (rendered when read, so History can never hold a plain string);
    ``values`` are checked by rendering once now. Returns the row id."""
    if not kinds.is_informational(kind):
        raise ValueError(f"{kind!r} is not an informational alert kind")
    render_explanation(template_id, **values)  # unknown id, missing/extra slot or wrong type: refused, nothing written
    _aware(at)
    async with conn.begin_nested():
        await pb.require_owned(conn, user_ref, strategy_id)
        return int((await conn.execute(_INSERT_NOTE, {
            "strategy_id": strategy_id, "rule_id": f"info:{kind}", "kind": kind, "at": at, "template": template_id,
            "values": json.dumps({k: _encode_slot(v) for k, v in values.items()})})).scalar_one())
