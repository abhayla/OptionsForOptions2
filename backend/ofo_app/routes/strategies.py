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

ADR-075 (issue #208): a leg may carry its planned entry price and capture time (``planned_entry`` as decimal text,
``captured_at`` as ISO 8601 with an offset, both or neither). They are part of the definition: stored, returned on every
load and in every history entry, and changed only by a save that sends new ones (a reprice). A leg without them (a
draft saved before ADR-075) is returned without the two keys; nothing re-captures them on load.

W-024 (REQ-065 AC-2, ADR-003 Q226): every response is a closed ``ApiModel`` and every refusal goes through the one
error boundary (ofo_app/errors.py), so a body holds catalogue text only: 404 for a missing strategy or another user's
(the same answer); 422 for a definition the catalogue refuses (contract not in the catalogue, not live, quantity not
whole lots, another underlying, a name outside ADR-064's list); 409 when the change is based on a stale revision or a
STORED definition no longer reads (unknown schema version, contract id gone, terms changed, malformed) - never a guess.
"""

from __future__ import annotations

import datetime
from collections import Counter
from collections.abc import Callable, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, Query
from ofo.engine.legs import Action
from ofo.engine.legs import Leg as EngineLeg
from ofo.errors import LegValue, render
from ofo.strategy import stored_form as sf
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ofo_app import eligibility_from_zerodha as elig
from ofo_app import paper_store, tracked_contracts
from ofo_app import strategy_store as store
from ofo_app.api_models import ApiModel, CatalogueText, Identifier, Money
from ofo_app.db import get_db
from ofo_app.errors import ClosedRoute, Failure
from ofo_app.routes.broker import current_user_ref
from ofo_app.strategy_refused import StrategyRefused
from ofo_app.tracked_contracts import ContractState
from ofo_app.underlying import Underlying

router = APIRouter(route_class=ClosedRoute)

def _refuse_live_state(data: Any) -> Any:
    if isinstance(data, Mapping):
        live = sorted(k for k in data if k in sf.LIVE_STATE_NAMES)
        if live:
            raise ValueError("live market data is never saved in a strategy")  # logged by loc/type only, never shown
    return data


class LegIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # No range here: an id outside 1..MAX_CONTRACT_ID (0, -1, 10^18 and up, past bigint) is refused by the domain as
    # MISSING_CONTRACT_ID and answered like any id the catalogue does not hold, one code for both sides (issue #184).
    contract_id: int = Field(description="The catalogue's internal contract id (never a broker token)")
    action: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0, description="Units (lots x lot size)")
    planned_entry: Optional[str] = Field(default=None, examples=["44.90"],
                                         description="ADR-075: the leg's planned entry price, decimal text in rupees")
    captured_at: Optional[str] = Field(default=None, examples=["2026-10-15T11:02:17+05:30"],
                                       description="ADR-075: when the planned entry was captured, ISO 8601 with offset")
    entry_source: Literal["typed", "captured"] | None = Field(
        default=None, description="REQ-077 AC-4: 'typed' when the planned entry is the user's own price (its time "
                                  "is captured_at); absent or 'captured' otherwise. Only with the pair")

    _no_live = model_validator(mode="before")(_refuse_live_state)


class StrategyIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    underlying: Underlying
    legs: list[LegIn] = Field(min_length=1)
    rules_ref: Optional[str] = None
    risk_limits: dict[str, str] = Field(default_factory=dict, description="name -> decimal as a string")
    preferences: dict[str, str] = Field(default_factory=dict)

    _no_live = model_validator(mode="before")(_refuse_live_state)


class StrategyCreateIn(StrategyIn):
    """Save Draft and Save As (REQ-134 AC-1, AC-2): a new strategy with the name the user typed. The name is optional
    only so an older client keeps working; it then holds the default (``sf.DEFAULT_STRATEGY_NAME``)."""

    name: str = Field(default=sf.DEFAULT_STRATEGY_NAME,
                      description="1 to 20 characters after trimming, one line; duplicates allowed (REQ-134 AC-1)")


class StrategyNameIn(BaseModel):
    """Rename (REQ-134 AC-3): the new name and the revision the screen showed."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    expected_revision: int = Field(gt=0, description="The revision this change was based on (409 if another change "
                                                     "landed since)")


class StrategyUpdateIn(StrategyIn):
    expected_revision: int = Field(gt=0, description="The revision this change was based on (409 if another change "
                                                     "landed since)")


# ---- responses: closed ApiModels (no free text can reach a body); exclude_unset keeps the stored form's exact keys ----

class LegOut(ApiModel):
    contract_id: int
    action: Literal["BUY", "SELL"]
    # Issue #500: the catalogue's answer for the leg's stored contract. Segment and token (the id the outcome API prices
    # by) are set ONLY when it is live; otherwise both are None and contract_state says why (tracked_contracts).
    contract_state: ContractState
    exchange_segment: Optional[Identifier]  # noqa: UP045 - None when contract_state is not live
    exchange_token: Optional[int]  # noqa: UP045 - None when contract_state is not live
    instrument: Identifier
    strike: Optional[Identifier]
    expiry: Identifier
    quantity: int
    planned_entry: Optional[Money] = None  # ADR-075; absent (unset) for a leg saved without one
    captured_at: Optional[datetime.datetime] = None
    entry_source: Literal["typed", "captured"] | None = None  # REQ-077 AC-4; set with the pair (pre-0024: captured)


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
    underlying: Underlying
    legs: list[LegOut]
    rules_ref: Optional[Identifier]
    risk_limits: RiskLimitsOut
    preferences: PreferencesOut


class VersionOut(ApiModel):
    """W-144 (REQ-038 AC-2/AC-3): one version after the first execution; ``state`` says which one is active."""

    number: int
    state: Literal["proposed", "active", "superseded"]
    based_on: Optional[int]  # noqa: UP045 - None for version 1
    created_at: datetime.datetime
    confirmed_at: Optional[datetime.datetime]  # noqa: UP045 - None until the user confirms
    reconciled_at: Optional[datetime.datetime]  # noqa: UP045 - None until a reconciled return activates it
    outcome: Optional[Identifier]  # noqa: UP045 - the last execution outcome recorded for it
    reconciliation_required: bool  # the active version only: Zerodha is away from it (ADR-018); sticky
    definition: DefinitionOut  # what this version holds: a proposed version is read back here (REQ-038 AC-3)


class StrategyOut(ApiModel):
    id: int
    name: CatalogueText  # REQ-134: the user's name, quoted user text (strip the outer quotes to edit it)
    status: Identifier
    revision: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    definition: DefinitionOut  # the ACTIVE definition (after the first execution, the active version's)
    versions: list[VersionOut] = Field(default_factory=list)  # W-144: empty before the first execution


class FirstLegOut(ApiModel):
    """REQ-134 AC-4: the first leg's contract terms; the browser writes "NIFTY 27 Oct 22500 PE and 3 more"."""

    instrument: Identifier
    strike: Optional[Identifier]  # noqa: UP045 - None for a future
    expiry: Identifier


class SummaryOut(ApiModel):
    id: int
    underlying: Underlying
    status: Identifier
    created_at: datetime.datetime
    updated_at: datetime.datetime
    name: CatalogueText  # REQ-134 AC-4: quoted user text
    leg_count: int  # legs of the active definition; "and N more" is leg_count - 1
    first_leg: FirstLegOut
    tracked: Optional[bool]  # noqa: UP045 - True/False from the tracking store; None = could not be read (never "no")
    can_delete: bool  # REQ-070 AC-6: False once a basket was sent (or when that could not be read)


class RenamedOut(ApiModel):
    id: int
    name: CatalogueText
    revision: int  # unchanged by a rename (REQ-134 AC-3)
    updated_at: datetime.datetime  # unchanged by a rename: the last-saved time follows the definition


class DeletedOut(ApiModel):
    id: int
    revision: int  # unchanged by a delete or its Undo


class StrategyListOut(ApiModel):
    strategies: list[SummaryOut]


class EntryOut(ApiModel):
    """One activity-history entry. The summary is rendered from stored data through the catalogue on every read."""

    schema_version: int
    seq: int
    at: datetime.datetime
    change_summary: CatalogueText
    definition: DefinitionOut
    restorable: bool  # the server's answer (the rule restore enforces); the screen offers Restore/Undo only on true


class HistoryOut(ApiModel):
    entries: list[EntryOut]


_FORM_TEMPLATE = MappingProxyType({
    sf.CONTRACT_NOT_IN_CATALOGUE: "strategy_contract_not_in_catalogue",
    sf.MISSING_CONTRACT_ID: "strategy_contract_not_in_catalogue",  # an id outside 1..MAX_CONTRACT_ID is in no catalogue
    sf.CONTRACT_TERMS_CHANGED: "strategy_contract_terms_changed",
    sf.CONTRACT_NOT_LIVE: "strategy_contract_not_live",
    sf.QUANTITY_NOT_LOT_MULTIPLE: "strategy_quantity_not_lot_multiple",
    sf.UNDERLYING_MISMATCH: "strategy_underlying_mismatch",
    sf.UNKNOWN_NAME: "strategy_name_not_allowed",
    sf.STRATEGY_NAME_EMPTY: "strategy_name_empty",  # REQ-134 AC-1: "Give the strategy a name"
    sf.STRATEGY_NAME_INVALID: "strategy_name_invalid",
    sf.VALUE_NOT_ALLOWED: "user_input_request_invalid",  # ADR-069: the fixed input error (422), value never echoed
    sf.INVALID_PLANNED_ENTRY: "user_input_request_invalid",  # ADR-075: a malformed / one-sided / future entry (422)
})
#: On the 409 path (a stored definition read back) only these two keep their own message; the rest are "unreadable".
_STORED_OWN_MESSAGE = frozenset({sf.CONTRACT_NOT_IN_CATALOGUE, sf.CONTRACT_TERMS_CHANGED})


#: A store refusal's code -> (template, status); any other store code is the underlying refusal (422).
_STORE_REFUSAL = MappingProxyType({
    store.NOT_FOUND: ("user_input_request_not_available", Failure.NOT_FOUND),
    store.HISTORY_NOT_FOUND: ("user_input_request_not_available", Failure.NOT_FOUND),
    store.VERSION_NOT_FOUND: ("user_input_request_not_available", Failure.NOT_FOUND),
    store.REVISION_CONFLICT: ("strategy_revision_conflict", Failure.CONFLICT),
    store.RESTORE_AFTER_EXECUTION: ("strategy_restore_after_execution", Failure.CONFLICT),  # W-144, ADR-019
    store.VERSION_PENDING: ("strategy_version_pending", Failure.CONFLICT),  # W-144, ADR-019 Q191
    store.RECONCILIATION_REQUIRED: ("strategy_reconciliation_required", Failure.CONFLICT),  # ADR-018, Q222
    store.DELETE_AFTER_BASKET: ("strategy_delete_after_basket", Failure.CONFLICT),  # REQ-070 AC-6, ADR-118
})


def refused_answer(exc: Exception, form_status: int) -> Exception:
    """The exception the boundary answers: 404 for a missing strategy or entry, else a catalogue message."""
    if isinstance(exc, store.StrategyStoreError):
        template, failure = _STORE_REFUSAL.get(exc.code, ("strategy_underlying_fixed", None))
        return StrategyRefused(template, failure)
    assert isinstance(exc, sf.StoredFormError)
    if form_status == 409:
        own = exc.code in _STORED_OWN_MESSAGE
        return StrategyRefused(_FORM_TEMPLATE[exc.code] if own else "strategy_stored_unreadable", Failure.CONFLICT)
    return StrategyRefused(_FORM_TEMPLATE.get(exc.code, "strategy_definition_invalid"))


def _definition_out(saved: sf.SavedDefinition) -> dict:
    """The stored form for a response; a leg's planned entry goes out as its Decimal and aware datetime (the door
    writes them as a plain-digit string and ISO text), so no text from the row reaches the body unparsed."""
    doc = sf.to_document(saved)
    entries = saved.entries if isinstance(saved, sf.SavedDefinition) else ()  # to_document already refused others
    for leg, entry in zip(doc["legs"], entries):
        if entry is not None:
            leg["planned_entry"], leg["captured_at"] = entry.price, entry.captured_at
            leg["entry_source"] = entry.source
    return doc


async def _with_tokens(db: Any, *docs: dict) -> None:
    """Adds each leg's catalogue answer to the documents in place (issue #500): ``contract_state`` and, ONLY when that
    is live, the exchange segment and token the outcome API prices it by. The stored form keeps only the contract id
    (ADR-057), and a retired or delisted contract's token may now belong to a new contract (ADR-059), so the key comes
    from ofo_app.tracked_contracts.resolve, the one door; a leg that is not live (retired, delisted, token reassigned,
    missing) gets None for both, so no outcome request can carry another contract's key (fail closed)."""
    ids = sorted({leg["contract_id"] for doc in docs for leg in doc["legs"]})
    found = {c.contract_id: c for c in await tracked_contracts.resolve(db, ids)}
    for doc in docs:
        for leg in doc["legs"]:
            answer = found[leg["contract_id"]]
            feed_id = answer.feed_id
            leg["contract_state"] = answer.state
            leg["exchange_segment"] = None if feed_id is None else feed_id.exchange_segment
            leg["exchange_token"] = None if feed_id is None else feed_id.exchange_token


async def _strategy_out(db: Any, stored: store.StoredStrategy) -> StrategyOut:
    doc = _definition_out(stored.saved)
    version_docs = [_definition_out(await store.version_saved(db, v)) for v in stored.versions]
    await _with_tokens(db, doc, *version_docs)
    return StrategyOut.model_validate({
        "id": stored.id, "name": sf.shown_name(stored.name), "status": stored.status, "revision": stored.revision,
        "created_at": stored.created_at, "updated_at": stored.updated_at, "definition": doc,
        "versions": [{"number": v.number, "state": v.state, "based_on": v.based_on, "created_at": v.created_at,
                      "confirmed_at": v.confirmed_at, "reconciled_at": v.reconciled_at, "outcome": v.outcome,
                      "reconciliation_required": v.reconciliation_required, "definition": d}
                     for v, d in zip(stored.versions, version_docs, strict=True)]})


async def _definition(db: Any, body: StrategyIn) -> sf.SavedDefinition:
    sf.check_map_names(risk_limits=list(body.risk_limits), preferences=list(body.preferences))  # ADR-064, before any query
    sf.check_setting_values(rules_ref=body.rules_ref, preferences=body.preferences)  # ADR-069, before any query
    limits = {name: sf.limit_from_text(value, f"risk_limit.{name!r}") for name, value in body.risk_limits.items()}
    now = datetime.datetime.now(datetime.timezone.utc)
    entries = [None if leg.planned_entry is None and leg.captured_at is None
               else sf.entry_from_input(leg.planned_entry, leg.captured_at, now, f"leg_{i + 1}",
                                        leg.entry_source or sf.SOURCE_CAPTURED)
               for i, leg in enumerate(body.legs)]  # ADR-075, before any query
    for i, leg in enumerate(body.legs):  # REQ-077 AC-4: a mark without the pair is refused, never dropped
        if leg.entry_source is not None and entries[i] is None:
            raise sf.StoredFormError(sf.INVALID_PLANNED_ENTRY, f"leg_{i + 1}.entry_source needs the entry pair")
    return await store.build_definition(
        db, body.underlying, [sf.LegChoice(leg.contract_id, Action(leg.action), leg.quantity, entry)
                              for leg, entry in zip(body.legs, entries)],
        rules_ref=body.rules_ref, risk_limits=limits, preferences=dict(body.preferences))


_NO_PRICE = Decimal("0")  # the message names the leg's contract only; no price is shown


def _leg_identity(saved: sf.SavedDefinition) -> list[tuple[int, Action]]:
    """A leg is the same leg when its contract and side are the same (quantity and planned entry do not make it new)."""
    legs = saved.definition.legs
    return [(contract_id, leg.action) for contract_id, leg in zip(saved.contract_ids, legs, strict=True)]


def _added_legs(saved: list[tuple[int, Action]], stored: list[tuple[int, Action]]) -> list[int]:
    """Indexes of the saved legs that are ADDED relative to the stored version, counted per copy (a multiset): a second
    copy of a stored leg is added. Defence in depth: the definition refuses two legs on one contract today."""
    kept = Counter(stored)
    added = []
    for i, key in enumerate(saved):
        if kept[key] > 0:
            kept[key] -= 1
        else:
            added.append(i)
    return added


async def _check_eligible(db: Any, saved: sf.SavedDefinition, today_of: elig.TodayReader,
                          stored: sf.SavedDefinition | None) -> None:
    """W-092 / ADR-104, REQ-053 AC-3 add-time check: every ADDED leg's contract must be eligible from Zerodha's data
    (in the current list, not expired on the database clock's India date). A leg already in the stored version
    (``stored``, None for a new strategy; counted per copy, so a second copy of a stored leg is added) never blocks a
    save, so an old draft stays editable; the execution gate
    re-checks every leg. The first added leg that is not eligible is refused with the gate's own message
    (gate_contract_unavailable, or gate_contract_unconfirmed when no list was ever loaded)."""
    added = _added_legs(_leg_identity(saved), _leg_identity(stored) if stored is not None else [])
    if not added:
        return
    statuses = await elig.leg_statuses(db, [saved.contract_ids[i] for i in added], await today_of(db))
    underlying = saved.definition.underlying
    for index, status in zip(added, statuses, strict=True):
        if status is not None and status.tradable:
            continue
        leg = saved.definition.legs[index]
        engine_leg = EngineLeg(leg.action, leg.instrument, leg.strike, leg.expiry, leg.quantity, _NO_PRICE)
        value = LegValue(index + 1, engine_leg,
                         underlying)
        template = "gate_contract_unconfirmed" if status is None else "gate_contract_unavailable"
        raise StrategyRefused(template, message=render(template, leg=value))


async def _run(db: Any, work: Callable, *, form_status: int) -> Any:
    """Runs one store call; commits on success, rolls back on any error (nothing half-written)."""
    try:
        result = await work()
        await db.commit()
    except (store.StrategyStoreError, sf.StoredFormError) as exc:
        await db.rollback()
        raise refused_answer(exc, form_status) from None
    except Exception:
        await db.rollback()
        raise
    return result


@router.post("/strategies", status_code=201, response_model=StrategyOut, response_model_exclude_unset=True)
async def save_draft(body: StrategyCreateIn, today_of: Annotated[elig.TodayReader, Depends(elig.get_eligibility_today)],
                     db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        saved = await _definition(db, body)
        await _check_eligible(db, saved, today_of, None)
        return await _strategy_out(db, await store.save_draft(db, user_ref, saved, body.name))
    return await _run(db, work, form_status=422)


@router.get("/strategies", response_model=StrategyListOut)
async def list_strategies(db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyListOut:
    async def work():
        rows = await store.list_strategies(db, user_ref)
        tracked = await _tracked_ids(db, [r.id for r in rows])
        return StrategyListOut.model_validate({"strategies": [
            {"id": r.id, "underlying": r.underlying, "status": r.status, "created_at": r.created_at,
             "updated_at": r.updated_at, "name": sf.shown_name(r.name), "leg_count": r.leg_count,
             "first_leg": {"instrument": r.first_leg.instrument, "strike": r.first_leg.strike,
                           "expiry": r.first_leg.expiry},
             "tracked": None if tracked is None else r.id in tracked, "can_delete": r.can_delete} for r in rows]})
    return await _run(db, work, form_status=409)


async def _tracked_ids(db: Any, ids: list[int]) -> set[int] | None:
    """The ids with a tracking row, or None when the tracking store cannot be read: the list still answers and every
    row says "unknown", never "not tracked" by default (REQ-134 AC-4). The read runs in its own savepoint."""
    try:
        async with db.begin_nested():
            return await paper_store.tracked_ids(db, ids)
    except Exception:  # noqa: BLE001 - any read failure only costs the tracked flag
        return None


@router.patch("/strategies/{strategy_id}/name", response_model=RenamedOut, response_model_exclude_unset=True)
async def rename_strategy(strategy_id: int, body: StrategyNameIn, db: Annotated[Any, Depends(get_db)],
                          user_ref: Annotated[str, Depends(current_user_ref)]) -> RenamedOut:
    """REQ-134 AC-3: changes only the name (and adds one history entry). 404 for another user's strategy, 409 on a
    stale revision, 422 for an empty or over-long name."""
    async def work():
        renamed = await store.rename(db, user_ref, strategy_id, body.name, expected_revision=body.expected_revision)
        return RenamedOut.model_validate({"id": renamed.id, "name": sf.shown_name(renamed.name),
                                          "revision": renamed.revision, "updated_at": renamed.updated_at})
    return await _run(db, work, form_status=422)


@router.delete("/strategies/{strategy_id}", response_model=DeletedOut)
async def delete_strategy(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                          user_ref: Annotated[str, Depends(current_user_ref)],
                          expected_revision: Annotated[int, Query(gt=0)]) -> DeletedOut:
    """REQ-070 AC-6: hides a strategy that never sent a basket (its rows and history stay). 409 `Can't delete: orders
    were sent` otherwise; 404 for another user's, a missing or an already hidden strategy."""
    async def work():
        await store.delete_draft(db, user_ref, strategy_id, expected_revision=expected_revision)
        return DeletedOut.model_validate({"id": strategy_id, "revision": expected_revision})
    return await _run(db, work, form_status=409)


@router.post("/strategies/{strategy_id}/undelete", response_model=StrategyOut, response_model_exclude_unset=True)
async def undelete_strategy(strategy_id: int, db: Annotated[Any, Depends(get_db)],
                            user_ref: Annotated[str, Depends(current_user_ref)],
                            expected_revision: Annotated[int, Query(gt=0)]) -> StrategyOut:
    """Undo of a delete: the same strategy comes back (REQ-070 AC-6)."""
    async def work():
        return await _strategy_out(db, await store.undelete_draft(db, user_ref, strategy_id,
                                                                  expected_revision=expected_revision))
    return await _run(db, work, form_status=409)


@router.get("/strategies/{strategy_id}", response_model=StrategyOut, response_model_exclude_unset=True)
async def get_strategy(strategy_id: int, db: Any = Depends(get_db),
                       user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        return await _strategy_out(db, await store.load(db, user_ref, strategy_id))
    return await _run(db, work, form_status=409)


@router.put("/strategies/{strategy_id}", response_model=StrategyOut, response_model_exclude_unset=True)
async def update_strategy(strategy_id: int, body: StrategyUpdateIn,
                          today_of: Annotated[elig.TodayReader, Depends(elig.get_eligibility_today)],
                          db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        store.check_strategy_id(strategy_id)  # before the catalogue is read
        saved = await _definition(db, body)
        await _check_eligible(db, saved, today_of, (await store.load(db, user_ref, strategy_id)).saved)
        return await _strategy_out(db, await store.update(db, user_ref, strategy_id, saved,
                                                          expected_revision=body.expected_revision))
    return await _run(db, work, form_status=422)


@router.get("/strategies/{strategy_id}/history", response_model=HistoryOut, response_model_exclude_unset=True)
async def strategy_history(strategy_id: int, db: Any = Depends(get_db),
                           user_ref: str = Depends(current_user_ref)) -> HistoryOut:
    async def work():
        entries = await store.history(db, user_ref, strategy_id)
        docs = [sf.entry_to_document(e) | {"definition": _definition_out(e.saved), "restorable": e.restorable}
                for e in entries]
        await _with_tokens(db, *(d["definition"] for d in docs))
        return HistoryOut.model_validate({"entries": [
            doc | {"change_summary": sf.render_summary(doc["change_summary"])} for doc in docs]})
    return await _run(db, work, form_status=409)


@router.post("/strategies/{strategy_id}/restore/{seq}", response_model=StrategyOut, response_model_exclude_unset=True)
async def restore_strategy(strategy_id: int, seq: int,
                           today_of: Annotated[elig.TodayReader, Depends(elig.get_eligibility_today)],
                           expected_revision: int = Query(gt=0),
                           db: Any = Depends(get_db), user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    async def work():
        current = (await store.load(db, user_ref, strategy_id)).saved
        for entry in await store.history(db, user_ref, strategy_id):
            if entry.seq == seq:  # a missing entry is left to restore, which answers it as not found
                await _check_eligible(db, entry.saved, today_of, current)
        return await _strategy_out(db, await store.restore(db, user_ref, strategy_id, seq,
                                                           expected_revision=expected_revision))
    return await _run(db, work, form_status=409)


@router.post("/strategies/{strategy_id}/versions/{number}/confirm", response_model=StrategyOut,
             response_model_exclude_unset=True)
async def confirm_version(strategy_id: int, number: int, db: Any = Depends(get_db),
                          user_ref: str = Depends(current_user_ref)) -> StrategyOut:
    """W-144 (REQ-038 AC-3, ADR-019 Q191): the user confirms the pending proposed version. It stays proposed: only a
    reconciled execution return makes it active."""
    async def work():
        return await _strategy_out(db, await store.confirm_version(db, user_ref, strategy_id, number))
    return await _run(db, work, form_status=409)


# --- GC-UI step 5 (D-B40 / D-B41; REQ-091 AC-1..AC-6, ADR-203, F-64): the Strategy Chart's data ----------------------

PRICE_HISTORY_HELD = "price_history_held"
PriceHistoryState = Literal["available", "leg_not_listed", "no_future_candles", "all_gaps", "no_session",
                            "broker_refused", "future_not_in_catalogue", "quantity_not_whole_lots"]


def require_price_history() -> None:
    """REQ-091 AC-1 (SPEC CHANGE by ADR-203): the held flag ``strategy_price_history``; off -> 409, before any read."""
    from ofo_app import held_switches  # noqa: PLC0415 - one reader of the held flags

    if not held_switches.held_on(held_switches.STRATEGY_PRICE_HISTORY):
        raise StrategyRefused(PRICE_HISTORY_HELD, Failure.CONFLICT)


def get_history_opener() -> Any:
    from ofo_app.price_history_source import history_opener  # noqa: PLC0415 - the adapter loads only on use
    return history_opener()


def get_future_finder() -> Any:
    from ofo_app.strategy_price_history import nearest_future  # noqa: PLC0415
    return nearest_future


def get_history_now() -> datetime.datetime:
    from ofo.timeutil import IST  # noqa: PLC0415
    return datetime.datetime.now(IST)


class PriceValueOut(ApiModel):
    value: Money
    display: CatalogueText


class PricePointOut(ApiModel):
    t: datetime.datetime
    strategy: Optional[PriceValueOut]  # noqa: UP045 - None = a gap (a leg had no candle that minute, REQ-091 AC-4)
    future: PriceValueOut


class PriceHistoryOut(ApiModel):
    available: bool
    state: PriceHistoryState
    reason: Optional[CatalogueText]  # noqa: UP045
    source: CatalogueText
    future_label: Optional[CatalogueText]  # noqa: UP045
    as_of: Optional[datetime.datetime]  # noqa: UP045 - the newest point's time (ADR-015)
    notes: list[CatalogueText]
    points: list[PricePointOut]


@router.get("/strategies/{strategy_id}/price-history", response_model=PriceHistoryOut,
            dependencies=[Depends(require_price_history)])
async def strategy_price_history(  # noqa: PLR0913 - one query parameter or seam each
        strategy_id: int, db: Annotated[Any, Depends(get_db)], user_ref: Annotated[str, Depends(current_user_ref)],
        opener: Annotated[Any, Depends(get_history_opener)], finder: Annotated[Any, Depends(get_future_finder)],
        now: Annotated[datetime.datetime, Depends(get_history_now)],
        invert: Annotated[bool, Query()] = False, days: Annotated[int, Query(ge=1, le=15)] = 10) -> PriceHistoryOut:
    """The strategy's combined net price per unit per minute beside the index future (REQ-091 AC-2..AC-5). Another
    user's strategy answers exactly as a missing one (store.load is owner-scoped). Prices only, no P&L (AC-6)."""
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415
    from ofo.outcome import price_history as ph  # noqa: PLC0415

    from ofo_app import strategy_price_history as sph  # noqa: PLC0415

    async def work():
        # S5-1: the owner's token is read FIRST, while this request's connection holds no transaction: the read may
        # commit (an expired session is ended) and refuses a connection in a transaction (GC-6 MAJOR-1). One
        # connection per request (ADR-048); a store error answers no_session, never a 500.
        reader = await opener(db)
        stored = await store.load(db, user_ref, strategy_id)
        # Issue #500: a stored contract id reaches a ListedContract only through tracked_contracts.resolve, the one door.  # noqa: E501 - long line kept whole
        answers = await tracked_contracts.resolve(db, stored.saved.contract_ids)
        if any(a.stored is None for a in answers):
            raise StrategyRefused("strategy_stored_unreadable", Failure.CONFLICT)
        listed = [a.stored.listed for a in answers]  # type: ignore[union-attr]
        for a in answers:
            if a.state != tracked_contracts.LIVE:  # retired / delisted / token reassigned: no chart, no Kite fetch
                return sph.Answer("leg_not_listed", render_explanation("price_history_leg_not_listed",
                                                                       leg=sph.label(a.stored.listed)))  # type: ignore[union-attr]
        definition = stored.saved.definition
        legs = []
        for leg, lc in zip(definition.legs, listed, strict=True):  # saved quantity is lots x lot size
            lots, rest = divmod(leg.quantity, lc.contract.lot_size)
            if rest or lots < 1:  # F4: a lot-size change after saving; never a silent floor, never a 500
                return sph.Answer("quantity_not_whole_lots", render_explanation("price_history_quantity_not_whole_lots",
                                                                                leg=sph.label(lc)))
            legs.append(sph.ChartLeg(leg.action, lots))
        return await sph.prepare(db, legs, listed, definition.underlying, reader=reader, finder=finder)
    # F1: every DB read above ran in ONE short block; _run commits it, which hands the pooled connection back BEFORE
    # any Kite call. The Kite phase below gets no database handle (pool: 2 connections shared with orders).
    plan = await _run(db, work, form_status=409)
    ans = plan if isinstance(plan, sph.Answer) else await sph.fetch(plan, days=days, invert=invert, now=now)
    chart = ans.chart
    points = [] if chart is None or ans.state != "available" else [
        PricePointOut(t=p.t, future=PriceValueOut(value=p.future, display=ph.future_display(p.future)),
                      strategy=None if p.strategy is None else PriceValueOut(
                          value=p.strategy, display=ph.strategy_display(p.strategy)))
        for p in chart.points]
    return PriceHistoryOut(available=ans.state == "available", state=ans.state, reason=ans.reason,
                           source=render_explanation("price_history_source"), future_label=ans.future_label,
                           as_of=None if not points else chart.as_of, notes=list(ans.notes), points=points)
