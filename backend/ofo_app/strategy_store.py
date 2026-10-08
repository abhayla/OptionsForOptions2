"""PostgreSQL store for strategy drafts and their pre-execution activity history (W-061).

Spec basis: REQ-038 AC-5 ("A strategy's definition and its activity history are saved in the database when the user
presses Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the
strategy."); REQ-038 AC-2 (activity-history entries with restore before the first execution); ADR-016 (no silent
contract substitution); REQ-054 AC-3 / ADR-057 (legs link the catalogue's internal contract id). Schema: migration
0007_strategy_store. The stored form is ofo.strategy.stored_form.

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


@dataclass(frozen=True)
class StrategySummary:
    id: int
    underlying: str
    status: str
    created_at: datetime
    updated_at: datetime


_COLUMNS = "id, user_ref, status, created_at, updated_at, definition::text AS definition_text"
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
    "VALUES (:id, :summary, CAST(:definition AS JSONB), :version) RETURNING seq")
_UPDATE = text(f"UPDATE public.strategies SET definition = CAST(:definition AS JSONB) WHERE id = :id "
               f"RETURNING {_COLUMNS}")
_HISTORY = text("SELECT seq, at, change_summary, definition::text AS definition_text FROM public.strategy_history "
                "WHERE strategy_id = :id ORDER BY seq")
_HISTORY_ONE = text("SELECT definition::text AS definition_text FROM public.strategy_history "
                    "WHERE strategy_id = :id AND seq = :seq")
_EXISTING_IDS = text("SELECT id FROM public.catalogue_contracts WHERE id = ANY(CAST(:ids AS BIGINT[]))")


def _check_id(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StrategyStoreError(NOT_FOUND, f"{what} {value!r}")
    return value


# ----------------------------------------------------------------------------------------------------------------
# The catalogue link
# ----------------------------------------------------------------------------------------------------------------


async def catalogue_resolver(conn: Any, contract_ids: Iterable[int]) -> sf.Resolver:
    """Reads every named contract id from the catalogue once; the resolver answers None for an id it does not hold."""
    wanted = sorted({c for c in contract_ids if isinstance(c, int) and not isinstance(c, bool) and c > 0})
    existing = {int(r[0]) for r in (await conn.execute(_EXISTING_IDS, {"ids": wanted})).all()} if wanted else set()
    terms: dict[int, sf.CatalogueTerms] = {}
    for contract_id in sorted(existing):
        stored = await load_contract(conn, contract_id)
        contract = stored.listed.contract
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
                          updated_at=row.updated_at, saved=saved)


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


async def _summary(conn: Any, current_text: str, new: sf.SavedDefinition) -> str:
    try:
        old = await _read(conn, current_text)
    except sf.StoredFormError as exc:  # the replaced text no longer reads (e.g. a contract's terms changed)
        return f"definition replaced (the previous one could not be compared: {exc.code})"
    return sf.change_summary(old, new)


async def update(conn: Any, user_ref: str, strategy_id: int, saved: sf.SavedDefinition) -> StoredStrategy:
    """A new definition for a draft: history entry of the previous definition first, then the new one, all or
    nothing. The caller commits."""
    document = await _check_saveable(conn, saved)
    async with conn.begin_nested():
        row = await _locked(conn, user_ref, strategy_id)
        if row.underlying != saved.definition.underlying:
            raise StrategyStoreError(UNDERLYING_FIXED, f"strategy {strategy_id} is on {row.underlying}; a strategy on "
                                                       f"{saved.definition.underlying} is a new strategy")
        if sf.parse_json(row.definition_text) == sf.parse_json(document):
            return _stored(row, saved)
        summary = await _summary(conn, row.definition_text, saved)
        await _write_history(conn, row.id, summary, row.definition_text)
        written = await _write_definition(conn, row.id, document)
    return _stored(written, saved)


async def restore(conn: Any, user_ref: str, strategy_id: int, seq: int) -> StoredStrategy:
    """Makes history entry ``seq`` current; the replaced definition is written as a new entry first (nothing is
    deleted). The entry's contracts must still be live with the same terms. The caller commits."""
    async with conn.begin_nested():
        row = await _locked(conn, user_ref, strategy_id)
        if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
            raise StrategyStoreError(HISTORY_NOT_FOUND, f"history entry {seq!r}")
        entry_text = (await conn.execute(_HISTORY_ONE, {"id": row.id, "seq": seq})).scalar_one_or_none()
        if entry_text is None:
            raise StrategyStoreError(HISTORY_NOT_FOUND, f"strategy {strategy_id} has no history entry {seq}")
        saved = await _read(conn, entry_text)
        resolve = await catalogue_resolver(conn, saved.contract_ids)
        sf.check_against_catalogue(saved, resolve, require_live=True)
        if sf.parse_json(row.definition_text) == sf.parse_json(entry_text):
            return _stored(row, saved)
        await _write_history(conn, row.id, f"restored entry {seq}", row.definition_text)
        written = await _write_definition(conn, row.id, entry_text)
    return _stored(written, saved)


# ----------------------------------------------------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------------------------------------------------


async def load(conn: Any, user_ref: str, strategy_id: int) -> StoredStrategy:
    row = (await conn.execute(_SELECT, {"id": _check_id(strategy_id, "strategy"), "user_ref": user_ref})).one_or_none()
    if row is None:
        raise StrategyStoreError(NOT_FOUND, f"strategy {strategy_id}")
    return _stored(row, await _read(conn, row.definition_text))


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
