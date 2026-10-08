"""One consistent market snapshot for a strategy, read from a ``MarketDataProvider`` (W-063 step 2).

The snapshot holds, read at ONE provider time: each leg's listed contract and quote, the index spot quote, each
expiry's forward (ADR-061) and the provider status. Nothing here computes a P&L; a stale or unavailable input is kept
with its health so the outcome service labels or refuses it (W-059/W-060), never computes it silently.

Answer states per input (run-discipline B4 (d)):

- leg instrument not in the provider's master: ``LegMarket.contract`` None, ``problem`` "unknown instrument".
- leg contract expired (its expiry date is before the valuation date, or the forward says the expiry close passed):
  ``problem`` "expired".
- leg with no quote yet: ``quote`` None (the outcome labels it "no live quote").
- forward refused (spot missing/unhealthy, expired, absurd chain): ``forward_errors[expiry]`` holds the reason.
- spot fallback: the ``ExpiryForward`` itself carries "estimated from spot".

Standard library only.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from ofo.instruments.models import ListedContract
from ofo.marketdata.forward import ExpiryForward, ForwardUnavailable, parity_forward
from ofo.marketdata.provider import MarketDataProvider, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote


def contract_id(lc: ListedContract) -> str:
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


@dataclass(frozen=True)
class LegMarket:
    instrument_id: str
    contract: ListedContract | None
    quote: NormalizedQuote | None
    problem: str | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    underlying: str
    valuation: datetime.datetime
    rate: Decimal
    status: ProviderStatus
    spot: NormalizedQuote | None
    legs: Mapping[str, LegMarket]
    forwards: Mapping[datetime.date, ExpiryForward]
    forward_errors: Mapping[datetime.date, str] = field(default_factory=dict)


def read_snapshot(provider: MarketDataProvider, underlying: str, instrument_ids: list[str],
                  valuation: datetime.datetime, rate: Decimal) -> MarketSnapshot:
    """Read every input the outcome needs from ``provider`` in one pass (one status, one spot, one chain/expiry)."""
    if not isinstance(provider, MarketDataProvider):
        raise ValueError(f"provider must be a MarketDataProvider, got {provider!r}")
    status = provider.status()
    spot = provider.underlying_quote(underlying)
    master = {contract_id(lc): lc for lc in provider.instrument_master()}
    chains: dict[datetime.date, list[NormalizedQuote]] = {}
    legs: dict[str, LegMarket] = {}
    for iid in instrument_ids:
        lc = master.get(iid)
        if lc is None:
            legs[iid] = LegMarket(iid, None, None, "unknown instrument")
            continue
        c = lc.contract
        if c.name != underlying:
            legs[iid] = LegMarket(iid, lc, None, f"the contract is on {c.name}, the strategy is on {underlying}")
            continue
        if c.expiry is None or c.expiry < valuation.date():
            legs[iid] = LegMarket(iid, lc, None, "expired")
            continue
        if c.expiry not in chains:
            chains[c.expiry] = provider.option_chain_snapshot(underlying, c.expiry)
        quote = next((q for q in chains[c.expiry] if q.instrument_id == iid), None)
        legs[iid] = LegMarket(iid, lc, quote)
    forwards: dict[datetime.date, ExpiryForward] = {}
    errors: dict[datetime.date, str] = {}
    for expiry, chain in chains.items():
        try:
            forwards[expiry] = parity_forward(chain, spot, expiry, valuation, rate)
        except ForwardUnavailable as exc:
            errors[expiry] = str(exc)
    return MarketSnapshot(underlying, valuation, rate, status, spot, legs, forwards, errors)
