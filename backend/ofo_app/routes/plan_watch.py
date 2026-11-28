"""GET /api/strategies/{id}/plan-watch (P10, ADR-330 (13), (11)): the live "Plan watch": one line per trigger with
fires at / now / distance / state, in rupees and percent.

The lines are composed from the two stored sources and never recomputed here (ADR-008, one engine): the plan's rules
and limits come from the one adjustment check (``adjustment_check.run_check``: ``Evaluation.limits`` and the evaluated
rules), the Stops-panel triggers from the trigger store. Money figures: P&L levels in rupees; an index exit in index
points; a leg stop in the option's price per unit (each line's ``unit`` says which). Wave 1 uses the check's own
figures (``state_of``); ``strategy_money_view`` is a later phase.

Answer states: plan present -> its lines; no plan (source "none") -> ``no_plan_text`` and NO plan lines, the armed
triggers still listed (ADR-330 (11)); the user's pause in force -> no plan lines (no evaluation), triggers paused;
prices not live or no spot -> state "paused" and no ``now`` (absent, never 0); a limit or rule the evaluator could not
check -> "not_computable" with its reason; a rule true since tracking started -> "not_applicable" (F-71); a rule that
needs a side the entry strategy had and no longer has open -> "not_applicable" with "Not applicable: the call / put
side is closed" (ADR-330 (2) (a); entry or open legs unreadable -> no side judged closed, the rule keeps its state);
a rule fired
-> "fired"; the price reads (market, REST index quote) not answered within ``price_budget.PRICE_BUDGET_S``
(``watch_of`` wraps the readers) are cancelled and read as
"not connected" (no chain, no spot): the same "prices not live" answer. The price reads are bounded by that budget; the
margin read after them has its own 8 s timeout, and the cut REST read is shielded (only the waiting request is
cancelled, the shared read finishes);
evaluation unreadable, trigger store unreadable -> the check's refusal, no lines (fail closed); strategy
not found or another user's -> its 404. Writes nothing. Suggest-only (ADR-003): nothing here exits anything.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
from collections.abc import Callable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import side_scope
from ofo.adjustment import stop_lines as sl
from ofo.charges import ChargeRates
from ofo.engine import adjust_money
from ofo.errors.explanations import render_explanation
from ofo.money import HUNDREDTH, PAISE
from ofo.strategy.definition import display_contract
from sqlalchemy.exc import SQLAlchemyError

from ofo_app import adjustment_check as check
from ofo_app import paper_book, paper_trigger_store, price_budget, tracked_contracts
from ofo_app.adjustment_readers import Prefetched
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.adjustment import (
    ApproachMargin,
    MarketReader,
    RestSpotReader,
    TrackedReader,
    get_approach_margin,
    get_market_reader,
    get_rest_spot_reader,
    get_tracked_reader,
)
from ofo_app.routes.adjustment_check import CheckPauseOut, CheckRun, run_check
from ofo_app.routes.adjustment_preferences import UserPreferences, UserValuesIn
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from ofo_app.routes.paper import identity_of
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
_NOT_AVAILABLE = "user_input_request_not_available"
PERCENT = Decimal(100)
SHOWN_PCT = HUNDREDTH
_PCT_UNIT = "%"

LineKind = Literal["target", "stop", "credit_stop", "rule", "index_exit", "leg_stop"]
LineState = Literal["watching", "fired", "not_applicable", "not_computable", "paused"]
LineUnit = Literal["pnl_rupees", "index_points", "option_price", "percent", "rule_unit"]


@dataclasses.dataclass
class BatchReads:
    """What the batch route read ONCE for all its rows (Lane B3, I-48), keyed by strategy id or contract id, so a row
    never takes another row's entry: ``triggers`` (each row's own stored triggers), ``contracts`` (the stored answer
    of every contract those triggers name, one ``tracked_contracts.resolve``), ``kinds`` (each row's position kind,
    one ``kinds_of``) and ``expiry_kinds`` ((underlying, nearest expiry) -> expiry kind, the memo ``read_tracked``
    takes as ``kinds``; filled by the first row that reads it). A key that is absent is read by the row itself, as the
    single route reads it: the prefetch is never a reason to answer less."""

    triggers: Mapping[int, list[paper_trigger_store.TriggerRow]] = dataclasses.field(default_factory=dict)
    contracts: Mapping[int, tracked_contracts.TrackedContract] = dataclasses.field(default_factory=dict)
    kinds: Mapping[int, str] = dataclasses.field(default_factory=dict)
    expiry_kinds: dict[tuple[str, datetime.date], str] = dataclasses.field(default_factory=dict)
    #: the rows' paper orders and the answers of every contract they and the triggers name (``read_tracked``'s input)
    tracked: Prefetched = dataclasses.field(default_factory=Prefetched)
    #: puts the request's session back as it was (``plan_watch_prefetch.install`` made it answer the check path's
    #: per-row statements from the batch's set-based reads for the request); a no-op when nothing was installed
    restore: Callable[[], None] = lambda: None


async def prefetch(db: Any, strategy_ids: list[int], user_ref: str) -> BatchReads:
    """The batch's shared reads, a FIXED number of queries whatever the number of rows (PC round 2 W-02: one round trip
    costs about 134 ms, 136 statements for nine rows took 18 s): one query per table for all ids
    (``plan_watch_prefetch.read_all``), the rows' paper orders, ONE contract resolve (orders and triggers) and ONE
    kind read. A failed read leaves the rows to read for themselves, as the single route does; the session is rolled
    back first when the failure was a database error."""
    from ofo_app import strategy_store  # noqa: PLC0415 - late: strategy_store reaches the order modules
    reads = BatchReads()
    restore: Callable[[], None] = reads.restore
    try:
        # in the try: a changed statement stops the prefetch, not the batch
        from ofo_app import (  # noqa: PLC0415
            plan_watch_prefetch,
        )
        pre = await plan_watch_prefetch.read_all(db, strategy_ids, user_ref)
        restore = plan_watch_prefetch.install(db, pre)
        mine = [sid for sid in strategy_ids if sid in pre.data["strategies"]]  # another's id reads for itself
        orders = await paper_book.load_owned_many(db, user_ref, mine)  # answered from memory by the installed execute
        triggers = {}
        for sid in mine:  # answered from memory too: no query
            rows = await paper_trigger_store.list_for(db, sid)
            triggers[sid] = [r for r in reversed(rows) if r.cancelled_at is None]
        ids = sorted({r.trigger.contract_id for rows in triggers.values() for r in rows
                      if r.trigger.contract_id is not None}
                     | {o.order.contract_id for rows in orders.values() for o in rows})
        found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)} if ids else {}
        with_rows = [sid for sid, rows in triggers.items() if rows]
        kinds = await strategy_store.kinds_of(db, with_rows) if with_rows else {}
    except asyncio.CancelledError:  # the request went away between the install and the return: put the session back
        restore()
        raise
    except Exception as exc:  # noqa: BLE001 - the prefetch is only a saving: any failure, each row reads for itself
        log.warning("plan watch batch: shared reads failed, each row reads for itself: %s", type(exc).__name__)
        restore()
        rollback = getattr(db, "rollback", None)
        if rollback is not None and isinstance(exc, SQLAlchemyError):  # a failed statement leaves the session unusable
            try:
                await rollback()
            except Exception:  # noqa: BLE001 - a broken connection: the rows then refuse one by one, never a whole 500
                log.warning("plan watch batch: rollback after the shared reads failed too")
        return reads
    reads.triggers, reads.contracts, reads.kinds = triggers, found, kinds
    reads.tracked = Prefetched(orders, found)
    reads.restore = restore
    return reads


class WatchLineOut(ApiModel):
    """One trigger. ``fires_at`` / ``now`` / ``distance_rs`` are in the line's ``unit``; ``distance_pct`` is the
    distance as a percent (of the fires-at level for a P&L line, of ``now`` for a price line, percentage points for a
    percent rule). ``now`` and the distances are None (never 0) when the line is paused or not computable."""

    key: Identifier
    kind: LineKind
    section: Literal["plan", "armed"]
    label: CatalogueText
    unit: LineUnit
    fires_at: Money | None
    now: Money | None
    distance_rs: Money | None
    distance_pct: Money | None
    state: LineState
    reason: CatalogueText | None = None


class PlanWatchOut(ApiModel):
    strategy_id: int
    as_of: datetime.datetime
    as_of_text: CatalogueText
    plan_state: Literal["planned", "no_plan", "paused"]
    no_plan_text: CatalogueText | None
    armed_heading: CatalogueText | None
    paused: CheckPauseOut | None = None
    lines: list[WatchLineOut]


def _q(v: Decimal | None) -> Decimal | None:
    return None if v is None else v.quantize(PAISE, rounding=ROUND_HALF_UP)


def _pct(distance: Decimal | None, reference: Decimal | None) -> Decimal | None:
    if distance is None or reference is None or reference == 0:
        return None
    return (distance / abs(reference) * PERCENT).quantize(SHOWN_PCT, rounding=ROUND_HALF_UP)


def _line(key: str, kind: str, section: str, label: Any, unit: str, state: str, *,  # noqa: PLR0913
          fires: Decimal | None = None, now: Decimal | None = None, distance: Decimal | None = None,
          pct: Decimal | None = None, reason: Any = None) -> dict:
    return {"key": key, "kind": kind, "section": section, "label": label, "unit": unit, "fires_at": _q(fires),
            "now": _q(now), "distance_rs": _q(distance), "distance_pct": pct, "state": state, "reason": reason}


def _closed(run: CheckRun) -> frozenset[str]:
    """The sides ("call" / "put") the entry strategy had and no longer has open; empty when it cannot be said."""
    entry = getattr(run.tracked, "entry_position", None)
    now = getattr(run.tracked, "position", None)
    return side_scope.closed_sides(getattr(entry, "legs", None), getattr(now, "legs", None))


_NOT_APPLICABLE = {"call": "plan_watch_side_not_applicable_call", "put": "plan_watch_side_not_applicable_put"}


def _plan_lines(run: CheckRun, live: bool) -> list[dict]:
    lines = _plan_lines_all(run, live)
    gone = side_scope.rule_notes(run.body, _closed(run))  # rule id -> its closed side(s); {} when nothing is closed
    if not gone:
        return lines
    rule_of = {lim.trigger_id: lim.rule_id for lim in (run.ev.limits if run.ev else ())}
    out = []
    for x in lines:
        rid = rule_of.get(x["key"], x["key"])  # a rule line's key is its rule id; a limit's, its trigger
        side = sorted(gone[rid])[0] if rid in gone else None
        # one sentence per side; a side the catalogue does not name keeps the line as it was (fail closed)
        out.append(x if side not in _NOT_APPLICABLE else _line(
            x["key"], x["kind"], "plan", x["label"], x["unit"], "not_applicable",
            reason=render_explanation(_NOT_APPLICABLE[side])))
    return out


def _plan_lines_all(run: CheckRun, live: bool) -> list[dict]:
    out, state, ev = run.out, run.state, run.ev
    if state is None or ev is None:
        return []
    results = {r.rule_id: r for r in out.results}
    fired = {rid for rid, r in results.items() if r.kind == "flag"}
    lines: list[dict] = []
    seen: set[str] = set()
    pnl = state.pnl if live else None
    for lim, shown in zip(ev.limits, out.limits, strict=True):
        seen.add(lim.rule_id)
        kind = ("target" if lim.trigger_id == "T-07" else "credit_stop" if lim.rule_id == sl.CREDIT_RULE else "stop")
        label = shown.text or render_explanation("adjust_condition_line_id", label=lim.trigger_id)
        if lim.state == "already_true":
            lines.append(_line(lim.trigger_id, kind, "plan", label, "pnl_rupees", "not_applicable"))
            continue
        fires = _fires_at(kind, lim, state)
        if lim.state == "not_checked" or fires is None:
            # W-30: a row that is not checked still carries its level when the evaluator has one (never a guess); the
            # reason it is not checked travels beside it
            lines.append(_line(lim.trigger_id, kind, "plan", label, "pnl_rupees", "not_computable", fires=fires,
                               reason=shown.reason))
            continue
        if not live or pnl is None:
            lines.append(_line(lim.trigger_id, kind, "plan", label, "pnl_rupees", "paused", fires=fires))
            continue
        # rupees still to go before the line is reached
        distance = adjust_money.distance_to_level(fires, pnl, kind == "target")
        lines.append(_line(lim.trigger_id, kind, "plan", label, "pnl_rupees",
                           "fired" if lim.rule_id in fired else "watching", fires=fires, now=pnl, distance=distance,
                           pct=_pct(distance, fires)))
    for v in ev.values:  # each other rule the evaluator checked, true or false
        if v.rule_id in seen or v.trigger_id in sl.STOP_TRIGGERS:
            continue
        seen.add(v.rule_id)
        lines.append(_rule_line(v, run, live, v.rule_id in fired))
    for rid, r in results.items():  # a rule with no value: not checked, or true since tracking started
        if rid in seen or r.trigger_id in sl.STOP_TRIGGERS or r.kind == "flag":
            continue
        seen.add(rid)
        label = render_explanation("adjust_condition_line_id", label=_label_of(run, r.trigger_id))
        lines.append(_line(rid, "rule", "plan", label, "rule_unit",
                           "not_applicable" if r.kind == "already_true" else "not_computable", reason=r.reason))
    return lines


def _label_of(run: CheckRun, trigger_id: str) -> str:
    label, _unit = check.trigger_words(run.body, trigger_id)
    return label if label else trigger_id


def _fires_at(kind: str, lim: pe.LimitNow, state: pe.StrategyState) -> Decimal | None:
    """The P&L level, in rupees, at which the limit is reached: the target = its % of max profit; a stop = minus the
    evaluator's own rupee loss line (``LimitNow.amount``); None = not known (never a guess)."""
    if kind == "target":
        if isinstance(state.max_profit, Decimal) and isinstance(lim.threshold, Decimal):
            return adjust_money.pct_of(state.max_profit, lim.threshold)
        return None
    return -lim.amount if isinstance(lim.amount, Decimal) else None


