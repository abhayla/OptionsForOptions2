"""Strategy draft API: Save Draft, list, load, edit, activity history and restore (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-1 (definition and live state are separate objects); REQ-038 AC-2 (activity history with
restore); ADR-051/ADR-060 (one owner user in V1, as W-058's broker routes).

Copy from: legacy-reuse rows ``app/api/routes/strategy.py`` and ``app/schemas/strategies.py`` (REFERENCE/SKIP: their
float P&L calculators and optional strategy_id are not copied).

Bodies carry the definition only: per leg the catalogue contract id, the side and the quantity in units; strike, expiry
and instrument come from the catalogue contract, never from the body. A body field that names live market data (ltp,
bid, iv, spot, margin, ...) is refused with 422; any other unknown field is refused with 422 too - nothing is dropped
silently. Decimals (risk limits) are strings; a JSON number there is refused.

W-024 (REQ-065 AC-2, ADR-003 Q226): every response is a closed ``ApiModel`` and every refusal goes through the one
error boundary (ofo_app/errors.py), so a body holds catalogue text only: 404 for a missing strategy or another user's
(the same answer); 422 for a definition the catalogue refuses (contract not in the catalogue, not live, quantity not
whole lots, another underlying, a name outside ADR-064's list); 409 when the change is based on a stale revision or a
STORED definition no longer reads (unknown schema version, contract id gone, terms changed, malformed) - never a guess.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ofo.engine.legs import Action
from ofo.errors import UserFacing, UserFacingError, render
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.db import get_db
from ofo_app.errors import Failure
from ofo_app.routes.broker import current_user_ref

router = APIRouter()

def _refuse_live_state(data: Any) -> Any:
    if isinstance(data, Mapping):
        live = sorted(k for k in data if k in sf.LIVE_STATE_NAMES)
        if live:
            raise ValueError("live market data is never saved in a strategy")  # logged by loc/type only, never shown
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


class StrategyUpdateIn(StrategyIn):
    expected_revision: int = Field(gt=0, description="The revision this change was based on (409 if another change "
                                                     "landed since)")


# ---- responses: closed ApiModels (no free text can reach a body); exclude_unset keeps the stored form's exact keys ----

class LegOut(ApiModel):
    contract_id: int
    action: Literal["BUY", "SELL"]
    instrument: Identifier
    strike: Optional[Identifier]
    expiry: Identifier
    quantity: int


class RiskLimitsOut(ApiModel):
    max_loss: Optional[Identifier] = None
    max_capital: Optional[Identifier] = None
    max_margin: Optional[Identifier] = None


class PreferencesOut(ApiModel):
    objective: Optional[Identifier] = None
    market_view: Optional[Identifier] = None
    risk_preference: Optional[Identifier] = None
    capital: Optional[Identifier] = None
    expected_range_low: Optional[Identifier] = None
    expected_range_high: Optional[Identifier] = None


class DefinitionOut(ApiModel):
    schema_version: int
    underlying: Literal["NIFTY", "SENSEX"]
    legs: list[LegOut]
    rules_ref: Optional[Identifier]
    risk_limits: RiskLimitsOut
    preferences: PreferencesOut


class StrategyOut(ApiModel):
    id: int
    status: Identifier
    revision: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    definition: DefinitionOut


class SummaryOut(ApiModel):
    id: int
    underlying: Literal["NIFTY", "SENSEX"]
    status: Identifier
    created_at: datetime.datetime
    updated_at: datetime.datetime


class StrategyListOut(ApiModel):
    strategies: list[SummaryOut]


class EntryOut(ApiModel):
    """One activity-history entry. The summary is rendered from stored data through the catalogue on every read."""

    schema_version: int
    seq: int
    at: datetime.datetime
    change_summary: CatalogueText
    definition: DefinitionOut


class HistoryOut(ApiModel):
    entries: list[EntryOut]


class StrategyRefused(UserFacing, Exception):
    """A refused Save Draft call: carries only its `render()` message; the error boundary shows it (422), or at the status of
    ``failure`` (404 not found; 409 for a stale revision or a saved form that no longer reads)."""

    def __init__(self, template: str, failure: Failure | None = None) -> None:
        self.message: UserFacingError = render(template)
        super().__init__(template)
        self.failure: Failure | None = failure


_FORM_TEMPLATE = MappingProxyType({
    sf.CONTRACT_NOT_IN_CATALOGUE: "strategy_contract_not_in_catalogue",
    sf.CONTRACT_TERMS_CHANGED: "strategy_contract_terms_changed",
    sf.CONTRACT_NOT_LIVE: "strategy_contract_not_live",
    sf.QUANTITY_NOT_LOT_MULTIPLE: "strategy_quantity_not_lot_multiple",
    sf.UNDERLYING_MISMATCH: "strategy_underlying_mismatch",
    sf.UNKNOWN_NAME: "strategy_name_not_allowed",
    sf.VALUE_NOT_ALLOWED: "user_input_request_invalid",  # ADR-069: the fixed input error (422), value never echoed
})
#: On the 409 path (a stored definition read back) only these two keep their own message; the rest are "unreadable".
_STORED_OWN_MESSAGE = frozenset({sf.CONTRACT_NOT_IN_CATALOGUE, sf.CONTRACT_TERMS_CHANGED})


def _refused(exc: Exception, form_status: int) -> Exception:
    """The exception the boundary answers: 404 for a missing strategy or entry, else a catalogue message."""
    if isinstance(exc, store.StrategyStoreError):
        if exc.code in (store.NOT_FOUND, store.HISTORY_NOT_FOUND):
            return StrategyRefused("user_input_request_not_available", Failure.NOT_FOUND)
        if exc.code == store.REVISION_CONFLICT:
            return StrategyRefused("strategy_revision_conflict", Failure.CONFLICT)
        return StrategyRefused("strategy_underlying_fixed")
    assert isinstance(exc, sf.StoredFormError)
    if form_status == 409:
        own = exc.code in _STORED_OWN_MESSAGE
        return StrategyRefused(_FORM_TEMPLATE[exc.code] if own else "strategy_stored_unreadable", Failure.CONFLICT)
    return StrategyRefused(_FORM_TEMPLATE.get(exc.code, "strategy_definition_invalid"))


def _strategy_out(stored: store.StoredStrategy) -> StrategyOut:
    return StrategyOut.model_validate({
        "id": stored.id, "status": stored.status, "revision": stored.revision,
        "created_at": stored.created_at, "updated_at": stored.updated_at,
        "definition": sf.to_document(stored.saved)})


async def _definition(db: Any, body: StrategyIn) -> sf.SavedDefinition:
    sf.check_map_names(risk_limits=list(body.risk_limits), preferences=list(body.preferences))  # ADR-064, before any query
    sf.check_setting_values(rules_ref=body.rules_ref, preferences=body.preferences)  # ADR-069, before any query
    limits = {name: sf.limit_from_text(value, f"risk_limit.{name!r}") for name, value in body.risk_limits.items()}
    return await store.build_definition(
        db, body.underlying, [sf.LegChoice(leg.contract_id, Action(leg.action), leg.quantity) for leg in body.legs],
        rules_ref=body.rules_ref, risk_limits=limits, preferences=dict(body.preferences))


async def _run(db: Any, work: Callable, *, form_status: int) -> Any:
    """Runs one store call; commits on success, rolls back on any error (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except (store.StrategyStoreError, sf.StoredFormError) as exc:
        await db.rollback()
        raise _refused(exc, form_status) from None
    except Exception:
        await db.rollback()
        raise
    return result


@router.post("/strategies", status_code=201, response_model=StrategyOut, response_model_exclude_unset=True)
async def save_draft(body: StrategyIn, db: Any = Depends(get_db),
                     user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        return _strategy_out(await store.save_draft(db, user_ref, await _definition(db, body)))
    return await _run(db, work, form_status=422)


@router.get("/strategies", response_model=StrategyListOut)
async def list_strategies(db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyListOut:
    async def work():
        rows = await store.list_strategies(db, user_ref)
        return StrategyListOut.model_validate({"strategies": [
            {"id": r.id, "underlying": r.underlying, "status": r.status, "created_at": r.created_at,
             "updated_at": r.updated_at} for r in rows]})
    return await _run(db, work, form_status=409)


@router.get("/strategies/{strategy_id}", response_model=StrategyOut, response_model_exclude_unset=True)
async def get_strategy(strategy_id: int, db: Any = Depends(get_db),
                       user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        return _strategy_out(await store.load(db, user_ref, strategy_id))
    return await _run(db, work, form_status=409)


@router.put("/strategies/{strategy_id}", response_model=StrategyOut, response_model_exclude_unset=True)
async def update_strategy(strategy_id: int, body: StrategyUpdateIn, db: Any = Depends(get_db),
                          user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        store.check_strategy_id(strategy_id)  # before the catalogue is read
        return _strategy_out(await store.update(db, user_ref, strategy_id, await _definition(db, body),
                                                expected_revision=body.expected_revision))
    return await _run(db, work, form_status=422)


@router.get("/strategies/{strategy_id}/history", response_model=HistoryOut, response_model_exclude_unset=True)
async def strategy_history(strategy_id: int, db: Any = Depends(get_db),
                           user_ref: str = Depends(current_user_ref)) -> HistoryOut:
    async def work():
        docs = [sf.entry_to_document(e) for e in await store.history(db, user_ref, strategy_id)]
        return HistoryOut.model_validate({"entries": [
            doc | {"change_summary": sf.render_summary(doc["change_summary"])} for doc in docs]})
    return await _run(db, work, form_status=409)


@router.post("/strategies/{strategy_id}/restore/{seq}", response_model=StrategyOut, response_model_exclude_unset=True)
async def restore_strategy(strategy_id: int, seq: int, expected_revision: int = Query(gt=0),
                           db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        return _strategy_out(await store.restore(db, user_ref, strategy_id, seq, expected_revision=expected_revision))
    return await _run(db, work, form_status=409)
