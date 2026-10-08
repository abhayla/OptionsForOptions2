"""PostgreSQL store for the contract catalogue and its broker rows (W-053, re-keyed by W-056).

Spec basis: REQ-053 AC-2 and Q244/Q257 (never deleted; truncated update refused; revisable terms follow the source
with history; identity never changes); REQ-054 AC-3/AC-4 and "Exchange segment vocabulary"; ADR-050. Schema:
migrations 0003_catalogue_store, 0004_broker_instruments and 0005_contract_lifecycle.

Identity over time (W-057, ADR-057, REQ-054 AC-3): every stored contract has an internal id (catalogue_contracts.id),
and every link (broker rows, history, and later strategy legs, orders, audit records) uses that id, never the raw
token. (exchange_segment, exchange_token) is unique among LIVE contracts only (a partial unique index, retired =
FALSE). A load on a date after a stored contract's expiry retires it (retired = TRUE, unlisted; its broker rows are
retired by the database guard); a later row with the same token is then a new contract with a new id. While a contract
is live, a changed expiry or strike under its token is a revision with history (ADR-057; the "strike never changes"
wording of REQ-053 Q257 is superseded for live contracts).
Delisting (W-057 round 2, ADR-058, REQ-054 AC-3): a live contract the list stops carrying while its expiry is still
ahead is marked delisted (kept, unlisted, delisted_on stamped by the database, a history row, broker rows freed), so its
token is free for reuse. Live = neither retired nor delisted. The truncated-download guard (Q244 as changed by ADR-058)
counts per index (underlying): the whole update is refused, nothing written, if MORE than ``max_delist_percent`` (an
admin setting, default 10) of that index's live contracts would disappear at once. ``force=True`` (reason + actor +
audit event) overrides the count; the contracts it drops are delisted too. Retired rows never change; nothing is ever deleted.

A live contract's identity is (exchange_segment, exchange_token) in public.catalogue_contracts. Zerodha's instrument_token,
trading symbol, segment code, lot size, tick size and freeze limit live only in public.broker_instruments (one row per
contract and broker). The domain `Contract` still carries lot/tick as its current terms: on load they are taken from
the contract's Zerodha row, and a stored contract with no Zerodha row stops the load (fail closed, AC-3).

Copy from (legacy-reuse.md M2): abhayla/algochanakya@bf9faf7:backend/app/services/instrument_master.py is REFERENCE
only (its refresh deletes and re-inserts; this store never deletes).

load_catalogue(conn) -> Catalogue: every stored contract (listed or not) with its broker rows. Fails closed
(CatalogueStoreError naming the row) on a strike or tick that is not a finite Decimal, a contract with no Zerodha row,
or a row outside the catalogue's scope.

apply_update(conn, rows, *, as_of, force=False, reason=None, actor=None, max_delist_percent=10):
1. ``pg_advisory_xact_lock(CATALOGUE_UPDATE_LOCK_KEY)`` serialises updates until the caller's transaction ends.
2. Loads the LIVE contracts; those whose expiry is before the load date are retired (ADR-057).
3. Validates every in-scope row BEFORE anything is written: strike and tick fit their columns exactly, every row has
   an expiry and one Zerodha broker row, no token or Zerodha token appears twice, a live Zerodha token never moves to
   another exchange identity, and a revision keeps its Zerodha identity (broker_token, broker_segment). Rows whose
   expiry has passed are skipped (ADR-059).
4. Calls the domain ``Catalogue.update``, which holds the rules: the ADR-058 per-index and ADR-059 per-expiry
   truncation guards (a refusal writes nothing), and the ADR-059 revision test - a row on a live token is a revision
   only if underlying, type and segment are unchanged and either the expiry moved <= 6 days with the strike unchanged,
   or the strike changed with the expiry unchanged; any other change is a token reuse, and both guards count it. A row about to be inserted that
   is identical to a delisted contract reinstates it (same internal id).
5. Writes inside a SAVEPOINT, in this order: delist (not carried, or token reused), retire, reinstate, insert new
   contracts and their broker rows, revise expiry/strike, see the broker rows (the database stamps seen_on and writes
   history only for a changed value), mark seen contracts listed; then checks no stored contract lacks its Zerodha
   row. Nothing is ever deleted.
6. ``force=True``: the domain's ADMIN_CHANGE_RECORDED event (naming every contract the update delists) is appended
   through ofo_app.audit_store on the SAME connection inside step 5's savepoint, after the writes.
Transaction control (commit) stays with the caller.

Known limit (accepted, W-053 fix round 2; widened by W-057): the truncation guards live in the domain; the application
role can still UPDATE currently_listed, retired or delisted with raw SQL, bypassing them (the database guard still
refuses retiring a live contract, any change to a retired one, and any return of a delisted one other than an
identical, unexpired reinstatement). The application role can also UPDATE a live contract's expiry and strike by any
amount with raw SQL: the database records each change as a revision with history, but does not apply the ADR-059
revision test (expiry moved <= 6 days, or strike alone) - only this store's path through the domain does.
"""

