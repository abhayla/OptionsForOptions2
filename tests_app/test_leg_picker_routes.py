"""REQ-080 (W-147 backend): the leg picker's strikes, futures and depth reads.

No database, no server, no Kite: a fake provider behind the REAL shared ``FanOut`` and ``LiveFeed``, a fake stored
catalogue, and the app's door through ``TestClient`` with every seam overridden.

Hand figures (the same recorded 2026-10-08 09:20:09 IST NIFTY quotes as ``tests/engine/test_chain_values.py``, worked
out independently with a separate Black-Scholes): spot 22,533.25, expiry 2026-10-13, r 0.065, spot-fallback forward
(two priced strikes): 22500 CE LTP 151.30 -> IV 11.344 %, delta 0.573009; 22550 PE LTP 145.10 -> IV 13.652 %, delta
-0.492031. The catalogue grid is 22450..22600 in steps of 50: 22533.25 is 16.75 from 22550 and 33.25 from 22500, so
ATM = 22550.
"""
from __future__ import annotations

import ast
import asyncio
import datetime
import math
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.executable_price import Depth, DepthLevel
from ofo.engine.legs import Instrument
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.kite_frames import DayStats
from ofo.marketdata.provider import NotSupported, ProviderStatus
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app import chain_push
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import ChainCatalogue
from ofo_app.live_push import LiveFeed
from ofo_app.routes import leg_picker
from ofo_app.routes.leg_picker import (
    FuturesCatalogue,
    depth_answer,
    futures_answer,
    strikes_answer,
)
from ofo_app.routes.outcome import MarketContext

D = Decimal
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 13)
NEXT_EXPIRY = datetime.date(2026, 10, 20)
FAR_EXPIRY = datetime.date(2026, 11, 24)
NIFTY_ID = "NSE_INDEX:256265"
RATE = D("0.065")
GRID = [D(s) for s in (22450, 22500, 22550, 22600)]
HTTP_OK, HTTP_UNPROCESSABLE = 200, 422
PRICES = {("22500", "CE"): ("151.30", 3218475), ("22550", "PE"): ("145.10", 4022200)}


def _contract(token: int, kind: str, strike: D | None, expiry: datetime.date = EXPIRY) -> PickableContract:
    return PickableContract(contract_id=token, instrument_id=f"NSE_FO:{token}", exchange_segment="NSE_FO",
                            exchange_token=token, instrument_type=kind, expiry=expiry, strike=strike, lot_size=65,
                            symbol=f"NIFTY{expiry:%y%b}{strike or ''}{kind}".upper())


def contracts_for(grid: list[D], expiry: datetime.date = EXPIRY, base: int = 44000) -> tuple[PickableContract, ...]:
    return tuple(_contract(base + 2 * i + j, kind, strike, expiry)
                 for i, strike in enumerate(grid) for j, kind in enumerate(("CE", "PE")))


CONTRACTS = contracts_for(GRID)


def cid(strike: str, kind: str, contracts=CONTRACTS) -> str:
    return next(c.instrument_id for c in contracts if c.strike == D(strike) and c.instrument_type == kind)


def catalogue(contracts=CONTRACTS, expiries=(EXPIRY,), **kw) -> ChainCatalogue:
    return ChainCatalogue(tuple(expiries), tuple(contracts), **kw)


def quote(instrument_id: str, kind: Instrument | None, strike: D | None, ltp: str, *, oi: int | None = 1000,
          health: DataHealth = DataHealth.AVAILABLE, bid: str | None = None, ask: str | None = None,
          expiry: datetime.date | None = EXPIRY) -> NormalizedQuote:
    return NormalizedQuote(instrument_id, "NIFTY", "NSE", "NSE_FO" if kind else "INDICES", kind,
                           expiry if kind else None, strike, D(ltp), None if bid is None else D(bid),
                           None if ask is None else D(ask), 500, oi if kind else None, None, None, None, None, None, None,
                           T0, SourceMetadata("fake", "fake-feed"), health)


