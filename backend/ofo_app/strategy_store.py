"""PostgreSQL store for strategy drafts and their pre-execution activity history (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-2 (activity-history entries with restore before the first execution); ADR-016 (no silent
contract substitution); REQ-054 AC-3 / ADR-057 (legs link the catalogue's internal contract id). Schema: migration
0008_strategy_store. The stored form is ofo.strategy.stored_form.

Copy from: legacy-reuse rows ``app/models/strategies.py`` (REFERENCE) and ``app/api/routes/strategy.py`` (REFERENCE /
SKIP: float P&L and optional strategy_id are not copied).

- save_draft: a new strategy (status 'draft') holding the definition; no history entry yet.
- update: writes a history entry holding the PREVIOUS definition (with a plain-words summary of the change), then the
  new definition, inside one savepoint: any error stores nothing. Saving the same text again is not a change.
- restore(seq): the entry's definition becomes current; the replaced one is written as a new entry first. History is
  never deleted or rewritten (the database refuses it; the store never tries).
- load / history: refuse (StoredFormError with a fixed code) a stored form this code does not know, a contract id the
  catalogue no longer holds, or terms that changed; never a guessed replacement.
- Another user's strategy answers exactly like a missing one (NOT_FOUND), so its existence is not told.
Transaction control (commit) stays with the caller.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import text

from ofo.engine.legs import Instrument
from ofo.instruments.models import FUTURE_TYPE
from ofo.strategy import stored_form as sf
from ofo_app.catalogue_store import load_contract

NOT_FOUND = "not_found"
HISTORY_NOT_FOUND = "history_entry_not_found"
UNDERLYING_FIXED = "underlying_fixed"
REVISION_CONFLICT = "revision_conflict"
#: W-144 (REQ-038 AC-2/AC-3, ADR-019): after the first fill, restore is refused and a second pending change is refused.
RESTORE_AFTER_EXECUTION = "restore_after_execution"
VERSION_PENDING = "version_pending"
VERSION_NOT_FOUND = "version_not_found"
#: W-144 fix 1 (ADR-018, REQ-060 Q222): Zerodha is away from the active version; sticky until a recorded resolution.
RECONCILIATION_REQUIRED = "reconciliation_required"


class StrategyStoreError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class StoredStrategy:
    id: int
    user_ref: str
    status: str
    created_at: datetime
    updated_at: datetime
    saved: sf.SavedDefinition
    revision: int
    versions: tuple[StoredVersion, ...] = ()  # W-144: every version after the first execution, by number


@dataclass(frozen=True)
class StrategySummary:
    id: int
    underlying: str
    status: str
    created_at: datetime
    updated_at: datetime


_COLUMNS = "id, user_ref, status, created_at, updated_at, revision, definition::text AS definition_text"
BIGINT_MAX = 2**63 - 1  # strategies.id (BIGSERIAL)
INTEGER_MAX = 2**31 - 1  # strategy_history.seq and strategies.revision (INTEGER)
_INSERT = text(
    "INSERT INTO public.strategies (user_ref, underlying, definition, definition_schema_version) "
    f"VALUES (:user_ref, :underlying, CAST(:definition AS JSONB), :version) RETURNING {_COLUMNS}")
_SELECT = text(f"SELECT {_COLUMNS} FROM public.strategies WHERE id = :id AND user_ref = :user_ref")
_SELECT_FOR_UPDATE = text(
    f"SELECT {_COLUMNS}, underlying FROM public.strategies WHERE id = :id AND user_ref = :user_ref FOR UPDATE")
_LIST = text("SELECT id, underlying, status, created_at, updated_at FROM public.strategies "
             "WHERE user_ref = :user_ref ORDER BY id")
_INSERT_HISTORY = text(
    "INSERT INTO public.strategy_history (strategy_id, change_summary, definition, definition_schema_version) "
    "VALUES (:id, CAST(:summary AS JSONB), CAST(:definition AS JSONB), :version) RETURNING seq")
_UPDATE = text(f"UPDATE public.strategies SET definition = CAST(:definition AS JSONB) WHERE id = :id "
               f"RETURNING {_COLUMNS}")
_HISTORY = text("SELECT seq, at, change_summary::text AS change_summary, definition::text AS definition_text FROM public.strategy_history "
                "WHERE strategy_id = :id ORDER BY seq")
_HISTORY_ONE = text("SELECT definition::text AS definition_text FROM public.strategy_history "
                    "WHERE strategy_id = :id AND seq = :seq")
_EXISTING_IDS = text("SELECT id FROM public.catalogue_contracts WHERE id = ANY(CAST(:ids AS BIGINT[]))")


def _check_id(value: Any, what: str, limit: int = BIGINT_MAX, code: str = NOT_FOUND) -> int:
    """An id outside its column's range cannot exist: answered before any query (never a database range error)."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= limit:
        raise StrategyStoreError(code, f"{what} {value!r}")
    return value


