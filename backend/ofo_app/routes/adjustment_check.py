"""GET /api/strategies/{id}/adjustment-check (GC-ADJ2 step 1C; REQ-158 AC-5, REQ-159 AC-2, REQ-160 AC-3, REQ-045 AC-1,
F-71): the tracked strategy's playbook evaluated now, through the adjustment-approaches route's own seams (tracked
strategy, market, REST spot, margin, charge rates); the logic is ``ofo_app.adjustment_check``.

Answer states: strategy not found / another user's -> the approaches route's not-found answer; legs unreadable
(TrackedUnreadable) -> its refusal; type None -> playbook source ``none`` and no results; not connected or no spot ->
every rule ``not_checked`` with its reason (never a 500, never a flag); the records' store unreadable -> a refusal
(503), never an empty list. ADR-237 (6): this check writes NOTHING (no record, no lapse, no rule memory: only the
background worker writes, through the alert gate); it shows the current condition and the stored records.
Suggest-only (ADR-003): nothing here places an order. Wording: a system playbook's flag is "Adjustment opportunity
detected", the user's own playbook or plan's "Your rule was triggered" (REQ-045 AC-1, Q252); a rule true at entry is
"Already true when tracking started" (F-71).
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import stop_lines as sl
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.checks import pnl_amount as rupee
from ofo.charges import ChargeRates
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.money import PAISE
from ofo.timeutil import IST
from sqlalchemy.exc import SQLAlchemyError

from ofo_app import adjustment_check as check
from ofo_app import playbook_store, scenario_mode
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.outcome_margin import PlannedOrderIn
from ofo_app.routes.adjustment import (
    ApproachMargin,
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_approach_margin,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
    margin_block,
    release_connection,
)
from ofo_app.routes.adjustment_opportunities import condition_text
from ofo_app.routes.adjustment_preferences import UserPreferences, UserValuesIn
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import (
    MarketContext,
    get_market_context,
    judge_spot,
    load_charge_rates,
)
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_NOT_AVAILABLE = "user_input_request_not_available"


class CheckPlaybookOut(ApiModel):
    source: Literal["plan", "active", "system", "none"]
    id: int | None
    status: Literal["approved", "draft"] | None
    draft: bool


class CheckStageOut(ApiModel):
    name: CatalogueText | None  # the stage name as the user typed it (spaces allowed)
    index: int | None


class CheckResultOut(ApiModel):
    kind: Literal["flag", "not_checked", "already_true"]
    rule_id: Identifier
    trigger_id: Identifier
    cmp: Literal["le", "ge", "lt"] | None
    value: Money | None  # None for a clock trigger (T-10b) and for a not-checked rule
    threshold: Money | None
    reason: CatalogueText | None
    wording: CatalogueText | None
    condition: CatalogueText | None = None  # the condition in words, from the body's label and unit
    #: GC-ICFIX u142: a fired stop's loss now and stop line in rupees and percent, and the time it fired
    #: (all server text)
    stop_text: CatalogueText | None = None
    fired_at: datetime.datetime | None = None  # issue 12: when its open record was shown
    #: ADR-309: the rule's value at this check and that check's time text; `value` of a held fired rule is the value
    #: that fired it
    live_value: Money | None = None
    live_as_of_text: CatalogueText | None = None
    suggestion_id: int | None = None  # a flag's open REQ-112 record (Dismiss / acted on name it)
    note: CatalogueText | None = None  # ADR-217: "You dismissed this" on a flag whose dismissed record still holds


class CheckLimitOut(ApiModel):
    """ADR-304: the limit a rule acts on for this trade now, the evaluator's own number (``playbook_eval.limits_now``)."""  # noqa: E501

    rule_id: Identifier
    trigger_id: Identifier
    threshold: Money | None  # the % now (the credit line: the multiple); None = nothing to compare
    amount: Money | None  # a stop's rupee loss, where there is one
    later: list[Money]  # the later stages' values
    tightened_by: Money | None  # the expiry-day tightening X % when it is applied now
    state: Literal["checked", "not_checked", "already_true"]
    reason: CatalogueText | None  # the evaluator's reason text when not checked
    text: CatalogueText | None  # the one sentence the card prints for this limit; None -> the card says could-not-load
    # ADR-296: "already_true" only: the adjustment number it has been true since (None = the entry)
    after: int | None = None
    # why a not-checked row is not (e.g. target_unset: the trade's Target was emptied)
    reason_code: Identifier | None = None