def _rule_line(v: pe.RuleValue, run: CheckRun, live: bool, fired: bool) -> dict:
    label = render_explanation("adjust_condition_line_id", label=_label_of(run, v.trigger_id))
    if not (isinstance(v.value, Decimal) and isinstance(v.threshold, Decimal)):  # a clock rule: no number to subtract
        said = "fired" if fired else "watching" if live else "paused"
        return _line(v.rule_id, "rule", "plan", label, "rule_unit", said)
    _label, unit = check.trigger_words(run.body, v.trigger_id)
    percent = unit == _PCT_UNIT
    kind = "percent" if percent else "rule_unit"
    if not live:
        return _line(v.rule_id, "rule", "plan", label, kind, "paused", fires=v.threshold)
    distance = adjust_money.distance_to_level(v.threshold, v.value, v.cmp == "ge")  # still to go (negative: past)
    return _line(v.rule_id, "rule", "plan", label, kind, "fired" if fired else "watching", fires=v.threshold,
                 now=v.value, pct=_q(distance) if percent else None)


async def _is_own(db: Any, user_ref: str, strategy_id: int) -> bool:
    """True when the strategy exists and belongs to the user (a draft or a tracked one); any read failure: False."""
    from ofo_app import playbook_store  # noqa: PLC0415 - database layer at run time
    try:
        await playbook_store.require_owned(db, user_ref, strategy_id)
    except Exception:  # noqa: BLE001 - not owned, gone, or unreadable: the caller keeps the original refusal
        return False
    return True


