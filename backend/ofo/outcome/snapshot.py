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
- an expiry's chain: ``chains[expiry]`` holds every quote read for it (empty mapping when no leg expiry was read).

Standard library only.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from ofo.engine.black_scholes import DAYS_IN_YEAR
from ofo.engine.executable_price import Depth
from ofo.engine.legs import Instrument
from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.instruments.models import ListedContract
from ofo.marketdata.forward import ExpiryForward, ForwardUnavailable, parity_forward
from ofo.marketdata.provider import MarketDataProvider, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote
from ofo.marketdata.shared_compute import FeedScope
from ofo.timeutil import EXPIRY_CLOSE


def contract_id(lc: ListedContract) -> str:
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


@dataclass(frozen=True)
class LegMarket:
    instrument_id: str
    contract: ListedContract | None
    quote: NormalizedQuote | None
    problem: ExplanationText | None = None  # a catalogue render (W-066)


@dataclass(frozen=True)
class LegLiquidity:
    """REQ-085 AC-4: what the feed holds for one leg's liquidity, read at the clock. ``depth`` None = the feed
    holds no depth for it (a quote or ltp packet, or the feed not healthy): the warning is then "liquidity unknown",
    never a verdict. ``last_trade_ts`` is epoch seconds; None = none yet (or no day values)."""

    depth: Depth | None
    last_trade_ts: int | None


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
    #: REQ-106 AC-1 / REQ-027 (Q254): each read expiry's chain quotes, kept so the outcome finds the ATM strike (nearest
    #: that expiry's forward) and solves its CE and PE IV for the expected move; read at the same instant as the rest.
    chains: Mapping[datetime.date, tuple[NormalizedQuote, ...]] = field(default_factory=dict)
    #: REQ-085 AC-4: each read leg's depth and last trade time; a leg missing from here has unknown liquidity
    liquidity: Mapping[str, LegLiquidity] = field(default_factory=dict)


#: A leg is one of the three engine types; any other catalogue row (the index rows) is not a leg.
_LEG_TYPES = frozenset(i.value for i in Instrument)


def _forward(chain, spot, expiry, at, where):
    """One expiry's forward; with ``shared`` computed once per (feed owner, underlying, expiry, snapshot instant, the
    exact quotes it reads, the expiry close and the days-per-year convention). A refused forward raises and is never
    cached (the next reader tries again). The quote set is sorted, so the order a chain is read in never splits it."""
    shared, underlying = where
    instant, rate = at
    if shared is None:
        return parity_forward(chain, spot, expiry, instant, rate)
    quotes = tuple(sorted((q.instrument_id, q.bid, q.ask, q.timestamp, q.health.value) for q in chain))
    spot_part = (None,) if spot is None else (spot.ltp, spot.timestamp, spot.health.value)
    inputs = (rate, EXPIRY_CLOSE, DAYS_IN_YEAR, *spot_part, quotes)
    scope = (underlying, expiry, instant, "forward", None)
    return shared.compute(scope, inputs, lambda: parity_forward(chain, spot, expiry, instant, rate))


def snapshot_instant(clock: datetime.datetime, quotes) -> datetime.datetime:
    """The one instant of an answer: the latest frame time among the quotes actually read, never later than ``clock``.
    Every figure (IV, Greeks, forward, the strategy's P&L) is valued at it, so two readers of one snapshot share every
    figure whatever their clocks say; with no quote read it is the clock."""
    times = [q.timestamp for q in quotes if q is not None]
    return min(clock, max(times)) if times else clock


def _expired(expiry: datetime.date, clock: datetime.datetime) -> bool:
    """Judged on the REAL clock, never the frame time: after the close no contract is valued with time left."""
    return expiry < clock.date() or datetime.datetime.combine(expiry, EXPIRY_CLOSE) <= clock


def read_snapshot(provider: MarketDataProvider, underlying: str, instrument_ids: list[str],  # noqa: PLR0913
                  valuation: datetime.datetime, rate: Decimal, shared: FeedScope | None = None) -> MarketSnapshot:
    """Read every input the outcome needs from ``provider`` in one pass (one status, one spot, one chain/expiry).

    ``valuation`` is the clock reading; the snapshot's own ``valuation`` is the one snapshot instant (the latest frame
    time read, capped at the clock). ``shared`` (REQ-050, ADR-053): a :class:`FeedScope`; each expiry's forward is then
    computed once per feed snapshot, with the feed owner in the key."""
    if not isinstance(provider, MarketDataProvider):
        raise ValueError(f"provider must be a MarketDataProvider, got {provider!r}")
    status = provider.status()
    spot = provider.underlying_quote(underlying)
    master = {contract_id(lc): lc for lc in provider.instrument_master()}
    chains: dict[datetime.date, list[NormalizedQuote]] = {}
    legs: dict[str, LegMarket] = {}
    liquidity: dict[str, LegLiquidity] = {}
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
        if c.expiry is None or _expired(c.expiry, valuation):
            legs[iid] = LegMarket(iid, lc, None, render_explanation("outcome_why_expired"))
            continue
        if c.expiry not in chains:
            chains[c.expiry] = provider.option_chain_snapshot(underlying, c.expiry)
        quote = next((q for q in chains[c.expiry] if q.instrument_id == iid), None)
        legs[iid] = LegMarket(iid, lc, quote)
        day = provider.latest_day_stats(iid, valuation).stats
        liquidity[iid] = LegLiquidity(provider.latest_depth(iid, valuation), None if day is None else day.last_trade_ts)
    instant = snapshot_instant(valuation, [spot, *(q for chain in chains.values() for q in chain)])
    forwards: dict[datetime.date, ExpiryForward] = {}
    errors: dict[datetime.date, str] = {}
    for expiry, chain in chains.items():
        try:
            forwards[expiry] = _forward(chain, spot, expiry, (instant, rate), (shared, underlying))
        except ForwardUnavailable:
            errors[expiry] = render_explanation("outcome_why_forward")  # the cause goes to no user
    ended: dict[str, datetime.datetime] = {}
    index_id = getattr(provider, "index_id", lambda _u: None)(underlying)
    for iid in [*instrument_ids, *([index_id] if index_id else [])]:
        held = spot if iid == index_id else (legs[iid].quote if iid in legs else None)
        t = provider.last_quote_time(iid) if held is None else None
        if t is not None:
            ended[iid] = t
    return MarketSnapshot(underlying, instant, rate, status, spot, legs, forwards, errors, ended,
                          {expiry: tuple(chain) for expiry, chain in chains.items()}, liquidity)