from __future__ import annotations

import csv
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TextIO

from sqlalchemy import text

from ofo.instruments.catalogue import (
    DEFAULT_MAX_DELIST_PERCENT,
    IST,
    Catalogue,
    CatalogueUpdateResult,
    check_max_delist_percent,
    is_revision,
)
from ofo.instruments.models import ZERODHA, BrokerRef, Contract, InstrumentId, ListedContract
from ofo.instruments.parser import ParsedInstruments, parse_instruments_rows, zerodha_segment
from ofo_app import audit_store

#: Fixed key for the update lock (any constant; only the catalogue store uses it).
CATALOGUE_UPDATE_LOCK_KEY = 5_300_053_001

#: Column scales (strike NUMERIC(12,2) in 0003; tick_size NUMERIC(10,4) on broker_instruments in 0004).
STRIKE_SCALE = Decimal("0.01")
STRIKE_LIMIT = Decimal(10) ** 10
TICK_SCALE = Decimal("0.0001")
TICK_LIMIT = Decimal(10) ** 6

CONTRACTS = "public.catalogue_contracts"
BROKER_ROWS = "public.broker_instruments"

_LOCK = text("SELECT pg_advisory_xact_lock(:k)")
_SELECT = text(
    f"SELECT c.id, c.exchange_segment, c.exchange_token, c.name, c.expiry, c.strike, c.instrument_type, "
    f"c.currently_listed, b.broker, b.broker_token, b.broker_symbol, b.broker_segment, b.lot_size, b.tick_size, "
    f"b.freeze_limit, b.seen_on "
    f"FROM {CONTRACTS} AS c LEFT JOIN {BROKER_ROWS} AS b ON b.contract_id = c.id WHERE NOT c.retired AND NOT c.delisted "
    f"ORDER BY c.id, b.broker"
)
_SELECT_ONE = text(
    f"SELECT c.id, c.exchange_segment, c.exchange_token, c.name, c.expiry, c.strike, c.instrument_type, "
    f"c.currently_listed, c.retired, c.delisted, c.delisted_on, b.broker, b.broker_token, b.broker_symbol, b.broker_segment, b.lot_size, "
    f"b.tick_size, b.freeze_limit, b.seen_on "
    f"FROM {CONTRACTS} AS c LEFT JOIN {BROKER_ROWS} AS b ON b.contract_id = c.id WHERE c.id = :id ORDER BY b.broker"
)
_LIVE_ID = text(
    f"SELECT id FROM {CONTRACTS} WHERE exchange_segment = :exchange_segment AND exchange_token = :exchange_token "
    f"AND NOT retired AND NOT delisted"
)
_RETIRE = text(
    f"UPDATE {CONTRACTS} SET retired = TRUE, currently_listed = FALSE "
    f"WHERE id = ANY(CAST(:ids AS BIGINT[])) AND NOT retired AND NOT delisted"
)
_REINSTATE = text(
    f"UPDATE {CONTRACTS} SET delisted = FALSE, currently_listed = TRUE "
    f"WHERE id = ANY(CAST(:ids AS BIGINT[])) AND delisted AND NOT retired"
)
_SELECT_DELISTED = text(
    f"SELECT d.id, d.exchange_segment, d.exchange_token, d.name, d.expiry, d.strike, d.instrument_type, "
    f"d.currently_listed, b.broker, b.broker_token, b.broker_symbol, b.broker_segment, b.lot_size, b.tick_size, "
    f"b.freeze_limit, b.seen_on "
    f"FROM {CONTRACTS} AS d LEFT JOIN {BROKER_ROWS} AS b ON b.contract_id = d.id "
    f"WHERE d.delisted AND NOT d.retired AND (d.exchange_segment, d.exchange_token) IN "
    f"(SELECT s, t FROM unnest(CAST(:segments AS TEXT[]), CAST(:tokens AS BIGINT[])) AS k(s, t)) "
    f"ORDER BY d.id, b.broker"
)
_DELIST = text(
    f"UPDATE {CONTRACTS} SET delisted = TRUE, currently_listed = FALSE "
    f"WHERE id = ANY(CAST(:ids AS BIGINT[])) AND NOT retired AND NOT delisted"
)
_INSERT = text(
    f"INSERT INTO {CONTRACTS} (exchange_segment, exchange_token, name, expiry, strike, instrument_type) "
    f"VALUES (:exchange_segment, :exchange_token, :name, :expiry, :strike, :instrument_type)"
)
_INSERT_BROKER = text(
    f"INSERT INTO {BROKER_ROWS} (contract_id, broker, broker_token, broker_symbol, broker_segment, lot_size, "
    f"tick_size, freeze_limit) "
    f"SELECT id, :broker, :broker_token, :broker_symbol, :broker_segment, :lot_size, :tick_size, :freeze_limit "
    f"FROM {CONTRACTS} WHERE exchange_segment = :exchange_segment AND exchange_token = :exchange_token "
    f"AND NOT retired AND NOT delisted"
)
_REVISE = text(
    f"UPDATE {CONTRACTS} SET expiry = :expiry, strike = :strike, currently_listed = TRUE "
    f"WHERE exchange_segment = :exchange_segment AND exchange_token = :exchange_token AND NOT retired AND NOT delisted"
)
_SEE_BROKER = text(
    f"UPDATE {BROKER_ROWS} SET broker_symbol = :broker_symbol, lot_size = :lot_size, tick_size = :tick_size, "
    f"freeze_limit = COALESCE(CAST(:freeze_limit AS INTEGER), freeze_limit) "
    f"WHERE broker = :broker AND contract_id = (SELECT id FROM {CONTRACTS} "
    f"WHERE exchange_segment = :exchange_segment AND exchange_token = :exchange_token AND NOT retired AND NOT delisted)"
)
_SET_LISTED = text(
    f"UPDATE {CONTRACTS} SET currently_listed = :listed "
    f"WHERE NOT retired AND NOT delisted AND (exchange_segment, exchange_token) IN "
    f"(SELECT s, t FROM unnest(CAST(:segments AS TEXT[]), CAST(:tokens AS BIGINT[])) AS k(s, t))"
)
_MISSING_BROKER_ROW = text(
    f"SELECT count(*) FROM {CONTRACTS} AS c WHERE NOT EXISTS "
    f"(SELECT 1 FROM {BROKER_ROWS} AS b WHERE b.contract_id = c.id AND b.broker = :broker)"
)