async def _armed_reads(db: Any, strategy_id: int, reads: BatchReads | None) -> tuple[list, dict, str]:
    """(the row's live trigger rows, their contracts by id, the position kind): from the batch's shared read of THIS
    row when it has one, else read here, as the single route does; a key the batch did not read is read here."""
    from ofo_app import position_kind, strategy_store  # noqa: PLC0415 - late: strategy_store reaches the order modules
    mine = reads.triggers.get(strategy_id) if reads is not None else None
    rows = mine if mine is not None else [
        r for r in reversed(await paper_trigger_store.list_for(db, strategy_id)) if r.cancelled_at is None]
    ids = sorted({r.trigger.contract_id for r in rows if r.trigger.contract_id is not None})
    shared = reads.contracts if reads is not None else {}
    found = {cid: shared[cid] for cid in ids if cid in shared}
    missing = [cid for cid in ids if cid not in found]
    if missing:
        found |= {c.contract_id: c for c in await tracked_contracts.resolve(db, missing)}
    if not rows:
        return rows, found, position_kind.UNKNOWN
    if reads is not None and strategy_id in reads.kinds:
        return rows, found, reads.kinds[strategy_id]
    return rows, found, (await strategy_store.kinds_of(db, [strategy_id])).get(strategy_id, position_kind.UNKNOWN)


