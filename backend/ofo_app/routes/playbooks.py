"""Playbook API (GC-ADJ2 step 2; REQ-158 AC-3, AC-4, AC-6, AC-7, REQ-159 AC-1): list, read, create, duplicate,
rename, delete, make active, save as new and save in place, all through ``ofo_app.playbook_store`` (public functions).

- The user is the session's (``current_user_ref``), never a body field. Another user's playbook answers 404 exactly
  like a missing one, on every route; a request body or query holds no user.
- Refusals are the store's, answered with the catalogue text at their status: playbook_name_taken 409,
  system_playbook_save_in_place 409, playbook_version_conflict 409, playbook_not_found 404, playbook_body_invalid 422
  (naming the field). A gap or overlap between stages (REQ-159 AC-1) is 422 with the days and stage names. A body
  field or a request field the shape does not define is refused, never ignored. A store failure (database) is raised
  to the error boundary after a rollback: never a 200.
- DRAFT IS A SYSTEM-PLAYBOOK LABEL ONLY: ``draft`` is true only for a system playbook whose status is draft. A user's
  own playbook, including a copy of a draft system playbook, is never labelled Draft and carries ``status`` None (the
  user's own numbers have no approval state; the table's DEFAULT 'draft' is not shown).
- Suggest-only (ADR-003): nothing here places an order.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import time
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment import playbook_stages as stages
from ofo.adjustment.playbook_text import name_shown
from ofo.adjustment.playbook_types import SHOWN_NAMES, TYPE_KEYS
from ofo.charges import ChargeRates
from ofo.errors import render
from ofo.errors.explanations import (
    ADJUSTMENT_APPROACH_LABEL_TEXT,
    PLAYBOOK_APPROACH_LABEL_TEXT,
    PLAYBOOK_DAY_RULE_ACTION_TEXT,
    PLAYBOOK_DAY_RULE_KIND_TEXT,
    PLAYBOOK_GUARD_LABEL_TEXT,
    PLAYBOOK_SUMMARY_TEXT,
    approach_name_id,
    render_explanation,
)
from ofo.marketdata.spot_source import resolve_spot
from ofo.strategy.stored_form import shown_name
from pydantic import BaseModel, ConfigDict

from ofo_app import adjustment_check as check
from ofo_app import paper_store, scenario_mode, strategy_store
from ofo_app import playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.playbook_body_out import PlaybookBody
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
from ofo_app.routes.adjustment_check import CheckResultOut, CheckStageOut, current_margin, result_out
from ofo_app.routes.broker import current_user_ref
from ofo_app.routes.outcome import MarketContext, get_market_context, load_charge_rates
from ofo_app.strategy_refused import StrategyRefused

log = logging.getLogger(__name__)
router = APIRouter(route_class=ClosedRoute)
ID_MAX = 9_223_372_036_854_775_807  # the id column is BIGSERIAL: a larger number is simply not there
_STATUS = {
    store.NOT_FOUND: Failure.NOT_FOUND,
    store.NAME_TAKEN: Failure.CONFLICT,
    store.SYSTEM_SAVE_IN_PLACE: Failure.CONFLICT,
    store.VERSION_CONFLICT: Failure.CONFLICT,
    store.BODY_INVALID: None,  # 422
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CreateIn(_In):
    type: str
    name: str
    body: dict[str, Any]


class DuplicateIn(_In):
    name: str


class SaveIn(_In):
    body: dict[str, Any]
    version: int


class TypeOut(ApiModel):
    key: Identifier
    name: CatalogueText
    active_id: int
    has_system: bool


class TypesOut(ApiModel):
    types: list[TypeOut]


class PlaybookOut(ApiModel):
    id: int
    name: CatalogueText
    type: Identifier
    type_name: CatalogueText
    is_system: bool
    status: Literal["approved", "draft"] | None
    draft: bool
    active: bool
    version: int
    updated_at: datetime.datetime


class PlaybookListOut(ApiModel):
    playbooks: list[PlaybookOut]


class PlaybookFullOut(PlaybookOut):
    body: PlaybookBody


class DeletedOut(ApiModel):
    deleted: bool
    active_now_system: bool
    message: CatalogueText | None


def _refused(exc: store.PlaybookStoreError | stages.StageProblem) -> StrategyRefused:
    if isinstance(exc, stages.StageProblem):
        return StrategyRefused(exc.template, None, message=render(exc.template, **exc.slots))
    return StrategyRefused(exc.code, _STATUS[exc.code], message=render(exc.code, **exc.slots))


def _id(playbook_id: int) -> int:
    if not 1 <= playbook_id <= ID_MAX:
        raise store.PlaybookStoreError(store.NOT_FOUND, f"playbook {playbook_id}")
    return playbook_id


def _name(name: str) -> str:
    """A double quote cannot be quoted back in a refusal's text (the PlaybookName slot): refused as an invalid name."""
    if '"' in name:
        raise store.PlaybookStoreError(store.BODY_INVALID, "playbook name", field="name")
    return name


