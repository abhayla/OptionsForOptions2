"""Contract catalogue: what NIFTY/SENSEX option and future contracts exist.

REQ-053 AC-2: the catalogue is stored separately from current eligibility (what Zerodha permits
today — see `ofo.instruments.eligibility`), and a contract missing from a newer instrument list is
marked not currently listed, never deleted.

Lot size, tick size and strike gap are always DERIVED from the parsed instrument data for the
matching underlying + expiry — never hard-coded (ADR-007 Q36).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterable, Union

from ofo.audit import AuditLog, EventType
from ofo.instruments.models import (
    FUTURE_TYPE,
    OPTION_TYPES,
    BrokerRef,
    Contract,
    InstrumentId,
    ListedContract,
    check_broker_code,
    find_ref,
)

# A row given to load()/update(): a listed contract with its broker rows, or a bare contract (no broker row, so it
# cannot be traded at any broker; REQ-054 AC-3).
Row = Union[Contract, ListedContract]


def _listed(row: Row) -> ListedContract:
    if isinstance(row, ListedContract):
        return row
    if isinstance(row, Contract):
        return ListedContract(contract=row)
    raise TypeError(f"catalogue rows are Contract or ListedContract, got {row!r}")

# The two underlyings this catalogue tracks (ADR-007 / REQ-053 scope: NIFTY on NFO, SENSEX on BFO).
SUPPORTED_UNDERLYINGS: dict[str, str] = {
    "NIFTY": "NFO",
    "SENSEX": "BFO",
}

# The update date is the calendar date in India (the exchanges' timezone), ADR-007.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class ContractKind(str, Enum):
    """Option vs future — Zerodha ticks and lot sizes can legitimately differ between the two
    for the SAME underlying + expiry (e.g. real fixture: NIFTY 2026-09-29 options tick 0.05,
    futures tick 0.1). Any aggregation across contracts for one underlying + expiry must be
    scoped to one kind, never mixed (REQ-053 AC-2 finding, fix round 1)."""

    OPTION = "option"
    FUTURE = "future"


def _kind_types(kind: ContractKind) -> frozenset[str]:
    if kind is ContractKind.OPTION:
        return OPTION_TYPES
    if kind is ContractKind.FUTURE:
        return frozenset({FUTURE_TYPE})
    raise ValueError(f"unknown contract kind: {kind!r}")


def _refuse_duplicate_ids(rows: list[ListedContract]) -> None:
    """Fail closed: two in-scope rows of one list with the same exchange identity stop the load, naming both. (On the
    real 2026-10-02 file 30 NSE cash/index pairs share an exchange token; none of the 4,970 NFO/BFO rows do.)"""
    seen: dict[InstrumentId, ListedContract] = {}
    for row in rows:
        if row.id in seen:
            names = [", ".join(r.broker_symbol for r in x.broker_refs) or x.contract.name for x in (seen[row.id], row)]
            raise ValueError(f"two instrument rows share the identity {row.id.exchange}:{row.id.exchange_token} "
                             f"({names[0]} and {names[1]}); the list is refused, nothing changed")
        seen[row.id] = row


@dataclass
class CatalogueEntry:
    """A contract plus its listedness and its per-broker rows (mutable; identity is `contract.id`)."""

    contract: Contract
    currently_listed: bool
    broker_refs: dict[str, BrokerRef] = field(default_factory=dict)

    @property
    def id(self) -> InstrumentId:
        return self.contract.id

    def ref(self, broker: str) -> BrokerRef:
        """The broker's own row for this contract; `MissingBrokerRef` when there is none (AC-3: never guessed)."""
        check_broker_code(broker)
        return find_ref(self.contract, self.broker_refs.values(), broker)

    def has_ref(self, broker: str) -> bool:
        check_broker_code(broker)
        return broker in self.broker_refs


def _entry(row: ListedContract, previous: "CatalogueEntry | None") -> CatalogueEntry:
    refs = dict(previous.broker_refs) if previous is not None else {}
    for ref in row.broker_refs:
        refs[ref.broker] = ref  # a broker's newer row replaces its older one; other brokers' rows are kept
    return CatalogueEntry(contract=row.contract, currently_listed=True, broker_refs=refs)