async def _armed_lines(db: Any, strategy_id: int, run: CheckRun, live: bool,
                       reads: BatchReads | None = None) -> list[dict]:
    from ofo_app import position_kind  # noqa: PLC0415 - late: position_kind reaches the order modules
    try:
        rows, found, kind = await _armed_reads(db, strategy_id, reads)
    except SQLAlchemyError as exc:
        log.warning("plan watch: triggers of strategy %s unreadable: %s", strategy_id, type(exc).__name__)
        raise StrategyRefused(_NOT_AVAILABLE, Failure.UPSTREAM_BUSY) from None
    marks = _leg_marks(run)
    lines = []
    for r in rows:
        t = r.trigger
        up = t.direction == "above"
        if t.kind == "conditional_exit":
            label = render_explanation("plan_watch_index_above" if up else "plan_watch_index_below", level=t.level)
            unit, price = "index_points", run.spot
        else:
            try:
                identity = identity_of(found[t.contract_id])
            except (KeyError, RuntimeError):
                lines.append(_line(f"trigger-{t.id}", "leg_stop", "armed", render_explanation(
                    "adjust_condition_line_id", label="leg stop"), "option_price", "not_computable", fires=t.level))
                continue
            leg = display_contract(identity)  # the app's one contract style: "NIFTY 3 Nov 22650 PE", never an ISO date
            unit, price = "option_price", marks.get((identity[1].value, identity[2]))
            side = "above" if up else "below"
            if price is not None and live:  # the sentence carries the live price beside the level (item 6)
                label = render_explanation(f"plan_watch_leg_{side}_now", leg=leg, level=t.level, now=price)
            else:
                label = render_explanation(f"plan_watch_leg_{side}", leg=leg, level=t.level)
        key = f"trigger-{t.id}"
        kind_out = "index_exit" if t.kind == "conditional_exit" else "leg_stop"
        if price is None or not live:  # prices not live: a paused line with no `now` (never an old number)
            lines.append(_line(key, kind_out, "armed", label, unit, "paused" if not live else "not_computable",
                               fires=t.level))
            continue
        distance = adjust_money.distance_to_level(t.level, price, up)
        lines.append(_line(key, kind_out, "armed", label, unit, "fired" if r.fired_at is not None else "watching",
                           fires=t.level, now=price, distance=distance, pct=_pct(distance, price)))
    if kind in (position_kind.REAL, position_kind.UNKNOWN):
        # ADR-330 (64) / R6: a real (or unreadable) position has no paper stop; an old armed row stays stored, never
        # shown as a live line: "not applicable", with the position-kind sentence, no price and no distance
        lines = [{**ln, "state": "not_applicable", "now": None, "distance_rs": None, "distance_pct": None,
                  "reason": position_kind.line_of(kind)} for ln in lines]
    return lines