class FakeProvider:
    def __init__(self) -> None:
        self.quotes: dict[str, NormalizedQuote] = {}
        self.vendor_subscribed: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.unknown: set[str] = set()
        self.status_value = ProviderStatus(DataHealth.AVAILABLE, True, False)
        self.depths: dict[str, Depth] = {}
        self.stats: dict[str, DayStats] = {}
        self.futures: dict[datetime.date, NormalizedQuote] = {}
        self.futures_offered = True
        self._listener = None

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        if any(i in self.unknown for i in ids):
            raise KeyError("unknown")
        self.subscribe_calls.append(list(ids))
        self.vendor_subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.vendor_subscribed.difference_update(ids)

    def index_id(self, underlying: str) -> str | None:
        return NIFTY_ID if underlying == "NIFTY" else None

    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        return self.quotes.get(NIFTY_ID) if underlying == "NIFTY" else None

    def option_chain_snapshot(self, underlying: str, expiry: datetime.date) -> list[NormalizedQuote]:
        return [q for q in self.quotes.values() if q.underlying == underlying and q.expiry == expiry]

    def status(self) -> ProviderStatus:
        return self.status_value

    def futures_quote(self, underlying: str, expiry: datetime.date) -> NormalizedQuote | None:
        if not self.futures_offered:
            raise NotSupported("no futures quotes")
        return self.futures.get(expiry)

    def latest_depth(self, instrument_id: str, now=None) -> Depth | None:
        return self.depths.get(instrument_id)

    def latest_day_stats(self, instrument_id: str, now=None) -> DayStats | None:
        return self.stats.get(instrument_id)


def make_feed(provider: FakeProvider | None = None) -> tuple[FakeProvider, LiveFeed]:
    provider = provider or FakeProvider()
    return provider, LiveFeed(MarketContext(provider, lambda: T0, RATE), FanOut(provider))


def priced_provider(spot_health: DataHealth = DataHealth.AVAILABLE, contracts=CONTRACTS):
    provider, feed = make_feed()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "22533.25", health=spot_health)
    for (strike, kind), (ltp, oi) in PRICES.items():
        c = cid(strike, kind, contracts)
        provider.quotes[c] = quote(c, Instrument(kind), D(strike), ltp, oi=oi)
    return provider, feed


@pytest.fixture(autouse=True)
def _release_lease():
    yield
    leg_picker.LEASE.release()


def answer(feed, width: int = 10, cat: ChainCatalogue | None = None, expiry=EXPIRY):
    return strikes_answer(feed, "NIFTY", expiry, width, cat or catalogue(), lambda: T0)


def cells(out) -> list:
    return [c for r in out.rows for c in (r.ce, r.pe) if c is not None]


def test_core_the_strikes_read_gives_feed_prices_and_engine_iv_and_delta_for_recorded_nifty_strikes():
    """AC-1/AC-2: the core. Strikes around the ATM, ATM marked; LTP and OI from the feed; IV and delta from the engine
    equal the independent hand figures; a strike without a price is null."""
    _, feed = priced_provider()
    out = answer(feed)
    assert [r.strike for r in out.rows] == [D("22450.00"), D("22500.00"), D("22550.00"), D("22600.00")]
    assert [r.is_atm for r in out.rows] == [False, False, True, False] and out.atm_strike == D("22550.00")
    ce = out.rows[1].ce
    assert (ce.ltp, ce.oi, ce.lot_size, ce.health) == (D("151.30"), 3218475, 65, "available")
    assert abs(ce.iv_percent - D("11.344")) <= D("0.01") and abs(ce.delta - D("0.573009")) <= D("0.0001")
    pe = out.rows[2].pe
    assert (pe.ltp, pe.oi) == (D("145.10"), 4022200)
    assert abs(pe.iv_percent - D("13.652")) <= D("0.01") and abs(pe.delta - D("-0.492031")) <= D("0.0001")
    assert out.rows[0].ce.ltp is None and out.rows[0].ce.iv_percent is None and out.rows[0].ce.delta is None