class CheckPauseOut(ApiModel):
    until: Identifier  # HHMM IST, e.g. 1030 (an Identifier has no ':')
    text: CatalogueText


class AdjustmentCheckOut(ApiModel):
    strategy_id: int
    #: GC-ICFIX u141: the time this check was evaluated, and its display text ("As of 10:42:17 AM IST")
    as_of: datetime.datetime
    as_of_text: CatalogueText
    strategy_type: Identifier | None
    type_name: CatalogueText | None
    playbook: CheckPlaybookOut
    stage: CheckStageOut
    withheld: CatalogueText | None
    results: list[CheckResultOut]
    # ADR-304: the limits the target / stop rules act on now (empty: no playbook / paused)
    limits: list[CheckLimitOut] = []  # noqa: RUF012
    #: A-38 (GC-IC1 4a): the user's pause in force at the check's own time -> {until, text} and no evaluation (the
    #: worker skips it too); none, cleared or expired -> None
    paused: CheckPauseOut | None = None


async def pause_in_force(db: Any, user_ref: str, strategy_id: int, now: datetime.datetime) -> dict | None:
    """The check's pause block at ``now`` (the market reader's clock, the check's own time); None when not paused."""
    from ofo.adjustment import monitor_pause  # noqa: PLC0415 - A-38

    from ofo_app import strategy_pause_store  # noqa: PLC0415 - A-38
    until = await strategy_pause_store.pause_of(db, user_ref, strategy_id)
    if until is None or not monitor_pause.in_force(until, now):
        return None
    end = until.astimezone(IST).time().replace(second=0, microsecond=0)
    return {"until": f"{end:%H%M}", "text": render_explanation("monitor_pause_shown", time=end)}


#: the shown scale of a check value and threshold (the scenario fixtures' "0.3416" / "0.5000"); the evaluator keeps
#: the exact values, only the answer is rounded (half-up, GC-ADJ2 step 5 item 1)
SHOWN_PLACES = Decimal("0.0001")


def _num(v: Decimal | str | None) -> Decimal | None:
    if not isinstance(v, Decimal):  # a clock value or UNLIMITED is not a number
        return None
    return v.quantize(SHOWN_PLACES, rounding=ROUND_HALF_UP)


def _condition(r: pe.Flag | pe.AlreadyTrue, body: Mapping | None,
               cheapest: tuple[str, Decimal, int] | None = None, target: check.TargetFigures | None = None) -> Any:
    """The condition in words from the evaluated body's own label and unit; None without a comparison. T-19 also names
    the cheapest offered approach and its cost (``cheapest``, ADR-221)."""
    if r.cmp is None:
        return None
    if isinstance(r, HeldFlag):  # ADR-309: the record's own figures, never the live ones beside them
        target = None if r.target is None else check.TargetFigures(*r.target)
        body, cheapest = None, None  # no live label, unit or T-19 approach, even when the record has no sentence
        if r.record is not None and (own := condition_text(r.record)) is not None:
            return own
    value, threshold = _num(r.value), _num(r.threshold)
    label, unit = check.trigger_words(body, r.trigger_id)
    shown = str(r.value) if value is None else str(value)
    limit = str(r.threshold) if threshold is None else str(threshold)
    if r.trigger_id == "T-19" and cheapest is not None:
        return check.condition_line_t19(label, shown, limit, *cheapest)
    side = next((h.side for h in getattr(r, "members", ()) if h.trigger_id == r.trigger_id), None)  # D-58: tested side
    return check.condition_line(r.trigger_id, label, unit, shown, limit, r.beyond, target, side)


