"""The one door from a stored contract id to its live feed key, app-wide (W-122; REQ-109 AC-1, AC-2, AC-5; issue #500).

Why: a stored contract id outlives its exchange token. catalogue_store documents that (exchange_segment,
exchange_token) is unique among LIVE contracts only: after a contract retires (expiry passed, ADR-057) or is delisted
(ADR-058) the exchange may give its token to a NEW contract (ADR-059). Pricing a stored id by ``segment:token`` without
checking who holds that token now prices another contract (measured by the W-122 round-2 verifier: leg 0 delisted,
a 26000 CE inserted on its token NSE_FO:44624, and the view answered LIVE +195.00 with leg 0 at the new contract's
45.15).

Design (run-discipline C8, a structural guarantee): ``resolve`` is the only place in backend/ofo_app where a stored
contract id becomes a feed key: the tracking route, the saved strategy's legs handed to the Builder for outcome requests
(routes/strategies.py) and Execute's entry legs (routes/execute.py). A key is given ONLY when the catalogue row
is live (neither retired nor delisted) AND the
live contract holding its (segment, token) today is the same internal id. Every other answer is an explicit state and
carries no feed key, so nothing can be priced for it:

- ``live``: the key is ``segment:token``; the feed's own answer (live / stale / missing) is then ofo.tracking.paper's;
- ``contract_retired``: expired and retired (settlement at expiry is REQ-109 AC-7, Step 5, not here);
- ``contract_delisted``: delisted and its token not held by another live contract;
- ``token_reassigned``: the token now belongs to a different live contract (delisted-then-reused, or any live row the
  live lookup does not answer with this id);
- ``contract_missing``: no stored contract has the id, or a live row the live lookup cannot find (fails closed).

A strategy with any leg not ``live`` is PAUSED with that reason in the view (no paper P&L, no detection) and refused
at Start tracking; a saved strategy's leg that is not live carries its state and no key (the Builder sends no outcome
request for it); Execute refuses it. A repo scan (tests_app/test_strategy_tracking_imports.py) fails when any module of
backend/ofo_app outside a reviewed list reaches the catalogue's raw identity any other way.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ofo.instruments.models import InstrumentId
from ofo.tracking.paper import ContractReason

from ofo_app.catalogue_store import CatalogueStoreError, StoredContract, live_contract_id, load_contract

ContractState = Literal["live"] | ContractReason
LIVE: ContractState = "live"


@dataclass(frozen=True)
class TrackedContract:
    """One stored contract's answer: ``feed_key`` is set only when ``state`` is live; ``stored`` is None only when no
    contract has the id."""

    contract_id: int
    state: ContractState
    stored: StoredContract | None

    @property
    def identity(self) -> str | None:
        """The stored contract's own exchange identity, for DISPLAY only (a reused token's quote is another
        contract's); None when no contract has the id."""
        if self.stored is None:
            return None
        c = self.stored.listed.contract
        return f"{c.exchange_segment}:{c.exchange_token}"

    @property
    def feed_id(self) -> InstrumentId | None:
        """The exchange id to price this contract by: set ONLY when the contract is live and holds its own token."""
        if self.state != LIVE or self.stored is None:
            return None
        c = self.stored.listed.contract
        return InstrumentId(c.exchange_segment, c.exchange_token)

    @property
    def feed_key(self) -> str | None:
        """The feed key (``segment:token``) of ``feed_id``; None exactly when ``feed_id`` is."""
        return self.identity if self.feed_id is not None else None


async def _state(db: Any, stored: StoredContract) -> ContractState:
    if stored.retired:
        return "contract_retired"
    c = stored.listed.contract
    holder = await live_contract_id(db, InstrumentId(c.exchange_segment, c.exchange_token))
    if holder is not None and holder != stored.contract_id:
        return "token_reassigned"
    if stored.delisted:
        return "contract_delisted"
    return LIVE if holder == stored.contract_id else "contract_missing"


async def resolve_one(db: Any, contract_id: int) -> TrackedContract:
    try:
        stored = await load_contract(db, contract_id)
    except CatalogueStoreError:
        return TrackedContract(contract_id, "contract_missing", None)
    return TrackedContract(contract_id, await _state(db, stored), stored)


async def resolve(db: Any, contract_ids: Sequence[int]) -> tuple[TrackedContract, ...]:
    """Each stored contract's answer, in order (module docstring)."""
    return tuple([await resolve_one(db, cid) for cid in contract_ids])


def reasons(contracts: Sequence[TrackedContract]) -> list[ContractReason | None]:
    """Per leg: None when live, else the reason it is not (ofo.tracking.paper.tracking_view's contract_reasons)."""
    return [None if c.state == LIVE else c.state for c in contracts]  # type: ignore[misc]
