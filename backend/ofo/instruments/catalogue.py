"""Contract catalogue: what NIFTY/SENSEX option and future contracts exist.

REQ-053 AC-2: the catalogue is stored separately from current eligibility (what Zerodha permits
today — see `ofo.instruments.eligibility`), and a contract missing from a newer instrument list is
marked not currently listed, never deleted.

Lot size, tick size and strike gap are always DERIVED from the parsed instrument data for the
matching underlying + expiry — never hard-coded (ADR-007 Q36).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from ofo.instruments.models import Contract

# The two underlyings this catalogue tracks (ADR-007 / REQ-053 scope: NIFTY on NFO, SENSEX on BFO).
SUPPORTED_UNDERLYINGS: dict[str, str] = {
    "NIFTY": "NFO",
    "SENSEX": "BFO",
}


@dataclass
class CatalogueEntry:
    """A contract plus its listedness in the catalogue (mutable; identity is the contract)."""

    contract: Contract
    currently_listed: bool


class Catalogue:
    """Contract catalogue for the supported underlyings, keyed by `instrument_token`.

    `update()` never deletes an entry: a contract absent from a newer list is marked
    `currently_listed = False` and kept (REQ-053 AC-2).
    """

    def __init__(self) -> None:
        self._entries: dict[int, CatalogueEntry] = {}

    @staticmethod
    def _in_scope(contract: Contract) -> bool:
        return (
            contract.name in SUPPORTED_UNDERLYINGS
            and contract.exchange == SUPPORTED_UNDERLYINGS[contract.name]
            and (contract.is_option() or contract.is_future())
        )

    def load(self, contracts: Iterable[Contract]) -> int:
        """Initial load: every in-scope contract is inserted as currently listed.

        Returns the number of contracts loaded into scope (out-of-scope rows are silently
        skipped — this catalogue only tracks NIFTY/SENSEX).
        """
        count = 0
        for contract in contracts:
            if not self._in_scope(contract):
                continue
            self._entries[contract.instrument_token] = CatalogueEntry(
                contract=contract, currently_listed=True
            )
            count += 1
        return count

    def update(self, contracts: Iterable[Contract]) -> "CatalogueUpdateResult":
        """Refresh from a newer instrument list.

        Contracts present in `contracts` are (re)inserted as currently listed. In-scope
        contracts already in the catalogue but absent from `contracts` are marked
        `currently_listed = False` — they are never removed (AC-2).
        """
        seen_tokens: set[int] = set()
        added = 0
        for contract in contracts:
            if not self._in_scope(contract):
                continue
            seen_tokens.add(contract.instrument_token)
            existing = self._entries.get(contract.instrument_token)
            if existing is None:
                added += 1
            self._entries[contract.instrument_token] = CatalogueEntry(
                contract=contract, currently_listed=True
            )

        newly_unlisted = 0
        for token, entry in self._entries.items():
            if token not in seen_tokens and entry.currently_listed:
                entry.currently_listed = False
                newly_unlisted += 1

        return CatalogueUpdateResult(added=added, newly_unlisted=newly_unlisted)

    def all_entries(self) -> list[CatalogueEntry]:
        return list(self._entries.values())

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

    def lot_size(self, name: str, expiry: date) -> int:
        """Lot size for an underlying + expiry, derived from its contracts.

        Raises `ValueError` if no contracts are found, or if the lot size is inconsistent across
        contracts for that underlying + expiry (a real data anomaly — fail closed, never guess).
        """
        contracts = self.contracts_for(name, expiry)
        if not contracts:
            raise ValueError(f"no contracts found for {name} expiry {expiry}: cannot derive lot size")
        lot_sizes = {c.lot_size for c in contracts}
        if len(lot_sizes) != 1:
            raise ValueError(
                f"inconsistent lot size for {name} expiry {expiry}: {sorted(lot_sizes)}"
            )
        return lot_sizes.pop()

    def tick_size(self, name: str, expiry: date) -> Decimal:
        """Tick size for an underlying + expiry, derived from its contracts."""
        contracts = self.contracts_for(name, expiry)
        if not contracts:
            raise ValueError(f"no contracts found for {name} expiry {expiry}: cannot derive tick size")
        tick_sizes = {c.tick_size for c in contracts}
        if len(tick_sizes) != 1:
            raise ValueError(
                f"inconsistent tick size for {name} expiry {expiry}: {sorted(tick_sizes)}"
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