def result_out(r: pe.Result, flag_wording: Any, opened: dict[str, int] | None = None, *,  # noqa: PLR0913
               dismissed: frozenset[str] = frozenset(), body: Mapping | None = None,
               cheapest: tuple[str, Decimal, int] | None = None, target: check.TargetFigures | None = None) -> dict:
    # dismissed and body are keyword-only: a positional body once landed in dismissed (TypeError on a None body)
    if isinstance(r, pe.Flag):
        return {"kind": "flag", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": r.cmp, "value": _num(r.value),
                "threshold": _num(r.threshold), "reason": None, "wording": flag_wording,
                "condition": _condition(r, body, cheapest, target), "suggestion_id": (opened or {}).get(r.rule_id),
                "note": render_explanation("suggestion_outcome_dismissed") if r.rule_id in dismissed else None}
    if isinstance(r, pe.AlreadyTrue):
        return {"kind": "already_true", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": r.cmp,
                "value": _num(r.value), "threshold": _num(r.threshold), "reason": None,
                "wording": render("adjust_trigger_already_true_after", n=r.after) if r.after else render(r.code),
                "condition": _condition(r, body, cheapest, target)}
    return {"kind": "not_checked", "rule_id": r.rule_id, "trigger_id": r.trigger_id, "cmp": None, "value": None,
            "threshold": None, "reason": render(r.code, **dict(r.slots)), "wording": None}


def limit_text(x: pe.LimitNow, reason: Any, percent_stop_checked: bool, target_unset: bool = False) -> Any:  # noqa: C901 - one sentence per answer state
    """ADR-304 (3): the one sentence for a limit row, from the evaluator's own numbers
    (the card prints it, derives nothing).
    A rule that is not checked says why and shows NO number, even when the row still carries one; a row the card cannot
    state (an unknown state, a checked row with nothing to compare) -> None."""
    if x.state not in ("checked", "not_checked", "already_true"):
        return None
    target, credit = x.trigger_id == "T-07" or x.rule_id == sl.RUPEE_PROFIT_RULE, x.rule_id == sl.CREDIT_RULE
    if x.state == "not_checked":
        # ADR-305: the Target was emptied for this trade; not "switched off in the rule set"
        if target and target_unset:
            return render_explanation("limit_target_none")
        return None if reason is None else render_explanation("limit_target_off" if target else "limit_stop_off", reason=reason)  # noqa: E501
    if not isinstance(x.threshold, Decimal):
        return None
    pct = x.threshold.normalize()
    money = isinstance(x.amount, Decimal)
    if x.rule_id in sl.RUPEE_RULES:  # ADR-330 (5): the typed rupee level itself, whole trade, before charges
        line = render_explanation("limit_target_rupees" if target else "limit_stop_rupees", amount=x.threshold)
    elif target:
        line = render_explanation("limit_target", pct=pct)
    elif credit:
        line = render_explanation("limit_stop_credit", multiple=pct, amount=x.amount) if money else \
            render_explanation("limit_stop_credit_plain", multiple=pct)
    else:
        line = render_explanation("limit_stop_loss", pct=pct, amount=x.amount) if money else \
            render_explanation("limit_stop_loss_plain", pct=pct)
    if not credit and x.later and isinstance(x.later[-1], Decimal) and x.later[-1] != x.threshold:
        line = render_explanation("limit_later", line=line, pct=x.later[-1].normalize())
    if isinstance(x.tightened_by, Decimal):
        line = render_explanation("limit_tightened", line=line, pct=x.tightened_by.normalize())
    if x.state == "already_true":
        line = (render_explanation("limit_already_true_after", line=line, n=x.after) if x.after > 0
                else render_explanation("limit_already_true", line=line))
    if credit and percent_stop_checked:  # two stops race: the first to be reached acts (ADR-247)
        line = render_explanation("plan_stop_words_first", words=line)
    return line


def target_is_unset(source: str, guards: object) -> bool:
    """ADR-305: the plan's Target was emptied for this trade (the percent guard is ""), AND no readable rupee target
    stands in for it (ADR-330 (5): a rupee target save sets the percent guard to "" on purpose)."""
    if source != "plan" or not isinstance(guards, Mapping) or guards.get("profit_target_pct_of_max_profit") != "":
        return False
    raw = guards.get(sl.RUPEE_PROFIT_KEY)
    try:
        return not (isinstance(raw, str) and rupee.level_of(raw) is not None)
    except ValueError:
        return True


