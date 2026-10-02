"""PostgreSQL store for the contract catalogue (W-053; REQ-053 AC-2, owner decision Q244).

Copy from (legacy-reuse.md M2): abhayla/algochanakya@bf9faf7:backend/app/services/instrument_master.py is REFERENCE
only (its refresh deletes and re-inserts; this store never deletes). The catalogue rules live in
``ofo.instruments.catalogue.Catalogue``; this module only stores and reloads its state.

load_catalogue(conn) -> Catalogue: every stored contract, listed or not. Fails closed (CatalogueStoreError naming the
row) on a strike or tick that is not a finite Decimal, a duplicate instrument_token, or a row outside the catalogue's
scope.

apply_update(conn, contracts, *, as_of, force=False, reason=None, actor=None, audit_log=None):
1. ``pg_advisory_xact_lock(CATALOGUE_UPDATE_LOCK_KEY)`` serialises updates until the caller's transaction ends.
2. Validates every in-scope contract BEFORE anything is written: strike and tick are finite Decimals that fit their
   columns exactly (NUMERIC(12,2) / NUMERIC(10,4) would otherwise round silently), one set of terms per token, and a
   token already stored keeps its terms (a contract is immutable by identity; the database also refuses, OF006).
3. Loads the stored catalogue and calls the domain ``Catalogue.update`` (Q244: refuses, raising ValueError, if the
   update would drop any listed contract whose expiry has not passed as of ``as_of``). A refusal writes nothing.
4. Writes the result inside a SAVEPOINT (one unit: all of it or none): INSERT the new contracts, UPDATE
   currently_listed = TRUE on stored contracts present in the list (the database stamps last_seen_at), UPDATE
   currently_listed = FALSE on contracts that left the list. Nothing is ever deleted.
Transaction control (commit) stays with the caller.

Eligibility (what Zerodha permits today, ``ofo.instruments.eligibility``) is not stored here (REQ-053 AC-2).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TextIO

from sqlalchemy import text

from ofo.instruments.catalogue import Catalogue, CatalogueUpdateResult
from ofo.instruments.models import Contract
from ofo.instruments.parser import parse_instruments_rows

#: Fixed key for the update lock (any constant; only the catalogue store uses it).
CATALOGUE_UPDATE_LOCK_KEY = 5_300_053_001

#: Column scales (migration 0003: strike NUMERIC(12,2), tick_size NUMERIC(10,4)).
STRIKE_SCALE = Decimal("0.01")
STRIKE_LIMIT = Decimal(10) ** 10
TICK_SCALE = Decimal("0.0001")
TICK_LIMIT = Decimal(10) ** 6

_COLUMNS = (
    "exchange, instrument_token, exchange_token, tradingsymbol, name, expiry, strike, tick_size, lot_size, "
    "instrument_type, segment"
)
_LOCK = text("SELECT pg_advisory_xact_lock(:k)")
_SELECT = text(f"SELECT id, {_COLUMNS}, currently_listed FROM public.catalogue_contracts ORDER BY id")
_INSERT = text(
    f"INSERT INTO public.catalogue_contracts ({_COLUMNS}) VALUES (:exchange, :instrument_token, :exchange_token, "
    ":tradingsymbol, :name, :expiry, :strike, :tick_size, :lot_size, :instrument_type, :segment)"
)
_SET_LISTED = text(
    "UPDATE public.catalogue_contracts SET currently_listed = :listed "
    "WHERE instrument_token = ANY(CAST(:tokens AS BIGINT[]))"
)


class CatalogueStoreError(ValueError):
    """The store refused: a value it cannot store or reload exactly, or a contract whose terms would change."""


@dataclass(frozen=True)
class StoreUpdateResult:
    added: int
    seen: int
    newly_unlisted: int
    domain: CatalogueUpdateResult


def _label(contract: Contract) -> str:
    return f"{contract.tradingsymbol} (instrument_token {contract.instrument_token})"


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


def check_storable(contract: Contract) -> None:
    """Refuse a contract the table would store differently (rounded, NaN, float)."""
    where = f"contract {_label(contract)}"
    _check_decimal(contract.strike, "strike", STRIKE_SCALE, STRIKE_LIMIT, where)
    _check_decimal(contract.tick_size, "tick_size", TICK_SCALE, TICK_LIMIT, where)
    if not isinstance(contract.lot_size, int) or isinstance(contract.lot_size, bool):
        raise CatalogueStoreError(f"{where}: lot_size {contract.lot_size!r} is not an int")
    if contract.expiry is not None and (not isinstance(contract.expiry, date) or isinstance(contract.expiry, datetime)):
        raise CatalogueStoreError(f"{where}: expiry {contract.expiry!r} is not a date")


def parse_rows_naming_the_row(stream: TextIO) -> list[Contract]:
    """Parse a Zerodha instrument CSV like ``ofo.instruments.parser``, but a row that cannot be parsed (a strike or
    tick that is not a Decimal, a missing column) stops the load with an error naming its line and symbol."""
    contracts: list[Contract] = []
    reader = csv.DictReader(stream)
    for row in reader:
        try:
            contracts.extend(parse_instruments_rows([row]))
        except ValueError as exc:
            symbol = (row.get("tradingsymbol") or "").strip() or "?"
            token = (row.get("instrument_token") or "").strip() or "?"
            raise CatalogueStoreError(
                f"line {reader.line_num}: {symbol} (instrument_token {token}): {exc}"
            ) from None
    return contracts


def _row_contract(row: Any) -> Contract:
    where = f"stored row id={row.id} {row.tradingsymbol} (instrument_token {row.instrument_token})"
    contract = Contract(
        instrument_token=int(row.instrument_token),
        exchange_token=int(row.exchange_token),
        tradingsymbol=row.tradingsymbol,
        name=row.name,
        expiry=row.expiry,
        strike=row.strike,
        tick_size=row.tick_size,
        lot_size=int(row.lot_size),
        instrument_type=row.instrument_type,
        segment=row.segment,
        exchange=row.exchange,
    )
    _check_decimal(contract.strike, "strike", STRIKE_SCALE, STRIKE_LIMIT, where)
    _check_decimal(contract.tick_size, "tick_size", TICK_SCALE, TICK_LIMIT, where)
    return contract


async def load_catalogue(conn: Any) -> Catalogue:
    """Every stored contract as a domain Catalogue, each with its stored listedness."""
    rows = (await conn.execute(_SELECT)).all()
    contracts: list[Contract] = []
    unlisted: set[int] = set()
    seen: dict[int, int] = {}
    for row in rows:
        contract = _row_contract(row)
        if contract.instrument_token in seen:
            raise CatalogueStoreError(
                f"stored rows id={seen[contract.instrument_token]} and id={row.id} share instrument_token "
                f"{contract.instrument_token}"
            )
        seen[contract.instrument_token] = row.id
        contracts.append(contract)
        if not row.currently_listed:
            unlisted.add(contract.instrument_token)
    catalogue = Catalogue()
    loaded = catalogue.load(contracts)
    if loaded != len(contracts):
        in_scope = {e.contract.instrument_token for e in catalogue.all_entries()}
        stray = next(c for c in contracts if c.instrument_token not in in_scope)
        raise CatalogueStoreError(f"stored row {_label(stray)} is outside the catalogue's scope")
    for entry in catalogue.all_entries():
        if entry.contract.instrument_token in unlisted:
            entry.currently_listed = False
    return catalogue


def _params(contract: Contract) -> dict[str, Any]:
    return {
        "exchange": contract.exchange,
        "instrument_token": contract.instrument_token,
        "exchange_token": contract.exchange_token,
        "tradingsymbol": contract.tradingsymbol,
        "name": contract.name,
        "expiry": contract.expiry,
        "strike": contract.strike,
        "tick_size": contract.tick_size,
        "lot_size": contract.lot_size,
        "instrument_type": contract.instrument_type,
        "segment": contract.segment,
    }


async def apply_update(
    conn: Any,
    contracts: Iterable[Contract],
    *,
    as_of: datetime,
    force: bool = False,
    reason: str | None = None,
    actor: str | None = None,
    audit_log: Any = None,
) -> StoreUpdateResult:
    """Apply a newer instrument list to the stored catalogue (see the module docstring). Refusals raise before any
    write: ValueError from the domain (Q244, force without reason/actor/audit_log), CatalogueStoreError here."""
    contracts = list(contracts)
    await conn.execute(_LOCK, {"k": CATALOGUE_UPDATE_LOCK_KEY})
    catalogue = await load_catalogue(conn)
    before = {e.contract.instrument_token: (e.contract, e.currently_listed) for e in catalogue.all_entries()}

    scoped: dict[int, Contract] = {}
    for contract in contracts:
        if not Catalogue._in_scope(contract):
            continue
        check_storable(contract)
        token = contract.instrument_token
        if token in scoped and scoped[token] != contract:
            raise CatalogueStoreError(f"the list holds two different contracts for instrument_token {token}")
        scoped[token] = contract
        stored = before.get(token)
        if stored is not None and stored[0] != contract:
            raise CatalogueStoreError(
                f"contract {_label(contract)} differs from the stored contract {stored[0]!r}: a contract's terms "
                f"never change (REQ-053 AC-2)"
            )

    domain = catalogue.update(
        contracts, as_of=as_of, force=force, reason=reason, actor=actor, audit_log=audit_log
    )

    after = {e.contract.instrument_token: e.currently_listed for e in catalogue.all_entries()}
    new = [scoped[t] for t in sorted(scoped) if t not in before]
    seen = sorted(t for t in scoped if t in before)
    unlisted = sorted(t for t, listed in after.items() if not listed and before.get(t, (None, False))[1])
    new_tokens = {c.instrument_token for c in new}  # compare tokens with tokens, never with Contract objects
    if set(after) != set(before) | new_tokens or any(not after[t] for t in scoped):
        raise CatalogueStoreError("domain catalogue state does not match the planned write; nothing written")

    async with conn.begin_nested():
        if new:
            await conn.execute(_INSERT, [_params(c) for c in new])
        if seen:
            await conn.execute(_SET_LISTED, {"listed": True, "tokens": seen})
        if unlisted:
            await conn.execute(_SET_LISTED, {"listed": False, "tokens": unlisted})
    return StoreUpdateResult(added=len(new), seen=len(seen), newly_unlisted=len(unlisted), domain=domain)
