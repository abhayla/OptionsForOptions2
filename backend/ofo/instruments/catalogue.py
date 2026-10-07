"""Contract catalogue: what NIFTY/SENSEX option and future contracts exist.

REQ-053 AC-2: the catalogue is stored separately from current eligibility (what Zerodha permits
today — see `ofo.instruments.eligibility`), and a contract missing from a newer instrument list is
marked not currently listed, never deleted.

Lot size, tick size and strike gap are always DERIVED from the parsed instrument data for the
matching underlying + expiry — never hard-coded (ADR-007 Q36).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterable, Union

from ofo.audit import AuditLog, EventType
from ofo.instruments.models import (
    FUTURE_TYPE,
    OPTION_TYPES,
    BSE_FO,
    NSE_FO,
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

# The two underlyings this catalogue tracks, by exchange segment (ADR-007 / REQ-053 scope; REQ-054 segment list).
SUPPORTED_UNDERLYINGS: dict[str, str] = {
    "NIFTY": NSE_FO,
    "SENSEX": BSE_FO,
}

# The update date is the calendar date in India (the exchanges' timezone), ADR-007.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

#: ADR-058: an update is refused if MORE than this percentage of one index's live contracts would disappear at once
#: (an admin setting; ofo_app.config.Settings.CATALOGUE_MAX_DELIST_PERCENT holds the same default).
DEFAULT_MAX_DELIST_PERCENT = Decimal("10")
#: ADR-059: ... or if any one unexpired expiry of an index would lose MORE than half of its live contracts at once.
MAX_EXPIRY_LOSS_FRACTION = Decimal("0.5")
#: ADR-059 (a): "the strike is unchanged and the expiry moved by at most 6 calendar days" (62964: 5 days, 61746: 3
#: days); a move of 7 days or more is a token reuse, i.e. a new contract.
MAX_EXPIRY_MOVE_DAYS = 6


def check_max_delist_percent(value: object) -> Decimal:
    """The ADR-058 setting: an int or Decimal from 0 to 100 (never a float or bool); anything else is refused."""
    if (isinstance(value, bool) or not isinstance(value, (int, Decimal)) or not Decimal(value).is_finite()
            or not Decimal(0) <= Decimal(value) <= Decimal(100)):
        raise ValueError(f"max_delist_percent must be an int or Decimal from 0 to 100, got {value!r}")
    return Decimal(value)


def is_revision(old: Contract, new: Contract) -> bool:
    """ADR-059: a list row on a stored contract's token revises that contract only if the underlying, option type and
    exchange segment are unchanged AND either (a) the strike is unchanged and the expiry moved by at most
    MAX_EXPIRY_MOVE_DAYS calendar days, or (b) the expiry is unchanged and the strike changed. Anything else is the
    exchange reusing the token: a new contract. An unchanged row is case (a) with a 0-day move."""
    if (old.name, old.instrument_type, old.exchange_segment) != (new.name, new.instrument_type, new.exchange_segment):
        return False
    if old.expiry is None or new.expiry is None:
        return old.expiry == new.expiry and old.strike == new.strike
    if old.strike == new.strike:
        return abs((new.expiry - old.expiry).days) <= MAX_EXPIRY_MOVE_DAYS
    return old.expiry == new.expiry


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
    """Fail closed: two in-scope rows of one list with the same exchange identity stop the load, naming both. (F-10: on the
    real 2026-10-02 file 30 NSE cash/index pairs share an exchange token; they are outside V1 and never reach here.)"""
    seen: dict[InstrumentId, ListedContract] = {}
    for row in rows:
        if row.id in seen:
            names = [", ".join(r.broker_symbol for r in x.broker_refs) or x.contract.name for x in (seen[row.id], row)]
            raise ValueError(f"two instrument rows share the identity {row.id.exchange_segment}:{row.id.exchange_token} "
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
        old = refs.get(ref.broker)
        if old is not None and ref.freeze_limit is None and old.freeze_limit is not None:
            # REQ-054 "Per-broker values and their date": a list without a value leaves the stored value.
            ref = dataclasses.replace(ref, freeze_limit=old.freeze_limit)
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
            and contract.exchange_segment == SUPPORTED_UNDERLYINGS[contract.name]
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
        max_delist_percent: object = DEFAULT_MAX_DELIST_PERCENT,
    ) -> "CatalogueUpdateResult":
        """Refresh from a newer instrument list.

        Contracts present in `contracts` are (re)inserted as currently listed. In-scope
        contracts already in the catalogue but absent from `contracts` are marked
        `currently_listed = False` — they are never removed (AC-2).

        Refuses (raises `ValueError`, changes nothing) when the list looks truncated (ADR-058, ADR-059, replacing the
        old Q244 "refuse any unexpired drop"): MORE than `max_delist_percent` (default 10) of one index's live
        contracts would disappear at once, or any one unexpired expiry of an index would lose MORE than half of its
        live contracts. Live = listed and not expired on the update date, judged against `as_of` (timezone-aware,
        never a hidden clock) converted to its India (IST) calendar date: a contract expiring ON that date has not yet
        passed. Contracts of an already-passed expiry may roll off; a list row whose expiry has passed is skipped.
        A row on an existing token that is not a revision (`is_revision`, ADR-059) replaces the entry: a new contract.

        `force=True` overrides the guards (a real broker delisting) but ONLY with a non-empty
        `reason`, a non-empty `actor` and an explicit `audit_log` (no hidden global): a forced
        update is refused otherwise, and every forced update appends one ADMIN_CHANGE_RECORDED
        event (who, when = `as_of`, reason, exact dropped contract ids) before anything changes
        (REQ-064; issue #80). `reason`/`actor`/`audit_log` are rejected without `force`.
        """
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("Catalogue.update() requires a timezone-aware as_of")
        update_date = as_of.astimezone(IST).date()
        limit = check_max_delist_percent(max_delist_percent)

        rows = [_listed(r) for r in contracts]
        in_scope = [r for r in rows if self._in_scope(r.contract)]
        # ADR-059: a row whose expiry is already before the load date is skipped, never loaded.
        in_scope_new = [r for r in in_scope if r.contract.expiry is None or r.contract.expiry >= update_date]
        skipped_expired = len(in_scope) - len(in_scope_new)
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

        # ADR-059: a row on an existing token that is not a revision is the exchange reusing the token.
        replaced = sorted(r.id for r in in_scope_new
                          if r.id in self._entries and not is_revision(self._entries[r.id].contract, r.contract))
        live = {iid: e for iid, e in self._entries.items()
                if e.currently_listed and (e.contract.expiry is None or e.contract.expiry >= update_date)}
        vanishing = sorted((e for iid, e in live.items() if iid not in new_ids), key=lambda e: e.id)
        # ADR-059: both guards count every live contract that stops being live in this update - not carried, AND
        # delisted because its token now carries another contract.
        leaving_live = vanishing + [live[i] for i in replaced if i in live]
        if force:
            assert audit_log is not None and reason is not None and actor is not None
            leaving = vanishing + [self._entries[i] for i in replaced]
            audit_log.append(
                EventType.ADMIN_CHANGE_RECORDED,
                actor=actor.strip(),
                timestamp=as_of,
                correlation_id=f"catalogue-force-update-{as_of.isoformat()}",
                payload={
                    "action": "catalogue_force_update",
                    "reason": reason.strip(),
                    # every contract this update delists: not carried (ADR-058) or its token reused (ADR-059), under
                    # the two keys the audit allowlist declares (ofo_app.audit_allowlist, REQ-063 AC-5); any other key
                    # would be dropped before storage
                    "dropped_instrument_tokens": [[e.id.exchange_segment, e.id.exchange_token] for e in leaving],
                    "dropped_tradingsymbols": [
                        [r.broker, r.broker_symbol] for e in leaving for r in e.broker_refs.values()
                    ],
                },
            )
        else:
            _refuse_truncation(list(live.values()), leaving_live, limit, update_date)

        added = 0
        replaced_set = set(replaced)
        for row in in_scope_new:
            existing = None if row.id in replaced_set else self._entries.get(row.id)
            if existing is None:
                added += 1
            self._entries[row.id] = _entry(row, existing)

        newly_unlisted = 0
        for iid, entry in self._entries.items():
            if iid not in new_ids and entry.currently_listed:
                entry.currently_listed = False
                newly_unlisted += 1

        return CatalogueUpdateResult(added=added, newly_unlisted=newly_unlisted, skipped_expired=skipped_expired,
                                     replaced=tuple(replaced), delisted=tuple(e.id for e in vanishing))

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


def _refuse_truncation(live: list[CatalogueEntry], vanishing: list[CatalogueEntry], limit: Decimal,
                       update_date: date) -> None:
    """ADR-058 per-index count and ADR-059 per-expiry half guard (both "more than": the boundary itself passes).
    `vanishing` is every live contract that stops being live: not carried AND token reused (ADR-059)."""
    def counts(entries, key):
        out: dict = {}
        for e in entries:
            out[key(e)] = out.get(key(e), 0) + 1
        return out

    live_index, gone_index = counts(live, lambda e: e.contract.name), counts(vanishing, lambda e: e.contract.name)
    for name in sorted(gone_index):
        if gone_index[name] * 100 > limit * live_index[name]:
            share = (Decimal(gone_index[name] * 100) / live_index[name]).quantize(Decimal("0.1"))
            raise ValueError(
                f"Catalogue update refused: would drop {gone_index[name]} of {live_index[name]} live {name} contracts "
                f"({share}%), more than {limit}% at once - the source list may be truncated (ADR-058); nothing changed; "
                f"override needs force=True with a reason, actor and audit_log")
    by_expiry = lambda e: (e.contract.name, e.contract.expiry)  # noqa: E731
    live_expiry, gone_expiry = counts(live, by_expiry), counts(vanishing, by_expiry)
    for key in sorted(gone_expiry, key=lambda k: (k[0], k[1] or date.max)):
        if gone_expiry[key] > MAX_EXPIRY_LOSS_FRACTION * live_expiry[key]:
            raise ValueError(
                f"Catalogue update refused: would drop {gone_expiry[key]} of {live_expiry[key]} live {key[0]} "
                f"contracts of expiry {key[1]}, more than half of one expiry at once - the source list may be "
                f"truncated (ADR-059); nothing changed; override needs force=True with a reason, actor and audit_log")


@dataclass
class CatalogueUpdateResult:
    added: int
    newly_unlisted: int
    skipped_expired: int = 0  # in-scope rows whose expiry had passed: never loaded (ADR-059)
    replaced: tuple[InstrumentId, ...] = ()  # tokens reused by a new contract in this list (ADR-059)
    delisted: tuple[InstrumentId, ...] = ()  # live contracts this list stopped carrying (ADR-058)
