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

import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from ofo.adjustment import playbook_stages as stages
from ofo.adjustment.playbook_text import name_shown
from ofo.adjustment.playbook_types import SHOWN_NAMES, TYPE_KEYS
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from pydantic import BaseModel, ConfigDict

from ofo_app import playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.playbook_body_out import PlaybookBody
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused

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
        answer = await store.delete(db, user_ref, _id(playbook_id))
        return DeletedOut.model_validate({"deleted": True, "active_now_system": answer.active_now_system,
                                          "message": answer.message})
    return await _run(db, work)


@router.post("/api/playbooks/{playbook_id}/activate", response_model=PlaybookFullOut)
async def activate_playbook(playbook_id: int, db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)]) -> PlaybookOut:
    async def work() -> PlaybookOut:
        return await _out(db, user_ref, await store.make_active(db, user_ref, _id(playbook_id)), full=True)
    return await _run(db, work)