def check_strategy_id(value: Any) -> int:
    return _check_id(value, "strategy")


def _check_revision(row: Any, expected_revision: Any) -> None:
    """Optimistic concurrency: a write names the revision it was based on; another write since then refuses it."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision != row.revision:
        raise StrategyStoreError(REVISION_CONFLICT, f"strategy {row.id} is at revision {row.revision}, the change was "
                                                    f"based on {expected_revision!r}; reload and apply it again")


# ----------------------------------------------------------------------------------------------------------------
# The catalogue link
# ----------------------------------------------------------------------------------------------------------------


async def catalogue_resolver(conn: Any, contract_ids: Iterable[int]) -> sf.Resolver:
    """Reads every named contract id from the catalogue once; the resolver answers None for an id it does not hold."""
    wanted = sorted({c for c in contract_ids if isinstance(c, int) and not isinstance(c, bool) and 0 < c <= sf.MAX_CONTRACT_ID})
    existing = {int(r[0]) for r in (await conn.execute(_EXISTING_IDS, {"ids": wanted})).all()} if wanted else set()
    terms: dict[int, sf.CatalogueTerms] = {}
    for contract_id in sorted(existing):
        stored = await load_contract(conn, contract_id)
        contract = stored.listed.contract
        if contract.instrument_type not in {i.value for i in Instrument}:
            continue  # an INDEX row is not a leg: the resolver does not hold it, so the save refuses it (REQ-001 AC-2)
        future = contract.instrument_type == FUTURE_TYPE
        terms[contract_id] = sf.CatalogueTerms(
            underlying=contract.name, instrument=Instrument(contract.instrument_type),
            strike=None if future else contract.strike, expiry=contract.expiry, lot_size=contract.lot_size,
            live=not stored.retired and not stored.delisted)
    return terms.get


def _contract_ids_in(definition_text: str) -> list[int]:
    """The contract ids a stored text names, read loosely (the strict read happens in stored_form)."""
    try:
        doc = sf.parse_json(definition_text)
    except sf.StoredFormError:
        return []
    legs = doc.get("legs") if isinstance(doc, dict) else None
    if not isinstance(legs, list):
        return []
    return [leg["contract_id"] for leg in legs if isinstance(leg, dict) and isinstance(leg.get("contract_id"), int)]


async def _read(conn: Any, definition_text: str) -> sf.SavedDefinition:
    resolve = await catalogue_resolver(conn, _contract_ids_in(definition_text))
    return sf.loads(definition_text, resolve)


async def build_definition(conn: Any, underlying: str, choices: Sequence[sf.LegChoice], *,
                           rules_ref: Optional[str] = None, risk_limits: Mapping | tuple = (),
                           preferences: Mapping | tuple = ()) -> sf.SavedDefinition:
    """A definition from the user's picks; every leg's terms come from a live catalogue contract."""
    resolve = await catalogue_resolver(conn, [c.contract_id for c in choices if isinstance(c, sf.LegChoice)])
    return sf.build_from_catalogue(underlying, choices, resolve, rules_ref=rules_ref, risk_limits=risk_limits,
                                   preferences=preferences)


# ----------------------------------------------------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------------------------------------------------


def _stored(row: Any, saved: sf.SavedDefinition) -> StoredStrategy:
    return StoredStrategy(id=int(row.id), user_ref=row.user_ref, status=row.status, created_at=row.created_at,
                          updated_at=row.updated_at, saved=saved, revision=int(row.revision))


async def _check_saveable(conn: Any, saved: sf.SavedDefinition) -> str:
    if not isinstance(saved, sf.SavedDefinition):
        raise sf.StoredFormError(sf.INVALID_DEFINITION, f"expected a SavedDefinition, got {saved!r}")
    resolve = await catalogue_resolver(conn, saved.contract_ids)
    sf.check_against_catalogue(saved, resolve, require_live=True)
    return sf.dumps(saved)


async def save_draft(conn: Any, user_ref: str, saved: sf.SavedDefinition) -> StoredStrategy:
    """Save Draft: a new strategy row. The caller commits."""
    if not isinstance(user_ref, str) or not user_ref:
        raise StrategyStoreError(NOT_FOUND, "a strategy belongs to a user")
    document = await _check_saveable(conn, saved)
    async with conn.begin_nested():
        row = (await conn.execute(_INSERT, {"user_ref": user_ref, "underlying": saved.definition.underlying,
                                            "definition": document, "version": sf.SCHEMA_VERSION})).one()
    return _stored(row, saved)


async def _write_history(conn: Any, strategy_id: int, summary: str, current_text: str) -> int:
    summary = sf.check_summary_text(summary)  # closed shape or refused: no text that is not catalogue data is stored
    version = sf.check_schema_version(sf.parse_json(current_text))
    return int((await conn.execute(_INSERT_HISTORY, {"id": strategy_id, "summary": summary,
                                                     "definition": current_text, "version": version})).scalar_one())


async def _write_definition(conn: Any, strategy_id: int, document: str) -> Any:
    return (await conn.execute(_UPDATE, {"id": strategy_id, "definition": document})).one()


async def _locked(conn: Any, user_ref: str, strategy_id: int) -> Any:
    row = (await conn.execute(_SELECT_FOR_UPDATE, {"id": _check_id(strategy_id, "strategy"),
                                                   "user_ref": user_ref})).one_or_none()
    if row is None:
        raise StrategyStoreError(NOT_FOUND, f"strategy {strategy_id}")
    return row


async def lock_strategy(conn: Any, user_ref: str, strategy_id: int) -> None:
    """Takes the strategy's row lock until the caller's transaction ends (W-094: one writer per strategy at a time).
    Another user's strategy answers NOT_FOUND exactly like a missing one."""
    await _locked(conn, user_ref, strategy_id)