def _precheck(strategy_type: str, body: object) -> None:
    """What every save checks before a write: the store's body check, then the keys and the stage coverage."""
    if strategy_type not in SHOWN_NAMES:
        raise store.PlaybookStoreError(store.BODY_INVALID, "strategy type", field="strategy_type")
    checked = store.check_body(body, strategy_type)  # a dict, or it raised
    stages.check_keys(checked)
    stages.check_stages(checked)


def _row(pb: store.Playbook, active_id: int) -> dict[str, Any]:
    return {"id": pb.id, "name": name_shown(pb.name), "type": pb.strategy_type,
            "type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[pb.strategy_type]),
            "is_system": pb.is_system, "status": pb.status if pb.is_system else None,
            "draft": pb.is_system and pb.status == "draft", "active": pb.id == active_id, "version": pb.version,
            "updated_at": pb.updated_at}


async def _out(db: Any, user_ref: str, pb: store.Playbook, *, full: bool = False) -> PlaybookOut:
    active = await store.active_for(db, user_ref, pb.strategy_type)
    row = _row(pb, active.id)
    if full:
        return PlaybookFullOut.model_validate(row | {"body": PlaybookBody.of(pb.body)})
    return PlaybookOut.model_validate(row)


async def _run(db: Any, work: Any) -> Any:
    """One store call: commit on success; any refusal or failure rolls back (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except (store.PlaybookStoreError, stages.StageProblem) as exc:
        await db.rollback()
        raise _refused(exc) from None
    except Exception:
        await db.rollback()
        raise
    return result


@router.get("/api/playbooks/types", response_model=TypesOut)
async def playbook_types(db: Annotated[Any, Depends(get_db)],
                         user_ref: Annotated[str, Depends(current_user_ref)]) -> TypesOut:
    async def work() -> TypesOut:
        out = []
        for key in TYPE_KEYS:
            active = await store.active_for(db, user_ref, key)
            listed = await store.list_for_type(db, user_ref, key)
            out.append({"key": key, "name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[key]),
                        "active_id": active.id, "has_system": any(p.is_system for p in listed)})
        return TypesOut.model_validate({"types": out})
    return await _run(db, work)


class LabelOut(ApiModel):
    key: Identifier
    text: CatalogueText


class LabelsOut(ApiModel):
    approaches: list[LabelOut]
    day_kinds: list[LabelOut]
    day_actions: list[LabelOut]
    past_note: CatalogueText  # REQ-160 AC-4, shown on the Test step before any run
    summary: list[LabelOut]  # sentence templates: "{slot}" is filled by the editor from the body's own strings
    guards: list[LabelOut]  # each guard key in words (Limits and guards never shows a raw key)
    no_values: CatalogueText  # a trigger with no value list for an expiry kind (null in the body)


def _labels(table: Mapping[str, str], template_id: Callable[[str], str]) -> list[dict[str, Any]]:
    return [{"key": key, "text": render_explanation(template_id(key))} for key in table]


@router.get("/api/playbooks/labels", response_model=LabelsOut)
async def playbook_labels() -> LabelsOut:
    """GC-ADJ2 step 3 (REQ-159 AC-4/AC-5, REQ-160 AC-1): every word the editor shows that the body does not carry, all
    from the catalogue: approach names (the compare's table first, the editor's table for the rest), day rule kinds and
    actions, the summary's sentences. A read of fixed text: no user, no database. Declared before
    ``/api/playbooks/{playbook_id}`` so "labels" is never read as an id."""
    return LabelsOut.model_validate({
        "approaches": _labels(ADJUSTMENT_APPROACH_LABEL_TEXT, approach_name_id)
        + _labels(PLAYBOOK_APPROACH_LABEL_TEXT, lambda k: "playbook_approach_" + k.lower().replace("-", "_")),
        "day_kinds": _labels(PLAYBOOK_DAY_RULE_KIND_TEXT, lambda k: f"playbook_day_kind_{k}"),
        "day_actions": _labels(PLAYBOOK_DAY_RULE_ACTION_TEXT, lambda k: f"playbook_day_action_{k}"),
        "past_note": render_explanation("playbook_test_past_out_of_v1"),
        "summary": _labels(PLAYBOOK_SUMMARY_TEXT, lambda k: f"playbook_summary_{k}"),
        "guards": _labels(PLAYBOOK_GUARD_LABEL_TEXT, lambda k: f"playbook_guard_{k}"),
        "no_values": render("adjust_trigger_no_expiry_values")})


@router.get("/api/playbooks", response_model=PlaybookListOut)
async def list_playbooks(type: Annotated[str, Query()], db: Annotated[Any, Depends(get_db)],
                         user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookListOut:
    """The type's system playbook first, then the user's own by name."""
    async def work() -> PlaybookListOut:
        rows = await store.list_for_type(db, user_ref, type)
        active = await store.active_for(db, user_ref, type)
        return PlaybookListOut.model_validate({"playbooks": [_row(p, active.id) for p in rows]})
    return await _run(db, work)


@router.get("/api/playbooks/{playbook_id}", response_model=PlaybookFullOut)
async def read_playbook(playbook_id: int, db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    async def work() -> PlaybookOut:
        return await _out(db, user_ref, await store.get(db, user_ref, _id(playbook_id)), full=True)
    return await _run(db, work)


@router.post("/api/playbooks", status_code=201, response_model=PlaybookFullOut)
async def create_playbook(data: CreateIn, db: Annotated[Any, Depends(get_db)],
                          user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    """Create, or save as new: the body may be a system playbook's. The new one is the user's own (no Draft label)."""
    async def work() -> PlaybookOut:
        _precheck(data.type, data.body)
        made = await store.create(db, user_ref, data.type, _name(data.name), data.body)
        return await _out(db, user_ref, made, full=True)
    return await _run(db, work)


@router.post("/api/playbooks/{playbook_id}/duplicate", status_code=201, response_model=PlaybookFullOut)
async def duplicate_playbook(playbook_id: int, data: DuplicateIn, db: Annotated[Any, Depends(get_db)],
                             user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    async def work() -> PlaybookOut:
        copy = await store.duplicate(db, user_ref, _id(playbook_id), _name(data.name))
        return await _out(db, user_ref, copy, full=True)
    return await _run(db, work)


@router.patch("/api/playbooks/{playbook_id}", response_model=PlaybookFullOut)
async def rename_playbook(playbook_id: int, data: DuplicateIn, db: Annotated[Any, Depends(get_db)],
                          user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    async def work() -> PlaybookOut:
        renamed = await store.rename(db, user_ref, _id(playbook_id), _name(data.name))
        return await _out(db, user_ref, renamed, full=True)
    return await _run(db, work)


@router.put("/api/playbooks/{playbook_id}", response_model=PlaybookFullOut)
async def save_playbook(playbook_id: int, data: SaveIn, db: Annotated[Any, Depends(get_db)],
                        user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    """Save in place: the user's own playbook only, at the version the caller read."""
    async def work() -> PlaybookOut:
        current = await store.get(db, user_ref, _id(playbook_id))
        if not current.is_system:  # a system playbook goes straight to the store's refusal, row unchanged
            _precheck(current.strategy_type, data.body)
        saved = await store.save_in_place(db, user_ref, playbook_id, data.body, data.version)
        return await _out(db, user_ref, saved, full=True)
    return await _run(db, work)