def test_ac_5_a_missing_quote_is_a_null_cell_with_the_list_reason_and_other_strikes_stay_priced():
    """AC-5 (attack 1): contracts without a quote read null and the list says so; the priced ones stay priced."""
    _, feed = priced_provider()
    out = answer(feed)
    assert out.state == "LIVE" and out.reason == "SOME_PRICES_MISSING"
    assert [c.ltp for c in cells(out) if c.ltp is not None] == [D("151.30"), D("145.10")]
    assert sum(c.health == "unavailable" for c in cells(out)) == 6  # 8 cells, 2 quotes


def test_ac_5_no_quote_at_all_is_waiting_for_prices_not_an_empty_list():
    """AC-5: strikes are listed with null prices and the one reason, never an empty table."""
    provider, feed = make_feed()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "22533.25")
    out = answer(feed)
    assert len(out.rows) == 4 and out.reason == "WAITING_FOR_PRICES" and all(c.ltp is None for c in cells(out))


@pytest.mark.parametrize("health", [DataHealth.STALE, DataHealth.DELAYED, DataHealth.UNHEALTHY])
def test_ac_5_a_stale_spot_gives_the_stale_reason_and_no_engine_values_as_current(health):
    """AC-5 (attack 2, ADR-015): the index is not AVAILABLE -> reason FEED_STALE and no IV or delta anywhere (the engine
    never prices on a stale index); each LTP still follows its own quote's health."""
    _, feed = priced_provider(spot_health=health)
    out = answer(feed)
    assert out.reason == "FEED_STALE" and out.rows
    assert all(c.iv_percent is None and c.delta is None for c in cells(out))


@pytest.mark.parametrize("health", [DataHealth.STALE, DataHealth.DELAYED, DataHealth.UNHEALTHY, DataHealth.UNAVAILABLE])
def test_ac_5_a_stale_option_quote_is_a_null_cell_and_carries_its_health(health):
    """AC-5 (attack 2): one option quote not AVAILABLE -> that cell has no LTP, OI, IV or delta; health says why."""
    provider, feed = priced_provider()
    c = cid("22500", "CE")
    provider.quotes[c] = quote(c, Instrument.CE, D("22500"), "151.30", health=health)
    cell = answer(feed).rows[1].ce
    assert (cell.ltp, cell.oi, cell.iv_percent, cell.delta, cell.health) == (None, None, None, None, health.value)


def test_ac_2_a_zero_price_is_null_never_rupees_zero():
    """AC-2: an exchange 0 ('no trade yet') is not a price."""
    provider, feed = priced_provider()
    c = cid("22500", "CE")
    provider.quotes[c] = quote(c, Instrument.CE, D("22500"), "0")
    cell = answer(feed).rows[1].ce
    assert cell.ltp is None and cell.iv_percent is None and cell.delta is None


def test_ac_5_no_feed_is_not_connected_with_no_rows_and_no_number():
    """AC-5: no Zerodha session -> NOT_LIVE / NOT_CONNECTED, no rows, no spot."""
    out = answer(None)
    assert (out.state, out.reason, out.rows, out.spot, out.atm_strike) == ("NOT_LIVE", "NOT_CONNECTED", [], None, None)


def test_ac_5_no_live_spot_gives_no_rows_and_no_guessed_atm_and_holds_nothing():
    """AC-5: without the index price there is no window to centre: reason SPOT_MISSING and nothing subscribed."""
    provider, feed = make_feed()
    out = answer(feed)
    assert (out.reason, out.rows, out.atm_strike) == ("SPOT_MISSING", [], None) and not provider.vendor_subscribed
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "0")
    assert answer(feed).reason == "SPOT_MISSING"


@pytest.mark.parametrize(("cat", "reason"), [
    (ChainCatalogue((), (), unreadable=True), "CATALOGUE_UNREADABLE"),
    (ChainCatalogue((), ()), "CATALOGUE_EMPTY"),
    (ChainCatalogue((NEXT_EXPIRY,), CONTRACTS), "EXPIRY_UNKNOWN")])