def _leg_marks(run: CheckRun) -> dict[tuple[str, Decimal], Decimal | None]:
    """(CE / PE, strike) -> the open leg's mark now (the check's own ``mark_of``); empty when no market or position."""
    if run.market is None or run.tracked is None:
        return {}
    rows = {x.tradingsymbol: x for x in run.market.chain}
    return {(x.type, x.strike): check.mark_of(rows.get(x.tradingsymbol)) for x in run.tracked.position.legs}


def _remember_kind(reads: BatchReads, run: CheckRun) -> None:
    """Record the row's non-empty expiry kind under (underlying, nearest open expiry), the key ``read_tracked`` looks
    up (``_stored_kind_or_empty``); an empty (not known) kind is never recorded, so the next row reads it itself."""
    position = getattr(run.tracked, "position", None)
    legs = getattr(position, "legs", None)
    kind = getattr(position, "expiry_kind", "")
    if position is not None and legs and kind:
        reads.expiry_kinds.setdefault((position.underlying, min(x.expiry for x in legs)), kind)


async def watch_of(  # noqa: PLR0913 - the route's inputs, passed on
        strategy_id: int, *, db: Any, user_ref: str, tracked_reader: TrackedReader, market_reader: MarketReader,
        rest_reader: RestSpotReader, margin_of: ApproachMargin, ctx: MarketContext | None,
        rates: ChargeRates | None, prefs: Any, user_values: Any, reads: BatchReads | None = None) -> PlanWatchOut:
    """ONE strategy's Plan watch: the single route's whole answer, also what the batch route answers per row (same code,
    so the same lines, wording and refusals; ADR-008). ``reads``: what the batch read once for all its rows; None
    (the single route) reads everything here. The screen-isolation check runs once, first in ``run_check`` (I-48: it
    used to run here as well, a second identical statement per row)."""
    from ofo_app.adjustment_readers import read_market  # noqa: PLC0415 - imports routes.adjustment
    # Lane J2: the one price budget (ofo_app/price_budget.py), the same wrapper the adjustment-check route uses
    market_reader, rest_reader = price_budget.budgeted(market_reader, rest_reader, not_live_market=read_market)
    try:
        run = await run_check(strategy_id, db=db, user_ref=user_ref, tracked_reader=tracked_reader,
                              market_reader=market_reader, rest_reader=rest_reader, margin_of=margin_of, ctx=ctx,
                              rates=rates, prefs=prefs, user_values=user_values)
    except StrategyRefused as refused:
        if refused.failure is not Failure.NOT_FOUND or not await _is_own(db, user_ref, strategy_id):
            raise  # another user's or a missing strategy stays "not found"
        # issue-list row 3 (27 Nov): an own saved draft is not tracked, nothing is watched: say so, not "not found"
        now = datetime.datetime.now(datetime.UTC)
        return PlanWatchOut.model_validate({
            "strategy_id": strategy_id, "as_of": now, "as_of_text": render_explanation("check_as_of", time=now),
            "plan_state": "no_plan", "no_plan_text": render_explanation("plan_sheet_no_plan"),
            "armed_heading": None, "paused": None, "lines": []})
    if reads is not None:  # hand the expiry kind this row read to the next rows of the batch (same rule, same request)
        _remember_kind(reads, run)
    live = run.fresh is not False and run.spot is not None  # unknown health with a spot is read as the check reads it
    out = run.out
    plan = out.playbook.source != "none"
    pause = out.paused
    plan_lines = [] if not plan or pause is not None else _plan_lines(run, live)
    armed = await _armed_lines(db, strategy_id, run, live and pause is None, reads)
    return PlanWatchOut.model_validate({
        "strategy_id": strategy_id, "as_of": out.as_of, "as_of_text": out.as_of_text,
        "plan_state": "paused" if plan and pause is not None else "planned" if plan else "no_plan",
        "no_plan_text": None if plan else render_explanation("plan_sheet_no_plan"),
        "armed_heading": render_explanation("plan_watch_armed_heading") if armed else None,
        "paused": pause, "lines": plan_lines + armed})


@router.get("/api/strategies/{strategy_id}/plan-watch", response_model=PlanWatchOut)
async def plan_watch(  # noqa: PLR0913 - FastAPI dependencies, one per input
        strategy_id: int, *,
        db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)],
        prefs: UserPreferences, user_values: UserValuesIn) -> PlanWatchOut:
    return await watch_of(strategy_id, db=db, user_ref=user_ref, tracked_reader=tracked_reader,
                          market_reader=market_reader, rest_reader=rest_reader, margin_of=margin_of, ctx=ctx,
                          rates=rates, prefs=prefs, user_values=user_values)