#: REQ-054 "Per-broker values and their date": a list without a value (Zerodha has no freeze limit) leaves the
#: stored value; the broker-row UPDATE keeps it with COALESCE and the revision check skips it.
#: Q257: these terms follow the list, each change recorded by the database; identity fields never change (OF006).
#: ADR-057: a live contract's expiry and strike are revisable (Zerodha's lot/tick/symbol on the broker row).
REVISABLE_FIELDS = ("expiry", "strike")
IDENTITY_FIELDS = ("exchange_segment", "exchange_token", "name", "instrument_type")
BROKER_REVISABLE_FIELDS = ("broker_symbol", "lot_size", "tick_size", "freeze_limit")
BROKER_IDENTITY_FIELDS = ("broker_token", "broker_segment")


class CatalogueStoreError(ValueError):
    """The store refused: a value it cannot store or reload exactly, or a contract whose identity would change."""


@dataclass(frozen=True)
class StoreUpdateResult:
    added: int
    seen: int  # stored contracts present in the list (including the revised ones)
    newly_unlisted: int
    revised: int  # stored contracts whose expiry, strike or Zerodha terms changed
    domain: CatalogueUpdateResult
    retired: int = 0  # live contracts retired by this load (expiry before the load date, ADR-057)
    delisted: int = 0  # live contracts the list no longer carries (ADR-058) or whose token it reuses (ADR-059)
    reinstated: int = 0  # delisted contracts back, identical, under their own internal id (ADR-059)


@dataclass(frozen=True)
class StoredContract:
    """One stored contract by its internal id (live or retired): what a strategy leg, order or audit record links to."""

    contract_id: int
    listed: ListedContract
    currently_listed: bool
    retired: bool
    delisted: bool
    delisted_on: date | None