def test_ac_5_every_catalogue_answer_state_has_its_reason_and_no_rows(cat, reason):
    """AC-5: unreadable, empty, expiry not listed: no rows, the named reason, nothing subscribed."""
    provider, feed = priced_provider()
    out = answer(feed, cat=cat)
    assert (out.reason, out.rows) == (reason, []) and not provider.vendor_subscribed


def test_ac_1_width_40_subscribes_exactly_the_strikes_asked_for_and_reading_twice_does_not_grow_it():
    """AC-1 (attack 7): a 100-strike grid with width 40 holds 81 strikes x CE/PE + the index; the same read again
    makes no new vendor call; a smaller width then releases what the window no longer needs."""
    grid = [D(22000 + 50 * i) for i in range(100)]
    contracts = contracts_for(grid)
    provider, feed = make_feed()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "24533.25")  # 24533.25: ATM 24550 = index 51
    cat = catalogue(contracts)
    first = answer(feed, 40, cat)
    assert len(first.rows) == 81 and first.atm_strike == D("24550.00")
    expected = 81 * 2 + 1
    assert len(provider.vendor_subscribed) == expected and feed.fanout.subscriber_count(NIFTY_ID) == 1
    calls = len(provider.subscribe_calls)
    for _ in range(3):
        answer(feed, 40, cat)
    assert len(provider.vendor_subscribed) == expected and len(provider.subscribe_calls) == calls
    answer(feed, 10, cat)
    assert len(provider.vendor_subscribed) == 21 * 2 + 1
    assert feed.fanout.subscriber_count(NIFTY_ID) == 1  # the shared index was never dropped and added twice


def test_ac_1_a_new_window_is_taken_before_the_old_is_released():
    """AC-1: widening to 20 keeps every contract of width 10 held through the change (no vendor unsubscribe of them)."""
    grid = [D(22000 + 50 * i) for i in range(100)]
    contracts = contracts_for(grid)
    provider, feed = make_feed()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "24533.25")
    answer(feed, 10, catalogue(contracts))
    narrow = set(provider.vendor_subscribed)
    dropped: list[set[str]] = []
    original = provider.unsubscribe
    provider.unsubscribe = lambda ids: (dropped.append(set(ids)), original(ids))[1]
    answer(feed, 20, catalogue(contracts))
    assert narrow <= provider.vendor_subscribed and not any(d & narrow for d in dropped)


def test_ac_1_the_lease_ends_after_its_seconds_and_a_reader_in_between_renews_it(monkeypatch):
    """AC-1: no read for LEASE_SECONDS releases the window (nothing is held for ever)."""
    monkeypatch.setattr(leg_picker, "LEASE_SECONDS", 0.05)

    async def scenario() -> tuple[int, int]:
        provider, feed = priced_provider()
        answer(feed)
        await asyncio.sleep(0.03)
        answer(feed)  # renews
        await asyncio.sleep(0.03)
        alive = len(provider.vendor_subscribed)
        await asyncio.sleep(0.08)
        return alive, len(provider.vendor_subscribed)

    alive, after = asyncio.run(scenario())
    assert alive == 9 and after == 0


def test_ac_5_an_unknown_contract_is_one_unavailable_cell_and_the_rest_still_stream():
    """AC-5 (answer state: instrument not found): the provider does not know one contract -> that cell null, the rest
    of the window held and priced."""
    provider, feed = priced_provider()
    bad = cid("22450", "PE")
    provider.unknown.add(bad)
    out = answer(feed)
    assert out.rows[0].pe.health == "unavailable" and out.rows[1].ce.ltp == D("151.30")
    assert bad not in provider.vendor_subscribed and cid("22500", "CE") in provider.vendor_subscribed
    assert feed.fanout.subscriber_count(cid("22500", "CE")) == 1  # the single-id probes were released