async def _summary(conn: Any, current_text: str, new: sf.SavedDefinition) -> str:
    try:
        old = await _read(conn, current_text)
    except sf.StoredFormError:  # the replaced text no longer reads (e.g. a contract's terms changed)
        return sf.unreadable_replacement_summary()
    return sf.change_summary(old, new)


async def update(conn: Any, user_ref: str, strategy_id: int, saved: sf.SavedDefinition, *,
                 expected_revision: int) -> StoredStrategy:
    """A new definition for a draft: history entry of the previous definition first, then the new one, all or
    nothing. ``expected_revision`` is the revision the change was based on (REVISION_CONFLICT otherwise, nothing
    written). After the first fill (W-144) the change is a new PROPOSED version instead and the active definition
    stays as it is (``_propose``). The caller commits."""
    _check_id(strategy_id, "strategy")
    document = await _check_saveable(conn, saved)
    async with conn.begin_nested():
        row = await _locked(conn, user_ref, strategy_id)
        _check_revision(row, expected_revision)
        if row.underlying != saved.definition.underlying:
            raise StrategyStoreError(UNDERLYING_FIXED, f"strategy {strategy_id} is on {row.underlying}; a strategy on "
                                                       f"{saved.definition.underlying} is a new strategy")
        execution = await execution_state(conn, user_ref, row.id)
        if execution != NOT_EXECUTED:
            await _propose(conn, row, saved, document, execution)
            return await load(conn, user_ref, row.id)
        if sf.parse_json(row.definition_text) == sf.parse_json(document):
            return _stored(row, saved)
        summary = await _summary(conn, row.definition_text, saved)
        await _write_history(conn, row.id, summary, row.definition_text)
        written = await _write_definition(conn, row.id, document)
    return _stored(written, saved)


