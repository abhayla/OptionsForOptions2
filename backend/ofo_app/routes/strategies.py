"""Strategy draft API: Save Draft, list, load, edit, activity history and restore (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-1 (definition and live state are separate objects); REQ-038 AC-2 (activity history with
restore); ADR-051/ADR-060 (one owner user in V1, as W-058's broker routes).

Copy from: legacy-reuse rows ``app/api/routes/strategy.py`` and ``app/schemas/strategies.py`` (REFERENCE/SKIP: their
float P&L calculators and optional strategy_id are not copied).

Bodies carry the definition only: per leg the catalogue contract id, the side and the quantity in units; strike, expiry
and instrument come from the catalogue contract, never from the body. A body field that names live market data (ltp,
bid, iv, spot, margin, ...) is refused with 422 ``live_state_field``; any other unknown field is refused with 422
too - nothing is dropped silently. Decimals (risk limits) are strings; a JSON number there is refused.

Answers: 201/200 with the strategy; 404 ``{"error": "not_found"}`` for a missing strategy or another user's (the same
answer); 404 ``history_entry_not_found``; 422 ``{"error": <code>}`` for a definition the catalogue refuses (contract
not in the catalogue, not live, quantity not whole lots, another underlying); 409 ``{"error": <code>}`` when a STORED
definition no longer reads (unknown schema version, contract id gone, terms changed, malformed) - never a guess.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ofo.engine.legs import Action
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.db import get_db
from ofo_app.routes.broker import current_user_ref

router = APIRouter()


def _refuse_live_state(data: Any) -> Any:
    if isinstance(data, Mapping):
        live = sorted(k for k in data if k in sf.LIVE_STATE_NAMES)
        if live:
            raise ValueError(f"live_state_field: {', '.join(live)} is live market data and is never saved in a strategy")
    return data


class LegIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contract_id: int = Field(gt=0, description="The catalogue's internal contract id (never a broker token)")
    action: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, description="Units (lots x lot size)")

    _no_live = model_validator(mode="before")(_refuse_live_state)


class StrategyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[LegIn] = Field(min_length=1)
    rules_ref: Optional[str] = None
    risk_limits: dict[str, str] = Field(default_factory=dict, description="name -> decimal as a string")
    preferences: dict[str, str] = Field(default_factory=dict)

    _no_live = model_validator(mode="before")(_refuse_live_state)


def _error(status: int, code: str, detail: Optional[str] = None) -> JSONResponse:
    content = {"error": code} if detail is None else {"error": code, "detail": detail}
    return JSONResponse(status_code=status, content=content)


def _refused(exc: Exception, form_status: int) -> JSONResponse:
    if isinstance(exc, store.StrategyStoreError):
        if exc.code == store.NOT_FOUND:
            return _error(404, store.NOT_FOUND)
        if exc.code == store.HISTORY_NOT_FOUND:
            return _error(404, exc.code)
        return _error(422, exc.code, exc.detail)
    assert isinstance(exc, sf.StoredFormError)
    return _error(form_status, exc.code, exc.detail)


def _strategy_out(stored: store.StoredStrategy) -> dict[str, Any]:
    return {"id": stored.id, "status": stored.status, "created_at": stored.created_at.isoformat(),
            "updated_at": stored.updated_at.isoformat(), "definition": sf.to_document(stored.saved)}


async def _definition(db: Any, body: StrategyIn) -> sf.SavedDefinition:
    limits = {name: sf.decimal_from_text(value, f"risk limit {name!r}") for name, value in body.risk_limits.items()}
    return await store.build_definition(
        db, body.underlying, [sf.LegChoice(leg.contract_id, Action(leg.action), leg.quantity) for leg in body.legs],
        rules_ref=body.rules_ref, risk_limits=limits, preferences=dict(body.preferences))


async def _run(db: Any, work: Callable, *, form_status: int, status: int = 200) -> JSONResponse:
    """Runs one store call; commits on success, rolls back on any error (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except (store.StrategyStoreError, sf.StoredFormError) as exc:
        await db.rollback()
        return _refused(exc, form_status)
    except Exception:
        await db.rollback()
        raise
    return JSONResponse(status_code=status, content=result)


@router.post("/strategies", status_code=201)
async def save_draft(body: StrategyIn, db: Any = Depends(get_db),
                     user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        return _strategy_out(await store.save_draft(db, user_ref, await _definition(db, body)))
    return await _run(db, work, form_status=422, status=201)


@router.get("/strategies")
async def list_strategies(db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        rows = await store.list_strategies(db, user_ref)
        return {"strategies": [{"id": r.id, "underlying": r.underlying, "status": r.status,
                                "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat()}
                               for r in rows]}
    return await _run(db, work, form_status=409)


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: int, db: Any = Depends(get_db),
                       user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        return _strategy_out(await store.load(db, user_ref, strategy_id))
    return await _run(db, work, form_status=409)


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: int, body: StrategyIn, db: Any = Depends(get_db),
                          user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        return _strategy_out(await store.update(db, user_ref, strategy_id, await _definition(db, body)))
    return await _run(db, work, form_status=422)


@router.get("/strategies/{strategy_id}/history")
async def strategy_history(strategy_id: int, db: Any = Depends(get_db),
                           user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        return {"entries": [sf.entry_to_document(e) for e in await store.history(db, user_ref, strategy_id)]}
    return await _run(db, work, form_status=409)


@router.post("/strategies/{strategy_id}/restore/{seq}")
async def restore_strategy(strategy_id: int, seq: int, db: Any = Depends(get_db),
                           user_ref: str = Depends(current_user_ref)) -> JSONResponse:
    async def work():
        return _strategy_out(await store.restore(db, user_ref, strategy_id, seq))
    return await _run(db, work, form_status=409)