def limits_out(limits: tuple[pe.LimitNow, ...], target_unset: bool = False) -> list[dict]:
    """The limits now as the reply states them: numbers in the reply's shown scale, the reason as its catalogue text."""
    race = any(x.trigger_id in (sl.TRIGGER_MAX_LOSS, sl.RUPEE_LOSS_RULE) and x.state != "not_checked" for x in limits)
    out = []
    for x in limits:
        reason = None if x.reason is None else render(x.reason, **dict(x.slots))
        out.append({"rule_id": x.rule_id, "trigger_id": x.trigger_id, "threshold": _num(x.threshold), "amount": _num(x.amount),  # noqa: E501
                    "later": [_num(v) for v in x.later], "tightened_by": _num(x.tightened_by), "state": x.state,
                    "reason": reason, "text": limit_text(x, reason, race, target_unset),
                    "after": x.after if x.state == "already_true" and x.after > 0 else None,
                    "reason_code": ("target_unset"
                                    if target_unset and x.trigger_id == "T-07" and x.state == "not_checked" else None)})
    return out


def _held_stop_line(r: pe.Flag, credit: bool) -> Any:
    """ADR-309: a stop kept fired from its record: the record's loss and line only; None if not numbers."""
    if not all(isinstance(v, Decimal) for v in (r.value, r.threshold)):
        return None
    if credit:
        return render_explanation("stop_held_credit", loss=_num(r.value), stop=_num(r.threshold))
    return render_explanation("stop_held_loss", loss_pct=_num(r.value).normalize(),
                              stop_pct=_num(r.threshold).normalize())


def _reached(line: Any, at: datetime.datetime, today: datetime.date | None) -> Any:
    """The stop sentence with when it was reached: the time, and the date too when that was not today (IST, the server's
    day; ``today`` None = the time only)."""
    day = at.astimezone(IST).date()
    if today is None or day == today:
        return render_explanation("stop_fired_at", line=line, time=at)
    return render_explanation("stop_fired_on", line=line, date=day, time=at)


def stop_text(
    r: pe.Result, limits: tuple[pe.LimitNow, ...], pnl: Any, fired_at: Mapping[str, datetime.datetime],
    today: datetime.date | None = None,
) -> Any:
    """GC-ICFIX u142: a fired stop's warning detail, all from the evaluator's numbers: the loss now and the stop line in
    rupees and percent (the credit stop: rupees and the multiple), and when its record opened.
    Any figure missing -> None."""
    if not isinstance(r, pe.Flag):
        return None
    credit = r.rule_id == sl.CREDIT_RULE
    if not credit and r.trigger_id != sl.TRIGGER_MAX_LOSS:
        return None
    at = fired_at.get(r.rule_id)
    if isinstance(r, HeldFlag):  # ADR-309: the record's own figures, never the loss now beside them
        line = _held_stop_line(r, credit)
        return line if line is None or at is None else _reached(line, at, today)
    lim = next((x for x in limits if x.rule_id == r.rule_id and (credit or x.trigger_id == sl.TRIGGER_MAX_LOSS)), None)
    if lim is None or not all(isinstance(v, Decimal) for v in (lim.amount, lim.threshold, pnl, r.value, r.threshold)):
        return None
    loss = max(-pnl, Decimal(0)).quantize(PAISE, rounding=ROUND_HALF_UP)
    try:
        if credit:
            line = render_explanation(
                "stop_fired_credit", loss=loss, stop=lim.amount, multiple=lim.threshold.normalize())
        else:
            line = render_explanation("stop_fired_loss", loss=loss, loss_pct=_num(r.value).normalize(), stop=lim.amount,
                                      stop_pct=_num(r.threshold).normalize())
        return line if at is None else _reached(line, at, today)
    except (TypeError, ValueError):
        return None


def t19_record(trigger_id: str, cheapest: tuple[str, Decimal, int] | None) -> dict:
    """ADR-221: a T-19 record keeps the approach, cost and unpriced count it was shown with (the list draws them)."""
    if trigger_id != "T-19" or cheapest is None:
        return {}
    return {"approach": cheapest[0], "approach_cost": cheapest[1], "unpriced": cheapest[2]}


def target_record(trigger_id: str, state: pe.StrategyState | None) -> dict:
    """ADR-294 (2): a T-07 record keeps the two figures it was shown with (exact text; the record's own timeline entry,
    no new column), so the inbox and the history draw the same sentence as the check screen. Others: nothing."""
    figures = check.target_of(state) if trigger_id == "T-07" else None
    if figures is None:
        return {}
    return {"target": {"before": format(figures.before, "f"),
                       "after": None if figures.after is None else format(figures.after, "f"),
                       "reason": figures.reason}}