async def restore(conn: Any, user_ref: str, strategy_id: int, seq: int, *,
                  expected_revision: int) -> StoredStrategy:
    """Makes history entry ``seq`` current; the replaced definition is written as a new entry first (nothing is
    deleted). The entry's contracts must still be live with the same terms; ``expected_revision`` as in update.
    The caller commits."""
    _check_id(strategy_id, "strategy")
    _check_id(seq, "history entry", INTEGER_MAX, HISTORY_NOT_FOUND)
    async with conn.begin_nested():
        row = await _locked(conn, user_ref, strategy_id)
        _check_revision(row, expected_revision)
        if await execution_state(conn, user_ref, row.id) != NOT_EXECUTED:  # ADR-019: restore is pre-execution only
            raise StrategyStoreError(RESTORE_AFTER_EXECUTION, f"strategy {strategy_id} has executed")
        entry_text =(await conn.execute(_HISTORY_ONE, {"id": row.id, "seq": seq})).scalar_one_or_none()
        if entry_text is None:
            raise StrategyStoreError(HISTORY_NOT_FOUND, f"strategy {strategy_id} has no history entry {seq}")
        saved = await _read(conn, entry_text)
        resolve = await catalogue_resolver(conn, saved.contract_ids)
        sf.check_against_catalogue(saved, resolve, require_live=True)
        if sf.parse_json(row.definition_text) == sf.parse_json(entry_text):
            return _stored(row, saved)
        await _write_history(conn, row.id, sf.summary_text([{"kind": "restored", "seq": seq}]), row.definition_text)
        written = await _write_definition(conn, row.id, entry_text)
    return _stored(written, saved)


# ----------------------------------------------------------------------------------------------------------------
# Versions after the first execution (W-144; REQ-038 AC-2..AC-4; ADR-019). Schema: migration 0022_strategy_versions.
# The rules are the domain's (ofo.strategy.versions.StrategyRecord): every decision below replays the stored state into
# a StrategyRecord and asks it (edit / confirm / apply_result); nothing here restates when a version may change.
# ----------------------------------------------------------------------------------------------------------------

#: The answers of ``execution_state``. Anything but NOT_EXECUTED is versioned (fail closed).
NOT_EXECUTED = "not_executed"
EXECUTED = "executed"
IN_FLIGHT = "in_flight"  # a plan is open: Zerodha may have filled it, its fill state is unknown
UNREADABLE = "unreadable"  # the plan store could not be read: counted as executed, never a silent overwrite


@dataclass(frozen=True)
class StoredVersion:
    number: int
    state: str  # proposed | active | superseded
    based_on: int | None
    created_at: datetime
    confirmed_at: datetime | None
    reconciled_at: datetime | None
    outcome: str | None
    definition_text: str
    reconciliation_required: bool = False  # set on the active version only (migration 0023)


_VERSIONS = text("SELECT number, state, based_on, created_at, confirmed_at, reconciled_at, outcome, "
                 "definition::text AS definition_text, reconciliation_required FROM public.strategy_versions "
                 "WHERE strategy_id = :id "
                 "ORDER BY number")
_INSERT_VERSION = text(
    "INSERT INTO public.strategy_versions (strategy_id, number, state, based_on, definition, "
    "definition_schema_version, confirmed_at, reconciled_at) "
    "VALUES (:id, :n, :state, :based_on, CAST(:definition AS JSONB), :version, "
    ":confirmed_at, :reconciled_at)")
_CONFIRM_VERSION = text("UPDATE public.strategy_versions SET confirmed_at = clock_timestamp() WHERE strategy_id = :id "
                        "AND number = :n AND state = 'proposed' AND confirmed_at IS NULL")