def test_ac_5_a_price_the_lease_does_not_hold_is_not_live():
    """AC-5 (liveness from the holder): a quote sitting in the book for a contract the picker does not hold is not
    shown; here the lease holds a different expiry's window."""
    provider, feed = priced_provider()
    other = contracts_for(GRID, NEXT_EXPIRY, 45000)
    for c in other:
        provider.quotes[c.instrument_id] = quote(c.instrument_id, Instrument(c.instrument_type), c.strike, "90.00",
                                                 expiry=NEXT_EXPIRY)
    both = ChainCatalogue((EXPIRY, NEXT_EXPIRY), CONTRACTS + other)
    out = answer(feed, cat=ChainCatalogue((EXPIRY, NEXT_EXPIRY), other), expiry=NEXT_EXPIRY)
    assert out.reason is None and all(c.ltp == D("90.00") for c in cells(out))
    provider.vendor_subscribed.clear()  # nothing streams any more: the book still has the old quotes
    leg_picker.LEASE.release()
    leg_picker.LEASE._lease = None
    # the same read after the lease is gone re-holds; a read that cannot hold anything shows no price
    provider.unknown.update(c.instrument_id for c in both.contracts)
    out = answer(feed, cat=ChainCatalogue((EXPIRY, NEXT_EXPIRY), other), expiry=NEXT_EXPIRY)
    assert all(c.ltp is None for c in cells(out))


# ---- AC-6 futures and forward ----------------------------------------------------------------------------------------

FUT = _contract(46000, "FUT", None, FAR_EXPIRY)


def futures_catalogue() -> FuturesCatalogue:
    return FuturesCatalogue((EXPIRY, NEXT_EXPIRY), (FUT,))


def test_ac_6_every_option_expiry_names_its_forward_and_which_one_was_used_and_futures_list_their_ltp():
    """AC-6: spot-fallback forward (no chain quotes held for the expiry), labelled; the future's LTP is shown."""
    provider, feed = priced_provider()
    provider.futures[FAR_EXPIRY] = quote(FUT.instrument_id, Instrument.FUT, None, "22611.40", expiry=FAR_EXPIRY)
    out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
    assert out.state == "LIVE" and out.reason is None and out.spot == D("22533.25")
    assert [(f.expiry, f.ltp, f.ltp_reason, f.lot_size) for f in out.futures] == [(FAR_EXPIRY, D("22611.40"), None, 65)]
    assert [f.expiry for f in out.forwards] == [EXPIRY, NEXT_EXPIRY]
    # hand: spot x e^(r T), T = seconds to 15:30 IST on the expiry / (365 x 86400) = 5.2710... / 365 days
    seconds = (datetime.datetime.combine(EXPIRY, datetime.time(15, 30), IST) - T0).total_seconds()
    expected = 22533.25 * math.exp(0.065 * int(seconds) / (365 * 86400))
    near = out.forwards[0]
    assert near.source == "spot_fallback" and near.strikes_used == 0 and near.reason is None
    assert abs(float(near.forward) - expected) <= 0.01 and near.label is not None  # "estimated from spot"


def test_ac_6_with_three_usable_strikes_the_forward_is_the_parity_one_and_says_parity():
    """AC-6 (attack 5 red case): >= 3 strikes with a bid and an ask on both sides -> parity. Each strike's call-put
    mid difference is (F - K) e^(-r T) for F = 22,600, so the median forward is 22,600."""
    provider, feed = make_feed()
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "22533.25")
    seconds = (datetime.datetime.combine(EXPIRY, datetime.time(15, 30), IST) - T0).total_seconds()
    growth_inverse = math.exp(-0.065 * int(seconds) / (365 * 86400))
    for k in (22500, 22550, 22600):
        diff = round((22600 - k) * growth_inverse, 2)
        c, p = cid(str(k), "CE"), cid(str(k), "PE")
        call_mid, put_mid = 100 + max(diff, 0), 100 + max(-diff, 0)
        provider.quotes[c] = quote(c, Instrument.CE, D(k), f"{call_mid:.2f}", bid=f"{call_mid - 0.05:.2f}",
                                   ask=f"{call_mid + 0.05:.2f}")
        provider.quotes[p] = quote(p, Instrument.PE, D(k), f"{put_mid:.2f}", bid=f"{put_mid - 0.05:.2f}",
                                   ask=f"{put_mid + 0.05:.2f}")
    out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
    near = out.forwards[0]
    assert near.source == "parity" and near.strikes_used == 3 and near.label is None
    assert abs(near.forward - D("22600")) <= D("0.05")
    assert out.forwards[1].source == "spot_fallback"  # the other expiry holds no chain: labelled, never silent