def _listed(row: ListedContract | Contract) -> ListedContract:
    return row if isinstance(row, ListedContract) else ListedContract(contract=row)


def _label(row: ListedContract | Contract) -> str:
    row = _listed(row)
    for ref in row.broker_refs:
        if ref.broker == ZERODHA:
            return f"{ref.broker_symbol} (instrument_token {ref.broker_token})"
    return f"{row.contract.exchange_segment}:{row.contract.exchange_token}"


def _check_decimal(value: Any, field: str, scale: Decimal, limit: Decimal, where: str) -> None:
    if not isinstance(value, Decimal):
        raise CatalogueStoreError(f"{where}: {field} {value!r} is {type(value).__name__}, not Decimal (ADR-008)")
    if not value.is_finite():
        raise CatalogueStoreError(f"{where}: {field} {value} is not a finite Decimal")
    try:
        exact = value.quantize(scale) == value
    except InvalidOperation:
        exact = False
    if not exact or abs(value) >= limit:
        raise CatalogueStoreError(f"{where}: {field} {value} does not fit its column exactly (scale {scale})")


def _check_int(value: Any, field: str, where: str, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise CatalogueStoreError(f"{where}: {field} {value!r} is not an int")


def check_storable(row: ListedContract | Contract) -> None:
    """Refuse a contract or broker row the tables would store differently (rounded, NaN, float)."""
    row = _listed(row)
    contract = row.contract
    where = f"contract {_label(row)}"
    _check_decimal(contract.strike, "strike", STRIKE_SCALE, STRIKE_LIMIT, where)
    _check_decimal(contract.tick_size, "tick_size", TICK_SCALE, TICK_LIMIT, where)
    _check_int(contract.lot_size, "lot_size", where)
    if contract.expiry is not None and (not isinstance(contract.expiry, date) or isinstance(contract.expiry, datetime)):
        raise CatalogueStoreError(f"{where}: expiry {contract.expiry!r} is not a date")
    for ref in row.broker_refs:
        # The database allows a zero lot or tick only under Zerodha's INDICES segment (it cannot see the contract's own
        # segment from the broker table); the contract's segment is checked here.
        if (ref.lot_size == 0 or ref.tick_size == 0) and not contract.is_index():
            raise CatalogueStoreError(f"{where}: a zero lot or tick size is allowed only on an index contract")
        _check_decimal(ref.tick_size, f"{ref.broker} tick_size", TICK_SCALE, TICK_LIMIT, where)
        _check_int(ref.lot_size, f"{ref.broker} lot_size", where)
        _check_int(ref.freeze_limit, f"{ref.broker} freeze_limit", where, optional=True)


def parse_rows_naming_the_row(stream: TextIO) -> ParsedInstruments:
    """Parse a Zerodha instrument CSV like ``ofo.instruments.parser``; rows outside V1 are skipped and counted, and a V1
    row that cannot be parsed stops the load with an error naming its line and symbol."""
    rows: list[ListedContract] = []
    skipped = 0
    reader = csv.DictReader(stream)
    for row in reader:
        if zerodha_segment(row.get("exchange") or "") is None and "exchange" in row:
            skipped += 1
            continue
        try:
            rows.extend(parse_instruments_rows([row]))
        except ValueError as exc:
            symbol = (row.get("tradingsymbol") or "").strip() or "?"
            token = (row.get("instrument_token") or "").strip() or "?"
            raise CatalogueStoreError(f"line {reader.line_num}: {symbol} (instrument_token {token}): {exc}") from None
    return ParsedInstruments(rows, skipped_outside_v1=skipped)


def _stored_row(rows: list[Any]) -> tuple[ListedContract, bool]:
    """One contract's joined rows (one per broker row) -> the listed contract and its listedness."""
    head = rows[0]
    refs = []
    for r in rows:
        if r.broker is None:
            continue
        refs.append(BrokerRef(broker=r.broker, broker_token=r.broker_token, broker_symbol=r.broker_symbol,
                              broker_segment=r.broker_segment, lot_size=int(r.lot_size), tick_size=r.tick_size,
                              seen_on=r.seen_on,
                              freeze_limit=None if r.freeze_limit is None else int(r.freeze_limit)))
    zerodha = [ref for ref in refs if ref.broker == ZERODHA]
    where = f"stored row id={head.id} {head.exchange_segment}:{head.exchange_token}"
    if zerodha:
        where += f" {zerodha[0].broker_symbol} (instrument_token {zerodha[0].broker_token})"
    _check_decimal(head.strike, "strike", STRIKE_SCALE, STRIKE_LIMIT, where)
    if not zerodha:
        raise CatalogueStoreError(f"{where}: has no {ZERODHA} row; it cannot be traded and has no lot size (REQ-054 AC-3)")
    ref = zerodha[0]
    _check_decimal(ref.tick_size, "tick_size", TICK_SCALE, TICK_LIMIT, where)
    contract = Contract(exchange_segment=head.exchange_segment, exchange_token=int(head.exchange_token), name=head.name,
                        expiry=head.expiry, strike=head.strike, tick_size=ref.tick_size, lot_size=ref.lot_size,
                        instrument_type=head.instrument_type)
    return ListedContract(contract=contract, broker_refs=tuple(refs)), bool(head.currently_listed)


async def _load_live(conn: Any) -> list[tuple[int, ListedContract, bool]]:
    """Every LIVE (not retired) stored contract: (internal id, listed contract, stored listedness)."""
    grouped: dict[int, list[Any]] = {}
    for row in (await conn.execute(_SELECT)).all():
        grouped.setdefault(row.id, []).append(row)
    out = []
    for contract_id, rows in grouped.items():
        listed, is_listed = _stored_row(rows)
        out.append((contract_id, listed, is_listed))
    return out


def _catalogue_of(live: list[tuple[int, ListedContract, bool]]) -> Catalogue:
    listed_rows = [listed for _, listed, _ in live]
    unlisted = {listed.id for _, listed, is_listed in live if not is_listed}
    catalogue = Catalogue()
    try:
        loaded = catalogue.load(listed_rows)
    except ValueError as exc:
        raise CatalogueStoreError(f"stored rows: {exc}") from None
    if loaded != len(listed_rows):
        in_scope = {e.id for e in catalogue.all_entries()}
        stray = next(r for r in listed_rows if r.id not in in_scope)
        raise CatalogueStoreError(f"stored row {_label(stray)} is outside the catalogue's scope")
    for entry in catalogue.all_entries():
        if entry.id in unlisted:
            entry.currently_listed = False
    return catalogue


async def load_catalogue(conn: Any) -> Catalogue:
    """Every LIVE stored contract as a domain Catalogue, each with its broker rows and stored listedness. Retired
    contracts are read by their internal id with ``load_contract``."""
    return _catalogue_of(await _load_live(conn))


def _check_contract_id(contract_id: Any) -> int:
    if isinstance(contract_id, bool) or not isinstance(contract_id, int) or contract_id <= 0:
        raise CatalogueStoreError(f"a contract is linked by its positive integer internal id, got {contract_id!r}")
    return contract_id


async def load_contract(conn: Any, contract_id: int) -> StoredContract:
    """The stored contract with this internal id, live or retired (ADR-057: a link keeps pointing at its contract
    after the token is reused). Fails closed when no contract has the id."""
    rows = (await conn.execute(_SELECT_ONE, {"id": _check_contract_id(contract_id)})).all()
    if not rows:
        raise CatalogueStoreError(f"no stored contract has internal id {contract_id}")
    listed, is_listed = _stored_row(rows)
    return StoredContract(contract_id=contract_id, listed=listed, currently_listed=is_listed,
                          retired=bool(rows[0].retired), delisted=bool(rows[0].delisted),
                          delisted_on=rows[0].delisted_on)


async def live_contract_id(conn: Any, instrument_id: InstrumentId) -> int | None:
    """The internal id of the LIVE contract holding this exchange identity today, or None (never a retired one)."""
    if not isinstance(instrument_id, InstrumentId):
        raise TypeError(f"a live contract is found by its InstrumentId, got {instrument_id!r}")
    rows = (await conn.execute(_LIVE_ID, {"exchange_segment": instrument_id.exchange_segment,
                                          "exchange_token": instrument_id.exchange_token})).all()
    if len(rows) > 1:  # the partial unique index forbids this; fail closed if it was ever dropped
        raise CatalogueStoreError(f"{len(rows)} live contracts share {instrument_id}; refusing to pick one")
    return int(rows[0].id) if rows else None


def _contract_params(row: ListedContract) -> dict[str, Any]:
    c = row.contract
    return {"exchange_segment": c.exchange_segment, "exchange_token": c.exchange_token, "name": c.name,
            "expiry": c.expiry, "strike": c.strike, "instrument_type": c.instrument_type}


def _broker_params(row: ListedContract, ref: BrokerRef) -> dict[str, Any]:
    return {"exchange_segment": row.contract.exchange_segment, "exchange_token": row.contract.exchange_token,
            "broker": ref.broker, "broker_token": ref.broker_token, "broker_symbol": ref.broker_symbol,
            "broker_segment": ref.broker_segment, "lot_size": ref.lot_size, "tick_size": ref.tick_size,
            "freeze_limit": ref.freeze_limit}


def _see_params(row: ListedContract, ref: BrokerRef) -> dict[str, Any]:
    p = _broker_params(row, ref)
    return {k: p[k] for k in ("exchange_segment", "exchange_token", "broker", "broker_symbol", "lot_size", "tick_size",
                              "freeze_limit")}


class _BufferedAuditLog:
    """Collects the domain's forced-update audit event(s); apply_update writes them through the W-052 store only after
    the catalogue write succeeded."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append(self, event_type: Any, *, actor: str, timestamp: datetime, correlation_id: str,
               payload: Any = None) -> None:
        self.events.append({"event_type": event_type, "actor": actor, "timestamp": timestamp,
                            "correlation_id": correlation_id, "payload": payload})


def _keys(ids: Iterable[InstrumentId]) -> dict[str, list]:
    pairs = sorted(ids)
    return {"segments": [i.exchange_segment for i in pairs], "tokens": [i.exchange_token for i in pairs]}


def _check_percent(value: Any) -> Decimal:
    try:
        return check_max_delist_percent(value)
    except ValueError as exc:
        raise CatalogueStoreError(str(exc)) from None


def _refuse_identity_change(label: str, what: str, fields: tuple[str, ...], old: Any, new: Any) -> None:
    for field in fields:
        if getattr(old, field) != getattr(new, field):
            raise CatalogueStoreError(
                f"contract {label}: {what}{field} {getattr(old, field)!r} -> {getattr(new, field)!r}"
                f" - a live contract's identity never changes and two live contracts never share a token"
                f" (REQ-054 AC-3, ADR-057); nothing written"
            )


def _same_contract(stored: ListedContract, row: ListedContract) -> bool:
    """ADR-059 reinstatement: the same token, underlying, type, strike and expiry (and the same Zerodha token)."""
    fields = ("exchange_segment", "exchange_token", "name", "instrument_type", "strike", "expiry")
    if any(getattr(stored.contract, f) != getattr(row.contract, f) for f in fields):
        return False
    old, new = stored.ref(ZERODHA), row.ref(ZERODHA)
    return (old.broker_token, old.broker_segment) == (new.broker_token, new.broker_segment)


async def _reinstatable(conn: Any, rows: list[ListedContract]) -> dict[InstrumentId, int]:
    """For each row to be inserted, the one delisted (not retired) contract identical to it, if any (ADR-059). Two
    identical delisted candidates for one row refuse the list (fail closed: never guess which one returns)."""
    if not rows:
        return {}
    grouped: dict[int, list[Any]] = {}
    for found in (await conn.execute(_SELECT_DELISTED, _keys(r.id for r in rows))).all():
        grouped.setdefault(found.id, []).append(found)
    candidates: dict[InstrumentId, list[tuple[int, ListedContract]]] = {}
    for contract_id, found in grouped.items():
        listed, _ = _stored_row(found)
        candidates.setdefault(listed.id, []).append((contract_id, listed))
    out: dict[InstrumentId, int] = {}
    for row in rows:
        matches = [cid for cid, listed in candidates.get(row.id, []) if _same_contract(listed, row)]
        if len(matches) > 1:
            raise CatalogueStoreError(f"{len(matches)} delisted contracts (ids {sorted(matches)}) are identical to "
                                      f"{_label(row)}; cannot tell which one returns; nothing written")
        if matches:
            out[row.id] = matches[0]
    return out


async def apply_update(
    conn: Any,
    contracts: Iterable[ListedContract | Contract],
    *,
    as_of: datetime,
    force: bool = False,
    reason: str | None = None,
    actor: str | None = None,
    max_delist_percent: Any = DEFAULT_MAX_DELIST_PERCENT,
) -> StoreUpdateResult:
    """Apply a newer instrument list to the stored catalogue (see the module docstring). Refusals raise before any
    write: ValueError from the domain (the ADR-058/059 truncation guards; force without reason/actor),
    CatalogueStoreError here."""
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("apply_update() requires a timezone-aware as_of (the retirement date, ADR-057)")
    update_date = as_of.astimezone(IST).date()
    limit = _check_percent(max_delist_percent)
    rows = [_listed(r) for r in contracts]
    await conn.execute(_LOCK, {"k": CATALOGUE_UPDATE_LOCK_KEY})
    live = await _load_live(conn)
    for contract_id, listed, _ in live:
        if listed.contract.expiry is None and not listed.contract.is_index():  # an index never expires (REQ-072 AC-1)
            raise CatalogueStoreError(f"stored contract id={contract_id} {_label(listed)} has no expiry; cannot tell "
                                      "when its token retires (ADR-057); nothing written")
    # ADR-057: a live contract whose expiry is before the load date is retired; its token is free from now on.
    retiring = [(cid, listed, is_listed) for cid, listed, is_listed in live if listed.contract.expiry is not None
                and listed.contract.expiry < update_date]
    kept = [item for item in live
            if item[1].contract.expiry is None or item[1].contract.expiry >= update_date]
    contract_ids = {listed.id: cid for cid, listed, _ in kept}
    catalogue = _catalogue_of(kept)
    before = {e.id: e for e in catalogue.all_entries()}
    was_listed = {i: e.currently_listed for i, e in before.items()}  # the domain update mutates the entries
    # A Zerodha token held by an unexpired live contract never moves to another exchange identity in one list.
    stored_by_token = {(ref.broker_segment, ref.broker_token): listed
                       for _, listed, _ in kept for ref in listed.broker_refs if ref.broker == ZERODHA}

    scoped: dict[InstrumentId, ListedContract] = {}
    zerodha_tokens: dict[tuple[str, str], InstrumentId] = {}
    for row in rows:
        if not Catalogue._in_scope(row.contract):
            continue
        check_storable(row)
        label = _label(row)
        if row.contract.expiry is None and not row.contract.is_index():
            raise CatalogueStoreError(f"contract {label}: has no expiry; cannot tell when its token retires "
                                      "(ADR-057); the list is refused, nothing written")
        if row.contract.expiry is not None and row.contract.expiry < update_date:  # ADR-059: a stale row is skipped, never loaded (the domain skips too)
            continue
        refs = {r.broker: r for r in row.broker_refs}
        if ZERODHA not in refs or len(refs) != len(row.broker_refs):
            raise CatalogueStoreError(f"contract {label}: needs exactly one {ZERODHA} row (REQ-054 AC-3)")
        if row.id in scoped:  # even an identical repeat: one token, one row per list (ADR-057)
            raise CatalogueStoreError(f"the list holds token {row.id.exchange_segment}:{row.id.exchange_token} "
                                      f"twice ({_label(scoped[row.id])} and {label}); the list is refused, "
                                      "nothing written")
        token_key = (refs[ZERODHA].broker_segment, refs[ZERODHA].broker_token)
        if token_key in zerodha_tokens:
            raise CatalogueStoreError(f"the list gives {ZERODHA} token {token_key[1]} to {zerodha_tokens[token_key]} "
                                      f"and {row.id}")
        zerodha_tokens[token_key] = row.id
        scoped[row.id] = row
        owner = stored_by_token.get(token_key)
        if owner is not None and owner.id != row.id:  # the live Zerodha row would point at another identity
            _refuse_identity_change(label, "", IDENTITY_FIELDS, owner.contract, row.contract)
        stored = before.get(row.id)
        if stored is not None and is_revision(stored.contract, row.contract):  # a revision keeps the Zerodha row
            _refuse_identity_change(label, f"{ZERODHA} ", BROKER_IDENTITY_FIELDS, stored.broker_refs[ZERODHA],
                                    refs[ZERODHA])

    audit = _BufferedAuditLog() if force else None
    # The domain holds the rules (ADR-058 index guard, ADR-059 half-expiry guard, revision test, stale rows).
    domain = catalogue.update(rows, as_of=as_of, force=force, reason=reason, actor=actor, audit_log=audit,
                              max_delist_percent=limit)
    replaced = set(domain.replaced)
    vanishing = set(domain.delisted)
    if (replaced != {i for i in scoped if i in before and not is_revision(before[i].contract, scoped[i].contract)}
            or not vanishing <= set(before) or vanishing & set(scoped)):
        raise CatalogueStoreError("domain catalogue state does not match the planned write; nothing written")
    present = [scoped[i] for i in sorted(scoped) if i in before and i not in replaced]
    arriving = [scoped[i] for i in sorted(scoped) if i not in before or i in replaced]
    reinstate = await _reinstatable(conn, arriving)
    new = [r for r in arriving if r.id not in reinstate]
    returning = [r for r in arriving if r.id in reinstate]
    revised = [r for r in present
               if any(getattr(before[r.id].contract, f) != getattr(r.contract, f) for f in REVISABLE_FIELDS)
               or any(getattr(before[r.id].broker_refs[ZERODHA], f) != getattr(r.ref(ZERODHA), f)
                      for f in BROKER_REVISABLE_FIELDS if getattr(r.ref(ZERODHA), f) is not None)]
    terms_revised = [r for r in present
                     if any(getattr(before[r.id].contract, f) != getattr(r.contract, f) for f in REVISABLE_FIELDS)]
    retire_ids = sorted(cid for cid, _, _ in retiring)
    delist_ids = sorted(contract_ids[i] for i in vanishing | replaced)
    seen = present + returning

    async with conn.begin_nested():
        if delist_ids:  # first: frees each token that leaves the market (or is reused) before a contract takes it
            await conn.execute(_DELIST, {"ids": delist_ids})
        if retire_ids:
            await conn.execute(_RETIRE, {"ids": retire_ids})
        if reinstate:  # ADR-059: the same contract (same internal id) returns
            await conn.execute(_REINSTATE, {"ids": sorted(reinstate.values())})
        if new:
            await conn.execute(_INSERT, [_contract_params(r) for r in new])
            await conn.execute(_INSERT_BROKER, [_broker_params(r, ref) for r in new for ref in r.broker_refs])
        if terms_revised:
            await conn.execute(_REVISE, [{"exchange_segment": r.contract.exchange_segment,
                                          "exchange_token": r.contract.exchange_token,
                                          "expiry": r.contract.expiry, "strike": r.contract.strike}
                                         for r in terms_revised])
        if seen:
            await conn.execute(_SEE_BROKER, [_see_params(r, ref) for r in seen for ref in r.broker_refs])
            await conn.execute(_SET_LISTED, {"listed": True, **_keys(r.id for r in seen)})
        missing = (await conn.execute(_MISSING_BROKER_ROW, {"broker": ZERODHA})).scalar_one()
        if missing:
            raise CatalogueStoreError(f"{missing} stored contract(s) have no {ZERODHA} row after the write; "
                                      "nothing written (REQ-054 AC-3)")
        # Inside the savepoint, after the writes: a refused audit append rolls back the catalogue change too.
        for event in audit.events if audit is not None else ():
            await audit_store.append(conn, event.pop("event_type"), **event)
    leaving_listed = sum(1 for i in vanishing | replaced if was_listed[i])
    newly_unlisted = sum(1 for _, _, was_listed in retiring if was_listed) + leaving_listed
    return StoreUpdateResult(added=len(new), seen=len(present), newly_unlisted=newly_unlisted,
                             revised=len(revised), domain=domain, retired=len(retire_ids), delisted=len(delist_ids),
                             reinstated=len(reinstate))


def with_terms(row: ListedContract, **changes: Any) -> ListedContract:
    """A copy of a listed contract with contract and/or Zerodha-row fields changed (lot_size and tick_size change both,
    as the parser sets them). Used by tests and repair tools; never by apply_update."""
    contract_fields = {f.name for f in dataclasses.fields(Contract)}
    ref_fields = {f.name for f in dataclasses.fields(BrokerRef)}
    c_changes = {k: v for k, v in changes.items() if k in contract_fields}
    r_changes = {k: v for k, v in changes.items() if k in ref_fields}
    unknown = set(changes) - contract_fields - ref_fields
    if unknown:
        raise TypeError(f"unknown field(s): {sorted(unknown)}")
    refs = tuple(dataclasses.replace(r, **r_changes) if r.broker == ZERODHA else r for r in row.broker_refs)
    return ListedContract(contract=dataclasses.replace(row.contract, **c_changes), broker_refs=refs)