_SUPERSEDE_ACTIVE = text("UPDATE public.strategy_versions SET state = 'superseded' WHERE strategy_id = :id "
                         "AND state = 'active'")
_ACTIVATE = text("UPDATE public.strategy_versions SET state = 'active', reconciled_at = clock_timestamp(), "
                 "outcome = :outcome, actual = CAST(:actual AS JSONB) WHERE strategy_id = :id AND number = :n "
                 "AND state = 'proposed' AND confirmed_at IS NOT NULL")
_FLAG_ACTIVE = text("UPDATE public.strategy_versions SET reconciliation_required = TRUE WHERE strategy_id = :id "
                    "AND number = :n AND state = 'active'")
_RECORD_OUTCOME = text("UPDATE public.strategy_versions SET state = :state, outcome = :outcome, "
                       "actual = CAST(:actual AS JSONB) WHERE strategy_id = :id AND number = :n AND state = 'proposed'")

#: A closed plan's stored reason as the domain's result status (positions decide; the word only chooses among the
#: outcomes the positions allow). Any other reason is FAILED: it can never activate a version.
_CLOSE_STATUS = {"filled": "complete", "exited": "complete", "partial": "partial", "nothing_placed": "rejected",
                 "unresolved_from_positions": "failed"}


async def _version_rows(conn: Any, strategy_id: int) -> tuple[StoredVersion, ...]:
    return tuple(StoredVersion(int(r.number), r.state, None if r.based_on is None else int(r.based_on), r.created_at,
                               r.confirmed_at, r.reconciled_at, r.outcome, r.definition_text,
                               r.reconciliation_required is True)
                 for r in (await conn.execute(_VERSIONS, {"id": strategy_id})).all())


async def _plans(conn: Any, user_ref: str, strategy_id: int) -> tuple[Any, ...]:
    from ofo_app import execution_plan_store as plans  # noqa: PLC0415 - that module imports this one
    return await plans.plans_for(conn, user_ref, strategy_id)


async def execution_state(conn: Any, user_ref: str, strategy_id: int) -> str:
    """Has the strategy executed? Stored versions, or any plan order with a fill (``execute_plan.latest_filled_plan``,
    the one copy of the rule) -> EXECUTED; an open plan -> IN_FLIGHT; a store that cannot be read -> UNREADABLE.
    Only a readable store with no fill, no open plan and no version is NOT_EXECUTED (fail closed)."""
    from ofo_app import execute_plan as ep  # noqa: PLC0415 - kept with _plans (import order)
    try:
        async with conn.begin_nested():
            versions = await _version_rows(conn, strategy_id)
            history = await _plans(conn, user_ref, strategy_id)
    except Exception:  # noqa: BLE001 - any failure to read is "unknown", and unknown counts as executed
        return UNREADABLE
    if any(p.status == "open" for p in history):  # before the versions: an in-flight plan is never "executed"
        return IN_FLIGHT
    if versions:
        return EXECUTED
    return NOT_EXECUTED if ep.latest_filled_plan(history) is None else EXECUTED


def _now() -> datetime:
    import datetime as _dt  # noqa: PLC0415
    return _dt.datetime.now(_dt.UTC)


def built_from(stored: StoredStrategy) -> int:
    """The version number of the definition ``load`` answered (the one an Execute builds from): the active version's,
    or 1 before any version row exists (that definition becomes version 1 at the first edit, ``_first_version``).
    Version rows with no active one cannot name it: refused (fail closed)."""
    if not stored.versions:
        return 1
    active = next((r for r in stored.versions if r.state == "active"), None)
    if active is None:
        raise StrategyStoreError(VERSION_PENDING, f"strategy {stored.id} has no active version")
    return active.number


def _refuse_if_flagged(strategy_id: int, active: StoredVersion | None) -> None:
    """ADR-018 / REQ-060 Q222: while Zerodha is away from the active version nothing changes it (the stored flag is
    read here first; the replayed domain refuses again)."""
    if active is not None and active.reconciliation_required:
        raise StrategyStoreError(RECONCILIATION_REQUIRED, f"strategy {strategy_id}: reconciliation required")