def test_ac_6_futures_quote_not_offered_is_said_not_shown_as_zero():
    """AC-6 (answer state: the provider offers no futures quote): ltp null with NOT_OFFERED; forwards still answer."""
    provider, feed = priced_provider()
    provider.futures_offered = False
    out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
    assert (out.futures[0].ltp, out.futures[0].ltp_reason) == (None, "NOT_OFFERED") and out.forwards[0].forward


def test_ac_6_no_futures_quote_a_stale_one_and_a_zero_one_are_null():
    """AC-6: missing, stale and zero futures quotes are null with NO_QUOTE (a stale one keeps its health word)."""
    provider, feed = priced_provider()
    out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
    assert (out.futures[0].ltp, out.futures[0].ltp_reason) == (None, "NO_QUOTE")
    for health, ltp in ((DataHealth.STALE, "22611.40"), (DataHealth.AVAILABLE, "0")):
        provider.futures[FAR_EXPIRY] = quote(FUT.instrument_id, Instrument.FUT, None, ltp, health=health,
                                             expiry=FAR_EXPIRY)
        out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
        assert (out.futures[0].ltp, out.futures[0].ltp_reason) == (None, "NO_QUOTE")


def test_ac_6_without_a_spot_or_session_or_catalogue_the_forward_is_null_with_a_reason():
    """AC-6: no spot -> forwards null SPOT_MISSING; no feed -> NOT_LIVE; unreadable/empty catalogue named; an expired
    expiry (valuation after its close) is NOT_PRICEABLE, never a raw error."""
    provider, feed = make_feed()
    out = futures_answer(feed, "NIFTY", futures_catalogue(), lambda: T0)
    assert out.reason == "SPOT_MISSING" and [(f.forward, f.reason) for f in out.forwards] == [(None, "SPOT_MISSING")] * 2
    off = futures_answer(None, "NIFTY", futures_catalogue(), lambda: T0)
    assert off.state == "NOT_LIVE" and off.reason == "NOT_CONNECTED" and off.futures[0].ltp_reason == "NOT_LIVE"
    assert futures_answer(None, "NIFTY", FuturesCatalogue((), (), unreadable=True), lambda: T0).reason == (
        "CATALOGUE_UNREADABLE")
    assert futures_answer(None, "NIFTY", FuturesCatalogue((), ()), lambda: T0).reason == "CATALOGUE_EMPTY"
    provider.quotes[NIFTY_ID] = quote(NIFTY_ID, None, None, "22533.25")
    expired = FuturesCatalogue((datetime.date(2026, 10, 7),), ())
    assert futures_answer(feed, "NIFTY", expired, lambda: T0).forwards[0].reason == "NOT_PRICEABLE"


# ---- AC-7 / AC-8 depth ----------------------------------------------------------------------------------------------

def level(price: str, qty: int) -> DepthLevel:
    return DepthLevel(D(price), qty)


def depth_rig():
    provider, feed = priced_provider()
    c = cid("22500", "CE")
    feed.fanout.subscribe(lambda _q: None, [c])  # a strategy socket holds the leg
    provider.depths[c] = Depth(tuple(level(f"{150 - i}.05", 100 * (i + 1)) for i in range(5)),
                               tuple(level(f"{151 + i}.00", 50 * (i + 1)) for i in range(5)))
    provider.stats[c] = DayStats(D("140.00"), D("160.50"), D("120.25"), D("133.10"), 1791444009)
    return provider, feed, c


