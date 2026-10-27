"""W-116 (REQ-029 AC-1/AC-2/AC-4/AC-6/AC-8; REQ-049 AC-2; ADR-077): the Option Chain push and its REST read.

The push-class and REST-function tests run on a fake provider behind the REAL shared ``FanOut``, a fake stored
catalogue and a fake channel minted by the door's ``socket_body``: no database, no server, no Kite. The app-route tests
at the end override every seam of the REST read (context, streaming, clock, catalogue reader), so no database either.

Expected values come from the inputs the tests write, by hand: the catalogue grid is 25000..25400 in steps of 50; a spot
of 25162.30 is 12.30 from 25150 and 37.70 from 25200, so ATM = 25150 and two strikes each side are 25050, 25100, 25150,
25200, 25250. A pushed ``ltp`` is the fake quote's price as a 2-decimal string, ``at`` its time, ``health`` its health.
"""
from __future__ import annotations

import asyncio
import datetime
import itertools
import json
import pathlib
import re
from decimal import Decimal

import pytest
from ofo.engine.legs import Instrument
from ofo.errors import render
from ofo.marketdata.fanout import FanOut
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth
from ofo_app import chain_push
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import (
    ERROR_REPLY_SECONDS,
    ChainCatalogue,
    ChainOut,
    ChainPush,
    ChainRequest,
    atm_strike,
    strike_window,
)
from ofo_app.errors import socket_body
from ofo_app.live_push import MIN_PUSH_INTERVAL, ChannelClosed, LiveFeed
from ofo_app.routes.chain import chain_read
from ofo_app.routes.outcome import MarketContext

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 19, 9, 20, 0, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 27)
NEXT_EXPIRY = datetime.date(2026, 11, 3)
NIFTY_ID = "NSE_INDEX:256265"
GRID = [Decimal(25000 + 50 * i) for i in range(9)]  # 25000 .. 25400
WINDOW_2 = [Decimal(s) for s in ("25050", "25100", "25150", "25200", "25250")]
ERROR = render("user_input_request_invalid").as_dict()
UNSUPPORTED = render("gate_underlying_unsupported", symbol="BANKNIFTY").as_dict()
ONE, TWO, THREE, FIVE, EIGHT = 1, 2, 3, 5, 8  # push / row counts
HTTP_OK, HTTP_UNPROCESSABLE = 200, 422


def contracts_for(expiry: datetime.date, token_base: int) -> tuple[PickableContract, ...]:
    out = []
    for i, strike in enumerate(GRID):
        for j, side in enumerate(("CE", "PE")):
            token = token_base + 2 * i + j
            out.append(PickableContract(contract_id=token, instrument_id=f"NSE_FO:{token}", exchange_segment="NSE_FO",
                                        exchange_token=token, instrument_type=side, expiry=expiry, strike=strike,
                                        lot_size=75, symbol=f"NIFTY{expiry:%y%b}{strike}{side}".upper()))
    return tuple(out)


CONTRACTS = contracts_for(EXPIRY, 40000)
NEXT_CONTRACTS = contracts_for(NEXT_EXPIRY, 50000)


def cid(strike: str, side: str, contracts=CONTRACTS) -> str:
    return next(c.instrument_id for c in contracts if c.strike == Decimal(strike) and c.instrument_type == side)


