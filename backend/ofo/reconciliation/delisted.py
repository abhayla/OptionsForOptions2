"""ADR-058: a delisted contract held by a live strategy raises that strategy's reconciliation (ADR-018/ADR-019).

ADR-058 consequence, verbatim: "A delisted contract held by a live strategy raises that strategy's reconciliation
(ADR-018) instead of failing the load." The catalogue update marks the contract delisted and keeps loading; this
function is the other half: every strategy with a NON-ZERO position (long or short, platform fills or adopted
holdings) in such a contract is blocked with the reason CODE ``DELISTED_HELD`` (a code, never a sentence: user wording
comes only from the message catalogue). A strategy that does not hold the contract is untouched.

Real case: none recorded. The ADR-058 case (NIFTY Dec-2029 23000 CE, token 61746) was not held by any strategy, so the
tests build the held positions by hand on a real ``OrderBook``.

Mapping: the book keys positions by the broker's tradingsymbol (``Order.contract``); the catalogue knows a contract by
its exchange identity (``InstrumentId``) and carries the broker's symbol on its broker row. The catalogue store hands
this function both (``DelistedContract``). Fail closed: two delisted contracts naming one symbol, or one delisted
contract naming two held symbols, is ambiguous and raises before any strategy is blocked.

The book is taken as a protocol, not imported: only the execution flows import ``ofo.orders`` (AC-3 import guard,
tests/execution/test_strategy_only.py), exactly as ``grouping.py`` does.

The app caller (after each catalogue update, with the LIVE order book) needs the persisted order book (issue #313,
GC-2c): until that exists nothing is wired to an in-memory book, because a book rebuilt empty would block nothing and
look fine.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from ofo.instruments.models import InstrumentId

#: ADR-058 reason code on the blocking reconciliation event.
DELISTED_HELD = "delisted_held"


class DelistedMappingError(ValueError):
    """A delisted contract cannot be mapped to exactly one book contract key; nothing was blocked."""


class HeldBook(Protocol):
    """What this function reads and writes on an ``OrderBook``."""

    def strategy_ids(self) -> tuple[str, ...]: ...

    def positions_for(self, strategy_id: str) -> Mapping[str, int]: ...

    def block_strategy(self, strategy_id: str, reason: str) -> None: ...


@dataclass(frozen=True)
class DelistedContract:
    """One contract a catalogue update delisted: its exchange identity and the broker symbol(s) its rows carry."""

    instrument_id: InstrumentId
    tradingsymbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, InstrumentId):
            raise ValueError(f"a delisted contract needs an InstrumentId, got {self.instrument_id!r}")
        if not self.tradingsymbols or any(not isinstance(s, str) or not s.strip() for s in self.tradingsymbols):
            raise ValueError(f"a delisted contract needs non-empty tradingsymbols, got {self.tradingsymbols!r}")


def block_delisted_held(book: HeldBook, delisted: Iterable[DelistedContract]) -> tuple[str, ...]:
    """Block every strategy holding a non-zero position in a delisted contract; return the blocked strategy ids."""
    holdings = {sid: book.positions_for(sid) for sid in book.strategy_ids()}
    held_keys = {key for positions in holdings.values() for key in positions}
    owner_of: dict[str, InstrumentId] = {}
    to_block: dict[str, None] = {}
    for contract in delisted:
        matched = {s for s in contract.tradingsymbols if s in held_keys}
        if len(matched) > 1:
            raise DelistedMappingError(f"{contract.instrument_id} matches {len(matched)} held book contracts "
                                       f"{sorted(matched)}; nothing blocked")
        for symbol in contract.tradingsymbols:
            other = owner_of.setdefault(symbol, contract.instrument_id)
            if other != contract.instrument_id:
                raise DelistedMappingError(f"{symbol} is named by delisted {other} and {contract.instrument_id}; "
                                           "nothing blocked")
        for sid, positions in holdings.items():
            if matched & set(positions):
                to_block[sid] = None
    for sid in to_block:  # only after every mapping was proven unambiguous
        book.block_strategy(sid, DELISTED_HELD)
    return tuple(to_block)