def _replay(active: Any, proposed: Any = None, *, confirmed: bool = False, flagged: bool = False) -> Any:
    """The stored state as the domain's StrategyRecord: ``active`` executed and reconciled, then ``proposed`` (when
    given) pending, confirmed when ``confirmed``. Its proposal, if any, is domain version 2. ``flagged`` restores the
    sticky ``reconciliation_required`` (a broker observation away from the active version); the domain holds no
    proposal while flagged, so both together are refused (fail closed)."""
    from ofo.strategy import versions as v  # noqa: PLC0415
    at = _now()
    record = v.StrategyRecord(active, at=at)
    record.propose_execution(at=at)
    record.confirm(1, at=at)
    record.apply_result(v.ExecutionResult(1, v.ResultStatus.COMPLETE, v.Position.of(active.intended_position()), at,
                                          "stored-active-version"))
    if flagged:
        if proposed is not None:
            raise StrategyStoreError(RECONCILIATION_REQUIRED, "a flagged strategy holds no replayable proposal")
        record.observe_broker_position(v.Position(), at=at, reference="stored-reconciliation-required")
        if not record.reconciliation_required:
            raise StrategyStoreError(RECONCILIATION_REQUIRED, "the stored flag could not be restored")
        return record
    if proposed is not None and record.edit(proposed, at=at) is not None and confirmed:
        record.confirm(2, at=at)
    return record


async def _first_version(conn: Any, row: Any, user_ref: str, execution: str) -> StoredVersion:
    """Version 1 = the definition that executed (the strategy row, which no edit changes once a plan exists), active
    since the close of the latest filled plan (the return that read it from Zerodha). Without a readable filled plan
    there is no executed definition to name: refused, nothing written."""
    from ofo_app import execute_plan as ep  # noqa: PLC0415
    if execution != EXECUTED:
        raise StrategyStoreError(VERSION_PENDING, f"strategy {row.id}: the executed state cannot be read")
    history = await _plans(conn, user_ref, row.id)
    number = ep.latest_filled_plan(history)
    closed = next((p.closed_at for p in history if p.plan_number == number), None)
    if closed is None:
        raise StrategyStoreError(VERSION_PENDING, f"strategy {row.id}: no closed filled plan")
    version = sf.check_schema_version(sf.parse_json(row.definition_text))
    await conn.execute(_INSERT_VERSION, {"id": row.id, "n": 1, "state": "active", "based_on": None,
                                         "definition": row.definition_text, "version": version,
                                         "confirmed_at": closed, "reconciled_at": closed})
    return (await _version_rows(conn, row.id))[0]


async def _propose(conn: Any, row: Any, saved: sf.SavedDefinition, document: str, execution: str) -> None:
    """After the first fill: the domain's ``edit`` decides; a meaningful change is stored as a new PROPOSED version
    based on the active one, which stays as it is. A pending proposal or an open plan refuses (VERSION_PENDING)."""
    from ofo.strategy.versions import VersionError  # noqa: PLC0415
    if execution == IN_FLIGHT:
        raise StrategyStoreError(VERSION_PENDING, f"strategy {row.id} has an open execution plan")
    rows = await _version_rows(conn, row.id)
    active = next((r for r in rows if r.state == "active"), None)
    if active is None:
        active = await _first_version(conn, row, row.user_ref, execution)
        rows = await _version_rows(conn, row.id)
    pending = next((r for r in rows if r.state == "proposed"), None)
    record = _replay((await _read(conn, active.definition_text)).definition,
                     None if pending is None else (await _read(conn, pending.definition_text)).definition,
                     confirmed=pending is not None and pending.confirmed_at is not None,
                     flagged=active.reconciliation_required)
    try:
        version = record.edit(saved.definition, at=_now())
    except VersionError:
        if record.reconciliation_required:
            raise StrategyStoreError(RECONCILIATION_REQUIRED, f"strategy {row.id}: reconciliation required") from None
        raise StrategyStoreError(VERSION_PENDING, f"strategy {row.id} has a proposed version waiting") from None
    if version is None:
        return  # no meaningful change: nothing written
    await conn.execute(_INSERT_VERSION, {"id": row.id, "n": max(r.number for r in rows) + 1, "state": "proposed",
                                         "based_on": active.number, "definition": document,
                                         "version": sf.SCHEMA_VERSION, "confirmed_at": None, "reconciled_at": None})


