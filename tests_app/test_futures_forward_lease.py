"""GC-UI F-3: the Futures tab's "Forward used for pricing" is the forward the builder prices with (ADR-061, D-C33).

RCA: the futures lease held only the futures and the index, so the live chain snapshot (the book of subscribed
contracts) of an expiry no other screen had open held no strikes and ``parity_forward`` answered the spot fallback while
the chain was live. The lease now also holds ``forward_strike_ids`` of every listed option expiry.

Answer states (unchanged in meaning): parity (3+ two-sided strikes held), spot_fallback (fewer), SPOT_MISSING (no
index quote), NOT_PRICEABLE (expired). DB-free: a real FanOut over a provider whose chain is the held contracts only.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.legs import Instrument
from ofo.instruments.models import Contract, ListedContract
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app.live_push import LiveFeed
from ofo_app.routes import leg_picker
from ofo_app.routes.leg_picker import FuturesCatalogue, futures_answer
from ofo_app.routes.outcome import MarketContext

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 28, 11, 0, tzinfo=IST)
EXPIRIES = (datetime.date(2026, 11, 3), datetime.date(2026, 11, 10), datetime.date(2026, 11, 23))
SPOT = Decimal("22800")
STRIKES = [Decimal(22000 + 50 * i) for i in range(33)]  # 22000 .. 23600
INDEX_ID = "NSE:256265"
SRC = SourceMetadata("fake", "fake-feed")
MIN_STRIKES, PER_EXPIRY_MAX = 3, 11


def _lc(token: int, expiry, strike, kind) -> ListedContract:
    return ListedContract(Contract("NFO-OPT", token, "NIFTY", expiry, strike, Decimal("0.05"), 75, kind))


def _master() -> list[ListedContract]:
    out, token = [], 1000
    for e in EXPIRIES:
        for k in STRIKES:
            for kind in ("CE", "PE"):
                out.append(_lc(token, e, k, kind))
                token += 1
    return out


def _quote(lc: ListedContract, ltp: Decimal, two_sided: bool) -> NormalizedQuote:
    c = lc.contract
    return NormalizedQuote(f"{c.exchange_segment}:{c.exchange_token}", "NIFTY", "NFO", "NFO-OPT",
                           Instrument(c.instrument_type), c.expiry, c.strike, ltp,
                           ltp - 1 if two_sided else None, ltp + 1 if two_sided else None, None, None,
                           None, None, None, None, None, None, T0, SRC, DataHealth.AVAILABLE)


class Provider:
    """Quotes exist only for subscribed contracts (the live book's rule); a call/put pair obeys parity to F=SPOT+10."""

    def __init__(self, two_sided: bool = True) -> None:
        self.master = _master()
        self.vendor: set[str] = set()
        self.two_sided = two_sided
        self.index = NormalizedQuote(INDEX_ID, "NIFTY", "NSE", "INDICES", None, None, None, SPOT, None, None, None,
                                     None, None, None, None, None, None, None, T0, SRC, DataHealth.AVAILABLE)

    def live_quote_stream(self, listener) -> None: ...
    def subscribe(self, ids) -> None: self.vendor.update(ids)
    def unsubscribe(self, ids) -> None: self.vendor.difference_update(ids)
    def index_id(self, underlying): return INDEX_ID
    def instrument_master(self): return self.master
    def underlying_quote(self, underlying): return self.index if INDEX_ID in self.vendor else None
    def futures_quote(self, underlying, expiry): return None

    def option_chain_snapshot(self, underlying, expiry):
        out = []
        for lc in self.master:
            c = lc.contract
            iid = f"{c.exchange_segment}:{c.exchange_token}"
            if c.expiry != expiry or iid not in self.vendor:
                continue
            call = max(Decimal(100) + (SPOT + 10 - c.strike), Decimal(2))
            price = Decimal(100) if c.instrument_type == "PE" else call
            out.append(_quote(lc, price, self.two_sided))
        return out


def _feed(provider: Provider) -> LiveFeed:
    return LiveFeed(MarketContext(provider, lambda: T0, Decimal("0")), FanOut(provider))


@pytest.fixture(autouse=True)
def _release():
    yield
    leg_picker.FUTURES_LEASE.release()


CAT = FuturesCatalogue(option_expiries=EXPIRIES, futures=())
KEY = ("owner", "NIFTY", "futures")


def _answer(feed, cat=CAT, at=T0):
    return futures_answer(feed, "NIFTY", cat, lambda: at)


def test_core_every_listed_expiry_is_on_parity_with_no_other_screen_open():
    feed = _feed(Provider())
    _answer(feed)  # the first read opens the lease; the index arrives with it
    out = _answer(feed)
    assert [f.source for f in out.forwards] == ["parity"] * len(EXPIRIES)
    assert all(f.strikes_used >= MIN_STRIKES and f.label is None for f in out.forwards)


def test_lease_holds_forward_strikes_of_each_expiry_and_counts_contracts():
    provider = Provider()
    feed = _feed(provider)
    _answer(feed)
    held = leg_picker.FUTURES_LEASE.ids_of(KEY)
    by_id = {f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}": lc.contract for lc in provider.master}
    for e in EXPIRIES:
        assert len({by_id[i].strike for i in held if i in by_id and by_id[i].expiry == e}) >= MIN_STRIKES
    assert INDEX_ID in held
    assert len(held) <= 1 + PER_EXPIRY_MAX * len(EXPIRIES)  # index + (one leg + 5 strikes x CE/PE) per expiry


def test_fewer_than_three_two_sided_strikes_keep_the_honest_fallback_label():
    feed = _feed(Provider(two_sided=False))
    _answer(feed)
    out = _answer(feed)
    assert all(f.source == "spot_fallback" and f.label for f in out.forwards)


def test_no_feed_is_spot_missing_and_an_expired_expiry_is_not_priceable():
    assert _answer(None).forwards[0].reason == "SPOT_MISSING"
    late = datetime.datetime(2026, 11, 4, 16, tzinfo=IST)
    provider = Provider()
    feed = LiveFeed(MarketContext(provider, lambda: late, Decimal("0")), FanOut(provider))  # the context clock rules
    one = FuturesCatalogue(option_expiries=(EXPIRIES[0],), futures=())
    _answer(feed, one, late)
    assert _answer(feed, one, late).forwards[0].reason == "NOT_PRICEABLE"


def test_releasing_the_lease_releases_every_forward_strike():
    provider = Provider()
    feed = _feed(provider)
    _answer(feed)
    assert len(provider.vendor) > 1
    leg_picker.FUTURES_LEASE.release(KEY)
    assert provider.vendor == set()