def index_quote(ltp: str, at: datetime.datetime = T0, health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    return NormalizedQuote(NIFTY_ID, "NIFTY", "NSE", "INDICES", None, None, None, Decimal(ltp), None, None, None, None,
                           None, None, None, None, None, None, at, SourceMetadata("fake", "fake-feed"), health)


def option_quote(instrument_id: str, ltp: str, *, at: datetime.datetime = T0, oi: int = 1000, volume: int = 500,  # noqa: PLR0913
                 health: DataHealth = DataHealth.AVAILABLE, contracts=CONTRACTS, bid: str | None = None,
                 ask: str | None = None) -> NormalizedQuote:
    c = next(c for c in contracts if c.instrument_id == instrument_id)
    return NormalizedQuote(instrument_id, "NIFTY", "NSE", "NSE_FO", Instrument(c.instrument_type), c.expiry, c.strike,
                           Decimal(ltp), None if bid is None else Decimal(bid), None if ask is None else Decimal(ask),
                           volume, oi, None, None, None, None, None, None, at,
                           SourceMetadata("fake", "fake-feed"), health)


class FakeProvider:
    """The provider methods the fan-out and the push use; records every vendor subscribe / unsubscribe call."""

    def __init__(self) -> None:
        self.quotes: dict[str, NormalizedQuote] = {}
        self.vendor_subscribed: set[str] = set()
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.unknown: set[str] = set()
        self._listener = None

    def live_quote_stream(self, listener) -> None:
        self._listener = listener

    def subscribe(self, ids) -> None:
        if any(i in self.unknown for i in ids):
            raise KeyError("unknown")
        self.subscribe_calls.append(list(ids))
        self.vendor_subscribed.update(ids)

    def unsubscribe(self, ids) -> None:
        self.unsubscribe_calls.append(list(ids))
        self.vendor_subscribed.difference_update(ids)

    def index_id(self, underlying: str) -> str | None:
        return NIFTY_ID if underlying == "NIFTY" else None

    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        return self.quotes.get(NIFTY_ID) if underlying == "NIFTY" else None

    def option_chain_snapshot(self, underlying: str, expiry: datetime.date) -> list[NormalizedQuote]:
        return [q for q in self.quotes.values() if q.underlying == underlying and q.expiry == expiry]

    def tick(self, q: NormalizedQuote) -> None:
        self.quotes[q.instrument_id] = q
        if self._listener is not None:
            self._listener(q)


class FakeChannel:
    def __init__(self) -> None:
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def receive(self):
        item = await self.inbound.get()
        if item is ChannelClosed:
            raise ChannelClosed()
        return item

    async def send(self, source) -> None:
        """Minted exactly as the app's door socket mints it, then read back as JSON."""
        self.sent.append(json.loads(bytes(socket_body(source, (ChainOut,)))))


class Clock:
    def __init__(self, start) -> None:
        self.now = start

    def __call__(self):
        return self.now


class Reader:
    def __init__(self, by_expiry: dict | None = None, *, unreadable: bool = False) -> None:
        self.by_expiry = {EXPIRY: CONTRACTS, NEXT_EXPIRY: NEXT_CONTRACTS} if by_expiry is None else by_expiry
        self.unreadable = unreadable
        self.calls: list[tuple[str, datetime.date]] = []

    async def __call__(self, underlying: str, expiry: datetime.date) -> ChainCatalogue:
        self.calls.append((underlying, expiry))
        if self.unreadable:
            return ChainCatalogue(expiries=(), contracts=(), unreadable=True)
        return ChainCatalogue(expiries=tuple(sorted(self.by_expiry)), contracts=self.by_expiry.get(expiry, ()))


def make_rig(reader: Reader | None = None, provider: FakeProvider | None = None, fanout: FanOut | None = None):
    provider = provider or FakeProvider()
    wall = Clock(T0)
    feed = LiveFeed(MarketContext(provider, wall, Decimal("0.065")), fanout or FanOut(provider))
    channel, mono = FakeChannel(), Clock(1000.0)
    push = ChainPush(channel, feed, monotonic=mono, now=wall, reader=reader or Reader(), poll=0.005)
    return provider, feed, channel, mono, push


def request(each_side=2, expiry: datetime.date = EXPIRY) -> dict:
    return {"underlying": "NIFTY", "expiry": expiry.isoformat(), "strikes_each_side": each_side}


async def settle(n: int = 6) -> None:
    for _ in range(n):
        await asyncio.sleep(0.01)


async def start(push, channel, req: dict | None = None):
    task = asyncio.create_task(push.run())
    await channel.inbound.put(request() if req is None else req)
    await settle()
    return task


async def close(channel, task) -> None:
    await channel.inbound.put(ChannelClosed)
    await task


def tick_window(provider, ltp_offset: int = 0, health: DataHealth = DataHealth.AVAILABLE, at=T0) -> None:
    for k, strike in enumerate(WINDOW_2):
        provider.tick(option_quote(cid(str(strike), "CE"), f"{100 + k + ltp_offset}.50", at=at, health=health))
        provider.tick(option_quote(cid(str(strike), "PE"), f"{200 + k + ltp_offset}.25", at=at, health=health))


async def test_ac1_core_two_pushes_for_a_five_strike_chain_with_changing_ltps_and_per_cell_health():
    """AC-1 (core proof): a 5-strike chain around ATM reaches the channel as two pushes one second apart, rows by strike
    with the CE and PE cells of each strike, each cell with its quote's own price and health, state LIVE."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    provider.tick(option_quote(cid("25150", "CE"), "131.00", health=DataHealth.STALE))
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(channel.sent) == TWO
    first, second = channel.sent
    assert first["state"] == second["state"] == "LIVE"
    assert [r["strike"] for r in first["rows"]] == ["25050.00", "25100.00", "25150.00", "25200.00", "25250.00"]
    for k, row in enumerate(first["rows"]):
        assert row["ce"]["instrument_id"] == cid(row["strike"], "CE") and row["ce"]["ltp"] == f"{100 + k}.50"
        assert row["pe"]["instrument_id"] == cid(row["strike"], "PE") and row["pe"]["ltp"] == f"{200 + k}.25"
        assert row["ce"]["health"] == row["pe"]["health"] == "available"
    atm_row = second["rows"][2]
    assert atm_row["ce"] == {"instrument_id": cid("25150", "CE"), "ltp": "131.00", "bid": None, "ask": None,
                             "change": None, "oi": 1000, "oi_change": None, "volume": 500, "health": "stale",
                             "at": T0.isoformat(), "permitted": False, "unavailable_reason": "unknown",
                             "iv": None, "delta": None, "gamma": None, "theta": None, "vega": None}
    assert second["rows"][2]["pe"]["health"] == "available"


async def test_ac2_default_columns_present_and_change_null_without_a_previous_close():
    """AC-2/AC-3/AC-4: each cell carries exactly LTP, bid/ask, Change, OI (+ change), Volume, the engine's IV and
    Greeks (row 33) plus id, health, time; the feed has no previous close, so change is null on every cell."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    await close(channel, task)
    cells = [row[s] for row in channel.sent[0]["rows"] for s in ("ce", "pe")]
    assert {frozenset(c) for c in cells} == {frozenset({"instrument_id", "ltp", "bid", "ask", "change", "oi",
                                                        "oi_change", "volume", "health", "at", "permitted",
                                                        "unavailable_reason", "iv", "delta", "gamma", "theta",
                                                        "vega"})}
    assert [c["change"] for c in cells] == [None] * 10
    assert set(channel.sent[0]) == {"state", "underlying", "expiry", "spot", "spot_at", "spot_health", "atm_strike",
                                    "rows_missing", "rows", "answered_at", "market_closed", "last_price_at",
                                    "greeks_basis", "greeks_missing"}


async def test_ac4_at_most_one_push_a_second_and_none_without_a_change():
    """AC-4: LTPs change every 0.2 s for 2 s: at most one push per second; then 2 s with no change: no push."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    for step in range(10):
        tick_window(provider, ltp_offset=step + 1)
        mono.now += 0.2
        await settle(2)
    pushed = len(channel.sent)
    for _ in range(10):
        mono.now += 0.2
        await settle(2)
    await close(channel, task)
    assert pushed == THREE  # t=0 (first), t=1.0, t=2.0: hand count of 1 s gates over 2 s
    assert len(channel.sent) == pushed  # the t=2.0 push carried the last tick; 2 quiet seconds push nothing
    assert channel.sent[-1]["rows"][0]["ce"]["ltp"] == "110.50"  # the last tick (offset 10) was the one pushed


async def test_ac4_requests_are_applied_at_most_once_a_second_latest_wins():
    """AC-4 / threat model (push storm): three different requests inside one second read the catalogue once at once,
    then once for the latest a second later; the middle one is never read or subscribed."""
    reader = Reader()
    provider, _feed, channel, mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel, request(2))
    await channel.inbound.put(request(3))
    await channel.inbound.put(request(4))
    await settle()
    assert reader.calls == [("NIFTY", EXPIRY)]
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(reader.calls) == TWO
    assert len(provider.subscribe_calls) == TWO  # 5 strikes, then 9 (4 each side): never 7
    assert len(channel.sent[-1]["rows"]) == EIGHT  # 4 each side of 25150: only 3 below it on the grid (25000..25350)


@pytest.mark.parametrize(("spot", "atm"), [("25162.30", "25150.00"), ("25175", "25150.00"), ("25175.01", "25200.00"),
                                           ("24000", "25000.00"), ("26000", "25400.00")])
async def test_ac8_atm_is_the_catalogue_strike_nearest_the_spot(spot, atm):
    """AC-8: the ATM strike is the grid strike nearest the live spot (a tie at 25175 takes the lower, 25150), the spot
    is shown, and the rows are centred on it (fewer at the grid's ends)."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote(spot))
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert body["atm_strike"] == atm and body["spot"] == f"{Decimal(spot):.2f}"
    assert body["spot_health"] == "available" and body["spot_at"] == T0.isoformat()
    strikes = [Decimal(r["strike"]) for r in body["rows"]]
    i = GRID.index(Decimal(atm))
    assert strikes == GRID[max(0, i - 2): i + 3]


def test_ac8_pure_atm_and_window_on_the_grid():
    """AC-8: the helpers on the grid itself; a window outside 1..15 is refused."""
    assert atm_strike(GRID, Decimal("25124.99")) == Decimal("25100")
    assert atm_strike(GRID, Decimal("25125")) == Decimal("25100")
    assert list(strike_window(GRID, Decimal("25000"), 1)) == [Decimal("25000"), Decimal("25050")]
    for bad in (0, 16):
        with pytest.raises(ValueError):
            strike_window(GRID, Decimal("25000"), bad)


@pytest.mark.parametrize("health", list(DataHealth))
async def test_ac2_each_cell_carries_its_quotes_own_health(health):
    """REQ-049 AC-2: each of the five health states reaches its cell as the quote gave it, never upgraded."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider, health=health)
    task = await start(push, channel)
    await close(channel, task)
    assert {row[s]["health"] for row in channel.sent[0]["rows"] for s in ("ce", "pe")} == {health.value}


async def test_ac2_a_held_contract_without_a_quote_reads_unavailable():
    """REQ-049 AC-2: a subscribed contract with no quote yet is shown unavailable with no number."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    await close(channel, task)
    assert channel.sent[0]["rows"][0]["ce"] == {"instrument_id": cid("25050", "CE"), "ltp": None, "bid": None,
                                                "ask": None, "change": None, "oi": None, "oi_change": None,
                                                "volume": None, "health": "unavailable", "at": None,
                                                    "permitted": False, "unavailable_reason": "unknown",
                                                "iv": None, "delta": None, "gamma": None, "theta": None, "vega": None}


@pytest.mark.parametrize("bad", [0, 16, -1, "x", "5", True, 2.0, None])
async def test_strikes_each_side_out_of_range_is_refused(bad):
    """Threat model (unbounded strike range): 0, 16, -1, 'x', a numeric string, a bool, a float and null are refused
    with the one input message, and nothing is subscribed or read."""
    reader = Reader()
    provider, _feed, channel, _mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel, request(bad))
    await close(channel, task)
    assert channel.sent == [ERROR]
    assert reader.calls == [] and provider.subscribe_calls == []


@pytest.mark.parametrize("raw", [{**request(), "fallback": True}, {**request(), "extra": 1}, {"underlying": "BANKNIFTY",
                                 "expiry": EXPIRY.isoformat()}, "text"])
async def test_unreadable_requests_are_refused(raw):
    """Threat model: the REST fallback flag, an unknown key, an unknown underlying or a non-object are refused."""
    provider, _feed, channel, _mono, push = make_rig()
    task = await start(push, channel, raw)
    await close(channel, task)
    unsupported = isinstance(raw, dict) and raw.get("underlying") == "BANKNIFTY"
    assert channel.sent == [UNSUPPORTED if unsupported else ERROR] and provider.subscribe_calls == []


async def test_expiry_change_releases_the_old_contracts_and_keeps_the_index_held():
    """Threat model (leaked subscription on an expiry change): the new expiry's contracts are taken BEFORE the old are
    released; afterwards every old contract has 0 subscribers, the index 1, and the index was never unsubscribed."""
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    old_ids = [cid(str(s), side) for s in WINDOW_2 for side in ("CE", "PE")]
    assert all(feed.fanout.subscriber_count(i) == ONE for i in old_ids)
    mono.now += 1.0
    await channel.inbound.put(request(expiry=NEXT_EXPIRY))
    await settle()
    new_ids = [cid(str(s), side, NEXT_CONTRACTS) for s in WINDOW_2 for side in ("CE", "PE")]
    assert [feed.fanout.subscriber_count(i) for i in old_ids] == [0] * 10
    assert [feed.fanout.subscriber_count(i) for i in new_ids] == [1] * 10
    assert feed.fanout.subscriber_count(NIFTY_ID) == ONE
    assert all(NIFTY_ID not in call for call in provider.unsubscribe_calls)
    assert provider.unsubscribe_calls == [old_ids]
    await close(channel, task)
    assert channel.sent[-1]["expiry"] == NEXT_EXPIRY.isoformat()


async def test_close_releases_everything():
    """Threat model (leaked subscription after disconnect): on close every contract and the index has 0 subscribers
    and the vendor holds nothing."""
    provider, feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    assert provider.vendor_subscribed
    await close(channel, task)
    assert provider.vendor_subscribed == set()
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0


async def test_an_unknown_contract_is_one_unavailable_cell_and_the_rest_of_the_window_streams():
    """W-116 round 2 (finding 1): a contract the provider does not know makes THAT cell unavailable instead of failing
    the whole window: the new expiry is taken, its other contracts are held, the old window is released, no error."""
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    unknown = cid("25150", "CE", NEXT_CONTRACTS)
    provider.unknown = {unknown}
    mono.now += 1.0
    await channel.inbound.put(request(expiry=NEXT_EXPIRY))
    await settle()
    counts = {i: feed.fanout.subscriber_count(i) for i in (unknown, cid("25150", "PE", NEXT_CONTRACTS),
                                                           cid("25150", "CE"), NIFTY_ID)}
    await close(channel, task)
    assert counts == {unknown: 0, cid("25150", "PE", NEXT_CONTRACTS): ONE, cid("25150", "CE"): 0, NIFTY_ID: ONE}
    assert ERROR not in channel.sent
    last = channel.sent[-1]
    assert last["expiry"] == NEXT_EXPIRY.isoformat() and last["rows"][2]["ce"]["health"] == "unavailable"


async def test_spot_missing_shows_no_rows_and_no_guessed_atm_then_rows_when_the_spot_arrives():
    """Answer state 'spot missing': LIVE with rows empty and rows_missing SPOT_MISSING, atm null, only the index held;
    once the spot arrives the window is picked and subscribed."""
    provider, feed, channel, mono, push = make_rig()
    task = await start(push, channel)
    first = channel.sent[0]
    assert (first["state"], first["rows"], first["rows_missing"], first["atm_strike"], first["spot"]) == (
        "LIVE", [], "SPOT_MISSING", None, None)
    assert first["spot_health"] == "unavailable" and provider.vendor_subscribed == {NIFTY_ID}
    provider.tick(index_quote("25162.30"))
    mono.now += 1.0
    await settle()
    await close(channel, task)
    last = channel.sent[-1]
    assert last["atm_strike"] == "25150.00" and len(last["rows"]) == FIVE and last["rows_missing"] is None
    assert feed.fanout.subscriber_count(NIFTY_ID) == 0


@pytest.mark.parametrize(("reader", "missing"), [(Reader({NEXT_EXPIRY: NEXT_CONTRACTS}), "EXPIRY_UNKNOWN"),
                                                 (Reader({}), "CATALOGUE_EMPTY"),
                                                 (Reader({EXPIRY: ()}), "CATALOGUE_EMPTY"),
                                                 (Reader(unreadable=True), "CATALOGUE_UNREADABLE")])
async def test_catalogue_answer_states(reader, missing):
    """Answer states: expiry unknown, catalogue empty, catalogue unreadable: no rows, the reason named, no ATM."""
    provider, _feed, channel, _mono, push = make_rig(reader)
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert (body["rows"], body["rows_missing"], body["atm_strike"]) == ([], missing, None)


async def test_no_feed_answers_not_connected_with_no_number():
    """Answer state NOT_CONNECTED (no feed): no rows, no spot, no ATM."""
    channel = FakeChannel()
    push = ChainPush(channel, None, monotonic=Clock(1000.0), now=Clock(T0), reader=Reader(), poll=0.005)
    task = await start(push, channel)
    await close(channel, task)
    assert len(channel.sent) == ONE
    body = channel.sent[0]
    assert (body["state"], body["rows"], body["spot"], body["atm_strike"]) == ("NOT_CONNECTED", [], None, None)


def _catalogue() -> ChainCatalogue:
    return ChainCatalogue(expiries=(EXPIRY, NEXT_EXPIRY), contracts=CONTRACTS)


async def test_two_holders_and_fallback_answer_not_connected():
    """Finding liveness-from-shared-subscribers: another socket holds every contract and the index, yet the REST read
    with fallback=1 (this screen's own socket is down) answers NOT_CONNECTED with no number; without the flag LIVE."""
    provider = FakeProvider()
    fanout = FanOut(provider)
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    _p, feed, channel_a, _m, push_a = make_rig(provider=provider, fanout=fanout)
    _p2, _f2, channel_b, _m2, push_b = make_rig(provider=provider, fanout=fanout)
    task_a, task_b = await start(push_a, channel_a), await start(push_b, channel_b)
    assert fanout.subscriber_count(cid("25150", "CE")) == TWO
    streaming = lambda i: fanout.subscriber_count(i) > 0  # noqa: E731 - outcome.get_streaming's predicate
    streaming.ctx = feed.ctx
    req = ChainRequest.model_validate(request())
    down = chain_read(feed.ctx, streaming, req, _catalogue(), fallback=True, now=Clock(T0))
    up = chain_read(feed.ctx, streaming, req, _catalogue(), fallback=False, now=Clock(T0))
    await close(channel_a, task_a)
    await close(channel_b, task_b)
    assert (down.state, down.rows, down.spot, down.atm_strike) == ("NOT_CONNECTED", [], None, None)
    assert down.spot_at == T0
    assert up.state == "LIVE" and up.atm_strike == Decimal("25150") and len(up.rows) == FIVE


def test_rest_read_without_a_holder_is_not_live():
    """Issue #206's rule: no socket holds the contracts, so the REST read is NOT_CONNECTED."""
    provider = FakeProvider()
    fanout = FanOut(provider)
    provider.tick(index_quote("25162.30"))
    ctx = MarketContext(provider, Clock(T0), Decimal("0.065"))
    streaming = lambda i: fanout.subscriber_count(i) > 0  # noqa: E731
    streaming.ctx = ctx
    body = chain_read(ctx, streaming, ChainRequest.model_validate(request()), _catalogue(), fallback=False,
                      now=Clock(T0))
    assert body.state == "NOT_CONNECTED"


def test_ac6_no_order_basket_margin_or_execute_reachable_from_the_chain_code():
    """AC-6: the chain modules import nothing that places, builds, checks or sends an order."""
    root = pathlib.Path(chain_push.__file__).parent
    for path in (root / "chain_push.py", root / "routes" / "chain.py"):
        imports = re.findall(r"^\s*(?:from|import)\s+([\w.]+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        assert imports, path
        allowed = {"__future__", "asyncio", "contextlib", "datetime", "logging", "time", "collections.abc",
                   "dataclasses", "decimal", "typing", "pydantic", "sqlalchemy.exc", "fastapi", "ofo.errors",
                   "ofo.instruments", "ofo.instruments.eligibility", "ofo_app.eligibility_from_zerodha",
                   "ofo.marketdata.quote", "ofo.money", "ofo_app.api_models", "ofo_app.catalogue_picker",
                   "ofo_app.live_push", "ofo_app.routes.outcome", "ofo_app", "ofo_app.db", "ofo_app.chain_push",
                   "ofo_app.errors", "ofo_app.routes", "ofo_app.underlying",
                   "ofo.engine.chain_values"}  # row 33: the engine's IV/Greeks maths only
        assert set(imports) <= allowed, (path.name, set(imports) - allowed)


def _app_client(ctx: MarketContext | None, reader: Reader):
    from ofo_app.main import create_app  # noqa: PLC0415 - the app is built per test, with no lifespan (no database)
    from ofo_app.routes import chain, outcome  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    app = create_app()
    app.dependency_overrides[outcome.get_market_context] = lambda: ctx
    app.dependency_overrides[outcome.get_streaming] = lambda: None
    app.dependency_overrides[outcome.get_answer_clock] = lambda: Clock(T0)
    app.dependency_overrides[chain.get_chain_reader] = lambda: reader
    return TestClient(app)


def test_rest_route_answers_the_chain_and_refuses_a_bad_strike_count():
    """AC-1/AC-8 through the app's door: GET /api/market/chain answers the chain message; fallback=1 NOT_CONNECTED;
    strikes_each_side 0, 16 and 'x' are refused with the one input message (422)."""
    provider = FakeProvider()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    reader = Reader()
    client = _app_client(MarketContext(provider, Clock(T0), Decimal("0.065")), reader)
    query = {"underlying": "NIFTY", "expiry": EXPIRY.isoformat(), "strikes_each_side": 2}
    ok = client.get("/api/market/chain", params=query)
    assert ok.status_code == HTTP_OK, ok.text
    assert ok.json()["state"] == "LIVE" and ok.json()["atm_strike"] == "25150.00" and len(ok.json()["rows"]) == FIVE
    assert client.get("/api/market/chain", params={**query, "fallback": "1"}).json()["state"] == "NOT_CONNECTED"
    for bad in ("0", "16", "x", "-1"):
        refused = client.get("/api/market/chain", params={**query, "strikes_each_side": bad})
        assert refused.status_code == HTTP_UNPROCESSABLE and refused.json() == ERROR, (bad, refused.text)


def test_the_chain_socket_is_a_door_route():
    """The socket is registered as a door socket route minting only ChainOut (and catalogue messages)."""
    from ofo_app.errors import ClosedWebSocketRoute  # noqa: PLC0415
    from ofo_app.routes import chain  # noqa: PLC0415

    route = chain.socket_route()
    assert isinstance(route, ClosedWebSocketRoute) and route.path == "/api/market/chain/live"
    app_paths = {getattr(r, "path", None) for r in _app_client(None, Reader()).app.routes}
    assert {"/api/market/chain/live", "/api/market/chain"} <= app_paths


async def test_a_connection_holding_nothing_is_never_live():
    """Finding liveness-from-shared-subscribers: a request whose index and contracts the provider cannot name subscribes
    nothing, so this connection holds nothing and the answer is NOT_CONNECTED, never LIVE."""
    provider, _feed, channel, _mono, push = make_rig()
    task = await start(push, channel, {"underlying": "SENSEX", "expiry": EXPIRY.isoformat(), "strikes_each_side": 2})
    await close(channel, task)
    assert provider.subscribe_calls == []
    assert channel.sent[0]["state"] == "NOT_CONNECTED" and channel.sent[0]["rows"] == []


class WrongIndexProvider(FakeProvider):
    def underlying_quote(self, underlying: str) -> NormalizedQuote | None:
        q = self.quotes.get(NIFTY_ID)
        return None if q is None else option_quote(cid("25150", "CE"), "25162.30")


async def test_a_quote_of_another_instrument_is_never_the_spot():
    """AC-8: a provider answering the index with another instrument's quote gives no spot and no ATM (spot missing)."""
    provider = WrongIndexProvider()
    provider.tick(index_quote("25162.30"))
    _p, _feed, channel, _mono, push = make_rig(provider=provider)
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert (body["spot"], body["atm_strike"], body["rows_missing"]) == (None, None, "SPOT_MISSING")


async def test_storm_spot_missing_then_an_unknown_contract_sends_at_most_one_message_a_second():
    """W-116 round 2 (Tier A finding 1, the core proof): the spot is missing when the request is applied, then the
    re-picked window holds a contract the provider does not know while prices change on every loop. Over 30 poll loops
    in each of three seconds at most ONE message leaves; no error is sent; the rows appear once the spot arrives, the
    unknown contract's cell is unavailable with no number and every other contract is held."""
    provider, feed, channel, mono, push = make_rig()
    provider.unknown = {cid("25150", "CE")}
    task = await start(push, channel)
    assert channel.sent[-1]["rows_missing"] == "SPOT_MISSING"
    provider.tick(index_quote("25162.30"))
    per_second = []
    for sec in range(3):
        mono.now += 1.5
        n0 = len(channel.sent)
        for loop in range(30):
            tick_window(provider, ltp_offset=100 * sec + loop + 1)
            await asyncio.sleep(0.01)
        per_second.append(len(channel.sent) - n0)
    held = (feed.fanout.subscriber_count(cid("25150", "CE")), feed.fanout.subscriber_count(cid("25150", "PE")))
    await close(channel, task)
    assert held == (0, ONE)
    assert per_second == [ONE, ONE, ONE]
    assert ERROR not in channel.sent
    last = channel.sent[-1]
    assert [r["strike"] for r in last["rows"]] == ["25050.00", "25100.00", "25150.00", "25200.00", "25250.00"]
    unknown_cell = last["rows"][2]["ce"]
    assert (unknown_cell["health"], unknown_cell["ltp"], unknown_cell["oi"]) == ("unavailable", None, None)
    assert last["rows"][2]["pe"]["ltp"] is not None and last["rows"][2]["pe"]["health"] == "available"


async def test_fifty_invalid_messages_in_a_second_get_at_most_one_reply_a_second():
    """W-116 round 2 (finding 4): invalid client messages pass the same one-a-second gate as every push: 50 inside one
    second get no reply in the second a push already used, then ONE error reply, never 50."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    n0 = len(channel.sent)
    for _ in range(50):
        await channel.inbound.put({"underlying": "NIFTY", "expiry": "x"})
    await settle(20)
    same_second = len(channel.sent) - n0
    mono.now += 1.0
    await settle(20)
    await close(channel, task)
    assert same_second == 0
    assert channel.sent[n0:] == [ERROR]


async def test_bid_and_ask_stream_and_zero_reads_null():
    """REQ-029 AC-4 (bid/ask live), F-29: each cell carries its quote's bid and ask as 2-decimal strings, 0 -> null."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    provider.tick(option_quote(cid("25150", "CE"), "131.00", bid="130.05", ask="130.95"))
    provider.tick(option_quote(cid("25150", "PE"), "90.00", bid="0", ask="0"))
    task = await start(push, channel)
    provider.tick(option_quote(cid("25150", "CE"), "131.00", bid="130.10", ask="131.20"))
    mono.now += 1.0
    await settle()
    await close(channel, task)
    first, second = channel.sent[0]["rows"][2], channel.sent[1]["rows"][2]
    assert (first["ce"]["bid"], first["ce"]["ask"]) == ("130.05", "130.95")
    assert (first["pe"]["bid"], first["pe"]["ask"], first["pe"]["ltp"]) == (None, None, "90.00")
    assert (second["ce"]["bid"], second["ce"]["ask"]) == ("130.10", "131.20")


async def test_oi_refreshes_at_most_every_five_seconds_while_ltp_streams():
    """REQ-029 AC-4 / Q46: an OI change alone inside 5 s is not pushed; an LTP change is pushed at once with the OI
    still as shown; once 5 s have passed the new OI is pushed."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    new_oi = 3000
    provider.tick(option_quote(cid("25150", "CE"), "131.00", oi=1000))
    task = await start(push, channel)
    provider.tick(option_quote(cid("25150", "CE"), "131.00", oi=2000))
    mono.now += 1.0
    await settle()
    oi_only = len(channel.sent)
    provider.tick(option_quote(cid("25150", "CE"), "132.00", oi=new_oi))
    mono.now += 1.0
    await settle()
    ltp_push = channel.sent[-1]["rows"][2]["ce"]
    mono.now += 3.0
    await settle()
    await close(channel, task)
    assert oi_only == ONE
    assert (ltp_push["ltp"], ltp_push["oi"]) == ("132.00", 1000)
    assert len(channel.sent) == THREE and channel.sent[-1]["rows"][2]["ce"]["oi"] == new_oi


async def test_window_re_centres_on_the_live_atm_and_releases_the_old_contracts():
    """W-116 round 2 (finding 3): the spot moves 25162.30 -> 25398; within 5 s the rows hold the new ATM 25400, the old
    contracts below the new window are released, the index stays held and was never unsubscribed."""
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    task = await start(push, channel)
    provider.tick(index_quote("25398.00"))
    mono.now += 5.0
    await settle()
    old = [cid(s, side) for s in ("25050", "25100", "25150", "25200", "25250") for side in ("CE", "PE")]
    old_counts = [feed.fanout.subscriber_count(i) for i in old]
    new_count = feed.fanout.subscriber_count(cid("25400", "CE"))
    index_count = feed.fanout.subscriber_count(NIFTY_ID)
    index_dropped = any(NIFTY_ID in call for call in provider.unsubscribe_calls)
    await close(channel, task)
    last = channel.sent[-1]
    assert last["atm_strike"] == "25400.00"
    assert [r["strike"] for r in last["rows"]] == ["25300.00", "25350.00", "25400.00"]
    assert old_counts == [0] * 10 and new_count == ONE and index_count == ONE
    assert not index_dropped


def _timed(channel, mono) -> list[float]:
    """Record the monotonic time of every message the channel sends (the one gate's own clock)."""
    times: list[float] = []
    send = channel.send

    async def timed_send(source) -> None:
        times.append(mono.now)
        await send(source)

    channel.send = timed_send
    return times


async def test_an_invalid_message_every_second_never_starves_the_data_pushes():
    """#439 item 1 (finding rate-gate-on-success-path-only, side effect): a client sending an invalid message every
    1.0 s for 20 s while quotes change still gets its data pushes (a pending push takes the gate before a pending error
    reply), and still never two messages less than 1 s apart. Red on the error-first gate: 0 data pushes."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    times = _timed(channel, mono)
    task = await start(push, channel)
    n0 = len(channel.sent)
    for sec in range(20):
        await channel.inbound.put({"underlying": "NIFTY", "expiry": "x"})
        tick_window(provider, ltp_offset=sec + 1)
        mono.now += 1.0
        await settle(3)
    await close(channel, task)
    sent = channel.sent[n0:]
    data = [m for m in sent if m != ERROR]
    # hand count: 20 slots; an error reply takes a slot only after waiting ERROR_REPLY_SECONDS and at most once every
    # ERROR_REPLY_SECONDS, so at most 20 // 5 = 4 slots go to errors and >= 16 to pushes (an error-first gate: 0 pushes)
    assert len(data) >= 20 - 20 // ERROR_REPLY_SECONDS
    assert 1 <= sent.count(ERROR) <= 20 // ERROR_REPLY_SECONDS
    assert all(b - a >= MIN_PUSH_INTERVAL for a, b in itertools.pairwise(times))


async def test_one_invalid_message_under_changing_quotes_still_gets_its_error_reply():
    """#439 fix round 2 (verifier case E): ONE invalid message while quotes change every second for 30 s. Red on the
    push-always-first gate: 30 pushes, 0 error replies (the reply deferred forever). The aged-error rule sends exactly
    one reply between 5 s and 7 s after the message, the pushes keep >= 28 slots, never two messages within 1 s."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    times = _timed(channel, mono)
    task = await start(push, channel)
    n0 = len(channel.sent)
    sent_at = mono.now
    await channel.inbound.put({"underlying": "NIFTY", "expiry": "x"})
    for sec in range(30):
        tick_window(provider, ltp_offset=sec + 1)
        mono.now += 1.0
        await settle(3)
    await close(channel, task)
    sent = channel.sent[n0:]
    error_times = [t for t, m in zip(times[n0:], sent, strict=True) if m == ERROR]
    assert len(error_times) == 1
    assert ERROR_REPLY_SECONDS <= error_times[0] - sent_at <= ERROR_REPLY_SECONDS + 2
    assert len(sent) - 1 >= 28  # noqa: PLR2004
    assert all(b - a >= MIN_PUSH_INTERVAL for a, b in itertools.pairwise(times))


async def test_invalid_messages_with_no_data_change_get_at_most_one_error_every_five_seconds():
    """#439 item 1: error replies are coalesced - an invalid message every second for 20 s with nothing new to push gets
    at most one error reply per ERROR_REPLY_SECONDS (never one per message), and at least one reply."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    times = _timed(channel, mono)
    task = await start(push, channel)
    n0 = len(channel.sent)
    for _ in range(20):
        await channel.inbound.put({"underlying": "NIFTY", "expiry": "x"})
        mono.now += 1.0
        await settle(3)
    await close(channel, task)
    sent = channel.sent[n0:]
    error_times = [t for t, m in zip(times[n0:], sent, strict=True) if m == ERROR]
    assert sent == [ERROR] * len(error_times)
    assert 1 <= len(error_times) <= 20 // ERROR_REPLY_SECONDS  # at most 4 in 20 s, never 20
    assert all(b - a >= ERROR_REPLY_SECONDS for a, b in itertools.pairwise(error_times))


# ---- row 33: the engine's IV and Greeks on the chain (REQ-029 AC-2/AC-3/AC-4) --------------------------------------
# Inputs by hand: spot 25162.30, window 25050..25250 (tick_window: CE 100.50 + k, PE 200.25 + k). The 25050 CE at
# 100.50 is below its intrinsic 112.30, so the engine refuses it (a dash); every other cell is above intrinsic.
GREEK_KEYS = ("iv", "delta", "gamma", "theta", "vega")


def _numbers(node, path="") -> list[str]:
    """Every JSON number in a pushed body (ints are only counts: oi, oi_change, volume)."""
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in _numbers(v, f"{path}.{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in _numbers(v, f"{path}[{i}]")]
    return [path] if isinstance(node, (int, float)) and not isinstance(node, bool) else []


async def test_attack_3_pushed_iv_and_greeks_are_engine_strings_and_no_money_or_greek_is_a_json_number():
    """Attack 3: every priced cell carries IV and the four Greeks as strings; the refused 25050 CE (below intrinsic)
    is null, never 0; the only JSON numbers are the integer counts; the basis says the spot fallback (no bid/ask)."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert (body["greeks_basis"], body["greeks_missing"]) == ("SPOT_FALLBACK", None)
    cells = {row[s]["instrument_id"]: row[s] for row in body["rows"] for s in ("ce", "pe")}
    refused = cells.pop(cid("25050", "CE"))
    assert [refused[k] for k in GREEK_KEYS] == [None] * 5
    for cell in cells.values():
        assert all(isinstance(cell[k], str) for k in GREEK_KEYS), cell
        assert Decimal(cell["iv"]) > 0 and cell["iv"] == f"{Decimal(cell['iv']):.2f}"
    assert Decimal(cells[cid("25150", "CE")]["delta"]) > 0 > Decimal(cells[cid("25150", "PE")]["delta"])
    assert {p.rsplit(".", 1)[-1] for p in _numbers(body)} <= {"oi", "volume"}


async def test_attack_3_ltp_streams_every_second_while_iv_refreshes_at_most_every_oi_refresh_seconds():
    """Attack 3 / standing item (a): LTP changes push every second with the new fields on; the engine runs once at the
    start and again only when OI_REFRESH_SECONDS have passed (never per tick), and OI holds in between."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    runs_at_start = push.model_runs
    for offset in (1, 2, 3, 4):
        tick_window(provider, ltp_offset=offset)
        provider.tick(option_quote(cid("25150", "CE"), f"{102 + offset}.50", oi=1000 + offset))
        mono.now += 1.0
        await settle()
    runs_inside = push.model_runs
    pushes_inside = len(channel.sent)
    mono.now += 1.0  # 5 s since the first refresh
    tick_window(provider, ltp_offset=9)
    await settle()
    await close(channel, task)
    assert (runs_at_start, runs_inside, push.model_runs) == (ONE, ONE, TWO)
    assert pushes_inside == FIVE  # the first push and one per second for 4 seconds
    assert [m["rows"][2]["ce"]["oi"] for m in channel.sent[:FIVE]] == [1000] * FIVE
    assert all(m["rows"][2]["ce"]["iv"] is not None for m in channel.sent)


async def test_attack_3_a_new_window_contract_gets_its_iv_at_once_not_after_the_refresh():
    """Standing item (a): a re-centre brings contracts the last model never saw: the engine runs at once for them."""
    provider, _feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    task = await start(push, channel)
    runs = push.model_runs
    provider.tick(option_quote(cid("25300", "CE"), "40.00"))  # outside the window: not shown
    provider.tick(index_quote("25310.00"))
    for strike, ltp in (("25300", "60.00"), ("25350", "35.00"), ("25400", "20.00")):
        provider.tick(option_quote(cid(strike, "CE"), ltp))
    mono.now += 5.0
    await settle(10)
    await close(channel, task)
    assert push.model_runs > runs
    last = {row["strike"]: row for row in channel.sent[-1]["rows"]}
    assert last["25300.00"]["ce"]["iv"] is not None


@pytest.mark.parametrize(("state", "spot_health", "cell_health", "missing"), [
    ("live with LTP", DataHealth.AVAILABLE, DataHealth.AVAILABLE, None),
    ("cell stale (not priced)", DataHealth.AVAILABLE, DataHealth.STALE, None),
    ("spot unhealthy: forward refused", DataHealth.UNHEALTHY, DataHealth.AVAILABLE, "SPOT_REFUSED"),
])
async def test_standing_d_each_answer_state_gives_a_value_or_a_dash(state, spot_health, cell_health, missing):
    """Standing item (d): per answer state the ATM CE's IV is a value only when its own quote is priced and the spot
    is usable; otherwise a dash, with the chain-level reason when the engine could not run at all."""
    provider, _feed, channel, _mono, push = make_rig()
    provider.tick(index_quote("25162.30", health=spot_health))
    tick_window(provider, health=cell_health)
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    iv = body["rows"][2]["ce"]["iv"]
    assert body["greeks_missing"] == missing, state
    assert (iv is not None) == (missing is None and cell_health is DataHealth.AVAILABLE), state


async def test_standing_d_no_live_feed_and_spot_missing_carry_no_greeks_and_no_basis():
    """Standing item (d): NOT_CONNECTED and a spot-missing answer have no rows, no basis, no reason."""
    _provider, _feed, channel, _mono, push = make_rig()
    task = await start(push, channel)
    await close(channel, task)
    body = channel.sent[0]
    assert (body["rows"], body["rows_missing"], body["greeks_basis"], body["greeks_missing"]) == (
        [], "SPOT_MISSING", None, None)
    out = chain_push.chain_answer(None, ChainRequest(underlying="NIFTY", expiry=EXPIRY),
                                  ChainCatalogue(expiries=(EXPIRY,), contracts=CONTRACTS), None, live=False,
                                  now=Clock(T0))
    assert (out.state, out.greeks_basis, out.greeks_missing, out.rows) == ("NOT_CONNECTED", None, None, [])



# ---- row 33: REQ-029 AC-9 filters (server side) and the per-row moneyness ------------------------------------------
# Window 25050..25250 around ATM 25150 (spot 25162.30). tick_window gives OI 1000 / volume 500 everywhere, CE LTP
# 100.50 + k and PE 200.25 + k; each test then changes one cell by hand.

def _filtered_rig():
    provider, feed, channel, mono, push = make_rig()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    provider.tick(option_quote(cid("25200", "CE"), "103.50", oi=5000))
    provider.tick(option_quote(cid("25100", "PE"), "201.25", bid="201.00", ask="201.50"))
    return provider, feed, channel, mono, push


async def test_ac9_each_row_carries_its_moneyness_from_the_server_atm():
    """AC-9: the server marks each row on the calls' side against atm_strike; the screen filters by the word only."""
    _provider, _feed, channel, _mono, push = _filtered_rig()
    task = await start(push, channel)
    await close(channel, task)
    assert [r["moneyness"] for r in channel.sent[0]["rows"]] == ["ITM", "ITM", "ATM", "OTM", "OTM"]


@pytest.mark.parametrize(("extra", "strikes"), [
    ({}, ["25050.00", "25100.00", "25150.00", "25200.00", "25250.00"]),
    ({"min_oi": 2000}, ["25200.00"]),
    ({"min_volume": 501}, []),
    ({"min_ltp": "203.00"}, ["25200.00", "25250.00"]),
    ({"bid_and_ask": True}, ["25100.00"]),
    ({"min_oi": 2000, "bid_and_ask": True}, []),
])
async def test_ac9_socket_filters_narrow_the_rows_only_never_a_value_or_the_subscription(extra, strikes):
    """AC-9 / attack 6: a row stays when either side meets each filter; the kept rows' values are unchanged and the
    subscription is the whole window whatever the filters."""
    provider, _feed, channel, _mono, push = _filtered_rig()
    task = await start(push, channel, {**request(), **extra})
    held = set(provider.vendor_subscribed)
    await close(channel, task)
    body = channel.sent[0]
    assert [r["strike"] for r in body["rows"]] == strikes
    assert body["rows_missing"] is None
    if "25200.00" in strikes:
        row = next(r for r in body["rows"] if r["strike"] == "25200.00")
        assert (row["ce"]["ltp"], row["ce"]["oi"]) == ("103.50", 5000)
    window = {cid(str(k), s) for k in WINDOW_2 for s in ("CE", "PE")}
    assert window <= held


def test_ac9_rest_read_applies_the_same_filters_and_refuses_bad_ones():
    """AC-9: the first-paint REST read takes the same filters; a negative or non-number minimum is refused (422)."""
    provider = FakeProvider()
    provider.tick(index_quote("25162.30"))
    tick_window(provider)
    provider.tick(option_quote(cid("25200", "CE"), "103.50", oi=5000))
    client = _app_client(MarketContext(provider, Clock(T0), Decimal("0.065")), Reader())
    query = {"underlying": "NIFTY", "expiry": EXPIRY.isoformat(), "strikes_each_side": 2}
    ok = client.get("/api/market/chain", params={**query, "min_oi": "2000"})
    assert ok.status_code == HTTP_OK, ok.text
    assert [(r["strike"], r["moneyness"]) for r in ok.json()["rows"]] == [("25200.00", "OTM")]
    for bad in ({"min_oi": "-1"}, {"min_ltp": "-0.05"}, {"min_ltp": "nan"}, {"min_volume": "x"}):
        refused = client.get("/api/market/chain", params={**query, **bad})
        assert refused.status_code == HTTP_UNPROCESSABLE, (bad, refused.text)