async def confirm_version(conn: Any, user_ref: str, strategy_id: int, number: int) -> StoredStrategy:
    """The user's confirmation of the pending proposed version (domain ``confirm``). It never makes the version
    active: only a reconciled execution return does (``settle_versions``). The caller commits."""
    from ofo.strategy.versions import VersionError  # noqa: PLC0415
    _check_id(strategy_id, "strategy")
    _check_id(number, "version", INTEGER_MAX, VERSION_NOT_FOUND)
    async with conn.begin_nested():
        row = await _locked(conn, user_ref, strategy_id)
        rows = await _version_rows(conn, row.id)
        if not any(r.number == number for r in rows):
            raise StrategyStoreError(VERSION_NOT_FOUND, f"strategy {strategy_id} has no version {number}")
        active = next((r for r in rows if r.state == "active"), None)
        pending = next((r for r in rows if r.state == "proposed"), None)
        _refuse_if_flagged(row.id, active)
        if active is None or pending is None or pending.number != number:
            raise StrategyStoreError(VERSION_PENDING, f"version {number} is not the pending proposed version")
        record = _replay((await _read(conn, active.definition_text)).definition,
                         (await _read(conn, pending.definition_text)).definition,
                         confirmed=pending.confirmed_at is not None)
        try:
            record.confirm(2, at=_now())
        except VersionError:
            raise StrategyStoreError(VERSION_PENDING, f"version {number} cannot be confirmed now") from None
        await conn.execute(_CONFIRM_VERSION, {"id": row.id, "n": number})
    return await load(conn, user_ref, strategy_id)


def _actual_json(position: Any) -> str:
    import json  # noqa: PLC0415
    return json.dumps([{"underlying": c[0], "instrument": c[1].value, "strike": None if c[2] is None else str(c[2]),
                        "expiry": c[3].isoformat(), "units": units} for c, units in position.lines])


