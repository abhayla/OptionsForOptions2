"""The admin's system playbook API (REQ-169 AC-1..AC-3; ADR-222 (10)): history, save a new version, restore an earlier
version, approve a Draft. Every route depends on ``routes.settings.require_admin`` (the ONE admin guard; a test fails
for any route of this router without it, reads included). Users still only copy system playbooks (``/api/playbooks``).

- Validation is the user editor's own: ``routes.playbooks.precheck`` (the store's body check, the keys, the stage gap
  and overlap) before any write, refused with the same reasons and statuses as a user's save (REQ-160).
- Test before Save is the user editor's Test route (``POST /api/playbooks/test`` with the system type and the edited
  body): it evaluates and writes nothing. No second evaluator.
- Every write is a NEW version (``ofo_app.system_playbook_store``, migration 0034); the admin's reason is stored and
  written to the audit log, not sent back (admin free text cannot pass the response door, as the Settings routes).
- Refusals of this API (no reason 422, a stale base version 409, a version not stored 404, already approved 409) answer
  the catalogue reason; a store failure is raised to the error boundary after a rollback: never a 200.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from ofo.adjustment import playbook_stages as stages
from ofo.adjustment.playbook_types import SHOWN_NAMES
from ofo.errors.explanations import render_explanation
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from ofo_app import playbook_store as pbs
from ofo_app import system_playbook_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, respond
from ofo_app.playbook_body_out import PlaybookBody
from ofo_app.routes.playbooks import refused as editor_refused
from ofo_app.routes.playbooks import precheck
from ofo_app.routes.settings import RefusedOut, require_admin

router = APIRouter(route_class=ClosedRoute, dependencies=[Depends(require_admin)])
Admin = Annotated[str, Depends(require_admin)]
Db = Annotated[Any, Depends(get_db)]
BASE = "/api/system-playbooks/{strategy_type}"

#: this API's own refusals -> (catalogue explanation, HTTP status); every other store refusal is the editor's
_OWN = {
    store.REASON_REQUIRED: ("system_playbook_refused_reason", 422),
    store.VERSION_STALE: ("system_playbook_refused_stale", 409),
    store.VERSION_NOT_FOUND: ("system_playbook_refused_version", 404),
    store.ALREADY_APPROVED: ("system_playbook_refused_approved", 409),
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SystemSaveIn(_In):
    body: dict[str, Any]
    reason: StrictStr
    base_version: StrictInt


class SystemReasonIn(_In):
    reason: StrictStr
    base_version: StrictInt


class SystemVersionOut(ApiModel):
    type: Identifier
    type_name: CatalogueText
    version: int
    status: Literal["approved", "draft"]
    draft: bool
    current: bool
    restored_from: int | None
    saved_by: Identifier
    saved_at: datetime.datetime
    body: PlaybookBody


class SystemHistoryOut(ApiModel):
    versions: list[SystemVersionOut]  # newest (current) first


def _out(v: store.SystemVersion, current: int) -> SystemVersionOut:
    return SystemVersionOut.model_validate({
        "type": v.strategy_type,
        "type_name": render_explanation("adjust_check_type_name", name=SHOWN_NAMES[v.strategy_type]),
        "version": v.version, "status": v.status, "draft": v.status == "draft", "current": v.version == current,
        "restored_from": v.restored_from, "saved_by": v.saved_by, "saved_at": v.saved_at,
        "body": PlaybookBody.of(v.body)})


async def _run(db: Any, work: Any) -> object:
    """One store call: commit on success; any refusal or failure rolls back (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except pbs.PlaybookStoreError as exc:
        await db.rollback()
        own = _OWN.get(exc.code)
        if own is None:
            raise editor_refused(exc) from None
        template, status = own
        slots = {"version": int(exc.slots["version"])} if "version" in exc.slots else {}
        return respond(RefusedOut(reason=render_explanation(template, **slots)), status)
    except stages.StageProblem as exc:
        await db.rollback()
        raise editor_refused(exc) from None
    except Exception:
        await db.rollback()
        raise
    return result


def _type(strategy_type: str) -> str:
    if strategy_type not in SHOWN_NAMES:
        raise pbs.PlaybookStoreError(pbs.BODY_INVALID, "strategy type", field="strategy_type")
    return strategy_type


@router.get(f"{BASE}/versions", response_model=SystemHistoryOut)
async def system_playbook_history(strategy_type: str, db: Db) -> object:
    async def work() -> SystemHistoryOut:
        rows = await store.history(db, _type(strategy_type))
        return SystemHistoryOut.model_validate({"versions": [_out(v, rows[0].version) for v in rows]})
    return await _run(db, work)


@router.post(f"{BASE}/versions", status_code=201, response_model=SystemVersionOut)
async def save_system_playbook(strategy_type: str, data: SystemSaveIn, db: Db, admin: Admin) -> object:
    """AC-1/AC-2: the editor's whole pre-save check, then the next version with the admin, time and reason."""
    async def work() -> SystemVersionOut:
        precheck(_type(strategy_type), data.body)
        saved = await store.save(db, admin, strategy_type, data.body, data.reason, data.base_version)
        return _out(saved, saved.version)
    return await _run(db, work)


@router.post(f"{BASE}/versions/{{version}}/restore", status_code=201, response_model=SystemVersionOut)
async def restore_system_playbook(strategy_type: str, version: int, data: SystemReasonIn, db: Db,
                                  admin: Admin) -> object:
    """AC-2 "Restore this version": an earlier version's body becomes current as a NEW version."""
    async def work() -> SystemVersionOut:
        earlier = await store.version(db, _type(strategy_type), version)
        precheck(strategy_type, earlier.body)
        saved = await store.restore(db, admin, strategy_type, version, data.reason, data.base_version)
        return _out(saved, saved.version)
    return await _run(db, work)


@router.post(f"{BASE}/approve", status_code=201, response_model=SystemVersionOut)
async def approve_system_playbook(strategy_type: str, data: SystemReasonIn, db: Db, admin: Admin) -> object:
    """AC-3: a Draft system playbook marked approved (a new version, same numbers). The decision row is the recording
    session's (REQ-169 AC-3), not this route's."""
    async def work() -> SystemVersionOut:
        saved = await store.approve(db, admin, _type(strategy_type), data.reason, data.base_version)
        return _out(saved, saved.version)
    return await _run(db, work)