def test_ac_7_depth_gives_five_levels_each_side_the_days_values_and_the_two_times():
    """AC-7: 5 bid and 5 ask levels with quantities, best first; open/high/low/previous close; last trade time and the
    time the server read the depth."""
    _, feed, c = depth_rig()
    out = depth_answer(feed, c, lambda: T0)
    assert out.state == "AVAILABLE" and out.reason is None
    assert [(lv.price, lv.quantity) for lv in out.bids] == [(D("150.05"), 100), (D("149.05"), 200), (D("148.05"), 300),
                                                            (D("147.05"), 400), (D("146.05"), 500)]
    assert [(lv.price, lv.quantity) for lv in out.asks][0] == (D("151.00"), 50) and len(out.asks) == 5
    assert (out.day_open, out.day_high, out.day_low, out.prev_close) == (D("140.00"), D("160.50"), D("120.25"),
                                                                        D("133.10"))
    assert out.last_trade_at == datetime.datetime.fromtimestamp(1791444009, IST) and out.read_at == T0


def test_ac_7_a_provider_without_day_values_still_gives_depth_with_those_null():
    """AC-7: previous close 'where the data carries it' (F-47): absent -> null, depth still shown."""
    provider, feed, c = depth_rig()
    del provider.stats[c]
    out = depth_answer(feed, c, lambda: T0)
    assert out.state == "AVAILABLE" and (out.day_open, out.prev_close, out.last_trade_at) == (None, None, None)


@pytest.mark.parametrize("case", ["no_feed", "session_ended", "not_connected", "stale", "not_streaming", "no_depth",
                                  "empty"])
def test_ac_8_when_depth_cannot_be_read_it_says_so_with_the_reason_and_never_an_empty_table(case):
    """AC-8 (attack 3): every unreadable state is NOT_AVAILABLE with its reason; the level lists are empty only then."""
    provider, feed, c = depth_rig()
    feed_in = feed
    if case == "no_feed":
        feed_in = None
    elif case == "session_ended":
        provider.status_value = ProviderStatus(DataHealth.UNHEALTHY, False, True)
    elif case == "not_connected":
        provider.status_value = ProviderStatus(DataHealth.UNAVAILABLE, False, False)
    elif case == "stale":
        provider.status_value = ProviderStatus(DataHealth.STALE, True, False)
    elif case == "not_streaming":
        feed_in = make_feed(provider)[1]  # a feed nobody holds the contract on
    elif case == "no_depth":
        del provider.depths[c]  # a quote-only packet: no depth, which is not "no liquidity"
    else:
        provider.depths[c] = Depth((), ())
    out = depth_answer(feed_in, c, lambda: T0)
    reason = {"no_feed": "NO_SESSION", "session_ended": "NO_SESSION", "not_connected": "NO_SESSION",
              "stale": "FEED_STALE", "not_streaming": "NOT_STREAMING", "no_depth": "NO_DEPTH_RECEIVED",
              "empty": "DEPTH_EMPTY"}[case]
    assert (out.state, out.reason, out.bids, out.asks) == ("NOT_AVAILABLE", reason, [], [])
    assert (out.day_open, out.last_trade_at) == (None, None)


def test_ac_8_a_provider_with_no_depth_reader_is_no_depth_received():
    """AC-8: the test replay's provider has no ``latest_depth``: NO_DEPTH_RECEIVED, never an error."""
    provider, feed, c = depth_rig()
    provider.latest_depth = None  # type: ignore[assignment]
    assert depth_answer(feed, c, lambda: T0).reason == "NO_DEPTH_RECEIVED"


# ---- the app's door -------------------------------------------------------------------------------------------------