def cheapest(state: pe.StrategyState) -> tuple[str, Decimal, int] | None:
    """The T-19 approach, cost and unpriced count the check used (ADR-221); None when it had none."""
    if state.adjustment_approach is None or state.adjustment_cost is None:
        return None
    return state.adjustment_approach, state.adjustment_cost, state.adjustment_unpriced


async def stored_records(db: Any, user_ref: str, strategy_id: int,
                         ev: pe.Evaluation,
                         ) -> tuple[dict[str, int], frozenset[str], dict[str, datetime.datetime], list[pe.Result]]:
    """ADR-237 (6): the screen READS the records; only the background worker opens and lapses them, through the one
    gate (``ofo.adjustment.alert_gate``, stored by ``background.DbGateStore``). Returns (rule id -> id of its open
    record, for each flagged rule that has one; the flagged rules whose latest record is dismissed and none is open,
    for the ADR-217 "You dismissed this" note). Writes nothing. A store read that fails raises
    ``StrategyRefused`` (never an empty answer that would read as "nothing is open")."""
    try:
        open_recs = await playbook_store.open_suggestions(db, user_ref, strategy_id)
        open_now = {rec.rule_id: rec.id for rec in open_recs}
        held = await playbook_store.dismissed_holding(db, user_ref, strategy_id)
    except SQLAlchemyError as exc:
        log.warning("adjustment check: records of strategy %s unreadable: %s", strategy_id, type(exc).__name__)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.UPSTREAM_BUSY) from None
    results = shown_results(ev, open_recs)
    flagged = {r.rule_id for r in results if isinstance(r, pe.Flag)}
    opened = {rid: sid for rid, sid in open_now.items() if rid in flagged}
    fired = {rec.rule_id: rec.shown_at for rec in open_recs if rec.rule_id in opened}
    return opened, frozenset(rid for rid in held if rid in flagged and rid not in opened), fired, results


@dataclass(frozen=True)
class HeldFlag(pe.Flag):
    """ADR-309: a rule shown fired from its open record while the check reads it clear; the figures are the record's.
    ``target`` = the T-07 record's own (before, after, reason) shown when it fired; None when none was stored."""

    target: tuple[Decimal, Decimal | None, str | None] | None = None
    #: #709 item 7: the stored record itself; its sentence is ``condition_text(record)``, so the label, unit, beyond
    #: and T-19 approach are the record's, never the live playbook's or the live check's
    record: Any = None


def live_fields(rule_id: str, live: Mapping[str, Decimal], fired_at: Mapping[str, datetime.datetime],
                as_of_text: Any) -> dict:
    """The per-rule fields beside the evaluator's answer: when its record opened, and the value now WITH the check's own
    time (ADR-309)."""
    value = live.get(rule_id)
    return {"fired_at": fired_at.get(rule_id), "live_value": value,
            "live_as_of_text": None if value is None else as_of_text}


def _from_record(flag: pe.Flag, rec: Any) -> pe.Flag:
    """D-31: ``flag`` as its open record ``rec`` shows it (the record's value, limit and sentence); the flag itself when
    the rule has no open record or the record stored no comparison to show."""
    if (rec is None or rec.trigger_id is None or rec.value is None or rec.threshold is None
            or (flag.cmp or rec.cmp) is None):
        return flag
    return HeldFlag(flag.rule_id, flag.trigger_id, flag.stage_name, rec.value,
                    rec.threshold if rec.limit is None else rec.limit, flag.cmp or rec.cmp, flag.members, flag.beyond,
                    target=getattr(rec, "target", None), record=rec)