class Catalogue:
    """Contract catalogue for the supported underlyings, keyed by the exchange identity `InstrumentId` (ADR-050).

    `update()` never deletes an entry: a contract absent from a newer list is marked
    `currently_listed = False` and kept (REQ-053 AC-2).
    """

    def __init__(self) -> None:
        self._entries: dict[InstrumentId, CatalogueEntry] = {}

    @staticmethod
    def _in_scope(contract: Contract) -> bool:
        return (
            contract.name in SUPPORTED_UNDERLYINGS
            and contract.exchange == SUPPORTED_UNDERLYINGS[contract.name]
            and (contract.is_option() or contract.is_future())
        )

    def load(self, contracts: Iterable[Row]) -> int:
        """Initial load: every in-scope contract is inserted as currently listed.

        Returns the number of contracts loaded into scope (out-of-scope rows are silently
        skipped — this catalogue only tracks NIFTY/SENSEX).
        """
        scoped = [r for r in map(_listed, contracts) if self._in_scope(r.contract)]
        _refuse_duplicate_ids(scoped)
        count = 0
        for row in scoped:
            self._entries[row.id] = _entry(row, self._entries.get(row.id))
            count += 1
        return count

    def update(
        self,
        contracts: Iterable[Row],
        *,
        as_of: datetime,
        force: bool = False,
        reason: str | None = None,
        actor: str | None = None,
        audit_log: AuditLog | None = None,
    ) -> "CatalogueUpdateResult":
        """Refresh from a newer instrument list.

        Contracts present in `contracts` are (re)inserted as currently listed. In-scope
        contracts already in the catalogue but absent from `contracts` are marked
        `currently_listed = False` — they are never removed (AC-2).

        Refuses (raises `ValueError`, changes nothing) if the update would drop ANY currently
        listed contract whose expiry has not yet passed (owner decision Q244, REQ-053). Expiry
        is judged against `as_of`, a timezone-aware moment passed in by the caller (never a
        hidden clock), converted to its India (IST) calendar date: a contract expiring ON that
        date has not yet passed. Contracts of an already-passed expiry may roll off, and new
        contracts may be added. An empty list therefore refuses while any unexpired contract is
        listed.

        `force=True` overrides the guard (a real broker delisting) but ONLY with a non-empty
        `reason`, a non-empty `actor` and an explicit `audit_log` (no hidden global): a forced
        update is refused otherwise, and every forced update appends one ADMIN_CHANGE_RECORDED
        event (who, when = `as_of`, reason, exact dropped contract ids) before anything changes
        (REQ-064; issue #80). `reason`/`actor`/`audit_log` are rejected without `force`.
        """
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("Catalogue.update() requires a timezone-aware as_of")
        update_date = as_of.astimezone(IST).date()

        rows = [_listed(r) for r in contracts]
        in_scope_new = [r for r in rows if self._in_scope(r.contract)]
        _refuse_duplicate_ids(in_scope_new)
        new_ids = {r.id for r in in_scope_new}

        if not force and (reason is not None or actor is not None or audit_log is not None):
            raise ValueError("Catalogue.update(): reason/actor/audit_log are only valid with force=True")
        if force:
            if reason is None or not reason.strip():
                raise ValueError("Catalogue.update(force=True) refused: a non-empty reason is required")
            if actor is None or not actor.strip():
                raise ValueError("Catalogue.update(force=True) refused: a non-empty actor is required")
            if audit_log is None:
                raise ValueError("Catalogue.update(force=True) refused: an audit_log is required")

        dropped_live = sorted(
            (
                e
                for iid, e in self._entries.items()
                if e.currently_listed
                and iid not in new_ids
                and (e.contract.expiry is None or e.contract.expiry >= update_date)
            ),
            key=lambda e: e.id,
        )
        if force:
            assert audit_log is not None and reason is not None and actor is not None
            audit_log.append(
                EventType.ADMIN_CHANGE_RECORDED,
                actor=actor.strip(),
                timestamp=as_of,
                correlation_id=f"catalogue-force-update-{as_of.isoformat()}",
                payload={
                    "action": "catalogue_force_update",
                    "reason": reason.strip(),
                    "dropped_instrument_ids": [[e.id.exchange, e.id.exchange_token] for e in dropped_live],
                    "dropped_broker_symbols": [
                        [r.broker, r.broker_symbol] for e in dropped_live for r in e.broker_refs.values()
                    ],
                },
            )
        else:
            if dropped_live:
                first = dropped_live[0]
                symbols = ", ".join(r.broker_symbol for r in first.broker_refs.values())
                raise ValueError(
                    f"Catalogue.update() refused: would drop {len(dropped_live)} contract(s) "
                    f"that have not expired as of {update_date} (first: {first.contract.name} "
                    f"{first.id.exchange}:{first.id.exchange_token} {symbols}, "
                    f"expiry {first.contract.expiry}) — the source list may be incomplete or truncated; "
                    f"override needs force=True with a reason, actor and audit_log"
                )

        added = 0
        for row in in_scope_new:
            existing = self._entries.get(row.id)
            if existing is None:
                added += 1
            self._entries[row.id] = _entry(row, existing)

        newly_unlisted = 0
        for iid, entry in self._entries.items():
            if iid not in new_ids and entry.currently_listed:
                entry.currently_listed = False
                newly_unlisted += 1

        return CatalogueUpdateResult(added=added, newly_unlisted=newly_unlisted)

    def all_entries(self) -> list[CatalogueEntry]:
        return list(self._entries.values())

    def get(self, instrument_id: InstrumentId) -> CatalogueEntry | None:
        """The entry for one exchange identity, or None."""
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError(f"the catalogue is keyed by InstrumentId, got {instrument_id!r}")
        return self._entries.get(instrument_id)

    def entries_for_broker_symbol(self, broker: str, symbol: str) -> list[CatalogueEntry]:
        """Entries whose row at `broker` carries `symbol` (a broker's symbol is not unique by itself, F-03)."""
        check_broker_code(broker)
        return [e for e in self._entries.values()
                if broker in e.broker_refs and e.broker_refs[broker].broker_symbol == symbol]

    def contracts_for(
        self, name: str, expiry: date, instrument_types: frozenset[str] | None = None
    ) -> list[Contract]:
        """All contracts (listed or not) for one underlying + expiry, optionally filtered by type."""
        result = []
        for entry in self._entries.values():
            c = entry.contract
            if c.name != name or c.expiry != expiry:
                continue
            if instrument_types is not None and c.instrument_type not in instrument_types:
                continue
            result.append(c)
        return result

    def lot_size(self, name: str, expiry: date, kind: ContractKind) -> int:
        """Lot size for an underlying + expiry + contract kind, derived from its contracts.

        `kind` is required and mandatory (not defaulted): Zerodha can legitimately set a
        different lot size for an underlying's futures than its options on the same expiry, so
        aggregating across kinds is never safe (REQ-053 AC-2 finding, fix round 1).

        Raises `ValueError` if no contracts are found, or if the lot size is inconsistent across
        contracts for that underlying + expiry + kind (a real data anomaly — fail closed, never
        guess).
        """
        contracts = self.contracts_for(name, expiry, instrument_types=_kind_types(kind))
        if not contracts:
            raise ValueError(
                f"no {kind.value} contracts found for {name} expiry {expiry}: cannot derive lot size"
            )
        lot_sizes = {c.lot_size for c in contracts}
        if len(lot_sizes) != 1:
            raise ValueError(
                f"inconsistent lot size for {name} expiry {expiry} kind={kind.value}: {sorted(lot_sizes)}"
            )
        return lot_sizes.pop()

    def tick_size(self, name: str, expiry: date, kind: ContractKind) -> Decimal:
        """Tick size for an underlying + expiry + contract kind, derived from its contracts.

        `kind` is required: on the real fixture, NIFTY 2026-09-29 options tick 0.05 while its
        futures tick 0.1 — aggregating across kinds must never be done (REQ-053 AC-2 finding,
        fix round 1).
        """
        contracts = self.contracts_for(name, expiry, instrument_types=_kind_types(kind))
        if not contracts:
            raise ValueError(
                f"no {kind.value} contracts found for {name} expiry {expiry}: cannot derive tick size"
            )
        tick_sizes = {c.tick_size for c in contracts}
        if len(tick_sizes) != 1:
            raise ValueError(
                f"inconsistent tick size for {name} expiry {expiry} kind={kind.value}: {sorted(tick_sizes)}"
            )
        return tick_sizes.pop()

    def strike_gap(self, name: str, expiry: date) -> Decimal:
        """The near-the-money strike gap for an underlying + expiry, derived from option strikes.

        Zerodha's strike ladder widens far from the money; the gap is measured as the smallest
        positive difference between consecutive distinct strikes (the near-the-money granularity),
        never hard-coded (ADR-007 Q36).
        """
        options = self.contracts_for(name, expiry, instrument_types=frozenset({"CE", "PE"}))
        if not options:
            raise ValueError(f"no option contracts found for {name} expiry {expiry}: cannot derive strike gap")
        strikes = sorted({c.strike for c in options})
        if len(strikes) < 2:
            raise ValueError(
                f"fewer than 2 distinct strikes for {name} expiry {expiry}: cannot derive a gap"
            )
        gaps = [b - a for a, b in zip(strikes, strikes[1:])]
        return min(gaps)


@dataclass
class CatalogueUpdateResult:
    added: int
    newly_unlisted: int