def _app_client(feed, cat: ChainCatalogue, fut: FuturesCatalogue):
    from ofo_app.main import create_app  # noqa: PLC0415 - built per test, no lifespan (no database)
    from ofo_app.routes import outcome  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    async def reader(_u, _e):
        return cat

    async def futures_reader(_u):
        return fut

    app = create_app()
    app.dependency_overrides[leg_picker.get_feed] = lambda: feed
    app.dependency_overrides[outcome.get_answer_clock] = lambda: (lambda: T0)
    app.dependency_overrides[leg_picker.get_picker_reader] = lambda: reader
    app.dependency_overrides[leg_picker.get_futures_reader] = lambda: futures_reader
    return TestClient(app)


def test_the_three_routes_answer_through_the_door_and_refuse_bad_input():
    """AC-1/AC-7: GET strikes, futures and depth mint their models; width 15, an unlisted width, a bad instrument id
    and an unknown underlying are refused with 422."""
    provider, feed, c = depth_rig()
    client = _app_client(feed, catalogue(), futures_catalogue())
    query = {"underlying": "NIFTY", "expiry": EXPIRY.isoformat()}
    ok = client.get("/api/leg-picker/strikes", params=query)
    assert ok.status_code == HTTP_OK, ok.text
    assert ok.json()["atm_strike"] == "22550.00" and ok.json()["width"] == 10
    assert client.get("/api/leg-picker/strikes", params={**query, "width": "20"}).json()["width"] == 20
    for bad in ("15", "0", "x", "50", "-10"):
        assert client.get("/api/leg-picker/strikes", params={**query, "width": bad}).status_code == HTTP_UNPROCESSABLE
    assert client.get("/api/leg-picker/strikes", params={**query, "underlying": "BANKNIFTY"}).status_code == (
        HTTP_UNPROCESSABLE)
    futures = client.get("/api/leg-picker/futures", params={"underlying": "NIFTY"})
    assert futures.status_code == HTTP_OK and len(futures.json()["forwards"]) == 2
    depth = client.get("/api/leg-picker/depth", params={"instrument_id": c})
    assert depth.status_code == HTTP_OK and depth.json()["state"] == "AVAILABLE" and len(depth.json()["bids"]) == 5
    assert client.get("/api/leg-picker/depth", params={"instrument_id": "nse fo 1"}).status_code == HTTP_UNPROCESSABLE


def test_ac_7_the_picker_has_no_order_route_and_imports_nothing_that_places_an_order():
    """AC-7: only GET routes under /api/leg-picker, and the module imports no order, basket, margin or execute code."""
    assert {(tuple(sorted(r.methods)), r.path) for r in leg_picker.router.routes} == {
        (("GET",), leg_picker.STRIKES_PATH), (("GET",), leg_picker.FUTURES_PATH), (("GET",), leg_picker.DEPTH_PATH)}
    tree = ast.parse(pathlib.Path(leg_picker.__file__).read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    allowed = {"__future__", "asyncio", "datetime", "collections.abc", "dataclasses", "decimal", "typing", "fastapi",
               "pydantic", "sqlalchemy.exc", "ofo.engine.chain_values", "ofo.marketdata.forward",
               "ofo.marketdata.kite_provider", "ofo.marketdata.provider", "ofo.marketdata.quote", "ofo.money",
               "ofo.rules.inputs", "ofo_app.api_models", "ofo_app.catalogue_picker", "ofo_app.chain_push",
               "ofo_app.errors", "ofo_app.live_push", "ofo_app.routes", "ofo_app.routes.outcome",
               "ofo_app.underlying", "ofo_app", "ofo_app.catalogue_picker", "ofo_app.db"}
    assert imported <= allowed, imported - allowed
    forbidden = ("execute", "basket", "margin", "order")
    assert not [m for m in imported if any(w in m.rsplit(".", 1)[-1] for w in forbidden)], imported


def test_the_picker_reuses_the_chain_catalogue_helpers_and_does_not_change_them():
    """AC-2: the helpers it reuses keep their signatures (the chain read and push are unchanged by this row)."""
    assert chain_push.MAX_STRIKES_EACH_SIDE == 15 and leg_picker.WIDTHS == (10, 20, 30, 40)