def shown_results(ev: pe.Evaluation, open_recs: Any) -> list[pe.Result]:
    """ADR-309 (1): the shown fired state follows the gate's open RECORD. A rule the check evaluated false
    (``ev.clear``), or could not check at all (market closed, prices not live: ``NotChecked``), that still has an open
    record is shown as fired, with the figures that fired it; a not-checked rule keeps its not-checked line beside it.
    The gate (never the screen) ends the record. A rule with NO open record is left as the evaluator says it (not
    checked, already true): nothing is invented where no record exists."""
    cmp_of = {v.rule_id: v.cmp for v in ev.values}
    # GC-ICFIX issue 19: a close (prices not live) reads the rule "not checked", which is not "cleared": the open record
    # stays shown as fired with its own figures, the not-checked line beside it (the stop must not vanish at 15:30)
    unread = {r.rule_id for r in ev.results if isinstance(r, pe.NotChecked)}
    # D-31 (ADR-309 (1)): a rule that is firing now AND has an open record is shown from that record too (its value, its
    # sentence), the figures the opportunity list shows; the value of this poll is the separate "Now" value
    by_rule = {rec.rule_id: rec for rec in open_recs}
    return [*(_from_record(x, by_rule.get(x.rule_id)) if isinstance(x, pe.Flag) else x for x in ev.results),
            *(HeldFlag(rec.rule_id, rec.trigger_id, rec.stage, rec.value,
                       rec.threshold if rec.limit is None else rec.limit,
                       cmp_of.get(rec.rule_id) or rec.cmp, target=getattr(rec, "target", None), record=rec)
              for rec in open_recs
              if ((rec.rule_id in ev.clear and rec.rule_id in cmp_of) or rec.rule_id in unread)
              and rec.trigger_id is not None and rec.value is not None and rec.threshold is not None
              and (cmp_of.get(rec.rule_id) or rec.cmp) is not None)]


def live_values(ev: pe.Evaluation) -> dict[str, Decimal]:
    """The rule's value at this check (its own as-of is the reply's ``as_of``), shown beside a held fired state."""
    return {v.rule_id: q for v in ev.values if (q := _num(v.value)) is not None}


async def current_margin(margin_of: ApproachMargin, tracked: Any, market: Any) -> dict | None:
    try:
        legs = [PlannedOrderIn(market.instrument_ids[x.tradingsymbol], x.side, x.lots, x.entry)
                for x in tracked.position.legs]
        return margin_block(await margin_of(legs))
    except Exception:  # noqa: BLE001 - a margin read failing is "margin not stated" (T-16 not checked), never a 500
        log.warning("adjustment check: margin read failed")
        return None


@dataclass(frozen=True)
class CheckRun:
    """One adjustment check as ``run_check`` leaves it: the reply, and the pieces it was built from (None when no
    evaluation ran: no playbook, or the user's pause is in force). The plan-watch route reads these, never a second
    evaluation (ADR-008)."""

    out: AdjustmentCheckOut
    state: pe.StrategyState | None = None
    ev: pe.Evaluation | None = None
    body: Mapping | None = None
    tracked: Any = None
    market: Any = None
    spot: Decimal | None = None  # the judged spot; None = no usable spot
    fresh: bool | None = None  # the prices' health (check.prices_fresh): True fresh, False stale, None unknown


@router.get("/api/strategies/{strategy_id}/adjustment-check", response_model=AdjustmentCheckOut)
async def adjustment_check(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int,
        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        prefs: UserPreferences, user_values: UserValuesIn) -> AdjustmentCheckOut:
    return (await run_check(strategy_id, db=db, user_ref=user_ref, tracked_reader=tracked_reader,
                            market_reader=market_reader, rest_reader=rest_reader, margin_of=margin_of, ctx=ctx,
                            rates=rates, prefs=prefs, user_values=user_values)).out