async def settle_versions(conn: Any, user_ref: str, strategy_id: int, history: Sequence[Any],
                          broker_units: Mapping[tuple, int] | None) -> str | None:
    """Called by the execution return after it closed the open plan (same transaction, strategy row locked).

    Only the CONFIRMED proposed version is judged, and only by a closed ENTRY plan BUILT FROM IT (the plan's stored
    ``strategy_version`` equals its number, created after the confirmation): a plan built from another version, or
    with no link, never moves it (fail closed). The plan's stored close reason is the result status and
    ``broker_units`` (this strategy's share of Zerodha's net per contract; outside lots are not its, ADR-109) is the
    actual position - the broker wins (AC-4). The domain's ``apply_result`` decides: only ACTIVATED makes it active.
    A version is judged once (its outcome is then stored). The sticky flag (ADR-018, Q222) is set on the ACTIVE
    version when the judged result leaves Zerodha away from it: MISMATCH, PARTIAL, REJECTED/FAILED with units
    changed, or ``broker_units`` None (undecidable); while it is set nothing activates (BLOCKED) and no return clears
    it. Returns the outcome kind recorded, or None."""
    from ofo.strategy import versions as v  # noqa: PLC0415
    rows = await _version_rows(conn, strategy_id)
    active = next((r for r in rows if r.state == "active"), None)
    pending = next((r for r in rows if r.state == "proposed" and r.confirmed_at is not None), None)
    if active is None or pending is None or pending.outcome is not None or any(p.status == "open" for p in history):
        return None
    built = [p for p in history if p.action == "ENTRY" and p.status == "closed" and p.created_at is not None
             and p.strategy_version == pending.number and pending.confirmed_at is not None
             and p.created_at >= pending.confirmed_at]
    if not built:
        return None
    if broker_units is None:  # the return cannot tell this strategy's units: reconcile before anything else
        await conn.execute(_FLAG_ACTIVE, {"id": strategy_id, "n": active.number})
        return None
    plan = built[-1]
    status = v.ResultStatus(_CLOSE_STATUS.get(plan.close_reason, "failed"))
    try:
        position = v.Position.of(dict(broker_units))
        record = _replay((await _read(conn, active.definition_text)).definition,
                         (await _read(conn, pending.definition_text)).definition, confirmed=True)
        outcome = record.apply_result(v.ExecutionResult(2, status, position, _now(), f"plan:{plan.plan_number}"))
    except (v.VersionError, sf.StoredFormError):
        await conn.execute(_FLAG_ACTIVE, {"id": strategy_id, "n": active.number})
        return None  # a position or stored form the domain refuses: nothing activates, reconcile first (fail closed)
    kind = outcome.kind
    if active.reconciliation_required and kind is not v.OutcomeKind.MISMATCH:
        kind = v.OutcomeKind.BLOCKED  # the domain's rule while flagged: recorded, never activated
    actual = _actual_json(outcome.actual)
    if kind is v.OutcomeKind.ACTIVATED:
        await conn.execute(_SUPERSEDE_ACTIVE, {"id": strategy_id})
        await conn.execute(_ACTIVATE, {"id": strategy_id, "n": pending.number, "outcome": kind.value,
                                       "actual": actual})
        return kind.value
    state = "proposed" if kind is v.OutcomeKind.PARTIAL else "superseded"
    await conn.execute(_RECORD_OUTCOME, {"id": strategy_id, "n": pending.number, "state": state,
                                         "outcome": kind.value, "actual": actual})
    if kind in (v.OutcomeKind.PARTIAL, v.OutcomeKind.MISMATCH) or record.reconciliation_required:
        await conn.execute(_FLAG_ACTIVE, {"id": strategy_id, "n": active.number})
    return kind.value


# ----------------------------------------------------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------------------------------------------------


async def load(conn: Any, user_ref: str, strategy_id: int) -> StoredStrategy:
    """The strategy with its ACTIVE definition: after the first execution that is the active version's (a proposed
    version is never returned as the definition), before it the strategy row's."""
    row = (await conn.execute(_SELECT, {"id": _check_id(strategy_id, "strategy"), "user_ref": user_ref})).one_or_none()
    if row is None:
        raise StrategyStoreError(NOT_FOUND, f"strategy {strategy_id}")
    versions = await _version_rows(conn, row.id)
    active = next((r for r in versions if r.state == "active"), None)
    current = row.definition_text if active is None else active.definition_text
    return dataclasses.replace(_stored(row, await _read(conn, current)), versions=versions)


async def version_saved(conn: Any, version: StoredVersion) -> sf.SavedDefinition:
    """One version's stored definition read back through the catalogue (refused like ``load`` when it no longer
    reads)."""
    return await _read(conn, version.definition_text)


async def list_strategies(conn: Any, user_ref: str) -> list[StrategySummary]:
    rows = (await conn.execute(_LIST, {"user_ref": user_ref})).all()
    return [StrategySummary(int(r.id), r.underlying, r.status, r.created_at, r.updated_at) for r in rows]


async def history(conn: Any, user_ref: str, strategy_id: int) -> list[sf.HistoryEntry]:
    row = (await conn.execute(_SELECT, {"id": _check_id(strategy_id, "strategy"), "user_ref": user_ref})).one_or_none()
    if row is None:
        raise StrategyStoreError(NOT_FOUND, f"strategy {strategy_id}")
    out = []
    for r in (await conn.execute(_HISTORY, {"id": row.id})).all():
        out.append(sf.HistoryEntry(int(r.seq), r.at, r.change_summary, await _read(conn, r.definition_text)))
    return out