@router.delete("/api/playbooks/{playbook_id}", response_model=DeletedOut)
async def delete_playbook(playbook_id: int, db: Annotated[Any, Depends(get_db)],
                          user_ref: Annotated[str, Depends(current_user_ref)]) -> DeletedOut:
    async def work() -> DeletedOut:
        current = await store.get(db, user_ref, _id(playbook_id))  # not found for another user's, before any write
        answer = await store.delete(db, user_ref, playbook_id)
        # the store returns plain text; the door takes only a catalogue result: render the same entry
        message = (render_explanation("playbook_system_active_again", type=SHOWN_NAMES[current.strategy_type])
                   if answer.active_now_system else None)
        return DeletedOut.model_validate({"deleted": True, "active_now_system": answer.active_now_system,
                                          "message": message})
    return await _run(db, work)


@router.post("/api/playbooks/{playbook_id}/activate", response_model=PlaybookFullOut)
async def activate_playbook(playbook_id: int, db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    async def work() -> PlaybookOut:
        return await _out(db, user_ref, await store.make_active(db, user_ref, _id(playbook_id)), full=True)
    return await _run(db, work)


# ---- Test (GC-ADJ2 step 3; REQ-160 AC-3, AC-4) -----------------------------------------------------------------------
class TestIn(_In):
    type: str
    body: dict[str, Any]


class TestStrategyOut(ApiModel):
    strategy_id: int
    name: CatalogueText
    stage: CheckStageOut
    withheld: CatalogueText | None
    results: list[CheckResultOut]


class TestOut(ApiModel):
    type: Identifier
    type_name: CatalogueText
    none_text: CatalogueText | None  # "No current <type> strategy to test against", or None when one was tested
    past_note: CatalogueText  # REQ-160 AC-4: testing past expiries is out of V1
    strategies: list[TestStrategyOut]


@dataclasses.dataclass(frozen=True)
class _Seams:
    tracked_reader: TrackedReader
    market_reader: MarketReader
    rest_reader: RestSpotReader
    margin_of: ApproachMargin
    ctx: MarketContext | None
    rates: ChargeRates | None


#: REQ-160 AC-3: the whole outside read of ONE strategy (tracked legs, chain/market, REST spot, margin) is bounded by
#: this many seconds; strategies are read TEST_READ_CONCURRENCY at a time, so N strategies take at most
#: ceil(N / TEST_READ_CONCURRENCY) x this limit. A slow strategy is listed not checked, never a stalled answer.
TEST_READ_LIMIT_SECONDS = 8.0
TEST_READ_CONCURRENCY = 4
TEST_TIMED_OUT_CODE = "adjust_test_read_timed_out"


@dataclasses.dataclass
class _Read:
    """What one strategy's bounded read got to (kept on a timeout, so a known type can still be listed)."""
    tracked: Any = None
    market: Any = None
    spot: Any = None
    margin: dict | None = None
    done: bool = False


async def _read_one(row: Any, seams: _Seams, listed: Any, read: _Read) -> None:
    from ofo_app.adjustment_readers import TrackedUnreadable  # noqa: PLC0415 - it imports routes.adjustment
    try:
        read.tracked = await seams.tracked_reader(row.id, seams.rates)
    except TrackedUnreadable:  # legs not readable: its type is not known, so it is not "of that type"
        read.tracked = None
        return
    if read.tracked is None:
        return
    market = await seams.market_reader(read.tracked, seams.ctx)
    read.market = market
    read.spot = resolve_spot(market.feed, await seams.rest_reader(read.tracked.position.underlying),
                             market.last_close, now=market.now)
    read.margin = await current_margin(seams.margin_of, read.tracked, market)
    read.done = True


def _not_checked(row: Any, body: dict[str, Any]) -> dict[str, Any]:
    """A strategy of the type whose reads did not finish: every rule listed not checked, with the reason."""
    results = [pe.NotChecked(rule["id"], (rule.get("any_of") or rule["all_of"])[0], TEST_TIMED_OUT_CODE)
               for rule in body.get("rules", [])]
    return {"strategy_id": row.id, "name": shown_name(row.name), "stage": {"name": None, "index": None},
            "withheld": None, "results": [result_out(r, None) for r in results]}


async def _read_bounded(row: Any, seams: _Seams, listed: Any, gate: asyncio.Semaphore, data: TestIn,
                        ) -> tuple[Any, _Read] | dict[str, Any] | None:
    """-> (row, read) when read in full and of the type; a not-checked entry when the type is known but the read timed
    out or failed; None when not of the type (or its type is not known)."""
    read = _Read()
    async with gate:
        started = time.monotonic()
        try:
            await asyncio.wait_for(_read_one(row, seams, listed, read), TEST_READ_LIMIT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - one strategy's failed read is "not checked", never a 500
            log.debug("playbook test: strategy %s read %s after %.2fs", row.id, type(exc).__name__,
                      time.monotonic() - started)
            if read.tracked is None:
                return None  # not even its legs are read: its type is not known
            known = check.strategy_type(read.tracked.position, None, listed)
            return _not_checked(row, data.body) if known == data.type else None
        log.debug("playbook test: strategy %s read in %.2fs", row.id, time.monotonic() - started)
    if read.tracked is None:
        return None
    spot = read.spot
    if check.strategy_type(read.tracked.position, spot.value if spot.available else None, listed) != data.type:
        return None
    return row, read


async def _tested(db: Any, user_ref: str, data: TestIn, seams: _Seams) -> list[dict[str, Any]]:
    """Read only. Cheap first: a strategy with no open paper leg is skipped before any outside read; the rest are read
    TEST_READ_CONCURRENCY at a time, each under TEST_READ_LIMIT_SECONDS."""
    rows = await strategy_store.list_strategies(db, user_ref)
    tracked_ids = await paper_store.tracked_ids(db, [r.id for r in rows])
    listed = None if seams.ctx is None else seams.ctx.provider.instrument_master()
    gate = asyncio.Semaphore(TEST_READ_CONCURRENCY)
    answers = await asyncio.gather(*(_read_bounded(r, seams, listed, gate, data)
                                     for r in rows if r.id in tracked_ids))
    strategies = []
    for answer in answers:
        if answer is None:
            continue
        if isinstance(answer, dict):
            strategies.append(answer)
            continue
        row, read = answer
        tracked, market, spot = read.tracked, read.market, read.spot
        state = check.state_of(tracked, market, spot, read.margin, seams.rates, check.prices_fresh(seams.ctx),
                               data.body)
        entry = check.scenario_entry(scenario_mode.current(), state, tracked.position)
        if entry is not None:
            state = dataclasses.replace(state, entry_atm_iv=entry.atm_iv)
        ev = pe.evaluate(data.body, state, {}, entry)  # empty memory; the returned memory is dropped
        strategies.append({"strategy_id": row.id, "name": shown_name(row.name),
                           "stage": {"name": ev.stage_name, "index": ev.stage_index},
                           "withheld": None if ev.withheld is None else render(ev.withheld),
                           "results": [result_out(r, None) for r in ev.results]})
    return strategies


@router.post("/api/playbooks/test", response_model=TestOut)
async def test_playbook(  # noqa: PLR0913 - FastAPI dependencies, one per input (as the check route)
        data: TestIn, db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        tracked_reader: Annotated[TrackedReader, Depends(get_tracked_reader)],
        market_reader: Annotated[MarketReader, Depends(get_market_reader)],
        rest_reader: Annotated[RestSpotReader, Depends(get_rest_spot_reader)],
        margin_of: Annotated[ApproachMargin, Depends(get_approach_margin)],
        ctx: Annotated[MarketContext | None, Depends(get_market_context)],
        rates: Annotated[ChargeRates | None, Depends(load_charge_rates)]) -> TestOut:
    """REQ-160 AC-3: the unsaved body checked exactly as a save checks it (``_precheck``: body, keys, stage gap and
    overlap), then evaluated on each of the user's tracked strategies of the type. Nothing is written: empty rule
    memory (a rule true now flags; the F-71 entry state is the scenario's stated entry only), no rule state, no
    suggestion, no order; the transaction is rolled back. A not-checked rule is listed with its reason, never passed."""
    seams = _Seams(tracked_reader, market_reader, rest_reader, margin_of, ctx,
                   rates if isinstance(rates, ChargeRates) else None)
    try:
        _precheck(data.type, data.body)
    except (store.PlaybookStoreError, stages.StageProblem) as exc:
        raise _refused(exc) from None
    try:
        strategies = await _tested(db, user_ref, data, seams)
    finally:
        await db.rollback()  # read only: whatever a reader touched is never kept
    type_name = SHOWN_NAMES[data.type]
    return TestOut.model_validate({
        "type": data.type, "type_name": render_explanation("adjust_check_type_name", name=type_name),
        "none_text": None if strategies else render_explanation("playbook_test_no_strategy", type=type_name),
        "past_note": render_explanation("playbook_test_past_out_of_v1"), "strategies": strategies})
