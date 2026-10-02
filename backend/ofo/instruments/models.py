"""Contract identity and per-broker instrument data (ADR-050, REQ-054 AC-3/AC-4).

A contract's identity is the exchange's own (exchange segment, exchange token): every broker carries it and it is
the same at every broker (findings F-01). A broker's own token, trading symbol, segment code, lot size, tick size and
freeze limit are that broker's data about the contract (F-02..F-04) and live only in a `BrokerRef`, never in the
`Contract`. A contract with no `BrokerRef` for a broker cannot be traded at that broker: no symbol is guessed or
derived (AC-3).

Money and strike/tick values are `decimal.Decimal`; quantities are `int`. Never float.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

# Instrument types that carry a strike (options).
OPTION_TYPES = frozenset({"CE", "PE"})
FUTURE_TYPE = "FUT"

# One broker code vocabulary (REQ-054 AC-3). V1 has only Zerodha (REQ-054 AC-2).
ZERODHA = "zerodha"
BROKER_CODES: frozenset[str] = frozenset({ZERODHA})


class MissingBrokerRef(ValueError):
    """A contract has no row for the broker (or the broker code is unknown): it cannot be traded there."""


def check_broker_code(broker: object) -> str:
    """Fail closed on any broker code outside the one vocabulary."""
    if not isinstance(broker, str) or broker not in BROKER_CODES:
        raise MissingBrokerRef(f"unknown broker code {broker!r}; known: {sorted(BROKER_CODES)}")
    return broker


@dataclass(frozen=True, order=True)
class InstrumentId:
    """The exchange's identity of a contract: (exchange segment, exchange token). Same at every broker (F-01)."""

    exchange: str
    exchange_token: int

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise ValueError(f"instrument identity needs an exchange, got {self.exchange!r}")
        if (isinstance(self.exchange_token, bool) or not isinstance(self.exchange_token, int)
                or self.exchange_token <= 0):
            raise ValueError(f"instrument identity needs a positive integer exchange token, got {self.exchange_token!r}")


@dataclass(frozen=True)
class Contract:
    """A contract: exchange identity, descriptive fields and revisable terms. Holds no broker's ids.

    `lot_size` and `tick_size` are the contract's current terms as the instrument list showed them; the per-broker,
    dated copy is in `BrokerRef` (AC-4).
    """

    exchange: str
    exchange_token: int
    name: str
    expiry: Optional[date]
    strike: Decimal
    tick_size: Decimal
    lot_size: int
    instrument_type: str
    segment: str

    @property
    def id(self) -> InstrumentId:
        return InstrumentId(self.exchange, self.exchange_token)

    def is_option(self) -> bool:
        return self.instrument_type in OPTION_TYPES

    def is_future(self) -> bool:
        return self.instrument_type == FUTURE_TYPE


@dataclass(frozen=True)
class BrokerRef:
    """One broker's own data for one contract, with the date the broker's list showed it (AC-3, AC-4)."""

    broker: str
    broker_token: str
    broker_symbol: str
    broker_segment: str
    lot_size: int
    tick_size: Decimal
    seen_on: Optional[date]
    freeze_limit: Optional[int] = None

    def __post_init__(self) -> None:
        check_broker_code(self.broker)
        for name in ("broker_token", "broker_symbol", "broker_segment"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"broker row needs a non-empty {name}, got {value!r}")


@dataclass(frozen=True)
class ListedContract:
    """One instrument-list row: the contract and the broker rows that list it."""

    contract: Contract
    broker_refs: tuple[BrokerRef, ...] = field(default=())

    @property
    def id(self) -> InstrumentId:
        return self.contract.id

    def ref(self, broker: str) -> BrokerRef:
        return find_ref(self.contract, self.broker_refs, broker)


def find_ref(contract: Contract, refs, broker: str) -> BrokerRef:
    """The broker's row for the contract, or `MissingBrokerRef` (fail closed: never guess a symbol)."""
    check_broker_code(broker)
    for r in refs:
        if r.broker == broker:
            return r
    raise MissingBrokerRef(f"{contract.id} has no {broker} row; it cannot be traded at {broker}")
