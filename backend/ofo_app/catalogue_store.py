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

apply_update(conn, rows, *, as_of, force=False, reason=None, actor=None):
1. ``pg_advisory_xact_lock(CATALOGUE_UPDATE_LOCK_KEY)`` serialises updates until the caller's transaction ends.
2. Validates every in-scope row BEFORE anything is written: strike and tick fit their columns exactly, every row has a
   Zerodha broker row, no two rows share a Zerodha token, and a contract already stored keeps its identity (name,
   instrument_type, strike) and its Zerodha row keeps its identity (broker_token, broker_segment) - refused here and by
   the database (OF006). Revisable terms follow the list (Q257): the contract's expiry, and the Zerodha row's
   broker_symbol, lot_size, tick_size and freeze_limit; the database triggers record each change in
   public.catalogue_term_changes (broker NULL for expiry, the broker otherwise) with a database-stamped time.
3. Loads the stored catalogue and calls the domain ``Catalogue.update`` (Q244). A refusal writes nothing.
4. Writes inside a SAVEPOINT: INSERT new contracts, INSERT their broker rows (contract found by its identity), UPDATE
   revised expiries, UPDATE every present stored contract's broker row (the database stamps seen_on/last_seen_at and
   writes history only for a changed value), mark present contracts listed and departed ones unlisted, then checks no
   stored contract lacks its Zerodha row. Nothing is ever deleted.
5. ``force=True``: the domain's ADMIN_CHANGE_RECORDED event is appended through ofo_app.audit_store on the SAME
   connection inside step 4's savepoint, after the writes.
Transaction control (commit) stays with the caller.

