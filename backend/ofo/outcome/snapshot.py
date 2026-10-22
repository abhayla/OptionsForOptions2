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
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from ofo.engine.legs import Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.instruments.models import ListedContract
from ofo.marketdata.forward import ExpiryForward, ForwardUnavailable, parity_forward
from ofo.marketdata.provider import MarketDataProvider, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote
from ofo.marketdata.shared_compute import FeedScope


def contract_id(lc: ListedContract) -> str:
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


@dataclass(frozen=True)
class LegMarket:
    instrument_id: str
    contract: ListedContract | None
    quote: NormalizedQuote | None
    problem: ExplanationText | None = None  # a catalogue render (W-066)


@dataclass(frozen=True)
class MarketSnapshot:
    underlying: str
    valuation: datetime.datetime
    rate: Decimal
    status: ProviderStatus
    spot: NormalizedQuote | None
    legs: Mapping[str, LegMarket]
    forwards: Mapping[datetime.date, ExpiryForward]
    forward_errors: Mapping[datetime.date, ExplanationText] = field(default_factory=dict)
    #: ADR-077: the kept last quote TIME of each input (spot index, legs) that holds no quote now; never a price.
    ended_times: Mapping[str, datetime.datetime] = field(default_factory=dict)


#: A leg is one of the three engine types; any other catalogue row (the index rows) is not a leg.
_LEG_TYPES = frozenset(i.value for i in Instrument)


def _forward(chain, spot, expiry, at, where):
    """One expiry's forward; with ``shared`` computed once per (feed owner, underlying, expiry, valuation instant, the
    exact quotes it reads). A refused forward raises and is never cached (the next reader tries again)."""
    shared, underlying = where
    valuation, rate = at
    if shared is None:
        return parity_forward(chain, spot, expiry, valuation, rate)
    quotes = tuple((q.instrument_id, q.bid, q.ask, q.timestamp, q.health) for q in chain)
    inputs = (rate, spot.ltp, spot.timestamp, spot.health, quotes) if spot is not None else (rate, None, quotes)
    scope = (underlying, expiry, valuation, "forward", None)
    return shared.compute(scope, inputs, lambda: parity_forward(chain, spot, expiry, valuation, rate))


def read_snapshot(provider: MarketDataProvider, underlying: str, instrument_ids: list[str],  # noqa: PLR0913
                  valuation: datetime.datetime, rate: Decimal, shared: FeedScope | None = None) -> MarketSnapshot:
    """Read every input the outcome needs from ``provider`` in one pass (one status, one spot, one chain/expiry).

    ``shared`` (REQ-050, ADR-053): a :class:`FeedScope`; each expiry's forward is then computed once per feed snapshot,
    with the feed owner in the key."""
    if not isinstance(provider, MarketDataProvider):
        raise ValueError(f"provider must be a MarketDataProvider, got {provider!r}")
    status = provider.status()
    spot = provider.underlying_quote(underlying)
    master = {contract_id(lc): lc for lc in provider.instrument_master()}
    chains: dict[datetime.date, list[NormalizedQuote]] = {}
    legs: dict[str, LegMarket] = {}
    for iid in instrument_ids:
        lc = master.get(iid)
        if lc is None or lc.contract.instrument_type not in _LEG_TYPES:  # an INDEX row is not a leg (REQ-001 AC-2)
            legs[iid] = LegMarket(iid, None, None, render_explanation("outcome_why_unknown_instrument"))
            continue
        c = lc.contract
        if c.name != underlying:
            legs[iid] = LegMarket(iid, lc, None, render_explanation("outcome_why_other_underlying", contract_on=c.name,
                                                              underlying=underlying))
            continue
        if c.expiry is None or c.expiry < valuation.date():
            legs[iid] = LegMarket(iid, lc, None, render_explanation("outcome_why_expired"))
            continue
        if c.expiry not in chains:
            chains[c.expiry] = provider.option_chain_snapshot(underlying, c.expiry)
        quote = next((q for q in chains[c.expiry] if q.instrument_id == iid), None)
        legs[iid] = LegMarket(iid, lc, quote)
    forwards: dict[datetime.date, ExpiryForward] = {}
    errors: dict[datetime.date, str] = {}
    for expiry, chain in chains.items():
        try:
            forwards[expiry] = _forward(chain, spot, expiry, (valuation, rate), (shared, underlying))
        except ForwardUnavailable:
            errors[expiry] = render_explanation("outcome_why_forward")  # the cause goes to no user
    ended: dict[str, datetime.datetime] = {}
    index_id = getattr(provider, "index_id", lambda _u: None)(underlying)
    for iid in [*instrument_ids, *([index_id] if index_id else [])]:
        held = spot if iid == index_id else (legs[iid].quote if iid in legs else None)
        t = provider.last_quote_time(iid) if held is None else None
        if t is not None:
            ended[iid] = t
    return MarketSnapshot(underlying, valuation, rate, status, spot, legs, forwards, errors, ended)
