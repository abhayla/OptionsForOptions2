"""GC-LIVE 30 Oct 2026: a paper book's Greeks and Decay were `no_iv` for every open book while the market was live.

RCA: the paper routes' market read held only the contracts the book holds, so with no other screen open the index had
no live quote (``snapshot.spot`` None: no forward can be built on it) and the expiry's chain had no call/put pair, so
``paper_decay.solved_iv`` answered None. The outcome push already holds the index and ``forward_strike_ids`` (D-C33,
ADR-061); the paper read did not. Class: every book with an open option while the market is live.

Answer states: index + forward present -> an IV; no live feed (nothing can be held, no index) -> honest ``None``;
leg quote absent -> None; index held by nobody -> the read holds it itself. DB-free: a real FanOut over a provider
whose chain is the held contracts only.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.legs import Instrument
from ofo.instruments.models import Contract, ListedContract
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.provider import MarketDataProvider, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo.tracking import paper, paper_decay
from ofo_app.live_push import LiveFeed
from ofo_app.routes import paper as paper_routes
from ofo_app.routes.outcome import MarketContext

MAX_WAIT_S = 2.5
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 30, 11, 0, tzinfo=IST)
EXPIRY = datetime.date(2026, 11, 3)
SPOT = Decimal("22930")
STRIKES = [Decimal(22000 + 50 * i) for i in range(33)]
INDEX_ID = "NSE:256265"
SRC = SourceMetadata("fake", "fake-feed")


def _lc(token: int, strike, kind) -> ListedContract:
    return ListedContract(Contract("NFO-OPT", token, "NIFTY", EXPIRY, strike, Decimal("0.05"), 65, kind))


def _id(lc: ListedContract) -> str:
    return f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}"


class Provider(MarketDataProvider):
    """Quotes exist only for subscribed contracts (the live book's rule); call/put obey parity to F=SPOT+10."""

    def __init__(self) -> None:
        self.master, token = [], 1000
        for k in STRIKES:
            for kind in ("CE", "PE"):
                self.master.append(_lc(token, k, kind))
                token += 1
        self.vendor: set[str] = set()
        self.index = self._q(INDEX_ID, "INDICES", None, None, None, SPOT)

    @staticmethod
    def _q(iid, seg, kind, expiry, strike, ltp, spread=0):  # noqa: PLR0913
        return NormalizedQuote(iid, "NIFTY", "NSE" if seg == "INDICES" else "NFO", seg, kind, expiry, strike, ltp,
                               ltp - spread if spread else None, ltp + spread if spread else None, None, None, None,
                               None, None, None, None, None, T0, SRC, DataHealth.AVAILABLE)

    def status(self): return ProviderStatus(DataHealth.AVAILABLE, True)
    def historical(self, instrument_id, start, end): return []
    def source_metadata(self): return SRC

    def live_quote_stream(self, listener) -> None: ...
    def subscribe(self, ids) -> None: self.vendor.update(ids)
    def unsubscribe(self, ids) -> None: self.vendor.difference_update(ids)
    def index_id(self, underlying): return INDEX_ID
    def instrument_master(self): return self.master
    def underlying_quote(self, underlying): return self.index if INDEX_ID in self.vendor else None
    def futures_quote(self, underlying, expiry): return None
    def last_quote_time(self, iid): return None

    def option_chain_snapshot(self, underlying, expiry):
        out = []
        for lc in self.master:
            c = lc.contract
            if c.expiry != expiry or _id(lc) not in self.vendor:
                continue
            f = SPOT + 10  # put = 150 + its intrinsic; the call follows by parity (C - P = F - K), both above intrinsic
            put = Decimal(150) + max(c.strike - f, Decimal(0))
            price = put if c.instrument_type == "PE" else put + f - c.strike
            out.append(self._q(_id(lc), "NFO-OPT", Instrument(c.instrument_type), c.expiry, c.strike, price, 1))
        return out


def _rig(hold_legs: bool = True):
    provider = Provider()
    ctx = MarketContext(provider, lambda: T0, Decimal("0.065"))
    feed = LiveFeed(ctx, FanOut(provider))
    legs = [next(_id(lc) for lc in provider.master
                 if lc.contract.strike == k and lc.contract.instrument_type == "CE") for k in (Decimal(22950),
                                                                                                Decimal(23150))]
    nolisten = lambda _q: None  # noqa: E731
    if hold_legs:
        feed.fanout.subscribe(nolisten, legs)  # the book's own hold: the legs only, no other screen open
    return provider, ctx, feed, legs


def _open(snap, key: str) -> paper_decay.OpenContract:
    c = snap.legs[key].contract.contract
    return paper_decay.OpenContract(key, paper_decay.Instrument(c.instrument_type), c.strike, c.expiry, 65,
                                    paper.leg_price(snap, key).price)


async def test_core_a_held_leg_gets_an_iv_when_the_read_holds_the_forward_strikes(monkeypatch):
    monkeypatch.setattr(paper_routes, "FORWARD_WAIT_S", 0.2, raising=False)
    _, ctx, feed, legs = _rig()
    snap = await paper_routes._snapshot(ctx, feed, "NIFTY", legs)
    assert snap.forwards.get(EXPIRY) is not None
    iv = paper_decay.solved_iv(snap, "NIFTY", _open(snap, legs[0]))
    assert iv is not None and iv > 0


async def test_the_forward_hold_is_released_after_the_read(monkeypatch):
    monkeypatch.setattr(paper_routes, "FORWARD_WAIT_S", 0.2, raising=False)
    provider, ctx, feed, legs = _rig()
    await paper_routes._snapshot(ctx, feed, "NIFTY", legs)
    assert provider.vendor == set(legs)


async def test_no_live_feed_means_no_forward_and_an_honest_none():
    _, ctx, _feed, legs = _rig()
    snap = await paper_routes._snapshot(ctx, None, "NIFTY", legs)
    assert snap.spot is None
    assert paper_decay.solved_iv(snap, "NIFTY", _open(snap, legs[0])) is None


async def test_a_leg_with_no_quote_has_no_iv_even_with_the_forward(monkeypatch):
    monkeypatch.setattr(paper_routes, "FORWARD_WAIT_S", 0.2, raising=False)
    _provider, ctx, feed, legs = _rig()
    snap = await paper_routes._snapshot(ctx, feed, "NIFTY", legs)
    open_c = _open(snap, legs[0])
    ghost = paper_decay.OpenContract("NFO-OPT:999999", open_c.instrument, open_c.strike, open_c.expiry, 65, open_c.ltp)
    assert paper_decay.solved_iv(snap, "NIFTY", ghost) is None


async def test_the_read_holds_the_index_itself_so_spot_is_never_the_missing_input(monkeypatch):
    monkeypatch.setattr(paper_routes, "FORWARD_WAIT_S", 0.2, raising=False)
    provider, ctx, feed, legs = _rig()
    assert provider.underlying_quote("NIFTY") is None  # before: nobody holds the index
    snap = await paper_routes._snapshot(ctx, feed, "NIFTY", legs)
    assert snap.spot is not None
    assert paper_decay.solved_iv(snap, "NIFTY", _open(snap, legs[0])) is not None


@pytest.mark.parametrize("n", [0])
async def test_no_legs_no_hold(n):
    provider, ctx, feed, _legs = _rig()
    snap = await paper_routes._snapshot(ctx, feed, "NIFTY", [])
    assert snap.legs == {} and provider.vendor == set(_legs)


async def test_core_f3_a_contract_nobody_holds_is_priced_and_keeps_its_iv_inputs(monkeypatch):
    """GC-LIVE F-3: the priced-hold released the legs before the IV hold re-read, so a leg no other screen holds came
    back with no quote (price_state missing, book PAUSED). Every open contract is priced AND has an IV."""
    monkeypatch.setattr(paper_routes, "FORWARD_WAIT_S", 0.2, raising=False)
    provider, ctx, feed, legs = _rig(hold_legs=False)
    snap = await paper_routes._snapshot(ctx, feed, "NIFTY", legs)
    assert [paper.leg_price(snap, k).state for k in legs] == [paper.LIVE, paper.LIVE]
    assert all(paper_decay.solved_iv(snap, "NIFTY", _open(snap, k)) is not None for k in legs)
    assert provider.vendor == set()  # everything the read held is released


async def test_nobody_holds_and_the_provider_is_cold_after_hours_does_not_wait(monkeypatch):
    """Market closed: the ready check is the display price (last close), so it never waits the full hold."""
    provider, _ctx, feed, legs = _rig(hold_legs=False)
    ctx2 = MarketContext(provider, lambda: datetime.datetime(2026, 10, 31, 11, 0, tzinfo=IST), Decimal("0.065"))
    loop = __import__("asyncio").get_event_loop()
    t0 = loop.time()
    await paper_routes._snapshot(ctx2, feed, "NIFTY", legs)
    assert loop.time() - t0 < MAX_WAIT_S