async def run_check(  # noqa: PLR0913 - the route's inputs, passed on
        strategy_id: int, *, db: Any, user_ref: str, tracked_reader: TrackedReader, market_reader: MarketReader,
        rest_reader: RestSpotReader, margin_of: ApproachMargin, ctx: MarketContext | None,
        rates: ChargeRates | None, prefs: Any, user_values: Any) -> CheckRun:
    from ofo_app.adjustment_readers import (  # noqa: PLC0415 - imports routes.adjustment
        TrackedExited,
        TrackedUnreadable,
        entry_facts_in,
    )
    from ofo_app.scenario_guard import check_screen_isolation  # noqa: PLC0415 - imports routes.broker
    await check_screen_isolation(db, user_ref, strategy_id)  # IC e2e decision 4: never across the live/scenario line
    scn = scenario_mode.current()
    if scn is not None:
        await scenario_mode.sync_frame(db, scn)  # IC e2e decision 2: the shared frame index, read on every check
    rates = rates if isinstance(rates, ChargeRates) else None
    try:
        tracked = await tracked_reader(strategy_id, rates)
    except TrackedExited:  # every leg exited: the worker lapses its open records (REQ-112 AC-2; ADR-237 (6))
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    except TrackedUnreadable as exc:
        log.warning("adjustment check: strategy %s unreadable: %s", strategy_id, exc)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.CONFLICT) from None
    if tracked is None:
        raise StrategyRefused(_NOT_AVAILABLE, Failure.NOT_FOUND)
    await release_connection(db)  # D-36 (c): market and REST reads wait on the broker
    market = await market_reader(tracked, ctx)
    spot = judge_spot(market, await rest_reader(tracked.position.underlying), ctx)
    listed = check.listed_of(ctx)
    stype = check.entry_type(tracked, listed)  # D-04
    resolved = await check.resolve(db, user_ref, strategy_id, stype)
    reply: dict[str, Any] = {
        "strategy_id": strategy_id, "as_of": market.now,
        "as_of_text": render_explanation("check_as_of", time=market.now),
        "strategy_type": stype,
        "type_name": None if stype is None else render_explanation("adjust_check_type_name", name=SHOWN_NAMES[stype]),
        "playbook": {"source": resolved.source, "id": resolved.playbook_id, "status": resolved.status,
                     "draft": resolved.draft},
        "stage": {"name": None, "index": None}, "withheld": None, "results": []}
    reply["paused"] = await pause_in_force(db, user_ref, strategy_id, market.now)
    if resolved.body is None or reply["paused"] is not None:  # A-38: paused -> shown with its end, not evaluated
        return CheckRun(AdjustmentCheckOut.model_validate(reply), body=resolved.body, tracked=tracked, market=market,
                        spot=spot.value if spot.available else None, fresh=check.prices_fresh(ctx))
    # D-36 (c): the reads above are done; give the request's connection back BEFORE the broker is waited on (the next
    # statement below starts a new transaction on a fresh checkout; rows read so far stay readable, no expiry on commit)
    await release_connection(db)
    margin = await current_margin(margin_of, tracked, market)
    # ADR-245: the carry gap in force (plan, else the user's own, else the admin default) is resolved inside state_of
    # ADR-243: the roll basis in force is resolved inside state_of too, from the same layers and the stored entry facts
    state = check.state_of(tracked, market, spot, margin, rates, check.prices_fresh(ctx), resolved.body,
                           config=prefs.approach, user_values=user_values, strategy_layer=resolved.strategy_layer,
                           entry_facts=await entry_facts_in(db, strategy_id), resolved=resolved)
    # read-only (review round 2, finding 3): evaluated against the stored rule memory, NOTHING written; the background
    # worker is the one writer of rule memory and records (ADR-237 (6)), so the two never disagree about a dip
    ev, _memory = await check.evaluate_stored(db, user_ref, strategy_id, resolved.body, state, scenario_mode.current(),
                                              tracked.position, gap_until=prefs.gap_until)
    opened, dismissed, fired_at, shown = await stored_records(db, user_ref, strategy_id, ev)
    live = live_values(ev)
    wording = render_explanation("adjust_check_flag_system" if resolved.is_system else "adjust_check_flag_user")
    guards = resolved.body.get("guards")
    # ADR-305: emptied for this trade
    target_unset = target_is_unset(resolved.source, guards)
    reply |= {"stage": check.stage_out(ev.stage_name, ev.stage_index),
              "withheld": None if ev.withheld is None else render(ev.withheld),
              "results": [result_out(r, wording, opened, dismissed=dismissed, body=resolved.body,
                                    cheapest=cheapest(state), target=check.target_of(state))
                              | {"stop_text": stop_text(r, ev.limits, state.pnl, fired_at,
                                                           market.now.astimezone(IST).date())}
                              | live_fields(r.rule_id, live, fired_at, reply["as_of_text"])
                          for r in shown],
              "limits": limits_out(ev.limits, target_unset)}
    return CheckRun(AdjustmentCheckOut.model_validate(reply), state, ev, resolved.body, tracked, market,
                    spot.value if spot.available else None, check.prices_fresh(ctx))
