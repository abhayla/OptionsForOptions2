"""Positions > Adjustment opportunities (GC-ADJ2 step 5; REQ-162 AC-1..AC-3, REQ-112 AC-1/AC-2/AC-4/AC-6, REQ-045 AC-8).

- GET /api/adjustment-opportunities: every suggestion record of the user's strategies (paper and imported real),
  newest first, grouped as the check that opened them groups them (one group = one strategy at one check; each record
  keeps its own outcome), with the strategy's saved name (the user-text slot), the source label ("Adjustment
  opportunity detected" for a system playbook's flag, "Your rule was triggered" for the user's own playbook or the
  strategy's plan), the condition in plain words, the outcome's text, and the outcome counts. An acted-on record of a
  paper strategy says Paper - not sent to Zerodha (ADR-135). Empty -> "No adjustment opportunities".
- POST /api/adjustment-opportunities/{id}/dismiss {reason}: reason from the closed list (DISMISS_REASONS) or none;
  outcome dismissed, shown as "You dismissed this" (REQ-112 AC-6).
- POST /api/adjustment-opportunities/{id}/acted-on: the compare's prepare button; outcome acted on.

Refusals (nothing written on any): another user's or a missing id -> suggestion_not_found (404); a final record ->
suggestion_not_open (409); a reason off the list -> 422. Each outcome change is one timeline entry (the store's
UPDATE, guarded by the database). Suggest-only (ADR-003): no route here reaches an order.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment.held_reasons import HELD_TEXT_IDS
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.strategy.stored_form import shown_name
from pydantic import BaseModel, ConfigDict

from ofo_app import playbook_store as store
from ofo_app.adjustment_check import condition_line, condition_line_t19, stage_name_text
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused
from ofo_app.strategy_store import StrategyStoreError

router = APIRouter(route_class=ClosedRoute)
ID_MAX = 9_223_372_036_854_775_807  # BIGSERIAL: a larger number is simply not there
OUTCOMES = ("open", "dismissed", "acted_on", "completed", "partly_completed", "lapsed")
_STATUS = {store.SUGGESTION_NOT_FOUND: Failure.NOT_FOUND, store.SUGGESTION_NOT_OPEN: Failure.CONFLICT}
_LABEL = {store.SOURCE_SYSTEM: "adjust_check_flag_system", store.SOURCE_OWN: "adjust_check_flag_user"}

Outcome = Literal["open", "dismissed", "acted_on", "completed", "partly_completed", "lapsed"]


class DismissIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reason: Literal["expected_within_plan", "will_act_later", "not_relevant", "other"] | None = None


class OpportunityOut(ApiModel):
    id: int
    rule_id: Identifier
    trigger_id: Identifier | None
    stage: CatalogueText | None
    value: Money | None
    threshold: Money | None
    condition: CatalogueText | None
    shown_at: datetime.datetime
    outcome: Outcome
    outcome_text: CatalogueText
    detail: CatalogueText | None  # a dismiss reason or why it lapsed
    can_act: bool  # open: Dismiss and acted on are allowed


class GroupOut(ApiModel):
    group: Identifier
    strategy_id: int
    strategy_name: CatalogueText
    shown_at: datetime.datetime
    label: CatalogueText
    summary: CatalogueText | None  # "3 adjustment conditions triggered" for a group of several (REQ-045 AC-8)
    has_open: bool  # an open record links to the compare of its strategy (REQ-162 AC-3)
    records: list[OpportunityOut]


class CountOut(ApiModel):
    outcome: Outcome
    text: CatalogueText
    count: int


class ReasonOut(ApiModel):
    id: Identifier
    text: CatalogueText


class HeldOut(ApiModel):
    """REQ-170 AC-4: a crossing the alert gate held (daily limit / quiet time). Not a record: no outcome, nothing to
    act on, no compare link."""

    id: int
    strategy_id: int
    strategy_name: CatalogueText
    rule_id: Identifier
    trigger_id: Identifier | None
    reason: Literal["daily_limit", "quiet_time"]
    text: CatalogueText
    held_at: datetime.datetime


class InboxOut(ApiModel):
    groups: list[GroupOut]
    held: list[HeldOut]
    counts: list[CountOut]
    empty_text: CatalogueText | None
    dismiss_reasons: list[ReasonOut]


class SuggestionOut(ApiModel):
    id: int
    outcome: Outcome
    outcome_text: CatalogueText


def outcome_text(s: store.Suggestion, paper: bool) -> Any:
    if s.outcome == "acted_on" and paper:
        return render_explanation("suggestion_outcome_acted_on_paper")
    return render_explanation(f"suggestion_outcome_{s.outcome}")


def _detail(s: store.Suggestion) -> Any:
    if s.outcome == "dismissed" and s.dismiss_reason in store.DISMISS_REASONS:
        return render_explanation(f"suggestion_dismiss_{s.dismiss_reason}")
    if s.lapse_reason is not None:
        return render_explanation(f"suggestion_lapsed_{s.lapse_reason}")
    return None


def condition_text(s: store.Suggestion) -> Any:
    """A record's condition in the catalogue's words (the inbox line; the adjustment history's Why, REQ-163 AC-1)."""
    if s.cmp not in ("le", "ge", "lt") or s.trigger_id is None or s.value is None or s.threshold is None:
        return None
    if s.trigger_id == "T-19" and s.approach is not None and s.approach_cost is not None:  # ADR-221: as the check
        return condition_line_t19(s.label, format(s.value, "f"), format(s.threshold, "f"), s.approach,
                                  s.approach_cost, s.unpriced)
    return condition_line(s.trigger_id, s.label, s.unit, format(s.value, "f"), format(s.threshold, "f"))


def _record(s: store.Suggestion, paper: bool) -> dict:
    return {"id": s.id, "rule_id": s.rule_id, "trigger_id": s.trigger_id,
            "stage": stage_name_text(s.stage), "value": s.value, "threshold": s.threshold,
            "condition": condition_text(s), "shown_at": s.shown_at, "outcome": s.outcome,
            "outcome_text": outcome_text(s, paper), "detail": _detail(s), "can_act": s.outcome == "open"}


def held_body(rows: list[store.HeldInboxRow]) -> list[dict]:
    """The held crossings in the catalogue's words (held_reasons.HELD_TEXT_IDS), newest first."""
    return [{"id": h.id, "strategy_id": h.strategy_id, "strategy_name": shown_name(h.strategy_name),
             "rule_id": h.rule_id, "trigger_id": h.trigger_id, "reason": h.reason,
             "text": render_explanation(HELD_TEXT_IDS[h.reason]), "held_at": h.held_at} for h in rows]


def inbox_body(rows: list[store.InboxRow], held: list[store.HeldInboxRow] | None = None) -> dict:
    groups: dict[str, dict] = {}
    for row in rows:  # newest first; a group's first row seen is its newest record
        s = row.suggestion
        key = f"{s.strategy_id}-{s.group or s.id}"
        g = groups.get(key)
        if g is None:
            label = _LABEL.get(s.source or "", _LABEL[store.SOURCE_SYSTEM])
            g = groups[key] = {"group": key, "strategy_id": s.strategy_id,
                               "strategy_name": shown_name(row.strategy_name), "shown_at": s.shown_at,
                               "label": render_explanation(label), "records": []}
        g["records"].append(_record(s, row.paper))
    for g in groups.values():
        g["records"].sort(key=lambda r: (r["rule_id"], r["id"]))
        n = len(g["records"])
        g["summary"] = render_explanation("suggestion_group_count", count=n) if n > 1 else None
        g["has_open"] = any(r["can_act"] for r in g["records"])
    counted = {o: sum(1 for r in rows if r.suggestion.outcome == o) for o in OUTCOMES}
    return {"groups": list(groups.values()), "held": held_body(held or []),
            "counts": [{"outcome": o, "text": render_explanation(f"suggestion_outcome_{o}"), "count": counted[o]}
                       for o in OUTCOMES],
            "empty_text": None if rows else render_explanation("suggestion_inbox_empty"),
            "dismiss_reasons": [{"id": r, "text": render_explanation(f"suggestion_dismiss_{r}")}
                                for r in store.DISMISS_REASONS]}


def open_counts(rows: list[store.InboxRow]) -> dict[int, int]:
    """GC-MU A3 (ADR-230 (2)): open records per strategy, by the inbox's own definition (outcome "open", as
    `can_act` and the "open" count above); a strategy with none is absent. One definition, read from `store.inbox`."""
    counts: dict[int, int] = {}
    for row in rows:
        if row.suggestion.outcome == "open":
            counts[row.suggestion.strategy_id] = counts.get(row.suggestion.strategy_id, 0) + 1
    return counts


def open_mark(count: int) -> Any:
    """The card's words for `count` open records, or None for none (no mark at 0)."""
    if count < 1:
        return None
    if count == 1:
        return render_explanation("suggestion_open_count_one")
    return render_explanation("suggestion_open_count", count=count)


def _id(suggestion_id: int) -> int:
    if not 1 <= suggestion_id <= ID_MAX:
        raise StrategyStoreError(store.SUGGESTION_NOT_FOUND, f"suggestion {suggestion_id}")
    return suggestion_id


async def _close(db: Any, work: Any) -> SuggestionOut:
    """One store call: commit on success; a refusal rolls back (nothing written) and answers its catalogue text."""
    try:
        s = await work()
        await db.commit()
    except StrategyStoreError as exc:
        await db.rollback()
        if exc.code not in _STATUS:
            raise
        raise StrategyRefused(exc.code, _STATUS[exc.code], message=render(exc.code)) from None
    except Exception:
        await db.rollback()
        raise
    return SuggestionOut.model_validate({"id": s.id, "outcome": s.outcome, "outcome_text": outcome_text(s, False)})


@router.get("/api/adjustment-opportunities", response_model=InboxOut)
async def adjustment_opportunities(db: Annotated[Any, Depends(get_db)],
                                   user_ref: Annotated[str, Depends(current_user_ref)]) -> InboxOut:
    return InboxOut.model_validate(inbox_body(await store.inbox(db, user_ref), await store.held_inbox(db, user_ref)))


@router.post("/api/adjustment-opportunities/{suggestion_id}/dismiss", response_model=SuggestionOut)
async def dismiss_opportunity(suggestion_id: int, body: DismissIn, db: Annotated[Any, Depends(get_db)],
                              user_ref: Annotated[str, Depends(current_user_ref)]) -> SuggestionOut:
    return await _close(db, lambda: store.dismiss(db, user_ref, _id(suggestion_id), body.reason))


@router.post("/api/adjustment-opportunities/{suggestion_id}/acted-on", response_model=SuggestionOut)
async def acted_on_opportunity(suggestion_id: int, db: Annotated[Any, Depends(get_db)],
                               user_ref: Annotated[str, Depends(current_user_ref)]) -> SuggestionOut:
    return await _close(db, lambda: store.act_on(db, user_ref, _id(suggestion_id)))