Known limit (accepted, W-053 fix round 2): Q244 lives in the domain; the application role can still UPDATE
currently_listed with raw SQL, bypassing it.
"""

from __future__ import annotations

import csv
import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TextIO

from sqlalchemy import text

from ofo.instruments.catalogue import IST, Catalogue, CatalogueUpdateResult
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


#: ADR-058: refuse an update that would drop MORE than this percentage of an index's live contracts at once. The admin
#: setting is ofo_app.config.Settings.CATALOGUE_MAX_DELIST_PERCENT; a test asserts the two defaults are equal.
DEFAULT_MAX_DELIST_PERCENT = Decimal("10")


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
    delisted: int = 0  # live, unexpired contracts the list no longer carries (ADR-058)


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
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or not Decimal(value).is_finite() \
            or not Decimal(0) <= Decimal(value) <= Decimal(100):
        raise CatalogueStoreError(f"max_delist_percent must be an int or Decimal from 0 to 100, got {value!r}")
    return Decimal(value)


def _refuse_truncated(kept: list[tuple[int, ListedContract, bool]], vanishing: list[tuple[int, ListedContract, bool]],
                      limit: Decimal) -> None:
    """ADR-058: per index (underlying), refuse when MORE than `limit` percent of its live contracts would disappear."""
    live: dict[str, int] = {}
    gone: dict[str, int] = {}
    for _, listed, _ in kept:
        live[listed.contract.name] = live.get(listed.contract.name, 0) + 1
    for _, listed, _ in vanishing:
        gone[listed.contract.name] = gone.get(listed.contract.name, 0) + 1
    for name in sorted(gone):
        if gone[name] * 100 > limit * live[name]:
            share = (Decimal(gone[name] * 100) / live[name]).quantize(Decimal("0.1"))
            raise CatalogueStoreError(
                f"Catalogue update refused: would drop {gone[name]} of {live[name]} live {name} contracts ({share}%), "
                f"more than {limit}% at once - the source list may be truncated (ADR-058); nothing written; override "
                f"needs force=True with a reason, actor and audit_log")


def _refuse_identity_change(label: str, what: str, fields: tuple[str, ...], old: Any, new: Any) -> None:
    for field in fields:
        if getattr(old, field) != getattr(new, field):
            raise CatalogueStoreError(
                f"contract {label}: {what}{field} {getattr(old, field)!r} -> {getattr(new, field)!r}"
                f" - a live contract's identity never changes and two live contracts never share a token"
                f" (REQ-054 AC-3, ADR-057); nothing written"
            )


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
    write: ValueError from the domain (Q244; force without reason/actor), CatalogueStoreError here."""
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("apply_update() requires a timezone-aware as_of (the retirement date, ADR-057)")
    update_date = as_of.astimezone(IST).date()
    limit = _check_percent(max_delist_percent)
    rows = [_listed(r) for r in contracts]
    await conn.execute(_LOCK, {"k": CATALOGUE_UPDATE_LOCK_KEY})
    live = await _load_live(conn)
    for contract_id, listed, _ in live:
        if listed.contract.expiry is None:
            raise CatalogueStoreError(f"stored contract id={contract_id} {_label(listed)} has no expiry; cannot tell "
                                      "when its token retires (ADR-057); nothing written")
    # ADR-057: a live contract whose expiry is before the load date is retired; its token is free from now on.
    retiring = [(cid, listed, is_listed) for cid, listed, is_listed in live if listed.contract.expiry < update_date]
    kept = [item for item in live if item[1].contract.expiry >= update_date]
    in_list = {r.id for r in rows if Catalogue._in_scope(r.contract)}
    vanishing = [item for item in kept if item[1].id not in in_list]  # live, unexpired, not carried: delisted
    if not force:
        _refuse_truncated(kept, vanishing, limit)
    vanishing_ids = {item[1].id for item in vanishing}
    # Without force the delisted contracts leave the domain catalogue first (the count above is the guard); with force
    # the domain sees them dropped and records them in its audit event.
    catalogue = _catalogue_of(kept if force else [item for item in kept if item[1].id not in vanishing_ids])
    before = {e.id: e for e in catalogue.all_entries()}
    # Every unexpired live contract, including those about to be delisted: a Zerodha token held by one of them never
    # moves to another exchange identity inside one list (fail closed).
    stored_by_token = {(ref.broker_segment, ref.broker_token): listed
                       for _, listed, _ in kept for ref in listed.broker_refs if ref.broker == ZERODHA}

    scoped: dict[InstrumentId, ListedContract] = {}
    zerodha_tokens: dict[tuple[str, str], InstrumentId] = {}
    revised: list[ListedContract] = []
    for row in rows:
        if not Catalogue._in_scope(row.contract):
            continue
        check_storable(row)
        label = _label(row)
        if row.contract.expiry is None:
            raise CatalogueStoreError(f"contract {label}: has no expiry; cannot tell when its token retires "
                                      "(ADR-057); the list is refused, nothing written")
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
        stored = before.get(row.id)
        if stored is None:
            owner = stored_by_token.get(token_key)
            if owner is not None:  # the live Zerodha row now points at another identity: an identity change
                _refuse_identity_change(label, "", IDENTITY_FIELDS, owner.contract, row.contract)
            continue
        _refuse_identity_change(label, "", IDENTITY_FIELDS, stored.contract, row.contract)
        old_ref = stored.broker_refs[ZERODHA]
        _refuse_identity_change(label, f"{ZERODHA} ", BROKER_IDENTITY_FIELDS, old_ref, refs[ZERODHA])
        if (any(getattr(stored.contract, f) != getattr(row.contract, f) for f in REVISABLE_FIELDS)
                or any(getattr(old_ref, f) != getattr(refs[ZERODHA], f) for f in BROKER_REVISABLE_FIELDS
                       if getattr(refs[ZERODHA], f) is not None)):  # a value the list does not carry is kept
            revised.append(row)

    audit = _BufferedAuditLog() if force else None
    domain = catalogue.update(rows, as_of=as_of, force=force, reason=reason, actor=actor, audit_log=audit)

    after = {e.id: e.currently_listed for e in catalogue.all_entries()}
    new = [scoped[i] for i in sorted(scoped) if i not in before]
    present = [scoped[i] for i in sorted(scoped) if i in before]
    terms_revised = [r for r in present
                     if any(getattr(before[r.id].contract, f) != getattr(r.contract, f) for f in REVISABLE_FIELDS)]
    unlisted = {i for i, listed in after.items() if not listed}
    if (set(after) != set(before) | {r.id for r in new} or any(not after[i] for i in scoped)
            or not unlisted <= vanishing_ids):
        raise CatalogueStoreError("domain catalogue state does not match the planned write; nothing written")
    retire_ids = sorted(cid for cid, _, _ in retiring)
    delist_ids = sorted(cid for cid, _, _ in vanishing)

    async with conn.begin_nested():
        if delist_ids:  # first: frees each token that leaves the market before a new contract takes it
            await conn.execute(_DELIST, {"ids": delist_ids})
        if retire_ids:
            await conn.execute(_RETIRE, {"ids": retire_ids})
        if new:
            await conn.execute(_INSERT, [_contract_params(r) for r in new])
            await conn.execute(_INSERT_BROKER, [_broker_params(r, ref) for r in new for ref in r.broker_refs])
        if terms_revised:
            await conn.execute(_REVISE, [{"exchange_segment": r.contract.exchange_segment,
                                          "exchange_token": r.contract.exchange_token,
                                          "expiry": r.contract.expiry, "strike": r.contract.strike}
                                         for r in terms_revised])
        if present:
            await conn.execute(_SEE_BROKER, [_see_params(r, ref) for r in present for ref in r.broker_refs])
            await conn.execute(_SET_LISTED, {"listed": True, **_keys(r.id for r in present)})
        missing = (await conn.execute(_MISSING_BROKER_ROW, {"broker": ZERODHA})).scalar_one()
        if missing:
            raise CatalogueStoreError(f"{missing} stored contract(s) have no {ZERODHA} row after the write; "
                                      "nothing written (REQ-054 AC-3)")
        # Inside the savepoint, after the writes: a refused audit append rolls back the catalogue change too.
        for event in audit.events if audit is not None else ():
            await audit_store.append(conn, event.pop("event_type"), **event)
    newly_unlisted = sum(1 for _, _, was_listed in retiring + vanishing if was_listed)
    return StoreUpdateResult(added=len(new), seen=len(present), newly_unlisted=newly_unlisted,
                             revised=len(revised), domain=domain, retired=len(retire_ids), delisted=len(delist_ids))


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
